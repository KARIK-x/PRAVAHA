# KRONOS NABIL — FINAL GO/NO-GO DECISION
Date: 2026-10-17 | Read-only | No training performed

## 1. Exact Lookback, Stride, Sequence Construction

### From Official Code (finetune_csv/finetune_base_model.py)
- Lookback: 90 bars (configurable via lookback_window)
- Predict: 10 bars (configurable via predict_window)
- Window: 101 bars (lookback + predict + 1)
- Stride: 1 (sliding window, consecutive)
- Sequence construction: window_data = data.iloc[start_idx:start_idx+101]
  - x = window_data[feature_list] (90 input + 10 target? No — full window is 101)
  - The split between input and target happens in the model's forward pass
  - x is normalized (z-score) and clipped to ±5
  - x_stamp = time features (minute, hour, weekday, day, month)

### Training Dataset
- __len__(): n_samples = len(data) - window + 1
- __getitem__(idx):
  - max_start = len(data) - window
  - train: start_idx = (idx * 9973 + (epoch+1) * 104729) % (max_start + 1) [randomized per epoch]
  - val/test: start_idx = idx % (max_start + 1) [sequential]
  - end_idx = start_idx + window
  - window_data = data.iloc[start_idx:end_idx]
  - Returns: (x_tensor, x_stamp_tensor)

### Data Splitting (internal, single CSV)
- train_end = int(total_length * train_ratio)
- val_end = int(total_length * (train_ratio + val_ratio))
- train: data.iloc[:train_end]
- val: data.iloc[train_end:val_end]
- test: data.iloc[val_end:]
- No test DataLoader created (test_ratio=0.0 by default)

## 2. Target Leakage Analysis

### Target Leakage: NONE
- Each sequence's target (next 10 bars) is within the same split
- No target from val/test leaks into train
- The model sees 90 input bars and predicts 10 future bars
- No future target information in input windows

### Future-Data Leakage: NONE
- Input window: last 90 bars (historical only)
- Time features derived from bar's own timestamp
- Normalization uses window's own mean/std (not future data)
- No future-derived features

### Symbol Mixing: NONE
- Single symbol per CSV (no symbol column used by loader)
- Sequences are per-file (no cross-symbol mixing)

### Split Overlap: DOCUMENTED
- NABIL train: 2011-05-19 to 2022-12-29 (2,078 rows)
- NABIL val: 2022-09-01 to 2024-06-30 (416 rows)
- NABIL test: 2024-04-01 to 2025-06-30 (287 rows)
- Train/Val overlap: 71 dates (2022-09-01 to 2022-12-29) — input context for val
- Val/Test overlap: 57 dates (2024-04-01 to 2024-06-30) — input context for test
- Train/Test overlap: 0 dates
- This is the official Kronos split pattern (with lookback buffers)
- Val/test metrics may be optimistic due to overlap

### Important Note on Pre-Split Data
Our per-symbol CSVs are ALREADY split (train/val/test). The official loader
re-splits a single CSV internally. If we pass train+NABIL.csv alone, the
loader would split it 90/10/0 (train/val/test), which is DIFFERENT from
our pre-split files.

For the exploratory baseline, we should either:
A. Combine train+val+test into one CSV and let official code split (90/10/0)
B. Use train CSV only (90/10 split, no test set for training)
C. Modify the config to use our pre-split files (requires code changes)

Recommendation: Option A (combine all three into one CSV, let official code split)
This uses all data and follows the official pattern.

## 3. Sequence Count Verification

### NABIL Eligible Sequences
- Train: 1,978 sequences (2,078 rows - 101 + 1 = 1,978)
- Val: 316 sequences (416 rows - 101 + 1 = 316)
- Test: 187 sequences (287 rows - 101 + 1 = 187)
- Total: 2,481 sequences

### Reproducibility
- Sequence counts are deterministic (len(data) - window + 1)
- Training sequences use randomized start indices per epoch (data augmentation)
- Validation sequences use sequential start indices (idx % (max_start + 1))

## 4. Model/Tokenizer Compatibility

### Correct Pairing (from megatool/kronos_service.py)
| Model | Tokenizer | Context | Params |
|---|---|---|---|
| Kronos-mini | Kronos-Tokenizer-2k | 2048 | 4.1M |
| Kronos-small | Kronos-Tokenizer-base | 512 | 24.7M |
| Kronos-base | Kronos-Tokenizer-base | 512 | 102.3M |

### Official Code Support
- Uses config.finetuned_tokenizer_path for tokenizer
- Uses config.pretrained_predictor_path for model
- No hardcoded model names
- Supports Mini + Tokenizer-2k via configuration (no code changes)

### Verification
- CustomKlineDataset instantiated successfully with NABIL CSV
- Data length: 180, Available samples: 80 (with lookback=90, predict=10)
- Timestamps parsed correctly, sorting works, time features derived

## 5. Batch Size and Training Epochs

### Proposed Configuration
- tokenizer_epochs: 10 (official default: 30)
- basemodel_epochs: 5 (official default: 20)
- batch_size: 16 (official default: 32)
- accumulation_steps: 2 (to compensate for smaller batch)

### Support Verification
- All parameters are config-driven (no hardcoded values)
- batch_size: used in DataLoader (batch_size=config.batch_size)
- epochs: used in training loop (for epoch in range(config.training.tokenizer_epochs))
- No minimum/maximum constraints in code

### Recommendation for T4 GPU
- batch_size: 16 (reduce from 32 for T4 memory)
- tokenizer_epochs: 10 (reduce from 30 for faster iteration)
- basemodel_epochs: 5 (reduce from 20 for faster iteration)
- Early stopping: patience=3 on validation loss
- Gradient accumulation: 2 (to compensate for smaller batch)

## 6. Validation Metric and Naive Baseline

### Validation Metric
- Primary: MAE on close price (next 10 bars)
- The official code does not implement validation metrics directly
- Validation would need to be added to the training script
- OR: use the official code's built-in validation (if any)

### Naive Persistence Baseline
- For each prediction window: predict last observed close for all 10 future bars
- Calculate MAE between predicted and actual close prices
- Use exactly the same evaluation samples as Kronos
- This is the simplest possible baseline

### Scale-Aware Metrics
- MAE: mean absolute error (price-level)
- RMSE: root mean squared error (price-level)
- MAPE: mean absolute percentage error (relative)
- Direction accuracy: % of correct up/down predictions

### Hyperparameter Selection
- Must use validation set only (not test set)
- Test set used only for final evaluation
- No hyperparameter tuning on test set

## 7. Checkpoint Safety

### Checkpoint Directory
- Path: /kaggle/working/kronos_nepse/
- Separate from pretrained weights: YES (different directory)
- Cannot overwrite pretrained: YES
- Resume: skip_existing flag (if true, skip already-trained models)
- Official code creates directories with os.makedirs(..., exist_ok=True)

### Safety Verification
- Checkpoint dir is in /kaggle/working/ (Kaggle output directory)
- Pretrained weights are in /kaggle/input/ (read-only)
- No path overlap between checkpoint and pretrained
- Logs: rotating file handler in base_save_path/logs/

## 8. Final Decision

### READY_TO_START_EXPLORATORY_BASELINE

### Conditions
1. Must obtain official Kronos fine-tuning code from GitHub
2. Must use single-symbol CSV (NABIL.csv) — NOT combined CSV
3. Must label as "exploratory baseline" — NOT verified forecasting
4. Must document: no source verification, unadjusted prices, single symbol
5. Must NOT use for trading decisions or performance claims
6. Must save checkpoints to /kaggle/working/kronos_nepse/
7. Must not upload private data

### Exact Training Command
```bash
python finetune_csv/finetune_base_model.py --config nepse_nabil_config.yaml
```

### Exact Data Path
- Input: /kaggle/input/nepse-data/NABIL.csv (single symbol, combined train+val+test)
- OR: Use train CSV only with train_ratio=0.9, val_ratio=0.1, test_ratio=0.0

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

### What Can Proceed
- Clone official Kronos repo in Kaggle
- Download pretrained weights from HuggingFace
- Upload NABIL.csv to Kaggle dataset
- Run exploratory baseline (with conditions above)

### What Must Remain Blocked
- Production fine-tuning with unverified data
- Any claim of verified financial forecasting
- Use of suspect/invalid rows in training
- Representation of unadjusted prices as adjusted
- Kaggle upload of private data

### Safety
- No databases modified
- No training performed
- No GPU resources consumed
- No commits, pushes, or deployments
- Production port 8710 untouched
- All existing work preserved

### Report Created
- KRONOS_NABIL_PREFLIGHT.md (previous)
- KRONOS_FINAL_GO_NOGO.md (this report)
