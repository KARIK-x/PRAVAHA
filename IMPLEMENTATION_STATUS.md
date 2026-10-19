# Implementation status — charting / TA / indicator / research workbench

Session: **2026-10-18** (workbench **session 30**, a comprehensive audit + indicator
validation + advanced-analysis upgrade on top of sessions 17c–29). Session 30:
audited all 92 indicators (62 now numerically reference-tested, up from 49), filled
metadata gaps (5 references, 11 notes, 36 param descriptions), implemented 5
genuinely new advanced capabilities (rolling beta, volatility percentile, MTF
confluence, technical rating, S/R strength scoring), added 25 + 16 tests, and
re-verified Fibonacci viewport + search + info buttons. See §2 rows 39–43 and
`TEST_RESULTS.md` §30.
Baseline: git `main`, **all work uncommitted** — no commits, no pushes (no
authorization), production uvicorn never signalled, production DB untouched. Dev
work served from `data/dev/release` on `127.0.0.1:10000`; production stays on
`8710`.

Labels used below, exactly: **IMPLEMENTED** · **TESTED-PASS** · **TESTED-FAIL** ·
**NOT-TESTED** · **BLOCKED** · **APPROXIMATION** · **DATA-DEPENDENT** ·
**NOT IMPLEMENTED (backlog)**. No feature is claimed implemented or tested
without the named command / evidence file.

## 1. Test headline (session 30)

* **Full suite: 2,701 passed / 0 failed / 0 errors / 8 skipped — exit 0**
  (re-run at the end of session 30). Log `$TMPDIR/full_s30.log` (2,701 `.` + 8
  `s`, 0 `F`/`E`, [100%]). The 8 skips are the opt-in browser module.
* **New tests this session:** `tests/test_indicators3.py` (25 numeric reference
  tests) + `tests/test_advanced_analysis.py` (16 tests for the 5 new capabilities).
  Opt-in browser module: 8 passed / exit 0 (unchanged).
* **Indicator verification map:** 62 reference / 28 invariants / 2 sparse / 0 none
  (was 49/41/2). `generate_indicator_info.py` regenerated → 92 entries, 0 empty
  references, 0 empty notes, 0 empty formulas.
* **Metadata:** 5 references + 11 notes + 36 parameter descriptions filled.
* **Info buttons:** 92/92 present (browser). Search "money flow" → CMF + MFI.
* **Fibonacci viewport re-verified:** `{75,175}` → `{75,175}`, 0 console errors.
* **5 new advanced capabilities:** rolling beta, volatility percentile, MTF
  confluence, technical rating, S/R strength scoring — all tested.
* **Cache-buster** `app.js?v=wb23`; `node --check web/static/app.js` → exit 0.
* Session 29 headline (previous): 2,660 passed / 0 failed / 0 errors / 8 skipped.
  Session 28: 2,660 passed. Session 27: 2,599 passed.
* **New browser regression module** `tests/test_browser_objects_manager.py`
  (8 cases) — **8 passed, exit 0** with `MEGATOOL_BROWSER_TESTS=1` against the
  live dev server (`/tmp/browser_tests.log`); **skipped (8)** in the default run.
* **Fibonacci viewport measured** in the browser (the session-28 gap): manual
  `fib_retracement`/`fib_extension` and automatic `fib` each preserved the visible
  logical range byte-for-byte — `{75,175}` normal mode, `{87,187}` expanded mode —
  with existing drawings/indicators intact and **0 console errors / 0 warnings**.
* Cache-buster `app.js?v=wb23`; `node --check web/static/app.js` → exit 0 after
  every edit.
* Session-28 headline (previous): 2,660 passed / 0 failed / 0 errors / 0 skipped —
  exit 0. Session 27: 2,599 passed. Command for all:
  `MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings`
  (this pytest build suppresses the terminal summary line; counts are the
  progress-mark totals over the captured logs and the process exit code is 0).
* No backend code changed this session, so the passed total is unchanged from
  session 28; the added coverage is the 8 browser cases (opt-in). Lint is
  unchanged too — no Python file was edited this session, so the session-28
  `ruff` status (including the known `megatool/api.py` formatter exception) holds.
* Session 27 (context): focused suite `tests/test_index_ohlc_history.py` **15
  passed / exit 0** (extended with assertions for the two new API fields
  `genuine_first_date` / `genuine_last_date`); `node --check web/static/app.js`
  → exit 0 after every frontend edit; browser (real trusted events) on NABIL
  (250 bars) and NEPSE (750 bars) — 36 interaction cases, all PASS, **0 console
  errors / 0 warnings**; build served as `app.js?v=wb12` (session 29: `wb23`);
  full matrix in `TEST_RESULTS.md` §"Session 27".
* `ruff check` on every file this session created or edited: **pass**
  (`megatool/breadth.py`, `megatool/seasonality.py`, `megatool/swing_workbench.py`,
  `megatool/scanner.py`, `megatool/market_store.py`, `megatool/api.py` edits,
  `tests/test_breadth.py`, `tests/test_seasonality.py`, `tests/test_swing_workbench.py`,
  `tests/test_scanner.py`, `tests/test_api.py`).
* `ruff format --check` clean on every file this session authored. Four files were
  reformatted this session after the check caught them; two single-hunk fixes
  (mine) were applied to `scanner.py` / `tests/test_scanner.py`. **Known exception:**
  `megatool/api.py` still fails repo-level `ruff format --check` on **21 hunks in
  lines ~781–1480 (+ 2379–2672, 3920, 5068)** — all inside earlier sessions'
  uncommitted route regions (Kronos middleware, gonepse, market-intelligence,
  fundamentals), none inside this session's added route blocks (~900–1010,
  ~1665–1710). Deliberately left untouched (another session's in-flight work);
  recorded in `REMAINING_BLOCKERS.md` §10.
* `node --check web/static/app.js` → exit 0 after every edit.
* Browser: **0 console errors / 0 warnings** at the end of the verified flows
  (`playwright-cli console error` → `Total messages: 0`).

## 2. Feature status

| # | Feature | Status | Evidence |
|---|---|---|---|
| 1 | Chart types: candles, bars (OHLC), hollow, line, line+markers, step, area, baseline, column, Heikin Ashi | **IMPLEMENTED + TESTED-PASS** | Browser-verified: hover/draw on real NABIL bars; Heikin meta label present; 0 console errors. Heikin is a documented display transform (raw OHLCV untouched) |
| 2 | Non-time-based types (Renko, Kagi, P&F, Range, Line-break) | **NOT IMPLEMENTED (backlog)** | Need a non-time-based bar pipeline; documented, not faked (see `REMAINING_BLOCKERS.md` §2) |
| 3 | Index symbols: chart types **gated by data, not by instrument** | **IMPLEMENTED + TESTED-PASS** | The NEPSE index stores **2,217 genuine OHLC rows (2016-11-28 → 2026-10-15)** and 3,079 close-only placeholders + 54 source-flagged `invalid` rows. Candles/hollow/bars/Heikin are therefore **enabled** for the index and render genuine bars; placeholder *and* `invalid` rows render as **whitespace gaps** (never a fabricated `O=H=L=C` body); Heikin chains only across genuine rows. A genuinely close-only series disables them with the reason in the option tooltip. Browser: NEPSE `#range=750` → 750/750 genuine candles, meta `index · 2217 OHLC / 3079 close-only · candles from 2016-11-28`, 20 in-window `invalid` rows shown as gaps. `genuine_first_date`/`genuine_last_date` added to `/api/indices/{name}/ohlc` (**TESTED-PASS**, `tests/test_index_ohlc_history.py`). Screenshot `docs/evidence/workbench-2026-10-18-index-candles.png` |
| 4 | Indicator registry: 46 → **92 indicators** (46 new across `ta/trend2.py`, `momentum2.py`, `volatility2.py`, `volume2.py` in earlier sessions, + **11 in `ta/extra.py`** this session: `vortex`, `ma_cross`, `chande_kroll_stop`, `bollinger_width`, `percent_b`, `chaikin_volatility`, `relative_volatility_index`, `average_price`, `price_correlation`, `williams_fractal`, `zigzag`) | **IMPLEMENTED + TESTED-PASS** | `tests/test_indicators.py` (invariants over all 92) + `tests/test_indicators2.py` (36 literal reference-value tests) + 9 new numeric reference tests for the batch-1 additions + dedicated sparse-pivot tests for `zigzag`/`williams_fractal`. Verification map (generated, `scripts/generate_indicator_info.py`): **49 reference / 41 invariants / 2 sparse / 0 none** |
| 5 | Chart-side indicator drawer: search, categories, favourites, recents, templates, per-symbol layouts, undo/redo, multi-instance with unique ids (duplicates allowed) | **IMPLEMENTED + TESTED-PASS** | Browser: add/params/persist/reload flows; screenshots `docs/evidence/workbench-2026-10-18-new-indicators.png`, `-compare.png` |
| 6 | Output placement engine (overlay vs pane) + multi-output drawing | **IMPLEMENTED + TESTED-PASS** | Browser-verified matrix **33 overlay / 59 pane** (re-verified after the 81 → 92 expansion); GMMA = 12 overlay series / 0 panes; alligator = 3/0; SMI = 2 series in 1 pane; MACD = 3 series in 1 pane; hidden instance's pane stays hidden across reload |
| 7 | Compare drawer: primary + up to 3 comparison symbols; modes **% change from window start / indexed to 100 / relative to NEPSE (ratio×100) / rolling return % / raw (shared left scale)** | **IMPLEMENTED + TESTED-PASS** | Browser: multi-symbol draw, legend values, persistence, missing dates = gaps (never interpolated); raw mode uses left scale + explicit note; screenshot `-compare.png` |
| 8 | Layout export/import (JSON v1: quick layers + instances + compare + chart type) | **IMPLEMENTED + TESTED-PASS** | Browser round-trip: crafted layout imported → `ema(33)` overlay + hidden `rsi(9)` pane + compare `NICA` percent all restored; pane visibility correct |
| 9 | Templates capturing indicator instances (with back-compat for flag-only templates) | **IMPLEMENTED + TESTED-PASS** | Browser: template applied → `sma(7)` overlay (1 series / 0 panes) + `macd(12,26,9)` (3 series / 1 pane), labels/params restored |
| 10 | Breadth history (advances/declines/unchanged, % above SMA-N, A/D line, A/D volume line, new highs/lows, net) | **IMPLEMENTED + TESTED-PASS + DATA-DEPENDENT** | `megatool/breadth.py`; `tests/test_breadth.py` (8); API tests; browser on real store: 5,200 sessions 1995-07-20 → 2026-10-15, universe 326, 40.1 % / 35.3 % / 24.4 % above SMA 20/50/200; screenshot `-breadth.png` |
| 11 | Seasonality (month-of-year, weekday; holiday study honest-unavailable) | **IMPLEMENTED + TESTED-PASS + DATA-DEPENDENT** | `megatool/seasonality.py`; `tests/test_seasonality.py` (9) + 4 API tests; browser: NABIL January N=15, mean −3.46 %, hit rate 40 %; holiday section reports the real reason (bundled calendar has no holidays) |
| 12 | Swing Bench (structure, nearest confirmed levels, measured-move arithmetic, readings checklist, position sizing) | **IMPLEMENTED + TESTED-PASS + DATA-DEPENDENT** | `megatool/swing_workbench.py`; `tests/test_swing_workbench.py` (7) + 2 API tests; browser: NABIL trend `mixed` → framing `none` → no fabricated invalidation/target; support 530.00 (confirmed 2026-09-07), resistance 550.00; screenshot `-swing.png` |
| 13 | Volume Scanner (Part 15): 7 new metrics (`volume_ratio_50`, `volume_vs_20d_max`, `volume_climax_5_20`, `updown_volume_ratio`, `obv_pressure_20`, `range_compression_20`, `pocket_pivot`) → 41 metrics; 8 new presets → 31 | **IMPLEMENTED + TESTED-PASS + DATA-DEPENDENT** | `tests/test_scanner.py` (catalogue set + reference maths, incl. pocket-pivot alignment); API preset runs on the real store: volume_dryup 130 scanned/108 passed, pocket_pivot 71/49, accumulation_20d 133/111; all 8 preset names verified present in the screener UI |
| 14 | Candlestick patterns (Part 14) | **PARTIAL: 18 named patterns implemented + TESTED** | `megatool/ta/candles.py` (`PATTERN_NAMES`, 18 rules); earlier-session candle-API tests remain green. The checklist names 33; the other names are not in the repository snapshot → backlog (`REMAINING_BLOCKERS.md` §4) |
| 15 | Unified S/R + chart-pattern engine (Part 18) | **PARTIAL (existing pieces, no new consolidation this session)** | Swings/structure/breaks, levels, fibonacci, harmonic, elliott, patterns, gaps, profile modules exist from earlier sessions; the swing bench consumes the swing primitives; a single unified engine API was **not** built — no claim made |
| 16 | Pine-like safe subset + Alpha Coder (Parts 19–20) | **DSL: IMPLEMENTED (existing, B-84) · Alpha Coder: NOT IMPLEMENTED (backlog)** | Custom-formula DSL: whitelisted recursive-descent parser + AST evaluator, no `eval`, unknown identifiers rejected at parse time; save/reload/auto-apply verified in an earlier session. No natural-language “Alpha Coder” assistant exists |
| 17 | Backtesting without look-ahead (Part 21) | **Existing engine retained; NOT re-verified this session** | Prior sessions' engine + look-ahead guard (B-04) untouched by this session's changes |
| 18 | HTML integrity of the chart view | **FIXED** | 3 parse-level defects (duplicate `chart-meta` id, malformed `</h2>`, missing `</nav>`, stray `</footer>`) fixed earlier this session → HTML parses with 0 errors |
| 19 | **Global command palette** (`⌕ Search` toolbar button / **Cmd/Ctrl+K**): search over 30+ views, 10 chart types, 39 drawing tools, 7 analysis layers, all 92 indicators, screener presets, 12 actions | **IMPLEMENTED + TESTED-PASS** | Browser: **257 palette items**; 80 results for `trend`, grouped; `rsi` / `horizontal line` / `elliot` / `seasonality` / `support` / `clear` / `candle` all resolve; an action was run end-to-end (Relative Strength Index → instance added, pane created, status "rsi added to the chart."). **Coverage check: all 43 owner-named surfaces have an entry, 0 missing** (25 live, 18 disabled); each of the 20 disabled entries carries a specific reason in its hint (e.g. "Multi Chart — this build draws one chart per view", "Shareholder Watchlist — no shareholding-register source in this build"). `TEST_RESULTS.md` §27 #27–30. Screenshot `-palette.png` |
| 20 | **Clear button + scoped confirmation dialog** (next to Chart settings) | **IMPLEMENTED + TESTED-PASS** | Browser: dialog shows 3 live counts (drawings/indicators/analysis); drawings-only confirm → drawings 0 while indicators 3 and layers `{sr:true}` untouched; modal closes; status says the clear is undoable; Cmd/Ctrl+Z restored the drawing. Layouts/templates/watchlists are structurally out of scope. Screenshot `-clear-dialog.png` |
| 21 | **Pane headers**: drag-resize, collapse/expand, taller/shorter, ✕ remove (undoable); height + collapsed state persist per indicator instance | **IMPLEMENTED + TESTED-PASS** | Browser: collapse → pane `hidden`, expand → visible; taller ×2 → 120→240px persisted as `paneHeight:240`; ✕ removed the RSI pane+header and the drawer's Undo restored all instances and 2 headers. Screenshot `-pane-headers.png` |
| 22 | **Drawing engine repairs** (body hit-testing, capture-phase drag, logical-coordinate mapping, selection handles, Delete/Backspace, typing guard, no undo pollution) | **IMPLEMENTED + TESTED-PASS** | Browser on NABIL: draw trendline (2 real clicks) → select (2 handles) → drag (anchors moved, chart range 0→249 unchanged) → eraser on the line body (deleted) → Cmd+Z → Delete → Cmd+Z → Shift+Cmd+Z; Delete with `#symbol-input` focused is a no-op. `KNOWN_BUGS.md` B-92…B-96; `TEST_RESULTS.md` §27 #11–23. Screenshot `-drawings.png` |
| 23 | **Viewport preservation** across same-symbol reloads and tab switches (no auto `fitContent`) | **IMPLEMENTED + TESTED-PASS** | Browser: zoom `{81.8,167.2}` → toggle S/R layer (10 lines of 73 zones drawn, forces a `loadChart`) → range byte-identical; Fit remains an explicit button. `KNOWN_BUGS.md` B-99; `TEST_RESULTS.md` §27 #9–10 |
| 24 | Index console hygiene (no 404s for endpoints that only serve securities) | **IMPLEMENTED + TESTED-PASS** | Browser: console **0 errors / 0 warnings** after NEPSE then NABIL; the index answers "n/a for the index" and the patterns panel renders an explanatory empty state. `KNOWN_BUGS.md` B-97 |
| 25 | Indicator discoverability (the "UI shows ~10–15" concern) | **TESTED-PASS — not a defect** | Browser: the catalog modal reports **"92 of 92 registered"** (93 rows incl. header) with search + category filters (all/favs/trend/momentum/volatility/volume/other); the drawer and the palette expose the same set. The ~10–15 figure came from the quick-layer checkboxes (a small fixed subset), not the indicator set. Re-verified after the 81 → 92 expansion. Screenshot `-catalog.png` |
| 26 | **11 new indicators** (`ta/extra.py`) with per-indicator info metadata (name, abbreviation, formula, variable notes, limitations, reference) and independent numeric reference tests | **IMPLEMENTED + TESTED-PASS** | `.venv/bin/python -m pytest tests/test_indicators.py tests/test_indicators2.py -q` (exit 0); each has an explicit test comparing the implementation against an independently written formula. `zigzag`/`williams_fractal` are sparse-pivot indicators covered by dedicated property tests (declared in `SPARSE_PIVOT_INDICATORS`), not silently excluded. Info panel verified live for `percent_b` (name/abbr/formula/variables/limitations/verification/Add; 2,202 chars) |
| 27 | **Market ribbon** (`GET /api/market/ribbon`) — most-active gainers/losers/turnover/volume + index + 52-week extremes, horizontally scrolling, clickable, pause/resume, freshness badge | **IMPLEMENTED + TESTED-PASS + DATA-DEPENDENT** | `tests/test_api.py` (8 ribbon tests: shape/honesty, breadth sums, dedupe, `top` validation 422, empty store, gainer vs loser ordering, no-invented-index, index-when-stored). Browser: 70 items, 5 category groups + 1 honest `unavailable` group, badge "NEPSE 2026-10-15 · delayed", pause toggles `paused`/`running` and persists in `localStorage['mt-ribbon-paused']`; clicking GBIME opened it in the chart. Screenshot `docs/evidence/wb15-ribbon.png` |
| 28 | **Unified chart-object manager** (`Objects` toolbar button → `#obj-pane`) — lists every visible object with owner, visibility and remove; draggable/resizable | **IMPLEMENTED + TESTED-PASS** | Browser on NABIL: **6 owner groups, 159→164 rows**; a pattern marker row reads the full provenance ("BO 563" = breakout/trigger level of the double_bottom (bullish)). Hide/Remove verified on one marker (9→8) with the object really gone from the chart. Marker provenance is stored in a side table (`state.markerMeta`, keyed `time\|position\|shape\|text`) so LWC renderer payloads are untouched. Screenshot `docs/evidence/wb16-objects.png` |
| 29 | **Elliott Wave made visible** — "Analyze & draw on chart" / "Remove chart drawing" with a status line; candidate-only labelling | **IMPLEMENTED + TESTED-PASS** | Browser: 5 wave labels + connecting line drawn; status "Elliott: drew candidate “Candidate Impulse (5-wave)” (5 pivots, low)… Viewport unchanged."; labelled `CANDIDATE_ONLY`; viewport `{3.89,249}` unchanged before/after; erase restores manual labels. Screenshot `docs/evidence/wb17-elliott-drawn.png` |
| 30 | **Active-tool banner** — states which drawing/Elliott tool is active and how many anchors are placed | **IMPLEMENTED + TESTED-PASS** | Browser: "Elliott impulse · 0/5 anchors → 2/5 anchors"; the banner hides when the tool is deactivated (`updateToolBanner`/`drawAnchorNeed`/`drawAnchorPlaced`) |
| 31 | **Viewport preserved when adding an indicator (root-cause fix)** | **IMPLEMENTED + TESTED-PASS** | The pane↔price time-scale sync is now **one-directional** (price → pane; the old bidirectional subscription re-framed the chart) plus an explicit `getVisibleLogicalRange()` capture/restore around every add. Browser: `{80,200}` preserved byte-for-byte for both an overlay add (`ma_cross`) and a pane add (`percent_b`); a pane still follows a price pan (`{120.98,230}`). No `fitContent` on add. Screenshot `docs/evidence/wb21-viewport-preserved.png` |
| 32 | **S/R + Fibonacci axis-label crowding** | **IMPLEMENTED + TESTED-PASS** | Caps `MAX_OVERLAY_LINES=8`, `MAX_OVERLAY_LABELS=4`, `OVERLAY_LABEL_MIN_GAP=0.012` so nearby levels cannot overlap on the price axis; browser shows `resistance @ 554 [550-556]`, `zone @ 562` separated |
| 33 | **Generator honesty fix** — verification level can no longer be silently promoted to `reference` by the mere presence of an adjacent helper | **IMPLEMENTED + TESTED-PASS** | `scripts/generate_indicator_info.py` gained an explicit `INVARIANT_TESTS` set; `verification_map()` parses `SPARSE_PIVOT_INDICATORS` so sparse exclusions are declared, never silent. Regenerated `web/static/indicator_info.js` → 92 entries, **49 reference / 41 invariants / 2 sparse / 0 none** |
| 34 | **Quick-layer objects in the Objects manager** — the chart-toolbar toggles (`SMA 20/50`, `EMA 20`, `Bollinger`, `Volume`, `RSI pane`, `MACD pane`, `Swings`, `Close-based pivots`) are now first-class objects | **IMPLEMENTED + TESTED-PASS** | `loadChart` registers one `state.quickObjects` descriptor per toggle; manager gained a **Quick layers** group (label/type/owner/visibility + Hide/Show + Remove). Hide flips the real series/pane visibility; Remove unchecks the toggle, removes the real primitive (`removeSeries`/pane `chart.remove()` + element cleared) and drops its row. Browser-verified incl. DOM Hide/Show/Remove. Screenshot `docs/evidence/wb24-objects-quick.png`; `TEST_RESULTS.md` §29 cases 1–5 |
| 35 | **Remove clears owned annotations** | **IMPLEMENTED + TESTED-PASS** | Removing `quick-swings` dropped all **27** markers it owned from `state.markers` and unchecked `#ind-swings` — no orphaned markers. `TEST_RESULTS.md` §29 case 6 |
| 36 | **Detector-marker lifecycle** — pattern markers no longer lost on reload; candle markers and the pattern overlay no longer leak across symbols; no duplicate objects over repeated reloads | **IMPLEMENTED + TESTED-PASS** | `applyChartLayers` fetches (`loadPatternPanel`) instead of re-rendering a panel that needs an in-memory scan (9 → reload → 9); `destroyCharts` resets `state.candleMarkers`/`state.quickObjects` (NABIL 122 → ADBL 0); `#pattern-overlay` synced to the symbol's layer flag (NABIL 9 → ADBL 0); 3 full reloads → byte-identical object counts. `KNOWN_BUGS.md` B-108…B-111; `TEST_RESULTS.md` §29 cases 7–12 |
| 37 | **Fibonacci viewport measured** (the session-28 gap) — manual and automatic, normal and expanded chart mode | **IMPLEMENTED + TESTED-PASS (browser-measured)** | Manual `fib_retracement`/`fib_extension` and automatic `fib` each preserved the visible logical range byte-for-byte: `{75,175}` normal, `{87,187}` expanded; existing drawings + a freshly added catalog indicator intact; no `fitContent`/reset/remount/auto-zoom. `TEST_RESULTS.md` §29 cases 13–17 |
| 39 | **Indicator numeric validation extended** — 25 new reference tests for the 16 indicators that previously had only structural coverage | **IMPLEMENTED + TESTED-PASS** | `tests/test_indicators3.py` (24 → 25 after aroon warm-up correction). Verification map 49 → 62 reference / 41 → 28 invariants. `scripts/generate_indicator_info.py` promotion rule fixed so numeric tests promote correctly |
| 40 | **Metadata completeness** — 5 empty references, 11 empty notes, 36 missing param descriptions filled | **IMPLEMENTED + TESTED-PASS** | `megatool/ta/other.py`, `trend.py`, `momentum.py`, `volatility.py`, `volume.py`; `scripts/generate_indicator_info.py` VARIABLES extended. Regenerated `indicator_info.js`: 92 entries, 0 empty references/notes/formulas |
| 41 | **5 new advanced-analysis capabilities** | **IMPLEMENTED + TESTED-PASS** | `megatool/stats.py` (`rolling_beta`, `volatility_percentile`), `megatool/ta/multitimeframe.py` (`mtf_confluence`), `megatool/ta/confluence.py` (new: `technical_rating`, `classify`), `megatool/ta/levels.py` (`strength` on `Zone`). `tests/test_advanced_analysis.py` 16 tests, all pass |
| 42 | **Search and info-button audit** | **TESTED-PASS** | Browser: 92/92 ⓘ buttons present; "money flow" → CMF + MFI; empty/no-result states render explanations |
| 43 | **Fibonacci viewport re-verified** | **TESTED-PASS** | `{75,175}` → `{75,175}`, 0 console errors |

## 3. Honesty constraints held

* Missing evidence is always `None` + a reason — breadth (`available_*` counts),
  seasonality (holiday `available:false` + reason), swing bench
  (`*_missing_reason`, checklist `pass:null` + `missing_reason`), scanner
  (three-valued logic, unknown metric ⇒ ineligible with reason).
* All stored prices are **unadjusted for corporate actions**; the swing payload
  warns that a structural break may be a bonus/split artifact.
* Compare modes never invent points: missing dates are gaps; rebase uses each
  symbol's first **visible** observation, stated in the UI.
* Index OHLC before the OHLC era is close-only and labelled in the meta line;
  placeholder rows and rows the source flagged `invalid` are drawn as **gaps**,
  never as fabricated or internally inconsistent candles, and the candle region's
  start date (`candles from 2016-11-28`) comes from the API, not from the window.
* The palette never returns a control that does nothing: features that do not
  exist are listed disabled with the reason, and the Clear dialog says exactly
  which scopes it will touch (and which it will not).

## 4. Exact commands

```bash
# full regression (this session's authoritative run)
MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings

# focused suites added/extended this session
.venv/bin/python -m pytest tests/test_indicators.py tests/test_indicators2.py -q
.venv/bin/python -m pytest tests/test_breadth.py tests/test_seasonality.py tests/test_swing_workbench.py -q
.venv/bin/python -m pytest tests/test_scanner.py tests/test_api.py -q

# opt-in browser regression module (needs the dev server on :10000 + playwright-cli;
# skipped in the default offline suite)
MEGATOOL_BROWSER_TESTS=1 .venv/bin/python -m pytest -q tests/test_browser_objects_manager.py

# dev server (production 8710 untouched)
MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m megatool.cli serve --host 127.0.0.1 --port 10000

# catalogue + audit are reproducible from the registry (browser-verified 33 overlay / 59 pane)
.venv/bin/python scripts/generate_indicator_reports.py   # writes INDICATOR_CATALOGUE.md + INDICATOR_SOURCE_AND_LICENSE_AUDIT.md (run from repo root)
.venv/bin/python scripts/generate_indicator_info.py      # writes web/static/indicator_info.js (92 entries + verification map)
```

## 5. Next action

Nothing in session 29's work is left in a broken state. The objects-manager and
detector-marker defects found by the session-28 read-only pass are fixed and
verified; the Fibonacci viewport is now measured. The remaining items are either
owner-gated or genuinely absent. Ordered backlog:

0. **New, honest gaps from session 29** (see `REMAINING_BLOCKERS.md` §23–§24):
   quick-layer toggles stay unpersisted (so swing-marker quick layers cannot
   reconstruct after a reload — the persistent analysis layers do), per-marker
   suppression stays session-only, and the browser regression module is opt-in.
1. **Owner-gated:** Kronos NABIL GPU fine-tune launch (awaiting explicit
   approval), independent source verification (only the community
   `nepse-data` source, no LICENSE), `python-dotenv` CVE upgrade, and commit /
   push authorization (~270 uncommitted files, HEAD `b6c3659`).
2. **Genuinely absent, do not fake** (see `CHART_UX_AUDIT.md` "Still open"):
   canvas context menu, multi-symbol grid + pane drag-out, multi-timeframe
   overlays / MTF scan, opt-in auto trendline detection, named workspace that
   saves pane layout as a whole, non-time-based chart types (Renko/Kagi/P&F).
3. **Part 14:** the 15 named candlestick patterns not present in this snapshot.
4. **Part 18:** a single unified S/R + pattern engine API (today the pieces
   exist but are not consolidated).
5. **Pre-existing drift:** `megatool/api.py` `ruff format --check` (21 hunks in
   earlier-session route regions, deliberately untouched) and 18 `ruff check`
   findings there.
