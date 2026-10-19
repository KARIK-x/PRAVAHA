# 28 analysis groups — status as of session 24 (2026-10-17)

Statuses are judged at **capability** granularity, from the code and tests that
exist in this repository, not from intent. A group is `TESTED-PASS` only when a
module exists *and* tests cover it; `PARTIAL` when some of it exists; `NOT
STARTED` when no module exists; `BLOCKED` when it needs data that is not
available (live/intraday).

| # | Group | Status | What exists / what is missing |
|---|---|---|---|
| 1 | Candlestick patterns & price action | **TESTED-PASS** | `ta/candles.py` (18 detectors incl. harami_cross, tweezer top/bottom), `/api/bars/{symbol}/candles`, chart markers |
| 2 | Trend & moving averages | **TESTED-PASS** | `ta/trend.py`: SMA/EMA/WMA/HMA/DEMA/TEMA/KAMA/Supertrend/Aroon/VWMA/PSAR |
| 3 | Oscillators (RSI, Stoch, StochRSI, MACD, CCI, MFI, ROC…) | **TESTED-PASS** | `ta/momentum.py`, `ta/other.py` (RSI/MACD/Stoch/CCI/ROC/Williams/TRIX/StochRSI/PPO/CMO/TSI) |
| 4 | Bollinger, ATR, PSAR, Ichimoku, volatility | **TESTED-PASS** | `ta/volatility.py` (BB/ATR/Donchian/Keltner/HV); Ichimoku in `ta/other.py` |
| 5 | Volume, VWAP, OBV, **Volume Profile** | **TESTED-PASS** | OBV/MFI/A-D/RelVol/VWAP-bands/CMF/Chaikin exist; Volume Profile added 2026-10-17 (`ta/profile.py`, `/api/bars/{symbol}/volume-profile`, chart layer): POC/tie→lower price, classic 70% two-sided value area (pointer-moved-bug caught in development and fixed), strict-HVN/LVN, overlap-proportional allocation; 11 module tests + endpoint contract; layer browser-verified on NIMB |
| 6 | Breakouts, false breakouts, reversals, gaps, ranges | **TESTED-PASS (new detectors)** | S/R levels + breakout logic in `ta/levels.py`/`ta/patterns.py`; gap + false-breakout classifiers added 2026-10-17 (`ta/gaps.py`, `/api/bars/{symbol}/gaps`, `/api/bars/{symbol}/breakouts`): gap = fact + ATR-scaled rule class (common/runaway/breakaway/exhaustion) with stated basis and post-hoc `closed_within_bars`; breakouts true/false/unconfirmed with measured run-beyond-level; 13 tests; live-verified on NIMB (4 gaps, 4 breakouts) |
| 7 | Relative strength & momentum screening | **TESTED-PASS** | `scanner.py` `relative_strength` metric + `/api/bars/{symbol}/relative-strength` (benchmark required, aligned dates) |
| 8 | Fibonacci retracements & extensions | **TESTED-PASS** | `ta/fibonacci.py`, `/api/bars/{symbol}/fibonacci` (200-contract), chart overlay, manual drawings |
| 9 | Elliott Wave | **TESTED-PASS** | `ta/elliott.py`, `/api/bars/{symbol}/elliott`, windowed + chart overlay |
| 10 | Chart patterns & **three-drive** | **PARTIAL** | `ta/patterns.py` chart-pattern catalogue; **no three-drive** pattern |
| 11 | Smart Money Concepts / ICT | **NOT STARTED** | No module; no BOS/CHoCH/displacement code |
| 12 | Liquidity, **order blocks**, supply/demand zones | **PARTIAL** | `ta/levels.py` S/R *zones* only; no order-block or liquidity-sweep detector |
| 13 | Wyckoff & market cycles | **NOT STARTED** | No module; `regime.py` is regime labels, not Wyckoff phases |
| 14 | Multi-timeframe analysis | **TESTED-PASS** | `ta/multitimeframe.py`, multi-timeframe indicator, `/weekly` `/monthly` routes |
| 15 | Swing trading & stock selection | **TESTED-PASS** | `ta/swings.py`, `/structure`, scanner/ranking |
| 16 | Intraday strategies & options education | **BLOCKED / NOT STARTED** | Intraday needs a live feed (blocked, see `docs/LIVE_DATA.md`); options content is educational only |
| 17 | Trading psychology & risk management | **PARTIAL** | `risk.py` (portfolio risk limits) exists; no psychology/discipline tooling |
| 18 | Position sizing, stops, **trailing stops** | **TESTED-PASS (new)** | `planning.py` position sizing + `risk.py` unchanged; trailing-stop engine added 2026-10-17 (`ta/trailing.py`, `/api/bars/{symbol}/trailing-stop`, advanced-analysis card): chandelier/swing/pct rules on one shared ratchet (up-only), strictly causal stop series, exit needs a later bar's low, no open-price fill claimed; 12 tests; card browser-verified on NIMB (837 bars, chandelier stop, historical exit at bar 36) |
| 19 | Fundamental analysis & financial ratios | **PARTIAL** | `fundamentals.py` + `/ratios` + YONEPSE financials adapter exist; **0 verified records ingested** |
| 20 | Company valuation & intrinsic value | **NOT STARTED** | No valuation/DCF module |
| 21 | Financial-statement analysis | **PARTIAL** | `fundamentals.py`, written-PDF transcription pipeline; depends on the same 0 verified records |
| 22 | Portfolio construction & management | **TESTED-PASS** | `portfolio.py` (positions, avg cost, realised/unrealised P&L, cash flow), `/api/portfolio*`, `risk.py` |
| 23 | Trading journal & performance review | **TESTED-PASS** | `journal.py`, `/api/journal` |
| 24 | IPO analysis & multibagger screening | **NOT STARTED** | IPO appears only as news notices (`news.py`); no IPO analytics |
| 25 | Floorsheet & broker-holding research | **TESTED-PASS** | `floorsheet.py`, `/api/floorsheet/*`, `/trend` |
| 26 | NEPSE & sector analysis | **TESTED-PASS** | `index_series.py`, `sectors.py`, `benchmark.py`, `/api/indices*` |
| 27 | AI-assisted strategy development | **PARTIAL** | `agent.py`+`llm.py` (deterministic rules; LLM optional) and `/api/screens/propose`; no free-form code generation (by design) |
| 28 | Strategy backtesting & quant evaluation | **TESTED-PASS** | `backtest.py`, `experiments.py`, `walkforward.py`, `/api/backtest`, `/api/experiments/*` |

**Tally:** TESTED-PASS 14 · PARTIAL 8 · NOT STARTED 5 · BLOCKED 1 (group 16 overlaps
`NOT STARTED`).

**Highest-value gaps:** SMC/ICT + order blocks (11–12), Wyckoff (13), valuation
(20), fundamentals ingestion (19/21), Volume Profile (5), trailing stops (18).
None of these is blocked by the live-data question — they are unbuilt, not
blocked.

**Note on reachability.** Groups 8, 9, 10, 14 are also reachable from the chart
UI; group 5's VWAP/OBV are reachable as indicators. A capability that exists only
as an engine with no route/UI is marked PARTIAL here even if its unit tests pass
(decision 11).

---

### Session 24 update — free real data now flows

* **Live pipeline**: the free public source now delivers **current-day**
  observations (the earlier "3.9 days stale" was the GitHub-Pages CDN mirror, not
  the data). See `docs/LIVE_DATA.md`.
* **Fundamentals (Groups 19/21)**: **21,698 real records across 307 symbols**
  (EPS, P/E, net-worth/share, paid-up capital, profit) imported from the same
  free source — no longer "0 verified records". Ratios still report
  **unavailable** until a stored price exists (never invented).
* Everything else is unchanged from the table above; Group 20 (valuation) remains
  NOT STARTED and Groups 11–13 (SMC/ICT, Wyckoff) remain NOT STARTED.

---

### Session 25 update

* **Group 19/20 inputs are now real and usable**: 372 symbols of daily OHLCV
  (1995→2026-10-15) and 21,698 reviewed fundamental records; **P/E and P/B derive
  from stored inputs** (NABIL P/E 19.25, P/B 2.21). Dividend yield remains
  unavailable (no DPS records). Group 20 (valuation/DCF) is still NOT STARTED.
* Groups 11–13 (SMC/ICT, order blocks, Wyckoff) remain NOT STARTED.
* All other rows are unchanged; the core-TA groups were re-verified by the suite
  (658 indicator/pattern/scanner tests pass).
