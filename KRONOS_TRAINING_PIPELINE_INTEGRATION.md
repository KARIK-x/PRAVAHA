# KRONOS TRAINING PIPELINE INTEGRATION — FINAL REPORT
Date: 2026-10-17 | No training performed

## 1. Official Kronos Fine-Tuning Implementation

### Available Locally (vendor/kronos/)
- model/kronos.py: Kronos model architecture
- model/module.py: Model modules
- tests/test_kronos_regression.py: Regression tests
- requirements.txt: numpy, pandas, torch>=2.0.0, einops, huggingface_hub, matplotlib, tqdm, safetensors

### NOT Available Locally
- No fine-tuning script in repository
- No training configuration files
- No checkpoint save/load utilities
- Official Kronos fine-tuning code must be obtained from: https://github.com/shiyu-coder/Kronos

### Official Kronos CSV Fine-Tuning (from cloned repo)
- Entry point: finetune_csv/finetune_base_model.py
- Config: finetune_csv/configs/config_ali09988_candle-5min.yaml
- Expected CSV columns: timestamps, open, close, high, low, volume, amount
- Data split: train_ratio (0.9), val_ratio (0.1), test_ratio (0.0) — single CSV, internal split
- Training: tokenizer (30 epochs) + basemodel (20 epochs)
- Device: CUDA GPU required
- Model paths: pretrained tokenizer + predictor from HuggingFace

### Qlib-Based Fine-Tuning (from cloned repo)
- Entry point: finetune/train_predictor.py
- Requires: Qlib installation, binary .bin data format
- Multi-symbol support via Qlib data handler
- More complex setup, not recommended for initial experiment

## 2. Artifact Compatibility

### Prepared Artifacts (read-only inspection)
| Artifact | Type | Symbols | Bars | Columns | Date Range |
|---|---|---|---|---|---|
| train_data.pkl | dict[str, DataFrame] | 351 | 214,760 | open, high, low, close, vol, amt | 2010-01-03 to 2022-12-29 |
| val_data.pkl | dict[str, DataFrame] | 351 | 98,022 | Same | 2022-09-01 to 2024-06-30 |
| test_data.pkl | dict[str, DataFrame] | 351 | 78,690 | Same | 2024-04-01 to 2025-06-30 |

### Compatibility Assessment
- Official Kronos CSV fine-tuning expects: timestamps, open, close, high, low, volume, amount
- Our data has: open, high, low, close, vol, amt (with datetime index)
- CONVERSION REQUIRED: column names (vol->volume, amt->amount) and index->timestamps column
- No Qlib conversion needed for CSV-based fine-tuning

## 3. Data Leakage Analysis

### Target Leakage: NONE
- Each sequence: 90 input bars + 10 prediction bars = 100 bars
- Target (next 10 bars) is within the same split
- No target from val/test leaks into train
- No future information in input windows

### Future-Data Leakage: NONE
- Input window: last 90 bars (historical only)
- Prediction target: next 10 bars (within same split)
- Time features derived from bar's own timestamp (not future)

### Symbol Mixing: NONE
- Sequences are per-symbol (no cross-symbol mixing)
- 351 symbols, each with independent sequences

### Split Overlap: DOCUMENTED
- Train/Val: 71 dates overlap (2022-09-01 to 2022-12-29) — input context for val
- Val/Test: 57 dates overlap (2024-04-01 to 2024-06-30) — input context for test
- Train/Test: 0 dates overlap
- This is the official Kronos split pattern (with lookback buffers)
- Val/test metrics may be optimistic due to overlap

### Conclusion
No target leakage or future-data leakage. Symbol mixing: none. Overlap is input context, not target leakage.

## 4. CSV Adapter Implementation

### Created Files
- data/kronos_audit/v2/adapter/convert_to_csv.py (adapter script)
- data/kronos_audit/v2/adapter/README.md (documentation)
- data/kronos_audit/v2/adapter/csv/ (output directory)
  - train_combined.csv (214,760 rows)
  - val_combined.csv (98,022 rows)
  - test_combined.csv (78,690 rows)
  - train/ (351 per-symbol CSVs)
  - val/ (351 per-symbol CSVs)
  - test/ (351 per-symbol CSVs)
  - manifest.json

### CSV Format
Columns: timestamps, open, high, low, close, volume, amount, symbol
- timestamps: ISO datetime (from datetime index)
- open/high/low/close: price (NPR)
- volume: shares traded
- amount: (O+H+L+C)/4 * volume
- symbol: stock symbol

### Adapter Usage
```bash
cd /Users/ashim/Downloads/AI\ trading\ NEPSE
.venv/bin/python data/kronos_audit/v2/adapter/convert_to_csv.py
```

## 5. Proposed Experiment Configuration

### Model and Tokenizer
- Model: Kronos Mini (from HuggingFace: shiyu-coder/Kronos-Mini)
- Tokenizer: Kronos-Tokenizer-base (from HuggingFace)
- Device: GPU (Kaggle T4 or P100)

### Training Entry Point
- Official Kronos: finetune_csv/finetune_base_model.py
- Config template: finetune_csv/configs/config_ali09988_candle-5min.yaml

### Configuration (adapted for NEPSE)
```yaml
data:
  data_path: "/kaggle/input/nepse-data/train_combined.csv"
  lookback_window: 90
  predict_window: 10
  max_context: 512
  clip: 5.0
  train_ratio: 0.9
  val_ratio: 0.1
  test_ratio: 0.0

training:
  tokenizer_epochs: 30
  basemodel_epochs: 20
  batch_size: 32
  log_interval: 50
  num_workers: 4
  seed: 42
  tokenizer_learning_rate: 0.0002
  predictor_learning_rate: 0.000001
  adam_beta1: 0.9
  adam_beta2: 0.95
  adam_weight_decay: 0.1
  accumulation_steps: 1

model_paths:
  pretrained_tokenizer: "/kaggle/input/kronos-pretrained/Kronos-Tokenizer-base"
  pretrained_predictor: "/kaggle/input/kronos-pretrained/Kronos-Mini"
  exp_name: "nepse_mini_finetune"
  base_path: "/kaggle/working/kronos_nepse"
  base_save_path: ""
  finetuned_tokenizer: ""
  tokenizer_save_name: "tokenizer"
  basemodel_save_name: "basemodel"

experiment:
  name: "kronos_nepse_exploratory"
  description: "Exploratory baseline for NEPSE daily data"
  use_comet: false
  train_tokenizer: true
  train_basemodel: true
  skip_existing: false

device:
  use_cuda: true
  device_id: 0
```

### Validation Metric
- Primary: MAE on close price (next 10 bars)
- Secondary: MSE, R2
- Baseline comparison: naive persistence (yesterday's close)

### Checkpoint Output
- Directory: /kaggle/working/kronos_nepse/
- Format: PyTorch state_dict
- Save: best validation checkpoint only

### Estimated Runtime
- Training: 2-4 hours (351 symbols, 214K train bars, 30+20 epochs)
- Uncertainty: High (depends on GPU, batch size, convergence)

### Baseline Comparison
- Naive persistence: predict yesterday's close
- Kronos pre-trained: zero-shot forecast
- Kronos fine-tuned: fine-tuned forecast
- Compare MAE/RMSE on test set

## 6. Kaggle Workflow

### Steps for Owner
1. Upload train_combined.csv, val_combined.csv, test_combined.csv to Kaggle dataset
2. Upload prepare.py for reproducibility
3. Create Kaggle notebook with GPU (T4 or P100)
4. Clone official Kronos repo in notebook
5. Download pretrained weights from HuggingFace
6. Run fine-tuning with the config above
7. Save checkpoints to /kaggle/working/
8. Download results

### Do NOT Upload
- Private trading records
- API keys or secrets
- Personal financial data
- Production databases

## 7. Final GO/NO-GO Decision

### READY_TO_LAUNCH (for exploratory baseline only)

Conditions:
1. Must obtain official Kronos fine-tuning code from GitHub
2. Must use the CSV adapter (already implemented)
3. Must label experiment as "exploratory baseline" - NOT verified forecasting
4. Must document: no source verification, unadjusted prices, overlapping splits
5. Must NOT use for trading decisions or performance claims
6. Must save checkpoints separately from production
7. Must not upload private data

### What Can Proceed
- Obtaining official Kronos fine-tuning code
- Using the CSV adapter (implemented)
- Running exploratory baseline (with conditions above)

### What Must Remain Blocked
- Production fine-tuning with unverified data
- Any claim of verified financial forecasting
- Use of suspect/invalid rows in training
- Representation of unadjusted prices as adjusted
- Kaggle upload of private data

### Report Created
- KRONOS_PRE_TRAINING_CHECKS.md (161 lines)
- KRONOS_EXPLORATORY_BASELINE_REVIEW.md (161 lines)

### Safety
- No databases modified
- No training performed
- No GPU resources consumed
- No commits, pushes, or deployments
- Production port 8710 untouched
- All existing work preserved
