# Session 29 — completion report (2026-10-18)

Scope: a focused bug-fix pass on top of session 28, following the read-only
verification that found (a) quick-layer overlays/panes missing from the Objects
manager and (b) detector markers rebuilt or lost on reload. **No rebuild, no
reversal of prior work, no new disconnected frontend.** The existing app is the
source of truth; working features, data and user configs were preserved.

Status labels used exactly: **IMPLEMENTED** · **TESTED-PASS** · **TESTED-FAIL** ·
**NOT-TESTED** · **BLOCKED** · **APPROXIMATION** · **DATA-DEPENDENT** ·
**NOT IMPLEMENTED (backlog)**.

## Safety envelope actually held

* Production uvicorn on **port 8710 was never signalled** — no kill, no restart, no
  modification. All work was served from `data/dev/release` on `http://127.0.0.1:10000`.
* Production DBs and Kronos model weights untouched. No GPU/training work.
* **No commits, no pushes, no deploys.** All work remains uncommitted on `main`
  (HEAD `b6c3659`). No destructive git operations.
* No secrets written to logs or reports. No paid APIs, no infra changes.
* Browser tests snapshot and restore every persisted per-symbol config they touch
  (layers, catalog indicators, drawings), so a test run never clobbers user setup.

## What was delivered (all browser-verified unless noted)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | **Quick-layer objects in the Objects manager** — the chart-toolbar toggles (`SMA 20/50`, `EMA 20`, `Bollinger`, `Volume`, `RSI pane`, `MACD pane`, `Swings`, `Close-based pivots`) are now first-class objects | **IMPLEMENTED + TESTED-PASS** | `loadChart` registers one `state.quickObjects` descriptor per toggle; manager gained a **Quick layers** group (label/type/owner/visibility + Hide/Show + Remove). Browser: 4 overlays + 2 panes listed with owners; DOM Hide flips the real series/pane visibility; Show restores. `docs/evidence/wb24-objects-quick.png`; `TEST_RESULTS.md` §29 cases 1–4 |
| 2 | **Hide/Remove act on the real chart object, not just the row** | **IMPLEMENTED + TESTED-PASS** | Removing `quick-rsi` deletes the pane chart (`chart.remove()`), clears + hides the element, unchecks `#ind-rsi`, drops the row. `TEST_RESULTS.md` §29 case 5 |
| 3 | **Remove clears owned annotations (no orphans)** | **IMPLEMENTED + TESTED-PASS** | `quick-swings` owned 27 markers → Remove dropped all 27 from `state.markers`, unchecked `#ind-swings`, row gone. `TEST_RESULTS.md` §29 case 6 |
| 4 | **Detector markers persist across reloads when safely reconstructable** | **IMPLEMENTED + TESTED-PASS** | Patterns layer was lost on reload (B-109) — the layer path now fetches (`loadPatternPanel`) instead of re-rendering a panel that needs an in-memory scan. Browser: 9 markers/9 series → full page reload → 9/9. Candles: 122 → 122. `TEST_RESULTS.md` §29 cases 7–8 |
| 5 | **No duplicate objects across repeated reloads** | **IMPLEMENTED + TESTED-PASS** | 3 full page reloads: `quick`/`markers`/`candle`/`pat`/`groups` byte-identical each run. `TEST_RESULTS.md` §29 case 9 |
| 6 | **Detector-marker cross-symbol leaks fixed** | **IMPLEMENTED + TESTED-PASS** | B-108: `destroyCharts` resets `state.candleMarkers` (NABIL 122 → ADBL 0). B-110: `#pattern-overlay` synced to the symbol's layer flag (NABIL 9 → ADBL 0). `TEST_RESULTS.md` §29 cases 10–11 |
| 7 | **Fibonacci viewport measured** (the session-28 gap) — manual + automatic, normal + expanded | **IMPLEMENTED + TESTED-PASS (browser-measured)** | Manual `fib_retracement`/`fib_extension` and automatic `fib` each preserved the visible logical range byte-for-byte: `{75,175}` normal, `{87,187}` expanded. Existing drawings + a freshly added catalog indicator intact. No `fitContent`/reset/remount/auto-zoom. `TEST_RESULTS.md` §29 cases 13–17 |
| 8 | **Browser console cleanliness** | **TESTED-PASS** | `playwright-cli console error` → `Errors: 0, Warnings: 0` after the quick-layer + reload + fib flows. `TEST_RESULTS.md` §29 case 18 |
| 9 | **Opt-in browser regression module** | **IMPLEMENTED + TESTED-PASS (opt-in)** | `tests/test_browser_objects_manager.py` (8 cases) drives a real browser via `playwright-cli`. 8 passed / exit 0 with `MEGATOOL_BROWSER_TESTS=1`; skipped (8) in the default offline suite |

## Test headline

* **Full suite: 2,660 passed / 0 failed / 0 errors / 8 skipped — exit 0**
  (`$TMPDIR/full_s29.log`; 2,660 `.` + 8 `s`, 0 `F`/`E`, 38 lines). The 8 skips
  are the new opt-in browser module.
* **New browser module:** `MEGATOOL_BROWSER_TESTS=1 .venv/bin/python -m pytest -q
  tests/test_browser_objects_manager.py` → **8 passed, exit 0**
  (`/tmp/browser_tests.log`).
* No backend code changed this session, so the passed total is unchanged from
  session 28; the added coverage is the 8 browser cases.
* Command for the full suite:
  `MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings`
  (this pytest build omits the terminal summary line; counts are the
  progress-mark totals over the captured logs and the exit code is 0).
* `node --check web/static/app.js` → exit 0 after every edit. Cache-buster
  `app.js?v=wb23`.

## Honesty notes (what is *not* claimed)

* **Quick-layer toggles are not persisted** (display toggles; reset to the HTML
  default on reload). Therefore a **swing-marker quick layer cannot reconstruct
  after a reload** — its own configuration is not stored anywhere. This is reported
  as a real limitation, not a fabricated restore. The persistent equivalent is the
  right-hand **Analysis layers** (candles/patterns/Elliott/harmonic/S/R/Fib/profile),
  stored per symbol in `localStorage['mt-chart-layers-<symbol>']`, which **do**
  reconstruct (row 4). `REMAINING_BLOCKERS.md` §23.
* **Per-marker suppression is session-only.** Hiding or removing an individual
  detector marker is not persisted; a reload rebuilds the detector's full set from
  its persisted layer flag. Persisting it would store transient UI state against
  recomputed output. `REMAINING_BLOCKERS.md` §24.
* **The Fibonacci measurements are browser-measured**, not covered by the offline
  pytest suite — a canvas cannot be measured from pytest. The browser module
  automates them (rows 1–9) but is opt-in, so the default suite skips it.
* No fabricated persistence, data, tests, indicator results or completions.
* No commits/pushes/deploys; production untouched.

## Bugs closed this session

* **B-107** — quick-layer overlays/panes missing from the Objects manager.
* **B-108** — candlestick markers leaked across symbols when the layer was off.
* **B-109** — pattern markers were lost on reload (panel re-render, no fetch).
* **B-110** — `#pattern-overlay` checkbox leaked across symbols.
* **B-111** — duplicate/orphan safety was unmeasured; now verified.

Full detail in `KNOWN_BUGS.md` (session-29 section).

## Blockers / owner decisions (unchanged)

1. **Kronos NABIL GPU fine-tune** — BLOCKED, awaiting explicit owner approval
   (`KRONOS_FINAL_GO_NOGO.md`).
2. **Independent source verification** — only community source
   `github.com/Aabishkar2/nepse-data` (no LICENSE; L-03).
3. **python-dotenv CVE upgrade** — owner decision pending.
4. **Commit / push** — not authorized (~275 uncommitted paths, HEAD `b6c3659`).
5. **Corporate actions** — all prices `unadjusted`; `trading_calendar.json`
   holidays empty.

## Deliverables updated / written this session

* `web/static/app.js` — `state.quickObjects` registration, `Quick layers`
  manager group, `quickObjectHidden`/`toggleQuickObject`/`removeQuickObject`,
  `destroyCharts` resets, `loadPatternPanel` in the layer path, `#pattern-overlay`
  sync.
* `web/static/index.html` — cache-buster `wb23`.
* `tests/test_browser_objects_manager.py` — new opt-in browser regression module
  (8 cases).
* `KNOWN_BUGS.md` — B-107…B-111 + session-29 open gaps.
* `REMAINING_BLOCKERS.md` — §23 (quick-layer persistence), §24 (opt-in browser
  tests).
* `CHART_UX_AUDIT.md` — §2b session-29 surfaces.
* `TEST_RESULTS.md` — §29 headline + 18-case browser matrix.
* `IMPLEMENTATION_STATUS.md` — session-29 header, rows 34–38, commands, next action.
* `CURRENT_PROJECT_STATE.md` — session-29 addendum.
* `CHANGELOG.md` — session-29 entry.
* This report.
