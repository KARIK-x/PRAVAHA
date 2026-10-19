# KRONOS NABIL SINGLE-SYMBOL TRAINING PREFLIGHT
Date: 2026-10-17 | Read-only | No training performed

## 1. Official Kronos CSV Fine-Tuning Entry Point

### Entry Point
- File: finetune_csv/finetune_base_model.py (from official Kronos repo)
- Command: `python finetune_base_model.py --config <config.yaml>`
- Arguments: --config (path to YAML config, default: config.yaml)
- Requires: PyTorch, CUDA GPU, pandas, numpy, yaml, einops, tqdm, safetensors

### CSV Schema (verified against actual loader code)
- Required columns: timestamps, open, close, high, low, volume, amount
- Timestamps: parsed with pd.to_datetime (flexible format)
- Sorting: by timestamps ascending (reset_index drop=True)
- Missing values: forward-filled (ffill) with warning
- Time features: minute, hour, weekday, day, month (derived from timestamps)
- Data split: internal time-based (train_ratio, val_ratio, test_ratio)

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

### Verification
- Official code uses config paths, not hardcoded model names
- For Kronos Mini, set:
  - pretrained_predictor_path: path to Kronos-mini weights
  - finetuned_tokenizer_path: path to Kronos-Tokenizer-2k weights
- The code supports this via configuration (no code changes needed)
- Data-loading smoke test: CustomKlineDataset instantiated OK (180 bars, 80 samples)

## 3. NABIL Data Verification

### Files
| Split | Path | Rows | Date Range | Symbols |
|---|---|---|---|---|
| Train | data/kronos_audit/v2/adapter/csv/train/NABIL.csv | 2,078 | 2011-05-19 to 2022-12-29 | NABIL only |
| Val | data/kronos_audit/v2/adapter/csv/val/NABIL.csv | 416 | 2022-09-01 to 2024-06-30 | NABIL only |
| Test | data/kronos_audit/v2/adapter/csv/test/NABIL.csv | 287 | 2024-04-01 to 2025-06-30 | NABIL only |

### Quality Checks
- Nulls: 0
- Duplicate timestamps: 0
- OHLC inconsistent: 0
- Non-positive prices: 0
- Negative volume: 0
- Sorted by timestamps: True
- Single symbol: NABIL only (verified)

### Eligible Sequences (window=101)
- Train: 1,978 sequences
- Val: 316 sequences
- Test: 187 sequences

## 4. Evaluation

### Split Leakage Analysis
- Train/Val overlap: 71 dates (2022-09-01 to 2022-12-29)
  - These dates appear in BOTH train and val
  - In train: as target observations
  - In val: as input context (lookback window)
  - This is the official Kronos split pattern
  - Val metrics may be optimistic
- Val/Test overlap: 57 dates (2024-04-01 to 2024-06-30)
  - Same pattern as train/val
  - Test metrics may be optimistic
- Train/Test overlap: 0 dates

### Naive Persistence Baseline
- For each prediction window: predict last observed close for all 10 future bars
- Calculate MAE and RMSE between predicted and actual close prices
- Use exactly the same evaluation samples as Kronos

### Scale-Aware Metrics
- MAE: mean absolute error (price-level)
- RMSE: root mean squared error (price-level)
- MAPE: mean absolute percentage error (relative)
- Direction accuracy: % of correct up/down predictions

### Limitations
- Prices are unadjusted (no corporate action handling)
- No independent source verification
- Split overlap may inflate metrics
- Trading calendar unavailable (approximate gap checks)

## 5. Proposed Configuration

### Exact Config (Kronos Mini + Tokenizer-2k)
```yaml
data:
  data_path: "/kaggle/input/nepse-data/NABIL.csv"
  lookback_window: 90
  predict_window: 10
  max_context: 512
  clip: 5.0
  train_ratio: 0.9
  val_ratio: 0.1
  test_ratio: 0.0

training:
  tokenizer_epochs: 10
  basemodel_epochs: 5
  batch_size: 16
  log_interval: 50
  num_workers: 4
  seed: 42
  tokenizer_learning_rate: 0.0002
  predictor_learning_rate: 0.000001
  adam_beta1: 0.9
  adam_beta2: 0.95
  adam_weight_decay: 0.1
  accumulation_steps: 2

model_paths:
  pretrained_tokenizer: "/kaggle/working/kronos-tokenizer-2k"
  pretrained_predictor: "/kaggle/working/kronos-mini"
  exp_name: "nepse_nabil_exploratory"
  base_path: "/kaggle/working/kronos_nepse"
  base_save_path: ""
  finetuned_tokenizer: ""
  tokenizer_save_name: "tokenizer"
  basemodel_save_name: "basemodel"

experiment:
  name: "kronos_nepse_single_symbol"
  description: "Exploratory baseline for NABIL single symbol"
  use_comet: false
  train_tokenizer: true
  train_basemodel: true
  skip_existing: false

device:
  use_cuda: true
  device_id: 0
```

### Checkpoint Directory
- Path: /kaggle/working/kronos_nepse/
- Separate from pretrained weights: YES
- Resume: skip_existing flag

## 6. Kaggle Workflow

### Steps
1. Upload NABIL.csv to Kaggle dataset
2. Create Kaggle notebook with GPU (T4 or P100)
3. Clone official Kronos repo
4. Download pretrained weights from HuggingFace:
   - NeoQuasar/Kronos-mini
   - NeoQuasar/Kronos-Tokenizer-2k
5. Run fine-tuning with the config above
6. Save checkpoints to /kaggle/working/kronos_nepse/
7. Download results

### Exact Command
```bash
python finetune_csv/finetune_base_model.py --config <config.yaml>
```

## 7. Final Decision

### READY_TO_START_EXPLORATORY_BASELINE (single-symbol)

### Conditions
1. Must obtain official Kronos fine-tuning code from GitHub
2. Must use single-symbol CSV (NABIL.csv)
3. Must label as "exploratory baseline" - NOT verified forecasting
4. Must document: no source verification, unadjusted prices, single symbol
5. Must NOT use for trading decisions or performance claims

### Safety
- No databases modified
- No training performed
- No GPU resources consumed
- No commits, pushes, or deployments
- Production port 8710 untouched
- All existing work preserved

### Report Created
- KRONOS_PREFLIGHT_FINAL.md (previous)
- KRONOS_MULTISYMBOL_COMPATIBILITY_ISSUE.md (previous)
- This report (final preflight)
