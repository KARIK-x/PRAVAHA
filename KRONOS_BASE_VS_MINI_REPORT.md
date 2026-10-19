# KRONOS-BASE VS KRONOS-MINI — COMPARISON REPORT
Date: 2026-10-17 | Sampling: top_k=0, top_p=0.9, T=1.0, sample_count=1 (nucleus)

## Model availability
- Kronos-Base: weights present (409,264,008 B), tokenizer Kronos-Tokenizer-base (15,842,368 B). Config: d_model=832, 12 layers, 16 heads. MPS device. Load time 3.265s.
- Kronos-Mini: weights present (16,440,776 B), tokenizer Kronos-Tokenizer-2k (15,842,376 B). Config: d_model=256, 4 layers, 4 heads. MPS device. Load time ~0.24s.
- No download needed. Both variants fully available locally.

## Forecast characteristics (NIMB, context 256, horizon 50)

| Metric | Mini | Base | Historical |
|---|---|---|---|
| Unique closes (of 50) | 48 | 49 | — |
| Consecutive equal closes | 1 | 1 | — |
| Return std | 1.1818% | 1.3497% | 1.5174% |
| Avg abs return | 0.9182% | 1.0193% | 1.0124% |
| Close range | 186.48–202.62 | 191.24–206.42 | 182.00–228.00 |
| Inference time | 0.749s | 6.444s | — |
| Load time | ~0.24s | 3.265s | — |

Base is slightly closer to historical volatility (1.3497% vs 1.5174%) than Mini (1.1818%). Base is ~8.6× slower to infer and ~13× slower to load.

## Walk-forward evaluation (context 256, horizon 5, 6 windows)

### NIMB
| Metric | Mini | Base | Naive | Drift20 |
|---|---|---|---|---|
| MAE (close) | 5.4517 | 4.4269 | 3.2967 | 4.1563 |
| Directional accuracy | 33.33% | 53.33% | — | — |
| Best competitor | naive | naive | | |

### NABIL
| Metric | Mini | Base | Naive | Drift20 |
|---|---|---|---|---|
| MAE (close) | 8.0279 | 11.3148 | 6.6233 | 8.0877 |
| Directional accuracy | 50.00% | 56.67% | — | — |
| Best competitor | naive | naive | | |

### SANIMA
| Metric | Mini | Base | Naive | Drift20 |
|---|---|---|---|---|
| MAE (close) | 7.3821 | 7.3096 | 6.4433 | 6.6032 |
| Directional accuracy | 40.00% | 43.33% | — | — |
| Best competitor | naive | naive | | |

## Key findings

1. **Base beats Mini on NIMB** (MAE 4.43 vs 5.45) but loses on NABIL (11.31 vs 8.03) and ties on SANIMA (7.31 vs 7.38). No consistent advantage.

2. **Neither variant beats naive persistence on any symbol.** Naive wins on all 3 symbols for both Mini and Base.

3. **Base has higher directional accuracy** (43-57%) than Mini (33-50%), but still near coin-flip levels.

4. **Base is ~8.6× slower to infer** (6.4s vs 0.75s) and ~13× slower to load (3.27s vs 0.24s). On an 8 GB M1, this is a meaningful resource cost.

5. **Base's forecast volatility** (1.3497%) is slightly closer to historical (1.5174%) than Mini's (1.1818%). Both are still below historical.

6. **Both variants suffer from the same fundamental issue**: neither demonstrates genuine predictive value over naive persistence on NEPSE data.

## Conclusion

Kronos-Base is marginally better than Kronos-Mini on NIMB (MAE 4.43 vs 5.45) but worse on NABIL (11.31 vs 8.03). Neither beats naive persistence. Base is ~8.6× slower. There is no evidence that either variant provides genuine predictive value on NEPSE data. The choice between Mini and Base should be based on resource constraints (Mini is faster and lighter) rather than accuracy (neither has a consistent advantage).

## Limitations
- Small sample: 3 symbols × 6 windows × 5 days = 90 forecast-target pairs per variant. Not statistically significant.
- Only 5-day horizon tested. Longer/shorter horizons may differ.
- Only nucleus sampling (top_k=0, top_p=0.9) tested. Greedy (top_k=1) may differ.
- Context 830 not tested for Base (only Mini tested with 830).

## Files created
- KRONOS_BASE_VS_MINI_REPORT.md (this file)

## Test results
- Backend pytest: 2331 passed, 0 failed, 0 errors, 0 skipped.
- No code changes made. Production port 8710 untouched.