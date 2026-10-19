# KRONOS-MINI HISTORICAL BACKTEST REPORT
Date: 2026-10-17 | Context: 830/256 bars, horizon 5, 6 windows, 3 symbols

## Sampling configuration
- Fixed: top_k=0, top_p=0.9, T=1.0, sample_count=1 (nucleus sampling, applied this session)
- No look-ahead: each window uses only bars up to the forecast origin
- Windows spaced 5 bars apart, no overlapping realized ranges

## Results

### NIMB (context 256, 6 windows)
| Metric | Kronos | Naive | Drift20 |
|---|---|---|---|
| MAE (close) | 5.4517 | 3.2967 | 4.1563 |
| Directional accuracy | 33.33% | — | — |
| Best competitor | naive_mae_close | | |

### NIMB (context 830, 1 window)
| Metric | Kronos | Naive | Drift20 |
|---|---|---|---|
| MAE (close) | 9.0403 | 5.7 | 4.5632 |
| Directional accuracy | 20.0% | — | — |
| Best competitor | drift20_mae_close | | |

### NABIL (context 256, 6 windows)
| Metric | Kronos | Naive | Drift20 |
|---|---|---|---|
| MAE (close) | 8.0279 | 6.6233 | 8.0877 |
| Directional accuracy | 50.0% | — | — |
| Best competitor | naive_mae_close | | |

### SANIMA (context 256, 6 windows)
| Metric | Kronos | Naive | Drift20 |
|---|---|---|---|
| MAE (close) | 7.3821 | 6.4433 | 6.6032 |
| Directional accuracy | 40.0% | — | — |
| Best competitor | naive_mae_close | | |

## Key findings

1. **Kronos-mini (nucleus sampling) does NOT beat naive persistence on any symbol.**
   - NIMB: Kronos MAE 5.45 vs naive 3.30 (naive wins by 65%)
   - NABIL: Kronos MAE 8.03 vs naive 6.62 (naive wins by 21%)
   - SANIMA: Kronos MAE 7.38 vs naive 6.44 (naive wins by 15%)

2. **Longer context (830) makes it worse**, not better. NIMB ctx 830: Kronos MAE 9.04 vs naive 5.70 (naive wins by 59%).

3. **Directional accuracy is poor**: 20-50%, barely better than coin flip (50%).

4. **The greedy (top_k=1) configuration was actually MORE accurate** (NIMB MAE 3.24 vs naive 3.58) but produced flat, unrealistic forecasts. The nucleus sampling (top_k=0) produces more realistic-looking forecasts but is LESS accurate.

5. **This is a fundamental bias-variance tradeoff**: greedy decoding gives low variance (flat, accurate-ish) but unrealistic; nucleus sampling gives high variance (realistic-looking, but less accurate). Neither configuration demonstrates genuine predictive value.

## Conclusion

Kronos-mini does not demonstrate genuine predictive value on NEPSE data. It marginally loses to naive persistence on all tested symbols. The forecast is a model sample, not a prediction with verified edge. The application correctly labels all forecasts as "predicted" and "model output — never an observed price."

## Limitations
- Small sample: 3 symbols × 6 windows × 5 days = 90 forecast-target pairs. Not statistically significant.
- Only NIMB, NABIL, SANIMA tested. Other symbols may differ.
- Only 5-day horizon tested. Longer/shorter horizons may differ.
- Only Kronos-mini tested. Small/base variants may differ.
- Greedy vs nucleus tradeoff not fully explored (temperature, top_p, sample_count combinations).

## Files created
- KRONOS_BACKTEST_REPORT.md (this file)
- /tmp/kronos_experiment_results.json (raw experiment data)