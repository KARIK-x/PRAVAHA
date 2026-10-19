# Reference → Mega Tool feature matrix

Statuses: **IMPLEMENTED · TESTED-PASS · TESTED-FAIL · PARTIAL · BLOCKED · NOT STARTED · NOT-TESTED**.
"Mega Tool today" describes the code as it exists; "Reference" cites the screenshot
indices from `REFERENCE_INVENTORY.md`.

## A. Market & breadth

| Feature | Refs | Mega Tool today | Gap | Plan |
|---|---|---|---|---|
| NEPSE index panel + session status | #2, #89 | **TESTED-PASS** `/api/live/market` + Overview live strip | Presentation only | Fold into new dashboard hero |
| Index history chart | #94–#100 | **PARTIAL** `/api/indices/{name}` exists; no index series in dev store | Needs index series ingested | Reuse `index_series`; honest "no series" state |
| Sector gainers/losers, sector table | #3, #74, #91 | **PARTIAL** `sectors.py`, `/api/indices`; no sector page | Missing page | New **Markets** view: sector table + rotation |
| Turnover / breadth stats | #2, #89 | **TESTED-PASS** dashboard breadth/totals | Presentation | Dashboard hero stats |
| Market breadth (A/D, TRIN, %>MA) | #101–#106 | **PARTIAL** breadth counts only | No A/D line, TRIN, %>MA | Add breadth series + charts (computable from bars) |
| PE / PB / dividend-yield distributions | #4, #5, #106 | **PARTIAL** fundamentals stored | No distribution charts | Histograms from `fundamentals` (real values only) |
| % of stocks above moving average | #6 | **NOT STARTED** | Computable from bars | Sector table, computed on demand |

## B. Stock ideas / models

| Feature | Refs | Mega Tool today | Gap | Plan |
|---|---|---|---|---|
| Model catalogue (cards) | #25 | **NOT STARTED** | No page | **Ideas** view: model tiles |
| Peter Lynch | #26 | **NOT STARTED** | Needs PEG + growth | Compute with honest "insufficient data" where inputs missing |
| CANSLIM | #25 | **NOT STARTED** | Needs quarterly EPS + RS + volume | Partial: RS + volume factors only |
| Magic Formula | #25 | **NOT STARTED** | Needs EBIT + EV | Insufficient data (no EV/EBIT) → declared |
| Piotroski F-score | #13, #25 | **NOT STARTED** | Needs 9 accounting inputs | Insufficient data (no ROA/current ratio/issuance) → declared |
| Altman Z-score | #7, #10 | **NOT STARTED** | Needs EBIT/sales/WC/retained | Insufficient data → declared |
| G-score / fundamental growth | #7, #15 | **NOT STARTED** | Needs multi-year series | Use growth CAGR from stored periods where present |
| MultiBagger / Bargain / 52-wk | #25, #27 | **PARTIAL** `ranking.py`, `scanner.py` | No dedicated screen | Express as saved screens (existing screen tree) |

> **Honesty rule applied here:** Mega Tool's fundamentals carry EPS, P/E, net-worth
> per share, paid-up capital and profit — **not** EBIT, current assets/liabilities,
> cash flow or share issuance. Models needing those will report
> `insufficient data` with the missing fields named, never a fabricated score.

## C. Company analysis

| Feature | Refs | Mega Tool today | Gap | Plan |
|---|---|---|---|---|
| Ratios (P/E, P/B, yield) | #13, #20 | **TESTED-PASS** `/api/fundamentals/{sym}/ratios` | — | Surface in the stock workspace |
| Valuation models (DDM/Graham/Gordon/Lynch) | #20–#22 | **PARTIAL** `forecast.py`; no valuation module | No valuation | **NOT STARTED** this session — declared |
| DuPont ROE decomposition | #23, #24 | **NOT STARTED** | Needs margin/turnover/leverage | Insufficient data → declared |
| Growth CAGR tables | #15–#17 | **PARTIAL** stored multi-period fundamentals | No CAGR view | Compute CAGR where ≥2 periods exist |
| Own financial signal/rating | #18, #19 | **PARTIAL** quality module | No composite | Defer; avoid inventing a score |
| Beta / Sharpe / Sortino / drawdown | #11, #12, #66 | **PARTIAL** `risk.py`, `stats.py` | Not shown per stock | Add to stock workspace |

## D. Screening & discovery

| Feature | Refs | Mega Tool today | Gap | Plan |
|---|---|---|---|---|
| Advanced screener with column chooser | #47, #48, #52 | **TESTED-PASS** `POST /api/screen` + rule builder | No column chooser/filter-row UI | New filter-row + column UI over the existing engine |
| Category tabs | #49, #52 | **PARTIAL** presets (23) | Not categorised | Group presets by category |
| Saved screens | #47 | **TESTED-PASS** `screens.py` | — | Wire into the new UI |
| Pattern scanner with thumbnails | #50, #51 | **PARTIAL** `ta/patterns.py` + `/patterns` | No thumbnail grid | Thumbnail grid from detected pivots |
| Multi-symbol indicator matrix | #76, #77 | **NOT STARTED** | Computable | **NOT STARTED** this session |
| Comparators (growth/financial/price/chart) | #53–#56 | **NOT STARTED** | Computable from stored data | **NOT STARTED** this session |

## E. Portfolio, journal, backtest

| Feature | Refs | Mega Tool today | Gap | Plan |
|---|---|---|---|---|
| Portfolio value/return cards | #57, #59, #60 | **TESTED-PASS** `/api/portfolio` + cash flow | Presentation | Portfolio hero + allocation |
| Holdings table + P/L | #58, #61 | **TESTED-PASS** positions with unrealised P&L | — | Rework the table |
| Risk stats / risk-reward | #66, #68 | **PARTIAL** `risk.py` limits | No per-position R:R | Add where support/resistance exist |
| Portfolio scoring gauges | #66, #67 | **NOT STARTED** | Composite | Defer (avoid invented scores) |
| Journal | — | **TESTED-PASS** `journal.py` | — | Keep, restyle |
| Backtest equity + metrics | #33–#36 | **TESTED-PASS** `backtest.py`, `experiments.py` | No returns histogram / trade donut | Add visual summaries |
| Trade log | #35 | **TESTED-PASS** backtest trade log | — | Keep |

## F. Charting

| Feature | Refs | Mega Tool today | Gap | Plan |
|---|---|---|---|---|
| Candles + volume + axes | #94 | **TESTED-PASS** lightweight-charts v4, `/api/bars` | — | Enlarge; hero layout |
| Indicator panes (RSI/MACD) | #94 | **TESTED-PASS** 46 indicators | Toolbar overloaded | Group into an **indicator browser** |
| Drawing tools | #96, #100 | **PARTIAL** Fibonacci + S/R drawings, persisted | No channels/rectangles | Keep; add overlay manager |
| Overlay clutter control | #96 | **PARTIAL** many levels drawn | **No visibility manager** | **Overlay manager** + clean default |
| Composition / indicator rail | #94, #99 | **NOT STARTED** | — | Right rail (deferred) |
| Chart scanner thumbnails | #50, #51 | **NOT STARTED** | — | Deferred |

## G. Cross-cutting product

| Feature | Refs | Mega Tool today | Plan |
|---|---|---|---|
| Data freshness + source honesty | all | **TESTED-PASS** live layer + diagnostics | Calm status chips, keep |
| Model explanations / methodology text | #26 | **PARTIAL** scanner `METRIC_HELP` | Methodology drawer per model |
| Loading / empty / error states | all | **PARTIAL** | Standardise |
