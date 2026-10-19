# KRONOS FINE-TUNING GO/NO-GO REVIEW
Date: 2026-10-17 | Read-only | No training performed

## 1. Source Reconciliation

### Available Provenance
- Source: github.com/Aabishkar2/nepse-data (community-maintained)
- Provenance columns: source, source_url, retrieved_at, validation_status, flags, adjustment_status
- All 515,327 rows have source_url pointing to per-symbol CSV files
- validation_status: 502,069 valid, 13,134 suspect, 124 invalid
- adjustment_status: 'unadjusted' for ALL rows (prices not adjusted for bonus/split)
- Flags: open_outside_range (38,475), volume_spike (11,043), close_outside_range (395), price_jump (115), high_low_inverted (109)

### Independent Source Verification
- No independent historical records available locally
- The only source is the community-maintained GitHub dataset
- No original NEPSE exchange data has been accessed
- No source reconciliation performed

### Conclusion
Source reconciliation is NOT AVAILABLE. The price_bars data comes from a single community source with no independent verification. Structural checks (OHLC consistency, null checks, etc.) do not establish historical price correctness.

## 2. Split Leakage Analysis

### Split Boundaries
| Split | Date Range | Symbols | Bars |
|---|---|---|---|
| Train | 2010-01-03 to 2022-12-29 | 351 | 214,760 |
| Val | 2022-09-01 to 2024-06-30 | 351 | 98,022 |
| Test | 2024-04-01 to 2025-06-30 | 351 | 78,690 |

### Overlap Analysis
- Train/Val overlap: 224 symbols have dates in both train and val (2022-09-01 to 2022-12-29)
- Val/Test overlap: ~3 months (2024-04-01 to 2024-06-30)

### Leakage Assessment
- The overlap is by design (official Kronos split pattern with lookback buffers)
- Input windows use lookback=90 bars, forecast horizon=10 bars
- Sequences are per-symbol (no cross-symbol mixing)
- Within each sequence, data is sorted chronologically
- The overlap provides context for the validation period (lookback window)
- No future target leakage within sequences (each sequence's target is within its split)
- However, the overlapping target observations mean val/test metrics may be optimistic

### Conclusion
Split leakage is DOCUMENTED but NOT RESOLVED. The overlap is intentional (Kronos pattern) but should be clearly labeled as providing input context, not target leakage. Evaluation metrics from overlapping periods may be optimistic.

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
Corporate actions are NOT HANDLED. Prices are unadjusted. This is a known limitation that should be documented in experiment results. Do not automatically adjust or delete prices.

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
| File | Checksum | Status |
|---|---|---|
| train_data.pkl | MATCH | Verified |
| val_data.pkl | MATCH | Verified |
| test_data.pkl | MATCH | Verified |
| prep_report.json | MATCH | Verified |

### Artifact Contents
| Split | Symbols | Bars | Date Range | Columns |
|---|---|---|---|---|
| Train | 351 | 214,760 | 2010-01-03 to 2022-12-29 | open, high, low, close, vol, amt |
| Val | 351 | 98,022 | 2022-09-01 to 2024-06-30 | open, high, low, close, vol, amt |
| Test | 351 | 78,690 | 2024-04-01 to 2025-06-30 | open, high, low, close, vol, amt |

### Quality Verification
- Null values: 0
- OHLC inconsistent: 0 (all rows structurally valid)
- Feature columns: correct (6 features)
- Symbol separation: no cross-symbol mixing
- Chronological ordering: verified for all symbols

## Final Decision

**B. BLOCKED_PENDING_SPECIFIC_FIXES**

### Structural Readiness: PASS
- Pipeline runs successfully
- Artifacts load with current pandas
- Quality filtering implemented (invalid excluded, suspect quarantined)
- OHLC consistency verified (0 inconsistent in prepared data)
- No cross-symbol mixing
- Chronological ordering verified

### Source-Data Correctness: BLOCKED
- No independent source reconciliation performed
- Single community source with no verification
- Structural checks do not establish historical price correctness
- 13,134 suspect rows quarantined but not resolved

### Evaluation Integrity: CONDITIONALLY PASS
- Split overlap is intentional (Kronos pattern) but may inflate metrics
- Overlapping target observations mean val/test metrics may be optimistic
- Must be documented in experiment results

### Readiness for Exploratory Experiment: CONDITIONALLY APPROVED
- A clearly labeled exploratory baseline can proceed IF:
  - Results are NOT represented as verified financial forecasting
  - Suspect/invalid data exclusion is documented
  - Split overlap is acknowledged
  - Prices are labeled as unadjusted
  - No corporate action handling is noted
  - No source verification is claimed

### Readiness for Reliable Financial Forecasting Research: BLOCKED
- Requires: independent source verification, corporate action handling, trading calendar, resolved split overlap

### Specific Fixes Required Before Reliable Research
1. **Independent source reconciliation** — access original NEPSE data or a second independent source
2. **Corporate action handling** — obtain bonus/split adjustment factors
3. **Trading calendar** — obtain authoritative NEPSE holiday calendar
4. **Split overlap resolution** — document or eliminate overlapping target observations
5. **Pickle compatibility** — resolved (protocol 4), but needs ongoing verification

### What Can Proceed Now
- A clearly labeled exploratory baseline experiment
- Structural validation and pipeline testing
- Model architecture evaluation (inference only, no fine-tuning)
- Documentation of limitations

### What Must Remain Blocked
- Production fine-tuning with unverified data
- Any claim of verified financial forecasting capability
- Use of suspect/invalid rows in training
- Representation of unadjusted prices as adjusted
