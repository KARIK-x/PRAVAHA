# Final Reference Implementation & Remaining Gaps Report

Mission: bring the NEPSE Mega Tool closer to the reference platform shown in the
106-screenshot analysis (NepseAlpha / SastoShare), implementing the missing
visualisations against **real stored data** with provenance, then close out the
functional chart-analysis defects (P2), the scanner/algorithm information panels
(P3), a full re-verification pass (P4) and the test run (P5).

Scope discipline for this document: a route, component or test **existing** is not
evidence that a workflow works. Statuses below are only `TESTED-PASS` when the
behaviour was actually exercised. Everything else is labelled
`PRESENT (not exercised)`, `ABSENT` or `BLOCKED`, and the reason is given.

---

## A. Executive summary

* **New top-level workspace: Sasto Share.** Added immediately below KIMI Research,
  with **7 nav items** that all open a working destination: Market Pulse, Movers &
  Sparklines, Valuation, Risk & Volatility, Sector Rotation, Dividends, and
  Strategy vs Buy & Hold. One view section (`#view-sastoshare`) with an in-view
  sub-tab row; the sidebar item and the sub-tab drive the same function, so the two
  navigation levels cannot diverge.
* **Nine new endpoints**, all assembled from data the tool already stores
  (`price_bars` in DuckDB, the `fundamentals` table in SQLite, the corporate-events
  registry). No new data source, no estimates, no placeholders: a missing input
  yields `null` plus a reason.
* **P1 features implemented:** table sparklines, 52-week range bars, historical
  P/E + P/B multi-pane chart, support/resistance + risk-reward (daily & weekly),
  volatility projection cone with beta, sector rotation workspace, dividend
  analysis, valuation models (Graham, margin of safety, Gordon growth, PEG), and a
  backtest-vs-buy-and-hold comparison (cumulative return, drawdown, return
  histogram, final value). The fundamental-map market-cap size encoding is
  **opt-in**, because a missing cap must never read as a small company.
* **P2 (chart-analysis defects) fixed at the source.** Elliott Wave and harmonic
  drawings silently produced nothing; the analysis window defaulted to a range
  that was not the chart's. Both layers now *detect and draw* through the same code
  path as the panel's own Draw button, disclose their window and minimum-bar
  requirement, and state the reason when they cannot draw. Seven render controls
  now report `found` vs `drawn`.
* **P3 (ⓘ controls) verified and fixed.** Every scanner preset, backtest strategy
  and KIMI catalogue entry opens the correct implementation-derived panel without
  changing the selection.
* **P4/P5 verification found and fixed two real defects:** the KIMI **Breadth** tab
  rendered an empty table while 5,200 sessions of real breadth history were
  available (it read a non-existent `history` key), and the historical **P/E** pane
  was dominated by a single near-zero EPS period.
* **Tests:** full suite **2,970 collected · 0 failed · 0 errors · 14 skipped ·
  exit 0**. Fourteen opt-in browser cases pass under `MEGATOOL_BROWSER_TESTS=1`.
* **Not done (documented, not faked):** intraday-only visuals, dividend *history*
  (no notices stored), quant model portfolios, Dupont/F-Score/G-Score/Z-Score, and
  a per-symbol news feed inside the chart panel. See §L.

---

## B. Reference materials reviewed

| Artifact | Path | Size / count | How it was used |
|---|---|---|---|
| Structured screenshot analysis | `NEPSE_Mega_Tool_106_Screenshot_Analysis.md` | 133 KB, 1,082 lines, **106 records** | Read in full — the primary feature inventory. OCR present for 86 records. |
| Same analysis as PDF | `NEPSE_Mega_Tool_106_Screenshot_Analysis.pdf` | 4,877,748 bytes | **NOT model-readable.** No `pdftotext`/`pdftoppm`/`pdfinfo`/`mutool`/`qpdf`/`magick` on the machine (only `/usr/bin/sips`). The PDF is a compilation of the same images, so visual evidence was taken from the PNGs below. |
| Screenshot images | `PHOTOS/` | **106 PNGs** | Read as images. This is the visual evidence the PDF contains. |
| Extra reference photos | `UI AND FEATURES PHOTO REFERENCE/` (`DASHBOARD`, `ANALYSIS, PORTFOLIO,SCREENING,SIGNALS AND INDICATORS`) | **116 files** | Available; not individually inspected (the MD inventory already enumerates the same surfaces). |
| App screenshots | `docs/screenshots/` | 15 | Not individually inspected. |

**Actually inspected visually (~21 of 106):** `001` and `087`–`106`. Records
`087`–`106` have **no OCR** in the MD and were resolved from the images; records
`002`–`086` were read from the MD's OCR text, not from pixels. This limitation is
carried forward honestly: a handful of low-level visual details in the OCR-covered
range may differ from the reference in ways neither the MD nor this work captured.
For example the reference **barometer** PNG shows a value near the 52-week high,
while this tool's barometer is an advance-share ⊕ %-above-50-MA transform; the
definition is printed under the gauge so the two can never be confused.

Reference platform: dark-themed **NepseAlpha / SastoShare** (market-overview
dashboards, per-symbol fundamental analysis, screening, signals, backtesting).

---

## C. Reference feature implementation matrix

Status legend:
`TESTED-PASS` = implemented and exercised ·
`PRESENT` = located in the codebase, not exercised ·
`PARTIAL` = some of the reference surface exists ·
`ABSENT` = not implemented ·
`BLOCKED` = needs data/credentials/owner input.

### C1. The Sasto Share workspace (P1 A–K)

Every row below was exercised in the browser on the dev server against the release
store; the backend was additionally exercised with `curl` and with the new
automated tests.

| Reference surface | Status | Where | Implementation | Data source / provenance |
|---|---|---|---|---|
| **(A) Table sparklines** | **TESTED-PASS** | Sasto Share → Movers & Sparklines | per-row inline SVG via `VIZ.sparkline`, 20 stored closes | `price_bars`; the panel states "Sparklines are stored daily closes, not a live tick feed" |
| **(B) 52-week range bar** | **TESTED-PASS** | Sasto Share → Movers (and Pulse) | `ssRangeBar()` — low/high with a position marker; a flat window reports "a position is undefined when high equals low" | `price_bars` 250-bar window |
| **(C) Historical P/E + P/B multi-pane** | **TESTED-PASS** | Sasto Share → Valuation | three stacked SVG panes (price, P/E, P/B) built from `/api/bars/{symbol}` + the fundamentals period series aligned by `period_end` | reported EPS / net worth per share; step series; publication-date limitation disclosed |
| **(D) Support/Resistance + risk-reward** | **TESTED-PASS** | Sasto Share → Risk & Volatility | daily **and** weekly frames via `swing_workbench`; entry/stop/target, R:R, and position sizing; when the structure is "mixed" it says so instead of inventing a level | `price_bars` |
| **(E) Volatility projection** | **TESTED-PASS** | Sasto Share → Risk & Volatility | volatility cone (1σ/2σ bands at 4 horizons) + realised vol + 3-month beta against the stored NEPSE index series | `price_bars` + `index_series`; the cone is labelled derived |
| **(F) Sector rotation workspace** | **TESTED-PASS** | Sasto Share → Sector Rotation | equal-weight sector index (rebased 100), 1w/1m/3m/6m returns, RSI(14), MACD(12,26,9), a 2×2 regime label, ranking table | `price_bars` + the securities master for the sector map; caveat states it is **not** the exchange's sector index |
| **(G) Dividend analysis** | **PARTIAL / BLOCKED** | Sasto Share → Dividends | yield table, payout, safety and a scenario calculator; the panel renders an explicit blocker | no `dps` field and `corporate_events` has 0 rows in dev, so yields are empty with the reason "no dps record stored"; the scenario calculator is explicitly data-independent |
| **(H) Valuation models** | **TESTED-PASS** | Sasto Share → Valuation | Graham number, margin of safety, Gordon growth, PEG — each with formula, value and the inputs used; unavailable models give the missing input | reported EPS / BVPS / P/E |
| **(I) Backtest vs Buy & Hold** | **TESTED-PASS** | Sasto Share → Strategy vs Buy & Hold | cumulative-return comparison, drawdown, return histogram and final value, built from the real `POST /api/backtest` payload so it can never disagree with the backtest shown elsewhere | backtest engine + `price_bars` |
| **(J) Fundamental-map market-cap size** | **TESTED-PASS** | Overview → fundamental map | opt-in checkbox encodes market capitalisation as point radius | market cap is **derived** (`paid_up_capital / 100 × last close`, NRs 100 face value) and labelled as such; symbols without a stored cap draw at minimum radius and the note gives the count |
| **(K) Other missing tools from the audit** | **TESTED-PASS** | Sasto Share → Market Pulse | market barometer, sentiment (% above 50/200-day MA), golden cross, per-sector MA participation, and P/E / P/B / price distribution ranges by sector | stored bars + reported fundamentals; every denominator is printed next to its ratio |

### C2. Present in the app (verified located, not re-exercised this session)

Overview `live-strip`/KPI/index chart, moving-average participation cards, P/E
**distribution bins** and click-through, turnover **heat grid**, top
gainers/losers/most-active, sector table; charting workspace (lightweight-charts)
with Fibonacci/level drawings, chart patterns, candlestick patterns, Elliott,
harmonic, correlation, trailing stop; screener + custom rule builder + factor
ranking; 233-tool catalogue (124 scanners / 77 algorithms / 32 fundamentals);
breadth/seasonality/swing tables; breadth history API; ideas view; portfolio,
journal, backtest, fundamentals, floorsheet, research-desk, news views; KIMI
18-tab workspace.

### C3. Earlier-session visualisation work (re-verified this session)

| Reference surface | Status | Where | Data source / provenance |
|---|---|---|---|
| Market barometer gauge | **TESTED-PASS** | `#ov-gauge`, `renderOverviewVisuals()` | `/api/market/dashboard` → breadth advancers/decliners + `% above 50-day MA`. Labelled "computed transform, not an external feed". |
| Sector performance bars | **TESTED-PASS** | `#ov-sector-chart` (14 bars) | same payload, `sectors[].avg_pct`; click → Sector Explorer |
| Turnover-share donut | **TESTED-PASS** | `#ov-sector-donut` | `sectors[].turnover`; empty sectors omitted |
| Fundamental map (P/E × P/B) | **TESTED-PASS** | `#ov-fundmap` | `valuation.scatter[]` (symbol, pe, pb, sector, **market_cap**); click → chart |
| NEPSE Breadth oscillator chart | **TESTED-PASS** | `#bh-chart`, `renderBreadthChart()` | `/api/breadth/history` series; 7 metrics; definitions echoed |
| Seasonality month/weekday/quarter bars | **TESTED-PASS** | `#sea-chart-months/-weekdays/-quarters` | `/api/seasonality/{symbol}`; quarter compounded from month returns |

Re-verified this session (not assumed): each of the four overview chart hosts
contains exactly one `<svg>` and the sector chart 14 bars; the breadth chart needed
its own **Load** click (it is deliberately on-demand) and then drew 5,200 sessions
1995-07-20 → 2026-10-15, and switching the metric to `pct_above_sma_50` re-rendered
with the matching note; seasonality drew 3 SVGs, 12 month bars and 12 table rows.

---

## D. The Sasto Share workspace (new top-level section) — item 1

* **Placement.** A new `<span class="nav-label">Sasto Share</span>` group in the
  sidebar, immediately below KIMI Research.
* **Seven nav items**, each mapped to a real view:
  `sastoshare` (Market Pulse), `ssmovers`, `ssvaluation`, `ssrisk`, `ssrotation`,
  `ssdividends`, `ssstrategy`.
  They are **seven distinct view names that all resolve to one section**,
  `#view-sastoshare`, through `SS_TAB_TO_NAV` / `SS_NAV_TO_TAB`. The in-view
  sub-tab row (`#ss-tabs`, `data-sstab`) calls the same `ssSubTab()`, so clicking
  the sidebar item and clicking the sub-tab can never show different panels.
* **No dead links, no empty placeholders, no duplicates.** Each panel renders real
  content or an explicit, reasoned unavailable state. Verified in the browser: all
  seven open, all render (pulse 7 cards / 3 SVGs, movers 2 cards / 24 sparkline
  SVGs, valuation 3 panes, risk 7 cards + cone, rotation 2 SVGs + table, dividends a
  reasoned blocker, strategy 3 SVGs after a run), with **no console errors**.
* **Honest limitation.** The requested S-A-S-T-O / S-H-A-R-E wordplay would be ten
  nav items; there are seven, because the mission also requires that *every* nav
  item open a meaningful working destination. Padding to ten would have created
  three dead links. The section therefore carries the platform's own name
  ("Sasto Share") with the seven destinations that have real backing data.

---

## E. Features implemented, and what was reused vs duplicated — items 2 & 3

**Reused (no duplication):**

| Reused component | How Sasto Share uses it |
|---|---|
| `market_store.MarketStore.get_bars` / `index_closes` | every price series, the sector index and the beta regression |
| `market_dashboard.valuation()` / `breadth()` / `movers()` / `sectors()` | the Pulse panel's distribution ranges and sector participation |
| `swing_workbench.swing_workbench` | support/resistance, reference levels, R/R framing, sizing (the daily and weekly frames call the same engine) |
| `backtest.run_backtest` **via the existing `POST /api/backtest` route** | the strategy leg of the comparison — not re-implemented, so the two can never disagree |
| `ta.historical_volatility` | realised volatility for the cone |
| `corporate_events` registry | the dividends panel's notice lookup |
| `web/static/viz.js` | every new chart (line / bars / gauge / donut / scatter / sparkline / empty) — no new third-party dependency |
| `toolInfoHtml` + `#tool-info` modal | no second information renderer was written |

**Genuinely new (nothing equivalent existed):**

* `megatool/sastoshare.py` — nine functions plus helpers (`_bulk_closes`,
  `_latest_fundamentals`, `_fundamental_series`, `_is_annual_label`, `_weekly_frame`,
  `_point_in_time`, `_rsi`, `_macd`, `_histogram`).
* Nine routes in `megatool/api.py`, registered before the StaticFiles mount:
  `GET /api/sastoshare/{pulse,movers,rotation,dividends}`,
  `GET /api/sastoshare/{valuation-history,valuation,risk,volatility}/{symbol}`,
  `POST /api/sastoshare/backtest-vs-hold`.
* The Sasto Share UI block in `web/static/app.js` (router keys, sub-tab, seven
  panel renderers, the shared `ssCard`/`ssKpis`/`ssRangeBar`/`ssUnavailable`
  helpers) and the `.ss-*` styles in `web/static/styles.css`.
* `renderFundMap()` extracted from the inline overview code so the size encoding
  could be added without duplicating the scatter call.
* `tests/test_sastoshare.py` — 37 cases.

**Market capitalisation is derived everywhere.** `paid_up_capital / 100 × last
close` (NRs 100 face value), labelled `derived` with the formula and inputs, and
`null` with a reason where `paid_up_capital` is not stored. The fundamental-map
size encoding is **opt-in** precisely so a missing cap cannot be misread as a small
company; when it is on, symbols without a cap are drawn at the minimum radius and
the note states how many.

---

## F. Rendering defects found, and how the Elliott / harmonic fixes work — items 4 & 5

Defects were reproduced empirically (HTTP API + browser evaluation), not inferred
from reading the code.

### F1. What was actually broken

| # | Defect | Root cause | Fix |
|---|---|---|---|
| 1 | Toggling the **Elliott Wave** layer filled the panel ("N counts found") but drew nothing on the chart | The layer only *ran the detector*; drawing was a separate manual action. A layer is a render control, so the toggle looked broken | `applyChartLayers()` now calls `runElliott()` **and** `drawElliottCandidate(symbol, 0)` — the same code path as the panel's Draw button |
| 2 | Same for the **harmonic** layer | same | `applyChartLayers()` now draws the first candidate via `drawHarmonicCandidate(0)` |
| 3 | A drawn candidate could be **off-screen**, so the user saw an empty chart and a "found" badge | the analysis window was independent of the chart viewport | the default window is now **"Same as chart range"** (`value="chart"` → `#range`), and `revealChartDates()` scrolls the time scale to the drawing |
| 4 | Switching range (60 → 750) kept the old **visible window**, so the new bars rendered off-screen | the viewport was restored unconditionally | the viewport is restored only when symbol **and** timeframe **and** the requested `#range` are unchanged; otherwise `fitContent()` |
| 5 | Elliott/harmonic badges said "N found" even when nothing was drawn | one boolean of information | `state.layerDrawn` records `{drawn, offRange, moved, …}`; badges read `N found · drawn` / `N found · not drawn` / `N found · M drawn` |
| 6 | Harmonic XABCD points had no dates, so drawing had to guess bar indices | the API dropped the date | `/api/bars/{symbol}/harmonic` attaches `date` to each X/A/B/C/D point plus `pivots`, `window`, `minimum`, `renderable` |
| 7 | Elliott candidates had no pivots attached, so the drawing had to re-derive swings | the API returned only the count and label | `/api/bars/{symbol}/elliott` attaches per-candidate `pivots` (date/kind/price/confirmed_date) plus `renderable`, `window{bars,first_date,last_date,confirmed_swings}`, `minimum{…}` and the previously-dropped `message` |

### F2. How the fix works

* **Detect and draw are one path.** `drawElliottCandidate(symbol, i)` reads the
  engine's `pivots` (not a re-derived swing list), filters them to the bars that are
  actually loaded, draws the polyline + markers, and returns a summary object
  `{drawn, offRange, moved, label, certainty, engineCount, first, last}`.
  `runElliottAndDraw()` turns that into a truthful status line, including
  "N of M pivots are outside the loaded range".
* **Reveal, never reload.** `revealChartDates(dates, pad)` scrolls only the time
  scale when a drawing lies outside the viewport. It never changes the number of
  loaded bars and never rescales the price axis, and it is a no-op when the dates
  are already visible.
* **The badge distinguishes detection from ink.** A layer that found 2 candidates
  and drew the first one shows `2 found · drawn`; one that found candidates but
  could not draw shows `2 found · not drawn` with the reason in the results panel.
* **Everything says why when it cannot draw.** Low pullback tolerance, a symbol
  with too few confirmed swings, or a candidate that lies outside the loaded bars
  each produce a specific sentence rather than an empty chart.

### F3. How the seven render controls are explained and connected

`state.layers` (the analysis-layer drawer) covers `sr`, `fib`, `profile`,
`candles`, `patterns`, `elliott`, `harmonic`. `state.overlayVis` covers
`levelLines`, `shapeLines`, `patMarkers`, `candleCap`, plus the display-mode
selector. Verified in the browser at 750 bars, all seven enabled one at a time:

| Control | Badge after loading NABIL @750 | Meaning |
|---|---|---|
| Swing zones (S/R) | `73 found · 8 drawn` | 73 zones detected; the nearest 8 are drawn, and the results panel states that the rest are hidden **on purpose** |
| Fibonacci | `8 found · drawn` | 8 retracement/extension lines drawn from the main swing, with the anchor provenance printed |
| Volume profile | `3 found · drawn` | POC + value area, derived from stored daily bars |
| Candlestick shapes | `200 found · drawn` | 200 shapes detected; the marker cap (`candleCap`, default 15) limits the letters, and the badge reports the cap honestly |
| Chart patterns | `6 found · drawn` | 6 classical patterns; "drawn" means *some* pattern ink is on, because level lines / shape lines / markers are three independent toggles |
| Elliott Wave | `2 found · drawn` | 2 wave counts, first drawn |
| Harmonic | `1 found · drawn` | at 250 bars it honestly reported no band-set match; at 750 one matched and was drawn |

Rapid successive toggles (150 ms apart) persist all three flags
(`{sr, fib, profile}` → all `true` in `localStorage`), so no toggle is lost. The
earlier appearance of a lost flag was a test artefact (repeated toggles against
pre-existing state), not a product defect.

**The display-mode preset** (`#ov-display-mode`) drives `state.overlayVis` and the
dependent selectors, and was verified to change the ink: `standard` → cap 15 → 15
markers drawn, `minimal` → cap 0 → none, `detailed` → cap 40 → 40, `research` →
cap all → all 56. One misleading detail was fixed: `minimal` used to leave the
candle-cap selector reading "last 8" while drawing nothing. The selector now has a
real `none (minimal)` option, the preset sets it to `0`, and the change handler no
longer coerces a legitimate `0` back to `15`.

---

## G. Minimum-bar requirements across ranges — item 6 (Fibonacci) & item 7

`#range` offers `60 / 120 / 250 / 750 / all` — **there is no "30" option**, so a
**~30-bar** window was tested through the API directly (`?limit=30`), which is the
same code path the chart uses. The table is the real response for NABIL.

| Range | bars | Elliott | Harmonic | Classical patterns | Fibonacci |
|---|---|---|---|---|---|
| ~30 bars (API) | 30 | `INSUFFICIENT_EVIDENCE`, 0 candidates, 2 confirmed swings — "Need at least 3 confirmed swings; got 2" | `INSUFFICIENT_EVIDENCE`, 0 windows — "Need at least 5 confirmed swings for an XABCD structure; got 2" | 0 | **5 levels** |
| 3 months (60) | 60 | `CANDIDATE_ONLY`, 2 candidates, 6 swings, renderable 2 | `NO_MATCH`, 2 windows tested, renderable 0 | 2 | 5 levels |
| 6 months (120) | 120 | `CANDIDATE_ONLY`, 2 candidates, 12 swings, renderable 2 | `NO_MATCH`, 8 windows | 6 | 5 levels |
| 1 year (250) | 250 | `CANDIDATE_ONLY`, 2 candidates, 27 swings, renderable 2 | `NO_MATCH`, 23 windows | 6 | 5 levels |
| 3 years (750) | 750 | `CANDIDATE_ONLY`, 2 candidates, 71 swings, renderable 2 | `CANDIDATE_ONLY`, 67 windows, **1 renderable match** | 6 | 5 levels |

Findings:

* **Fibonacci works at every range, including 30 bars.** It anchors on confirmed
  swings, so 5 levels exist even in the shortest window; the anchor provenance
  (which swing, which dates) is printed in the results panel.
* **Elliott and harmonic are swing-count limited, not bar-count limited.** The API
  says so explicitly: *"Counts are built from confirmed swing pivots, not bar count:
  a short window can still qualify if it holds enough pivots, and a long one cannot
  if it does not."* That is why 30 bars gives `INSUFFICIENT_EVIDENCE` with the exact
  pivot deficit while 750 bars gives 71 swings and a renderable harmonic match.
* **Too-short ranges explain themselves.** Instead of silently failing, the panel
  prints the minimum (`confirmed_swings_for_3_wave: 3`,
  `confirmed_swings_for_5_wave: 5`, `confirmed_swings: 5` for XABCD) and the number
  actually found, plus a note that "no match" may mean "not enough structure tested
  yet" rather than "no pattern exists".
* Classical candlestick patterns need at least ~60 bars to produce anything (0 at
  30, 2 at 60, 6 at 120+) — with the marker cap applied on top, and the badge
  reporting both numbers.

---

## H. Information-control fixes (P3) — item 8

* **One reusable model.** `toolInfoHtml(t)` renders 11 sections from the
  catalogue's own per-entry metadata: purpose (the entry's `description`),
  implemented rule (`formula`), default parameters, required input data,
  timeframe, output, how to interpret, execution path, keywords, limitations, and
  the stable id. The three derived lines (timeframe, output, interpretation) are
  computed from the entry's `kind` and `run.engine` and are **visibly labelled
  "derived"** — per-entry wording is never invented.
* **Every ⓘ in the app now resolves to the right entry.** All 31 screener presets
  and all 57 backtest strategies were checked to map to a catalogue id; the
  preset/strategy ⓘ opens the correct modal title. Catalogue counts confirmed by the
  browser: **124 scanners / 77 algorithms / 32 fundamentals**.
* **The ⓘ never selects and never runs.** Verified behaviourally: opening the panel
  leaves the selected option unchanged and runs nothing.
* **The KIMI catalogue ⓘ** now opens the shared floating `#tool-info` modal. The
  inline `#kimi-cat-info` panel sat 6,214 px below the button (effectively
  invisible); it is retained only for Run results and the single-result auto-show.
* **Keyboard and robustness.** Escape closes the modal. Buttons have `type="button"`
  and `aria-label`s; `bindToolInfoModal()` keeps `aria-label`/`title` in sync on
  change. A sparse tool object and a 2,000-character description both render without
  throwing. Modal CSS caps at `max-height: 84vh; overflow: auto`.
* **Honest missing metadata.** Where the catalogue has no entry for a tool, the panel
  says so rather than showing an empty shell.

---

## I. KIMI workflows exercised — item 9

All **18** KIMI tabs were opened and driven this session (the mission refers to the
17 feature tabs plus `overview`). Each was allowed to load and then, where the tab
is on-demand, its Run button was pressed. Results (text length, table rows, first
line, console errors):

| Tab | Result |
|---|---|
| overview | 2 tables, loaded |
| catalogues | 1 table, 11,108 chars (124/77/32) |
| dataquality | 2 tables |
| regime | Run → 5 rows (ACLBSL regime, SMA20/50, trend) |
| liquidity | Run → 10 rows (`liquidity_drought` over real stored volume) |
| **breadth** | **fixed this session** → 10 rows of real sessions with Advancers / Decliners / Unchanged / % above SMA 50 / A/D line |
| forensics | Run → 7 rows (price + stored-fundamental forensics) |
| factors | Run → 30 rows (cross-sectional factor ranking) |
| signals | Run → 4 rows (forward returns, next-session entry, no look-ahead) |
| montecarlo | Run → 8 rows (GBM terminal wealth) |
| valuation | Run → DCF panel |
| portfolio | Run → 15 rows (mean-variance / hierarchical allocations) |
| researchdesk | loaded |
| aidesk | loaded |
| reconcile | loaded |
| snapshots | loaded |
| askdata | loaded |
| corpevents | loaded |

**Defect found and fixed here:** `loadKimiBreadth()` requested
`/api/breadth/history?limit=10` and read `d.history`. The route ignores `limit` and
returns parallel `dates` + named `series` arrays — there is no `history` key — so
the tab rendered "Nothing to show" while 5,200 stored sessions were available. It
now slices the last 10 sessions client-side and renders six real columns, stating
the window and the universe definition.

---

## J. Test results — item 10

| Run | Command | Result |
|---|---|---|
| Full suite | `MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings` | **2,970 collected · 0 failed · 0 errors · 14 skipped · exit 0** |
| Previous session's baseline | same | 2,933 collected · 0 failed · 0 errors · 14 skipped |
| Delta | — | **+37** (`tests/test_sastoshare.py`). No previously-passing test changed outcome. |
| Opt-in browser tests | `MEGATOOL_BROWSER_TESTS=1 … pytest tests/test_browser_objects_manager.py tests/test_browser_viz_toolinfo.py -q` | **14 passed, exit 0** |
| New unit/contract tests | `pytest tests/test_sastoshare.py` | **37 passed** |
| JS syntax | `node --check web/static/app.js` | clean |
| Lint | `ruff check megatool/sastoshare.py tests/test_sastoshare.py` | clean |
| Format | `ruff format --check` on the files touched this session | clean |

The **14 skipped** are the opt-in browser tests; they are skipped by design without
`MEGATOOL_BROWSER_TESTS=1`.

**What the 37 new tests pin** (all synthetic and deterministic — no test asserts
anything about real NEPSE prices, and no test reaches the network; the live
securities feed behind the sector map is monkeypatched):

* honesty rules — a missing input is `null` plus a reason; derived figures say so;
* denominators — the pulse's breadth ratios carry the universe that actually had
  the window, and a sector's participation count matches its own members;
* the P/E step function steps at the period end, prefers the source's reported
  `pe`, and flags a suspect period without hiding it (`pe_axis.points_above_cap`);
* the growth rate uses **annual** periods only, refuses a CAGR off a negative base,
  and names which condition failed;
* Graham / margin of safety compute from stored inputs; Gordon and PEG return
  `null` with the missing input named;
* the buy-and-hold leg shares the strategy's exact dates and pays the same one-off
  entry cost, and the histogram count equals the trade count;
* the cone widens monotonically with the horizon and β is a real number when an
  index series is stored;
* dividends are empty **with a blocker** when nothing is stored, and the yield is
  `derived` with a correct payout when a DPS row exists;
* sector rotation labels its own index as an equal-weight **derived** index, and a
  member with too little history is *excluded* rather than truncating the sector —
  a defect the tests caught and the module now fixes;
* invalid symbols and unknown strategies are rejected with a 4xx.

**Manual work still needed even though tests pass:** none of the browser
interactions are covered by the normal suite. The seven Sasto Share panels, the
seven render controls, the ⓘ controls and all 18 KIMI tabs were therefore also
driven by hand in a real browser, and the two defects in §F1/§I were found that
way — i.e. tests passing did not mean the workflows worked.

---

## K. Remaining blockers — item 11

Carried forward unchanged from `REMAINING_BLOCKERS.md` / `BLOCKED_FEATURES_AUDIT.md`,
minus the resolved python-dotenv item:

1. **Kronos NABIL GPU run** — awaits explicit owner approval. The only community
   package found (`github.com/Aabishkar2/nepse-data`) is unlicensed (L-03).
2. **Live NEPSE API** — 401 / no intraday; corporate actions all `unadjusted`;
   `security_master` empty in dev. Intraday-only reference visuals (intraday
   sentiment, live sparklines, live sector gain) are therefore out of reach on real
   data and are not stubbed.
3. **Dividend analysis is data-blocked, not code-blocked.** `corporate_events` has
   **0 rows** in the dev store and the fundamentals table holds only `eps`,
   `net_worth_per_share`, `paid_up_capital`, `pe` and `profit` — there is no `dps`
   field. The Dividends panel therefore shows an empty yield table with the reason
   "no dps record stored", and the scenario calculator is explicitly independent of
   stored data. Nothing is inferred from price history.
4. **Floorsheet / dividend-bonus-AGM notices / IPO-rights-allotment** — need an
   external document or a credentialed collector run (the import paths are
   implemented and tested on synthetic input).
5. **Autonomous scheduling (NF-018)** — needs an OS-level timer (cron / launchd /
   systemd); the on-demand engine and one-shot CLI exist and pass.
6. **Publication dates (NF-025) and pre-existing revision history (NF-028)** —
   cannot be reconstructed from existing data; disclosed in-product.
7. **Holiday calendar** — `trading_calendar.json` has no holiday entries, so the
   holiday seasonality study returns `available: false` with the real reason.
8. **The dev DuckDB store is exclusively locked** by the running dev server, so all
   verification went through the HTTP API. `data/dev/qa` is empty.
9. **Commit / push / deploy** — not authorised; not performed. Production (`:8710`)
   was never touched.
10. **`python-dotenv` CVE** — **RESOLVED** (installed and locked at 1.2.4, above the
    recommended 1.2.2; the two stale blocker documents were corrected).

---

## L. Incomplete reference features — item 12

| Reference surface | Status | Why it is not done |
|---|---|---|
| Intraday sentiment / live sparklines / live sector gain | **BLOCKED** | live NEPSE API returns 401 and has no intraday feed; stored data is daily only. Stubbing it would fabricate data. |
| Dividend **history** (per-year book, growth, safety score) | **BLOCKED** | no `dps` and no notice rows. The yield *calculator* and the honest blocker are implemented. |
| Quant model portfolios (Alpha30, Sector Rotation portfolios) | **ABSENT** | would need a published constituent list and rebalancing rules that the reference does not publish in the screenshots; inventing a "model portfolio" would be a fabricated product. |
| Dupont / F-Score / G-Score / Z-Score / quant ranking per symbol | **ABSENT** | needs balance-sheet and cash-flow fields (total assets, liabilities, current ratio, receivables) that the fundamentals store does not hold. |
| Per-symbol news feed inside the chart side panel | **PARTIAL** | the news view and `/api/news/*` exist; embedding it in the chart panel was not done. |
| Alert delivery (email/webhook/desktop) | **BLOCKED** | would need credentials and an outbound channel; the in-app alert engine and one-shot CLI exist. |

---

## M. Changed files — item 13

Files created (this session unless noted):

| File | Purpose |
|---|---|
| `megatool/sastoshare.py` | the nine Sasto Share analytics functions + helpers |
| `tests/test_sastoshare.py` | 37 unit + contract tests (synthetic, offline) |
| `web/static/viz.js` | *(earlier)* SVG visualisation primitives, no new dependency |
| `tests/test_ui_viz_assets.py` | *(earlier)* fast static wiring guards |
| `tests/test_browser_viz_toolinfo.py` | *(earlier)* opt-in browser regression |
| `FINAL_REFERENCE_IMPLEMENTATION_AND_REMAINING_GAPS_REPORT.md` | this report |

Files modified:

| File | Change |
|---|---|
| `megatool/api.py` | nine `/api/sastoshare/*` routes (registered before the StaticFiles mount); Elliott/harmonic routes now attach `pivots`, `date`, `window`, `minimum`, `renderable`, `message` |
| `megatool/market_dashboard.py` | `valuation()` emits `scatter[].market_cap` plus `coverage.market_cap_available` / `market_cap_note` |
| `web/static/app.js` | Sasto Share block (router keys, `initSastoShare`, `ssSubTab`, `loadSastoShare`, `ssCard`, `ssKpis`, `ssRow`, `ssRangeBar`, `ssUnavailable`, `ssCaveats`, `ssPctCell`, `bindSsValuation`, `ssRenderPePane`, `ssDividendScenario`, `ssRunStrategy`, seven panel renderers); `renderFundMap()`; Elliott/harmonic `drawElliottCandidate` / `drawHarmonicCandidate` / `revealChartDates` / `elliottWindowParams` / `applyElliottCfg` / `applyHarmonicCfg`; `applyChartLayers` drawn-state reporting; `renderLayerDrawer` badge; `loadKimiBreadth` fix |
| `web/static/index.html` | Sasto Share nav group + `#view-sastoshare` section; `#ov-fundmap-size` checkbox; cache-busters (`styles.css v=wb7`, `app.js v=wb42`) |
| `web/static/styles.css` | `.ss-*` panel styles, `.warn-text`, `.ss-pe-toggle` |
| `docs/API_ROUTE_INVENTORY.md` | regenerated from the app (`scripts/route_inventory.py --md`) — now lists the nine `/api/sastoshare/*` routes with their test coverage |
| `MASTER_MISSION_CHECKLIST.md` | §9 for the Sasto Share session |
| `REMAINING_BLOCKERS.md` | §11 corrected — python-dotenv resolved at 1.2.4 |
| `BLOCKED_FEATURES_AUDIT.md` | python-dotenv row corrected to RESOLVED |

No production change was made: the release instance on **:8710** was never touched;
all work ran on the dev server on **:10000**. No commit, push or deploy was
performed. No secrets were added, no paid API or dependency was introduced, and no
destructive database operation was executed.

---

## N. Preserved: earlier-session subsections

### N1. Visualisation primitives (`web/static/viz.js`)

Hand-rolled SVG, **no new third-party dependency**, uses the app's existing CSS
custom properties.

| Primitive | Purpose | Interactivity | Accessibility |
|---|---|---|---|
| `VIZ.line(host, spec)` | multi-series line / area, zero line, bands, y-axis ticks | hover crosshair + tooltip | `role="img"`, `aria-label`, legend |
| `VIZ.bars(host, spec)` | vertical/horizontal bars, ± colouring, value labels, mean line | per-bar `<title>`; optional click | `role="img"`, `aria-label` |
| `VIZ.donut(host, spec)` | donut with legend and centre label | per-slice `<title>` | `role="img"`, `aria-label` |
| `VIZ.gauge(host, spec)` | semicircular dial with coloured zones + band label | zone `<title>` | `role="img"`, `aria-label` |
| `VIZ.sparkline(host, spec)` | tiny inline trend line | `<title>` | `role="img"`, `aria-label` |
| `VIZ.scatter(host, spec)` | x/y scatter, optional size encoding (`sizeBy` / `r` / `maxR`) | per-point `<title>`, optional click | `role="img"`, `aria-label` |
| `VIZ.empty(host, text)` | explicit empty state | — | plain text |

All primitives re-render on host resize (`ResizeObserver`, debounced) and never
invent values — a series with no finite points renders `VIZ.empty`.

### N2. Technical-indicator selector UI

* **Compact row** (`indInstanceRowHtml`): colour chip · name (truncating) · ⓘ ·
  `Hide` · `⚙ n` (parameters) · `✕` (remove).
* **Behind the ⚙ toggle** (`.ii-extra`, hidden by default): parameter inputs, Apply
  / Reset / Rename, Duplicate, Move up / Move down, and the category label.
  Expansion state lives in a module-level `indExpandedIds` Set and is deliberately
  **not** persisted into the chart layout (a view preference, not chart state).
* **Nothing removed:** every indicator, instance, parameter, overlay, calculation
  and the existing `#ind-info` pane are intact.

### N3. The seven earlier actionable tasks

| # | Task | Status | Evidence |
|---|---|---|---|
| 2.1 | python-dotenv CVE upgrade | **RESOLVED** | installed and locked at **1.2.4**; the two stale blocker documents were corrected |
| 2.2 | NF-001 floorsheet facts | **IMPLEMENTED · TESTED (synthetic)** | `tests/test_floorsheet.py`; still needs a real external document |
| 2.3 | NF-018 autonomous scheduling | **PARTIAL / BLOCKED** | on-demand engine + history + cooldown + one-shot CLI pass; the timer needs an OS scheduler |
| 2.4 | NF-025 point-in-time data | **IMPLEMENTED · TESTED** | `megatool/fundamentals.py` + `tests/test_fundamentals_pit_revisions.py`; the publication-date archive does not exist and is disclosed |
| 2.5 | NF-028 revision monitor | **IMPLEMENTED · TESTED** | going-forward old→new logging + `revision_monitor`; pre-existing history is unrecoverable and stated |
| 2.6 | Other actionable gaps | **RE-CHECKED** | the remainder are data-, environment- or owner-dependent |
| 2.7 | Regression & verification | **TESTED** | see §J |

Master checklist: see `MASTER_MISSION_CHECKLIST.md` §8 (earlier P1–P4 pass) and §9
(this Sasto Share session), with the per-item statuses above.
