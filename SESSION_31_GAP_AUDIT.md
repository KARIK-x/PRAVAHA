# SESSION 31 — GAP AUDIT

Re-audit of the platform against `NEPSE_MEGA_TOOL_MASTER_MISSION_CONDENSED.md`,
carried into Session 34 and re-checked after the catalogue + Part-C work.

Legend: ✅ closed · 🟡 partial · ⛔ blocked on data/source · ⬜ open

## Charting & TA (Part A)

| Gap | State | Evidence / note |
|---|---|---|
| Per-indicator numeric correctness | ✅ | 92 indicators: 62 against hand/reference series, 28 invariant, 2 sparse-map carve-outs |
| Indicator UI info for all 92 | ✅ | info button verified for every indicator (session 30) |
| Quick Layers persistence | ✅ | per-symbol `mt-quick-layers-<symbol>` |
| Object-manager cryptic labels (BO/DT/INV) | 🟡 | groups + scoped clearing tested; label trace partial |
| 5 advanced capabilities into dedicated panels | 🟡 | backend verified; surfaced via KIMI Catalogues; dedicated chart panels partial |
| Settings, import/export schema validation | 🟡 | favourites/recents/isolation tested; import validation partial |
| Safe refresh mechanism | ⛔ | needs an external scheduler; no in-app cron exists |

## Scanners / algorithms / strategies (Part B)

| Gap | State | Evidence |
|---|---|---|
| Searchable scanner catalogue (100–150) | ✅ | **124** scanners (31 presets + 93 new), all validated by `validate_tree` |
| Searchable algorithm catalogue (70–150) | ✅ | **77** (58 backtest + 19 analysis) |
| Fundamental tool catalogue | 🟡 | **32** tools; dividend yield blocked (0 DPS) |
| Per-tool info panel + run | ✅ | KIMI Catalogues tab, ⓘ + Run, browser-verified |
| Market ribbon / research navigation | 🟡 | NEPSE ribbon present; per-source stale labels partial |

## Quant / valuation / visualisation (Part C)

| Gap | State | Evidence |
|---|---|---|
| DCF + reverse DCF + sensitivity | ✅ | hand-computed DCF test; reverse-DCF round-trip |
| Efficient frontier (long-only) | ✅ | simplex projection, no scipy added |
| HRP | ✅ | single-linkage + recursive bisection |
| Deflated Sharpe | ✅ | skew/kurtosis/trials adjusted |
| Stress test | ✅ | beta-based market-shock scenario |
| Event study | ✅ | CAR, next-session entry; dates must be supplied |
| Liquidity drought | ✅ | NF-005 |
| Fundamental forensics | ✅ | NF-007 |
| Cross-sectional factor snapshot | ✅ | NF-008 |
| Coverage/feasibility explorer | ✅ | NF-030 |
| Data-source reconciliation (§6.2) | ⬜ | not implemented |
| Sector-specific valuation packs | 🟡 | partial |

## Data blockers (unchanged)

1. `floorsheet_trades` = 0 rows → NF-001, order-flow ⛔.
2. No sourced corporate-event/IPO/rights calendar → NF-004, NF-020 ⛔.
3. `dps` = 0 records → dividend yield returns not-available (never 0).
4. `promoter_holding`/`public_holding` = 0 → ownership ⛔.
5. All prices `unadjusted` → total-return features 🟡.
6. No in-app scheduler → alerts/auto-refresh ⛔.
7. Live NEPSE API gated (401) → live/intraday ⛔.
