# KRONOS TRAINING PIPELINE — FINAL QUALITY GATE
Date: 2026-10-17 | Read-only | No training performed

## 1. Official Kronos Fine-Tuning Implementation

### Entry Point
- File: finetune_csv/finetune_base_model.py (from cloned official repo)
- Command: python finetune_base_model.py --config <config.yaml>
- Requires: PyTorch, CUDA GPU, pandas, numpy, yaml

### CSV Schema (from _load_and_preprocess_data)
- Required columns: timestamps, open, high, low, close, volume, amount
- Timestamps: parsed with pd.to_datetime (flexible format)
- Sorting: by timestamps ascending
- Missing values: forward-filled (ffill) with warning
- Time features: minute, hour, weekday, day, month (derived from timestamps)

### Model Loading (from code inspection)
- Tokenizer: KronosTokenizer.from_pretrained(config.finetuned_tokenizer_path)
- Model: Kronos.from_pretrained(config.pretrained_predictor_path)
- Seeds: torch.manual_seed, np.random.seed, random.seed (all set to config.seed)
- Device: CUDA (config.device.use_cuda, config.device.device_id)

### Training Loop
- Tokenizer: 30 epochs (config.training.tokenizer_epochs)
- Basemodel: 20 epochs (config.training.basemodel_epochs)
- Batch size: 32 (config.training.batch_size)
- Optimizer: AdamW (beta1=0.9, beta2=0.95, weight_decay=0.1)
- Learning rates: tokenizer=0.0002, predictor=0.000001
- Gradient accumulation: 1 step
- Log interval: 50 batches
- Distributed: DDP (multi-GPU, optional)

### Checkpoint Saving
- Tokenizer: best_model saved to config.finetuned_tokenizer_path
- Basemodel: saved to config.basemodel_save_path
- Resume: skip_existing flag (if true, skip already-trained models)
- Logs: rotating file handler in base_save_path/logs/

### Data Splitting (internal, single CSV)
- train_ratio: 0.9 (90% of data for training)
- val_ratio: 0.1 (10% for validation)
- test_ratio: 0.0 (0% for test)
- Split is by time (sequential, not random)
- train_end = int(total_length * train_ratio)
- val_end = int(total_length * (train_ratio + val_ratio))

## 2. Model/Tokenizer Compatibility

### Correct Pairing (from megatool/kronos_service.py)
| Model | Tokenizer | Context | Params |
|---|---|---|---|
| Kronos-mini | Kronos-Tokenizer-2k | 2048 | 4.1M |
| Kronos-small | Kronos-Tokenizer-base | 512 | 24.7M |
| Kronos-base | Kronos-Tokenizer-base | 512 | 102.3M |

### Important Finding
The config template (config_ali09988_candle-5min.yaml) uses:
- pretrained_tokenizer: Kronos-Tokenizer-base
- pretrained_predictor: Kronos-base

For Kronos Mini, the correct tokenizer is Kronos-Tokenizer-2k, NOT base.
The official fine-tuning code supports this because it uses config paths,
not hardcoded model names. The user must set:
- pretrained_predictor_path: path to Kronos-mini weights
- finetuned_tokenizer_path: path to Kronos-Tokenizer-2k weights

### Recommendation
Use Kronos Mini + Kronos-Tokenizer-2k. The official code supports this
via configuration (no code changes needed).

## 3. Prepared Data Verification

### Artifact Inspection (read-only)
| Artifact | Type | Symbols | Bars | Columns | Date Range |
|---|---|---|---|---|---|
| train_data.pkl | dict[str, DataFrame] | 351 | 214,760 | open, high, low, close, vol, amt | 2010-01-03 to 2022-12-29 |
| val_data.pkl | dict[str, DataFrame] | 351 | 98,022 | Same | 2022-09-01 to 2024-06-30 |
| test_data.pkl | dict[str, DataFrame] | 351 | 78,690 | Same | 2024-04-01 to 2025-06-30 |

### Checksum Verification
- train_data.pkl: MATCH
- val_data.pkl: MATCH
- test_data.pkl: MATCH
- prep_report.json: MATCH

### Quality Verification
- Null values: 0
- OHLC inconsistent: 0
- Flat candles: 0
- Negative volume: 0
- Zero volume: 0
- Feature columns: correct (6 features)
- Symbol separation: no cross-symbol mixing
- Chronological ordering: verified for all symbols

### CSV Adapter Output
- train_combined.csv: 214,760 rows, 351 symbols
- val_combined.csv: 98,022 rows, 351 symbols
- test_combined.csv: 78,690 rows, 351 symbols
- Columns: timestamps, open, high, low, close, volume, amount, symbol
- Manifest saved

## 4. Data Leakage Verification

### Target Leakage: NONE
- Each sequence: 90 input bars + 10 prediction bars
- Target within same split, no future leakage
- No target from val/test in train

### Future-Data Leakage: NONE
- Input window: last 90 bars (historical only)
- Time features from bar's own timestamp
- No future-derived features

### Symbol Mixing: NONE
- Per-symbol sequences (no cross-symbol mixing)

### Split Overlap: DOCUMENTED
- Train/Val: 71 dates (input context for val)
- Val/Test: 57 dates (input context for test)
- Train/Test: 0 dates
- This is the official Kronos split pattern (with lookback buffers)
- Val/test metrics may be optimistic

## 5. Experiment Design Validation

### Proposed Configuration
| Parameter | Value | Source |
|---|---|---|
| lookback_window | 90 | Official Kronos default |
| predict_window | 10 | Official Kronos default |
| max_context | 512 | Official config |
| clip | 5.0 | Official Kronos default |
| train_ratio | 0.9 | Official config |
| val_ratio | 0.1 | Official config |
| test_ratio | 0.0 | Official config |
| tokenizer_epochs | 30 | Official config |
| basemodel_epochs | 20 | Official config |
| batch_size | 32 | Official config (adjust for T4) |
| seed | 42 | Official config |

### Recommendation: Conservative Configuration for T4
- batch_size: 16 (reduce from 32 for T4 memory)
- tokenizer_epochs: 10 (reduce from 30 for faster iteration)
- basemodel_epochs: 5 (reduce from 20 for faster iteration)
- Early stopping: patience=3 on validation loss
- Gradient accumulation: 2 (to compensate for smaller batch)

### Validation Metric
- Primary: MAE on close price (next 10 bars)
- Secondary: MSE, R2
- Baseline: naive persistence (yesterday's close)

### Naive Persistence Definition
- For each prediction window, predict the last observed close for all 10 future bars
- Calculate MAE between predicted and actual close prices
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

## 6. Source Data Limitations (Preserved)

1. **No independent source verification**: Single community source
2. **Unadjusted prices**: No corporate action handling
3. **No trading calendar**: Gap checks approximate
4. **Split overlap**: Intentional Kronos pattern, may inflate metrics
5. **Suspect rows quarantined**: 64,124 rows not in training data
6. **Invalid rows excluded**: 19 rows excluded

## 7. Final Quality Gate Decision

### A. READY_TO_LAUNCH_EXPLORATORY_BASELINE

### Conditions Met
1. Official Kronos implementation inspected (entry point, args, schema, training loop, checkpointing)
2. Model/tokenizer compatibility resolved (Mini + Tokenizer-2k, supported by config paths)
3. Prepared data verified (checksums, counts, columns, OHLC, nulls, ordering, symbol separation)
4. Data leakage verified (no target leakage, no future leakage, no symbol mixing)
5. Experiment design validated (conservative config for T4, validation metrics defined)
6. Source limitations documented (no source verification, unadjusted prices, etc.)
7. Artifacts not modified (all checksums match)

### What Can Proceed
- Obtaining official Kronos fine-tuning code from GitHub
- Using the CSV adapter (implemented and tested)
- Running exploratory baseline (with conditions)

### What Must Remain Blocked
- Production fine-tuning with unverified data
- Any claim of verified financial forecasting
- Use of suspect/invalid rows in training
- Representation of unadjusted prices as adjusted
- Kaggle upload of private data

### Exact Files Created
- data/kronos_audit/v2/adapter/convert_to_csv.py (CSV adapter)
- data/kronos_audit/v2/adapter/README.md (documentation)
- data/kronos_audit/v2/adapter/csv/ (output directory with CSVs and manifest)
- KRONOS_FINAL_GO_NOGO_REVIEW.md (previous review)
- KRONOS_PRE_TRAINING_CHECKS.md (pre-training checks)
- KRONOS_TRAINING_PIPELINE_INTEGRATION.md (pipeline integration)
- KRONOS_TRAINING_DATA_REMEDIATION_REPORT.md (remediation report)

### Exact Commands for Future Training Run
```bash
# 1. Obtain official Kronos code
git clone https://github.com/shiyu-coder/Kronos.git
cd Kronos
pip install -r requirements.txt

# 2. Download pretrained weights
# Kronos-Mini: https://huggingface.co/NeoQuasar/Kronos-mini
# Kronos-Tokenizer-2k: https://huggingface.co/NeoQuasar/Kronos-Tokenizer-2k

# 3. Upload data to Kaggle
# train_combined.csv, val_combined.csv, test_combined.csv
# (from data/kronos_audit/v2/adapter/csv/)

# 4. Configure
# Edit finetune_csv/configs/config_ali09988_candle-5min.yaml
# Set data_path, model_paths, etc.

# 5. Run training
python finetune_csv/finetune_base_model.py --config <config.yaml>

# 6. Save checkpoints
# /kaggle/working/kronos_nepse/
```

### Safety
- No databases modified
- No training performed
- No GPU resources consumed
- No commits, pushes, or deployments
- Production port 8710 untouched
- All existing work preserved
