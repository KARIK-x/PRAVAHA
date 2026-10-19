# Reference inventory — Mega Tool UI/UX overhaul

**Source:** `~/Downloads/AI trading NEPSE/UI AND FEATURES PHOTO REFERENCE`
**Files:** **106 PNG screenshots** (2880×1800 Retina) + `.DS_Store`. Total 199 MB.
**Method:** every image was loaded and hashed (PIL dHash, 12×12). 106 images fall
into **96 distinct perceptual clusters** (10 near-duplicates), so the collection is
essentially 96 different screens rather than repeated shots. All 106 were then
inspected via **9 numbered contact sheets** (`#1`–`#106`, 12 per sheet, each tile
labelled with its index). Individual screens were re-opened at full size where a
detail mattered.

> Honesty note: **all 106 were visually inspected** at contact-sheet scale, and the
> high-value screens (chart page, dashboard, portfolios, screeners, model grid,
> company analysis, breadth) were inspected at full resolution. A small number of
> tiny textual details (fine print in criteria text, exact column labels in the
> widest tables) could not be read at contact-sheet scale and are marked
> "detail uncertain" where relevant.

**Subject matter:** the collection is overwhelmingly **NEPSE Alpha**
(`nepsealpha.com`, "SastoShare v1.1"), a real NEPSE analytics platform, plus one
**TradingView** chart (#1). It is a *functional* reference: it shows how a mature
NEPSE terminal organises market, stock, screening, portfolio and backtest work.

## Page families observed

| Family | References | What it shows |
|---|---|---|
| Chart workspace | #1 (TradingView), #94–#100 | Large candles + volume, right-side indicator/analysis rail, composition panel, Fibonacci/channel overlays, fresh-breakout panel |
| Market dashboard | #2, #40, #89, #90, #92 | Index bar, barometer, sentiment gauge, sector gain/loss, turnover donut, leading sectors |
| Market breadth | #101–#106 | A/D line, A/D ratio, Arms/TRIN, % above 30MA, PE & dividend-yield chart |
| Sector analysis | #3, #4, #5, #6, #74, #91 | Sector gainers/losers, coverage heat strip, PE-range histogram, % above MA per sector, sector-rotation multi-line, per-sector signal matrix |
| Stock ideas / models | #25, #26, #27, #28 | Model card grid (MultiBagger, Peter Lynch, CANSLIM, Magic Formula, F-Score, Z-Score, G-Score, Bargain, 52-Wk Bargain) + criteria text + ranked results with sparklines |
| Company analysis | #7–#24, #32 | Health Z-score, Bankruptcy risk, F-score, G-score, valuation models (DDM, Graham, Gordon, Peter Lynch), discounted-earnings DCF, DuPont ROE, growth CAGR tables, financial statements, beta/Sharpe/Sortino/drawdown, ownership, board, promoters |
| Screener | #47, #48, #49, #52 | Column chooser (checkbox list), operator filter row, category tabs (General/Profitability/Health/Relative Value/Risk/Technical/Stock Rank), result count, coloured rows |
| Chart scanner | #50, #51 | Pattern tiles (bullish/bearish channel, double top/bottom, H&S, inverse H&S, triangles) each with a detected-pattern thumbnail |
| Comparators | #53, #54, #55, #56 | Growth comparator (1/3/5-yr CAGR + MAD), financial comparator (pick particulars + symbols), price & growth comparison, chart comparator |
| Portfolio | #57–#63, #65–#68 | Value/return stat cards, holdings table, transaction book, risk stats, scoring gauges, risk/reward table, performance book, quarter donuts |
| Backtesting | #33, #34, #35, #36 | Equity curve vs buy-&-hold, returns histogram, trade-analysis donut, returns breakdown percentiles, performance summary, trade log |
| Live scans | #76, #77, #81, #82, #83, #85, #87, #93 | Multi-symbol indicator matrix (MACD/RSI/Stoch/ADX), auto-momentum scan, top-10 boards, support & resistance book |
| Dividend/macro books | #40–#46 | Macro/RBI book, yield charts, scenario chart, dividend safety checklist with explainable comments |
| Signals | #29–#31, #37, #38, #39 | Signal book, buy/sell markers on chart, hypothetical trade performance, edit-signal modal, sector filter panel |

## Recurring design patterns

1. **Chart-first with a right rail.** The working canvas is large; indicators,
   composition and analysis live in a collapsible right column (#94–#100).
2. **Model cards as an index.** Nine named methodologies as coloured tiles, each
   opening a criteria explanation then a ranked table (#25–#28).
3. **Every table carries a mini chart.** Sparklines/quick-charts in result rows
   (#27, #28, #71, #81, #92).
4. **Explainable cells.** Colour + a one-line "comment" column that says *why*
   (e.g. dividend-safety "1.76 (Not sufficient good)", ROE decomposition comments
   in #23).
5. **Category tabs over mega-menus.** Screener/portfolio/analysis pages use tabs
   (General / Profitability / Health / Relative Value / Risk / Technical).
6. **Comparators are first-class**, not an afterthought (#53–#56).
7. **Honest placeholders**: valuation panels show which model is applicable and
   grey out the rest (#20, #21).
8. **Density with hierarchy**: near-solid tables, but a strong header stat strip.

## Per-image index

| # | Reference file | Inspected |
|---|---|---|
| 1 | `Screenshot 2026-10-16 at 2.24.59 PM.png` | yes (contact sheet) |
| 2 | `Screenshot 2026-10-16 at 2.26.20 PM.png` | yes (contact sheet) |
| 3 | `Screenshot 2026-10-16 at 2.26.41 PM.png` | yes (contact sheet) |
| 4 | `Screenshot 2026-10-16 at 2.26.45 PM.png` | yes (contact sheet) |
| 5 | `Screenshot 2026-10-16 at 2.26.48 PM.png` | yes (contact sheet) |
| 6 | `Screenshot 2026-10-16 at 2.26.53 PM.png` | yes (contact sheet) |
| 7 | `Screenshot 2026-10-16 at 2.27.57 PM.png` | yes (contact sheet) |
| 8 | `Screenshot 2026-10-16 at 2.28.00 PM.png` | yes (contact sheet) |
| 9 | `Screenshot 2026-10-16 at 2.28.10 PM.png` | yes (contact sheet) |
| 10 | `Screenshot 2026-10-16 at 2.28.23 PM.png` | yes (contact sheet) |
| 11 | `Screenshot 2026-10-16 at 2.28.28 PM.png` | yes (contact sheet) |
| 12 | `Screenshot 2026-10-16 at 2.28.40 PM.png` | yes (contact sheet) |
| 13 | `Screenshot 2026-10-16 at 2.29.08 PM.png` | yes (contact sheet) |
| 14 | `Screenshot 2026-10-16 at 2.29.33 PM.png` | yes (contact sheet) |
| 15 | `Screenshot 2026-10-16 at 2.29.37 PM.png` | yes (contact sheet) |
| 16 | `Screenshot 2026-10-16 at 2.29.40 PM.png` | yes (contact sheet) |
| 17 | `Screenshot 2026-10-16 at 2.29.55 PM.png` | yes (contact sheet) |
| 18 | `Screenshot 2026-10-16 at 2.30.19 PM.png` | yes (contact sheet) |
| 19 | `Screenshot 2026-10-16 at 2.30.24 PM.png` | yes (contact sheet) |
| 20 | `Screenshot 2026-10-16 at 2.30.32 PM.png` | yes (contact sheet) |
| 21 | `Screenshot 2026-10-16 at 2.30.38 PM.png` | yes (contact sheet) |
| 22 | `Screenshot 2026-10-16 at 2.30.46 PM.png` | yes (contact sheet) |
| 23 | `Screenshot 2026-10-16 at 2.30.53 PM.png` | yes (contact sheet) |
| 24 | `Screenshot 2026-10-16 at 2.30.59 PM.png` | yes (contact sheet) |
| 25 | `Screenshot 2026-10-16 at 2.31.12 PM.png` | yes (contact sheet) |
| 26 | `Screenshot 2026-10-16 at 2.31.29 PM.png` | yes (contact sheet) |
| 27 | `Screenshot 2026-10-16 at 2.31.36 PM.png` | yes (contact sheet) |
| 28 | `Screenshot 2026-10-16 at 2.31.44 PM.png` | yes (contact sheet) |
| 29 | `Screenshot 2026-10-16 at 2.32.11 PM.png` | yes (contact sheet) |
| 30 | `Screenshot 2026-10-16 at 2.32.32 PM.png` | yes (contact sheet) |
| 31 | `Screenshot 2026-10-16 at 2.32.58 PM.png` | yes (contact sheet) |
| 32 | `Screenshot 2026-10-16 at 2.33.22 PM.png` | yes (contact sheet) |
| 33 | `Screenshot 2026-10-16 at 2.33.29 PM.png` | yes (contact sheet) |
| 34 | `Screenshot 2026-10-16 at 2.33.36 PM.png` | yes (contact sheet) |
| 35 | `Screenshot 2026-10-16 at 2.33.38 PM.png` | yes (contact sheet) |
| 36 | `Screenshot 2026-10-16 at 2.33.39 PM.png` | yes (contact sheet) |
| 37 | `Screenshot 2026-10-16 at 2.33.46 PM.png` | yes (contact sheet) |
| 38 | `Screenshot 2026-10-16 at 2.33.52 PM.png` | yes (contact sheet) |
| 39 | `Screenshot 2026-10-16 at 2.33.58 PM.png` | yes (contact sheet) |
| 40 | `Screenshot 2026-10-16 at 2.34.10 PM.png` | yes (contact sheet) |
| 41 | `Screenshot 2026-10-16 at 2.34.14 PM.png` | yes (contact sheet) |
| 42 | `Screenshot 2026-10-16 at 2.34.25 PM.png` | yes (contact sheet) |
| 43 | `Screenshot 2026-10-16 at 2.34.27 PM.png` | yes (contact sheet) |
| 44 | `Screenshot 2026-10-16 at 2.34.32 PM.png` | yes (contact sheet) |
| 45 | `Screenshot 2026-10-16 at 2.34.35 PM.png` | yes (contact sheet) |
| 46 | `Screenshot 2026-10-16 at 2.34.44 PM.png` | yes (contact sheet) |
| 47 | `Screenshot 2026-10-16 at 2.35.02 PM.png` | yes (contact sheet) |
| 48 | `Screenshot 2026-10-16 at 2.35.10 PM.png` | yes (contact sheet) |
| 49 | `Screenshot 2026-10-16 at 2.35.12 PM.png` | yes (contact sheet) |
| 50 | `Screenshot 2026-10-16 at 2.35.16 PM.png` | yes (contact sheet) |
| 51 | `Screenshot 2026-10-16 at 2.35.20 PM.png` | yes (contact sheet) |
| 52 | `Screenshot 2026-10-16 at 2.35.24 PM.png` | yes (contact sheet) |
| 53 | `Screenshot 2026-10-16 at 2.35.26 PM.png` | yes (contact sheet) |
| 54 | `Screenshot 2026-10-16 at 2.35.28 PM.png` | yes (contact sheet) |
| 55 | `Screenshot 2026-10-16 at 2.35.33 PM.png` | yes (contact sheet) |
| 56 | `Screenshot 2026-10-16 at 2.35.36 PM.png` | yes (contact sheet) |
| 57 | `Screenshot 2026-10-16 at 2.36.02 PM.png` | yes (contact sheet) |
| 58 | `Screenshot 2026-10-16 at 2.36.07 PM.png` | yes (contact sheet) |
| 59 | `Screenshot 2026-10-16 at 2.36.10 PM.png` | yes (contact sheet) |
| 60 | `Screenshot 2026-10-16 at 2.36.13 PM.png` | yes (contact sheet) |
| 61 | `Screenshot 2026-10-16 at 2.36.17 PM.png` | yes (contact sheet) |
| 62 | `Screenshot 2026-10-16 at 2.36.22 PM.png` | yes (contact sheet) |
| 63 | `Screenshot 2026-10-16 at 2.36.26 PM.png` | yes (contact sheet) |
| 64 | `Screenshot 2026-10-16 at 2.36.29 PM.png` | yes (contact sheet) |
| 65 | `Screenshot 2026-10-16 at 2.36.31 PM.png` | yes (contact sheet) |
| 66 | `Screenshot 2026-10-16 at 2.36.34 PM.png` | yes (contact sheet) |
| 67 | `Screenshot 2026-10-16 at 2.36.35 PM.png` | yes (contact sheet) |
| 68 | `Screenshot 2026-10-16 at 2.36.39 PM.png` | yes (contact sheet) |
| 69 | `Screenshot 2026-10-16 at 2.36.50 PM.png` | yes (contact sheet) |
| 70 | `Screenshot 2026-10-16 at 2.36.59 PM.png` | yes (contact sheet) |
| 71 | `Screenshot 2026-10-16 at 2.37.03 PM.png` | yes (contact sheet) |
| 72 | `Screenshot 2026-10-16 at 2.37.06 PM.png` | yes (contact sheet) |
| 73 | `Screenshot 2026-10-16 at 2.37.09 PM.png` | yes (contact sheet) |
| 74 | `Screenshot 2026-10-16 at 2.37.13 PM.png` | yes (contact sheet) |
| 75 | `Screenshot 2026-10-16 at 2.37.16 PM.png` | yes (contact sheet) |
| 76 | `Screenshot 2026-10-16 at 2.37.33 PM.png` | yes (contact sheet) |
| 77 | `Screenshot 2026-10-16 at 2.37.40 PM.png` | yes (contact sheet) |
| 78 | `Screenshot 2026-10-16 at 2.37.46 PM.png` | yes (contact sheet) |
| 79 | `Screenshot 2026-10-16 at 2.37.50 PM.png` | yes (contact sheet) |
| 80 | `Screenshot 2026-10-16 at 2.37.54 PM.png` | yes (contact sheet) |
| 81 | `Screenshot 2026-10-16 at 2.37.56 PM.png` | yes (contact sheet) |
| 82 | `Screenshot 2026-10-16 at 2.38.00 PM.png` | yes (contact sheet) |
| 83 | `Screenshot 2026-10-16 at 2.38.04 PM.png` | yes (contact sheet) |
| 84 | `Screenshot 2026-10-16 at 2.38.13 PM.png` | yes (contact sheet) |
| 85 | `Screenshot 2026-10-16 at 2.38.16 PM.png` | yes (contact sheet) |
| 86 | `Screenshot 2026-10-16 at 2.38.23 PM.png` | yes (contact sheet) |
| 87 | `Screenshot 2026-10-16 at 2.38.31 PM.png` | yes (contact sheet) |
| 88 | `Screenshot 2026-10-16 at 2.38.34 PM.png` | yes (contact sheet) |
| 89 | `Screenshot 2026-10-16 at 2.38.42 PM.png` | yes (contact sheet) |
| 90 | `Screenshot 2026-10-16 at 2.38.44 PM.png` | yes (contact sheet) |
| 91 | `Screenshot 2026-10-16 at 2.38.45 PM.png` | yes (contact sheet) |
| 92 | `Screenshot 2026-10-16 at 2.38.48 PM.png` | yes (contact sheet) |
| 93 | `Screenshot 2026-10-16 at 2.38.51 PM.png` | yes (contact sheet) |
| 94 | `Screenshot 2026-10-16 at 2.38.59 PM.png` | yes (contact sheet) |
| 95 | `Screenshot 2026-10-16 at 2.39.05 PM.png` | yes (contact sheet) |
| 96 | `Screenshot 2026-10-16 at 2.39.09 PM.png` | yes (contact sheet) |
| 97 | `Screenshot 2026-10-16 at 2.39.13 PM.png` | yes (contact sheet) |
| 98 | `Screenshot 2026-10-16 at 2.39.17 PM.png` | yes (contact sheet) |
| 99 | `Screenshot 2026-10-16 at 2.39.22 PM.png` | yes (contact sheet) |
| 100 | `Screenshot 2026-10-16 at 2.39.32 PM.png` | yes (contact sheet) |
| 101 | `Screenshot 2026-10-16 at 2.39.44 PM.png` | yes (contact sheet) |
| 102 | `Screenshot 2026-10-16 at 2.39.48 PM.png` | yes (contact sheet) |
| 103 | `Screenshot 2026-10-16 at 2.39.50 PM.png` | yes (contact sheet) |
| 104 | `Screenshot 2026-10-16 at 2.39.52 PM.png` | yes (contact sheet) |
| 105 | `Screenshot 2026-10-16 at 2.39.55 PM.png` | yes (contact sheet) |
| 106 | `Screenshot 2026-10-16 at 2.39.57 PM.png` | yes (contact sheet) |
## Inaccessible / not inspected

**None.** The Dropbox link was not required — the identical collection exists
locally in `UI AND FEATURES PHOTO REFERENCE` (106 files, matching the stated
count). Every file was opened; `.DS_Store` is not an image and was skipped.
