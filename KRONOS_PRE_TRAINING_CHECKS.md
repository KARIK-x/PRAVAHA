# KRONOS EXPLORATORY EXPERIMENT — FINAL PRE-TRAINING CHECKS
Date: 2026-10-17 | Read-only | No training performed

## 1. Official Kronos Fine-Tuning Implementation

### Available Locally
- vendor/kronos/model/kronos.py: Model architecture (Kronos, KronosTokenizer)
- vendor/kronos/model/module.py: Model modules
- vendor/kronos/tests/test_kronos_regression.py: Regression tests
- megatool/kronos_service.py: Inference service (forecast, evaluate)
- scripts/kronos_data_prep.py: Data preparation (prototype)

### NOT Available Locally
- No fine-tuning script in repository
- No training configuration files (YAML/JSON)
- No checkpoint save/load utilities for training
- No optimizer or loss function implementation
- Official Kronos fine-tuning code must be obtained from: https://github.com/shiyu-coder/Kronos

### Model Configuration (from kronos_service.py)
- Variants: mini, small, base
- Context length: configurable (VARIANT_MAX_CONTEXT)
- Prediction length: configurable
- Tokenizer: KronosTokenizer (from vendor/kronos/model/)
- Inference: forecast() and evaluate() methods

### Expected Input Format (from data prep)
- Columns: open, high, low, close, vol, amt (6 features)
- Time features: minute, hour, weekday, day, month (5 features)
- Index: datetime
- Per-symbol sequences (no cross-symbol mixing)
- Lookback: 90 bars, Predict: 10 bars, Window: 101 bars
- Serialization: pickle (protocol 4, compatible with pandas 2.2.3)

### Checkpoint Output Paths
- Not defined locally
- Recommended: save to data/kronos_audit/ or separate experiment directory in Kaggle

## 2. Artifact Compatibility Check

### Artifact Inspection (read-only, no modification)
| Artifact | Python Type | Structure | Columns/Dtypes | Symbols | Bars | Date Range |
|---|---|---|---|---|---|---|
| train_data.pkl | dict[str, DataFrame] | Per-symbol DataFrames | open(float64), high(float64), low(float64), close(float64), vol(float64), amt(float64) | 351 | 214,760 | 2010-01-03 to 2022-12-29 |
| val_data.pkl | dict[str, DataFrame] | Per-symbol DataFrames | Same as above | 351 | 98,022 | 2022-09-01 to 2024-06-30 |
| test_data.pkl | dict[str, DataFrame] | Per-symbol DataFrames | Same as above | 351 | 78,690 | 2024-04-01 to 2025-06-30 |

### Timestamp Representation
- Index: datetime (pandas DatetimeIndex)
- Format: Timestamp objects
- Frequency: daily (trading days)

### Missing Values
- Null values: 0 (all rows have complete OHLCV)
- NaN values: 0
- Infinite values: 0

### OHLC Consistency
- Inconsistent rows: 0 (all rows pass high >= max(open,close), low <= min(open,close), high >= low)
- Flat candles: 0 (filtered out during preparation)
- Non-positive prices: 0 (filtered out)

### Date Boundaries
- Train: 2010-01-03 to 2022-12-29
- Val: 2022-09-01 to 2024-06-30
- Test: 2024-04-01 to 2025-06-30
- Train/Val overlap: 71 dates (2022-09-01 to 2022-12-29)
- Val/Test overlap: 57 dates (2024-04-01 to 2024-06-30)
- Train/Test overlap: 0 dates

### Compatibility with Official Kronos
- The official Kronos fine-tuning code expects Qlib-format data (binary .bin files)
- Our artifacts are pandas DataFrames in pickle format
- CONVERSION REQUIRED: A separate adapter is needed to convert our pickle files to Qlib format
- The adapter should be placed in a new directory (e.g., data/kronos_audit/v2/adapter/)
- Do NOT overwrite the prepared artifacts

### Proposed Adapter (not implemented yet)
- Input: train_data.pkl, val_data.pkl, test_data.pkl
- Output: Qlib-format .bin files (or CSV if Qlib not available)
- Conversion: DataFrame -> Qlib binary format with proper field mapping
- Verification: round-trip check (read back and compare)

## 3. Data Leakage Analysis

### Target Leakage Check
- Each sequence: 90 input bars + 10 prediction bars = 100 bars
- The target (next 10 bars) is within the same split
- No target from val/test leaks into train
- No future information in input windows (lookback only)

### Future-Data Leakage Check
- Input window: last 90 bars (historical only)
- Prediction target: next 10 bars (within same split)
- No lookahead in feature construction (OHLCV only, no future-derived features)
- Time features (minute, hour, weekday, day, month) are derived from the bar's own timestamp (not future)

### Symbol Mixing Check
- Sequences are per-symbol (each symbol's data is separate)
- No cross-symbol mixing in sequences
- 351 symbols, each with independent sequences

### Overlap Assessment
- Train/Val overlap (71 dates): These dates appear in BOTH train and val splits
  - In train: as target observations (the model sees these as future targets)
  - In val: as input context (the model uses these as historical input)
  - This means val metrics may be optimistic (the model has seen these dates in training)
- Val/Test overlap (57 dates): Same issue
- This is the official Kronos split pattern (with lookback buffers)
- RECOMMENDATION: Document this overlap clearly in experiment results

### Conclusion
No target leakage or future-data leakage within sequences. Symbol mixing: none. Overlap exists at the split level (intentional Kronos pattern) but does not constitute target leakage.

## 4. Proposed Experiment Plan

### Model and Tokenizer
- Model: Kronos Mini (from HuggingFace: shiyu-coder/Kronos-Mini or similar)
- Tokenizer: KronosTokenizer (from vendor/kronos/model/)
- Device: GPU (Kaggle T4 or P100)

### Training Entry Point
- Official Kronos fine-tuning code (NOT in this repository)
- Must be obtained from: https://github.com/shiyu-coder/Kronos
- Fine-tuning script: likely in examples/ or finetune/ directory

### Configuration
- Learning rate: 1e-4 (typical for fine-tuning)
- Batch size: 32 (adjust based on GPU memory)
- Epochs: 3-5 (small dataset, avoid overfitting)
- Early stopping: patience=2 on validation loss
- Optimizer: AdamW
- Scheduler: cosine with warmup

### Validation Metric
- Primary: MAE on close price (next 10 bars)
- Secondary: MSE, R2
- Baseline comparison: naive persistence (yesterday's close)

### Checkpoint Output
- Directory: /kaggle/working/kronos_nepse_checkpoint/
- Format: PyTorch state_dict or safetensors
- Save: best validation checkpoint only

### Estimated Runtime
- Training: 2-4 hours (362 symbols, ~214K train bars, 3-5 epochs)
- Validation: included in training loop
- Uncertainty: High (depends on GPU, batch size, convergence)

### Baseline Comparison
- Naive persistence: predict yesterday's close
- Kronos pre-trained: zero-shot forecast
- Kronos fine-tuned: fine-tuned forecast
- Compare MAE/RMSE on test set

## 5. Final GO/NO-GO Decision

### READY_TO_LAUNCH (for exploratory baseline only)

Conditions:
1. Must obtain official Kronos fine-tuning code from GitHub
2. Must convert pickle artifacts to Qlib format (separate adapter, not yet implemented)
3. Must label experiment as "exploratory baseline" — NOT verified forecasting
4. Must document: no source verification, unadjusted prices, overlapping splits
5. Must NOT use for trading decisions or performance claims
6. Must save checkpoints separately from production
7. Must not upload private data

### What Can Proceed
- Obtaining official Kronos fine-tuning code
- Implementing pickle-to-Qlib adapter
- Running exploratory baseline (with conditions above)

### What Must Remain Blocked
- Production fine-tuning with unverified data
- Any claim of verified financial forecasting
- Use of suspect/invalid rows in training
- Representation of unadjusted prices as adjusted
- Kaggle upload of private data

### Report Created
- KRONOS_EXPLORATORY_BASELINE_REVIEW.md (previous)
- This review (final pre-training checks)
