# Test results

**Session 2026-10-18 (session 30: comprehensive audit, indicator validation, 5 new advanced-analysis capabilities) — full suite 2,701 passed / 0 failed / 0 errors / 8 skipped, exit 0.** Command: `MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings`. This pytest build omits the terminal summary line in this environment: the count above is the passed-dot total over the captured log (`$TMPDIR/full_s30.log`: 2,701 `.` + 8 `s`, 0 `F`/`E`, [100%]) and the process exit code is 0. Up **+41** on session 29's 2,660. New this session: `tests/test_indicators3.py` (25 numeric reference tests for the 16 previously invariant-only indicators) and `tests/test_advanced_analysis.py` (16 tests for the 5 new capabilities: rolling beta, volatility percentile, MTF confluence, technical rating, S/R strength scoring). `tests/test_indicators.py`/`test_indicators2.py` unchanged (still green). Verification map moved 49 → 62 reference / 41 → 28 invariants / 2 sparse / 0 none after fixing the scanner's promotion rule. Opt-in browser module unchanged: 8 passed / exit 0 with `MEGATOOL_BROWSER_TESTS=1`. Frontend: `node --check web/static/app.js` exit 0; `generate_indicator_info.py` regenerated (92 entries, 0 empty references/notes/formulas). Browser re-verification: 92/92 ⓘ buttons, "money flow" → CMF + MFI, Fibonacci `{75,175}` → `{75,175}`, console 0 errors / 0 warnings. Evidence: `docs/evidence/wb24-objects-quick.png`. Report: `SESSION_30_COMPLETION_REPORT.md`.

**Session 2026-10-18 (session 29: complete the chart-objects manager, detector-marker lifecycle, measured Fibonacci viewport) — full suite 2,660 passed / 0 failed / 0 errors / 8 skipped, exit 0.** Command: `MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings`. This pytest build omits the terminal summary line in this environment: the count above is the passed-dot total over the captured log (`$TMPDIR/full_s29.log`: 2,660 `.` and **8** `s` characters, **0** `F`/`E` progress marks across 38 output lines) and the process exit code is 0. The 8 skips are the new **opt-in browser module** `tests/test_browser_objects_manager.py` (8 cases), which is skipped unless `MEGATOOL_BROWSER_TESTS=1` is set, so the default suite stays hermetic/offline; with the flag set against the live dev server it **ran green — 8 passed, exit 0** (log `/tmp/browser_tests.log`). No backend code changed this session, so no non-browser tests were added and the passed total is unchanged from session 28 (2,660); the 8 browser cases are the new coverage. Frontend fixes verified in a live browser (dev `127.0.0.1:10000`, `data/dev/release`, cache-buster `app.js?v=wb23`), final state **0 console errors / 0 warnings**: **quick-layer overlays/panes now appear in the Objects manager** (new *Quick layers* group; `quick-sma/ema/bb/vol/rsi/macd` present with label/type/owner; DOM Hide → series `visible:false`, Show → back; Remove deletes the pane chart + clears its element + unchecks the toolbar toggle + drops the row); **removing `quick-swings` cleared all 27 markers it owned** and unchecked the toggle; **detector markers reconstruct after a full page reload** (patterns: was lost → now `loadPatternPanel` in the layer path, 9 markers/9 series → reload → 9/9; candles 122 → 122); **no duplicate objects across three full reloads** (`quick`/`markers`/`candle`/`pat`/`groups` identical each run); **candle-marker cross-symbol leak fixed** (NABIL 122 → ADBL 0) and **pattern-overlay cross-symbol leak fixed** (NABIL 9 → ADBL 0); and the **Fibonacci viewport measured** (the session-28 gap): manual `fib_retracement`/`fib_extension` and automatic `fib` each preserved the visible logical range byte-for-byte — `{75,175}` normal mode, `{87,187}` expanded chart mode — with existing drawings and a freshly added catalog indicator intact. Evidence: `docs/evidence/wb24-objects-quick.png`. Bugs closed: B-107 (quick layers missing from the manager), B-108 (candle-marker cross-symbol leak), B-109 (pattern markers lost on reload), B-110 (pattern-overlay checkbox leak), B-111 (duplicate/orphan safety measured). Honest remaining gaps: quick-layer toggles stay unpersisted display toggles (so swing-marker quick layers cannot reconstruct after a reload; `REMAINING_BLOCKERS.md` §23) and per-marker suppression stays session-only (§24).

**Session 2026-10-18 (session 28: ribbon, object manager, Elliott, viewport root-cause fix, 11 new indicators) — full suite 2,660 passed / 0 failed / 0 errors / 0 skipped, exit 0.** Command: `MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings`. This pytest build omits the terminal summary line in this environment: the count above is the passed-dot total over the captured log (`$TMPDIR/full_s28.log`: 2,660 `.` characters, **0** `F`/`E` progress marks across 37 output lines) and the process exit code is 0. Up **+61** on session 27's 2,599. Added/changed this session: the indicator registry grew 81 → **92** via `megatool/ta/extra.py` (11 indicators), so `tests/test_indicators.py` gained 9 independently written numeric-reference tests plus dedicated **sparse-pivot** property tests for `zigzag` and `williams_fractal` (declared in `SPARSE_PIVOT_INDICATORS` so the exclusion is explicit, never silent); `tests/test_api.py` gained **8** ribbon tests (shape/honesty, breadth sums, dedupe vs `skipped_duplicates`, `top` validation → 422, empty store, real gainer-vs-loser ordering, no-invented-index, index-when-stored). `tests/test_indicators2.py` unchanged (36 literal reference tests, all still green). Backend addition: `GET /api/market/ribbon?top=N` in `megatool/api.py` (most-recent-stored-day gainers/losers/turnover/volume, index info from the last two stored closes, 52-week extremes deduped against the claimed set, and an `unavailable` group with a stated reason for categories with no honest source, e.g. `relvol`). Frontend additions verified in the browser (dev `127.0.0.1:10000`, `data/dev/release`): market ribbon (70 items, 5 category groups + 1 honest `unavailable` group, badge "NEPSE 2026-10-15 · delayed", pause/resume persisting in `localStorage['mt-ribbon-paused']`, click-through opened GBIME); unified **chart-object manager** (6 owner groups, 159→164 rows on NABIL; a marker row reads its full provenance; Hide/Remove verified on one marker 9→8 with the object really gone); **Elliott Wave** now draws on the chart (5 wave labels + line, status line, `CANDIDATE_ONLY`, viewport unchanged) and erases; **active-tool banner** ("Elliott impulse · 0/5 anchors → 2/5 anchors"); and the **viewport-preservation root-cause fix** (pane↔price sync made one-directional; `getVisibleLogicalRange()` captured/restored around every add — `{80,200}` preserved for both an overlay add `ma_cross` and a pane add `percent_b`, and a pane still follows a price pan). Final browser state **0 console errors / 0 warnings**; cache-buster `app.js?v=wb21`. Evidence: `docs/evidence/wb15-ribbon.png`, `wb16-objects.png`, `wb17-elliott-drawn.png`, `wb20-new-indicators.png`, `wb21-viewport-preserved.png`. Registry/catalogue reproducibility re-established this session: `scripts/generate_indicator_reports.py` was made fully dynamic (counts, placement and the verification split are computed from the registry and asserted against the browser matrix 33 overlay / 59 pane) and now emits the catalogue's **Verification** section from the same scanner the UI uses (`generate_indicator_info.verification_map`) → **49 reference / 41 invariants / 2 sparse / 0 none**.

**Session 2026-10-18 (session 27: chart/indicator/research workbench) — full suite 2,599 passed / 0 failed / 0 errors / 0 skipped, exit 0.** Command: `MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings`. This pytest build omits the terminal summary line in this environment: the count above is the passed-dot total over the captured log (2,599 `.` characters, **0** `F`/`E`/`s`/`x` progress marks across 37 output lines) and the process exit code is 0. Added this session: `tests/test_breadth.py` (8), `tests/test_seasonality.py` (9), `tests/test_swing_workbench.py` (7), `tests/test_indicators2.py` (36 reference-value tests) plus generic guards in `tests/test_indicators.py` over all 81 registered indicators; extended `tests/test_scanner.py` (volume-scanner catalogue + reference maths incl. pocket-pivot alignment) and `tests/test_api.py` (breadth / seasonality / swing-workbench route tests). Backend additions: `megatool/breadth.py`, `megatool/seasonality.py`, `megatool/swing_workbench.py`; 7 scanner metrics (34→41) and 8 presets (23→31); three new GET routes (`/api/breadth/history`, `/api/seasonality/{symbol}`, `/api/bars/{symbol}/swing-workbench`). Gates: `ruff check` clean on every file created or edited this session; `ruff format --check` clean on every file authored this session (4 files reformatted after the check caught them; `scanner.py` + `tests/test_scanner.py` single-hunk fixes) — **known exception** `megatool/api.py` keeps 21 pre-existing format hunks inside earlier sessions' uncommitted regions (line ranges in `REMAINING_BLOCKERS.md` §10; none inside this session's added route blocks); `node --check web/static/app.js` exit 0; `scripts/route_inventory.py` → **134 routes** (22 mutating / 112 read-only), **125 test-referenced**, the 9 unreferenced all pre-existing (fundamentals/eps-rankings, market-intelligence ×6, screen exports). Browser verification (dev `127.0.0.1:10000`, `data/dev/release`): chart types incl. hollow/Heikin/step/baseline/column/line+markers on NABIL; index close-only restriction on NEPSE (`index · 2217 OHLC / 3079 close-only`, candlestick types disabled, area active); indicator drawer placement matrix **28 overlay / 53 pane**; GMMA 12 overlay series / 0 panes, Alligator 3/0, SMI 2-in-1-pane, MACD 3-in-1-pane; a hidden instance's pane stays hidden across reload; compare drawer (4 symbols, 5 modes: % change / indexed / relative-to-NEPSE / rolling return / raw; gaps never interpolated); layout JSON round-trip restores instances + params + labels + visibility + compare + pane visibility; template-with-instances restore (`sma(7)` overlay + `macd(12,26,9)` pane); Breadth/Seasonality/Swing views render on real data — final **0 console errors / 0 warnings**. API spot checks on the real store: breadth 5,200 sessions (1995-07-20 → 2026-10-15; latest universe 326, adv 193 / dec 103 / unch 21); NABIL seasonality January N=15 mean −3.46 % hit rate 40 % (holiday section unavailable-with-reason); swing bench NABIL trend `mixed` → framing `none` (no fabricated invalidation/target), support 530.00 confirmed 2026-09-07, resistance 550.00; scanner presets volume_dryup 130 scanned / 108 passed, pocket_pivot 71/49, accumulation_20d 133/111. Evidence: `docs/evidence/workbench-2026-10-18-{new-indicators,compare,breadth,swing}.png`. Deliverables: `IMPLEMENTATION_STATUS.md`, `INDICATOR_CATALOGUE.md`, `INDICATOR_SOURCE_AND_LICENSE_AUDIT.md`, `CHART_UX_AUDIT.md`, `REMAINING_BLOCKERS.md`, this section.

**Session 2026-10-17c (charting mission) — frontend-only pass, backend untouched.** Full suite re-run unchanged: **2331 passed, 0 failed** (background run with `.venv/bin/python -m pytest tests -q --no-header -p no:cacheprovider`). `ruff check` pass, `ruff format --check` 172 files pass, `node --check web/static/app.js` exit 0 after every edit. Route inventory unchanged (117 routes, all test-referenced). Real-browser verification via `playwright-cli` against dev `127.0.0.1:10000`: drawing rail (19 tools / 8 groups), magnet strong-side numerical snap test (anchor landed exactly on bar 2026-07-16 `high` = 193), eraser + lock refusal, select-mode whole-drawing drag, rectangle/vline/position tools, undo/redo across new tools, per-symbol persistence across reload, indicator catalog add (RSI pane, Bollinger overlays + unit panes) and Remove, persistence across reload — final state **0 console errors / 0 warnings**. Cache-buster `?v=drail2`. Dedicated charting report: `docs/CHARTING_ACCEPTANCE_AUDIT.md`. Evidence: `/tmp/z_drail_*.png`, `/tmp/z_rect.png`, `/tmp/z_panes.png` (session artifacts).

**Last run:** 2026-10-16 (session 21, defect-fix pass) · **2121 passed, 0 failed, 0 errors, 0 skipped** (junitxml) · `main` @ `b6c3659`, 0 staged, 0 stashes · gate unset, production DBs untouched (prod SQLite `mtime` frozen at 10:31:58 across the run), prod PID 26596 never signalled.
*(Session 21 fixes: B-60 fibonacci 200-contract, B-61 Fibonacci overlay never drew, B-62 AND screen false-passed an unavailable metric, B-63 assistant panel could not be closed, B-64 `/api/sources` mislabelled a gated source. +5 tests → 2119 → 2121; `ruff check` pass · `ruff format --check` 221 files · `node --check web/static/app.js` exit 0 · `route_inventory.py` **98 routes (21 mutating, 77 read-only), all test-referenced** · 13/13 views load with **0 console errors/warnings** in a real browser. Evidence: `docs/evidence/session21-fib.png`, `session21-screener-nan.png`, `session21-sources.png`.)*

**Prior run:** 2026-10-16 (session 18, Phase 2–6 implementation) · **2051 passed, 0 failed, 0 errors, 0 skipped** (junitxml) · `main` @ `b6c3659`, 0 staged, 0 stashes · gate unset, production DBs untouched, prod PID 26596 never signalled.
*(+35 tests over the 2016 baseline: 10 candlestick-API + 15 watchlist + 10 experiment. New routes: `GET /api/bars/{symbol}/candles`, watchlists CRUD, experiments save/get/list/compare/reproduce/export → route inventory **88 routes** (71 read-only, 17 mutating), all test-referenced, exit 0. `node --check web/static/app.js` exit 0. Real-browser walkthrough via `playwright-cli` against an isolated dev server on `127.0.0.1:8799` — see "Session 18 browser evidence" below.)*

**Prior run:** 2026-10-15 (session 14, Phase 1 closure) · **1820 passed, 0 failed, 0 errors, 0 skipped** · 28.56 s · exit 0
*(full regression after the index-consumption integration — see "Run 2026-10-15 (session 14)" at the end; supersedes the runs below.)*
**Prior run:** 2026-10-15 · 1805 passed · 0 failed · 0 skipped (benchmark/reliability/deployment phases).
**Gates re-verified 2026-10-15 (final batch + mini-gates, independently re-run):**
`ruff check .` exit 0 · `ruff format --check .` exit 0 (**153 files**) ·
`route_inventory.py` → **69 routes** (57 read-only, 12 mutating), all test-referenced, exit 0 ·
`node --check web/static/app.js` → **exit 0** (the line-1972 SyntaxError was fixed this session) ·
element cross-check → **179 referenced ids, 0 missing from index.html** ·
browser smoke (headless Chromium, `executablePath` fallback to the installed 1243 shell) →
**13/13 checks, 11/11 tabs, 0 console errors** · git → **113 / 0 staged / 0 stashes / `b6c3659`**.
*(Prior gate record kept for history: 2026-10-14 forensic pass — 1322 passed; 57 routes; `smoke_live.py`
last run 2026-10-14 — 44 probed · 44 expected · 0 unexpected, exit 0 — **not** re-run this session;
the new routes were verified by API tests plus direct curl smoke instead.)*

**Historical snapshot — 2026-10-13 run (superseded, kept for the record):** 1105 passed, 0 failed · 48.49 s
**Lint (2026-10-13):** `ruff check .` clean (exit 0) · `ruff format --check .` **exit 1 — one file only**:
`AI Trading Nipsy/MEGA_TOOL_RESEARCH_REPORT.md`, an **untracked owner file** that appeared
after the 1061 baseline. Ruff scans every `.md`, so it picks up code fences inside that
research report. **It was deliberately not reformatted** — reformatting the owner's
untracked document to turn a gate green would be exactly the kind of silent tampering this
project forbids. Every project file formats clean. *(Since resolved by excluding
`AI Trading Nipsy/` from ruff — the report itself was never touched.)*
**Front end (2026-10-13):** `node --check web/static/app.js` clean — `app.js` was later
modified outside this backend mission (mtime 2026-10-14 10:08) and has failed at line 1972 since.
**Inventory (2026-10-13):** `python scripts/route_inventory.py` → 50 routes, all covered, exit 0
**Live smoke (2026-10-13):** `python scripts/smoke_live.py` → 40 probed · 40 expected · 0 unexpected, exit 0

> **Gate history for this session, for the record.** The lint gate was red for
> most of the sprint — 81 errors, then 75, all in the candlestick/summary
> modules delivered by a parallel worker — and the full suite briefly went red
> with 6 failures in `tests/test_summary.py` while that file was still being
> written. Both are reported as they happened in `DECISIONS.md`. They were
> fixed by the owning worker; nothing was skipped, xfailed or excluded to get
> to green.

```bash
cd "/Users/ashim/Downloads/AI trading NEPSE"
.venv/bin/python -m pytest -p no:warnings      # or: uv run pytest
uv run ruff check megatool/ tests/ scripts/
uv run ruff format --check megatool/ tests/ scripts/
node --check web/static/app.js
python scripts/route_inventory.py              # exits non-zero if a route lacks tests
python scripts/smoke_live.py
```

> `addopts` already contains `-q`. Adding another `-q` suppresses the summary
> line and makes it look like no result was printed.

---

## Per-file counts

| File | Tests |
|---|---:|
| `test_indicators.py` | 174 **(+26 RSI, +17 MFI)** |
| `test_candles.py` | 104 **(new)** |
| `test_api.py` | 115 **(+14)** |
| `test_written_transcribe.py` | 57 |
| `test_summary.py` | 72 **(new, +1 MFI cross-check)** |
| `test_fundamentals.py` | 56 |
| `test_written_pdf.py` | 46 |
| `test_audit_a_fixes.py` | 45 |
| `test_financial_integrity.py` | 38 |
| `test_research.py` | 32 |
| `test_backtest.py` | 32 |
| `test_journal.py` | 30 |
| `test_portfolio.py` | 29 |
| `test_forecast.py` | 29 |
| `test_ranking.py` | 27 |
| `test_levels.py` | 24 **(new)** |
| `test_fibonacci.py` | 23 **(new)** |
| `test_floorsheet.py` | 25 |
| `test_walkforward.py` | 23 |
| `test_scanner.py` | 22 **(+1 flat-symbol RSI)** |
| `test_workspace.py` | 24 **(new, +8 for the summary module)** |
| `test_swings.py` | 17 |
| `test_planning.py` | 21 |
| `test_written_reference.py` | 20 |
| `test_market_store_concurrency.py` | 5 **(new)** |
| `test_cli_floor.py` | 9 |
| `test_cli_serve.py` | 3 |
| `test_route_inventory.py` | 3 |
| **Total (28 files)** | **1105** |

### Added this session (796 → 982, +186)

| Test | File | Why |
|---|---|---|
| 23 × Fibonacci | `test_fibonacci.py` **(new)** | Every expected value **computed by hand from the formula**, not by calling the implementation twice: up/down retracement and extension tables, anchor-order mirroring (both tables sum to twice the midpoint), retracements stay inside the move while extensions go beyond, `0.5` labelled `convention` and never `fibonacci`, equal/non-finite/non-positive anchors rejected, custom and empty level sets, index carry-through, determinism, no non-finite output |
| 24 × S/R zones | `test_levels.py` **(new)** | Hand-chosen swing prices so zones are worked out on paper: clustering, separation, `min_touches` excluding a lone pivot while still reporting it, equal prices without dividing by zero, **output independent of input order**, tolerance boundary inclusive, distance/side from latest close, ATR mode and its fallback-and-warn, no `confidence` key anywhere, invalid-parameter rejection, non-finite swing price rejected |
| 16 × workspace | `test_workspace.py` **(new)** | Dated overview that is never called a live price; `change`/`change_percent` recomputed from the last two closes; **`modules` filter leaves unrequested modules honestly `NOT_STARTED`**; a failed module must carry an `error`, be `null` in `result`, and appear in `failed[]`; `overall_state` must reflect module failures; no `confidence`, no `"buy"`/`"sell"` anywhere in the payload; input window and bar bound |
| 5 × store concurrency | `test_market_store_concurrency.py` **(new)** | Regression guard for **B-19**: the locked helpers' contract, a **source guard** asserting no `self.execute(...)` remains outside a lock block, and two 8-thread stress tests asserting both no exception *and* that no key ever has two different answers (a second answer would mean one thread saw another's result) |
| 14 × fibonacci/levels API | `test_api.py` | Both routes: values round-trip through the shared module (the API cannot recompute a different table), 50% family label, caveats contain `CALCULATED`/`not a prediction`/`convention`, S/R zones sorted and not-liquidity disclaimed, `min_touches` default excludes lone pivots, 404/400/422 paths |
| 104 × candlestick library | `test_candles.py` **(new)** | Parallel worker; per-pattern positives, near-miss negatives, reversed directions, zero-range candles, invalid/non-finite OHLC, short history, boundary tolerances |
| 71 × trend/momentum/volatility | `test_summary.py` **(new)** | Parallel worker; net change, combined direction across horizons, hand-computed historical volatility, expanding/contracting regime, divergence detection in both directions including tie-skipping, and a no-lookahead guard asserting `divergence_last_index` never reads future bars |
| 8 × summary through the workspace | `test_workspace.py` | The module completes; **it still reaches the latest stored bar** (regression for a window-narrowing bug that left the summary 5 months stale); SMA 10/30, ROC12, TR-ATR and **textbook Wilder RSI** recomputed independently *inside the test* to 1e-9 — a round-trip check would pass even with a wrong smoothing, since a wrong-but-plausible RSI still lands in 30–70; zone labels agree with the numbers they describe; `macd_histogram == macd − signal`; no `confidence`/`buy`/`sell`; a corrupt bar is excluded with its count **and both window dates** stated; and a forced failure reports `FAILED` with the real message while the other modules still complete |

Progression: 511 (13 files) → 602 → 650 → 707 → 709 → 729 → 731 → 759 → 764 → 766 → 774 → 796 → 982 → 1061 → 1087 → **1105** (28 files).

---

## Undefined-ratio regression tests (2026-10-13, +44)

Two engine defects shared one shape: a ratio whose denominator **and** numerator
are both zero. `0/0` is undefined, but both indicators overwrote the result with
`100` — a confident directional claim produced by nothing happening.

| | RSI (B-23) | MFI (B-24) |
|---|---|---|
| Ratio | `avg_gain / avg_loss` | `positive flow / negative flow` |
| Guard that was missing | `avg_loss == 0` had no `avg_gain > 0` test | `negative == 0` had no `positive > 0` test |
| Reported on flat input | **100** | **100** |
| Now | `NaN` + `insufficient_data` | `NaN` + `insufficient_data` |
| Tests added | 26 (`test_indicators.py` 25, `test_scanner.py` 1) | 18 (`test_indicators.py` 17, `test_summary.py` 1) |

**Both independent references had the same bug** and were corrected, not deleted:
`_naive_wilder_rsi` (`tests/test_indicators.py`) and `_naive_mfi`
(`tests/test_summary.py`) each returned 100 for a 0/0 ratio. Tests now assert the
engine and the reference agree on `NaN` for flat input *and* still agree to 1e-10
on varying input — so the fix cannot hide behind a weakened oracle.

Design points these tests pin deliberately:

* **Neither 0 nor 100 is acceptable** for a flat series — both are directional.
* **100 and 0 remain exact** for purely positive / purely negative flow, proving
  the new guards do not overreach.
* **Wilder's momentum retention through a flat tail is preserved** and pinned as
  *standard* behaviour (RSI stays 100 after a flat tail following a rise), because
  changing it would mean inventing a decay rule.
* **The summary layer is not masking an engine bug.** A test asserts the engine
  itself returns `NaN`, so the consumer-side guard is a fast path, not a cover-up.
* Insufficient history, warm-up NaN, missing/all-NaN/partially-NaN volume, a NaN
  price bar, and scale-independence are each covered.


---

## What the new tests cover

### `test_written_transcribe.py` (57, new) — handwriting reader

Four of these assert against text quoted **verbatim** from the Apple Vision
output of real pages, so they pin the reader's behaviour on the page's own words
rather than on a fixture. No assertion claims an unverified figure is *true* —
only that it is read, refused, or kept as the page and the rules say.

| Area | What is asserted |
|---|---|
| Money parsing | 25 forms Vision actually emits (`38855,07`, `881•06`, `71535-52`, `226359. 28`, `(76,847.01)`); and the forms it must **refuse** — `642.285`, `55,642.285`, `12,34.5678` |
| Thousands split | `88 169.68` is 88169.68, not two tokens (the magnitude floor would otherwise keep the 169.68 fragment) |
| Day pattern | `11 sep - 77609.76 By` keeps its `.76` — lookarounds stop the day pattern eating an amount's tail |
| Net extraction | the figure after the **last** `=`, never the first number on the line; a colon-split `32595: 19` refused rather than joined into 3259519 |
| Labels | an OCR letter is trusted only when spelled A–H; `9Đ` and `91` come back unread instead of being mapped to 9D and 9I; unread labels are assigned by position, measured from the page's first *readable* letter, and marked `position` |
| Provenance | `label_raw` keeps the verbatim reading even when wrong; `unplaced` keeps figures whose column marker OCR could not read |
| Page 21, by eye | all four blocks read, `65550.337` refused, `Paid` note used instead, day numbers excluded, block reconciles |
| Pages 19 & 23, by eye | 8C's 1.00 sell shortfall and 8.03 receipt gap recorded as source facts, 8E's superseded readings kept, 9E/9F close exactly |
| Page 30, by eye | 12D/12E/12F read; un-resolvable red Received/Paid clouds become `None`, never a plausible number; 12D's 0.01 buy gap recorded not closed; 12F's sell components left **empty** rather than filled with a figure that would balance |
| Page 28, by eye | 12A/12B close exactly; **12C does not** — `77793.55 − 68832.46 = 8961.09` vs a written `8963.09`. All three figures stored unchanged, gap reported, no cause assigned, `settled` withheld |
| Inspection ≠ transcription | page 20 is in `VISUALLY_INSPECTED_PAGES` but in no read page — a page that was opened but yielded no record must not be counted as transcribed |
| Uniform record shape | all **15** visually read settlements share one key set (page 21's `net` column was briefly empty when two shapes collided) |

### `test_financial_integrity.py` (37, +2 for the B-17 fix) — Phase 2 of the completion audit

Every expected value in this file is worked out by hand, in comments, from a
fixture written by hand. Nothing asks the module under test for its own
expected value.

| Area | What is asserted |
|---|---|
| Settlement arithmetic | The four page-21 nets verified by ordinary subtraction *before* calling the validator; both sign conventions; an exactly-representable tolerance boundary; and a misread sell figure proven to be caught **without** the buy being "corrected" to balance (B-02) |
| Percentile math | Distinct values → 33.33/66.67/100; ties → average rank; n fully tied → `(n+1)/(2n)×100` (62.5 at n=4, 50.135 at n=369) |
| Ranking scores | A 4-symbol fixture whose scores are computed by hand in the source comment: **71.875 / 63.125 / 54.375 / 45.625**, all reproduced exactly |
| Directionality | Volatility inverted so the calmest symbol ranks best; and the L-06 asymmetry pinned (best scores `100 − 100/n`, never 100) |
| Unavailable factors | P/E, P/B, yield, index-relative and sector-relative absent from both contributions and effective weights |
| Substitution | Substituted value equals the cross-sectional median; symbol disclosed as incomplete; **and scores do move** when the gap symbol is present (L-05) |
| Portfolio ledger | Hand-replayed 4-trade ledger → avg cost 555.50, realized P&L exactly **20,075**, fees counted once per side, oversell refused without mutating the ledger |
| Backtest costs | Round trip hand-computed → fees **398.40**, final equity **99,601.60**, and `initial − final == fees` exactly |
| Backtest timing | `next_open` fills at the bar *after* the signal (entry 40.0, not the signal bar's close of 10.0); `same_close` buys at the signal bar and must be labelled |
| Duplicate trades | Rapid signal toggling → distinct `(entry, exit)` pairs, none duplicated, none ending before they start |
| Market data | Per-row provenance present; `(symbol, date)` unique; **B-17 fixed** — `invalid` rows excluded from `get_bars`/`latest_bars`/`all_closes`, `suspect` kept, `include_invalid` opt-in, and a `low = 0.0` row proven unable to set a symbol's all-time low |

### `test_fundamentals.py` (56, +12) — guard hardening from the audit

`price_as_of` is now required on all three ratios (B-15), so the staleness
check cannot be skipped by omission — including the exact audit reproduction
(2015 EPS into a 2026 price). Field and unit validation (B-14) refuses a
`revenue` record, a `dps` record, or an EPS measured in `shares`/`crore`.
Dividend yield gained staleness and unknown-period checks.

### `test_written_pdf.py` (39, +3) — lakh parser regression (B-13)

11 spellings of `lakh`/`lac`/`L` against hand-written expected values, crore
still winning when both units appear, and plain rupee figures never scaled.

### `test_ranking.py` (27) — multi-factor ranking

Score decomposition (contributions reproduce the score within 4-decimal
rounding), percentile bounds, determinism, weight/`min_bars`/
`max_missing_fraction` validation, missing-factor median substitution,
exclusion with a stated reason, universe accounting
(`ranked + excluded == universe`), `as_of` truncation including the store's
`trading_date` column name, volatility inversion, and JSON serialisation.

### `test_api.py` (+17) — `/api/rank` and `/api/fundamentals/*`

Ordered scores with explanations, unavailable factors at zero weight, "not a
prediction" disclaimer, 400s for bad weights, 404 for unknown symbols, `as_of`
truncation, the nothing-rankable case, CSV import/query/idempotency,
malformed-CSV rejection, and `dry_run` writing nothing.

### `test_walkforward.py` (23, new) — walk-forward validation of the ranking

The honest test of whether the ranking has ever worked: rank at each period end
using only data available then, hold the tails, measure what happened next.

| Area | What is asserted |
|---|---|
| Hand arithmetic | A six-symbol fixture whose flat price segments make every forward return a round number; the expected spreads (0.15, 0.04) and the summary mean (0.095) are written down in the test, not asked of the module |
| No look-ahead | Perturbing every bar *after* a rebalance leaves that period's chosen symbols unchanged; poisoning all later bars with absurd values does the same |
| Speed trim | Trimming each frame to the 250-bar factor window returns **exactly** the same ranking as the full frame, period by period — the optimisation is pinned, not trusted |
| Eligibility gate | A trim narrower than `min_bars` cannot starve the gate, because the effective window is `max(trim_window, min_bars)` |
| Staleness | A carried-forward price is flagged `stale_outcome`, never treated as a fresh trade; the count reaches the summary |
| Chance baseline | Reproducible under a fixed seed; a large consistent spread clears the null; `permutations=0` reports `None` rather than guessing |
| Honesty | Every result carries the survivorship-bias and no-costs caveats, and the chance baseline explains itself in the payload |

---

## Handwriting extraction benchmark (not pytest)

Priority 2 of `MEGA_TOOL_RESEARCH_REPORT.md`. Five pages chosen to cover the
report's stated criteria — p02 printed headers, p11 dense dated table, p18
transactions, p21 rotated settlement, p09 the messiest page.

Ground truth was built by visual transcription at full resolution, with
arithmetic self-checks wherever the page supports them (all four p21
settlements and all five p18 totals reconcile exactly).

```bash
uv run python scripts/score_benchmark.py
```

| Method | Numbers (exact) | Numbers (numeric) | Symbols | Time / page |
|---|---:|---:|---:|---:|
| Tesseract 5.5.0 | 3.3% (3/92) | 4.3% (4/92) | 0/46 | 0.57–1.99 s |
| Apple Vision, fixed orientation | 71.7% (66/92) | 90.2% (83/92) | 33/46 | 0.79–1.73 s |
| **Apple Vision + orientation detection** | **75.0% (69/92)** | **94.6% (87/92)** | **33/46** | 3–8 s |

Orientation detection is what runs in production (`scripts/run_vision_ocr.py`):
each page is scored at 0°/90°/180°/270° and the best is kept. It is the first
pass for all 52 pages — 52/52 succeeded, 0 failed.

Numbers are read far better than exact ones because Vision often misplaces a
separator inside an otherwise correct figure (`12059,43` for 12059.43). That is
why `parse_money` refuses ambiguous shapes instead of guessing: a wrong reading
multiplies a figure by 1000, a refused one costs a review.

Per page (Apple Vision, fixed orientation): p02 88%/97%, p09 81%/100%,
p11 92%/92%, p18 32%/74%, p21 58%/83% → 100% numeric after the page-21 ground
truth was corrected from a visual read (B-02).

`data/written_pdf/benchmark/` holds the ground truth and raw outputs. That
directory is **git-ignored** because the ground truth transcribes the owner's
private handwritten records.

---

## Live verification (real store, not fixtures)

Checked against the running server on `127.0.0.1:8710`:

| Check | Result |
|---|---|
| `/api/health` | 514,018 bars · 372 symbols |
| `/api/rank` on the real universe | 372 requested → 369 ranked, 3 excluded with reasons (CFL 41 bars, CMB 14, SLBBLP 50 — all under `min_bars=60`) |
| Score integrity on real data | 0 of 369 mismatched at 0.01 tolerance; **max deviation 2.0e-4**, median 7.1e-15 — the API rounds contributions to 4 dp, so hand-summation differs in the 4th decimal and never enough to change a displayed value |
| Median substitution flagged | 8 symbols marked incomplete (all `momentum_6m`, 70–119 bars) |
| Median substitution effect | Removing them changes 361/361 scores and 284/361 ranks; max shift 0.61 (L-05) |
| Directionality | Lowest volatility SAHAS 6.79 → percentile 99.7; highest SINDU 125.56 → percentile 0.0 |
| Unavailable factors | `pe_ratio, pb_ratio, dividend_yield, relative_strength, sector_percentile` — 0 contributions, 0 effective weight |
| Schema migration v3 → v4 | `fundamentals` table created, 0 rows |
| Fundamentals dry-run in browser | "Valid: 2 rows — nothing written"; real store still 0 rows |
| Console across all 11 tabs | 0 errors, 0 warnings |

### Real-store data-quality profile (read from a copy, server untouched)

| Check | Value |
|---|---|
| `source` | `github.com/Aabishkar2/nepse-data` for all 514,018 rows; `retrieved_at` 2026-10-12 06:45:04 → 06:50:28 UTC |
| `source_url` null | 0 |
| `validation_status` | valid 500,801 · suspect 13,093 · **invalid 124** |
| `adjustment_status` | `unadjusted` for 100% (no split/bonus adjustment) |
| Flags | 51,700 rows — `open_outside_range` 38,483 · `volume_spike` 11,013 · `high_low_inverted` 109 (+89 combined variants) |
| Symbol mapping | 372 bars ↔ 372 master; 0 orphans either direction |
| `sector` | NULL for **372 of 372** (B-07) |
| NULL OHLC / duplicate dates / future-dated | 0 / 0 / 0 |
| Negative volume | 0 |
| High < low | 115 · close outside `[low, high]` 555 · close ≤ 0 → 6 |

Screenshots: `docs/screenshots/ranking-panel.png`,
`docs/screenshots/fundamentals-tab.png`.
=== SUBSTANTIAL WORK UNIT 3: DOCUMENT VERIFICATION IN TEST_RESULTS ===
--- EXTENDED SESSION (2026-10-13) ---
Workstream A (RSI/MFI): verified B-23/B-24 fixes exist; independent flat-series test confirms NaN (not 100).
Workstream B (Temporal): swing confirmed_index >= index enforced; candle [0..i]; backtest next-bar-open; walk-forward period-end only.
Workstream C (B-21): quality.py:202 adds F_NON_POSITIVE (review severity); 10 zero-price bars flagged SUSPECT; retained in store.
Workstream D (Workspace): 24 test_workspace.py pass; 1 new integration regression added (test_workspace_integration.py: 1 pass).
Files changed: tests/test_workspace_integration.py (new regression); TEST_RESULTS.md (updated).
No source production edits; no data deleted; no commits.

---

## Run 2026-10-14 — backend repair mission

**Command:** `.venv/bin/python -m pytest -p no:warnings tests/`
**Result:** `1176 passed in 16.18s` · exit 0 · **0 failed, 0 skipped**

Baseline for this mission was `1136 collected / 1135 passed / 1 failed`
(the failure was `tests/test_elliott_regression.py::test_candidate_exists`).
The single failure is now fixed and ~40 meaningful tests were added/repaired:

| Suite | Before | After |
|---|---|---|
| `test_elliott_regression.py` | 1 test, **failed**, vacuous (`... or True`) | 8 real tests (candidate construction, to_dict schema, confirmed-swings look-ahead) |
| `test_scanner_quality_filter.py` | 2 vacuous (asserted a local dict literal) | 13 real pipeline tests (dedup, invalid-excluded/suspect-retained, eligibility, determinism, no-look-ahead) |
| `test_overlay_alignment.py` | 1 vacuous (tautology + range check) | 8 backend calendar/date-mapping tests |
| `test_timeframe_elliott_api.py` | — | 13 new API regression tests (weekly/monthly/elliott via `create_app` + isolated store) |
| `test_full_workflow.py` | stray root `test_integration_final.py`, uncollected + broken (ImportError, `find_swings` misuse, `levels_for(df)`, tautologies) | relocated + repaired, 2 real integration tests |

**Live endpoint verification (real data, server restarted to load the new routes):**
`GET /api/bars/NABIL/weekly` → 200, 783 weekly bars (2011-05-09 → 2026-10-05);
`GET /api/bars/NABIL/monthly` → 200, 185 monthly bars (2011-05-01 → 2026-10-01);
`GET /api/bars/NABIL/elliott` → 200, `status=CANDIDATE_ONLY`, 345 confirmed swings, 2 candidates;
unknown symbol → 404; symbol > 10 chars → 400. DB unchanged: 514,018 bars / 372 symbols.

**Lint:** unchanged (`ruff` scope still excludes only `AI Trading Nipsy/`). **Front end:** not touched this phase (`node --check app.js` still reports the pre-existing syntax error — deferred to Phase 2).

**Addendum (same date) — harmonic patterns (§7):** `tests/test_harmonic.py`
added (+20 tests): exact hand-computed XABCD fixtures matching *only* their own
published band set for all five definitions (Gartley/Bat/Butterfly/Crab/Cypher),
schema/uncertainty honesty, confirmed-swings look-ahead, degenerate-leg skip,
NO_MATCH vs INSUFFICIENT_EVIDENCE, documented `slack`, and the
`GET /api/bars/{symbol}/harmonic` contract. **Final suite: 1196 passed, 0
failed.** Route inventory: **54/54 routes test-covered.** Live: `NABIL/harmonic`
→ 200, CANDIDATE_ONLY (341 windows, 2 candidates).

---

## 2026-10-14 — backend features mega-mission (Stages A–K)

**Suite: 1196 → 1307 passed, 0 failed, 0 skipped · 19.35 s · exit 0**
(`.venv/bin/python -m pytest -p no:warnings tests/`). Gates: `ruff check .` exit 0 ·
`ruff format --check .` exit 0 (126 files) · `route_inventory.py` → 57/57 classified
and test-referenced, exit 0. Guardrails: 0 staged · 0 commits · HEAD `b6c3659` ·
frontend, `AI Trading Nipsy/` and `WRITTENdata.pdf` untouched.

| Suite | Delta | What it verifies |
|---|---|---|
| `test_backtest_lifecycle.py` | **+24 (new)** | Hand-computed trade lifecycles: one losing trade, win+loss pair, open-at-end, never-in, missing sessions, 2-bar minimum, NaN/zero-close marking, unfillable fill bar, duplicate dates (B-34), unaffordable sizing, slippage, no-churn exact losses, benchmark returns, no-look-ahead, √500 Sharpe scaling, determinism |
| `test_cost_model.py` | **+11 (new)** | PLACEHOLDER_FEE_RATE label, provenance both-or-neither validation, `cost_status()` verified/placeholder/custom, status-aware assumption text, API runs never "verified" |
| `test_forecast_rolling.py` | **+13 (new)** | Walk-forward `rolling_origin()`: hand-derived per-origin skills (mean model on [1..8] → skills √3.7 and √6.5), perfect-line 100% share with caveat, constant series → UNDETERMINED (not a fake win), naive → BASELINE, strict chronology, **leakage probes** (tampered future data leaves earlier origins bit-identical while later ones move; hold-out perturbation never moves `predicted`) |
| `test_news.py` | **+19 (new)** | News local layer: CSV/JSON parse, alias headers, timestamp normalisation (future/pre-1900 rejected with reasons), missing-title skip, in-file + cross-import dedup (idempotent), symbol association + invalid-token warnings, truncation warning, provenance per item, empty-archive honesty, staleness flag |
| `test_datasources.py` | **+20 (new)** | Adapter contract with **zero network** (any HTTP attempt fails the test): local-file aliases (incl. LTP, B-39), GitHub-dataset normalise/dedup/status-drop, fresh-cache and symbol-index offline paths, degraded local-CSV fallback, official-API refusal without credentials (B-09), token never leaks into `describe()`/`health()` |
| `test_ingest.py` | **+9 (new)** | First-ever ingestion coverage: provenance stamping, per-symbol failure isolation, progress callback, idempotent re-ingest, **security master contains only succeeded symbols (B-37)**, **zero-row runs log `failed` not `success` (B-38)**, local-CSV round trip |
| `test_api.py` | +8 | `POST /api/forecast/rolling` (round trip, 404/400/422), `POST /api/news/import` + `GET /api/news/summary` (round trip, empty-archive honesty, bad payload), dashboard B-10 honesty pinned (no index key; "no index value is shown"), `/api/strategies` `fee_rate_status`, backtest `cost_model` block |
| `test_floorsheet.py` | +4 | Symbol upper-casing + broker trimming, fractional-quantity warning, overflow skip, scientific-notation mangling (B-36) |
| `test_portfolio.py` | +3 | Zero close never marks to zero (B-35), zero-vs-missing flags are distinct, negative close never a mark |
| `test_backtest.py` | edit | `return_pct`/`avg_trade_pct` now asserted as **percent** (B-32 contract change, justified in-file) |

**Defects found and fixed:** B-32, B-33, B-34 (backtest), B-35 (portfolio),
B-36 (floor-sheet parser), B-37, B-38 (ingestion), B-39 (LTP alias +
false docstring). B-31 merged into B-11 (duplicate number for one limitation).
One test failure during development was the author's own hand-arithmetic slip
(mean of [1,2,3,4] is 2.5, not 3) — engine correct, expectation corrected.

**Not verified by this run (unchanged honesty):** backtest on live data
(structural + fixture only), forecasting on real out-of-sample data,
portfolio on real ledgers, floor-sheet with real records (0), news with a
real source (none exists), anything browser-side (Phase 2).

---

## Run 2026-10-14 — forensic verification pass

An independent verification pass re-inspected the actual source, tests and
diffs of the backend-features mission rather than trusting its report. It
re-established the baseline, re-verified every fixed defect (B-32…B-39) with
new independent tests, hunted for residual defects in the same code paths,
and re-ran all gates.

**Result:** `1322 passed, 0 failed, 0 skipped` in 19.93 s · exit 0
(command: `.venv/bin/python -m pytest -o addopts= -p no:warnings tests/`).
Baseline at pass start: 1307 passed / 0 failed / 0 skipped, exit 0
(`.venv/bin/python -m pytest -o addopts= -p no:warnings tests/`). Delta
**+15** net new tests (1307 → 1322); a temporary +16 became +15 because one
stray assertion was corrected to its hand-derived value.

**Gates:** `ruff check .` exit 0 · `ruff format --check .` exit 0 (126 files) ·
route inventory unchanged at **57 routes**, all classified and test-covered.

### New / strengthened tests this pass (+15)
| Suite | Δ | What it establishes |
|---|---|---|
| `test_backtest_lifecycle.py` | +6 | **B-32 pipeline consistency:** one winning round trip, every layer hand-agreed (trade `return_pct` = pnl/cost-basis ×100, equity `total_return_pct`, `realized_pnl` == equity change, `avg_trade_pct`, `win_rate_pct`). **B-34 hardening:** mixed date representations of one session rejected as duplicates; unparseable dates fail loudly; two securities sharing dates are not collapsed. |
| `test_api.py` | +3 | **B-32 at the API layer:** the same run computed via HTTP and via a direct engine call on identical bars must be *identical* (`metrics` and `trades` equal — a serialization layer that rescaled percent↔fraction would fail). **B-35 at the API layer:** an unusable mark serializes as JSON `null`, never `Infinity`/`NaN` tokens. **Rolling-origin leak probe through the HTTP route** (not just the function). |
| `test_portfolio.py` | +3 | **B-35 hardening:** NaN, +inf and −inf closes each leave the position unvalued with a finite summary (a bare `>0` guard let `+inf` through). |
| `test_floorsheet.py` | +2 | **B-36 taxonomy:** direct `_to_float` test over every input class (ints, decimals, negatives, separators, currency, NaN, ±inf, overflow `3e308`, malformed). **B-40:** scientific-notation-with-currency (`"1e5 USD"`, `"Rs 1e5"`) is skipped, never stripped to 15. |
| `test_ingest.py` | +1 | **B-37/38 malformed-response path:** a frame missing `trading_date` is counted as a failed symbol (not a crash), the good symbol still stores, the security master claims only the good symbol, and the log reads `partial`. |
| `test_news.py` | +1 | **v5→v6 migration:** a database rolled back to a pre-news shape (tables dropped, version stamped 5) regains `news_items`/`news_item_symbols` on `init_app_db` and reports version 6. |

### Defects found and fixed this pass
- **B-40** (`floorsheet._to_float`): a scientific-notation value carrying a
  currency sign (`"1e5 USD"`, `"Rs 1e5"`, `"1,000e2"`) escaped the B-36
  verbatim-parse fix through the character-stripping fallback, which deleted
  the `e` — `"1e5 USD"` became **15.0**. The fallback now rejects any string
  still containing `e`/`E` after currency stripping (row skipped with a
  reason); pure scientific notation still parses verbatim.
- **B-34 hardened:** `run_backtest` now normalizes `trading_date` with
  `pd.to_datetime(format="mixed")` before sorting/duplicate detection, so
  mixed representations of one session are caught and unparseable dates fail
  loudly (previously only same-type duplicates were caught).
- **B-35 hardened:** `value_portfolio`'s mark guard upgraded from a bare NaN
  test to `math.isfinite(close) and close > 0`, closing the `+inf` hole that
  would have poisoned totals and JSON.
- One pre-existing stray assertion in `test_floorsheet.py`
  (`amount == 50_000_000`) was corrected to its hand-derived value (`50_000`
  = 100 × 500).

### Verification verdicts (this pass)
- **B-32 (returns units):** TESTED-PASS. `*_pct` fields are percent end-to-end
  (engine → metrics → API JSON), proven by hand-derived single-trade
  arithmetic and by exact API/engine equality. `max_drawdown_pct`/`win_rate_pct`
  also percent; internal `sharpe` is unitless.
- **B-33 (invalid-close equity marking):** TESTED-PASS (retained from prior
  run's lifecycle suite; re-run green). Equity marks at last usable close,
  `stale_marks` counted, never collapses to cash.
- **B-34 (duplicate dates):** TESTED-PASS, now including mixed
  representations and unparseable dates.
- **B-35 (portfolio non-positive marks):** TESTED-PASS, now including NaN and
  ±inf, plus API JSON-serialization (nulls, no Infinity).
- **B-36 (`_to_float`):** TESTED-PASS over the full taxonomy; residual B-40
  found and fixed.
- **B-37 (security master):** TESTED-PASS — only delivered symbols registered,
  including the malformed-response path.
- **B-38 (ingest log status):** TESTED-PASS — success ⇒ ≥1 succeeded ∧ 0
  failed; partial/failed reported honestly, including zero-row and
  list-failure paths.
- **B-39 (LTP alias / adapter):** TESTED-PASS — `ltp`→`close` mapping verified
  on a controlled fixture; official adapter refuses without credentials and
  never leaks the token; no filename-based symbol guessing.
- **Rolling-origin forecasting:** TESTED-PASS at **function and API** level;
  leakage probes re-run (earlier origin bit-identical under tail tampering,
  later origin moves). **Out-of-sample NEPSE predictive performance remains
  NOT-TESTED** — no genuine historical out-of-sample set is wired in.
- **Cost model:** TESTED-PASS — placeholder/custom/verified statuses pinned;
  API runs can never be `verified` (no provenance fields in the request);
  fees charged **exactly once per side** (hand-computed equity gap == fees).
- **News schema v6:** TESTED-PASS — migration from a v5 shape verified,
  idempotent re-import, dedup, per-row skip reasons, empty-archive honesty,
  "no live source" language pinned. No live source exists (L4/T-15 open).

## Run 2026-10-14 — Phase 1 blocker code-readiness (D1, T-11, T-12, B-10)

Command: `.venv/bin/python -m pytest -o addopts= -p no:warnings tests/` →
**1389 passed, 0 failed, 0 skipped, exit 0** (was 1322; **+67** new tests).
`ruff check .` → 0. `ruff format --check .` → 0 (132 files).
`scripts/route_inventory.py` → exit 0 (57 routes, every route test-referenced).

### New / strengthened tests this pass (+67)
- `test_llm.py` (26) — provider abstraction (D1): unconfigured refuses with **no
  request** (a `MockTransport` handler that raises proves it); clean ollama vs
  openrouter selection; connection-refused/timeout → `LLMUnavailable`; HTTP/JSON
  errors → `LLMRequestError`; **key never in a result, exception or status**
  (presence + length only, `[redacted]` on an echoed 401); local mode works with
  no hosted credential; unknown provider errors instead of silently disabling.
- `test_sectors.py` (15) — sector loader (T-11): required-column refusal, empty
  file, BOM/whitespace normalisation, empty sector, **conflicting sector →
  ambiguous (no winner picked)**, unknown symbol reported and **never created**,
  name/`delisted` **not clobbered**, source required, idempotent.
- `test_index_series.py` (16) — index loader (B-10): required columns, unparseable
  date, non-numeric/non-finite/non-positive close, **duplicate date rejected**,
  chronological span, **any bad point aborts the whole import (nothing written)**,
  provenance required, idempotent.
- `test_cost_model.py` (+10 → 22) — fee schedule (T-12): the four register
  components exist with **rate=None** (nothing fabricated), placeholder is the
  only shipped schedule, unknown name errors, half-provenance rejected, a missing
  component rejected, full-provenance+known-rates → `verified`, partial → `partial`,
  `fee_uncertainty()` states exactly what is unknown, default aggregate rate and
  `cost_status` **unchanged**.

### Live end-to-end D1 verification (local Ollama, free, no private data)
`MEGATOOL_AI_PROVIDER=ollama MEGATOOL_AI_MODEL=llama3.2 megatool ai ping "…pong" --max-tokens 8`
→ `[ollama / llama3.2] 5.65s / Pong / tokens: 32 in 3 out / exit 0`.
Full path exercised: config → `get_provider()` → `OllamaProvider` → httpx →
localhost:11434 → parse → `LLMResult` → CLI. **D1 local mode: IMPLEMENTED +
TESTED-PASS (integration verified).** The same CLI refuses with exit 1 and makes
no request when no provider is configured.

### Blocker status after this pass (unchanged where data/permission-bound)
- **D1 (Ollama app integration): RESOLVED for local mode** — provider interface,
  config, timeouts, error handling, mock-server tests, and a real local ping all
  present. Hosted (OpenRouter) mode is **code-complete but NOT TESTED live** (no
  key present; none requested).
- **T-11 / T-12 / B-10: code-readiness implemented** — validated loaders/structure
  ready; **data still BLOCKED** on the owner's authoritative sector CSV, verified
  fee/tax rates, and published index series respectively. No data invented.
- **B-09, T-13, T-15, L4: remain BLOCKED** (external auth / real floor sheet /
  licensing / live source). Documented, not claimed resolved.

## Run 2026-10-14 — T-M1: eligibility plumbing + upsert safety

All commands run from the project root; every count below is from a run in this
session, exit codes captured (`set -o pipefail`).

| Command | Exit | Result |
|---|---|---|
| `pytest -o addopts= -p no:warnings tests/test_security_metadata.py tests/test_sectors.py -q` | 0 | 42 passed |
| focused battery: `test_security_metadata.py test_sectors.py test_scanner.py test_ranking.py test_ingest.py test_market_store_concurrency.py test_api.py` | 0 | **237 passed** |
| full suite `pytest -o addopts= -p no:warnings tests/ -q` | 0 | **1421 passed** (was 1389; +32 new T-M1 tests) |
| `ruff check .` | 0 | All checks passed! |
| `ruff format --check .` | 0 | 136 files already formatted (134 prior + `FORENSIC_CLOSURE_REPORT.md` + `test_security_metadata.py`) |

Two intermediate red runs are recorded honestly: the first focused run failed
3/42 (single-statement COALESCE design could not preserve on omission — bound
`False` still overwrote; replaced with two statement shapes), and one API test
failed once (assertion contradicted the unknown-metadata policy). Both were
fixed and re-verified; no production data was involved at any point.
Production DuckDB mtime unchanged: `2026-10-12 12:35:29`. Staged index: empty.

## Run 2026-10-14 — T-M2: dry-run security-metadata import harness

All commands run from the project root; exit codes captured. The full suite was
**not rerun** (explicit instruction: the change is additive — a new module, a
new CLI subcommand, a new test file — and T-M1's 1421-run result stands).

| Command | Exit | Result |
|---|---|---|
| `pytest -o addopts= -p no:warnings tests/test_metadata_dryrun.py -q` | 0 | **22 passed** (focused battery) |
| `pytest -o addopts= -p no:warnings tests/test_cli_floor.py tests/test_cli_serve.py tests/test_written_pdf.py -q` | 0 | **58 passed** (CLI-adjacent, since `cli.py` gained a subparser) |
| `ruff check .` | 0 | All checks passed! |
| `ruff format --check .` | 0 | 138 files already formatted (136 prior + `metadata_dryrun.py` + `test_metadata_dryrun.py`) |
| full suite `pytest … tests/ -q` | — | **NOT-TESTED this session** (no reason to repeat T-M1's successful 1421-run) |

One intermediate red run is recorded honestly: the first focused run failed
1/22 — `MarketStore` connects lazily, so the missing-database `IOException`
escaped `main()` as a traceback instead of the intended clean message (test
`test_cli_reports_locked_or_missing_database_honestly`). Fixed by forcing a
probe query at open time inside the CLI handler; re-verified green.

Additional manual verifications (not pytest):

- **Real-artifact integration**: `megatool metadata dry-run --input
  data/review/securities_review_UNVERIFIED.csv --db <fixture> --out-dir <temp>`
  → exit 0, 465 records examined, **0 rejected**, `source_category` reported as
  ignored, 464 additions + 1 conflict (NABIL, stored vs proposed sector), all
  465 flagged for manual review (status has no stored counterpart — B-2), 0
  values invented. Fixture store and outputs were in temp dirs only.
- **Overwrite refusal**: second identical run → exit 1,
  `refusing to overwrite …`.
- **Safety**: production DuckDB mtime unchanged `2026-10-12 12:35:29`;
  `data/review/` contains no new files (default `dry_run/` dir never created —
  all session runs used temp out-dirs); staged index 0; stashes 0.

## Run 2026-10-14 — T-M3: data-driven `sector_percentile`

| Command | Exit | Result |
|---|---|---|
| `pytest -o addopts= -p no:warnings tests/test_sector_factor.py -q` | 0 | **13 passed** (new focused file) |
| `pytest … tests/test_ranking.py tests/test_financial_integrity.py tests/test_walkforward.py -q` | 0 | **88 passed** (all `rank_universe` callers; 2 existing assertions updated to the computed-availability shape) |
| `pytest … tests/test_api.py -q -k rank` | 0 | **13 passed** (rank route now passes stored sectors; emits computed `unavailable`) |
| `ruff check <changed files>` | 0 | All checks passed! |
| `ruff format --check <changed files>` | 0 | already formatted |

Two honest intermediate red runs are recorded: 1/13 failed because
`build_factor_specs` emitted the sector spec twice (once via `PRICE_FACTORS`,
once via the status branch — score doubled to 200; fixed by excluding the key
from the static comprehension), and 1 existing test failed because
`sector_percentile` deliberately carries zero default weight (test updated to
pin that exception). Full suite **not rerun** — the change's blast radius
(ranking.py + its three test files + the rank route) is fully covered above.
Production DB untouched; no imports; nothing staged.

## Run 2026-10-14 — A2 + A3: B-3 evidence addendum; fee-model shape extension

| Command | Exit | Result |
|---|---|---|
| `pytest -o addopts= -p no:warnings tests/test_cost_model.py tests/test_backtest.py -q` | 0 | **60 passed** (28 cost model incl. 6 new shape tests + 32 backtest) |
| `ruff check megatool/backtest.py tests/test_cost_model.py` | 0 | All checks passed! |
| `ruff format --check megatool/backtest.py tests/test_cost_model.py` | 0 | already formatted |

A2 was documentation-only (addendum to `data/review/UNIVERSE_RECONCILIATION.md`).
A3 added structure with **zero rates**: tiered components (`FeeTier`),
gain-aware `applies_to`, placeholder CGT shape — the engine's cost application
is untouched and still placeholder-labelled. No production data touched;
nothing staged.

## Run 2026-10-15 — B-batch validations + Phase 2 features (F1/F3/F4/F5/F6/F8/F9/F10/F11/F12)

Baseline before new work: `pytest tests/test_sector_factor.py tests/test_ranking.py
tests/test_cost_model.py -q` → **68 passed**.

B-batch read-only dataset validations (B1–B4) were ad-hoc read-only scripts
(no production writes, no imports); results and methods are recorded in
**`data/review/DATASET_VALIDATION_2026-10-15.md`** (B1: 0/120 close mismatches
vs production; B2: 46,659 rows through the app's own `parse_floorsheet`, 0
qty×rate violations in first 200; B3: `read_index_csv` accepts 400/400 points;
B4: all 7 B-3 files exist, NLO thin with 3 rows).

| Command | Exit | Result |
|---|---|---|
| `pytest … tests/test_regime.py -q` | 0 | **13 passed** (new — F8 regime; incl. no-look-ahead pin, warmup) |
| `pytest … tests/test_alerts.py -q` | 0 | **10 passed** (new — F9 alerts; dedup/re-arm/refusals) |
| `pytest … tests/test_risk.py -q` | 0 | **7 passed** (new — F6 portfolio risk; drawdown/VaR/insufficient) |
| `pytest … tests/test_fundamentals.py -q` | 0 | **61 passed** (55 existing + 6 new — F10 ratio/compare routes) |
| `pytest … tests/test_agent.py -q` | 0 | **17 passed** (new — F12 routing/tool statuses + F1 AI-interpretation privacy) |
| `pytest … tests/test_research.py tests/test_route_inventory.py tests/test_llm.py -q` | 0 | **61 passed** (neighbors of the research-route changes) |
| `pytest … tests/test_news.py -q` | 0 | **25 passed** (19 existing + 6 new — F4 categorisation/relevance/repeated coverage) |
| `pytest … tests/test_journal.py tests/test_route_inventory.py -q` | 0 | **38 passed** (F5 reflect: no-call default, authorized stub, route) |
| `pytest … tests/test_floorsheet.py tests/test_route_inventory.py -q` | 0 | **40 passed** (F3 trend: hand-computed activity/flow, route) |
| `pytest … tests/test_planning.py -q` | 0 | **33 passed** (16 existing + 17 new — F11 constraint check, route) |
| `pytest … tests/test_api.py tests/test_route_inventory.py tests/test_portfolio.py -q` | 1 then 0 | **169 passed, 1 failed** — `test_research_topics_endpoint` pinned the old stale wording; assertion updated to the corrected text (+ `ai_status` presence), 2-test rerun → **2 passed** |
| `ruff check .` / `ruff format --check .` | 0 | **All checks passed; 151 files already formatted** |
| `pytest … tests/ -q` (end-of-session checkpoint, after all changes) | 0 | **1542 passed, 0 failed in 24.22s** |

Honest intermediate reds, each fixed before moving on: (1) news summary
repeated-coverage query missing its `params` binding + `eps` keyword firing
inside "nepse" (word-boundary fix) + one wording assert — 3 failed → 25
passed; (2) trend-route test expected 400 for `sessions=1`, FastAPI returns
422 — assertion corrected; (3) journal reflect recipient wording "AI call" vs
"model call" — assertion corrected; (4) the `test_api` stale-wording failure
above (the endpoint text claiming "no LLM key exists in this project" had
become false once providers were implemented — endpoint fixed, test updated).

Full suite not rerun between features (per instruction: smallest relevant
group per change); run once at the end-of-session checkpoint above.
Production DB untouched; no imports; nothing staged.

---

## Run 2026-10-15 (session 2) — app.js repair, frontend integration, B-1 evaluation, C3 research, final verification

Focused runs per change during the session, then one end-of-session checkpoint:

| Command | Exit | Result |
|---|---|---|
| `node --check web/static/app.js` | 0 | **clean** — after the orphan-fragment removal, re-verified after every later edit (twice more in the final batch) |
| `pytest … tests/test_regime.py -q` | 0 | **14 passed** — 13 existing + new `test_dates_come_from_trading_date_column_not_row_positions` (B-43 production-shape fix); `ruff check` + `ruff format --check` clean on the changed files |
| element cross-check (`node /tmp/id_check.js`) | 0 | **179 referenced ids, 0 missing** from `index.html` |
| browser smoke (Playwright, headless; `executablePath` fallback → installed `chromium_headless_shell-1243`, no install) | 0 | **13/13 checks PASS, 11/11 tabs, 0 console errors.** Ratio card: labels `P/E`, `P/B`, `Dividend yield %` present with honest reasons verbatim (`— no eps record stored for NABIL`, …); `NABIL,ADBL` compare renders both symbols; Risk card shows the limits + `no open positions`; Journal Reflect card present, **0** Reflect buttons clicked (empty journal), AI checkbox unchecked; no Import/Record/Delete/Clear/Evaluate clicked |
| endpoint smoke (curl) | — | Correct routes all **200**: `/api/regime`, `/api/alerts/history`, `/api/fundamentals/NABIL/ratios`, `/api/fundamentals/compare?symbols=NABIL,ADBL`, `/api/floorsheet/trend`, `/api/portfolio/risk`, `/api/securities?limit=1`, `/api/agent/tools`, `POST /api/agent/run`, `/api/bars/NABIL/levels`, `/api/bars/NABIL/fibonacci`. Three **404s were task-spec errors in the probe list, not product defects** (the real paths are the ones above, each verified 200). Observation (pre-existing, not this session's change): `/api/fundamentals/ratios?symbol=NABIL` matches `/api/fundamentals/{symbol}` and returns 200-empty for the "unknown symbol" `ratios` rather than 404 |
| `GET /api/regime` | 200 | `last_date` = **`2026-10-09`** — a real date (B-43 fix holds) and **exactly the store's coverage `last_date`** (`/api/status`: `data_as_of 2026-10-09`, last ingestion 2026-10-12 06:50). *Record correction:* an earlier session note quoted `2026-10-14`; the store's newest bar is `2026-10-09`, so `2026-10-09` is the correct, consistent value and the earlier note was wrong |
| `POST /api/alerts/evaluate {"conditions":[]}` | 400 | Rejected by pre-validation (`conditions must be a non-empty list`) — inspected source first to confirm no write path is reached; `GET /api/alerts/history` unchanged (`alerts: []`). No alert was ever evaluated or cleared |
| `pytest … tests/test_cost_model.py -q` | 0 | **28 passed** — fee structure untouched by C3 at this checkpoint (no preset modified); superseded by the C3 follow-up below (**34 passed**) |
| `pytest … tests/ -q` (end-of-session checkpoint) | 0 | **1543 passed, 0 failed in 23.76 s** (repeat run 23.86 s) |
| `ruff check .` | 1 → 0 | Initially **6 errors, all in this session's own untracked scratch** `data/review/dry_run_2026-10-15/sector_map_analysis.py` (F401 `sys`, UP015 ×3, B905 ×2) — fixed in that file only (plus one `ruff format` on it) → **`All checks passed!`**; source dirs were green throughout (`ruff check megatool tests web` → `All checks passed!`) |
| `ruff format --check .` | 0 | **153 files already formatted** (152 + the scratch file after formatting) |
| `scripts/route_inventory.py` | 0 | **69 routes** (was 57 on 2026-10-14; +12 Phase-2 routes), `by status: TEST=69`, every route referenced by ≥1 test |
| git safety | — | `git status --porcelain` **113** · staged **0** · stashes **0** · HEAD **`b6c36595d20d6a32f55b4bc2538067434c6886ec`** — unchanged all session; nothing staged/committed/pushed |

Honest reds and how they resolved: (1) browser smoke first surfaced
`r.map is not a function` in `renderRatioReport` — fixed (rows are arrays of
cells; label column restored), then re-verified green; (2) `ruff check .` red
on the session's own scratch script — fixed in that file, not excluded via
config; (3) three probe URLs in the verification task-spec pointed at routes
that never existed under those names — the real routes were then curl-verified
200 (spec error, not app error); (4) the `last_date` expectation of
`2026-10-14` was wrong — the store ends `2026-10-09` and the API agrees with
it exactly (record corrected above rather than the data being "fixed").

Server: uvicorn PID 71149 throughout (documented restart procedure used twice
earlier in the session, before these runs). Production DuckDB untouched.

### C3 follow-up (same date, after the CGT verdict landed) — focused fee-model change only

The Finance Act 2083 / IRD research returned **OFFICIALLY CONFIRMED** (enacted
आर्थिक ऐन, २०८३ धारा 57 उप-बिन्दु (२१)(क) amending ITA §95क(2)(क): listed-shares
CGT 7.5% >365d / 10% ≤365d for natural persons, effective साउन १, २०८३ =
FY 2083/84; quotes independently spot-verified against the machine-read
extracts `/tmp/economic_act_2083.txt:13221-13222` and
`/tmp/ird_income_tax_act.txt:4229-4232`). Change made: opt-in named schedule
`official-2083-84` added to `FEE_SCHEDULES` (`megatool/backtest.py`) with all
four components + provenance; default `PLACEHOLDER_FEE_RATE` and
`BacktestConfig` untouched; one existing test updated (its
`set(FEE_SCHEDULES) == {"placeholder"}` assertion encoded the blocked state);
6 tests added pinning the official numbers. Full suite deliberately **not**
repeated (owner instruction); no route/API/behaviour changed by this diff.

| Command | Exit | Result |
|---|---|---|
| `pytest -o addopts= -p no:warnings tests/test_cost_model.py -q` | 0 | **34 passed in 0.73 s** (28 existing incl. 1 updated + 6 new C3 pinning tests) |
| `ruff check megatool/backtest.py tests/test_cost_model.py` | 0 | `All checks passed!` |
| `ruff format --check megatool/backtest.py tests/test_cost_model.py` | 0 | `2 files already formatted` |

## Run 2026-10-15 (session 3) — C3/D-y: verified-schedule engine adoption

Focused batteries only, per the owner's instruction (the 1543-test full suite was NOT rerun; it ran
before this change and the default path is preserved untouched — every suite that pins backtest
behaviour was run instead):

| Command | Exit | Result |
|---|---|---|
| `pytest … tests/test_backtest.py tests/test_cost_model.py tests/test_planning.py -q` | 0 | **121 passed** — incl. the new C3/D-y section: tier boundaries at every slab edge (both sides), pre-revision table before 2024-05-14, NPR 10 minimum, SEBON both sides / DP sell only, 2dp rounding, full gross−costs−tax−net reconciliation (996 units @100.00 → 110.03: gross 9,989.88, costs 746.71, taxable gain 9,243.17, tax 693.24, net 8,549.93), >365d 7.5% vs ≤365d 10%, pre-amendment era 7.5%, loss never taxed (−752.08 gain, tax 0.0), cgt-not-declared → `None` + reason + warning, benchmark priced with the same model, config-validation refusals, flat-fee regression (same numbers + disclosure only) |
| `pytest … tests/test_api.py -q` | 0 | **138 passed** — incl. new: `POST /api/backtest` with `fee_schedule` → `cost_model.status="verified"`, schedule embedded, tax `None`+warning without a declaration; declared category → computed outcomes; unknown schedule → 400; cgt without schedule → 400; legacy custom `fee_rate` still 200/"custom"; `POST /api/planning` gains `cost_estimate` (same engine); `/api/strategies` discloses the opt-in keys and both schedules |
| `pytest … tests/test_backtest_lifecycle.py tests/test_financial_integrity.py -q` | 0 | **66 passed** — the other suites that pin backtest behaviour: unchanged |
| first focused run | 1 | **4 red, all in my own new hand-computed expectations** (engine verified correct each time): 99,600 sits in the >50k–5L slab (0.37% pre-revision, not 0.40%); a flat-price trade's gross is 0.0 (loss comes from costs); flat-mode reconciliation holds to ±0.01 (unrounded engine fees vs 2dp disclosure — schedule mode is exact by construction); Rs 0.015 sebon is a binary half-paisa case → test moved to exact-2dp values. All four fixed in the tests; no engine change needed |
| straddle discovery | — | the 2024-05-13 buy / 2024-05-15 sell fixture proved effectiveness is honored **per side** (buy pre-revision, sell current) and the warning counts exactly 1 side — kept as the regression for it |
| `ruff check` (7 changed files) | 1 → 0 | 2 findings in new code (import order in `planning.py`, unused import in `test_backtest.py`) — fixed → `All checks passed!` |
| `ruff format` (7 changed files) | 0 | 3 files reformatted, then `--check` clean |
| live server (documented restart procedure) | — | `GET /api/strategies`: defaults `fee_schedule: None`, `cgt: None`, `available: ['official-2083-84', 'placeholder']`. `POST /api/backtest` NABIL + schedule + declared category on real stored bars: `status: verified`, pre-revision buy side detected + warned, position open at end → **0 closed trades → `capital_gains_tax_paid: None`** (honest: no computed tax, not zero) |

Total across the focused + integration batteries: **325 passed, 0 failed**. Production DuckDB untouched;
no metadata imported; no records rewritten (historical flat-fee results keep their provenance —
recalculation under the schedule means re-running, which is opt-in per request).

## Run 2026-10-15 (session 4) — full regression validation after C3/D-y

Full backend suite rerun to close the validation gap left by session 3's focused-only approach.
No code changed; no tests modified; no production data touched.

| Command | Exit | Result |
|---|---|---|
| `.venv/bin/python -m pytest -p no:warnings tests/` | 0 | **1578 passed, 0 failed, 0 skipped in 29.12 s** |
| C3/D-y focused subset (`test_backtest.py`, `test_cost_model.py`, `test_planning.py`, `test_api.py`; `-k` filter for schedule/cgt/commission/sebon/dp/gross/tax/entry_cost/fee_schedule/official/pre_revision/capital_gains) | 0 | **47 passed, 212 deselected in 2.28 s** |
| `git status --short` / `git diff --cached` / `git stash list` | — | **113 / 0 / 0** — unchanged; the test run did not modify the working tree |

**Interpretation:** the C3/D-y engine adoption (session 3) introduced no regressions outside the
already-green focused batteries. The full-suite count rose from **1543** to **1578** (+35), matching
the new tests added for the verified schedule. The previous session's recommendation to rerun the
full suite at the next checkpoint is now satisfied.

## Run 2026-10-15 (session 5) — R5 / B-4: merged-security semantics

Focused batteries for the owner ruling on `merged → delisted/status`. The full 1578-test suite was
**not** rerun per instruction; only the tests directly affected by the R5 code changes were executed.
No production data was touched; tests used isolated `tmp_path` databases.

| Command | Exit | Result |
|---|---|---|
| `.venv/bin/python -m pytest -p no:warnings tests/test_security_metadata.py tests/test_metadata_dryrun.py -q` | 0 | **passed** — R5 upsert, reader, eligibility, scanner, dry-run, successor-symbol scenarios |
| `.venv/bin/python -m pytest -p no:warnings tests/test_api.py::test_screen_route_default_excludes_non_tradable_and_includes_unknown tests/test_api.py::test_screen_route_can_disable_filter_to_include_inactive tests/test_api.py::test_rank_route_default_excludes_non_tradable_and_includes_unknown tests/test_api.py::test_rank_route_opt_in_filter_same_as_default_now tests/test_api.py::test_rank_route_instrument_filter_and_full_exclusion_400 -q` | 0 | **passed** — API eligibility defaults |
| `.venv/bin/python -m pytest -p no:warnings tests/test_scanner.py tests/test_scanner_quality_filter.py tests/test_ranking.py tests/test_sectors.py -q` | 0 | **passed** — no regressions in scanner/ranking/sector consumers |
| `.venv/bin/ruff check megatool/market_store.py megatool/scanner.py megatool/api.py megatool/metadata_dryrun.py tests/test_security_metadata.py tests/test_metadata_dryrun.py tests/test_api.py` | 0 | `All checks passed!` |
| `.venv/bin/ruff format --check megatool/market_store.py megatool/scanner.py megatool/api.py megatool/metadata_dryrun.py tests/test_security_metadata.py tests/test_metadata_dryrun.py tests/test_api.py` | 0 | `7 files already formatted` |
| `git status --short` / `git diff --cached` / `git stash list` | — | **113 / 0 / 0** — production DB untouched; server not restarted |

**Interpretation:** R5 / B-4 implemented and verified. The new `security_master.status` and
`successor_symbol` columns, the default inactive-status exclusion in scanner/rank, and the updated
T-M2 dry-run reconciliation all behave as specified. The full-suite baseline remains 1578 passed
(session 4) and will need a rerun only at the next natural checkpoint after R1 or another broad
change.

---

## Run 2026-10-15 (session 6) — sector provenance in the loader

Focused battery for the sector-loader honesty improvement. The full 1578-test suite was **not**
rerun per instruction; only tests directly affected by the R6 schema and loader changes were
executed. No production data was touched; tests used isolated `tmp_path` databases.

| Command | Exit | Result |
|---|---|---|
| `.venv/bin/python -m pytest -p no:warnings tests/test_sectors.py tests/test_security_metadata.py -q` | 0 | **59 passed** — sector loader provenance storage and `securities_meta()` exposure |
| `.venv/bin/python -m pytest -p no:warnings tests/test_metadata_dryrun.py tests/test_api.py tests/test_scanner.py tests/test_ranking.py tests/test_sector_factor.py -q` | 0 | **223 passed** — no regressions in metadata dry-run, API, scanner, ranking or sector factor |
| `.venv/bin/ruff check megatool/market_store.py megatool/sectors.py tests/test_sectors.py tests/test_security_metadata.py` | 0 | `All checks passed!` |
| `.venv/bin/ruff format --check megatool/market_store.py megatool/sectors.py tests/test_sectors.py tests/test_security_metadata.py` | 0 | `4 files already formatted` |
| `git status --short` / `git diff --cached` / `git stash list` | — | working tree modified, **0 staged / 0 stashes** — production DB untouched; server not restarted |

**Interpretation:** Sector provenance is implemented and verified. Every future sector import
will carry stored, queryable source/retrieved/observed metadata, preventing unverified mappings
from appearing authoritative. The full-suite baseline remains 1578 passed (session 4) and should
be rerun only after R1 or another broad change.

---

## Run 2026-10-15 (session 7) — validation pipeline tightening + metadata gaps report + T-27 lint closure

Focused batteries for the validation-pipeline improvements and the T-27 candlestick lint gate. The
full 1578-test suite was **not** rerun per instruction; only tests directly affected by the R7 code
changes were executed. No production data was touched; tests used isolated `tmp_path` databases.

| Command | Exit | Result |
|---|---|---|
| `.venv/bin/python -m pytest -p no:warnings tests/test_sectors.py tests/test_metadata_dryrun.py tests/test_security_metadata.py -q` | 0 | **90 passed** — symbol-format validation, sector-provenance dry-run preview, missing-sector-source flag, malformed timestamp/date rejection, metadata gaps report |
| `.venv/bin/python -m pytest -p no:warnings tests/test_api.py tests/test_scanner.py tests/test_ranking.py tests/test_sector_factor.py tests/test_ingest.py tests/test_market_store_concurrency.py tests/test_fundamentals.py tests/test_portfolio.py -q` | 0 | **311 passed** — no regressions in API, scanner, ranking, sector factor, ingest, concurrency, fundamentals or portfolio |
| `.venv/bin/python -m pytest -p no:warnings tests/test_candles.py -q` | 0 | **104 passed** — T-27 lint gate now clean |
| `.venv/bin/ruff check megatool/market_store.py megatool/sectors.py megatool/metadata_dryrun.py megatool/cli.py tests/test_sectors.py tests/test_metadata_dryrun.py tests/test_security_metadata.py megatool/ta/candles.py tests/test_candles.py` | 0 | `All checks passed!` |
| `.venv/bin/ruff format --check megatool/market_store.py megatool/sectors.py megatool/metadata_dryrun.py megatool/cli.py tests/test_sectors.py tests/test_metadata_dryrun.py tests/test_security_metadata.py megatool/ta/candles.py tests/test_candles.py` | 0 | `10 files already formatted` |
| `git status --short` / `git diff --cached` / `git stash list` | — | working tree modified, **0 staged / 0 stashes** — production DB untouched; server not restarted |

**Interpretation:** The validation pipeline now rejects malformed symbols, previews sector
provenance in dry-runs, and surfaces metadata gaps without writing anything. The candlestick
module is fully lint-clean. The full-suite baseline remains 1578 passed (session 4) and should
be rerun only after R1 or another broad change.

---

## Run 2026-10-15 (session 8) — source-pipeline validation on real snapshots

Two things happened: Kimi K2.7's interrupted metadata-validation work was
finished and verified, then the whole YONEPSE/binayabaral pipeline was run
against the real downloaded snapshots in isolated databases. The full 1578-test
suite was **not** re-run; only directly affected tests were executed.

| Command | Exit | Result |
|---|---|---|
| `.venv/bin/python -m pytest -p no:warnings tests/test_datasources_yonepse.py tests/test_datasources_binayabaral.py tests/test_datasources.py tests/test_news.py tests/test_sectors.py tests/test_metadata_dryrun.py tests/test_security_metadata.py tests/test_ranking.py tests/test_sector_factor.py tests/test_index_series.py tests/test_market_store_concurrency.py` | 0 | **279 passed** |
| `.venv/bin/python -m pytest -p no:warnings tests/test_fundamentals.py tests/test_datasources_yonepse.py tests/test_datasources_binayabaral.py tests/test_datasources.py tests/test_news.py tests/test_sectors.py tests/test_metadata_dryrun.py tests/test_security_metadata.py tests/test_ranking.py tests/test_sector_factor.py tests/test_index_series.py tests/test_market_store_concurrency.py` | 0 | **279 passed** |
| `.venv/bin/python -m pytest -p no:warnings tests/test_api.py tests/test_scanner.py tests/test_backtest.py tests/test_portfolio.py tests/test_cost_model.py tests/test_quality.py tests/test_ingest.py` | 0 | **308 passed** |
| `.venv/bin/python scripts/validate_source_pipeline.py --raw data/review/source_probe_2026-10-15 --out data/review/source_validation` | 0 | six-blocker evidence table, production db written **False** |
| `.venv/bin/ruff check` + `ruff format --check` (all modified files) | 0 | clean |

**Pipeline measurements against real data (isolated DBs only):**

| Blocker | Measured result |
|---|---|
| 1. Sector classifications | 360/372 symbols classified (96.77%), provenance on all 360, idempotent re-import |
| 2. Sector-relative ranking | 58/60 ranked symbols with a computed within-sector percentile (10 real sectors, 100% coverage) |
| 3. Historical NEPSE index | 6,718 rows, 1997-07-20 → 2026-10-14; cross-check vs socrateai identical to the cent |
| 4. Fundamentals Lab | 21,128 records / 307 symbols loaded; 169 real `PE == 0` records accepted |
| 5. News and events | 334 dated items imported; 18 upstream-undated skipped with reasons; 28 undated general notices not dated |
| 6. Official NEPSE API 401 | BLOCKED (not bypassed) |

**Interpretation:** running the pipeline on real data, rather than fixtures,
found two genuine defects (a zero-vs-missing conflating bug in
`fundamentals.py`, and duplicate reporting periods that made the whole YONEPSE
financial file unloadable). Both are fixed with tests; the production store,
the production app DB and all original financial records are untouched.

---

## Run 2026-10-15 (session 9) — every source re-investigated; sector consensus, sector indices, point-in-time fundamentals

Core modules were touched (`megatool/api.py`, `megatool/fundamentals.py`), so the **full suite** was
re-run rather than a focused subset.

| Command | Exit | Result |
|---|---|---|
| `.venv/bin/python -m pytest -p no:warnings` (full suite) | 0 | **1656 passed, 0 failed** (baseline was 1578; +78 new) |
| `.venv/bin/python -m pytest -p no:warnings tests/test_sector_consensus.py` | 0 | 15 passed |
| `.venv/bin/python -m pytest -p no:warnings tests/test_datasources_socrateai.py` | 0 | 10 passed |
| `.venv/bin/python -m pytest -p no:warnings tests/test_datasources_yonepse.py tests/test_fundamentals.py` | 0 | 86 passed |
| `.venv/bin/python scripts/validate_source_pipeline.py --raw data/review/source_probe_2026-10-15` | 0 | evidence in `data/review/source_validation/`; production written **False** |
| `.venv/bin/ruff check` / `format --check` (all changed files) | 0 | clean |

**Measured against real downloaded snapshots (isolated DBs only):**

| Blocker | Result |
|---|---|
| 1. Sector classifications | 4-source consensus: 365/372 resolved (291 ordinary, 74 instrument), **0 conflicting, 7 unresolved**; 78.3% unanimity over 512 multiply-covered symbols |
| 2. Sector-relative ranking | 58/60 ranked symbols with a percentile, **10 real sectors**; **74 instrument symbols now excluded** (verified defect fixed) |
| 3. Historical NEPSE index | binayabaral 6,718 rows 1997-07-20→2026-10-14; socrateai **17 indices**, 141-session stratified cross-check **93.85% identical, worst difference 0.17** |
| 4. Fundamentals Lab | **21,703 records / 307 symbols**; **99.86%** carry a filing date (point-in-time) |
| 5. News and events | 334 dated items imported; 28 undated general notices deliberately not dated |
| 6. Official NEPSE API 401 | **BLOCKED** — all `/api/nots/*` return 401; `/api/authenticate/prove` returns 200; requirement documented, not circumvented |

**Interpretation:** re-investigating every source rather than trusting the previous report changed
three conclusions — socrateai carries **sector index** history that was not used; a real defect
ranked mutual funds and debentures against ordinary shares; and the fundamentals `period_end` was
derived from an unreliable fiscal-year conversion (it implied 3,910 filings *predating* the period
they report). All three are fixed and tested. Production DB, production app DB and the running server
are untouched.

---

## Run 2026-10-15 (session 14) — Phase 1 closure + index consumption

**Command:** `.venv/bin/python -m pytest -p no:warnings tests/ --junitxml=<tmp>/junit_full.xml`

**Result:** **1820 passed, 0 failed, 0 errors, 0 skipped** · 28.56 s · exit 0
(junit root: `tests=1820 failures=0 errors=0 skipped=0`). Delta over the 1805 baseline is **+15**,
entirely `tests/test_index_consumer.py` (new). Two pre-existing ranking tests were edited in place
(no count change).

**Focused reruns this session:**

| Command | Result |
|---|---|
| `pytest tests/test_index_consumer.py` | **15 passed, 0 failed** |
| `pytest tests/test_ranking.py tests/test_financial_integrity.py tests/test_sector_factor.py tests/test_api.py tests/test_friend_access.py` | **238 passed, 0 failed** |
| `ruff check` (5 changed paths) | exit 0 |
| `ruff format --check` (5 changed paths) | exit 0 |
| `scripts/ingest_nepse_official_quotes.py` (gate OFF) | **exit 2**, refuses to fetch |
| `scripts/benchmark_market_hours.py --source nepse --interval 60` (gate OFF) | **exit 0**, SCHEDULE-ONLY, zero NEPSE requests |
| `scripts/check_source_health.py` (gate OFF) | **exit 0**, gated, no host contact |

**Not tested (external):** live market-hours cadence (market closed; next session Sun 2026-10-18
11:00–15:00 NPT); the NEPSE official collector end-to-end (gate OFF by policy); friend deployment
(needs a real token + origin). No synthetic fixture is presented as live evidence.

**Production safety:** PID 26596 alive; market DuckDB mtime `2026-10-15 09:24:38` and app SQLite
`2026-10-14 15:52:00` unchanged before and after; 0 staged; no `data/health/` created.

---

## Session-15 — Phase 2–6 autonomous run (2026-10-15)

**Full suite:** `pytest --junitxml=… -q`
→ **tests=1999 failures=0 errors=0 skipped=0 time=32.2s** (final rerun after the
indicator expansion).

**New focused files:**

| Command | Result |
|---|---|
| `pytest tests/test_chart_patterns.py` | 14 passed |
| `pytest tests/test_indicators.py` (expanded to 46 registered indicators) | **266 passed** |
| `pytest tests/test_stats.py` | 18 passed |
| `pytest tests/test_patterns_stats_api.py` | 9 passed |
| `pytest tests/test_scanner.py` (extended) | passed (file group 109 collected with the above three) |
| `ruff check .` | exit 0 |
| `ruff format --check .` | 200 files already formatted |
| `scripts/route_inventory.py --md …` | 75 routes, 75 TEST, every route test-referenced |

**Performance (backend-only, isolated synthetic 60×650, warm, n=12; p50/p95 ms):**
dashboard 8.7/9.4 · quotes 1.4/1.5 · bars 18.9/42.2 · indicator 4.1/4.5 ·
patterns 5.7/6.0 · statistics 3.3/3.4 · screen 145.8/160.3 · rank 397.2/410.7 ·
backtest 8.3/9.0 · correlation 5.7/6.2. Harness: `scripts/perf_smoke.py`.
**Bottleneck:** `/api/rank` (documented, not rewritten).

**Browser QA (new this session):** isolated dev server `127.0.0.1:8712` +
`playwright-cli`. Verified: 46 indicators served; dashboard breadth with an
explicit "No change data 4" bucket (no invented zeros); patterns panel 8
detections; statistics panel 7 metrics; correlation 4x4 matching numpy to 1e-9;
23 presets in the dropdown and a run reporting `Evaluated 4 · Eligible 4 ·
Passed 1`; **0 console errors across all 11 views**. Found and fixed **B-46**
(percent scaling in `app.js`), then re-verified. Server killed, dev data deleted.

**Not tested (external, unchanged):** live NEPSE cadence (gate OFF), official
collector end-to-end, friend deployment, XSS/rendering fuzzing, full
click-through of every view. No synthetic fixture is presented as live evidence.


---

## Session-16 — verification mission (2026-10-16)

**Baseline re-established:** full suite at start = **1999 passed / 0 failed**.

**Final:** `pytest --junitxml=… -q` → **tests=2007 failures=0 errors=0 skipped=0
time=31.9s**.

| Command | Result |
|---|---|
| `pytest` (full) | **2007 passed / 0 failed / 0 errors / 0 skipped** |
| `pytest tests/test_friend_access.py` | 20 passed (17 + 3 new boundary-notice) |
| `pytest tests/test_api.py` | 101 passed (incl. 2 new degenerate-series tests) |
| `pytest tests/test_indicators.py` | 273 passed (incl. 6 new rolling_std tests) |
| `ruff check .` | clean |
| `ruff format --check .` | 205 files formatted |
| `node --check web/static/app.js` | clean |
| `scripts/verify_quant.py` | exit 0 — all independent checks agree (scipy present) |
| `scripts/perf_smoke.py` | rank p50 113.6 ms (was 391.7 ms) |
| `scripts/route_inventory.py` | 75 routes, all test-referenced |

**Browser E2E:** isolated dev server (127.0.0.1:8714/8715) + `playwright-cli`
across all 11 views → **0 console errors, 0 warnings**. Independent
cross-checks: portfolio arithmetic exact; research SMA20 re-derived by hand and
matched; backtest hand-computed (10,450 / 10,450 / 10,247.50) matched;
correlation matrix matched numpy to 1e-9.

**Independent quant verification (`scripts/verify_quant.py`):**
SMA/WMA/EMA vs pandas and an independent loop; RSI vs an independent Wilder
loop; MACD vs pandas ewm; Bollinger vs pandas rolling; Pearson/Spearman/Student-t
vs scipy.stats; OLS vs numpy lstsq; return stats recomputed; three hand-computed
backtests. **All agreed.**

**Still not tested:** dependency CVE scan (pip-audit unavailable), XSS fuzzing,
production migration, background jobs, soak testing, real-market latency.

---

## Session 17 — definitive audit (2026-10-16)

Full suite re-run: **2016 passed / 0 failed / 0 errors / 0 skipped** (38.1 s,
junitxml). Route inventory: **75 routes** (mutating=12, read-only=63, all
test-referenced). Engine counts re-verified by import: **46 indicators · 23
scanner presets · 9 agent tools**.

No code was changed and no test failed this session. The audit's findings are
requirement-coverage gaps (and two documentation-accuracy corrections), not new
defects — see `docs/PHASES_2_6_COMPLETION_AUDIT.md`. Browser click-through was
**not** repeated this session; the last real browser E2E (all 11 views, 0 console
errors) was the prior session, cited as such and not re-asserted.

---

## Run 2026-10-16 (session 18) — Phase 2–6 implementation

**Result: 2051 passed, 0 failed, 0 errors, 0 skipped** (junitxml, full suite).
Command:

```bash
.venv/bin/python -m pytest -q --junitxml=/tmp/junit.xml
# tests=2051, failures=0, errors=0, skipped=0
```

### New tests (35)

| File | Tests | Covers |
|---|---|---|
| `tests/test_candles_api.py` | 10 | `GET /api/bars/{symbol}/candles`: detection shape, no-"confirmed" honesty note, pattern filter, unknown-pattern 400, malformed 400, unknown 404, impossible-OHLC exclusion + count, friend-read allowlist |
| `tests/test_watchlists.py` | 15 | storage CRUD + validation (upper/dedupe/order, malformed rejected, duplicate names, add/remove/replace/rename/clear) and the HTTP routes (create/list, detail enrichment with `close: null` + reason for missing bars, PATCH, rename, delete, 404, 400 duplicate, 400 malformed, friend-denied) |
| `tests/test_experiments.py` | 10 | config-hash determinism/sensitivity/key-order, save round-trip, reproduce reports zero drift, compare reports a real delta, Markdown export carries hash + `data_as_of`, delete, 404, friend-denied |

### Gates re-run this session

| Gate | Result |
|---|---|
| `.venv/bin/python -m pytest` (full) | **2051 / 0 / 0 / 0** |
| `.venv/bin/python scripts/route_inventory.py` | **88 routes** (71 read-only, 17 mutating), all test-referenced, exit 0 |
| `node --check web/static/app.js` | exit 0 |
| `tests/test_route_inventory.py` (smoke/inventory tables must agree) | pass — both MUTATING tables updated together |
| `.venv/bin/python scripts/verify_quant.py` | exit 0 (unchanged) |

### Session 18 browser evidence (real Chromium via `playwright-cli`)

Isolated dev server: `MEGATOOL_DATA_DIR=data/dev/qa`, `127.0.0.1:8799`, gate unset,
owner-only boundary. **Not** the production server (8710). Scripted walkthrough
(`run-code`, two passes) with console/`pageerror`/`requestfailed` capture:

| Workflow | Evidence |
|---|---|
| Load chart (QABANK2, all range) | `#chart-meta` = "QABANK2 · 420 bars · 2024-06-03 → 2026-01-09 · source: qa-fixture · prices unadjusted" |
| Candlesticks auto-detect | 17 table rows; picker 15 entries; hint shows "243 bar(s) with impossible OHLC excluded · trend context 3" |
| Candlestick pattern subset | 3 patterns → 17 rows (filter respected) |
| Candlestick **None** | 0 rows + explicit "No candlestick patterns selected" message (fixed a fall-through-to-all bug this session) |
| Candlestick markers on chart | small "Sp"/"Do" circle markers visible on the rendered chart (screenshot) |
| Elliott panel | `Status CANDIDATE_ONLY · method elliott_extended_v1.0 · 33 confirmed swing(s) considered`; 33 manual label selects rendered |
| Elliott manual labels | selecting labels persisted to `localStorage` (`mt-elliott-QABANK2`); magenta "Manual wave count" line + labels drawn on chart (screenshot) |
| Harmonic panel | `Status NO_MATCH · 29 five-swing window(s) tested · patterns tried: Gartley, Bat, Butterfly, Crab, Cypher` |
| Watchlist create + detail | 3 list rows; detail 2 rows; missing symbol shows `—` + "no stored bar for this symbol" |
| Watchlist add / rename / delete | 2→3 rows on add; rename → "QA 1792119560097 renamed"; delete hides detail card |
| Backtest | metrics block rendered (204 chars) |
| Experiment save + list | 3 rows listed with hash + `data_as_of` |
| Experiment reproduce | "identical config: yes", A/B hash equal, every metric `same` |
| Report export | download `QABANK2-research-report.md` |
| Experiment export | download `experiment-3.md` |
| Console errors / failed requests | **0 console errors**, 0 failed requests (the one transient 400 earlier was a duplicate-name rename from a prior pass — expected) |

Not exercised in a browser this session: friend-token cross-origin mode, PDF/floorsheet
views, and any live-market path — those remain NOT-TESTED as before.

## Run 2026-10-16 (session 19) — custom rules, dashboard, extra detectors, analysis windows

**Result: 2080 passed, 0 failed, 0 errors, 0 skipped** (junitxml, full suite).

```bash
.venv/bin/python -m pytest tests/ -q --junitxml=/tmp/full19.xml
# tests=2080, failures=0, errors=0, skipped=0
```

### New tests (29)

| File | Tests | Covers |
|---|---|---|
| `tests/test_screens.py` | 14 | saved-custom-rule storage (save/list/get/update/duplicate/delete), unknown **metric** and unknown **operator** rejected at save, blank/duplicate names, nested AND/OR round-trip, API CRUD, a saved rule re-executed through `POST /api/screen` against real bars, 400/404 paths, friend-denied |
| `tests/test_analysis_window_api.py` | 9 | `/elliott` + `/harmonic` window params: `limit` narrows `swings_considered`, `start/end` accepted, 404 for unknown symbol, harmonic `patterns` subset echoed in `patterns_tested`, unknown pattern → 400, `slack` out of range → 422, `slack=0` = published ratios only, catalogue published |
| `tests/test_candles.py` (+6) | 6 | `harami_cross` fires on a doji second candle and does **not** fire on a large body; `tweezer_bottom`/`tweezer_top` fire on matching lows/highs and not when they differ; new names present in `PATTERN_NAMES` and `PATTERN_CANDLE_COUNT`; `tweezer_tolerance_ratio` is configurable |

### Gates re-run this session

| Gate | Result |
|---|---|
| `.venv/bin/python -m pytest` (full) | **2080 / 0 / 0 / 0** |
| `.venv/bin/python scripts/route_inventory.py` | **94 routes** (74 read-only, 20 mutating), all test-referenced, exit 0 |
| `node --check web/static/app.js` | exit 0 |
| `.venv/bin/ruff check .` | All checks passed |
| `.venv/bin/ruff format --check` | 218 files already formatted |

### Session 19 browser evidence (real Chromium via `playwright-cli`, QA fixture, 127.0.0.1:8799)

Console errors **0**, failed requests **0** across all passes.

| Workflow | Evidence |
|---|---|
| Screener → rule builder catalogue | 33 metrics loaded into the condition picker |
| Rule builder → **Run** | "4 of 15 eligible securities matched (19 evaluated). Rule: `rsi < 40`" with per-row *match* / *ineligible* + reason |
| Rule builder → Save / Duplicate / Delete | `#rb-saved` = `[qa-oversold]` → `[qa-oversold, qa-oversold-copy]` → `[qa-oversold]` |
| Customise dashboard | 7 panel rows listed; unchecking *Alerts* → `display:none`; moving *Totals* down → `style.order=2`; **Reset** → restored; `localStorage['mt-dashboard-layout']` persisted |
| Chart load (QAFLAT) | 120 bars on the candle series |
| Candlesticks (All) | 144 markers written; picker shows **18** entries incl. Harami Cross / Tweezer Bottom / Tweezer Top |
| Elliott (period = 120) | `CANDIDATE_ONLY · elliott_extended_v1.0 · 22 confirmed swing(s)`; 2 **Draw** buttons; drawing a candidate → 5 wave markers + line series |
| Harmonic (Gartley only, slack 0.02) | `NO_MATCH · 68 windows · patterns tried: Gartley · tolerance ±0.02 — matches are approximate` (honest no-match with the approximate wording) |
| Harmonic (slack 0.2, chart window) | `CANDIDATE_ONLY · 18 windows`; 5 candidates; **Draw** → 1 series + 1 D marker (confirms the B-56 window-alignment fix) |
| Harmonic (slack 0) | `NO_MATCH · tolerance 0 — published ratios only` |

Not exercised in a browser this session: friend-token cross-origin mode, PDF/floorsheet
views, live-market paths — unchanged NOT-TESTED.

---

## Session 20 (2026-10-16) — assistant, templates, index/RS, alerts, security

### Automated suite

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest tests/ -q -p no:randomly` | **2116 passed / 0 failed / 0 errors / 0 skipped** (session 19: 2051) |
| `.venv/bin/python -m pytest tests/test_screens.py` | 20 passed (14 before; +6 for the proposal grammar) |
| `.venv/bin/python -m pytest tests/test_templates.py` | 7 passed (new file) |
| `.venv/bin/python -m pytest tests/test_alerts.py` | 20 passed (10 before; +10 for severity/cooldown/ack) |
| `.venv/bin/python -m pytest tests/test_index_consumer.py` | 22 passed (+7 for RS endpoint + scanner metric) |
| `.venv/bin/python -m pytest tests/test_patterns_stats_api.py` | 13 passed (+1 for the `patterns=` filter) |
| `.venv/bin/python -m pytest tests/test_route_inventory.py` | 5 passed (+2 pinning that the gate cannot write the operator's DB) |
| `.venv/bin/python -m pytest tests/test_friend_access.py` | 22 passed (+2 for the new routes) |
| `.venv/bin/ruff check .` | All checks passed |
| `.venv/bin/ruff format --check .` | 221 files already formatted |
| `node --check web/static/app.js` | OK |
| `.venv/bin/python scripts/route_inventory.py` | 98 routes (20 mutating, 78 read-only); **every route is referenced by at least one automated test** |
| `uvx pip-audit --path .venv/lib/python3.12/site-packages` | **No known vulnerabilities found** (`megatool` itself is not on PyPI, so it was skipped) |

### Browser evidence (real Chromium via `playwright-cli`, QA fixture, `127.0.0.1:8799`)

Console errors **0** and failed requests **0** across every pass below.

| Workflow | Evidence |
|---|---|
| Fibonacci — two-click anchor | `Anchor 1: 2025-09-19 @ 224.98` from a real chart click; second click created `{t1: 2025-09-19, p1: 224.98, t2: 2025-10-03, p2: 264.61}` |
| Fibonacci — level maths | 5 level series; every drawn price equalled `p2 − r·(p2 − p1)` exactly (e.g. `0.786 → 233.4595`); table row shows both anchors and an editable ratio field |
| Fibonacci — drag an anchor | Handle hit-test `dist = 0.23 px`; dragging to a new screen point produced `2025-10-21 @ 183.49`, committed on release, persisted to `localStorage['mt-drawings-QABANK3']` |
| Fibonacci — ratio edit / undo / redo | `0.5, 0.618, 1.272` → 3 series; **Undo** → back to 5 ratios and 5 series; **Redo** → 3 ratios, 3 series |
| Fibonacci — multiple drawings, per-symbol isolation | Retracement + extension coexist (2 rows, 6 series); `QABANK2` shows *no drawings*; returning to `QABANK3` restores them |
| Fibonacci — survives unrelated changes | Toggling an indicator **and** changing the range rebuilt the chart while keeping both drawings and all 4 anchor markers at identical coordinates |
| Chart patterns — picker + overlay | 8 pattern rows; 8 pivot polylines + 16 level lines = 24 series; one polyline's data equalled the detector's reported pivots (`2025-12-15@102.0692, 2025-12-29@102.9893, 2026-01-02@101.8524`) |
| Chart patterns — selection filter | **None** → *"All matches are hidden by the current pattern selection."*; re-checking `double_top` → 2 rows, 4 overlay series, hint `1 of 15 selected` |
| Index & relative strength | `Benchmark NEPSE · stock −20.59% · index −5.71% · excess −14.88 pp · 420 aligned bars · 0 dates missing on either side` + ratio line on its own scale |
| RS — insufficient history | `EDGEFLAT`, 200-bar window over 120 aligned bars → **unavailable**, window returns shown as `—`, missing index dates counted (152) — never a number |
| Dashboard "Index context" panel | `2 series stored · composite NEPSE · 420 rows · last 2026-01-09`, hint *"Published index files — historical, NOT a live feed"* |
| Floating assistant | FAB opens the panel; provider line reads *"AI explanation: not configured (tools still work)"*; 6 example chips |
| Assistant — tool run | *"Show me the stored history summary for QABANK3"* → routed to the real `research` tool, `33 findings as of 2026-01-09 over 420 stored bars`, provenance `stored price_bars for QABANK3, 2024-06-03 → 2026-01-09`, raw data expandable |
| Assistant — propose + load | *"…rsi below 40 and price above its sma 50 and pe below 10"* → `rsi < 40 AND close_vs_sma(50) > 0`, unmatched list names P/E; **Load into rule builder** → Screener shows 2 editable rows (`rsi lt 40`, `close_vs_sma 50 gt 0`) |
| Assistant → rule → run | Edited the threshold to 60 → **Run rule** → *"3 of 16 eligible securities matched (19 evaluated)"* with per-condition actuals and per-symbol ineligibility reasons |
| Templates — run a workflow | `technical_review` → agent block + **2** result tables; steps shown as `GET /api/bars/QABANK3`, `…/statistics`, `…/structure` |
| Templates — save/load a copy | Saved copy appeared as 1 row; selecting another template then **Load** restored `technical_review` + `QABANK3` |
| Templates — POST step + no symbol | `sector_compare` (POST `/api/rank`) ran with no symbol and returned the ranked universe |
| Alerts — severity | Rows show `critical` / `info` pills; `fire_count` column present |
| Alerts — cooldown | `cooldown_minutes: 0` re-fired → *"1 fired now, 1 already recorded … Re-armed after cooldown: 1"*, fires column `2`; the un-cooled `info` condition stayed at `1` |
| Alerts — acknowledgement | Per-row **Acknowledge** → row marked `ack`; **Acknowledge all** acknowledged the remaining 1; history count unchanged and no condition re-armed |
| Security — XSS | `<img src=x onerror=…>` and `<script>` sent through the chat input: **0** injected nodes, handler never ran; markup in a template input likewise escaped |

### Incident recorded this session (see B-59)

Running the project's own required `scripts/route_inventory.py` gate migrated
`data/processed/megatool_state.sqlite` (three additive `ALTER TABLE` columns). No rows
changed — all tables remain empty — and the fix in D-aw stops it recurring. Recorded
here because it happened, not because it was harmless: a read-only gate touched the
operator's database.


---

## Session 22 (2026-10-16) — actual go-nepse Go library: gate results

**Scope of this run:** integrate the *actual* `github.com/voidarchive/go-nepse` library
(module `v0.2.5`) behind a Go subprocess bridge, wire it to the Python provider layer,
and re-run every project gate. No production resource was touched; no live NEPSE
request was made.

| Gate | Command | Result |
|---|---|---|
| Full Python suite | `.venv/bin/python -m pytest -q --junitxml=…` | **2150 passed / 0 failed / 0 errors / 0 skipped** |
| Lint | `.venv/bin/python -m ruff check .` | All checks passed |
| Format | `.venv/bin/python -m ruff format --check .` | 224 files already formatted |
| Frontend syntax | `node --check web/static/app.js` | exit 0 |
| Route inventory | `.venv/bin/python scripts/route_inventory.py` | **100 routes (21 mutating, 79 read-only), all test-referenced** |
| Go build | `go build …` in `tools/gonepse-bridge` | built (12.6 MB, darwin/arm64) |
| Go vet | `go vet ./...` | clean |
| Go tests | `go test ./...` | **9/9 pass** |

**New test totals.** +29 Python tests over session 21's 2121 → 2150
(21 in `tests/test_gonepse_adapter.py`, 3 in `tests/test_api.py`, 5 in
`tests/test_portfolio.py`). Plus 9 Go tests that Python does not run (they need the
Go toolchain).

**Go toolchain.** Go was **not installed** on this machine. Go **1.27.2** was
downloaded from `go.dev` into an isolated prefix
(`…/T/opencode/toolchain/go`) with `GOPATH`/`GOMODCACHE` likewise isolated — the
system, Homebrew and the project were not modified. The bridge declares `go 1.25`,
satisfied by 1.27.2.

**What the Go tests actually exercise (no NEPSE contact).** A local `httptest`
**TLS** server serves the library's own token fixture (`internal/auth/testdata/
token_response.json`) and canned market data. The tests assert that the bridge (a)
decoded a real `MarketSummary`, (b) made the mock receive an `Authorization: Salter
<token>` header — proving the token fetch + embedded-WASM salt parse + auth header
ran, (c) excluded the main index from `SubIndices`, (d) mapped a provider `404` to
`kind:"not_found"`, (e) rejected unknown ops / missing symbols as
`invalid_client_request`, (f) distinguished `timeout`/`canceled`/`rate_limit`, (g)
refused the real host without the gate, and (h) emitted a single decodable JSON
object. The test injects the test server's trusted client, so TLS verification
semantics are unchanged (never a real skip-verify path).

**TLS certificate diagnostic (verified handshake, no data request).** With
verification enabled, `nepalstock.com.np:443` presents a valid chain:
DigiCert/GeoTrust TLS RSA CA G1, subject `NEPAL STOCK EXCHANGE LTD /
www.nepalstock.com.np`, valid `Dec 12 2025 → Dec 10 2026`, SAN includes
`nepalstock.com.np`. Saved to `docs/evidence/session22-nepse-tls-cert.txt`. The
library's documented certificate problem is **not present today**; the bridge keeps
verification on and would report any certificate failure verbatim.

**Per-endpoint status.** No endpoint was exercised live — the owner gate is unset.
The mission's priority operations are implemented and unit-tested at the
bridge/adapter boundary; each is **IMPLEMENTED + TESTED-PASS (fixture)** and **live
NOT-TESTED (BLOCKED)**. This is not a claim that live data works.

**Honest limits.**
* **Live connection: BLOCKED.** `MEGATOOL_NEPSE_API_AUTHORIZED` is unset; both the
  Python adapter and the bridge refuse by design. No request reached NEPSE.
* The library's `Options.BaseURL` is dead code upstream; only
  `Options.Config.BaseURL` is used (documented; the bridge sets both).
* Historical rows carry no opening price, so `fetch_history` leaves `open` null
  rather than inventing it.
* Upstream `nepse.Version` reports `0.2.0` at module `v0.2.5`.
* Loopback/production isolation held: prod PID 26596 alive on `127.0.0.1:8710`
  (`/api/health` 200); prod SQLite mtime unchanged (`2026-10-16 10:31:58`); prod
  DuckDB mtime unchanged (`2026-10-15 09:24:38`).

**Portfolio cash-flow model (Priority 2).** Five tests in `tests/test_portfolio.py`
plus a route test and an empty-portfolio assertion in `tests/test_api.py` cover the
new `cash_flows()` model: exact signed `net` and `cumulative` for a buy-then-sell
(fees included on both sides), replay in `traded_at, id` order (not insert order),
multi-symbol `per_symbol_net`, a zeroed empty ledger, and that `GET /api/portfolio`
embeds the *same* summary the dedicated route returns. The model's `note` and the
valuation note both keep the explicit "not an account cash balance" distinction.
Hand-checked: BUY 100@250 fees 50 → −25,050; SELL 40@300 fees 30 → +11,970;
`net_cash_flow` −13,080. Browser (`session22-portfolio-cashflow.png`): the Portfolio
panel renders Invested 1,005 / Proceeds 474 / Fees 11 / Net cash flow −531 for a
seeded ledger, with **0 console errors/warnings**.

---

## Session 23 (2026-10-16) — live data layer: gate results

| Gate | Command | Result |
|---|---|---|
| Full Python suite | `pytest -q --junitxml=…` | **2174 passed / 0 failed / 0 errors / 0 skipped** |
| Lint / format | `ruff check .` / `ruff format --check .` | pass / 226 files formatted |
| Frontend syntax | `node --check web/static/app.js` | exit 0 |
| Route inventory | `scripts/route_inventory.py` | **103 routes (21 mutating, 82 read-only), all test-referenced** |
| Dependency audit | `uvx pip-audit` | **No known vulnerabilities found** |
| Live layer unit tests | `pytest tests/test_live.py` | **23 passed** (offline; HTTP boundary injected) |

**New tests (+29 over session 22's 2150 → 2174):** 23 in `tests/test_live.py`
(timestamp parsing incl. Nepal-time and epoch; freshness bands incl. market-closed;
never-invent-a-price; provider parsing for ShareHub/feed/YONEPSE; ShareHub 401
refresh; gate; cache-at-cadence; error surfacing; priority/forced selection), plus
route/status tests in `tests/test_api.py`.

**Measured live-data evidence (bounded, one probe each):**
* Official `/api/nots/*` without a token → **401 `WARNING: UNAUTHORIZED ACCESS`**.
  `/api/authenticate/prove` (browser UA) → 200 with `salt1..salt5` + JWE token;
  `curl` UA → HTTP/2 `PROTOCOL_ERROR`. TLS verify **OK** (DigiCert, to 2026-12-10).
* `GET /api/live/market` (YONEPSE) → request **1,334 ms**, newest observation
  **2026-10-12T09:14:59Z** ⇒ `age_seconds` **≈338,978 (3.9 d)** ⇒ label **`stale`**,
  368 quotes, 0 missing prices.
* ShareHub `/my-ip` → 200 in **0.14 s** (reachable; licence + allow-list required).
* `nepseapi.com` → early access only. `nepseapi.surajrimal.dev` → **HTTP 522** (down).

**Live access: BLOCKED.** No permitted low-latency source is configured. The
official path is not a "just open the gate" fix — it needs the anti-bot token,
which is not produced. This is reported, not worked around.

**Isolation:** production PID 26596 alive on `127.0.0.1:8710`; prod SQLite and
DuckDB mtimes unchanged; gate unset; dev server (8799) started on a throwaway app
DB and stopped; browser closed.

---

## Diagnostic pass (2026-10-16) — can go-nepse retrieve real NEPSE data?

**Result: NOT_TESTED / BLOCKED_BY_ACCESS_RESTRICTIONS.** No live go-nepse request
was made: its only access path is the WASM anti-bot token strip, which the brief
prohibits. No code changed in this pass.

**Verified without a bypass**
* Library = module **v0.2.5** (latest), CHANGELOG last release **0.2.0**
  (unmaintained); auth = `css.wasm` index strip + `Salter` header.
* Bridge refuses the real host without the gate (exit 3); a non-default host
  produces an honest provider error and makes no NEPSE request.
* Gate unset; `OfficialProvider.configured()` → False ("owner authorization gate
  is closed"); TLS verifies (`ssl_verify_result=0`).
* Go bridge tests (`go test ./...`) pass (fixtures). Python adapter tests: **21
  passed** (offline). These prove nothing about live data.
* Live challenge still exposes all 8 fields the library decodes ⇒ input parsing
  compatible; token acceptance unverifiable.
* Supply-chain note: a 12 MB x86-64 ELF named `basic` sits in the module root,
  unreferenced by any `.go` file.

**Bounded live probes (one each, no bypass):** `/api/nots/nepse-data/market-open`,
`/market-summary`, `/nepse-index`, `/lives-market` → all **HTTP 401
`WARNING: UNAUTHORIZED ACCESS`** in ~0.03 s, 0 records. `/api/authenticate/prove`
→ 200 (a challenge, not market data).

**Conclusion:** the app is blocked by the anti-bot token scheme (not by TLS,
network or missing credentials). Under the project's rules go-nepse is not a
usable live source; the dashboard's `official` provider stays inert and the
Overview shows the labelled YONEPSE fallback. Recommendation: validate ShareHub
in test mode before purchasing.

---

## Session 24 (2026-10-16) — free current-day data: gate results

| Gate | Command | Result |
|---|---|---|
| Full Python suite | `pytest -q --junitxml=…` | **2179 passed / 0 failed / 0 errors / 0 skipped** (baseline 2174) |
| Lint / format | `ruff check .` / `ruff format --check .` | pass / 228 files |
| Frontend syntax | `node --check web/static/app.js` | exit 0 |
| Route inventory | `scripts/route_inventory.py` | **103 routes (21 mutating, 82 read-only), all test-referenced** |
| Live layer + datasource tests | `pytest tests/test_live.py tests/test_datasources_yonepse.py` | pass |

**Measured live evidence (free, no auth, no key, no allow-list):**

| Probe | Result |
|---|---|
| Raw `data/market/status.json` | `is_open: true`, `last_checked 2026-10-16T07:17:03` (**31 min old**) |
| Raw `data/market/indices.json` | NEPSE **2,625.93** @ `2026-10-16T13:01:00` NPT |
| Raw `data/market/live.json` | **328 quotes**, per-symbol last-trade times in-session |
| GitHub-Pages mirror, same minute | `last_checked 2026-10-12` → ~4 days stale (this was the bug) |
| `GET /api/live/market` (raw healthy) | status **DELAYED**, age ≈37–43 min, latency ≈0.4 s, 328 quotes |
| `GET /api/live/market` (raw broken) | status **STALE**, age 4.0 d, **origin = Pages mirror**, fallback note |
| Official `/api/nots/*` | **401 UNAUTHORIZED** (anti-bot token; unchanged) |

**Real fundamentals:** 21,698 records / 307 symbols imported from the free source;
`/api/fundamentals/NABIL/ratios` returns reported EPS with P/E/P/B **unavailable**
(no stored close) — never invented.

**Upstream incident observed:** the raw file briefly contained git merge-conflict
markers; the adapter fell back and reported the stale mirror **with its origin**.
No conflict markers were repaired into data.

**Isolation:** production PID 26596 alive (`/api/health` 200); prod SQLite and
DuckDB mtimes unchanged; gate unset; dev server stopped; browser closed; 0 staged,
0 stashed.

---

## Session 25 (2026-10-16) — local release instance: gate results

| Gate | Command | Result |
|---|---|---|
| Full Python suite | `pytest -q --junitxml=…` | **2184 passed / 0 failed / 0 errors / 0 skipped** |
| Lint / format | `ruff check .` / `ruff format --check .` | pass / 228 files |
| Frontend syntax | `node --check web/static/app.js` | exit 0 |
| Route inventory | `scripts/route_inventory.py` | **103 routes (21 mutating, 82 read-only), all test-referenced** |
| Go bridge | `go vet ./...` + `go test ./...` | clean / pass |
| Dependency audit | `uvx pip-audit` | no known vulnerabilities |

**Real-provider test (not a fixture):** the dev instance on `127.0.0.1:10000`
served **live** YONEPSE data. `/api/live/market` → status **DELAYED**,
`age_seconds` ≈4533 (75 min), 328 quotes, NEPSE index 2,625.93, latency ≈1.9 s.
Origin was a recent commit (`f8941a30…`) because upstream `main` was a broken
merge — the walk-back worked. Measured during the incident, not asserted.

**Fixture tests:** the 2184-suite (indicators, patterns, scanner, routes,
adapters) is deterministic and offline; none of it claims live access.

**Browser (real server):** 14 views, **0 console errors/warnings**.
* Overview: header "delayed public source (yonepse) — not a live feed"; live strip
  OPEN, index 2,625.93, age 75.6 min; totals 372 symbols, as of 2026-10-15.
* Charts: `NABIL · 120 bars · 2026-04-20 → 2026-10-15 · github.com/Aabishkar2/nepse-data ·
  prices unadjusted`; 7 canvases.
* Screener: 372 evaluated, 350 eligible, 18 passed, 22 insufficient-data.
* Fundamentals ratios: NABIL P/E 19.2525 (eps 28.36, 2026-08-06, reviewed), P/B 2.208.
* Data diagnostics: status, age, provider vs receipt time, latency, securities, origin.

**Isolation:** production PID 26596 alive (`/api/health` 200); prod SQLite/DuckDB
mtimes unchanged; gate unset; dev data in `data/dev/release/`; 0 staged/stashed.

---

## Session 26 (2026-10-16) — UI overhaul: gate results

| Gate | Result |
|---|---|
| Full Python suite | **2199 passed / 0 failed / 0 errors / 0 skipped** (2184 → 2199) |
| `ruff check .` / `ruff format --check .` | pass / 234 files |
| `node --check web/static/app.js` | exit 0 |
| `scripts/route_inventory.py` | **105 routes (21 mutating, 84 read-only), all test-referenced** |
| Go bridge `go test ./...` | pass |
| Browser console (14 views) | **0 errors / 0 warnings** |

**New tests:** 13 in `tests/test_ideas.py` (catalogue honesty; unavailable models
return no rows; Graham fair value from stored EPS/BVPS `sqrt(22.5*10*100)=150`;
ranking order; P/B ordering; implausible per-share refused; EPS growth needs two
periods ≥1 yr apart; negative growth does not raise; PEG from P/E and growth;
momentum 12-1; 52-week ordering) + 2 route tests in `tests/test_api.py`.
**Fixture tests only** for the models — no live provider is involved.

**Browser verification (dev instance, `127.0.0.1:10000`):**
sidebar 6 groups / 14 nav buttons; global search present; 14 views render with 0
console errors; Ideas renders 10 cards with Magic Formula / Piotroski / Altman
**disabled**; Graham run → *372 evaluated, 40 matched*, ADBL fair value 1024.67 vs
price 333.8; Peter Lynch run → 4 matched; breadth bar 59.9 % / 32.8 % / 7.3 % / 0 %.
Evidence: `docs/evidence/session26-shell-dashboard.png`, `session26-dashboard.png`,
`session26-ideas.png`.

**Isolation:** production PID 26596 alive; prod DB mtimes unchanged; gate unset;
dev data in `data/dev/release/`; 0 staged/stashed.

---

## Session 27 — chart workspace: gate results

**Suite: 2199 passed / 0 failed / 0 errors / 0 skipped.** `ruff` clean; 234 files
formatted; `node --check` ok; `route_inventory.py` **105 routes, all
test-referenced**; Go bridge tests pass. Accuracy measurement-based; browser
interactions all exercised against the live dev instance (`127.0.0.1:10000`).

**Browser interactions verified (not just page load):**

| Action | Result |
|---|---|
| Symbol search + Load | `NABIL · Daily · 120 bars · 2026-04-20 → 2026-10-15 · unadjusted · historical`; 7 canvases in the price chart (lightweight-charts' internal pane grid) |
| Clean default | candles + volume only; zero S/R / Fibonacci / pattern overlays |
| Indicators popover → SMA on | SMA overlays render; S/R layer survives the reload (per-symbol persistence) |
| Indicators popover → RSI / MACD | both panes render (**B-65 fixed**) |
| Chart type = Line | line series replaces candles, panes intact |
| Timeframe select | endpoint switches (`/weekly`, monthly) |
| Layers: fib / candles / patterns / elliott / harmonic | 10 / 56 / 6 / 14 / **none** found; `harmonic` honestly reports "none" |
| Layer: S/R | 10 found, results list 10 rows, note "73 zones detected, 10 nearest drawn" |
| Detected row click | handler runs (`highlightResult` thickens that line) |
| "Hide all" | layers off, results cleared (**B-68 fixed**) |
| Draw popover → Fibonacci retracement | two clicks → "Fib retracement added", 1 row in the drawings list |
| Fit / zoom in / zoom out | no error; visible range changes |
| Fullscreen | `document.fullscreenElement` set, chart height 678 px |
| 14 views | **0 console errors / 0 warnings** |

**Accuracy:** S/R counts and the detected-items list come from the live
`/api/bars/{symbol}/levels` response (73 real zones), not fixtures. Fib counts
come from `/fibonacci`; pattern/elliott/harmonic counts from their panels.

---

## Session 28 — dashboard is visibly redesigned

Verified in-browser: hero KPIs (turnover NPR 5.5B, volume 15.7M, 199/106, as-of
2026-10-15), official-index chart, breadth + MA, 14 sectors, 8 gainers/8 losers
/8 active, P/E histogram (231 symbols). Banner now correct. 0 console errors.
2200 tests pass; ruff/node/routes all green.

## Go NEPSE library diagnostic (follow-up)

Gate results for this pass:
* `pytest tests/test_gonepse_adapter.py tests/test_live.py -q` → 21 + 23 attach tests pass.
* `/api/sources` and `/api/gonepse/status` expose `live_connection_tested: false`
  and `blocker: "anti-bot token obfuscation + owner gate (unset)"`.
* Live probe: 4/4 `/api/nots/*` endpoints → HTTP 401 in 0.031–0.046 s; TLS
  verify OK; challenge endpoint 200 repeating salts1..5 + JWE accessToken.

Classification: **BLOCKED_BY_ACCESS_RESTRICTIONS**, (live **NOT_TESTED**).
No fixture count was confused with a live result. Production untouched
(PID 26596). Gate remains unset. No code reverted from the live layer.

---

## Session 2026-10-16b — market-data collector (ten published datasets)

**Objective:** a reliable collector that retrieves the latest *legitimately
accessible* NEPSE market data, validates it, stores it in the existing
architecture, and serves it with honest freshness and provenance.

**What was built**
- `megatool/collector.py`: one run reads, validates and persists the market
  files the YONEPSE mirror publishes (the same permitted source the dashboard
  serves; no new endpoint, no auth, no anti-bot bypass):
  `market_live` (362 rows), `index` (4), `summary` (6), `status` (1),
  `sector_indices` (17), `history` (234), and the five ranking boards from
  `top_stocks.json`: `top_gainer`, `top_loser`, `top_turnover`, `top_trade`,
  `top_transaction`.
- Freshness is **source-stated or unknown**: `observed_at` comes only from
  stamps the publisher itself writes (per-row `last_updated`, `last_checked`,
  `generatedTime`); retrieval time is stored separately and never backdated.
  Datasets the source stamps no timestamp on (summary, rankings, sector
  definitions) are labelled `unknown` with a note — never assigned another
  dataset's stamp.
- Business-date cross-check: `summary.json` turnover/shares/transactions are
  matched against the same-day `history.json` row (0.5% tolerance, at least
  2 of 3 metrics) to attest *which session day* a snapshot describes, with
  the matched values as recorded evidence.
- Persistence: schema v7 in the app SQLite store (`collector_runs`,
  `collector_datasets`, `collector_quotes`, `collector_index`,
  `collector_summary`, `collector_rankings`, `collector_status`,
  `collector_sector_indices`); one transaction per run, full rollback on any
  failure; `ingestion_log` entry per run (`collector/yonepse`).
- Interfaces: `megatool collector snapshot|loop|status` (poll floor 60 s —
  faster polling adds nothing against a ~hourly publisher) and GET
  `/api/collector/status` (read-only, tested).

**Endpoints actually verified (live, bounded)**

| Endpoint | Result |
|---|---|
| `raw.githubusercontent.com/.../data/market/live.json` | HTTP 200, 362 quotes (362 valid, 0 flagged/duplicate/rejected), newest row stamp 15:14:59 NPT |
| `.../data/market/status.json` | HTTP 200, `is_open: false`, `last_checked 10:17 NPT` |
| `.../data/market/indices.json` | HTTP 200, 4 indices; **NEPSE 2625.93**, generated 15:19 NPT |
| `.../data/market/summary.json` | HTTP 200, 6 metrics; turnover matches history for 2026-10-16 exactly |
| `.../data/market/top_stocks.json` | HTTP 200, 218/106/348/348/348 rows across the five boards |
| `.../data/market/sector_indices.json` | HTTP 200, 17 definitions (no current values — stated, not faked) |
| `.../data/market/history.json` | HTTP 200, 234 session days (2025-02→2026-10-16) |

**Live verification results (isolated temp DB + JSON dir; two cycles, ~4.6 s each)**
- Run 1 + 2: both `SUCCESS`, 1992 rows inserted each, `business_date
  2026-10-16` attested 3/3 (turnover 4,880,089,108 = history; shares
  13,376,489; transactions 39,295).
- Freshness measured, not asserted: snapshot observation 15:19 NPT vs
  retrieval 22:12 NPT → age 27,471 s → **LAST-CLOSE** (market closed);
  `status.json`'s own last-check labelled `stale` — an older stamp than its
  cadence allows, reported as measured. **No sub-minute source was (or can
  be) claimed: NEPSE's official `/api/nots/*` remains 401 behind its token
  and is not bypassed.**
- Cross-verified NIMB LTP 206.2 in DB == bundle; NEPSE index close 2625.93 in
  DB == upstream; top gainer CKHL +14.82%.
- `/api/collector/status` served the live-collected run (status success,
  freshness last-close, 2 runs of history).

**Tests: `pytest` → 2234 passed, 0 failed, 0 errors/skips** (2200 prior +
30 new collector tests + 2 new `/api/collector/status` tests + 2 new
`fetch_market_extras` tests, all network-mocked; fixtures mirror the actual
published payload shapes). Gates: `ruff check .` clean; `ruff format --check .`
237 files clean; `node --check web/static/app.js` OK; `route_inventory.py`
→ 107 routes, all test-referenced.

**Honest limits (unchanged)**
- Sub-minute/real-time live NEPSE data remains **BLOCKED** behind the
  exchange's anti-bot token; this collector captures the freshest published
  state (~hourly in-session) and labels it truthfully.
- `status.json`'s open/closed flag is the publisher's ~daily check and is
  labelled by its own age; staleness of that file does not imply market state.
- Rankings/summary carry no source timestamps, so their freshness is
  `unknown` by design; the run envelope supplies the newest statement the
  source publishes anywhere in the bundle.
- Production untouched (PID 26596, :8710 health 200). Gate `MEGATOOL_NEPSE_API_AUTHORIZED` remains unset. No git write operations performed.

## Session 2026-10-17 — dashboard treemap heatmap, five chart drawing tools, Overkill-list determination

### 1. Dashboard turnover heatmap — IMPLEMENTED, TESTED-PASS
- `megatool/market_dashboard.py`: new `heat()` — turnover-weighted tiles from the
  live quote board; a quote lacking either a published percent change or a
  non-zero turnover is **excluded, never estimated**; equal-turnover ties break
  on symbol (arrival-order independent); `heat` key added to `build_dashboard`.
- API: `/api/market/dashboard` returns `tiles/covered/total_quotes/note`;
  browser-verified at :10000 — **120 tiles, meta "120 tiles of 348 covered · 362
  quotes"**, note reads "Symbols the source left without either are excluded,
  not estimated." Screenshot evidence: `/tmp/mt_heatmap2.png` (real GHL/KBL/
  TAMOR/NIMB/MFIL/HEI tiles; greens/reds by published pct; GHL largest by
  turnover 204,930,344 → 310.9 +2.27%).
- Renderer: pure-JS squarified treemap (Bruls/Huizing/van Wijk) in `app.js`
  (`squarify`, `heatColor`, `renderHeat`); big tiles labelled (sym + pct),
  small tiles label-free with full values in the tooltip; `.heat-grid`/
  `.heat-tile` styles appended to styles.css.
- Tests: `test_market_dashboard_assembles_one_payload_and_labels_sources`
  extended (`heat` key + tile honesty invariants); new
  `test_heat_excludes_unknown_pct_and_turnover_honestly` (exclusion + tie
  stability) — pass.

### 2. Chart drawing tools: trendline / ray / channel / text / measure — IMPLEMENTED, TESTED-PASS (browser-verified)
- Existing tools were fib retracement/extension + horizontal line only. Added:
  `trendline` (2-anchor segment), `ray` (2 anchors, projects 30 NEPSE sessions
  past the right edge with Fri/Sat skip and rightOffset), `parallel channel`
  (3rd click sets the channel offset; the offset anchor is draggable), 
  `text note` (single anchor + prompt; note text edited from the drawing list),
  `measure` (Δ price (Δ%) · bars count in the series title, dashed span box).
- Click flow reworked in `onChartClick` (one-click set, three-click set),
  anchors/handles extended to a third point (`p3` dragging), drawing list gains
  an Anchor-3 column and ratios editing only for fib types; undo/redo/persist/
  export unaffected.
- Verification: drove real `subscribeClick`-equivalent params through
  `onChartClick` for all six tool types on NIMB (120-bar chart); screenshot
  `/tmp/mt_drawings.png` shows trendline segments, ray projecting past the
  right edge, "measure −3.40 (−1.74%) · 31 bars" labels, channel lines,
  "NIMB breakout watch" text marker, fib 0.618/0.786 levels, numbered anchors.
  Test drawings then wiped (`mt-drawings-NIMB` removed) — workspace clean.
- `node --check app.js` pass.

### 3. "Global Overkill" / "Nipsy (NEPSE) Overkill" lists — NOT RECOVERABLE (stated honestly)
- Every candidate document was now examined:
  - Text PDFs (`ALL THE CONTENT…`, `The Phases COMPLETE !`, 
    `digitized_trading_ledger_and_notes.pdf`, `DASHBOARD content.pdf`):
    full-text search for `overkill` in any case → **0 hits** in all four.
  - Both `.pages` archives: every `.iwa` member carried through a
    Snappy-framing decoder + raw byte scan — **0 hits** (raw-literal scan of
    compressed streams covers strings stored verbatim).
  - `WRITTENdata.pdf`: 52 pages, all scanned handwriting — rendered pages 1,
    26, 52 at low DPI and inspected: personal trading notebook (per-scrip
    pools, settlement figures, IPO trackers). No feature lists; not OCR'd
    exhaustively, but no list-like content and no "Overkill" headings.
- Therefore the two original lists could not be retrieved and parity with
  them **cannot be honestly claimed**. Feature coverage is instead grounded in
  (a) the master spec fragments of "ALL THE CONTENT" (master analytical
  dashboard/quant research specification) and (b) the 106 reference
  screenshots, all implemented and labelled per-feature.

### 4. Environment/dev notes
- Dev server restarted to load the new `market_dashboard` module; still
  `MEGATOOL_DATA_DIR=data/dev/release` on :10000 (holds the DuckDB lock).
  Prod :8710 untouched.
- No git operations performed this session.

---

## Session 2026-10-17b — relative-strength multi-timeframe, volume profile, trailing stops, gaps/breakouts

### 1. Relative strength — the "no index consumer" gap is closed AND now multi-timeframe
The last report said `relative_strength` was disabled for lack of an index
consumer. Inspection showed that had **already been repaired** in an earlier
session (store holds the official NEPSE composite from published files —
6,720 rows 1997-07-20 → 2026-10-16; `ranking.relative_strength` factor data-driven;
`/api/bars/{symbol}/relative-strength` with benchmark selection, aligned-date
inner join, excess return, coverage warnings; chart ratio overlay;
scanner/screening metric; research topic). This session verified it live
(NIMB 60-bar: stock +4.45 %, index +1.38 %, excess **+3.07 pp**, aligned 837/837
bars) and closed the remaining checklist gap — **comparisons across multiple
timeframes in one call**:

- `megatool/rs_timeframes.py` — `parse_lookbacks` (validated, deduped, ≤6 —
  bounds 2..2000) + `timeframe_rows` (exact per-lookback stock/bench/Excess
  returns over the same aligned dates; per-lookback availability with the
  exact reason; never silently shortened).
- Endpoint grew an optional `lookbacks=20,60,120,250` query (400 with a
  precise message on any bad list); the single-window shape is unchanged.
- UI: "Lookback set" input + a Lookback/Stock/Index/Excess/Window-dates/Why
  unavailable table; default `20, 60, 120, 250`.
- Browser-verified on NIMB: table rows 4.48 pp / 3.07 pp / 2.49 pp / 0.03 pp
  matched the API response `[4.4788, 3.0744, 2.4856, 0.0258]` **exactly**.
- Sector-relative benchmark: still honestly unavailable — no sector
  sub-index series exists in any permitted source (binayabaral publishes the
  composite only; official sub-indices are behind the 401 token). Multiple
  GitHub-tree listings confirmed it. No substitute benchmark was invented.
- Tests: `tests/test_rs_timeframes.py` — 20 passing.

### 2. Volume profile — group 5's missing capability (IMPLEMENTED + TESTED-PASS)
`megatool/ta/profile.py` + `/api/bars/{symbol}/volume-profile` + chart
Analysis layer. Daily-bar profile with overlap-proportional allocation
(half-open convention), POC (tie → lower price), classic 70 % two-sided
value-area expansion, strict HVN/LVN. A pointer/label mixing bug in the
value-area expansion was caught by the hand-set arithmetic tests *before*
it ever ran on data and fixed. Tested: 11 module/endpoint tests; browser:
NIMB layer drawn (POC 192, VAH 210, VAL 189), drawer count "3 found".
The response states plainly that the cross-session split is an allocation
model, not observed trade distribution, and that nothing is a forecast.

### 3. Trailing stops — group 18's missing engine (IMPLEMENTED + TESTED-PASS)
`megatool/ta/trailing.py` + `/api/bars/{symbol}/trailing-stop` +
advanced-analysis card. Chandelier (HH(N) − k·ATR, Wilder), swing-low (M
bars) and percentage-from-peak methods behind one shared ratchet: causal
per-bar stops (uses bars ≤ t), moves up never down, exit requires a LATER
bar's low at the stop, fill recorded at the stop level with the no-open-price
limitation stated, rule values above the running close recorded but never
applied, malformed bars end the chain instead of being bridged. 12 tests
(hand-recomputed Wilder ATR chain); browser-verified on NIMB via the card:
837 bars, stop series exists, historical exit at bar 36 @ 183.04. Long side
only — NEPSE retail shorting is not modelled, said everywhere it matters.

### 4. Gaps & false breakouts — group 6's missing classifiers (IMPLEMENTED + TESTED-PASS)
`megatool/ta/gaps.py` + `/api/bars/{symbol}/gaps` + `/api/bars/{symbol}/breakouts`.
Gaps are reported as facts with a stated-rules ATR-scaled class and a *post
hoc* `closed_within_bars`; the commitment that holes are never read as gaps is
in the code and tested. Breakouts beyond a rolling extreme are classified
true/false/unconfirmed with the measured run beyond the level; unconfirmed
breakouts are never counted as true. 13 tests; live-verified on NIMB (4 gaps
— classes common/runaway — with one honestly size_atr-free during the ATR
warmup; 4 breakouts including a planted-true one).

### 5. Full-suite / inventory / Kronos / workflow checks
- Full pytest run after all changes: **2316 passed, 0 failed** (2273 + 43 new;
  deficit would occur if any test failed — none printed; progress reached
  100 % and no FAILED/ERROR lines exist in the log).
- `ruff check` + `ruff format` clean; `node --check` clean.
- Route inventory regenerated: **117 routes** (was 113), all Test-referenced.
- Kronos re-verified: status shows Kronos-small + Kronos-base + tokenizer
  present, Mini absent → availability honest; real MPS inference ran live
  (5-step forecast, 4.65 s, rows `is_predicted=true` with the honesty note).
- Research workflow E2E: real backtest on NIMB (−26.12 % sma_cross) → saved
  as an experiment → `/api/experiments/1/reproduce` returned the **same
  total_return −26.1193** → deleted (cleanup; methodology confirmed, not data).
- `/api/sources` re-labelled correctly today: official NEPSE API BLOCKED
  (401 token), GitHub community dataset available with terms note.
- Production server :8710 untouched (health 200; PID 26596 never signalled).
- Cache-buster cycled kronos2 → kronos3 → kronos4 → kronos5 → kronos6.

### 6. Honest limitations
- Sector-relative RS remains unavailable (no permitted sector-index source).
- Trailing-stop fills are stop-level, not gap-open fills (module receives no
  open prices; states that in `ordering_rule`).
- Volume-profile landmarks are daily-bar models; intraday profile needs data
  that does not exist in this store.
- Gap "breakaway/exhaustion" labels are charting-literature rules, not
  predictions; `closed_within_bars` looks forward by definition and is
  flagged accordingly.
- Kronos-mini weights still not downloaded (folder absent → reported absent).

---

## SESSION 18 RESULTS (2026-10-17, later) — declutter, unified history, rail popovers, tool wave 2, Kronos chart + Mini

### Backend
- Full suite after all changes: **2331 passed / 0 failed / 0 skipped**
  (`pytest tests/ --junitxml=/tmp/pytest18.xml`, XML parsed: tests=2331,
  failures=0, errors=0; stdout buried under numpy/swig warnings as usual).
- Kronos + API subset re-run after the per-variant tokenizer/context change:
  **174 passed / 0 failed**. Existing `context_len=600` rejection for base
  still holds; nothing referenced mini's blocked status.
- `ruff check megatool/`: clean. `ruff format --check`: one folder-tuple
  reflow applied to `megatool/kronos_service.py`, then clean.
- Dev server restarted (:10000) after backend changes with
  `MEGATOOL_DATA_DIR="$PWD/data/dev/release"`; `/api/health` OK
  (515,327 bars / 372 symbols). Production :8710 untouched.

### Kronos Mini (new capability, evidence-based)
- Official artifacts verified against the HF model card and `/api/models`:
  `NeoQuasar/Kronos-mini` 4,108,192 params F32 → model.safetensors exactly
  **16,440,776 bytes** on disk; `NeoQuasar/Kronos-Tokenizer-2k` → exactly
  **15,842,376 bytes**. MIT licence, ungated.
- Real inference on MPS via the running API: NIMB ctx=512 → 5 predicted rows,
  inference 0.966 s (load 0.244 s); NABIL ctx=2000 → 5 rows, 0.585 s —
  context beyond 512 **actually works** for mini (base/small still cap at
  512 and horizon 4000 is schema-rejected).
- Honest walk-forward (`/api/kronos/evaluate`, NABIL, 2 windows, horizon 5):
  kronos_mae_close 4.3331 vs naive_last_close 4.33 (marginally worse) and
  better than drift20 6.3194; direction 70%. Reported un-cherry-picked; the
  endpoint outputs `best_mae_competitor: naive_mae_close`.
- Browser E2E: popover availability "Kronos-mini: AVAILABLE — device Apple
  MPS", context input clamps to 2048, hint "≤ 2,048 context bars · 16 MB
  weights · Tokenizer-2k", forecast drawn as amber predicted candles,
  hide/show/remove verified, AI Forecaster variant note updated
  ("official weights on disk (16 MB) · context ≤ 2,048 bars · official
  Tokenizer-2k"). Screenshot `/tmp/z18_mini.png`.

### Frontend E2E (real Chromium via Playwright, `.venv` pw)
- 40-check consolidated sweep on NIMB (`/tmp/z18_final.py`) + diagnosis runs
  (`/tmp/z18_diag.py`) + retry-verified rerun (`/tmp/z18_i.py`): all PASS.
  First-pass failures audited one by one: five were the documented
  Playwright swallowed-click artifact + one test coordinate inside the price
  axis margin; two were real bugs (B-72 eraser status overwrite, B-73 tool
  switch leak) — fixed and re-verified. Zero console errors, zero pageerrors
  across the final runs.
- Undo/redo chain asserted step-by-step (drawings + zoom + pan), including
  the fixed stack-leak bug (B-69) and the pan-release drag guard (B-70).
- 17/17 second-wave drawing tools verified created + rendered with per-tool
  series/marker counts; persistence round-trip across reload verified.
- Cache-buster `?v=d18` served for app.js / kronos_ui.js / styles.css.

### Honest limitations
- Mini evaluation used 2 windows (fast probe); a deeper walk-forward sweep is
  not yet run — numbers above are not a claim of edge.
- Kronos chart overlay currently shows one resident forecast (the latest
  run); multi-experiment compare overlays remain future work.
- Intraday/NEPSE official API blocks unchanged; letter-cap control caps
  occurrences, not rule types.

## Session 20 (2026-10-17) — final verification + deliverables
- Backend pytest: 2331 passed, 0 failed, 0 errors, 0 skipped (73.9s).
- Frontend: node --check clean (app.js, kronos_ui.js). Cache-buster ?v=d34.
- Browser sweep (isolated dev :10000): 0 console/page errors across overview,
  research, charts, fullscreen, replay, autosave, Kronos, custom formula.
- Overview: banner normal, 4 totals, 11 gainers/losers/active.
- Research: Full Report 40 rows for NABIL; answer panel honest empty state.
- Charts: NABIL 120 bars, OHLC legend correct, fullscreen (view-charts) + Esc exit.
- Custom formula DSL: save/reload auto-apply (1 series), injection rejected.
- Kronos: mini inference 4.8s MPS, chip "PREDICTED · Kronos-mini · 10 candles".
- New deliverables: ALGORITHM_CATALOG.md (150 entries), ALGORITHM_IMPLEMENTATION_MATRIX.md
  (40 deeply integrated), MATHEMATICAL_VALIDATION_REPORT.md, AI_MODEL_DEPENDENCY_MATRIX.md,
  KRONOS_ACCEPTANCE_REPORT.md, DEPLOYMENT_READINESS_REPORT.md, SECURITY_AUDIT_REPORT.md,
  DATA_QUALITY_REPORT.md.

---

## Session 27 — chart interaction tests (2026-10-18)

### Automated

| Gate | Command | Result |
|---|---|---|
| Full suite | `MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings` | **2599 passed, 0 failed, 0 errors, 0 skipped, exit 0** (`$TMPDIR/full3.log`) |
| Index OHLC history (incl. the two new API fields) | `pytest -q tests/test_index_ohlc_history.py` | 15 passed, exit 0 |
| JS syntax | `node --check web/static/app.js` | clean |

### Browser (real trusted events via `playwright-cli`, no mocks)

Environment: dev server `127.0.0.1:10000`, `data/dev/release`, build `app.js?v=wb12`.
A gesture is "real mouse" when driven by the CLI's `mousemove`/`mousedown`/`mouseup`
(the library's own listeners must accept it), as opposed to `eval` of a handler.

| # | Case | Instrument | Result |
|---|---|---|---|
| 1 | Load daily chart | NABIL | 120 obs default window, candles, meta `NABIL · Daily · 120 obs · 2026-04-20 → 2026-10-15` |
| 2 | Load 1-year window | NABIL | 250 obs, meta correct |
| 3 | Load `#range=750`, candles | NEPSE | 750 obs, 750/750 genuine OHLC |
| 4 | Index meta honesty | NEPSE | `index · 2217 OHLC / 3079 close-only · candles from 2016-11-28` |
| 5 | Index chart types enabled | NEPSE | 0 options disabled (candles/bars/hollow/Heikin available) |
| 6 | OHLC legend | NEPSE | `O/H/L/C + T/O 4,717,028,104` (turnover labelled, not `V`) |
| 7 | Console cleanliness | NEPSE then NABIL | **0 errors, 0 warnings** |
| 8 | Analysis layer toggle | NABIL | S/R drawn: 10 lines of 73 zones; console clean |
| 9 | Viewport preserved across layer reload | NABIL | `{81.8, 167.2}` → `{81.8, 167.2}` (exact) |
| 10 | Viewport preserved across tab switch | NABIL | `to` unchanged (249); `from` micro-shift only from autoSize re-measure, no `fitContent` |
| 11 | Trendline draw (2 real clicks) | NABIL | 1 drawing, `t1/p1/t2/p2` set, status "Trendline added" |
| 12 | Body hit-test at line midpoint | NABIL | `dist 0`, anchor hit `null` (previous builds could only hit anchors) |
| 13 | Click-select (cursor tool) | NABIL | `drawSelectId` set, 2 selection markers, status offers Delete |
| 14 | Selection does not consume undo | NABIL | undo stack stays 1, redo stack 0 |
| 15 | Drag drawing body (3 moves) | NABIL | anchors moved t1 2026-01-27→2026-05-19, p1 503.43→549.54 |
| 16 | Chart does not pan during drag | NABIL | visible range 0→249 unchanged after the drag |
| 17 | Drag with placement tool active | NABIL | drawing does not move (tool owns the click) |
| 18 | Eraser click on line body | NABIL | 1 → 0, status "Drawing erased (Undo restores it)" |
| 19 | Cmd+Z after erase | NABIL | 0 → 1 (undo stack 1, redo stack 1) |
| 20 | Delete key on selection | NABIL | 1 → 0, status "Drawing deleted (Cmd/Ctrl+Z restores it)" |
| 21 | Cmd+Z then Cmd+Shift+Z | NABIL | 0 → 1 → 0 (redo consumed) |
| 22 | Delete/Backspace while typing | NABIL | `#symbol-input` focused → drawings unchanged (no accidental delete) |
| 23 | Escape clears selection | NABIL | `drawSelectId` null, 0 markers, status "Selection cleared" |
| 24 | Clear dialog contents | NABIL | 3 scoped rows with live counts (drawings 1 / indicators 4 / analysis 1), all enabled |
| 25 | Clear drawings only | NABIL | drawings 0; indicators 3 and layers `{sr:true}` untouched; modal closed |
| 26 | Cmd+Z after clear | NABIL | drawing restored (1) |
| 27 | Palette open + results | NABIL | 80 results, grouped, keyboard footer, count shown |
| 28 | Palette search relevance | — | `rsi`→Rate of Change/RSI; `horizontal line`→Draw: Horizontal line; `elliot`→Elliott Wave + tools; `seasonality`→view; `support`→S/R layer; `clear`→Clear chart…; `candle`→Candlestick entries |
| 29 | Palette disabled honesty | — | `alpha coder` → listed disabled with reason ("Not implemented — the sandboxed custom-formula DSL is the closest built feature") |
| 30 | Palette runs an action | NABIL | "Relative Strength Index" clicked → instance added, pane created, status "rsi added to the chart." |
| 31 | Pane collapse / expand | NABIL | pane `hidden` true → false |
| 32 | Pane taller (×2) | NABIL | height 120px → 240px, persisted on the instance (`paneHeight: 240`) |
| 33 | Pane ✕ remove | NABIL | instance + pane + header removed (inds sma, macd; 1 pane) |
| 34 | Drawer Undo after pane ✕ | NABIL | instances restored to sma, macd, rsi; 2 pane headers back |
| 35 | Indicator catalog coverage | — | `81 of 81 registered`, 82 rows, filters all/favs/trend/momentum/volatility/volume/other |
| 36 | Keyboard listener audit | — | Cmd/Ctrl+K unique to the palette; Cmd/Ctrl+Z guarded to the chart view and to non-typing targets; Delete guarded the same way; four `Escape` handlers with distinct idempotent effects |

### Palette coverage against the owner's named surfaces

`buildPaletteItems()` inspected live (async, 257 items). Every one of the 43
names the owner listed has its own entry — **0 missing**:

* **Side panels (18):** Top Stocks, Watchlist, Shareholder Watchlist, Chart
  Share, Chart Calendar, Candle Stick, Fresh Indicator Signal, Pine Script,
  Stock Alert, SMC/Support & Resistance, Trend Line Breakout, Volume Scan,
  Seasonality, Swing Trader, Stock Heat Map, Alpha Rider, Terminal, Alpha Coder.
* **Chart modes (12):** Main Chart, Multi Chart, StageAnalysis Chart,
  Seasonality Chart, Market Breadth Mode, Foot Print Mode, Elliot Wave Mode,
  Smart Money Holding, Floorsheet Mode, Trading Simulator, Minervini SEPA-VCP
  Chart, O'Neil CAN-SLIM Chart.
* **Scanners (7):** Parameter Scan, Draw To Scan, MTF Scan, Trade Monitor, Chart
  Patterns, Divergences, Relative Strength.
* **Trade signals AI (3):** Free AI Signals, Premium AI Signals, Open Algo
  Signal.
* **Terminal (3):** My Algorithms, Portfolios, Workspace.

25 resolve to live actions; the rest are **disabled with a specific reason**
(e.g. "Multi Chart — this build draws one chart per view"; "Divergences — not
implemented as a dedicated view"; "Shareholder Watchlist — no
shareholding-register source in this build"). No live result is a no-op.

### Not tested this session (unchanged from session 26, still as reported there)

Compare modes; breadth / seasonality / swing views; backtest; portfolio, journal
and watchlist CRUD; replay; Kronos overlays; floorsheet; screener preset runs;
Renko/Kagi/P&F (genuinely absent — see `REMAINING_BLOCKERS.md`).

---

## Session 29 — chart-objects manager completion + measured Fibonacci viewport (2026-10-18)

Focused bug-fix pass following the read-only session-28 verification. Frontend
only; production `8710` untouched; dev `127.0.0.1:10000` (`data/dev/release`);
cache-buster `app.js?v=wb23`.

### Automated gates

| Gate | Command | Result |
|---|---|---|
| Full suite (browser module skipped) | `MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings` | **2,660 passed, 0 failed, 0 errors, 8 skipped, exit 0** (`$TMPDIR/full_s29.log`: 2,660 `.` + 8 `s`, 0 `F`/`E`, 38 lines) |
| New browser regression module (opt-in) | `MEGATOOL_BROWSER_TESTS=1 .venv/bin/python -m pytest -q -p no:warnings tests/test_browser_objects_manager.py` | **8 passed, exit 0** (`/tmp/browser_tests.log`) |
| JS syntax | `node --check web/static/app.js` | clean, exit 0 |

The 8 skips in the default run are `tests/test_browser_objects_manager.py`; the
module is skipped unless `MEGATOOL_BROWSER_TESTS=1` (and skips itself if
`playwright-cli`/the dev server is absent), so the offline suite is unchanged.

### Browser matrix (real trusted events; `docs/evidence/wb24-objects-quick.png`)

| # | Case | Result |
|---|---|---|
| 1 | Quick-layer overlays listed in the Objects manager (`SMA 20/50`, `EMA 20`, `Bollinger`, `Volume`) | **PASS** — 4 rows with label/type/owner "Quick layers (toolbar)" |
| 2 | Oscillator panes listed (`RSI`, `MACD`) | **PASS** — `quick-rsi`/`quick-macd` rows, panes in `state.charts` |
| 3 | DOM **Hide** on a quick overlay | **PASS** — series `visible:false`; **Show** restores |
| 4 | DOM **Hide** on the RSI pane | **PASS** — pane element `hidden`; **Show** restores |
| 5 | **Remove** the RSI pane | **PASS** — `chart.remove()`, element cleared + hidden, `#ind-rsi` unchecked, row gone |
| 6 | **Remove** the swings quick layer (owned annotations) | **PASS** — owned 27 → 0 markers, `#ind-swings` unchecked, row gone |
| 7 | Detector markers **restore after a full page reload** (patterns) | **PASS** — 9 markers / 9 series → reload → 9 / 9 |
| 8 | Candle markers **restore after reload** (candles) | **PASS** — 122 → 122 |
| 9 | **No duplicate objects** across 3 full reloads | **PASS** — `quick`/`markers`/`candle`/`pat`/`groups` identical each run |
| 10 | Candle-marker cross-symbol leak | **FIXED** — NABIL (layer on) 122 → ADBL (no layers) 0 |
| 11 | Pattern-overlay cross-symbol leak | **FIXED** — NABIL 9 → ADBL 0, `#pattern-overlay` unchecked |
| 12 | Layer-off removes its plots/annotations | **PASS** — patterns 9 → 0 markers, 9 → 0 series |
| 13 | **Manual Fibonacci viewport** (`fib_retracement`) | **PASS** — zoomed to `{75,175}` → placed via the real click handler → `{75,175}`; drawing committed (5 series) |
| 14 | **Manual Fibonacci viewport** (`fib_extension`, expanded mode) | **PASS** — `{87,187}` → `{87,187}` |
| 15 | **Automatic Fibonacci viewport** (`fib` layer) | **PASS** — `{75,175}` → `{75,175}`, 8 fib series added |
| 16 | **Automatic Fibonacci viewport** (expanded mode) | **PASS** — `{87,187}` → `{87,187}` |
| 17 | Existing drawings/indicators preserved through auto fib | **PASS** — drawings unchanged; a freshly added catalog `sma(9)` still present |
| 18 | Browser console cleanliness | **PASS** — `playwright-cli console error` → `Errors: 0, Warnings: 0` |

Tolerance: the visible logical range is compared **exactly** (`from`/`to` rounded
to 3 dp). A `fitContent()` would reset the window to the full series (≈`{0,249}`),
so the preserved `{75,175}`/`{87,187}` windows are unambiguous evidence that no
re-fit, reset, remount or auto-zoom happened.

### Bugs closed this session

B-107 (quick-layer overlays/panes missing from the Objects manager) ·
B-108 (candle-marker cross-symbol leak) · B-109 (pattern markers lost on reload) ·
B-110 (pattern-overlay checkbox cross-symbol leak) · B-111 (duplicate/orphan
safety measured over repeated reloads). Full detail in `KNOWN_BUGS.md`.

### Not tested / honest gaps (unchanged or new)

* **Quick-layer toggles are not persisted** → a swing-marker quick layer cannot
  reconstruct after a reload (its config is not stored). Persistent detectors are
  the analysis layers, which **do** reconstruct (case 7/8). `REMAINING_BLOCKERS.md`
  §23.
* **Per-marker suppression is session-only** — a reload rebuilds the detector's
  full set from its persisted layer flag. Deliberate (persisting it would store
  transient UI state against recomputed output). §24.
* The manual/automatic Fibonacci measurements and every case above are
  **browser-measured** (a canvas cannot be measured from pytest); the browser
  module automates them but is **opt-in** and therefore **skipped** in the default
  offline run.
