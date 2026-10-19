# MEGA TOOL — FEATURE STATUS
Audit date: 2026-10-14 | Session-18 update below (2026-10-17) | Source: verified evidence

## SESSION 18 UPDATE (2026-10-17) — label declutter, unified history, grouped rail, tool wave 2, Kronos chart + Mini

Chart label declutter: IMPLEMENTED + TESTED-PASS. Pattern overlay is
quality-ranked, capped (1/3/5/8/12 via render controls), and every level/pivot
series is drawn with `title: ""` — the pivot/level identity lives in compact
markers (short code + BO/INV chips) and the Evidence table, so the price axis
no longer floods with full pattern names. Candlestick letters are capped to the
most recent N events (render control; previous letters stay in the
candlestick panel). New Render-controls section in the analysis drawer plus
four display modes (Minimal / Standard / Detailed / Research) preset the caps;
toggling re-renders from cached data without refetch and leaves no stale ink.

Unified undo/redo: IMPLEMENTED + TESTED-PASS. One typed stack
(`{kind:"draw"|kind:"view"}` entries, 100 max) drives toolbar buttons and
keyboard (Cmd/Ctrl+Z undo, Shift+Cmd/Ctrl+Z and Ctrl+Y redo; `preventDefault`
stops browser history navigation; inputs/textarea keep native text undo).
Chart navigation (wheel zoom, pan) is coalesced — each settled gesture commits
one `view` entry; adjacent commits within 2 s merge instead of stacking.
Browser-verified: drawing create/undo/redo, zoom-undo, pan-undo, button
disabled-state sync, stack typing exact after each step. Related fixes
B-69..B-73 (see KNOWN_BUGS.md).

OHLCV crosshair legend: IMPLEMENTED + TESTED-PASS (first
`subscribeCrosshairMove` in the app). Compact strip over the chart-left: SYM,
date, O/H/L/C, Δ and Δ% against the prior stored bar (colour-coded), volume;
falls back to the last bar when the pointer leaves. Values come only from
stored bars.

Grouped drawing rail: IMPLEMENTED + TESTED-PASS. The anonymous icon grid is
replaced by 9 category buttons (Cursor, Lines, Channels, Fibonacci, Measure,
Shapes, Text, Patterns, Positions); each opens a popover beside the rail
listing the group's tools with names + hints, and the rail search filters
across every group at once (Enter activates the first hit). Active category
tracks the active tool.

Second wave of drawing tools: IMPLEMENTED + TESTED-PASS (all verified live on
NIMB with anchor-level assertions): price_range, date_range, price_label, note
(text marker + handle), flag (⚑ marker), fib_timezones (verticals at
1,2,3,5,8,13,21,34,55,89 bars), fib_fan (rays through fib fractions of the leg,
extended to the loaded right edge), fib_channel (3 clicks, base + fib-ratio
parallels), trend-based fib extension (3 clicks, impulse projected from B),
regression_channel (OLS centre of closes + ±kσ bands, k = ratios[0]),
pitchfork (median A→mid(BC) + parallel tines), triangle, polyline
(variable-length, Enter/double-click finishes, Esc cancels), XABCD, ABCD,
three_drives, elliott_impulse (labels 1-5), elliott_abc (labels A-C).
Multi-anchor machinery is generic (`drawMulti` + t1..tN/p1..pN), drag moves any
anchor, whole-drawing move works for N anchors, draw-list table shows all
anchors. Still deliberately absent (audit honesty): fib arcs/spirals, Gann,
ellipse/circle/H&S manual shapes — LWC 4.2.3 has no native shape primitives and
the approximations drift with scale.

Kronos AI on the main chart: IMPLEMENTED + TESTED-PASS. A top-toolbar
"Kronos AI" popover runs real `/api/kronos/forecast` for the chart's own
symbol: model availability read from `/api/kronos/status` (Run disabled with
BLOCKED_MISSING_WEIGHTS when absent, never substituted), context clamped to the
variant's official limit, forecast drawn as amber predicted candles
(distinct from observed candles), hide/show/remove verified, honest status
text including device + inference seconds + "Model output — never an observed
price".

Kronos Mini: IMPLEMENTED + TESTED-PASS — genuinely, no relabelling:
- Official upstream facts (HF model card + /api/models): NeoQuasar/Kronos-mini,
  MIT, 4.1 M params, context 2048, paired with the separate official
  Kronos-Tokenizer-2k (15.8 MB).
- Downloaded both official artifacts into `data/models/` (byte sizes match the
  HF API exactly: 16,440,776 and 15,842,376); ~31 MB on a disk with 10 GB free.
- Backend upgraded: per-variant official tokenizer (mini ↔ Tokenizer-2k,
  small/base ↔ Tokenizer-base), per-variant context limits
  (`VARIANT_MAX_CONTEXT = {mini: 2048, small: 512, base: 512}`) enforced
  server-side in `ForecastRequest.__post_init__`, availability reports
  `variant_max_context` + `variant_tokenizer`, Pydantic schema cap raised to
  2048 hard with per-variant validation inside the service.
- Verified real inference on Apple MPS: NIMB ctx 512 (0.97 s), NABIL ctx 2000
  (0.59 s) — the ">2,000-token context" claim now holds with measured
  evidence; ctx 4000 rejected at the schema. Honest walk-forward: mini vs
  naive-last-close MAE 4.3331 vs 4.33 (wins vs drift20 6.32) on a 2-window
  probe — reported as-is, no cherry-picking.
- UI: chart popover shows "≤ 2,048 context bars · Tokenizer-2k" and clamps to
  the variant limit; AI Forecaster variant note and facts table updated the
  same way.

Cache-buster: `?v=d18` (app.js, kronos_ui.js, styles.css).
Suite: full 2331 passed / 0 failed (`--junitxml`, parsed) after all changes;
`ruff check` + `ruff format --check` clean; node --check clean on both JS
files. Production :8710 untouched.

Still open: elliott auto-count refinement, custom indicator editor/DSL,
templates/favourites, compare expansion, bars-pattern ghost feed, fib
arcs/spirals, intraday timeframes (no permitted source), Kronos-view chart
pane mini-run button (API verified, view reuses the select), scanner launcher
inside the charting view.

## SESSION 17c UPDATE (2026-10-17) — charting workspace mission (parts 2–27 of 48)

Sidebar icons: IMPLEMENTED + TESTED-PASS (18/18 nav buttons, consistent inline
stroke-SVG family, labels preserved, tooltips). Left drawing rail: IMPLEMENTED +
TESTED-PASS (19 tools / 8 groups, searchable, active state, lives inside the
fullscreen stage). New drawing tools: IMPLEMENTED (vline, crossline, hray,
extended line, rectangle, arrow, long/short position with editable R:R) —
position tool TESTED-PASS on NIMB incl. a wrong-sided-stop bug found and fixed
(B-65); hray/extended/short construction verified, dedicated screenshots
pending. Drawing interaction: TESTED-PASS — magnet off/weak/strong (strong
verified numerically: anchor snapped exactly to bar 2026-07-16 high = 193),
eraser mode with lock refusal verified, select mode with whole-drawing body
drag verified, per-drawing lock + lock-all/unlock-all, rename, Escape cancels
pending anchor then tool, stay-in-tool, delete-all confirm, undo/redo across
new tools, per-symbol persistence across reload.

Indicator catalog: IMPLEMENTED + TESTED-PASS (modal driven by
`GET /api/indicators`, 46 formula-documented entries; multi-term search across
name/label/category/formula/reference + category filter; add-to-chart routing
is unit-aware — price-unit outputs overlay, ratio/percent outputs
(percent_b/bandwidth) get their own synced pane because plotting them on price
wrecked the scale, bug B-66 fixed this session; per-symbol persistence across
reload verified; Remove verified; honest chips on every custom pane).
Related fixes: B-67 (saved indicators not restored on fresh load), B-68
(hidden-view chart scale, legacy no-op re-fit replaced with real fitContent).
Full details + explicit gap list: `docs/CHARTING_ACCEPTANCE_AUDIT.md`.
Still open from the charting mission: pitchforks/Gann/fib-fans-arcs, manual
Elliott + harmonic pattern tools, bars-pattern/ghost feed, custom indicator
editor/DSL, templates/favorites, compare expansion, intraday timeframes
(no permitted data), Kronos Mini (weights absent — availability reported honestly).

## SESSION 24 UPDATE (2026-10-17)

Relative Strength: IMPLEMENTED + TESTED-PASS (composite-index consumer was
already repaired before this session; **multi-timeframe table added** —
`lookbacks` param, per-lookback stock/index/excess with honest
unavailability, UI table matched API exactly on NIMB; sector-relative still
unavailable because no permitted sector-index source exists).
Volume Profile: IMPLEMENTED + TESTED-PASS (`ta/profile.py`, endpoint, chart
layer; overlap-proportional allocation, POC/70% VA/HVN/LVN; VA-pointer bug
caught by test before release; browser-verified on NIMB).
Trailing Stops: IMPLEMENTED + TESTED-PASS (`ta/trailing.py`, endpoint,
advanced-analysis card; causal ratchet chandelier/swing/pct, long side only).
Gaps & False Breakouts: IMPLEMENTED + TESTED-PASS (`ta/gaps.py`, two
endpoints; factual gaps + rule-based class labels with basis; breakouts
true/false/unconfirmed). Route inventory: 117 routes, all test-referenced.
Full suite: 2316 passed / 0 failed. Official NEPSE API remains BLOCKED
(401 token, not bypassed); no new permitted market-data source was found
beyond the already-integrated sets.

## FEATURE MATRIX (EVIDENCE-BASED)
Market Dashboard: IMPLEMENTED + PARTIAL (no index B-10)
Advanced Charting: PARTIAL (daily/weekly/monthly verified; SMA/EMA complete; Fibonacci/S/R/candlestick plots real but full overlay partial; browser NOT)
Scanner: IMPLEMENTED + TESTED-PASS (2/2 data-quality filter; 19 metrics)
AI Research: IMPLEMENTED + TESTED-PASS (deterministic rules, not LLM; 28+6 tests)
Floor-Sheet: PARTIAL (mechanism complete; synthetic only)
Fundamentals: PARTIAL (mechanism complete; 0 records)
News/Events: NOT IMPLEMENTED (blocked — no source)
Forecasting: IMPLEMENTED + TESTED-PASS (6 models; honest failure vs baseline)
Backtesting: IMPLEMENTED + TESTED-PASS (next-bar-open; B-11 fee placeholder documented)
Walk-Forward: IMPLEMENTED + TESTED-PASS (B-22 timeout documented; no method passed)
Portfolio: IMPLEMENTED + TESTED-PASS
Journal: IMPLEMENTED + TESTED-PASS
PDF Intelligence: PARTIAL (0/52 fully transcribed)
Multi-Timeframe: IMPLEMENTED + TESTED-PASS (weekly/monthly verified)
Data Quality: IMPLEMENTED + TESTED-PASS (B-21 preserved; 18/18)
Elliott Wave: PARTIAL (bounded only; full blocked by design)
Harmonic Patterns: NOT IMPLEMENTED
Classical Chart Patterns: PARTIAL (candlestick 15 patterns; head/shoulders etc missing)

## KEY FINDINGS
- 5 focused tests pass (multitimeframe 2/2, overlay 1/1, scanner 2/2)
- Full suite ~1124/0 observed (not freshly rerun this turn)
- Server running 200 OK (daily/weekly/monthly)
- No fabricated sectors, fees, fundamentals, floor-sheet
- All protected preserved
- Next: verify /monthly with real server OR complete chart overlay

---

## UPDATE — 2026-10-15 (Phase 2–6 autonomous run, session-15)

Superseding rows above where new evidence exists. Status labels are the
directive's: IMPLEMENTED / TESTED-PASS / TESTED-FAIL / PARTIAL / NOT STARTED / BLOCKED.

| Feature | Status | Evidence |
|---|---|---|
| Classical Chart Patterns | **TESTED-PASS** | New `megatool/ta/patterns.py` (double/triple top-bottom, H&S + inverse, ascending/descending/symmetrical triangles, rising/falling wedges, bull/bear flags, channel breakout) + `GET /api/bars/{symbol}/patterns` + charts-view panel. `tests/test_chart_patterns.py` 14 + `tests/test_patterns_stats_api.py` 9. Closes the "head/shoulders missing" gap. |
| Advanced Statistical Analysis | **TESTED-PASS** | New `megatool/stats.py` (descriptive, return/risk stats, Pearson/Spearman with exact Student-t p-values, OLS, rolling correlation, autocorrelation, variance ratio, correlation matrix) + `GET /api/bars/{symbol}/statistics` + `GET /api/stats/correlation` + charts-view panels. `tests/test_stats.py` 18 + API tests. numpy-only (no undeclared scipy). |
| Scanner | **TESTED-PASS** | Presets expanded 4 → 23 (RSI overbought/oversold, MACD crosses, SMA20/50/200, SMA5-vs-20, Bollinger lower/upper/squeeze, Stochastic, MFI, Donchian breakout, breakout+volume, 52w high/low, momentum, ADX trend, low-vol, liquidity). New single-symbol metrics: macd family, macd_cross, sma_cross, bollinger %B/bandwidth, stochastic K/D, mfi, adx, donchian position/breakout, turnover_sma_ratio. `tests/test_scanner.py` extended. |
| Advanced Charting | **TESTED-PASS** | Backend overlays verified via endpoint tests **and** one browser QA pass (charts view, patterns/statistics/correlation panels, 0 console errors). A full click-through of every view and XSS fuzzing remain NOT PERFORMED. |
| Harmonic Patterns | **IMPLEMENTED** | `megatool/ta/harmonic.py` + `GET /api/bars/{symbol}/harmonic` exist with tests (`tests/test_harmonic.py`); the row above ("NOT IMPLEMENTED") is stale for the current HEAD. |
| News/Events | **IMPLEMENTED + SOURCE BLOCKED** | Local import/validate/dedup/summarise layer + `/api/news/*`; no machine-readable upstream source (L4/T-15). See `docs/MASTER_REQUIREMENTS_REGISTER.md`. |

Kept from above (unchanged, still accurate): forecasting, backtesting,
walk-forward, portfolio, journal, multi-timeframe, data quality, Elliott
(bounded), PDF intelligence (partial).

Full suite this session: **1999 passed, 0 failed, 0 errors, 0 skipped** (junitxml,
32.0 s). `ruff check .` clean; `ruff format --check .` 203 files; `node --check
web/static/app.js` clean. Route inventory: 75 routes, all test-referenced.
Indicator catalogue: **46** registered (was 28). Defects found and fixed this
run: **B-45** (KAMA volatility), **B-46** (frontend percent scaling).

## Session 19 (2026-10-17) — chart polish, Kronos, replay, autosave
Cache-buster bumped to `?v=d19`. Frontend-only changes (app.js, index.html,
styles.css, kronos_ui.js); backend untouched.
- Drawing rail popover: two-line left-aligned items (name + description), 332 px,
  open animation, thin scrollbar, head count (§4). B-75.
- Hide-all-drawings toolbar button + per-drawing hide fix (B-76).
- OHLCV legend: timeframe label, per-bar change, update guard (B-74).
- Kronos chart control: stale guard (kronosSeq), symbol guard, daily-only tf
  enforcement, loading feedback, amber-outlined bullish/bearish forecast candles,
  #kf-chip "PREDICTED" badge, Forecaster→chart sharing (B-77, B-78).
- Chart styles: Candles / Bars (OHLC) / Line / Area (§8 C).
- Indicator favourites (★) + templates (save/apply/delete) (§8 E, B-80).
- Replay mode + autosave switch (§8 J/K, B-81).
- Fullscreen targets #view-charts so the toolbar stays reachable; Esc exits (B-79).
- New drawing tools: Schiff pitchfork, Gann fan (leg-relative, documented) (B-83).
- Math seam: olsFitXY + fibLevel exposed via window.__mtMath with fixtures (§10).
- New doc: docs/CHARTING_FEATURE_MATRIX.md (28 groups).
- 0 console/page errors in the browser sweep; backend suite run as regression.
