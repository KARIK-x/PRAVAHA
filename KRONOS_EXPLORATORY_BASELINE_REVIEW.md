# KRONOS EXPLORATORY BASELINE — FINAL GO/NO-GO REVIEW
Date: 2026-10-17 | Read-only | No training performed

## 1. Source Reconciliation

### Available Provenance
- Source: github.com/Aabishkar2/nepse-data (community-maintained)
- Provenance columns: source, source_url, retrieved_at, validation_status, flags, adjustment_status
- All 515,327 rows have source_url pointing to per-symbol CSV files
- validation_status: 502,069 valid, 13,134 suspect, 124 invalid
- adjustment_status: 'unadjusted' for ALL rows
- Flags: open_outside_range (38,475), volume_spike (11,043), close_outside_range (395), price_jump (115), high_low_inverted (109)

### Independent Source Verification
- No independent historical records available locally
- Single community source with no verification
- No original NEPSE exchange data accessed
- No source reconciliation performed

### Conclusion
Source reconciliation is NOT AVAILABLE. Structural checks do not establish historical price correctness.

## 2. Split Leakage Analysis

### Split Boundaries
| Split | Date Range | Symbols | Bars |
|---|---|---|---|
| Train | 2010-01-03 to 2022-12-29 | 351 | 214,760 |
| Val | 2022-09-01 to 2024-06-30 | 351 | 98,022 |
| Test | 2024-04-01 to 2025-06-30 | 351 | 78,690 |

### Overlap Analysis
- Train/Val overlap: 71 dates (2022-09-01 to 2022-12-29)
- Val/Test overlap: 57 dates (2024-04-01 to 2024-06-30)
- Train/Test overlap: 0 dates
- 224 symbols have train/val overlap at the symbol level

### Leakage Assessment
- Overlap is by design (official Kronos split pattern with lookback buffers)
- Input windows use lookback=90 bars, forecast horizon=10 bars
- Sequences are per-symbol (no cross-symbol mixing)
- Within each sequence, data is sorted chronologically
- The overlap provides input context for the validation period
- No future target leakage within sequences (each sequence's target is within its split)
- However, overlapping target observations mean val/test metrics may be optimistic

### Conclusion
Split leakage is DOCUMENTED but NOT RESOLVED. Overlap is intentional but should be clearly labeled. Evaluation metrics from overlapping periods may be optimistic.

## 3. Corporate Actions

### Available Metadata
- adjustment_status: 'unadjusted' for ALL 515,327 rows
- No corporate_actions table exists
- No bonus/split adjustment data available

### Impact
- Prices are NOT adjusted for bonus shares, stock splits, or rights issues
- Price discontinuities from corporate actions will appear as extreme moves
- The 23% max single-bar price change may be from corporate actions
- Kronos will train on unadjusted prices, potentially learning spurious patterns

### Conclusion
Corporate actions are NOT HANDLED. Prices are unadjusted. This is a known limitation that should be documented in experiment results.

## 4. Trading Calendar

### Available Calendar
- megatool/market_intelligence/config/trading_calendar.json exists
- Contains 0 holidays (empty list)
- No authoritative NEPSE trading calendar available

### Impact
- Gap checks are approximate (based on 7-day threshold, not actual trading days)
- Cannot distinguish holidays from data gaps
- Cannot verify if all expected trading days are present

### Checks Still Possible Without Calendar
- Duplicate date detection (0 found)
- Chronological ordering (verified)
- Per-symbol date range reporting
- Gap detection (>7 days threshold)

### Conclusion
No authoritative trading calendar available. Gap checks are approximate.

## 5. Artifact Integrity

### Checksum Verification
| File | Status |
|---|---|
| train_data.pkl | MATCH |
| val_data.pkl | MATCH |
| test_data.pkl | MATCH |
| prep_report.json | MATCH |

### Artifact Contents
| Split | Symbols | Bars | Date Range |
|---|---|---|---|
| Train | 351 | 214,760 | 2010-01-03 to 2022-12-29 |
| Val | 351 | 98,022 | 2022-09-01 to 2024-06-30 |
| Test | 351 | 78,690 | 2024-04-01 to 2025-06-30 |

### Quality Verification
- Null values: 0
- OHLC inconsistent: 0 (all rows structurally valid)
- Feature columns: correct (6 features: open, high, low, close, vol, amt)
- Symbol separation: no cross-symbol mixing
- Chronological ordering: verified for all symbols
- Flat candles: 0 (filtered out)
- Negative volume: 0
- Zero volume: 0

## 6. Kronos Fine-Tuning Entry Point

### Available Locally
- vendor/kronos/model/kronos.py: Model architecture (Kronos, KronosTokenizer)
- vendor/kronos/model/module.py: Model modules
- vendor/kronos/tests/test_kronos_regression.py: Regression tests
- megatool/kronos_service.py: Inference service (forecast, evaluate)
- scripts/kronos_data_prep.py: Data preparation (prototype)

### NOT Available Locally
- No fine-tuning script in repository
- No training configuration files
- No checkpoint save/load utilities
- Official Kronos fine-tuning code must be obtained from the Kronos GitHub repository

### Model Configuration (from kronos_service.py)
- Variants: mini, small, base
- Context length: configurable (VARIANT_MAX_CONTEXT)
- Prediction length: configurable
- Tokenizer: KronosTokenizer

### Expected Input Format (from data prep)
- Columns: open, high, low, close, vol, amt
- Time features: minute, hour, weekday, day, month
- Index: datetime
- Per-symbol sequences (no cross-symbol mixing)
- Lookback: 90 bars, Predict: 10 bars, Window: 101 bars

### Checkpoint Output Paths
- Not defined locally (would be in official Kronos fine-tuning code)
- Recommended: save to data/kronos_audit/ or separate experiment directory

## 7. Kaggle Workflow

### Current State
- Kronos Mini loaded in Kaggle (synthetic data smoke test passed)
- Inference works (forecast and evaluate)
- No fine-tuning performed yet

### Approved Artifacts for Transfer
| Artifact | Path | Size | Transfer? |
|---|---|---|---|
| train_data.pkl | data/kronos_audit/v2/train_data.pkl | 12.2 MB | Yes |
| val_data.pkl | data/kronos_audit/v2/val_data.pkl | 5.7 MB | Yes |
| test_data.pkl | data/kronos_audit/v2/test_data.pkl | 4.6 MB | Yes |
| prep_report.json | data/kronos_audit/v2/prep_report.json | 1.1 KB | Yes |
| checksums.json | data/kronos_audit/v2/checksums.json | 353 B | Yes |
| prepare.py | data/kronos_audit/v2/prepare.py | 9.5 KB | Yes (for reproducibility) |
| Kronos model weights | vendor/kronos/model/ | ~500 MB | No (download from HuggingFace) |
| Tokenizer | vendor/kronos/ | ~5 MB | No (download from HuggingFace) |

### Transfer Instructions (for owner)
1. Upload train_data.pkl, val_data.pkl, test_data.pkl to Kaggle dataset
2. Upload prepare.py for reproducibility
3. Download Kronos model weights from HuggingFace in Kaggle notebook
4. Use official Kronos fine-tuning code (not in this repo)
5. Save checkpoints to Kaggle output directory
6. Do NOT upload private data or trading records

## 8. Final GO/NO-GO Decision

### A. APPROVED_FOR_CONTROLLED_BASELINE_EXPERIMENT

**Conditions**:
1. The experiment must be labeled as "exploratory baseline" — NOT verified financial forecasting
2. Results must acknowledge:
   - No independent source verification
   - Unadjusted prices (no corporate action handling)
   - Overlapping train/val/test splits (may inflate metrics)
   - No trading calendar (approximate gap checks)
   - Suspect rows quarantined but not resolved
3. The experiment must NOT be used for:
   - Trading decisions
   - Performance claims
   - Client-facing results
   - Regulatory submissions
4. Fine-tuning must use only the v2 prepared artifacts (quality-filtered)
5. Checkpoints must be saved separately from production

### Structural Readiness: PASS
- Pipeline runs successfully
- Artifacts load with current pandas
- Quality filtering implemented
- OHLC consistency verified
- No cross-symbol mixing
- Chronological ordering verified

### Source-Data Correctness: NOT VERIFIED
- No independent source reconciliation
- Single community source
- Structural checks do not establish historical price correctness

### Evaluation Integrity: CONDITIONALLY PASS
- Split overlap is intentional (Kronos pattern)
- Overlapping target observations may inflate metrics
- Must be documented in experiment results

### Readiness for Exploratory Experiment: APPROVED (with conditions above)
### Readiness for Reliable Financial Forecasting Research: BLOCKED

### Specific Blockers for Reliable Research
1. Independent source reconciliation (no original NEPSE data available)
2. Corporate action handling (no adjustment factors)
3. Trading calendar (empty holiday list)
4. Split overlap resolution (intentional pattern, needs documentation)
5. Pickle compatibility (resolved, but needs ongoing verification)

### Evidence Needed to Resolve
- Independent access to original NEPSE source data
- Bonus/split adjustment factors from NEPSE
- Authoritative NEPSE trading holiday calendar
- Documentation of acceptable split overlap policy
