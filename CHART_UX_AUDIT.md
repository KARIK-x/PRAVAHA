# Chart UX audit — 2026-10-18 workbench session

Scope: the charting surface (`#view-charts`), the chart-side indicator drawer,
the compare drawer, the three new Workbench views (Breadth History, Seasonality,
Swing Bench), and the version-1 chart-layout file format. Method: real-browser
verification through `playwright-cli` against the dev server on
`127.0.0.1:10000` (`data/dev/release`), plus the automated suites named in
`TEST_RESULTS.md`. Production (`8710`, PID 26596) was never touched.

**Final browser state: `playwright-cli console error` → 0 messages (0 errors,
0 warnings).** Evidence screenshots:

| File | Shows |
|---|---|
| `docs/evidence/workbench-2026-10-18-new-indicators.png` | GMMA 12 overlay lines, Alligator 3, SMI pane (2 outputs, 1 pane), MACD pane (3 outputs, 1 pane) |
| `docs/evidence/workbench-2026-10-18-compare.png` | 4-series compare with legend, modes/scale labelling |
| `docs/evidence/workbench-2026-10-18-breadth.png` | Breadth History view: latest readings + 30-session table on real data |
| `docs/evidence/workbench-2026-10-18-swing.png` | Swing Bench view: NABIL, mixed trend, confirmed levels, sizing/caveats |

## 1. Chart surface

* Chart types offered: **candles, bars (OHLC), hollow candles, line,
  line + markers, step, area, baseline (two-colour), column, Heikin Ashi**.
  Heikin Ashi is a **display transform** — the payload and meta line state it,
  and raw OHLCV in the store is untouched (documented in chart-types
  implementation and its meta label).
* Index symbols are close-only before the OHLC era: the meta line shows
  `index · N OHLC / M close-only`, and `#chart-type` **disables**
  candles/bars/hollow/Heikin for the index while keeping the six line-family
  types enabled (verified in the browser on `NEPSE`).
* Non-time-based families (Renko, Kagi, Point & Figure, Range, Line-break) are
  **absent, not faked** — they need a non-time bar pipeline; see
  `REMAINING_BLOCKERS.md` §2.

## 2. Indicator drawer (chart-side)

Verified in-browser this session:

* Search + category filter + favourites (★) + recents; adding from the catalog
  creates an **instance** `{id, name, params, label, color, visible}` —
  duplicates allowed, ids unique; instances persist per symbol
  (`mt-custom-inds-<symbol>`) and old saved entries upgrade in place.
* **Placement engine** (overlay vs pane) with documented rules:
  display hint wins; momentum/volume → pane; trend → overlay except
  `adx`, `aroon`, `linreg_slope`, `supertrend`; volatility → overlay only for
  pure upper+middle+lower groups (Bollinger keeps a pane so `bandwidth`/`%B`
  cannot wreck the price scale); price-unit "other" series overlay.
  **Browser-verified matrix: 33 overlay / 59 pane** over all 92 registered
  indicators (re-verified after session 28's 81 → 92 expansion). Regression found and fixed this session: single-output trend
  indicators (`ema`, `sma`, …) had been routed to panes by the earlier
  output-name heuristic (see `KNOWN_BUGS.md` B-90).
* **Multi-output drawing**: one pane per instance with palette-cycled colours
  (MACD = 3 series in 1 pane; SMI = 2 in 1 pane; GMMA = 12 overlay series,
  0 panes; Alligator = 3 overlay, 0 panes).
* **Hidden instances keep hidden panes**: a hidden instance's pane stays
  hidden across reload (found + fixed this session — `addPane` force-unhides
  the container to measure it; `drawPane` now re-applies `el.hidden`;
  B-91).
* Undo/redo stack (`state.indHist`, depth 40) snapshots quick-layer flags +
  the instance list per symbol; templates capture instances too, and old
  flag-only templates still apply. Template with instances verified:
  `sma(7)` → 1 overlay series / 0 panes, `macd(12,26,9)` → 3 series / 1 pane.

## 3. Compare drawer

* Primary + up to **3 comparison symbols (4 total)**, each row with colour,
  style (line/step/area), width, and a visibility toggle.
* Modes (verified list from the shipped select): **% change from window
  start · Indexed to 100 · Relative to NEPSE (ratio × 100) · Rolling return %
  (window configurable) · Raw price (shared left scale)**.
* Timestamp alignment is explicit: rebasing uses each symbol's **first visible
  observation**; **missing dates are gaps and never interpolated**; relative
  mode states when the NEPSE composite is unavailable rather than drawing
  something else; comparison series live on an invisible `cmpscale`, except
  raw mode which shares the visible `left` scale **with an on-screen warning**.

## 4. Layout files and templates

* **Export/import JSON v1** (`kind: "chart-layout"`): quick layers + indicator
  instances (name, params, label, color, visible) + compare config + chart
  type. Browser round-trip verified: a crafted layout restored `ema(33)`
  (overlay, custom label) and a hidden `rsi(9)` instance (its pane created and
  left hidden) plus compare `{mode: percent, symbol: NICA}`.
* Storage keys remain `mt-custom-inds-<symbol>`, `mt-ind-templates`,
  `mt-ind-recents`, `mt-compare-<symbol>`, `mt-custom-formulas-<symbol>`.

## 5. New Workbench views (sidebar group "Workbench")

* **Breadth History** — real data: 5,200 sessions (1995-07-20 → 2026-10-15),
  latest universe 326, advances 193 / declines 103 / unchanged 21,
  40.1 % / 35.3 % / 24.4 % above the 20/50/200-bar SMA, A/D + volume lines,
  new highs/lows; definitions echoed beside the table; windowed requests still
  use earlier bars for warm-ups/comparisons.
* **Seasonality** — NABIL on real data: January N=15, mean −3.46 %, median
  −3.55 %, hit rate 40 %; 7 weekday rows; the **holiday section reports
  unavailable with the real reason** (bundled calendar has no entries — never
  approximated).
* **Swing Bench** — NABIL on the last 400 bars: trend `mixed` → framing
  `none` → **no fabricated invalidation/target**; nearest confirmed support
  530.00 (swing 2026-08-27, confirmed 2026-09-07), resistance 550.00
  (confirmed 2026-04-28); checklist rows that cannot be computed carry
  `pass:null` + reason; sizing reports its own reason when no framed structure
  exists; "Open chart for this symbol" jumps to the charting tab.

## 6. Corrections to earlier records

* `docs/CHARTING_FEATURE_MATRIX.md` (session 19) lists rows 17 "Seasonality"
  and 18 "Swing trading research" as **IMPLEMENTED**. That was **not true at
  the time**: neither view nor backing endpoint existed in `web/static/` before
  this session. They are genuinely implemented and browser-verified now
  (this document supersedes those two rows).
* The era's empty `state.customInds`-era catalog assumed **flag-only
  templates**; templates now capture instances with backward compatibility.

## 7. Remaining UX gaps

* Non-time-based chart types; Part 14 pattern completion (18 of the checklist
  named); Alpha Coder; Part 18 engine unification — all tracked in
  `REMAINING_BLOCKERS.md`.
* Lightweight Charts **4.2.3** (vendored) has no native band or HLC-area
  series; the workbench does not fake them (candle overlays such as Donchian/
  Keltner are drawn as three line outputs).
* Pre-existing minor: the rendered DOM nests a `<main>` inside the app shell
  (accepted, not fixed — outside this session's scope).

---

## Session 27 — UX deltas and competitive-pattern mapping (2026-10-18)

### Competitive review — patterns extracted

A desk review of the leading analysis platforms (public product/review material,
not a hands-on trial of each) surfaced the recurring patterns below. Sources are
linked so each claim can be checked. The right-hand column says what this app
does about it — including where it deliberately does not.

| Pattern seen in the market | Where it comes from | This app |
|---|---|---|
| Vertical drawing rail on the left of the chart, each tool with an icon + tooltip | TradingView | **Shipped** (session 26; tooltips + icons already in `RAIL_GROUPS`) |
| A cursor/select tool that moves and edits objects; body-drag, not anchor-hunting | TradingView | **Shipped this session** — body hit-testing, capture-phase drag, logical-coordinate mapping |
| Selection feedback on the chart (handles / highlighted object) | TradingView | **Shipped this session** — numbered anchor handles for the selected drawing |
| Object tree / drawing list with lock, hide, rename, delete | TradingView | **Shipped** (drawing list: rename, per-drawing visibility, lock, ratios, delete) |
| Drawing templates; drawings stored in data coordinates so they survive zoom/timeframe | TradingView | **Shipped** (templates + t/p anchors) |
| Drawings/indicators saved per symbol; layouts hold chart config **but not watchlists/alerts** | TradingView layouts doc | **Shipped** — layout JSON carries chart config only; watchlists/templates live separately (our Clear dialog mirrors this boundary) |
| Hotkeys: undo/redo, delete, escape; discoverable shortcut hints | TradingView shortcuts | **Shipped this session** — Cmd/Ctrl+Z, Shift+Cmd/Ctrl+Z, Delete/Backspace (typing-guarded), Esc, Cmd/Ctrl+K + palette footer hints |
| Right-click / quick menu on a selected object; in-place text editing | TradingView | **Partial** — text/note edit via the drawing list and a prompt; no context menu on the canvas |
| One search box that reaches symbols, tools, indicators and actions | TradingView / Koyfin | **Shipped this session** — the command palette |
| Clean, low-chrome research surface; screeners and dashboards in the same app | Koyfin | **Present** — this terminal's views; palette now makes all of them reachable by name |
| Automated trendline/Fibonacci detection drawn straight onto the chart | TrendSpider | **Partial** — S/R zones, Fibonacci and patterns are computed by the backend and drawn as *analysis layers* the user toggles; nothing is auto-drawn without opt-in |
| Multi-symbol view: many charts in one grid | TrendSpider multi-symbol | **Not implemented** — one chart per view; the Compare drawer overlays up to 4 symbols on one chart instead |
| Automation layers can make charts feel cluttered | TrendSpider review | **Mitigated by design** — every analysis layer is opt-in, counted ("10 of 73 zones"), and one click from off; viewport is preserved so toggling never loses the zoom |
| Multi-timeframe overlays (higher-timeframe levels on the lower-timeframe chart) | TrendSpider | **Not implemented** |
| Pane reordering / dragging a pane out into its own window | TradingView | **Not implemented** — panes resize, collapse and remove, but there is no drag-drop and no floating window; nothing fakes it |

### Shipped this session (UX)

1. **Command palette** (`⌕ Search`, Cmd/Ctrl+K): grouped, keyboard-driven search
   over 30+ views, 10 chart types, 39 drawing tools, 7 analysis layers, all 92
   indicators, screener presets and 12 actions; disabled-with-reason rows for
   requested features that do not exist.
2. **Scoped Clear button** next to Chart settings with a confirmation dialog and
   live counts; drawings undoable, indicator removes undoable, layouts /
   templates / watchlists untouched by construction.
3. **Pane headers**: drag-resize, collapse/expand, taller/shorter, ✕ remove
   (undoable). Height and collapse state persist per instance.
4. **Viewport preservation**: tab switches and same-symbol reloads no longer
   reset zoom; Fit is explicit.
5. **Honest chart types**: the index renders real candles over its 2,217 genuine
   OHLC rows and shows gaps for close-only/invalid rows; a close-only series
   disables candle types with the reason visible in the tooltip.
6. **Drawing interaction**: body-level erase/select, on-chart selection handles,
   Delete/Backspace, axis-locked moves (hline = price only, vline = time only),
   and no simultaneous chart pan while dragging.

### Still open (honest list)

* Canvas context menu on a drawing (TradingView-style quick menu).
* Multi-chart / multi-symbol grid and pane drag-out.
* Multi-timeframe overlays and an MTF scan.
* Automated (opt-in) trendline auto-detection drawn on the chart.
* Pane layout is per-instance, not a named workspace that can be saved/loaded as
  a whole. The existing layout JSON covers chart config only.

## 2. Session 28 (2026-10-18, later pass)

Everything below was verified in a live browser (`playwright-cli`), real trusted
events, on dev `127.0.0.1:10000` with `data/dev/release`; final state **0 console
errors / 0 warnings**; cache-buster `app.js?v=wb21`. Production (`8710`, PID
26596) never touched.

| Item | Status | Evidence |
|---|---|---|
| **Market ribbon** — horizontally scrolling strip: index info, top gainers/losers, turnover, volume, 52-week extremes; category headers; clickable symbols; **pause/resume**; freshness badge | **IMPLEMENTED + TESTED-PASS + DATA-DEPENDENT** | Backend `GET /api/market/ribbon` + 8 API tests (`tests/test_api.py`). Browser: 70 items, 5 category groups + 1 honest `unavailable` group (`relvol`, reason stated), badge "NEPSE 2026-10-15 · delayed", pause toggles `paused`/`running` and persists, clicking GBIME loaded it into the chart. Screenshot `docs/evidence/wb15-ribbon.png` |
| **Unified chart-object manager** — `Objects` toolbar button → floating, draggable, resizable `#obj-pane` listing every visible object with its **owner**, visibility toggle and remove | **IMPLEMENTED + TESTED-PASS** | `collectChartObjects()`/`renderObjectManager()`. Browser: **6 owner groups, 159→164 rows** on NABIL; the "BO 563" row explains itself ("breakout / trigger level of the double_bottom (bullish)…"); Hide/Remove verified on one marker (9→8) and the object really left the chart. Marker provenance kept in `state.markerMeta` (keyed `time\|position\|shape\|text`) so LWC renderer payloads are untouched. Screenshot `docs/evidence/wb16-objects.png` |
| **Elliott Wave made visible** — "Analyze & draw on chart" / "Remove chart drawing" + status line | **IMPLEMENTED + TESTED-PASS** | Browser: 5 wave labels + connecting line drawn for `CANDIDATE_ONLY` candidate "Candidate Impulse (5-wave) (5 pivots, low)"; viewport `{3.89,249}` unchanged before/after; erase restores the manual labels. Never fabricates wave labels. Screenshot `docs/evidence/wb17-elliott-drawn.png` |
| **Active-tool banner** — shows the active drawing/Elliott tool and anchors placed | **IMPLEMENTED + TESTED-PASS** | "Elliott impulse · 0/5 anchors → 2/5 anchors"; hides on tool deactivation (`updateToolBanner`/`drawAnchorNeed`/`drawAnchorPlaced`) |
| **Viewport preserved when adding an indicator** (root cause) | **IMPLEMENTED + TESTED-PASS** | The pane↔price time-scale sync is now **one-directional** (price → pane; the old bidirectional subscription re-framed the chart on every add) plus an explicit `getVisibleLogicalRange()` capture/restore around every add. Browser: `{80,200}` preserved byte-for-byte for an overlay add (`ma_cross`) and a pane add (`percent_b`); pane still follows a price pan (`{120.98,230}`). No `fitContent` on add. Screenshot `docs/evidence/wb21-viewport-preserved.png` |
| **S/R + Fib axis-label crowding** | **IMPLEMENTED + TESTED-PASS** | `MAX_OVERLAY_LINES=8`, `MAX_OVERLAY_LABELS=4`, `OVERLAY_LABEL_MIN_GAP=0.012`; browser shows `resistance @ 554 [550-556]` and `zone @ 562` not overlapping |
| **Indicator set 81 → 92** and catalogue discoverability | **IMPLEMENTED + TESTED-PASS** | 11 new indicators (`megatool/ta/extra.py`); catalog modal re-verified "**92 of 92 registered**"; ⓘ info panel verified for a new indicator (`percent_b`); search verified for `vortex`, `percent b`, `moving average cross`, `zigzag` |

## 2b. Session 29 (2026-10-18, chart-objects completion)

Verified in a live browser (`playwright-cli`), real trusted events, dev
`127.0.0.1:10000` + `data/dev/release`; final state **0 console errors / 0
warnings**; cache-buster `app.js?v=wb23`. Production (`8710`) never touched.

| Item | Status | Evidence |
|---|---|---|
| **Quick-layer overlays in the Objects manager** (`SMA 20/50`, `EMA 20`, `Bollinger`, `Volume`) | **IMPLEMENTED + TESTED-PASS** | New **Quick layers** group in `collectChartObjects()`; each row shows label / type / owner ("Quick layers (toolbar)") / visibility. Browser: `quick-sma`, `quick-ema`, `quick-bb`, `quick-vol` present with owners; DOM Hide → series `visible:false`, Show → back. Screenshot `docs/evidence/wb24-objects-quick.png` |
| **Oscillator panes in the Objects manager** (`RSI`, `MACD`) | **IMPLEMENTED + TESTED-PASS** | `quick-rsi` / `quick-macd` rows present; Hide hides the pane element, Show restores it, Remove deletes the pane chart + clears the element + unchecks the toolbar toggle + drops the row |
| **Remove clears owned annotations** | **IMPLEMENTED + TESTED-PASS** | `quick-swings` owned **27** markers: Hide hid all 27, Remove dropped all 27 from `state.markers` and unchecked `#ind-swings`; no orphan markers left |
| **Detector markers reconstruct on reload** | **IMPLEMENTED + TESTED-PASS** | Patterns layer was **lost** on reload (B-109) — now `applyChartLayers` fetches (`loadPatternPanel`); 9 markers/9 series → full reload → 9/9. Candles: 122 → reload → 122 |
| **No duplicate objects across reloads** | **IMPLEMENTED + TESTED-PASS** | 3 full reloads: `quick`/`markers`/`candle`/`pat`/`groups` identical each run; `state.candleMarkers` reset in `destroyCharts` fixes the cross-symbol leak (B-108) |
| **Cross-symbol pattern leak** | **IMPLEMENTED + TESTED-PASS** | `#pattern-overlay` checkbox now synced to the symbol's layer flag; NABIL (on) → 9 markers, ADBL (off) → 0 (B-110) |
| **Manual Fibonacci viewport** (`fib_retracement`, `fib_extension`) | **IMPLEMENTED + TESTED-PASS (browser-measured)** | Zoomed to `{75,175}` then placed via the real click handler: **`{75,175}` → `{75,175}`**, drawing committed (5 series). Expanded chart mode: `{87,187}` → `{87,187}` |
| **Automatic Fibonacci viewport + object preservation** | **IMPLEMENTED + TESTED-PASS (browser-measured)** | `toggleLayer('fib')`: `{75,175}` → `{75,175}`, 8 fib series added, existing drawings and a freshly added catalog indicator intact. Expanded mode: `{87,187}` → `{87,187}` |
| **Browser console** | **TESTED-PASS** | `playwright-cli console error` → `Errors: 0, Warnings: 0` after the quick-layer + reload + fib flows |

## 3. Tool-by-tool audit against the reference images (Phase 6)

Source: `docs/ui-redesign/REFERENCE_INVENTORY.md` — **106 NEPSE Alpha
(`nepsealpha.com`, SastoShare v1.1) + 1 TradingView screenshots**, all visually
inspected, into 96 distinct screens. The chart workspace is references **#1
(TradingView), #94–#100** (large candles + volume, right-side indicator/analysis
rail, composition panel, Fibonacci/channel overlays, fresh-breakout panel).

Honesty note: the inventory records the **chart page's layout and overlay
families**, not a legible icon-by-icon list of the reference platform's toolbar.
So the table below audits **our** chart-tool surface tool-by-tool (grounded in
`RAIL_GROUPS` in `web/static/app.js`), and the "Reference (#…)" column is filled
only where the inventory explicitly names the family; where it does not, it says
so rather than guessing.

| Our tool (id) | Group | Status | Evidence / notes | Reference (#…) |
|---|---|---|---|---|
| `__cursor` Cursor/crosshair | Cursor | TESTED-PASS | Pan/zoom + OHLCV read; viewport preserved | #94 (chart page, not itemised) |
| `select` Select | Cursor | TESTED-PASS | Whole-drawing drag + per-anchor drag, axis locks | not itemised |
| `eraser` Eraser | Cursor | TESTED-PASS | Body hit-test delete; locked stay; Undo restores | not itemised |
| `trendline` Trendline | Lines | TESTED-PASS | 2 anchors, data coordinates | #96, #100 (overlay lines) |
| `ray` Ray | Lines | TESTED-PASS | extends right through anchor 2 | not itemised |
| `extended` Extended line | Lines | TESTED-PASS | infinite both directions | not itemised |
| `hline` Horizontal line | Lines | TESTED-PASS | 1 anchor, price-only drag | not itemised |
| `hray` Horizontal ray | Lines | TESTED-PASS | extends right only | not itemised |
| `vline` Vertical line | Lines | TESTED-PASS | 1 anchor, time-only drag | not itemised |
| `crossline` Cross line | Lines | TESTED-PASS | H + V through the anchor | not itemised |
| `channel` Parallel channel | Channels | TESTED-PASS | 3 clicks, slope+width | #96/#100 (channel overlays) |
| `regression_channel` Regression channel | Channels | TESTED-PASS | OLS centre + kσ bands | #94–#100 (analysis rail concept) |
| `pitchfork` Pitchfork | Channels | TESTED-PASS | median A→mid(BC) + tines | not itemised |
| `schiff_pitchfork` Schiff pitchfork | Channels | TESTED-PASS | flattened fork | not itemised |
| `fib_retracement` Fib retracement | Fibonacci | TESTED-PASS | levels p2 − r·(p2−p1) | #96/#100 (Fibonacci overlays) |
| `fib_extension` Fib extension | Fibonacci | TESTED-PASS | p2 + r·(p2−p1) | #96/#100 |
| `fib_timezones` Fib time zones | Fibonacci | TESTED-PASS | verticals 1,2,3,5,8… | not itemised |
| `fib_fan` Fib fan | Fibonacci | TESTED-PASS | rays through fib fractions | not itemised |
| `fib_channel` Fib channel | Fibonacci | TESTED-PASS | base line + ratio parallels | not itemised |
| `fib_tbe` Trend-based Fib extension | Fibonacci | TESTED-PASS | impulse projected from B | not itemised |
| `measure` Measure | Measure | TESTED-PASS | Δprice, Δ%, Δbars, Δvolume | not itemised |
| `price_range` Price range | Measure | TESTED-PASS | Δprice between anchors | not itemised |
| `date_range` Date range | Measure | TESTED-PASS | sessions + bars between anchors | not itemised |
| `rectangle` Rectangle | Shapes | TESTED-PASS | 2 anchors | #96 (overlay shapes) |
| `arrow` Arrow | Shapes | TESTED-PASS | head at anchor 2 | not itemised |
| `triangle` Triangle | Shapes | TESTED-PASS | 3-point shape | not itemised |
| `polyline` Polyline | Shapes | TESTED-PASS | multi-click path, Enter/Esc to finish | not itemised |
| `gann_fan` Gann fan (leg-relative) | Shapes | **APPROXIMATION** | rays at 1/8th fractions of the anchor leg; angles follow the chart scale, **not** absolute degrees (stated in the tooltip) | not itemised |
| `circle` Circle | Shapes | **APPROXIMATION** | 72-segment polyline approximation | not itemised |
| `ellipse` Ellipse | Shapes | **APPROXIMATION** | 3 anchors; polyline approximation | not itemised |
| `text` Text note | Text | TESTED-PASS | editable via the drawing list | not itemised |
| `note` Note | Text | TESTED-PASS | 1 anchor + drag handle | not itemised |
| `price_label` Price label | Text | TESTED-PASS | level line + editable price chip | not itemised |
| `flag` Flag | Text | TESTED-PASS | flag marker at a bar | not itemised |
| `xabcd` XABCD | Patterns | TESTED-PASS | 5-anchor harmonic construction | #50/#51 (pattern tiles exist as a *scanner*, separate) |
| `abcd` ABCD | Patterns | TESTED-PASS | 4-anchor retracement chain | not itemised |
| `three_drives` Three drives | Patterns | TESTED-PASS | 4 anchors | not itemised |
| `elliott_impulse` Elliott impulse | Patterns | TESTED-PASS | 5 anchors, labelled a **candidate** | not itemised |
| `elliott_abc` Elliott correction | Patterns | TESTED-PASS | A-B-C | not itemised |
| `fib_arc` Fibonacci arcs | Patterns | **APPROXIMATION** | concentric arcs as polylines | not itemised |
| `fib_spiral` Fibonacci spiral | Patterns | **APPROXIMATION** | sampled polyline; axes not equal scale (stated) | not itemised |
| `hns` Head & Shoulders (manual) | Patterns | TESTED-PASS | user-drawn annotation, **not** a detector | #50 (scanner detects H&S separately) |
| `long_pos` Long position | Positions | TESTED-PASS | entry→stop, target from R:R | not itemised |
| `short_pos` Short position | Positions | TESTED-PASS | entry→stop, target from R:R | not itemised |

Supporting chart surfaces:

| Surface | Status | Evidence | Reference (#…) |
|---|---|---|---|
| 92-indicator drawer/catalog with ⓘ info panel and Add | **IMPLEMENTED + TESTED-PASS** | 92 rows, 92 ⓘ buttons, "Showing 92 of 92 registered"; search by name/abbr/term | #94 (indicator rail) |
| Analysis layers (S/R, Fibonacci, patterns, harmonic, Elliott, gaps, profile) | **IMPLEMENTED + TESTED-PASS** | opt-in toggles, counted ("10 of 73 zones"), viewport preserved | #96, #99 (indicator/analysis rail) |
| Chart-object manager (owner/visibility/remove) | **IMPLEMENTED + TESTED-PASS** | `wb16-objects.png`; session 29 adds the **Quick layers** group (toolbar overlays/panes/markers) — `wb24-objects-quick.png` | #96 (overlay clutter control) |
| Command palette (views/tools/indicators/actions) | **IMPLEMENTED + TESTED-PASS** | 257 items; disabled-with-reason rows | n/a (our own) |
| Composition / right rail (indicator + analysis + composition panel) | **PARTIAL** | indicators and analysis are in drawers/popovers, not a persistent right rail as in #94/#99 | #94, #99 (deferred) |
| Chart scanner thumbnail grid | **NOT IMPLEMENTED (backlog)** | pattern *detector* exists; no thumbnail grid | #50, #51 (deferred) |
| Canvas context menu on a drawing | **NOT IMPLEMENTED (backlog)** | edit via drawing list/prompt only | not itemised |

**Conclusions from the audit:** every tool that exists in the app is reachable,
named (tooltip + status label), and either numerically exact (lines, fib,
channels, positions) or an **explicitly labelled approximation** (Gann angles,
circle/ellipse/arc/spiral). Nothing in the reference chart page is claimed as
copied: the two reference *features* still genuinely absent are a **persistent
right composition rail** and a **pattern scanner thumbnail grid**, both listed
above as backlog/PARTIAL, not faked.

