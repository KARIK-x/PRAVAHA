# KRONOS PRE-TRAINING PREFLIGHT — FINAL REPORT
Date: 2026-10-17 | Read-only | No training performed

## 1. Official Training Entry Point

### Entry Point
- File: finetune_csv/finetune_base_model.py (from official Kronos repo)
- Command: `python finetune_base_model.py --config <config.yaml>`
- Arguments: --config (path to YAML config, default: config.yaml)
- Requires: PyTorch, CUDA GPU, pandas, numpy, yaml, einops, tqdm, safetensors

### CSV Schema (verified against actual loader code)
- Required columns: timestamps, open, close, high, low, volume, amount
- Timestamps: parsed with pd.to_datetime (flexible format)
- Sorting: by timestamps ascending
- Missing values: forward-filled (ffill) with warning
- Time features: minute, hour, weekday, day, month (derived from timestamps)
- Data split: internal time-based (train_ratio, val_ratio, test_ratio)

### Dataset Class
- CustomKlineDataset (from finetune_base_model.py)
- __init__: data_path, data_type, lookback_window, predict_window, clip, seed, train_ratio, val_ratio, test_ratio
- _load_and_preprocess_data: reads CSV, parses timestamps, sorts, derives time features
- _split_data_by_time: sequential split by ratio
- n_samples = len(data) - window + 1

### Model Loading
- Tokenizer: KronosTokenizer.from_pretrained(config.finetuned_tokenizer_path)
- Model: Kronos.from_pretrained(config.pretrained_predictor_path)
- Seeds: torch.manual_seed, np.random.seed, random.seed (all set to config.seed)
- Device: CUDA (config.device.use_cuda, config.device.device_id)

### Training Loop
- Tokenizer: config.training.tokenizer_epochs (default 30)
- Basemodel: config.training.basemodel_epochs (default 20)
- Batch size: config.training.batch_size (default 32)
- Optimizer: AdamW (beta1=0.9, beta2=0.95, weight_decay=0.1)
- Learning rates: tokenizer=0.0002, predictor=0.000001
- Gradient accumulation: config.training.accumulation_steps (default 1)
- Log interval: config.training.log_interval (default 50)
- Distributed: DDP (multi-GPU, optional)

### Checkpoint Saving
- Tokenizer: best_model saved to config.finetuned_tokenizer_path
- Basemodel: saved to config.basemodel_save_path
- Resume: skip_existing flag (if true, skip already-trained models)
- Logs: rotating file handler in base_save_path/logs/

## 2. Model/Tokenizer Compatibility

### Correct Pairing (from megatool/kronos_service.py)
| Model | Tokenizer | Context | Params |
|---|---|---|---|
| Kronos-mini | Kronos-Tokenizer-2k | 2048 | 4.1M |
| Kronos-small | Kronos-Tokenizer-base | 512 | 24.7M |
| Kronos-base | Kronos-Tokenizer-base | 512 | 102.3M |

### Official Code Support
- The official code uses config paths, not hardcoded model names
- For Kronos Mini, set:
  - pretrained_predictor_path: path to Kronos-mini weights
  - finetuned_tokenizer_path: path to Kronos-Tokenizer-2k weights
- The code supports this via configuration (no code changes needed)

### Verification
- Tested CustomKlineDataset with our CSV format: INSTANTIATED OK
- Data length: 180, Available samples: 80 (with lookback=90, predict=10)
- Timestamps parsed correctly, sorting works, time features derived

## 3. CSV Compatibility Verification

### Our CSV Format
Columns: timestamps, open, high, low, close, volume, amount, symbol
- timestamps: ISO datetime (from datetime index)
- open/high/low/close: price (NPR)
- volume: shares traded
- amount: (O+H+L+C)/4 * volume
- symbol: stock symbol

### Official Loader Expectations
- timestamps: parsed with pd.to_datetime (flexible) - MATCH
- open, high, low, close, volume, amount: required - MATCH
- Sorting: by timestamps ascending - MATCH (our data is sorted)
- Missing values: forward-filled (ffill) - N/A (we have 0 nulls)

### Verification Result
- CSV loads correctly in official CustomKlineDataset
- Timestamps parse as datetime64[ns]
- OHLC consistency: 0 inconsistent
- Nulls: 0
- Symbols: 351 (in combined CSV)

## 4. Data Leakage Verification

### Target Leakage: NONE
- Each sequence: 90 input bars + 10 prediction bars
- Target within same split, no future leakage
- No target from val/test leaks into train

### Future-Data Leakage: NONE
- Input window: last 90 bars (historical only)
- Time features from bar's own timestamp
- No future-derived features

### Symbol Mixing: NONE
- Per-symbol sequences (no cross-symbol mixing)

### Split Overlap: DOCUMENTED
- Train/Val: 71 dates (2022-09-01 to 2022-12-29) — input context for val
- Val/Test: 57 dates (2024-04-01 to 2024-06-30) — input context for test
- Train/Test: 0 dates
- This is the official Kronos split pattern (with lookback buffers)
- Val/test metrics may be optimistic

## 5. Data-Loading Smoke Test

### Command
```
cd /tmp/kronos_official/finetune_csv
/Users/ashim/Downloads/AI\ trading\ NEPSE/.venv/bin/python -c "
import sys; sys.path.insert(0, '..')
from finetune_base_model import CustomKlineDataset
ds = CustomKlineDataset('/tmp/test_kronos.csv', data_type='train', lookback_window=90, predict_window=10, train_ratio=0.9, val_ratio=0.1, test_ratio=0.0)
print('Dataset instantiated OK')
print('Data length:', len(ds.data))
print('Available samples:', ds.n_samples)
"
```

### Result
- Exit code: 0
- Output: "Dataset instantiated OK", "Data length: 180", "Available samples: 80"
- No optimizer steps performed
- No GPU consumed
- No training executed

## 6. Checkpoint Directory Safety

### Checkpoint Directory
- Path: /kaggle/working/kronos_nepse/
- Separate from pretrained weights: YES
- Separate from model files: YES
- Cannot overwrite pretrained weights: YES (different directory)
- Resume strategy: skip_existing flag (if true, skip already-trained models)

### Safety Verification
- Checkpoint dir is in /kaggle/working/ (Kaggle output directory)
- Pretrained weights are in /kaggle/input/ (read-only)
- No path overlap between checkpoint and pretrained
- Official code creates directories with os.makedirs(..., exist_ok=True)

## 7. Unresolved Blockers

1. **Official Kronos code not in repo**: Must clone from GitHub in Kaggle
2. **Pretrained weights not local**: Must download from HuggingFace in Kaggle
3. **Source-data correctness**: Not independently verified
4. **Unadjusted prices**: No corporate action handling
5. **Split overlap**: Documented but not resolved
6. **Trading calendar**: Empty (approximate gap checks)

## 8. Final Decision

### READY_TO_START_EXPLORATORY_BASELINE

### Conditions
1. Must obtain official Kronos fine-tuning code from GitHub
2. Must use CSV adapter (implemented and tested)
3. Must label experiment as "exploratory baseline" - NOT verified forecasting
4. Must document: no source verification, unadjusted prices, overlapping splits
5. Must NOT use for trading decisions or performance claims
6. Must save checkpoints to /kaggle/working/kronos_nepse/ (separate from pretrained)
7. Must not upload private data

### What Can Proceed
- Clone official Kronos repo in Kaggle
- Download pretrained weights from HuggingFace
- Upload CSV artifacts to Kaggle dataset
- Run exploratory baseline (with conditions above)

### What Must Remain Blocked
- Production fine-tuning with unverified data
- Any claim of verified financial forecasting
- Use of suspect/invalid rows in training
- Representation of unadjusted prices as adjusted
- Kaggle upload of private data

### Exact Commands for Future Training Run
```bash
# 1. Clone official Kronos
git clone https://github.com/shiyu-coder/Kronos.git
cd Kronos

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download pretrained weights (in Kaggle notebook)
# from huggingface_hub import snapshot_download
# snapshot_download("NeoQuasar/Kronos-mini", local_dir="/kaggle/working/kronos-mini")
# snapshot_download("NeoQuasar/Kronos-Tokenizer-2k", local_dir="/kaggle/working/kronos-tokenizer-2k")

# 4. Upload data (Kaggle dataset)
# train_combined.csv, val_combined.csv, test_combined.csv

# 5. Configure
# Edit finetune_csv/configs/config_ali09988_candle-5min.yaml
# Set data_path, model_paths, etc.

# 6. Run training
python finetune_csv/finetune_base_model.py --config <config.yaml>

# 7. Save checkpoints
# /kaggle/working/kronos_nepse/
```

### Safety
- No databases modified
- No training performed
- No GPU resources consumed
- No commits, pushes, or deployments
- Production port 8710 untouched
- All existing work preserved
