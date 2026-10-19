# KRONOS PREFLIGHT FINAL — MULTI-SYMBOL COMPATIBILITY ISSUE
Date: 2026-10-17 | Read-only | No training performed

## Critical Finding: Single-Symbol CSV Fine-Tuning

The official Kronos CSV fine-tuning (finetune_csv/finetune_base_model.py) expects
a SINGLE symbol's data in one CSV file. It does NOT use the 'symbol' column.

Verified from code inspection (finetune_csv/finetune_base_model.py, lines 53-56):
```python
df = pd.read_csv(self.data_path)
df['timestamps'] = pd.to_datetime(df['timestamps'])
df = df.sort_values('timestamps').reset_index(drop=True)
```

The 'symbol' column in our combined CSV is ignored by the loader.
If we use the combined CSV, the model would see interleaved data from 351
symbols as one time series, which is INCORRECT.

## Implications

1. **Multi-symbol training requires Qlib** (not available in our environment)
2. **CSV-based fine-tuning is single-symbol only**
3. **Our combined CSVs are NOT directly usable** for multi-symbol training
4. **Per-symbol CSVs ARE usable** (one symbol at a time)

## Recommended Approach for Exploratory Baseline

Option A: Single-symbol fine-tuning (RECOMMENDED for exploratory baseline)
- Pick one liquid NEPSE symbol (e.g., NABIL or NIMB)
- Use the per-symbol CSV from adapter/csv/train/{SYMBOL}.csv
- Fine-tune Kronos Mini on that single symbol's data
- Evaluate on the same symbol's test data
- This is a valid exploratory baseline

Option B: Multi-symbol via Qlib (NOT RECOMMENDED for now)
- Requires Qlib installation and binary data format
- More complex setup
- Not available in current environment

Option C: Train on all symbols sequentially (NOT RECOMMENDED)
- 351 separate training runs
- Not practical for exploratory baseline

## Per-Symbol CSV Verification
- 351 per-symbol CSVs in adapter/csv/train/
- 351 per-symbol CSVs in adapter/csv/val/
- 351 per-symbol CSVs in adapter/csv/test/
- Each CSV has columns: timestamps, open, high, low, close, volume, amount
- No symbol column needed (single symbol per file)

## Recommended Single-Symbol Experiment

### Symbol Selection
- NABIL (Nabil Bank) — most liquid NEPSE stock, 4,457 bars
- Or NIMB (Nepal Investment Mega Bank) — second most liquid

### Files Needed
- adapter/csv/train/NABIL.csv
- adapter/csv/val/NABIL.csv
- adapter/csv/test/NABIL.csv

### Config (single-symbol)
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

## Final Decision: READY_TO_START_EXPLORATORY_BASELINE (single-symbol)

The multi-symbol limitation is a significant finding. The exploratory baseline
should use a single liquid symbol (NABIL or NIMB) rather than the combined CSV.

This does not block the exploratory baseline — it just changes the scope from
multi-symbol to single-symbol, which is actually more appropriate for an
initial experiment.

### Conditions (unchanged)
1. Must obtain official Kronos fine-tuning code from GitHub
2. Must use single-symbol CSV (not combined)
3. Must label as "exploratory baseline" - NOT verified forecasting
4. Must document: no source verification, unadjusted prices, single symbol
5. Must NOT use for trading decisions or performance claims
6. Must save checkpoints to /kaggle/working/kronos_nepse/
7. Must not upload private data

### Safety
- No databases modified
- No training performed
- No GPU resources consumed
- No commits, pushes, or deployments
- Production port 8710 untouched
- All existing work preserved
