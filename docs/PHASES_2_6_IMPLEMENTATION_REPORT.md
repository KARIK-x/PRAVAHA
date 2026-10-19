# Phase 2–6 implementation report (session 18, 2026-10-16)

This is the **implementation** counterpart to the session-17 audit
(`docs/PHASES_2_6_COMPLETION_AUDIT.md`). The audit said *what was missing*; this
report says *what was built, how it was verified, and what remains*. Status
labels are restricted to: **TESTED-PASS · IMPLEMENTED · PARTIAL · TESTED-FAIL ·
NOT STARTED · BLOCKED · NOT-TESTED**. *Implemented ≠ TESTED-PASS.*

Repository state: `main` @ `b6c3659`, **0 staged, 0 stashes, nothing
committed/pushed**. Production PID 26596 never signalled. Authorization gate
unset. Production DuckDB/SQLite mtimes unchanged (`Oct 15 09:24` /
`Oct 14 15:52`).

---

## A. Implementation summary

The session-17 audit identified four capabilities that were **built but
unreachable** and two required capabilities that were **absent**. All six were
addressed:

1. **Candlestick engine → API → UI.** `megatool/ta/candles.py` (15 patterns, ~94
   engine tests) had **no route and no UI**. Added `GET /api/bars/{symbol}/candles`
   with parameters `start,end,limit,patterns,trend_bars,require_prior_trend`,
   plus public `PATTERN_NAMES` / `PATTERN_CANDLE_COUNT`. The route reuses the
   workspace OHLC-validity segmentation (impossible bars excluded **and counted**,
   never repaired). Status: **TESTED-PASS** (backend) / **IMPLEMENTED** (UI).
2. **Dead chart-marker code repaired.** `plotCandlestickMarkers` was defined but
   never called, read the wrong engine field (`p.rule` vs `p.name`), and
   `plotElliottWave` was a `console.log` stub. `series.setMarkers()` *replaces*
   the whole marker set, so per-source calls erased one another. Replaced with
   dedicated `state.*Markers` arrays flushed in **one** `setMarkers` call.
   Status: **TESTED-PASS** (browser).
3. **Elliott Wave UI.** The engine (`analyze_elliott_extended`) had no UI. Added a
   candidate table (scenario, structure, certainty, evidence, **alternative
   count**, **invalidation**, Fibonacci relations) **plus manual wave labelling**
   of confirmed pivots — stored per symbol in `localStorage`, drawn as a labelled
   polyline. Automatic candidate and manual labelling are presented as distinct
   capabilities. Status: **IMPLEMENTED** / **TESTED-PASS** (browser).
4. **Harmonic UI.** `analyze_harmonic` had no UI. Added a candidate table
   (pattern, direction, measured ratios, matched bands, completion zone,
   invalidation, certainty) and an XABCD overlay + D marker (pivot index → date
   via the full series, filtered to the plotted window). Status: **IMPLEMENTED** /
   **TESTED-PASS** (browser).
5. **Watchlists** (M1 §8.2). The `watchlists` table existed but had no API or UI.
   Added `megatool/watchlists.py` (storage, validation) + CRUD API + a Watchlists
   view. A symbol with no stored bar reports `close: null` **and a reason**.
   Status: **TESTED-PASS**.
6. **Reproducible experiments** (M4 §11.5 steps 8–11). Added
   `megatool/experiments.py`: save / list / get / delete, `reproduce` (re-runs
   through the **same** `_run_backtest_request`), `compare` (metric-by-metric
   deltas with tolerance) and Markdown/JSON export. Config identity is a
   **SHA-256 hash of canonical JSON**. Status: **TESTED-PASS**.

Backend files touched/created: `megatool/api.py` (routes +
`_run_backtest_request`), `megatool/ta/candles.py` (public catalogue),
`megatool/friend_access.py` (read allowlist + denied prefixes), **new**
`megatool/watchlists.py`, **new** `megatool/experiments.py`,
`scripts/route_inventory.py` + `scripts/smoke_live.py` (mutating-route tables kept
identical). Frontend: `web/static/index.html`, `web/static/app.js`.

Test count rose **2016 → 2051** (+35). Route inventory rose **75 → 88** routes,
all test-referenced.

---

## B. Research (≥15 platforms)

Deliverable: **`docs/PLATFORM_RESEARCH_MATRIX.md`** — **20 platforms**, each with
an official source URL, capabilities, interaction patterns, a design idea for a
local NEPSE tool, and a fit rating. TradingView's features page was read directly
this session; the remainder were assessed from each vendor's published official
product/documentation pages (stated honestly in the doc).

Patterns adopted: (1) pattern detection as a **chart toggle + table**, never an
opaque page; (2) **named saved state** (watchlists, saved experiments);
(3) **provenance always visible** (source + `data_as_of`); (4) **reproducible runs
with a stated config** (hash + reproduce + compare); (5) **transparency of any
aggregate** (no bare buy/sell); (6) **progressive disclosure** (advanced panels
collapsed). Deliberately **not** copied: proprietary layouts/colours/branding, a
Pine-Script-like language (the rule builder is a restricted parsed model with no
arbitrary code execution), live brokerage integration, or paid data
redistribution.

---

## C. Go NEPSE

Deliverable: **`docs/GO_NEPSE_INVESTIGATION.md`**.

**Decision: do NOT integrate.** Evidence from static inspection of
`github.com/VoidArchive/go-nepse`:

* Targets the **official** NEPSE production API (`DefaultBaseURL =
  "https://nepalstock.com.np"`, `/api/nots/...`) — the exact surface behind Mega
  Tool's authorization gate.
* Authenticates by **defeating NEPSE's anti-bot token obfuscation** with an
  embedded **WebAssembly** module run through `wazero` (salts → strip character
  positions → `Authorization: Salter <token>`).
* **Impersonates a browser** (fake Chrome UA + client hints) because "some NEPSE
  endpoints reject requests with non-browser user agents".
* Documents **`TLSVerification = false`** in its Quick Start (`InsecureSkipVerify:
  true`) — violates the project's TLS-on rule.
* Immature: v0.2.0 (2026-01-03), 35 commits, 9 stars, core unit/integration tests
  listed as *planned*; known-empty graph endpoints.

**Testing actually performed:** Go is **not installed** locally, and a live call to
NEPSE was **intentionally not attempted** — that would be the very bypass the gate
forbids. Verification was therefore static (source inspection). No network
request to any NEPSE endpoint was made by this session.

---

## D. Phase-by-phase status

| Phase | Status before | Status now | Delta |
|---|---|---|---|
| Phase 2 | PARTIAL | **PARTIAL (advanced)** | Watchlists delivered; saved-screens UI still missing |
| Phase 3 | PARTIAL | **PARTIAL (advanced)** | Candlestick API+markers, Elliott UI, Harmonic UI delivered; manual chart-pattern drawing + pattern-evaluation UI still missing |
| Phase 4 | PARTIAL | **PARTIAL (advanced)** | Experiments + Watchlists panels delivered; dashboard composition, index/RS panels still missing |
| Phase 5 | PARTIAL | **PARTIAL (advanced)** | Experiment save/reproduce/compare/export + report export delivered; custom rule builder + templates still missing |
| Phase 6 | PARTIAL | **PARTIAL (advanced)** | Export + accessibility advances; custom formula catalogue + background jobs (M5) still missing |

No phase is claimed **TESTED-PASS** — the mission's bar (every requirement
reached and exercised) is not met, and saying otherwise would be false.

---

## E. Test evidence (commands)

```bash
# Full suite (junitxml)
.venv/bin/python -m pytest -q --junitxml=/tmp/junit.xml
# → tests=2051  failures=0  errors=0  skipped=0

# Route inventory (exit 0; fails if any route lacks a test reference)
.venv/bin/python scripts/route_inventory.py
# → routes: 88 ; by class: mutating=17, read-only=71 ; by status: TEST=88

# Front-end parse
node --check web/static/app.js            # exit 0

# Route-table agreement (smoke_live ↔ route_inventory)
.venv/bin/python -m pytest tests/test_route_inventory.py tests/test_friend_access.py -q
```

New test files: `tests/test_candles_api.py` (10), `tests/test_watchlists.py` (15),
`tests/test_experiments.py` (10). The session-18 section of `TEST_RESULTS.md`
records the full browser evidence table.

> Exact suite totals are re-confirmed by the session's final regression run; the
> number recorded in `TEST_RESULTS.md` (2051) is the figure from the completed
> run.

---

## F. UI/UX workflows tested (real Chromium via `playwright-cli`)

Run against an **isolated dev server** (`MEGATOOL_DATA_DIR=data/dev/qa`,
`127.0.0.1:8799`, gate unset, owner-only boundary) — **not** production (8710),
which was never contacted.

| Workflow | Result |
|---|---|
| Load chart (QABANK2, all range) | 420 bars rendered; meta shows source + "prices unadjusted" |
| Candlestick auto-detect | 17 rows; 15-pattern picker; "243 bar(s) with impossible OHLC excluded" disclosed |
| Candlestick pattern subset | 3 patterns → 17 rows (filter respected) |
| Candlestick **None** | 0 rows + explicit message (bug B-52 fixed this session) |
| Candlestick markers | "Sp"/"Do" markers visible on the chart |
| Elliott panel | `CANDIDATE_ONLY`, 33 confirmed swings, evidence + invalidation shown |
| Elliott manual labels | labels persisted; magenta wave line + labels drawn |
| Harmonic panel | `NO_MATCH · 29 windows · 5 patterns` — honest no-match |
| Watchlist create/detail | missing symbol shows `—` + reason |
| Watchlist add/rename/delete | add 2→3; rename works; delete hides detail |
| Backtest → save → reproduce | "identical config: yes", every metric `same` |
| Report / experiment export | downloads `QABANK2-research-report.md`, `experiment-3.md` |
| Console errors / failed requests | **0 / 0** |

Accessibility/UX principles applied: progressive disclosure (collapsible pattern
picker), no meaning by colour alone (markers carry text labels; tables carry text
columns), explicit uncertainty text on every panel, and no do-nothing buttons.

---

## G. Historical and live data

* All new features read the **stored historical** dataset; none requires a live
  feed. Every response surfaces the source and `data_as_of`.
* The dev/QA fixture is **deliberately adversarial** (243/420 bars have impossible
  OHLC); the candlestick route excludes and counts them rather than repairing
  them, matching the established `workspace.py` convention.
* **Live data remains gated and unavailable**: NEPSE official API needs the
  owner's authorization; intraday/live news remain NOT-TESTED. No claim of "live"
  is made anywhere.
* Fixture dates (ending 2026-01-09) are a standing reminder that a 200 response is
  not proof of *current* data — the UI labels everything as stored historical.

---

## H. Remaining issues

1. **Custom technical-analysis rule builder** (AND/OR, comparisons, grouping,
   preview, save/load/duplicate/rename/delete/export) — **NOT STARTED**. This is
   the largest remaining Phase 5/6 item.
2. **Saved screens UI**, dashboard composition, index/relative-strength panels —
   **PARTIAL/NOT STARTED**.
3. **Tweezer / harami_cross** candlestick detectors do not exist (B-54).
4. **Elliott auto-candidates use the earliest confirmed swings** (B-55) — UI pairs
   them with manual labelling as the honest fallback.
5. **`pip-audit` unavailable** → no dependency CVE scan (B-53).
6. **Background-job architecture** (M5 §12.5) — **NOT STARTED**.
7. Blocked by external input: NEPSE official-API authorization; TMS (broker name +
   read-only URL + policy basis); YONEPSE data rights; friend-token deployment;
   8 retired symbols with no evidence-backed successor.
8. Not re-tested this session: XSS fuzzing, production migration, soak/long-run,
   friend-token cross-origin flow, live-market latency.

---

## I. Security confirmation

* `MEGATOOL_NEPSE_API_AUTHORIZED` **never set**; `MEGATOOL_INTEGRATION_AUTHORIZED`
  never set. **Zero** requests to any NEPSE endpoint this session.
* Production server (PID 26596, 127.0.0.1:8710) **never signalled**; production
  DuckDB/SQLite **never touched** (mtimes unchanged).
* No orders/broker/autonomous execution; no deploy/publish/tunnel/public exposure.
* TLS verification **on** (go-nepse's TLS-off guidance explicitly rejected).
* No secrets in code/logs/screenshots/reports; no production imports/migrations/
  db-init modified (new tables created lazily in their own modules).
* Git: **0 staged, 0 committed, 0 pushed, 0 stashes**; no `reset`/`clean`/
  `checkout --`/`add`/bulk delete. All modified/untracked/ignored/user files
  preserved (`AI Trading Nipsy/`, audit docs, original PDFs/journals untouched).
* New mutating routes added to **both** safety tables (`smoke_live.py` and
  `route_inventory.py`) so the live smoke tool still refuses to probe a write.
* No invented prices/candles/indicators/backtests/detections; every figure is
  stored, calculated or explicitly labelled.

---

## J. Prioritized next steps

1. **Custom rule builder** (highest remaining value): a restricted parsed rule
   model (AND/OR, comparisons, grouping) with preview, historical evaluation and
   save/load/duplicate/rename/delete/export — **no** arbitrary code execution.
2. **Dashboard composition** on the Watchlists/Overview views (column pickers,
   index + relative-strength panels) and **saved screens UI**.
3. **Pattern/experiment evaluation UI**: let a detected candlestick or chart
   pattern be evaluated historically (hit rate vs. baseline) with honest
   confidence intervals — reusing the single backtest path.
4. **Manual chart-pattern drawing** (trendlines/fibonacci drawn by the user) to
   complete the Phase-3 "manual vs automatic" story already begun for Elliott.
5. **Owner-gated items**: obtain the NEPSE authorization ruling, TMS source, and
   YONEPSE data-rights decision; then re-run the live smoke and intraday checks.
6. **Add `pip-audit`** to the toolchain and record a dependency CVE scan.
7. **M5 background jobs** (scheduled refresh, with explicit freshness/invalidation
   semantics — no speculative caching).
