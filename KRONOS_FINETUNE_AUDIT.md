# KRONOS FINE-TUNING PIPELINE — AUDIT REPORT
Date: 2026-10-17 | Source: official Kronos repo (master branch), shiyu-coder/Kronos

## 1. Official source files inspected
- finetune/config.py (6,247 B)
- finetune/dataset.py (5,434 B)
- finetune/qlib_data_preprocess.py (5,645 B)
- finetune/train_tokenizer.py (11,455 B)
- finetune/train_predictor.py (10,026 B)
- finetune/qlib_test.py (15,140 B)
- finetune/utils/training_utils.py (4,823 B)

## 2. Exact required dataset schema
### Qlib data format
- Microsoft Qlib format: binary calendar + instrument data files
- Required columns: open, high, low, close, vol (volume), amt (amount)
- Time features generated: minute, hour, weekday, day, month
- Sliding window: lookback (90) + predict (10) + 1 = 101 bars per sample
- Normalization: per-window z-score using ONLY lookback (past) data, clip ±5.0
- Split: train/val/test by time ranges (overlapping for lookback buffer)

### Preprocessing (qlib_data_preprocess.py)
- Uses Qlib's D.calendar() and QlibDataLoader
- Loads: `$open, $high, $low, $close, $volume, $vwap`
- Computes: amt = (open+high+low+close)/4 * vol
- Drops NaN, filters symbols with < lookback+predict+1 bars
- Saves as pickle: train_data.pkl, val_data.pkl, test_data.pkl

### Dataset (dataset.py)
- QlibDataset: pre-computes all valid (symbol, start_index) pairs
- Random sampling from the pool (not sequential)
- Per-epoch seed reset for reproducibility
- __getitem__ returns (x_tensor [101, 6], x_stamp_tensor [101, 5])

## 3. Existing NEPSE data compatibility
### Available data
- DuckDB: 372 symbols, 515,327 bars (2010-2026)
- Columns: time, open, high, low, close, volume, turnover, percent_change, validation_status, flags
- OHLC validity: 0 invalid bars (verified)

### Compatibility assessment
- NEPSE data has OHLCV (open, high, low, close, volume) — MATCHES required schema
- `turnover` can be renamed to `amt` (as done in kronos_service.py)
- Timestamps are daily (NEPSE trading days: Sun-Thu)
- No Qlib format — would need conversion or rewritten data loader
- No volume-at-price or order-book data

### Adaptation path
Option A: Convert NEPSE DuckDB → Qlib binary format (complex, Qlib dependency)
Option B: Rewrite data loading to read from DuckDB directly (moderate effort, no Qlib needed)
Option C: Use the existing QlibDataPreprocessor with a custom data loader (requires Qlib)

## 4. Required model checkpoints
### Tokenizer
- Kronos-Tokenizer-base (for small/base): 15,842,368 B, config: d_model=256, s1_bits=10, s2_bits=10
- Kronos-Tokenizer-2k (for mini): 15,842,376 B, config: d_model=256, s1_bits=10, s2_bits=10

### Predictor
- Kronos-mini: 16,440,776 B (4.1M params, d_model=256, 4 layers, 4 heads)
- Kronos-small: 98,980,656 B (24.7M params, d_model=512? — check config)
- Kronos-base: 409,264,008 B (102.3M params, d_model=832, 12 layers, 16 heads)

### Fine-tuning sequence
1. Tokenizer first: train_tokenizer.py (30 epochs, lr 2e-4, batch 50)
2. Predictor second: train_predictor.py (30 epochs, lr 4e-5, batch 50)
3. Tokenizer checkpoint → predictor's tokenizer
4. Predictor checkpoint → inference

### Per-variant support
- The official pipeline uses ONE tokenizer + ONE predictor per run
- Mini pairs with Tokenizer-2k (context 2048)
- Small/Base pair with Tokenizer-base (context 512)
- The pipeline does NOT support training multiple variants simultaneously

## 5. Training requirements

### Dependencies
- qlib (NOT installed) — required for data preprocessing
- torch (installed 2.14.1) — required
- pandas (installed 3.0.6) — required
- numpy (installed) — required
- comet_ml (optional, for logging)
- tqdm (required, for progress bars)

### Hardware
- DDP (Distributed Data Parallel) with NCCL backend — requires NVIDIA GPU
- M1 has NO CUDA, NO NCCL
- MPS (Metal) is NOT supported by the official training pipeline
- CPU training possible but extremely slow
- Memory: Base model 102.3M params + batch 50 × 101 × 6 features × 4 bytes ≈ ~120MB per batch. Plus model weights ~400MB. Total ~1-2GB for base. Feasible on 8GB but slow on CPU.
- Mini model 4.1M params + same batch → ~50MB. Very feasible.

### Training time estimates (CPU, M1)
- Mini: 30 epochs × 2000 batches × ~0.5s/batch ≈ 8-10 hours (tokenizer) + 8-10 hours (predictor) = ~20 hours total
- Base: 30 epochs × 2000 batches × ~5s/batch ≈ 80+ hours per component. Not practical on M1 CPU.

## 6. Chronological split design
### Official (Chinese market)
- Train: 2011-01-01 to 2022-12-31
- Val: 2022-09-01 to 2024-06-30 (overlaps train for lookback buffer)
- Test: 2024-04-01 to 2025-06-05 (overlaps val for lookback buffer)
- Backtest: 2024-07-01 to 2025-06-05

### NEPSE adaptation
- Available: 2010-2026 (372 symbols, 515K bars)
- Recommended split (chronological, no leakage):
  - Train: 2010-01-01 to 2022-12-31
  - Val: 2022-09-01 to 2024-06-30
  - Test: 2024-04-01 to 2025-06-30
  - Backtest: 2024-07-01 to 2026-10-15 (latest)
- Lookback buffer: 90 bars before each split boundary
- Validation: walk-forward on test set, compare against naive/drift baselines

### Leakage prevention
- Normalization uses only lookback (past) data per window
- Sliding window indices computed before split
- No future data in input features
- Time features (minute, hour, weekday, day, month) are derived from the timestamp only
- Test set is chronologically after train/val

## 7. Blockers
1. **Qlib not installed** — required for data preprocessing. Installation on macOS M1 may be problematic.
2. **DDP/NCCL** — official pipeline uses NVIDIA-only DDP. M1 has no CUDA. Would need to rewrite training loop for single-device (MPS or CPU).
3. **Qlib data format** — NEPSE data is in DuckDB, not Qlib binary. Need conversion or rewritten data loader.
4. **Training time** — Mini: ~20 hours on M1 CPU. Base: 80+ hours. Not practical without GPU.
5. **Memory** — Base model (102.3M params) + batch 50 may exceed 8GB on M1 during training.

## 8. Smallest safe next step
1. Rewrite `qlib_data_preprocess.py` to read from DuckDB instead of Qlib (Option B). This eliminates the Qlib dependency.
2. Rewrite training scripts for single-device (MPS or CPU), removing DDP/NCCL.
3. Start with Kronos-mini (4.1M params) — feasible on M1 CPU in ~20 hours.
4. Use the existing 372 NEPSE symbols with 2010-2026 history.
5. Implement chronological split with lookback buffer.
6. Compare fine-tuned mini against original mini and baselines.

## 9. Recommendation
Fine-tuning Kronos on NEPSE data is technically feasible for the Mini variant on M1 hardware (with ~20 hours of CPU training), but requires significant engineering to adapt the official pipeline from Qlib/Chinese-market to our DuckDB/NEPSE format and from DDP/CUDA to single-device/MPS.

The Base variant is not practical on M1 (80+ hours, memory constraints).

Before investing in fine-tuning, consider whether the current pre-trained model (which already shows no predictive edge over naive) would benefit from NEPSE-specific fine-tuning. The flat forecast issue was caused by greedy decoding (now fixed to nucleus sampling), not by lack of domain adaptation.

**Priority:** Low. The immediate value is in fixing the sampling configuration (done) and running larger evaluations (pending authorization). Fine-tuning is a longer-term research project.