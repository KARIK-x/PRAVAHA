## 2026-10-18 — session 30: comprehensive audit, indicator validation, 5 new advanced-analysis capabilities

**Added**
* **Indicator audit** — all 92 indicators examined; 5 empty references + 11 empty
  notes + 36 missing param descriptions filled. Verification map 49/41/2 →
  **62/28/2**.
* **Scanner promotion rule fixed** — numeric tests now promote over earlier
  invariant results.
* **25 numeric reference tests** (`tests/test_indicators3.py`) + independent naive
  helpers (`tests/_naive_helpers.py`).
* **5 genuinely new capabilities**: rolling beta, volatility percentile, MTF
  confluence, technical rating, S/R strength scoring.
* **16 tests** (`tests/test_advanced_analysis.py`) for the new capabilities.
* **Info/search audit** — 92/92 ⓘ buttons, "money flow" → CMF + MFI.
* **Fibonacci re-verified** — `{75,175}` → `{75,175}`, 0 console errors.

**Test headline**
* Full suite **2,701 passed / 0 failed / 0 errors / 8 skipped, exit 0**
  (`$TMPDIR/full_s30.log`). Opt-in browser module 8 passed / exit 0.

## 2026-10-18 — session 29: complete the chart-objects manager, fix detector-marker lifecycle, measure Fibonacci viewport

Following the read-only session-28 verification, this session closes the three
chart-object defects it found. Frontend only for the fixes; no backend, DB or
production change (prod `8710` untouched, dev `10000`).

**Fixed**
* **B-107 — quick-layer objects missing from the Objects manager.** The
  chart-toolbar toggles (`SMA 20/50`, `EMA 20`, `Bollinger`, `Volume`, `RSI pane`,
  `MACD pane`, `Swings`, `Close-based pivots`) created real series/panes whose
  handles were discarded, so nothing listed or could remove them. `loadChart` now
  registers one `state.quickObjects` descriptor per toggle and the manager gained
  a **Quick layers** group. Hide/Remove act on the real primitive: series
  `visible`, pane element + `chart.remove()`, and the markers a quick layer owns
  (swings/close-swings) are filtered out of `state.markers` on Remove.
* **B-108 — candlestick markers leaked across symbols.** `state.candleMarkers` was
  only reset inside `runCandles()`; `destroyCharts()` now resets it (and
  `state.quickObjects`), so a symbol with the layer off no longer inherits the
  previous symbol's letters (NABIL 122 → ADBL 0).
* **B-109 — pattern markers lost on reload.** `applyChartLayers()` re-rendered the
  panel (`renderPatternPanel()`, needs an in-memory scan) instead of fetching, so
  a persisted `patterns` layer drew nothing after a reload. It now calls
  `loadPatternPanel(symbol)`: 9 markers → full reload → 9 markers.
* **B-110 — `#pattern-overlay` checkbox leaked across symbols.** It was set true
  for a layer-on symbol and never cleared, and `loadChartInsights()` always loads
  the pattern panel, so a layer-off symbol still drew markers. It is now synced to
  the current symbol's flag before `loadChartInsights` runs (NABIL 9 → ADBL 0).

**Verified (browser, real trusted events)**
* Quick overlays/panes appear with label/type/owner; Hide/Show/Remove act on the
  chart; removing `quick-swings` cleared all 27 owned markers.
* Detector markers reconstruct from persisted layer config; no duplicate objects
  across three full reloads.
* **Fibonacci viewport measured** (the session-28 gap): manual `fib_retracement`
  and `fib_extension` and automatic `fib` each preserved `{75,175}` byte-for-byte
  in normal mode and `{87,187}` in expanded mode; existing drawings/indicators
  intact; 0 console errors. Screenshot `docs/evidence/wb24-objects-quick.png`.

**Added**
* `tests/test_browser_objects_manager.py` — 8 browser-driven regression cases
  (quick layers, oscillator panes, Hide/Remove + owned-annotation cleanup,
  detector-marker restoration, no-duplicate reloads, manual + automatic Fibonacci
  viewport, object preservation, console errors). **Opt-in**
  (`MEGATOOL_BROWSER_TESTS=1`); skipped (8) in the default offline suite.

**Not changed / honest gaps**
* Quick-layer toggles remain **unpersisted** display toggles, so swing-marker
  quick layers cannot reconstruct after a reload (their config is not stored). The
  persistent equivalent is the analysis layers, which do reconstruct (B-109).
  Recorded in `REMAINING_BLOCKERS.md` §23.
* Per-marker suppression stays session-only (persisting it would store transient
  UI state against recomputed output).

## 2026-10-18 — session 28: market ribbon, chart-object manager, visible Elliott, viewport root-cause fix, 11 new indicators

**Added**
* **Market ribbon** (backend `GET /api/market/ribbon` + a rewritten horizontally
  scrolling frontend strip): index info, top gainers/losers, turnover, volume and
  52-week extremes from the most recent stored trading day, grouped under category
  headers, with a freshness badge, **pause/resume** (persisted in
  `localStorage['mt-ribbon-paused']`) and click-to-load into the chart. Categories
  with no honest source are returned in `unavailable` with a stated reason
  (`relvol`); duplicates are claimed by the first group and reported in
  `skipped_duplicates`. 8 API tests in `tests/test_api.py`.
* **Unified chart-object manager** (`Objects` toolbar button → floating,
  draggable, resizable `#obj-pane`): every visible chart object with its **owner**,
  a plain-language description, a visibility toggle and a remove action — so
  pattern markers, candle letters, S/R zones, pivots, Elliott labels and harmonic
  points all have one place to inspect and clear. Marker provenance is stored in a
  side table (`state.markerMeta`) so Lightweight Charts renderer payloads are not
  altered.
* **Elliott Wave now draws on the chart**: "Analyze & draw on chart" claims a
  **candidate** count (`CANDIDATE_ONLY`, with pivot count and confidence in the
  status line) and draws the wave labels + connecting line; "Remove chart
  drawing" erases it and restores manual labels. The viewport is unchanged.
* **Active-tool banner**: states the active drawing/Elliott tool and how many
  anchors are placed (`Elliott impulse · 2/5 anchors`), and hides when the tool is
  deactivated.
* **11 indicators** in `megatool/ta/extra.py` (81 → **92**): `vortex`, `ma_cross`,
  `chande_kroll_stop`, `bollinger_width`, `percent_b`, `chaikin_volatility`,
  `relative_volatility_index`, `average_price`, `price_correlation`,
  `williams_fractal`, `zigzag` — each with formula, reference, notes and
  parameter variables, an ⓘ info entry, and its own test.

**Changed**
* **Adding an indicator no longer re-frames the chart** (root cause): the
  pane↔price time-scale sync is now one-directional (price → pane) and
  `addToChartFromCatalog()` captures/restores the visible logical range around
  every add. Verified `{80,200}` preserved for both overlay and pane adds.
* **S/R and Fibonacci axis labels no longer overlap**: caps
  `MAX_OVERLAY_LINES=8`, `MAX_OVERLAY_LABELS=4`, `OVERLAY_LABEL_MIN_GAP=0.012`.
* **The verification generator can no longer over-claim**: an explicit
  `INVARIANT_TESTS` set keeps the global invariant tests at coverage level, and
  sparse-pivot indicators are parsed from `SPARSE_PIVOT_INDICATORS`. Honest split
  regenerated: **49 reference / 41 invariants / 2 sparse / 0 none** over 92
  indicators.
* **`scripts/generate_indicator_reports.py` made reproducible**: counts,
  placement and the verification split are computed from the live registry (the
  placement mirror is asserted against the browser matrix **33 overlay / 59
  pane**), and the catalogue now emits a **Verification** section generated by
  the same scanner the UI uses.
* Indicator-drawer catalogue re-verified: **"92 of 92 registered"**, 92 ⓘ
  buttons; search by name, abbreviation and term.
* Cache-buster bumped to `app.js?v=wb21`.

**Fixed (defects)** — see `KNOWN_BUGS.md` B-100…B-106.

## 2026-10-18 — session 27: drawing repairs, honest index candles, command palette, scoped Clear, viewport preservation

**Added**
* **Global command palette** (`⌕ Search` in the chart toolbar, or **Cmd/Ctrl+K**
  from anywhere): one search box over views, chart types, all 39 drawing tools,
  analysis layers, all 81 registered indicators, screener presets and actions
  (fit/zoom/expand/undo/redo/clear/catalog/compare/replay). Keyboard-driven
  (↑ ↓ ↵ Esc), grouped results with hints, and a curated catalogue mapping the
  owner's requested names onto real features — entries with no implementation
  are listed **disabled with the reason** so search never returns a dead control.
* **Clear button** next to Chart settings, opening a scoped confirmation dialog
  (drawings on this symbol / indicators on this chart / analysis layers) with
  live counts. Nothing is cleared until confirmed; saved layouts, templates,
  watchlists, portfolios and journals are untouchable by construction; drawing
  clears are undoable with Cmd/Ctrl+Z and indicator removes with the drawer's
  Undo.
* **Pane headers** on every custom indicator pane: drag-to-resize, collapse /
  expand, taller / shorter, and ✕ to remove the indicator (undoable). Height and
  collapsed state persist on the instance, so a reopened chart keeps its layout.
* **`genuine_first_date` / `genuine_last_date`** on
  `/api/indices/{name}/ohlc`, so the candle region's start is stated by the API
  instead of inferred from the loaded window.

**Changed**
* **The NEPSE index now renders genuine candlesticks.** Chart-type availability
  is driven by the data rather than the instrument: with 2,217 genuine OHLC rows
  (2016-11-28 →) candles, hollow candles, Heikin Ashi and OHLC bars are enabled
  for the index; a genuinely close-only series disables them with the reason in
  the option tooltip.
* **Viewport preservation.** Switching tabs and re-loading the same
  symbol+timeframe (adding a layer, adding an indicator, applying a template) no
  longer calls `fitContent()`; the visible logical range is captured and
  restored. Fit remains an explicit button.
* **Drawing interaction reworked**: body hit-testing for every tool, capture-
  phase pointer handling so the chart does not pan during a drag, logical-
  coordinate drag mapping (works between bars and past the last bar), on-chart
  selection handles, and a Delete/Backspace handler that is typing-guarded.
* The OHLC legend labels a close-only/invalid row honestly and shows the index's
  market-wide turnover as `T/O` rather than `V`.

**Fixed** — see `KNOWN_BUGS.md` session 27: **B-92** (eraser only hit anchors),
**B-93** (no Delete/Backspace), **B-94** (drag also panned the chart),
**B-95** (no selection feedback; placement tools hijacked drags), **B-96**
(selection polluted undo), **B-97** (index console 404s), **B-98** (index
close-only restriction + fabricated placeholder OHLC), **B-99** (auto fitContent
reset the viewport).

**Evidence** — full suite `MEGATOOL_DATA_DIR=data/dev/release pytest -q`:
**2,599 tests, 0 failures, 0 errors, 0 skipped, exit 0** (`$TMPDIR/full3.log`);
`tests/test_index_ohlc_history.py` extended and passing (15 tests); browser
verification with real trusted pointer/keyboard events on NABIL (250 bars) and
NEPSE (750 bars): trendline draw → select → drag (range unchanged 0→249) →
eraser → Cmd+Z → Delete → Cmd+Z → Cmd+Shift+Z; typing-guard (Delete while
`#symbol-input` focused = no-op); Clear dialog drawings-only + undo; S/R layer
toggle with viewport preserved {81.8,167.2}; pane collapse/tall/remove + drawer
undo; indicator catalog "81 of 81 registered"; console **0 errors, 0 warnings**.
Screenshots: `docs/evidence/workbench-2026-10-18-index-candles.png`,
`-palette.png`, `-clear-dialog.png`, `-catalog.png`, `-pane-headers.png`,
`-drawings.png`.

---

# Changelog

All notable changes to Mega Tool, newest first. The repository has **no commits**
for this work (everything is uncommitted on `main` @ `b6c3659`), so this file is
the change record the commit history would otherwise carry. Dates are Nepal time;
"session" numbers follow the numbered runs recorded in the blocker register.

Format: each entry lists **Added**, **Changed**, **Fixed**, and the **Evidence**
(tests / gates actually run).

---

## 2026-10-18 — session 26: chart workbench — indicator drawer, 35 new indicators, chart types, compare, breadth/seasonality/swing

**Added**
* **35 new registered indicators** (46 → 81) across `megatool/ta/trend2.py`,
  `momentum2.py`, `volatility2.py`, `volume2.py`; each carries its formula and
  published reference in the registry; covered by 36 literal reference tests
  (`tests/test_indicators2.py`) and generic guards over all 81
  (`tests/test_indicators.py`).
* **Chart-side indicator drawer** replacing the toolbar popover
  (`#pop-indicators-btn` opens `#ind-drawer`): search, categories, favourites,
  recents, templates, undo/redo (depth 40), multi-instance unique ids with
  duplicates allowed, per-symbol persistence, and in-place upgrade of older
  saved entries. QA surface: `window.__mtIndDrawer`.
* **Compare drawer** (`#cmp-drawer`, `#pop-compare-btn`): primary + up to 3
  comparison symbols; five modes (% change from window start, indexed to 100,
  relative to NEPSE ratio × 100, rolling return %, raw on shared left scale);
  per-row colour/style/width/visibility; explicit alignment — rebase on each
  symbol's first visible observation, missing dates are gaps, never
  interpolated; relative mode states when the index is unavailable.
* **Chart-layout JSON v1** export/import (quick layers + indicator instances +
  compare + chart type) and instance-aware templates (old flag-only templates
  still apply).
* Chart types: hollow candles, Heikin Ashi (documented display transform),
  step, baseline, column, line + markers — on top of candles/bars/line/area.
  `INDEX_ALLOWED_TYPES` restricts index symbols to close-only-family types.
* `GET /api/breadth/history` with `megatool/breadth.py` (advances/declines/
  unchanged, % above SMA-N, A/D line, A/D volume line, new highs/lows, net) +
  the **Breadth History** view (8 unit tests + API tests).
* `GET /api/seasonality/{symbol}` with `megatool/seasonality.py` (month and
  weekday return stats with thin-month exclusion; holiday study reports
  unavailable-with-reason until a holiday calendar exists) + the
  **Seasonality** view (9 unit + 4 API tests).
* `GET /api/bars/{symbol}/swing-workbench` with `megatool/swing_workbench.py`
  (structure, nearest confirmed levels, measured-move arithmetic, readings
  checklist, position sizing; every missing input stays `None` + reason) + the
  **Swing Bench** view (7 unit + 2 API tests).
* Volume Scanner: 7 metrics (34 → 41: volume ratio 50, volume vs 20-day max,
  climax 5-vs-20, up/down volume ratio, OBV pressure, range compression,
  pocket pivot) and 8 presets (23 → 31); preset names surface in the screener
  UI and run on the real store.

**Changed**
* Indicator placement is now a documented rule set (`indPlacement()` in
  `web/static/app.js`): display hint first; momentum/volume → synced pane;
  trend → price overlay except `adx`, `aroon`, `linreg_slope`, `supertrend`;
  volatility → overlay only for pure upper+middle+lower band groups
  (Bollinger keeps a pane so `bandwidth`/`%B` cannot wreck the price scale);
  price-unit "other" series overlay. Browser-verified matrix: 28 overlay /
  53 pane. Multi-output indicators draw **all** outputs (one pane per
  instance; palette-cycled colours).
* Dev release cache-buster `?v=wb7` (app.js); production stays on 8710.

**Fixed**
* B-89 — chart-view HTML defects (duplicate `chart-meta` id, malformed `</h2>`,
  missing `</nav>`, stray `</footer>`) → document parses with 0 errors.
* B-90 — trend indicators with non-band output names were routed to panes
  (EMA/SMA in their own pane); fixed by the placement rules above.
* B-91 — a hidden instance's pane was force-unhidden by `addPane` sizing and
  stayed visible until reload; `drawPane` now re-applies `el.hidden`.

**Evidence**
* Full suite **2,599 passed / 0 failed / 0 skipped, exit 0**
  (`MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings`).
* `ruff check` clean on all session files; `ruff format --check` clean on all
  files authored this session; `node --check web/static/app.js` exit 0;
  route inventory 134 routes (22 mutating / 112 read-only), 125
  test-referenced. `megatool/api.py` keeps 21 pre-existing format hunks in
  earlier sessions' regions (`REMAINING_BLOCKERS.md` §10).
* Browser: 0 console errors / 0 warnings; screenshots
  `docs/evidence/workbench-2026-10-18-{new-indicators,compare,breadth,swing}.png`.
* New reports: `IMPLEMENTATION_STATUS.md`, `INDICATOR_CATALOGUE.md`,
  `INDICATOR_SOURCE_AND_LICENSE_AUDIT.md`, `CHART_UX_AUDIT.md`,
  `REMAINING_BLOCKERS.md`; regenerator `scripts/generate_indicator_reports.py`.

---

## 2026-10-16 — session 25: resilient free data, real price universe, local release on :10000

**Fixed**
* **Broken upstream merge no longer costs freshness.** YONEPSE's only branch
  carried a merge-conflict commit (`<<<<<<< HEAD` instead of JSON) on every market
  file, and the Pages mirror was days stale. The adapter now tries `main`, then
  walks back through recent commits (GitHub API, cached) choosing the **newest
  parseable** quote board, then the mirror — reporting the ref it used. It served
  **today's** data (NEPSE 2,625.93; 328 quotes) during the incident. Conflict
  markers are never repaired into data.
* **Startup log reported the wrong port.** `serve --port 10000` logged
  "Binding 127.0.0.1:8710" (the config default). The CLI now publishes the
  effective host/port and the boundary line reads `127.0.0.1:10000`.
* **Header overstated the absence of data.** It said "no live feed — historical
  dataset only" while a working public source was serving current-day prices; it
  now reads "delayed public source (yonepse) — not a live feed".

**Added**
* **`megatool fundamentals review --source <src> [--level reviewed|verified]`** —
  the explicit, source-scoped operator action the ratio guard implies. Ratios
  refuse `extracted` values by design; this promotes them without weakening the
  guard or reviewing globally. `review_source()` + 5 tests.
* **YONEPSE commit walk-back** with cached commit lookup, plus tests for the
  broken-merge case and the "never repair conflict markers" rule.

**Verified with real data**
* Historical fetch: **372/372 symbols, 515,327 rows, 1995-07-20 → 2026-10-15**.
* Fundamentals: **21,698 records / 307 symbols** reviewed; **NABIL P/E 19.25,
  P/B 2.21** from stored inputs with provenance and verification level shown.
  Dividend yield stays `null` (no DPS records) — never invented.
* Browser on `127.0.0.1:10000`: 14 views, **0 console errors**; chart renders 7
  canvases for `NABIL · 120 bars · github.com/Aabishkar2/nepse-data` with the
  "prices unadjusted" caveat; screener evaluated **372, eligible 350, passed 18,
  insufficient 22**; diagnostics show `DELAYED`, age 75.6 min, provider vs receipt
  time, latency, origin.

**Evidence**
* Full suite **2184 passed / 0 failed / 0 errors / 0 skipped**; `ruff` clean;
  `node --check` clean; `route_inventory.py` **103 routes, all test-referenced**;
  Go bridge `go vet` + `go test` pass.
* Screenshots: `docs/evidence/session25-{overview,chart-nabil,diagnostics}.png`.
* Production (PID 26596, :8710) untouched; gate unset; 0 staged/stashed.

---

## 2026-10-16 — session 24: free *current-day* NEPSE data (the staleness was a CDN)

**Fixed**
* **The free public source was pointing at a stale mirror.** `megatool/datasources/yonepse.py`
  read the CDN-cached **GitHub-Pages** copy (~4 days stale) instead of the
  repository's **raw content**, which was current. Measured the same minute:
  Pages `last_checked 2026-10-12T10:17`, raw `last_checked 2026-10-16T07:17`
  (31 min old) with **NEPSE 2,625.93** at `13:01` and **328 quotes** carrying
  in-session last-trade times. `BASE_URLS = (raw, pages)` now tries raw first and
  falls back to Pages only when raw is unreadable.
* **Freshness is cadence-aware.** `megatool/live.py` gains
  `publish_cadence_seconds` per provider and a status vocabulary: `live` (≤30 s)
  → LIVE_VERIFIED; `delayed` (within the source's own cadence) ; `stale` beyond;
  `last-close` when the market is closed; `historical` beyond 5 days. An hourly
  publisher at ~40 min is now correctly **DELAYED**, never "stale" and never "live".
* **Provenance of the mirror is reported.** `fetch_market_snapshot()` returns the
  base that answered; the payload exposes `origin`, so a fallback can never be
  described as fresh raw content.

**Added**
* **Live data-source diagnostics** in the Data view: each provider's status,
  observation age, provider vs receipt time, request latency, securities returned,
  poll vs publish cadence, and the actual origin mirror.
* **31 new/changed tests** across `tests/test_live.py` and
  `tests/test_datasources_yonepse.py` (base ordering, JSON-repair refusal,
  cadence-aware bands, status mapping, Pages-fallback provenance, origin).

**Verified with real data (free, no auth, no key, no allow-list)**
* **21,698 fundamental records across 307 symbols** ingested from the same source
  (EPS, P/E, net-worth/share, paid-up capital, profit). Ratios correctly return
  **unavailable** without a stored close — *"a price must not be invented"*.
* Observed an upstream incident in real time: the raw file briefly contained
  **git merge-conflict markers**; the adapter fell back to Pages and reported
  `STALE` (age 4.0 d) **with the origin and a fallback note**. Conflict markers
  are never "repaired" into data.
* Official API still `401 WARNING: UNAUTHORIZED ACCESS` (anti-bot token); the gate
  is never set by the app and go-nepse is not exercised live.

**Evidence**
* Full suite **2179 passed / 0 failed / 0 errors / 0 skipped**; `ruff` clean;
  `node --check` clean; `scripts/route_inventory.py` **103 routes, all
  test-referenced**.
* Browser: Overview live strip and Data-view diagnostics, **0 console errors**
  (`docs/evidence/session24-live-sources.png`, `session24-overview-live.png`).
* Production untouched.

---

## 2026-10-16 — session 23: live market data — a measured provider layer

**Added**
* **`megatool/live.py`** — a provider-agnostic live market layer. Providers:
  `sharehub` (licensed, ~20 s), `official` (gated go-nepse), `feed` (owner JSON
  URL), `yonepse` (public hourly fallback). Freshness is **measured** from the
  source's own newest timestamp (`age_seconds`) and surfaced separately from
  request latency; each provider is cached at its publication cadence.
* **Read-only routes** `GET /api/live/status`, `GET /api/live/market`,
  `GET /api/live/quotes`. `/api/status` now reports a real `live_feed_connected`
  and a `live` provider block.
* **Overview "Live market" strip** — provider, freshness badge, market
  open/closed, NEPSE index + change, observed age, quote count, source timestamp,
  a *Refresh now* button, and an end-to-end-age explanation. It polls only while
  Overview is visible.
* **29 new tests** (23 in `tests/test_live.py`, plus route/status tests in
  `tests/test_api.py`).

**Changed**
* `docs/LIVE_DATA.md` (new) records the provider comparison, the measured
  blocker, latency-vs-age, and the exact owner steps. `DECISIONS.md` adds
  D-bi…D-bm.

**Verified (measured, not assumed)**
* Official API `/api/nots/*` → **401 `WARNING: UNAUTHORIZED ACCESS`** without the
  anti-bot token; tokens are a WASM challenge. TLS verifies (DigiCert, to
  2026-12-10). → official live data stays **BLOCKED**; the gate is not the only
  obstacle.
* YONEPSE `/api/live/market`: request **1,334 ms**, observation **≈3.9 days old**
  → labelled **`stale`** in the API and the UI. 368 quotes returned.
* ShareHub reachable (`/my-ip` 200 in 0.14 s) but needs a licence + IP allow-list.
* `nepseapi.com` is early-access only; the free `NepseAPI-Unofficial` host
  returned **HTTP 522** (down). No free public sub-second source exists.

**Evidence**
* Full suite **2174 passed / 0 failed / 0 errors / 0 skipped**; `ruff` clean;
  `node --check` clean; `scripts/route_inventory.py` **103 routes, all
  test-referenced**; `uvx pip-audit` **no known vulnerabilities**.
* Browser: live strip renders correctly with 0 console errors across all views
  (`docs/evidence/session23-live-strip.png`).
* **Live access remains BLOCKED**; production (PID 26596) and its databases were
  never touched.

---

## 2026-10-16 — session 22: *actual* go-nepse integration + portfolio cash-flow model

### Actual go-nepse Go library, integrated behind a process boundary

**Added**
* **The real Go library, integrated.** `tools/gonepse-bridge/` is a small Go `main`
  package pinned at `github.com/voidarchive/go-nepse v0.2.5`. It links the library,
  reads one JSON request on stdin and writes one JSON envelope on stdout. Operations:
  `market-summary`, `market-status`, `securities`, `find-security`, `live-market`,
  `price-history`, `nepse-index`, `sub-indices`, `company`, `company-profile`,
  `dividends`, `floorsheet`, `market-depth`.
* **`GoNepseAdapter`** (`megatool/datasources/gonepse.py`) conforming to the existing
  provider contract, plus a network-free diagnostics route `GET /api/gonepse/status`
  and a `go-nepse` entry in `GET /api/sources`.
* **Provenance label** `DataSource.GONEPSE`, distinct from `NEPALSTOCK_OFFICIAL`.

**Changed**
* `docs/GO_NEPSE_INVESTIGATION.md` gains §11 (implementation + tests + honest status);
  its headline is banner-marked as superseded. `DECISIONS.md` adds D-bc…D-bg and marks
  **D-aj superseded by D-bc**.

**Fixed / verified**
* **TLS verification is ON and the certificate validates.** A verified handshake to
  `nepalstock.com.np:443` succeeds (DigiCert/GeoTrust, valid to 2026-12-10). The
  library's documented "cert problems" are absent today, so no insecure mode is used.
* **The owner gate holds in both layers.** Python refuses before spawning when
  `MEGATOOL_NEPSE_API_AUTHORIZED != "1"`; the bridge refuses a real-host call and
  exits `3`. Neither layer sets the variable.
* **Upstream quirk handled:** `Options.BaseURL` is ignored by the library for every
  request; the bridge sets `Options.Config.BaseURL`.

### Portfolio cash-flow model

**Added**
* **`cash_flows()`** (`megatool/portfolio.py`): a per-trade, signed cash-flow view
  derived from the recorded transactions. A **buy** costs `quantity × price + fees`
  (negative); a **sell** returns `quantity × price − fees` (positive); `cumulative`
  is the running total in `traded_at, id` ledger order. The summary reports
  `total_invested`, `total_proceeds`, `total_fees`, `net_cash_flow` and
  `per_symbol_net`. New read-only route **`GET /api/portfolio/cash-flow`**; the same
  summary is embedded in `GET /api/portfolio` as `cash_flow`, and shown as four
  stats in the Portfolio panel.
* **Honesty contract:** the model says in its own `note` that it is the *recorded
  trades'* net cash effect, **not an account cash balance** — deposits, withdrawals,
  dividends, interest and taxes are not recorded. The valuation note keeps "Cash
  balances are not modelled"; the two statements coexist rather than contradicting.

### Evidence

* `go vet` + `go test ./...` in `tools/gonepse-bridge`: **9/9 pass**.
* Full Python suite: **2150 passed / 0 failed / 0 errors / 0 skipped** (`pytest -q`
  + junitxml aggregate). **29 new Python tests** this session (21 adapter, 3 route/API,
  5 portfolio cash-flow) on top of session 21's 2121, plus 9 Go tests Python does not
  run.
* `ruff check .` pass; `ruff format --check .` 224 files; `node --check
  web/static/app.js` exit 0; `scripts/route_inventory.py` **100 routes (21 mutating,
  79 read-only), all test-referenced**.
* Python→Go→real-library roundtrip exercised (gate set locally, host unreachable →
  honest `network_error`); gate-unset path refuses before spawn.
* Browser: Portfolio panel shows Invested/Proceeds/Fees/Net cash flow and the
  caveat; Data & Quality shows the go-nepse row (`subprocess-json`, auth required,
  TLS on, "not authorized"); **0 console errors/warnings across all views**
  (`docs/evidence/session22-portfolio-cashflow.png`, `session22-sources-gonepse.png`).
* `docs/evidence/session22-nepse-tls-cert.txt` (verified TLS chain).
* **Live connection: BLOCKED** — the gate is unset; no live NEPSE request was made.
  Production (PID 26596, `127.0.0.1:8710`) and its databases were never touched.

---

## 2026-10-16 — session 21: fix the defects a re-verified frontend exposed

**Fixed**
* **B-61 — the API-detected Fibonacci overlay never rendered.** `plotFibonacci`
  read a non-existent `data.levels` array; the route returns `retracements` +
  `extensions`. The overlay now draws the endpoint's real levels, labelled and
  colour-coded, and nothing when `available` is false.
* **B-62 — a screen "passed" a security whose required metric was unavailable.**
  `evaluate_node` dropped unknown clauses, so `rsi < 30 AND bars_listed >= 60`
  passed a flat/illiquid symbol. Now three-valued: an AND/OR containing an
  unknown clause with no decisive boolean is *unknown* → the security is
  ineligible and the reason is shown.
* **B-63 — the assistant panel could not be closed.** `.chat-panel { display: flex }`
  beat the UA `[hidden]` rule; `[hidden] { display: none !important; }` makes the
  attribute authoritative.
* **B-64 — `/api/sources` mislabelled a gated source as down.** `available: null`
  ("not probed") now renders as "not probed"; the gated official and snapshot
  entries carry `access_method`/`requires_auth`, an `authorized` badge and a note.
* **B-60 — `/fibonacci` returned 422 for "not enough swings".** It now returns
  `200 {available:false, unavailable_reason}` (a malformed level set stays a 400),
  matching `relative-strength`/`patterns`.

**Changed**
* `megatool/api.py` — `/fibonacci` contract + ratio validation; `/api/sources`
  provenance fields.
* `megatool/scanner.py` — three-valued node evaluation.
* `web/static/app.js` — `plotFibonacci`; Screener/rule-builder "Why" shows the
  specific unavailable reason; Data & Quality source table (3-state + notes).
* `web/static/styles.css` — `[hidden]` authoritative.

**Evidence**
* `pytest` → **2121 passed / 0 failed / 0 errors / 0 skipped** (+5 tests).
* `ruff check .` pass · `ruff format --check .` 221 files · `node --check` exit 0 ·
  `route_inventory.py` **98 routes (21 mutating, 77 read-only), all test-referenced**.
* Real browser: 13/13 views, **0 console errors/warnings**; QABANK2 renders 11
  labelled Fibonacci levels; EDGEFLAT/EDGENAN are ineligible on the oversold preset.
  Screenshots: `docs/evidence/session21-fib.png`, `session21-screener-nan.png`,
  `session21-sources.png`.

---

## 2026-10-15 — session 14: Phase 1 closure + index consumption

**Added**
* `megatool/ranking.py`: `IndexAvailability` + `index_availability()` — a
  data-driven availability object for the `relative_strength` factor, mirroring
  the existing sector-factor pattern.
* `megatool/api.py`: `GET /api/indices` (stored series + coverage + benchmark
  identity) and `GET /api/indices/{name}` (one date-ordered series; **404** on an
  unknown name, never an empty-but-successful body).
* `tests/test_index_consumer.py` (15 tests) — availability states; the benchmark
  return is measured over the ranking **window**, not the lifetime; factor
  ordering by excess return; API list/series/404/empty; `/api/rank` benchmark
  disclosure.
* `CHANGELOG.md` (this file).

**Changed**
* `relative_strength` is now a **real, weightable ranking factor** measured against
  the official **NEPSE composite only** (`NEPSE_COMPOSITE_INDEX`). No substitute
  benchmark is ever asserted; when the series is absent/too short the factor is
  reported unavailable with a *measured* reason.
* `/api/rank` loads `store.index_closes("NEPSE")` and discloses the benchmark used
  (`RankResult.benchmark`), including its bar count and 60-day return.
* `megatool/friend_access.py`: `GET /api/indices` and `GET /api/indices/{name}`
  added to the deny-by-default friend allowlist (public, read-only market data).
* `tests/test_ranking.py`: two tests updated to treat `relative_strength` as a
  data-driven factor (previously a static "unavailable" entry). Default rankings
  are unchanged — the factor is weight 0 unless a caller weights it.

**Fixed**
* **B-44** — the ranking claimed *"Index data is unavailable; no substitute index
  is asserted"* while the store held **17 index series / 7,611 rows**. The stale
  static claim was removed; availability is computed from the store.
* **B-10 / BLK-8** — the historical index data now has a consumer (see Added /
  Changed). Previously it was stored but unused beyond a dashboard note.

**Evidence**
* Full suite **1820 passed / 0 failed / 0 errors / 0 skipped** (`junitxml`, 28.56 s).
* Focused: `test_index_consumer.py` 15 passed; `test_ranking.py`
  `test_financial_integrity.py test_sector_factor.py test_api.py
  test_friend_access.py` 238 passed.
* `ruff check` + `ruff format --check` clean on changed paths.
* Gates with `MEGATOOL_NEPSE_API_AUTHORIZED` unset: ingest **exit 2**; benchmark
  **schedule-only exit 0, zero NEPSE requests**; source-health **no host contact**.
* Production untouched: DuckDB mtime `2026-10-15 09:24:38`, app SQLite
  `2026-10-14 15:52:00`, server PID 26596 alive, 0 staged.

---

## 2026-10-15 — session 13: NEPSE-official live client + reliability + deployment scaffolding

**Added**
* `megatool/datasources/nepse_official_live.py` — the official-API client
  (anonymous `prove` → salt-strip `Salter` token, validated against the real
  `css.wasm` with max error 0.0), **gated OFF**.
* `megatool/benchmark.py` + `scripts/benchmark_market_hours.py` — a market-hours
  latency/freshness harness with schedule-only and replay modes and a pidfile lock.
* `megatool/source_health.py` + `scripts/check_source_health.py` — certificate
  inspection (expiry + days remaining, warn ≤ 30 d) and a health cache.
* `megatool/friend_access.py` — deny-by-default friend route allowlist + shared
  server-side token comparison (loopback = owner, never challenged).
* `docs/deployment_architecture.md`, `.env.example`, `netlify.toml`.

**Changed**
* `megatool/api.py` — `create_app` middleware/CORS wiring; `/api/sources` gained an
  add-on `health` field.
* `web/static/app.js` + `index.html` — runtime API-base + friend-token header.
* Hardened `_get_json`: circuit breaker (injectable clock), capped `Retry-After`,
  jitter backoff, 401-refresh-once, no retry on 401/403, retry on 5xx/timeouts.

**Evidence**
* Full suite **1805 passed**; gate refusal exit 2 on every gated script.

---

## 2026-10-15 — sessions 5–12 (summary)

* Coverage model disaggregated (`megatool/coverage.py`): identity 372/372,
  ordinary 277/277; the "78.3%" figure was cross-source *unanimity*, not coverage.
* Fundamentals Lab correctness: a real `PE == 0` no longer refuses a file;
  YONEPSE duplicate reporting periods de-duplicated by `(symbol, period_end)`.
* Sector-relative ranking: mutual funds/debentures no longer ranked against their
  issuer's ordinary shares.
* `regime.py` date bug fixed (dates came from row positions on the production shape).
* Historical index loader + `index_series` table (`megatool/index_series.py`).

---

## Standing invariants (never change without a new decision)

* The NEPSE collector stays gated OFF until the owner rules (Rule 9 / BLK-1).
* TLS certificate verification is never disabled.
* Unavailable data is never turned into a zero-valued quote.
* Synthetic fixtures are never presented as live evidence; provenance is per-row.
* Production databases and the running server are never modified by agent runs;
  all testing uses isolated DBs / temp storage.

---

## 2026-10-15 — Phase 2–6 autonomous run (session-15)

**Added**
* `megatool/ta/patterns.py` — rule-based classical chart patterns (double/triple
  top & bottom, H&S + inverse, ascending/descending/symmetrical triangles,
  rising/falling wedges, bull/bear flags, channel breakout) over confirmed swing
  pivots. Descriptive only; documented quality rule; look-ahead-safe.
* `megatool/stats.py` — descriptive stats, return/risk stats, Pearson/Spearman
  with exact Student-t p-values, OLS, rolling correlation, autocorrelation,
  variance ratio, correlation matrix. numpy-only (scipy not imported).
* API: `GET /api/bars/{symbol}/patterns`,
  `GET /api/bars/{symbol}/statistics`, `GET /api/stats/correlation`
  (routes 72 → 75, all test-referenced).
* `scripts/perf_smoke.py` — isolated, backend-only performance harness.
* `docs/PHASES_2_6_PROGRESS.md` — the required progress record (traceability,
  feature matrix, reference audit, six verification rounds, security, perf).
* Charts-view panels in `web/static/` for patterns, statistics and correlation.

**Changed**
* `megatool/scanner.py` — presets 4 → 23; 18 new single-symbol metrics
  (macd family, macd_cross, sma_cross, bollinger %B/bandwidth, stochastic K/D,
  mfi, adx, donchian position/breakout, turnover_sma_ratio).
* `megatool/friend_access.py` — allowlist extended for the new read-only routes.
* `.gitignore` — `data/dev/` (isolated dev/bench data) ignored.
* `docs/API_ROUTE_INVENTORY.md` regenerated; `MEGA_TOOL_FEATURE_STATUS.md`
  updated (classical chart patterns and statistical analysis no longer gaps).

**Verification**
* Full suite: **1999 passed / 0 failed / 0 errors / 0 skipped** (32.2 s).
* `ruff check .` clean; `ruff format --check .` 200 files.
* Reference-platform audit: all 15 URLs fetched and classified.
* Safety: gate OFF (zero NEPSE calls), production DBs untouched, nothing
  committed/staged/pushed/deployed.

**Documented bottleneck:** `POST /api/rank` (p50 ≈ 397 ms at 60 symbols × 650
bars) scales ~linearly; recorded as the top optimisation candidate, not
rewritten this session.

---

## 2026-10-16 — verification mission (session 16)

No new features. Focus: independent verification, defect hunting, and one
demonstrated optimisation.

**Defects found and fixed**
* **B-47** — symbol validation was inconsistent across six per-symbol endpoints
  (10-char cap on some, none on others), so a stored 11-char symbol analysed on
  one route and 400'd on another. Found by the E2E pass. Now one shared
  `valid_symbol()` on every per-symbol route.
* **B-49** — `/elliott` and `/harmonic` let `SwingError` escape as a 500 on a
  NaN-bearing series while their siblings returned a clean 400. Found by a
  degenerate-fixture sweep. Fixed.

**Hardening**
* `_log_access_boundary()` prints the access-boundary state at startup on every
  entrypoint, including a non-loopback/no-token WARNING that
  `uvicorn megatool.api:app` previously never showed. Never prints the token.
* One unescaped server value (`d.data_as_of`) wrapped in `esc()` (defence in
  depth; it is always a date).

**Performance (T-20 resolved)**
* **B-50** — `rolling_std` computed `np.std` per window; it was 89% of
  `rank_universe` runtime. Vectorised it (mean-centred cumulative sums) and made
  `historical_volatility` reuse it. `POST /api/rank` p50 **391.7 → 113.6 ms**
  (3.45×), results verified unchanged against pandas and an independent loop.
  No caching introduced.

**Verification added**
* `scripts/verify_quant.py` — independent cross-check harness (pandas, scipy,
  hand-computed backtests). All checks agree.
* `scripts/qa_fixture.py` — isolated end-to-end fixture builder.
* Full-browser E2E across all 11 views: 0 console errors.
* `docs/RELEASE_READINESS.md` — evidence-based readiness checklist.

**Verification results**
* Full suite **2007 passed / 0 failed / 0 errors / 0 skipped** (31.9 s).
* `ruff check .` clean; `ruff format --check .` 205 files; `node --check` clean.
* `scripts/verify_quant.py` exit 0; `route_inventory.py` 75 routes, all tested.

**Safety:** production DBs untouched, PID 26596 never signalled, gate unset
(zero NEPSE requests), all QA data isolated and deleted, 0 staged, nothing
committed/pushed/deployed.
 All other endpoints measured ≤ 19 ms p50.

**Defects found by the new tests / browser QA:** B-45 (KAMA volatility
off-by-one) — FIXED and covered by an independent reference; B-46 (frontend
percent scaling, found by the browser QA pass) — FIXED and re-verified against
the API. Both recorded in `KNOWN_BUGS.md`.

**Browser QA (first for this run):** an isolated dev server on `127.0.0.1:8712`
+ `playwright-cli` verified the real data → calc → API → DOM chain: 46
indicators served, patterns/statistics/correlation panels populated, correlation
values matched an independent numpy recomputation to 1e-9, all 23 scanner presets
listed and one run reported `Evaluated 4 · Eligible 4 · Passed 1`, and **0 console
errors across all 11 views**. The server was then killed and the dev data deleted;
the production server (PID 26596) and its databases were never touched.

# (continued)

## 2026-10-16 — session 26: reference-driven UI overhaul (shell · Ideas · docs)

**Added**
* **New app shell.** The flat 13-button top bar is replaced by a **left sidebar**
  with six labelled groups (Market / Discover / Portfolio / Research / Strategy /
  Data) and a top bar carrying a **global symbol search** and the data-freshness
  chip. Matches the reference rail (`docs/ui-redesign/REFERENCE_INVENTORY.md`).
* **Ideas view** — the reference's model-card index. Ten methodologies
  (Graham value, Peter Lynch PEG, book-value bargain, 52-week bargain, relative
  momentum, multi-bagger, CAN SLIM, Magic Formula, Piotroski F-score, Altman
  Z-score) rendered as cards with category, methodology and status. `megatool/ideas.py`
  + `GET /api/ideas` + `GET /api/ideas/{model}`.
* **Breadth stacked bar** on the dashboard (advancers/decliners/unchanged/missing)
  alongside the exact counts.
* **Reference documentation** `docs/ui-redesign/{REFERENCE_INVENTORY,
  REFERENCE_FEATURE_MATRIX,DESIGN_SYSTEM,IMPLEMENTATION_PLAN}.md`.

**Honesty rules encoded in the Ideas view**
* A model runs **only** when every input exists. Magic Formula, Piotroski F-score
  and Altman Z-score need EBIT, enterprise value, working capital, cash-flow or
  total assets — none is stored — so they are **disabled** and name the missing
  fields instead of producing a score.
* Per-share fields are bounds-checked; a unit error in the source (e.g. total
  equity stored as net-worth-per-share) is **refused**, not ranked.
* Negative EPS growth no longer raises (a fractional power of a negative ratio is
  complex) — it simply yields no growth score.

**Fixed**
* Price-only models (momentum, 52-week) were restricted to symbols that had
  fundamentals, silently shrinking their universe; the universe is now price
  membership and each model reports its own coverage.
* Graham ranking was inverted (worst margin of safety first); higher margin now
  ranks first.

**Evidence**
* Suite **2199 passed / 0 failed / 0 errors / 0 skipped** (2184 → 2199: +13 ideas,
  +2 route); `ruff` clean; `node --check` clean; `route_inventory.py` **105 routes,
  all test-referenced**; Go bridge tests pass.
* Browser (dev instance on `127.0.0.1:10000`): 14 views, **0 console errors**;
  sidebar 6 groups / 14 buttons; Ideas shows 10 cards, 3 disabled; Graham run →
  372 evaluated, 40 matched (ADBL fair value 1024.67 vs 333.8); breadth bar
  59.9 / 32.8 / 7.3 / 0 %. Screenshots `docs/evidence/session26-*.png`.
* Production (PID 26596) untouched; gate unset; 0 staged/stashed.

---

## 2026-10-16 — session 27: the chart workspace, actually finished

**Redesigned (phase D of the UI overhaul, previously NOT STARTED).**
* **The chart is now the main event.** The oversized settings card above it is
  gone; the canvas is `clamp(360px, 100vh − 250px, 820px)` wide and gets the
  remaining space, with the analysis drawer on the right when open. Controls live
  in one compact toolbar: Symbol · Timeframe · Chart type · Indicators · Draw ·
  Analysis · Fit / zoom / fullscreen / CSV.
* **Clean by default.** Candles + volume only. Support & resistance, Fibonacci,
  candlestick patterns, chart patterns, Elliott Wave and harmonic patterns are
  all **off** until switched on in the Analysis drawer, and each reports its own
  count (`fib 10`, `candles 56`, `patterns 6`, `elliott 14`, `harmonic none`).
* **An Analysis drawer, not a wall of levels.** Six layers with counts, "Hide
  all", per-layer persistence in `localStorage["mt-chart-layers-<SYM>"]`, and a
  "Detected items" list whose rows highlight their own overlay line. The S/R
  layer reports *"73 zones detected, 10 nearest drawn"* rather than drawing 73.
* **Overlay hygiene rules.** At most `MAX_OVERLAY_LINES = 10` lines per layer,
  labels only on the `MAX_OVERLAY_LABELS = 5` nearest the traded price, nearest
  first, dashed hairlines instead of thick bands.
* **Popovers instead of checkboxes.** The seven indicator controls and the eight
  drawing controls moved into Indicators/Draw popovers; the remaining analysis
  panels (candles, patterns, Elliott, harmonic, stats, correlation, drawings,
  relative strength) are inside a collapsed "Advanced analysis" section.
* **Real chart types.** Candles and Line (a line series still drives drawings),
  Fit, zoom in/out, fullscreen (Esc exits), and CSV export.

**Fixed defects (B-65 … B-68)**
* **B-65** RSI/MACD panes never rendered — `$("rsi-pane")` was missing the `#`.
* **B-66** overlays drawn unconditionally; the default chart was a wall of levels.
* **B-67** reloads accumulated charts because `destroyCharts()` ran before the
  `await`; loads are now serialised by a sequence token.
* **B-68** the detected-items list kept a hidden layer's rows.

**Evidence**
* Suite **2199 passed / 0 failed / 0 errors / 0 skipped**; `ruff` clean;
  `node --check` clean; **105 routes all test-referenced**; Go bridge tests pass.
* Browser, dev instance on `127.0.0.1:10000`: 14 views, **0 console errors**.
  Verified by interaction: symbol search, timeframe change, chart type toggle,
  indicators added/removed (RSI and MACD panes render), all six analysis layers
  enabled with real counts, "Hide all" clears results, a Fibonacci-retracement
  drawing placed by two clicks ("Fib retracement added", 1 row in the drawings
  list), fit / zoom / fullscreen.
* `docs/evidence/session27-chart-clean.png`, `session27-chart-sr.png`,
  `session27-chart-layers.png`, `session27-chart-final.png`.
* Production untouched; gate unset; 0 staged/stashed.

---

## 2026-10-16 — session 28: dashboard actually redesigned

**Fixed (root cause):** the Overview view still rendered the old card grid
(`loadOverview()` writing `#totals`, `#gainers`, `#losers`, `#active`,
`#breadth` into generic cards) while the initial `[data-view="overview"]`
handler and `boot()` both called it. The 12 reference cards described a
NEPSE-alpha-style dashboard, so nothing visible changed. The route's HTML was
header-redesigned (new shell) but the *content* was identical.

**Shipped.** `loadMarketOverview()` now renders, from the real release dataset:
- Hero KPI strip (NEPSE 2,634.17 +0.31%, market 199/106, turnover NPR 5.5B, volume 15.7M, status CLOSED, as-of 2026-10-15), live strip (DELAYED, NEPSE 2,625.93, 328 quotes, age 75 min).
- Large official-index chart (`/api/indices/NEPSE`, 120 bars, 2026-04-22 → 2026-10-16) with reflexivity note "stored official series, not a live feed".
- Market breadth + advances/decliners/unchanged/missing (honest denominators) and an MA-participation block (above 20/50/200-d MA, denominator).
- **Sector performance** (14 sectors with adv/dec and avg % change) + **P/E histogram** (231 symbols, real values).
- Gainers, losers, most-active tables (8 rows each), sourced from the free live snapshot.
- `#view-overview` now only runs `loadMarketOverview()`; the old grid (`#totals`, `#regime`, `#dash-index`, `#dash-picker`) is gone from the overview; the customise panels remain but no longer crash the page.

**Evidence:** `docs/evidence/session28-overview.png`; KPI/breadth/sectors/movers/valuation
all non-zero with real data; **2200 tests pass**, 0 console errors across 14
views.

**Still deferred (declared, not faked):** the "large NEPSE index chart" is now
a real official-index chart; sector heatmap, valuation scatter, watchlist, and
scanner widgets are still NOT on this dashboard and remain task-queue items.

---

## 2026-10-16 — session 28: dashboard visibly transformed

**Fixed the actual root cause** — the dashboard content was the old card grid
(`#totals`, `#gainers`... render by `loadOverview()`), not the new one. Rewired
`#view-overview` to render `loadMarketOverview()`: hero KPI strip, a real `NEPSE`
index chart with timeframe selection (120/250/750 obs verified to change the
range), breadth + MA participation, 14-sector table, gainers/losers/active,
P/E histogram (231 symbols).

Proof: 14 views × 0 console errors, 2200 tests pass, screenshot
`docs/evidence/session28-overview.png`.

Remaining: sector heatmap, watchlist, technical scanners, portfolio/backtest
visuals, valuation scatter; index hero done.
