# Remaining blockers — 2026-10-18

Ordered register of everything the workbench session did **not** complete, plus
standing constraints. Each item names its type: owner decision, backlog
feature, data dependency, or pre-existing condition. Nothing here is silently
dropped; nothing here is claimed done.

## 1. Kronos Mini NABIL run — OWNER DECISION (GPU)

* Status: **BLOCKED** — prepared but not launched; needs the owner's explicit
  approval before any training/GPU work (constraint in force since session 18).
* The exact command, config, data slice and expected artifacts are in
  `KRONOS_FINAL_GO_NOGO.md`. No GPU work was performed in this session.

## 2. Non-time-based chart types — BACKLOG

* Renko, Kagi, Point & Figure, Range bars, Line-break. These require a bar
  **pipeline** that is not a function of clock time (brick/box construction),
  with its own data model, crosshair alignment semantics and persistence.
  Deliberately **not** shipped as decorative imitations; raw OHLCV stays the
  only stored truth.

## 3. Parts 8–13 name checklists — MISSING INPUT

* The ~350 exact script/indicator names from the owner's specification
  (built-ins, Nepsealpha customs, community scripts, breadth, additional
  scripts) are **not present in this repository snapshot**, so a line-by-line
  cross-off cannot be produced here.
* What exists instead: the honest implemented catalogue —
  `INDICATOR_CATALOGUE.md` (81 registered indicators + 18 candle patterns),
  generated from the live registry. Adding the checklists as a file would let
  the next session produce the exact cross-off.

## 4. Candlestick patterns (Part 14) — BACKLOG

* 18 of the checklist's named patterns are implemented and tested
  (`megatool/ta/candles.py`). The remaining names live only in the owner's
  specification text (see §3); they are backlog, not approximated.

## 5. Alpha Coder (Parts 19–20) — BACKLOG

* The safe formula **DSL** exists (whitelisted parser/evaluator, no `eval`;
  editor with test/save/remove, per-symbol persistence, auto-apply). The
  natural-language "Alpha Coder" assistant (description → formula) was
  **not built**.

## 6. Part 18 unified S/R + chart-pattern engine — PARTIAL

* Swing structure/breaks, levels, fibonacci, harmonic, elliott, candlestick
  patterns, gaps and volume profile exist as separate, documented modules
  from earlier sessions; the swing bench composes the swing primitives.
  A single unified engine API over all of them was **not** consolidated in
  this session.

## 7. Corporate actions / price adjustments — DATA DEPENDENCY

* Every stored price is `adjustment_status='unadjusted'`; bonus/split events
  can distort historical levels, returns and structure. Payloads warn about
  this (swing bench caveat) but no adjustment source exists yet.

## 8. Fundamentals data limits — DATA DEPENDENCY

* `security_master` is empty in dev; no float-shares or DPS source; historical
  P/E uses point-in-time EPS only. (Standing items B-07/B-08 family in
  `KNOWN_BUGS.md`.)

## 9. Live data limits — POLICY / DATA DEPENDENCY

* Official NEPSE API returns HTTP 401 and stays gated by policy
  (`MEGATOOL_NEPSE_API_AUTHORIZED` unset); no intraday feed exists, so every
  intraday-dependent feature is out of scope until a licensed feed arrives.

## 10. `megatool/api.py` lint/format drift — PRE-EXISTING (earlier sessions)

* `ruff check megatool/api.py` → **18 findings**, all outside this session's
  added routes: I001 imports (9×), E702 (2×), F401 (2×), F841, F811
  (`fundamentals_compare` redefined), B904, E741 — at lines 10, 766, 1224,
  1248, 1260, 1262, 1274, 1292, 1299, 1338, 1394, 2291, 2292, 2345, 2391,
  2479, 2526, 3861.
* `ruff format --check megatool/api.py` → 21 hunks, all in lines ~781–1480
  (Kronos middleware, gonepse, market-intelligence, fundamentals routes) plus
  2379–2672 / 3920 / 5068 — again other sessions' regions.
* Deliberately untouched: reformatting/refactoring another session's
  in-flight, uncommitted code without review. This session's edits are clean
  and the one B008 attributable to a line added this session was fixed
  (scoped `# noqa: B008` with reason, matching the file's own noqa precedent).
* Also pre-existing: 9 routes without automated test references
  (fundamentals/eps-rankings, market-intelligence ×6, screen export.pdf/.xlsx)
  per `scripts/route_inventory.py`.

## 11. python-dotenv CVE — RESOLVED (upgraded)

* **Status: resolved.** ``python-dotenv`` is installed and locked at **1.2.4**
  (``uv.lock`` line 460, ``importlib.metadata.version('python-dotenv') ==
  '1.2.4'``), which is above the 1.2.2 the dependency audit recommended.
  The declared floor remains ``python-dotenv>=1.0`` in ``pyproject.toml``.
* This clears the earlier "owner decision" note. No further action is required
  for the dependency itself.
* Re-verified this session: the full test suite imports ``megatool.config``
  (the only importer, ``megatool/config.py:14``) and passes with exit 0.


## 12. Commit / push — NOT AUTHORIZED

* ~240 files remain uncommitted on `main` (the whole multi-session body of
  work). No commits, no pushes, no deploys were made — by rule.

## 13. Holiday seasonality — DATA DEPENDENCY

* `megatool/market_intelligence/config/trading_calendar.json` has **no holiday
  entries**, so the holiday study reports `available:false` with the real
  reason. Supplying a verified holiday list is the unblock.

## 14. Breadth payload size — MINOR / BACKLOG

* The default full-history breadth response is 5,200 sessions × ~14 series
  (~1–3 MB JSON). Fine locally; pagination or a default window would help if
  it ever leaves the local terminal.

## 15. Independent source verification — LIMITATION (L-03 family)

* The only community source is `github.com/Aabishkar2/nepse-data`, which
  carries no LICENSE file; redistribution terms unverified. Data stays local.

## 16. Minor DOM defect — ACCEPTED (pre-existing)

* The rendered app nests a `<main>` inside the shell (and one stray
  `</footer>` was removed earlier this session). Accepted as cosmetic; not
  fixed.

## 17. Chart UX features still absent — BACKLOG (session 27, do not fake)

* **Canvas context menu** on a drawing (TradingView-style quick menu): a drawing
  is selected/edited via the drawing list and the on-chart handles; there is no
  right-click menu on the canvas.
* **Multi-symbol grid** (many charts at once) and **pane drag-out** into a
  separate window: panes can be resized, collapsed and removed, but their
  **order cannot be changed** and they cannot be dragged into new tabs/panes.
  Nothing in the UI implies otherwise.
* **Multi-timeframe overlays** (higher-timeframe levels drawn on a
  lower-timeframe chart) and an **MTF scan**: not implemented.
* **Opt-in auto trendline / Fibonacci detection** drawn straight onto the chart
  (TrendSpider-style): S/R zones, Fibonacci and patterns are computed and
  available as opt-in *analysis layers*, but nothing is auto-drawn on load.
* **Named workspace that saves the pane layout as a whole**: pane height /
  collapsed state persist per indicator **instance** (localStorage), and the
  existing layout JSON v1 covers chart config (quick layers + instances +
  compare + chart type) — but there is no named workspace saving pane order.

## 18. Escape-key dispatch is not centralised — MINOR (session 27)

* Four independent `document` keydown listeners handle `Escape` (chat panel,
  drawing cancel/selection, drawers + fullscreen, palette/Clear modal). Each has
  a distinct, idempotent effect and they run in a fixed order, so behaviour is
  correct; they are simply not routed through one dispatcher. Other global keys
  are unique and typing-guarded (Cmd/Ctrl+K → palette; Cmd/Ctrl+Z and
  Delete/Backspace → guarded to the chart view and non-typing targets).

## 19. Pane layout not covered by automated tests — NOT-TESTED

* Pane resize / collapse / remove and the command palette and Clear dialog are
  verified in a **live browser with real trusted events** (`TEST_RESULTS.md`
  §27) but have **no pytest coverage** — they are DOM/browser behaviour. A
  headless Playwright test harness is not set up in this repo, so these remain
  browser-verified only, and are labelled as such rather than claimed as
  automated.

## 20. Session-28 surfaces verified in the browser, not by pytest — NOT-TESTED

* The market ribbon **frontend**, the chart-object manager, the Elliott
  draw/erase flow, the active-tool banner, the S/R + Fib label caps and the
  viewport-preservation fix are all verified in the **live browser**
  (`TEST_RESULTS.md` §28; screenshots `docs/evidence/wb15-*`, `wb16-*`,
  `wb17-*`, `wb21-*`) but have **no pytest coverage** — they are DOM/chart
  behaviour on a canvas. Only the ribbon **backend** endpoint has automated
  coverage (8 tests in `tests/test_api.py`). Labelled browser-verified, not
  claimed as automated.

## 21. Reference-platform features still absent — BACKLOG (session 28)

* **Persistent right composition rail** (reference NEPSE Alpha #94/#99): the
  indicator/analysis/composition panel is docked at the right there; here those
  are drawers and popovers (reachable, not docked).
* **Pattern-scanner thumbnail grid** (reference #50/#51): the detector exists but
  there is no tiled grid of detected-pattern thumbnails.
* Both are listed in `CHART_UX_AUDIT.md` §3 as PARTIAL / NOT IMPLEMENTED; nothing
  in the UI pretends they exist.

## 22. Ribbon data dependencies — DATA DEPENDENCY

* `security_master` is empty in the dev store, so ribbon rows show **tickers
  without company names** (`GET /api/market/ribbon` returns the name when it
  exists and omits it otherwise — no invented names).
* NEPSE has **no intraday feed** here, so the ribbon badge reads
  "NEPSE <last stored date> · delayed", and the `relvol` category is returned in
  `unavailable` with the reason (no intraday volume baseline) rather than a
  fabricated value.
* All ribbon prices inherit the store's `adjustment_status='unadjusted'`.

## 25. Session-30 new capabilities are backend-ready but not yet UI-wired — BACKLOG

* Rolling beta, volatility percentile, MTF confluence, technical rating and S/R
  strength scoring are implemented as tested pure functions in `megatool/stats.py`,
  `megatool/ta/multitimeframe.py`, `megatool/ta/confluence.py` and
  `megatool/ta/levels.py`. They are not yet exposed through an API route or a
  chart-workspace view; integration into the existing advanced-analysis workspace
  is the next step.

## 26. Three indicators remain at the invariants verification level — NOT-TESTED numerically

* `adx`, `keltner`, `supertrend` have only finite/first-valid checks in
  `tests/test_indicators3.py`. Adding hand-computed reference values for these
  (especially ADX's Wilder smoothing and Supertrend's ratchet) would promote them.

## 23. Quick-layer toggles are not persisted — BEHAVIOUR (session 29)

* The chart-toolbar quick layers (SMA/EMA/Bollinger/Volume/RSI/MACD/Swings/
  Close-based pivots) are **display toggles**, not persisted configuration: their
  checkbox state resets to the HTML default on a reload. Because of that, the
  **swing-marker** quick layers cannot reconstruct after a reload (their config is
  not stored anywhere).
* This is deliberate and honest rather than a fabricated restore. The
  **persistent** equivalent is the right-hand Analysis drawer layers (candles,
  patterns, Elliott, harmonic, S/R, Fibonacci, volume profile), which are stored
  per symbol in `localStorage['mt-chart-layers-<symbol>']` and **do** reconstruct
  their detectors on reload (verified: patterns 9 → reload → 9, session 29 /
  B-109).
* Persisting the quick-layer toggles would change user-visible persistence
  semantics and is an **owner decision**; it was not changed unilaterally.

## 24. Browser-only regression tests are opt-in — NOT-TESTED in the default suite

* `tests/test_browser_objects_manager.py` (8 cases) drives a **real browser**
  through `playwright-cli` to assert quick-layer/oscillator rows, Hide/Remove
  semantics, owned-annotation cleanup, detector-marker restoration, no-duplicate
  reloads, manual + automatic Fibonacci viewport preservation, object preservation
  and browser console errors.
* It is **opt-in** (`MEGATOOL_BROWSER_TESTS=1`, plus a live dev server on
  `127.0.0.1:10000`) because it needs a browser; without the flag the module is
  **skipped** (8 skips) so the default suite stays hermetic and offline. Run
  command in `TEST_RESULTS.md` §29.
* The manual/automatic Fibonacci viewport measurements are likewise
  browser-driven (a canvas cannot be measured from pytest) and labelled
  browser-measured, not automated.
