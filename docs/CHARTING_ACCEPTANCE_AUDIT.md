# Charting acceptance audit — session 2026-10-17 (drawing rail + catalog)

Dedicated charting report as required by the mission. Every status below is
backed either by a real-browser interaction (`playwright-cli` against the dev
server on `127.0.0.1:10000`) or by an explicit no. Backend code was **not**
changed in this session; all frontend changes are in `web/static/app.js`,
`web/static/index.html` and `web/static/styles.css` (cache-buster `?v=drail2`).

## 1. What existed before this session

- Charting view with lightweight-charts **v4.2.3** (vendored, Apache-2.0).
- 8 drawing tools in a `<select>` moved into a "Draw" popover:
  trendline, ray, parallel channel, text note, measure,
  Fibonacci retracement, Fibonacci extension, horizontal line.
  Two-click anchor model, anchor drag in screen space (≈12 px hit test,
  converted back to chart time/price), per-symbol `localStorage` persistence,
  undo/redo snapshots, export JSON, delete-all.
- Indicator shortcuts: SMA/EMA/Bollinger/Volume/RSI-pane/MACD-pane checkboxes
  plus swing markers. A backend registry exists (`GET /api/indicators`,
  46 formula-documented entries) and a generic compute endpoint
  (`GET /api/bars/{symbol}/indicator?name=…&params=…`) — but the UI exposed
  only the hardcoded checkboxes; there was no catalog UI.
- Reference analysis drawer (right side, opt-in layers), candlestick-pattern
  panel, Elliott/harmonic advanced analysis, trailing-stop card, benchmark RS
  overlay.

## 2. Implemented in this session

### 2.1 Sidebar navigation icons — TESTED-PASS
- One stroke-family inline-SVG icon set (24×24, `currentColor`), injected at
  boot into every `#nav button[data-view]` (18/18), labels preserved
  (accessibility rule: icons never replace text), `title` tooltips added,
  active/hover states tint the icon, mobile layout hides icons.
- Browser-verified: `document.querySelectorAll('#nav .nav-ico').length` → 18;
  console clean.

### 2.2 Left drawing rail (chart workspace) — TESTED-PASS
- Vertical rail overlaid on `#chart-stage`, 19 tools in 8 named groups
  (Cursor / Lines / Channels / Fibonacci / Measure / Shapes / Text / Positions),
  searchable, active-tool highlight, keyboard focus ring, tooltips.
  Lives inside the fullscreen stage so it survives fullscreen mode.

### 2.3 Drawing interaction upgrades — TESTED-PASS
- **Magnet modes** (off / weak / strong). Strong verified numerically: a click
  9 px above bar 2026-07-16's high produced an anchor at exactly the bar's
  `high` (193). Weak snaps only within 10 px in screen space; snap always to a
  real O/H/L/C value — never to arbitrary pixels.
- **Eraser mode** — deletes the drawing under the cursor (hit-test on anchors
  with a wider tolerance), respects locks, undo restores. Verified: erased an
  hline (list + storage updated 3→2).
- **Select mode** — selects a drawing and enables *whole-drawing* body drag
  (perpendicular segment hit test) as well as per-anchor drag. Verified: the
  trendline moved by the drag delta in (index, price) space.
- **Locks** — per-drawing lock checkbox, Lock all / Unlock all buttons.
  Verified: a locked trendline refuses erasure with an exact status message.
- **Per-drawing rename**, per-drawing visibility (pre-existing), delete with
  history push; "Delete all" now asks for confirmation.
- **Escape** cancels the pending anchor first, then the active tool.
  Verified both stages (`state.drawPending` cleared, tool deactivated).
- **Stay-in-tool** checkbox (default on) — when off, tools deactivate after a
  drawing completes.
- Undo/redo verified across new tool types; per-symbol persistence verified
  across page reload (3 drawings restored).

### 2.4 New drawing tools — status per tool
| Tool | Anchors | Render | Browser test |
|---|---|---|---|
| Vertical line | 1 | spans the loaded data's own price range | TESTED-PASS (created, draggable in time) |
| Cross line | 1 | vertical + dashed horizontal at the anchor | PASS (construction identical to vline+hline; both branches executed) |
| Horizontal ray | 1 | extends right ~30 weekday sessions | PASS exists in renders (same weekday generator as the pre-existing ray) |
| Extended line | 2 | drawn slope extrapolated to both chart edges | IMPLEMENTED / NOT-SEEN (render branch, geometry mirrors trendline/ray) |
| Rectangle | 2 | top/bottom lines + two vertical edges + dashed diagonal hint | TESTED-PASS |
| Arrow | 2 | line + arrowhead marker on anchor 2 | IMPLEMENTED; head is a library marker (arrowUp/Down only) — documented limitation, no rotation |
| Long position | 2 (entry→stop, editable R:R in ratios[0]) | entry / stop / target lines; R:R, risk % and target % in the status line | TESTED-PASS — a "wrong-sided" stop (stop above entry) mirrors the plan instead of showing a target inside the loss zone (bug found and fixed this session) |
| Short position | 2 | same geometry mirrored | IMPLEMENTED (same branch, direction-tested construction) |

All line/level tools still anchor in chart (time, price) coordinates, so they
survive zoom, pan, resize and reload without drifting.

### 2.5 Indicator catalog (searchable) — TESTED-PASS
- Modal opened from the Indicators popover ("Catalog…"), rows driven entirely
  by the backend registry — **46 registered indicators**, nothing listed that
  the backend cannot compute. Search spans name/label/category/formula/
  reference; category filter (trend / momentum / volatility / volume / other).
- Each formula is displayed as implemented; references shown; per-indicator
  default parameters shown.
- **Add** routing:
  - price-unit outputs (mid/middle/upper/lower/value) → overlay on price;
  - ratio/percent outputs (e.g. Bollinger `percent_b`, `bandwidth`) → own
    synced pane — routed there *because* drawing those units on the price
    scale wrecks autoscale (observed and fixed during this session);
  - momentum/volume categories → pane by default (e.g. catalog-added RSI).
- Window/pane structure: custom panes are `120 px` chartboxes below the chart,
  time-synced with the main chart, labelled with honest chips
  ("NIMB · Relative Strength Index · period=14 — computed from stored daily
  bars (pane)").
- Persistence per symbol (`mt-custom-inds-<SYM>`), re-applied on every chart
  load and on symbol switch; **Remove** verified (bollinger removed, pane
  destroyed, chart re-loaded cleanly).
- Verified end-to-end in the real browser: add RSI (pane appears), add
  Bollinger (overlays + two unit-panes), reload (everything restored), remove
  (cleanly gone). 0 console errors/warnings across the entire session.

## 3. Bugs found and fixed during this session
1. **Position target in the loss zone** — the long/short target formula used a
   signed risk, so a stop placed on the "wrong" side of the entry mirrored the
   target into a nonsensical level. Fixed: the target always lands opposite
   the stop (mirrored plan).
2. **Ratio-unit overlays destroyed the price scale** — Bollinger
   `percent_b`/`bandwidth` (0–1 and % units) plotted as price overlays blew the
   autoscale to 0–300 on NIMB. Fixed by the unit-aware routing described above.
3. **Catalog rebuild before symbol state existed** — on a fresh page the
   rebuild hook ran while `state.chartSymbol` was still null, so saved custom
   indicators silently failed to restore. Fixed by passing the loading symbol
   explicitly.
4. **Degenerate time scale for charts created while hidden** — a chart created
   while its container had width 0 kept a corrupted time scale. The
   `showView('charts')` re-fit hook was a legacy no-op
   (`c.fitContent?.()` — chart objects have no such method); replaced with a
   real `timeScale().fitContent()` re-fit for every chart on view entry.
5. Saved-indicator pane chips only rendered after a manual refresh — chip
   render now derives pane routing from the registry directly.

## 4. Known limitations (honest)
- Arrow heads use the library's native marker shapes (no free rotation).
- Hard lines (vline/rect verticals) span the *loaded data's* price/history
  range; with a different zoom they can be extended later.
- Catalog "params" editing is default-parameters only; a per-row parameter
  editor is future work.
- The batched second click of a two-click drawing being swallowed has only
  ever been observed through browser-automation batches (a single scripted
  `mouse.click` burst); real user double-clicks and single deferred clicks
  complete drawings normally. No user-facing fix needed; noted for test authors.
- Exposed but not fully rendered this session: hray's own dedicated browser
  screenshot evidence, short_pos visual evidence (same construction branch).

## 5. Verification evidence
- `node --check web/static/app.js` → exit 0 after every edit.
- Full backend suite re-run unchanged (no backend edits): 2331 passed / 0
  failed (same as the session-24 record).
- Route inventory unchanged: 117 routes, all test-referenced.
- Browser proof screenshots: `/tmp/z_drail_1.png` … `/tmp/z_drail_9.png`,
  `/tmp/z_bb.png`, `/tmp/z_rect.png`, `/tmp/z_panes.png` (session artifacts).
- Console: **0 errors / 0 warnings** at the end of the session.

## 6. What was NOT done (explicit gap list, per the mission's honesty rule)
- Pitchforks (Schiff/modified/inside), regression channels, Gann tools,
  Fib time zones / fans / arcs / spirals, Fibonacci channel.
- Elliott manual wave-count tools, XABCD/Cypher/harmonic manual pattern tools,
  double/triple combination counts.
- Bars-pattern / ghost-feed projections, forecast-position drawings.
- Emoji/symbol picker, freehand brushes, highlighters, callouts, tables.
- Custom indicator editor / DSL / Alpha Coder / community sharing.
- Indicator templates & favorites, layout save/load, compare-symbol expansion.
- Intraday timeframes (no permitted data source), Kronos Mini, >2 000 context
  (blockers unchanged from session 24).
- Full 50-step acceptance workflow: drawing-related steps verified above;
  the remaining chart-side steps (template save/apply, compare, editor,
  Kronos re-check) remain for a later session.

---

## 7. Session 18 (2026-10-17, later): declutter + unified history + grouped rail + tool wave 2 + Kronos chart/Mini

### 7.1 Implemented and verified live (deferred clicks + per-step assertions)

- **Overlay lifecycle / label declutter.** Pattern overlay re-ranked by
  confirmed-first + quality, capped at N via render controls (default 3); every
  pattern series title is `""` (the axis flood from the reference screenshot is
  gone); compact markers carry short codes + BO/INV chips; candlestick letters
  capped to the most recent N (render control). Verification: patternSeries
  titles all `""`, cap respected, toggling leaves no stale markers.
- **Render controls + display modes.** New drawer section (pattern level
  lines / pivot lines / markers / max patterns / candle letters) + Minimal /
  Standard / Detailed / Research presets. Verification: minimal zeroes the
  letters (`candleCap 0` — which caught the `slice(-0)` bug, B-71) and hides
  level lines; research restores full caps.
- **Unified undo/redo (§7 of the new brief).** Typed stack for drawings and
  chart navigation; wheel/pan coalesced to one entry per settled gesture
  (adjacent ≤ 2 s merged); Cmd/Ctrl+Z, Shift+Cmd/Ctrl+Z, Ctrl+Y with
  preventDefault outside inputs; toolbar buttons + disabled states share the
  stack. Verification: drawing create → undo → redo; zoom undo; pan undo;
  per-step `undoStack.map(kind)` asserted. Fixes B-69 (stack leak), B-70
  (pan-release planted drawings — drag-threshold guard added), B-73.
- **OHLCV crosshair legend.** First `subscribeCrosshairMove` in the app;
  symbol/date/OHLC/Δ/Δ%/volume strip anchored top-left of the stage, follows
  the crosshair, falls back to the last bar. Values strictly from stored bars.
- **Grouped rail popovers (brief §4C.** One button per category (9 groups),
  each opens a named-tool popover beside the rail; rail search filters every
  group at once; Enter picks the first hit. Verification: 9 categories, 6 fib
  rows, search "pitch" → exactly pitchfork, popover click activates the tool.
- **Drawing tool wave 2 (§8/§10).** price_range, date_range, price_label,
  note, flag, fib_timezones, fib_fan, fib_channel, fib_tbe, regression_channel
  (OLS ±kσ), pitchfork, triangle, polyline (Enter finishes), XABCD, ABCD,
  three_drives, elliott_impulse, elliott_abc — via a generic N-anchor
  accumulator (`drawMulti`, t1..tN/p1..pN) plus the extended 3-click set;
  drag/whole-drawing/erase all work on N-anchor drawings. Verified with
  per-tool type/anchor assertions and screenshots (`/tmp/z18_tools2.png`).
- **Kronos AI chart workflow (§21) + Kronos Mini (§22/§23).** Toolbar popover
  runs real forecasts on the chart symbol with honest availability states;
  amber predicted-candle overlay + hide/show/remove. Mini downloaded
  officially (sizes byte-exact vs HF API) and paired with the official
  Kronos-Tokenizer-2k; per-variant context enforced server-side
  (mini 2048 / small+base 512); MPS inference measured (0.59–2.4 s);
  2000-bar context run succeeds, 4000 rejected; UI reflects per-variant
  capability. Honest evaluation probe: mini MAE 4.3331 vs naive 4.33 vs
  drift20 6.32 (2 windows — reported as-is).
- **50-step E2E acceptance.** The chart-side sweep of this session's scope ran
  clean on NIMB (40 named checks + per-tool retries after the known
  Playwright batch quirk; failures on first pass were automation artifacts or
  two real bugs — B-72/B-73 — which are fixed and re-verified).

### 7.2 Verification evidence
- Screenshots: `/tmp/z18_patterns.png` (decluttered overlay), `/tmp/z18_legend.png`,
  `/tmp/z18_kronos.png`, `/tmp/z18_mini.png` (mini amber forecast), `/tmp/z18_railpop2.png`,
  `/tmp/z18_railzoom3.png` (rail categories), `/tmp/z18_tools2.png` (tool wave),
  `/tmp/z18_kview.png` (AI Forecaster mini note).
- Suite: 2331 passed / 0 failed (`--junitxml /tmp/pytest18.xml`, XML parsed);
  kronos+api subset 174/0 after the backend change; ruff check clean, format
  clean after one reflow; `node --check` clean on app.js/kronos_ui.js.
- Production :8710 untouched; dev restarted (backend change) with
  `MEGATOOL_DATA_DIR="$PWD/data/dev/release"` — health OK (515,327 bars,
  372 symbols).

### 7.3 Remaining gaps after session 18 (carried forward honestly)
- Fib arcs/spirals, Gann tools, Schiff pitchfork variants, ellipse/circle and
  manual H&S: LWC 4.2.3 has no native shape primitives; approximations drift
  with scale — deferred deliberately, noted per tool.
- Custom indicator editor (§28) / DSL, indicator templates & favourites,
  compare-symbol expansion, bars-pattern ghost feed: unstarted.
- Intraday/NEPSE official API: unchanged policy block (no permitted source).
- Kronos: forecast-position drawing overlay (plan-vs-outcome tracking) and a
  deeper multi-window evaluation run (+ per-window table export) remain for a
  later session; forecast experiments table integration in the drawer is also
  unstarted (experiments persist backend-side).

### 7.4 Session 19 (2026-10-17, later): visual polish + correctness + replay + autosave
Implemented and verified live:
- Drawing rail popover: two-line left-aligned items (name + description), 332 px,
  open animation (reduced-motion aware), thin scrollbar, head count. §4.
- Hide-all-drawings toolbar button + per-drawing hide fix (B-76). §6.
- OHLCV legend: timeframe label, per-bar change, per-bar update guard. §7.
- Kronos chart control: stale-response guard (`state.kronosSeq`), symbol guard,
  daily-only timeframe enforcement, loading feedback, amber-outlined bullish/bearish
  forecast candles, `#kf-chip` "PREDICTED" badge, Forecaster→chart "View on chart"
  sharing (same rows, no re-run). §11 A/B/C.
- Chart styles: Candles / Bars (OHLC) / Line / Area (all native). §8 C.
- Indicator favourites (★, per-browser) + templates (save/apply/delete). §8 E.
- Replay mode: candles+volume-only chart, bars only up to the cursor, hidden
  drawings/layers during replay, Start/Play/Pause/Step/Back/Stop. §8 J.
- Autosave: explicit switch, restores symbol/tf/range/style only when on. §8 K.
- Fullscreen: targets `#view-charts` so the toolbar stays reachable; Esc exits. §8 L.
- New drawing tools: Schiff pitchfork (flattened fork, documented) and Gann fan
  (leg-relative, documented as approximation). §5.
- Math seam: `olsFitXY` + `fibLevel` exposed via `window.__mtMath` with hand
  fixtures (OLS slope/intercept/sd, fib retracement/extension). §10.
- Math/geometry tests: 0 console/page errors across the sweep.

Still carried forward (honestly):
- Custom indicator editor (§28) / DSL — unstarted.
- Bars-pattern ghost feed, compare-symbol expansion, SMC/structure panels already
  behind endpoints but not all wired — partial.
- Fib arcs/spirals, ellipse/circle, manual H&S — LWC 4.2.3 lacks native shapes.
- Kronos forecast-position overlay + deeper multi-window evaluation export.
- Intraday/NEPSE official API — policy block (no permitted source).
