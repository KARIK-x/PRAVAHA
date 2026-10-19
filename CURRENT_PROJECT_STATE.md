# Current project state

Snapshot after the **2026-10-18 chart workbench session 26** (35 new indicators
→ 81 registry; chart-side indicator drawer; compare drawer with 5 modes;
chart-type expansion incl. hollow/Heikin/step/baseline/column/line+markers;
Breadth History / Seasonality / Swing Bench views; volume-scanner presets) on
top of the 2026-10-17 charting sessions (17c/d18) and the 2026-10-16 defect
pass.
Read-only baseline: git `main`, **all work uncommitted** (no commits without
authorization); production PID 26596 never signalled, production DBs untouched;
dev on `127.0.0.1:10000` (`data/dev/release`). Backend this session: 3 new GET
routes and 3 new modules (breadth, seasonality, swing workbench), 7 scanner
metrics + 8 presets; full suite re-run **2,599 passed / 0 failed / 0 skipped,
exit 0**; `ruff check` clean on every file touched this session (`megatool/api.py`
keeps 21 pre-existing format hunks inside earlier sessions' uncommitted regions —
see `REMAINING_BLOCKERS.md` §10); `node --check web/static/app.js` exit 0.
Frontend: cache-buster `?v=wb7` (app.js); real-browser sweep of the session's
scope with **0 console errors / 0 warnings**.

> **Session-27 headline (2026-10-18, later the same day):** the chart workbench
> gained a global **command palette** (Cmd/Ctrl+K; views, chart types, 39 drawing
> tools, analysis layers, all 81 indicators, screener presets, actions — with
> unimplemented requests listed disabled-with-reason), a scoped **Clear** button
> with a confirmation dialog, **pane headers** (drag-resize / collapse / remove,
> persisted per instance), **viewport preservation** across tab switches and
> same-symbol reloads, a reworked **drawing engine** (body hit-testing,
> capture-phase drag so the chart no longer pans, on-chart selection handles,
> Delete/Backspace with a typing guard, no undo pollution), and **honest index
> candlesticks** (the NEPSE index renders its 2,217 genuine OHLC rows as real
> candles and draws close-only/invalid rows as gaps — never fabricated bodies).
> Eight defects found live were fixed (**B-92…B-99**). Frontend cache-buster is
> now `?v=wb12`. Full suite re-run **2,599 passed / 0 failed / 0 errors /
> 0 skipped, exit 0**; index console **0 errors / 0 warnings**.
>
> *Note on numbering:* this file also contains older addenda titled "Session 27"
> and "Session 28" (both **2026-10-16**, unrelated). This "session 27" is the
> 2026-10-18 workbench run that follows the session-26 snapshot above.

> **Session-26 headline:** the chart workspace now ships 10 native chart types
> (incl. hollow, Heikin, step, baseline, column, line+markers), a full
> chart-side indicator drawer over an 81-entry registry with a browser-verified
> overlay/pane placement matrix (28/53), a 4-symbol compare drawer (5 modes,
> gaps never interpolated), versioned layout export/import and instance-aware
> templates, plus three new research views on real data — Breadth History
> (5,200 sessions), Seasonality (per-month/weekday stats; holidays
> honest-unavailable), and the Swing Bench (confirmed levels + measured-move
> arithmetic + sizing; nothing fabricated). Three bugs found live were fixed
> (B-89…B-91). Deliverables: `IMPLEMENTATION_STATUS.md`,
> `INDICATOR_CATALOGUE.md`, `INDICATOR_SOURCE_AND_LICENSE_AUDIT.md`,
> `CHART_UX_AUDIT.md`, `REMAINING_BLOCKERS.md`.

## Older snapshot (d18)

Snapshot after the **2026-10-17 charting session 18 (label declutter + unified
undo/redo + grouped drawing rail + second tool wave + Kronos chart workflow +
real Kronos Mini)** and the earlier 2026-10-17 session 17c / 2026-10-16 defect-fix pass.
Read-only baseline: git `main`, **all work uncommitted** (no commits without authorization); production PID 26596 never signalled, production DBs untouched. Backend changed once this session
(Kronos per-variant tokenizer/context; Pydantic caps): full suite re-run **2331 passed / 0 failed**
(`--junitxml`, parsed), `ruff check` + `ruff format --check` clean. Frontend: cache-buster `?v=d18` (app.js, kronos_ui.js, styles.css), Chromium sweep of this session's scope **0 console errors / 0 pageerrors**; new weights on disk
(`data/models/Kronos-mini` 16,440,776 B + `data/models/Kronos-Tokenizer-2k` 15,842,376 B — official, byte-exact vs HF).

> **Session-18 headline:** the chart's "label mess" is fixed (quality-capped
> pattern overlay with title-less series + compact chips, letter caps, four
> display modes), one typed undo/redo stack now covers drawings AND
> zoom/pan (Cmd/Ctrl+Z, Shift+Cmd/Ctrl+Z, Ctrl+Y) with gesture coalescing, the
> anon-icon drawing rail became 9 named-category popovers with cross-group
> search, 17 new drawing tools landed (measurement pairs, fib time
> zones/fan/channel/trend-based-ext, regression channel ±kσ, pitchfork,
> triangle, polyline, XABCD/ABCD/three-drives/Elliott impulse/ABC), and
> Kronos-Mini became really available: official 4.1M-param weights + official
> Tokenizer-2k, MPS inference measured, per-variant context (mini 2048).
> Five bugs found and fixed live (B-69…B-73 in KNOWN_BUGS.md).

## Older snapshot (17c)

Snapshot after the **2026-10-17 charting session (17c, drawing rail + indicator catalog)** and the 2026-10-16 defect-fix pass (session 21).
Read-only baseline: git `main`, **all work uncommitted** (no commits without authorization); production PID 26596 never signalled, production DBs untouched. Backend unchanged this session: full suite **2331 passed / 0 failed** re-run, route inventory **117 routes**, `ruff` clean. Frontend: cache-buster `?v=drail2`, real-browser sweep **0 console errors/warnings**; dedicated charting report in `docs/CHARTING_ACCEPTANCE_AUDIT.md`.

> **Session-17c headline:** the charting workspace gained a searchable drawing rail (19 tools / 8 groups), eight new drawing types, select/eraser/magnet/lock interaction modes, and a searchable indicator catalog over the 46-entry backend registry with unit-aware add routing and per-symbol persistence. Four charting bugs found live were fixed in the same session (B-65…B-68).
Read-only baseline: git `main` @ `b6c3659`, **0 staged, 0 committed, 0 pushed,
0 stashes**; production PID 26596 never signalled, authorization gate unset
(`None`), production SQLite `mtime` frozen at 10:31:58 across the run. Full suite
**2121 passed / 0 failed / 0 errors / 0 skipped**; route inventory **98 routes**
(77 read-only, 21 mutating), all test-referenced; `ruff check` + `ruff format
--check` clean; real-Chromium sweep of **13/13 views with 0 console errors/warnings**.

> **Session-21 headline:** a re-verification of the delivered frontend turned up
> four genuine defects, all fixed with browser evidence. The **auto-detected
> Fibonacci overlay never rendered** (read a non-existent payload key) and now
> draws the endpoint's real levels (B-61); the **scanner passed a security whose
> required metric was unavailable** (unknown clauses were dropped) and now uses
> three-valued logic so a missing metric makes a symbol ineligible with a reason
> (B-62); the **assistant panel could not be closed** because a class rule beat
> `[hidden]` (B-63); and **`/api/sources` mislabelled a gated source as down**
> (B-64). The `/fibonacci` thin-data answer moved from `422` to
> `200 {available:false, reason}` (B-60). The **go-nepse** position is unchanged
> (D-aj): the library's protocol is covered by the gated, TLS-on client
> `megatool/datasources/nepse_official_live.py`; the Go dependency itself is not
> integrated. See D-ax…D-bb and the session-21 section of `TEST_RESULTS.md`.

Snapshot after the **2026-10-16 completion sprint (session 19)**.
Read-only baseline: git `main` @ `b6c3659`, **0 staged, 0 committed, 0 pushed,
0 stashes**; production PID 26596 never signalled, authorization gate unset,
production DB mtimes unchanged. Full suite **2080 passed / 0 failed / 0 errors /
0 skipped**; route inventory **94 routes** (74 read-only, 20 mutating), all
test-referenced; `ruff check` + `ruff format --check` clean; real-Chromium
walkthrough with 0 console errors and 0 failed requests.

> **Session-19 headline:** the **custom rule builder** and **dashboard
> composition** — both previously NOT STARTED — are now implemented and verified.
> The rule builder reuses the existing, tested scanner tree (no new evaluation
> engine, no `eval`/`exec`/browser SQL) and adds saved-rule persistence; the
> dashboard customiser is client-side (show/hide/reorder/reset, persisted).
> The candlestick catalogue widened **15 → 18** with real, tested detectors
> (`harami_cross`, `tweezer_bottom`, `tweezer_top`, superseding D-al), and the
> Elliott/harmonic panels gained an **analysis-period selector**, a harmonic
> **pattern subset + tolerance**, and per-candidate **Draw** that plots the
> count's actual pivots — the harmonic window is now aligned to the chart
> (fixes B-56). See D-am…D-ap and the session-19 section of `TEST_RESULTS.md`.

Snapshot after the **2026-10-16 Phase 2–6 implementation session (session 18)**.
Read-only baseline: git `main` @ `b6c3659`, 0 staged, 0 stashes; nothing
committed/pushed in any AI session. Production PID 26596 never signalled,
authorization gate unset, production DB mtimes unchanged.

> **Phase 2–6 verdict: PARTIAL → materially advanced.** This session implemented
> the highest-value missing capabilities identified by the session-17 audit
> (`docs/PHASES_2_6_COMPLETION_AUDIT.md`): the previously-unreachable candlestick
> engine now has an API + UI, the Elliott and harmonic engines now have real UIs,
> and **watchlists** and **reproducible experiments** (save/reproduce/compare/
> export) are implemented end-to-end. Full suite **2051 passed / 0 failed**;
> route inventory 88 routes, all test-referenced; real-browser walkthrough
> verified. See `docs/PHASES_2_6_PROGRESS.md` and the session-18 section of
> `TEST_RESULTS.md`.

Snapshot after the **2026-10-15 Phase 1 closure (session 14)**.
Read-only baseline: git `main` @ `b6c3659`, 46 tracked files modified
(uncommitted), ~104 untracked files, **0 staged, 0 stashes**; nothing
committed/pushed in any AI session.

> **Phase 1 verdict: COMPLETE WITH EXTERNAL VALIDATION PENDING.** All local
> Phase 1 work is implemented and tested (full suite **1820 passed / 0 failed**
> on 2026-10-15). Remaining items are owner authorizations (NEPSE official API,
> TMS, YONEPSE data rights) and one live market-hours observation (next session
> Sun 2026-10-18 11:00–15:00 NPT). The NEPSE collector stays **gated OFF**.

## What Mega Tool is
A local-first NEPSE quantitative research terminal: **FastAPI + DuckDB +
lightweight-charts**, Python 3.12, on a MacBook Air M1 (8 GB). It is a research
and analysis tool — it does **not** route live broker orders.

## Stack / entry points
- Backend app: `megatool.api:app` (built by `create_app()`); CLI `megatool.cli`.
- Serve: `.venv/bin/python -m uvicorn megatool.api:app --host 127.0.0.1 --port 8710`
- Tests: `.venv/bin/python -m pytest -p no:warnings tests/`
- Storage: DuckDB `data/processed/megatool_market.duckdb` (market data) + a SQLite
  app-state DB, both behind `Paths` in `megatool/config.py`.

## Authoritative data baseline (must not silently change)
`price_bars` **514,018** · `security_master` **372** ·
500,801 `valid` / 13,093 `suspect` / 124 `invalid`.

## Test status
**1820 passed, 0 failed, 0 errors, 0 skipped** (2026-10-15 session-14 full suite,
junitxml, 28.56 s). `ruff check` 0 · `ruff format --check` 0 on changed paths.
Prior milestones: 1805 (reliability/deployment), 1730 (NEPSE-official live client),
1578 (C3/D-y). See `TEST_RESULTS.md` for per-run detail.
**Gates (re-verified 2026-10-15):** NEPSE ingest gate OFF → exit 2 · benchmark gate
OFF → schedule-only, exit 0, **zero NEPSE requests** · source-health gate OFF → no
host contact.

## Phase 1 source architecture (verify, do not redesign)
| Source | Access | Role | Prerequisite |
|---|---|---|---|
| NEPSE official API (direct Python `Salter` client) | **gated OFF** (Rule 9 / BLK-1) | intended primary | owner authorization ruling on automated access |
| YONEPSE | authorised, ~3 days stale | supplementary/reference (never auto-live) | data-rights ruling for production import (R1/BLK-2) |
| TMS | none (no broker API; ref repo is paper-only) | — | broker name + TMS URL + read-only policy (BLK-2 class) |
| GitHub (Aabishkar2 / binayabaral) | open | historical prices + index | none (local use only) |

## Index consumption (2026-10-15, new)
`index_series` (17 series / 7,611 rows) is now **consumed**: `relative_strength`
rankings factor the official NEPSE composite only (`megatool/ranking.py`), and
`GET /api/indices` + `GET /api/indices/{name}` serve the stored series read-only
(`megatool/api.py`, friend-allowlisted). Blocker **B-10 / BLK-8 RESOLVED**.

## Feature status (backend)

| Feature | Status | Evidence |
|---|---|---|
| Foundation / API / CLI | IMPLEMENTED | committed |
| Data pipeline + ingestion + validation | TESTED-PASS | first ingestion suite (`test_ingest.py`, 9 tests): failure isolation, provenance, idempotency, honest run log (B-37/B-38 fixed) |
| Storage (DuckDB/SQLite) | TESTED-PASS | tests |
| TA indicators (28) | TESTED-PASS | tests; RSI/MFI 0/0 → NaN |
| Fibonacci | TESTED-PASS | engine + independent expected values |
| Support/resistance levels | TESTED-PASS | engine tested |
| Candlestick patterns (15) | TESTED-PASS | engine + causality test |
| Multi-timeframe (weekly/monthly) | TESTED-PASS | correct calendar aggregation + live API 200 |
| Elliott Wave | TESTED-PASS (bounded) | live API 200 `CANDIDATE_ONLY`; confirmed-swings look-ahead fixed |
| Harmonic patterns (Gartley/Bat/Butterfly/Crab/Cypher) | TESTED-PASS (candidates) | `ta/harmonic.py` + 20 tests; live `NABIL/harmonic` 200, 2 candidates, uncertainty surfaced |
| Scanner | TESTED-PASS | real pipeline tests; dedup wired |
| Backtesting | TESTED-PASS (structural + fixture) | 24 lifecycle tests + cost-model suite; `next_open` no-look-ahead; B-32/33/34 fixed (B-34 hardened: mixed date representations rejected); API/engine number equality pinned; live-data run NOT-TESTED; `fee_rate` placeholder (B-11/T-12) |
| Workspace / research view (backend) | TESTED-PASS | workspace tests |
| Forecasting | TESTED-PASS (structural) | single-hold-out + **rolling-origin walk-forward** (`POST /api/forecast/rolling`) with leakage probes at **function and API** level; real out-of-sample evidence NOT-TESTED |
| Portfolio / risk | TESTED-PASS (structural) | B-35 fixed + hardened (NaN/±inf never mark; API serializes null not Infinity); real ledgers NOT-TESTED |
| News / Events (§22) | LOCAL LAYER IMPLEMENTED · SOURCE BLOCKED | import/validate/dedup/summarise (schema v6, v5→v6 migration verified, `POST /api/news/import`, `GET /api/news/summary`, 22 tests); no live source (L4/T-15) — nothing fetched or fabricated |
| Fundamentals / floor-sheet / PDF | IMPLEMENTED / NOT-TESTED | 0 real records (external input); floor-sheet parser hardened (B-36) + residual B-40 fixed; 20 adapter tests with zero network |
| Frontend / chart / overlays | **BLOCKED (broken)** | `app.js` SyntaxError — Phase 2 |
| Browser / E2E | NOT-TESTED | Playwright absent |

## Known gaps / blockers
- **Frontend broken** (Phase 2): `app.js` SyntaxError ~line 1972; overlay plots fed
  placeholder data; console.log markers; duplicate dashboard HTML.
- **External:** T-10 (Ollama), T-11 (sector CSV), T-12 (fee/tax), T-13 (floor sheet),
  T-15 (licensing), B-09 (NEPSE API auth), B-10 (index data), L4 (news source), D2 (OmniRouter).
  *Re-verified 2026-10-14 (investigation pass, no code changed):* all nine remain open.
  B-09 re-probed live → HTTP 401. Ollama v0.5.7 present (only `llama3.2`+`nomic-embed-text`,
  no vision model, 8 GiB RAM ceiling) but **no Ollama code exists in the app**. OmniRouter:
  **no env vars in-process, no endpoint/model/key anywhere** — nothing to test, nothing
  depends on it. No owner file (`sectors.csv`/`fees.csv`/`index_nepse.csv`/floor sheet)
  has been supplied yet. Full matrix + exact owner actions: `TASK_QUEUE.md`
  §"Phase 1 blocker verification (2026-10-14)".
  *Phase D code-readiness pass (2026-10-14):* **D1 RESOLVED for local mode** —
  `megatool/llm.py` (provider interface + Ollama/OpenRouter clients + disabled
  default), config knobs, `megatool ai status|ping`, 26 mock-transport tests, and a
  **live local Ollama ping** (`Pong`, exit 0) all verified; the app still runs with
  zero AI contact unless a provider is selected. **T-11/T-12/B-10 loaders built**
  (`megatool/sectors.py`, `FeeSchedule` in `backtest.py`, `megatool/index_series.py`
  + `index_series` table) — ready for the owner's files; **data still BLOCKED, none
  invented**. B-09/T-13/T-15/L4 unchanged (external). OpenRouter recorded as the
  selected hosted gateway (decision only, no key, no request). 1389 tests pass.
- **Owner decision R1:** promote `non_positive_price` from `review` to hard-invalid?
- Backtest `fee_rate` is a configurable, clearly-labelled placeholder (not a verified
  NEPSE fee).
- The "1000 synthetic datasets" claim is **not established** — no harness exists.

## Protected (never modify)
`AI Trading Nipsy/`, `MEGA_TOOL_RESEARCH_REPORT.md`, `WRITTENdata.pdf`, and all
historical trading journals/ledgers/PDFs/databases.

---

## Session-15 addendum — Phase 2–6 autonomous run (2026-10-15)

Two specification gaps were closed with new, tested vertical slices, plus a
scanner-capability expansion. See `docs/PHASES_2_6_PROGRESS.md` for the full
traceability / feature / reference-audit / verification record.

* **Classical chart patterns** — `megatool/ta/patterns.py` +
  `GET /api/bars/{symbol}/patterns` + charts-view panel. (Was: "head/shoulders
  etc missing".)
* **Advanced statistical analysis** — `megatool/stats.py` +
  `GET /api/bars/{symbol}/statistics` + `GET /api/stats/correlation` +
  charts-view panels. (Spec §16/§18.1.)
* **Scanner** — presets 4 → 23; 18 new single-symbol metrics.
* **Indicator library** 28 → **46** registered indicators (`ta/other.py` added;
  `vwma/dema/tema/kama/parabolic_sar/stochastic_rsi/ppo/cmo/tsi/cmf/chaikin_oscillator/volume_roc`
  plus the 6 primitives), each covered by the dynamic look-ahead / warm-up tests
  and a new engine-free literal reference. One real defect found and fixed:
  **B-45** (KAMA volatility dropped the most recent change).
* **Route count** 72 → **75** (all test-referenced). Full suite **1999 / 0 / 0 / 0**.

**Browser QA:** the real frontend chain was exercised once against an isolated
store (see `docs/PHASES_2_6_PROGRESS.md` §5.1); it found **B-46** (frontend
percent scaling), which is now fixed and re-verified. Charts-view frontend
integrity is therefore **TESTED-PASS (one pass)**, while the rest of the UI
remains browser-NOT-TESTED.

Safety unchanged: NEPSE gate OFF (zero calls), production DBs untouched, all
isolated work under `data/dev/` (git-ignored) or temp dirs, nothing
staged/committed/pushed/deployed. External blockers (NEPSE authorization, TMS,
YONEPSE data-rights, friend token, live-cadence observation) remain unchanged and
**do not** gate the local application.


---

## Session-16 addendum — verification mission (2026-10-16)

A verification-and-gap-closing pass, not a feature build.

* **Three defects fixed:** B-47 (inconsistent symbol validation across
  per-symbol endpoints), B-49 (`/elliott` and `/harmonic` 500 on a NaN series),
  and B-50 (performance: `rolling_std` per-window loop).
* **One performance win:** `POST /api/rank` p50 **391.7 → 113.6 ms** (3.45×),
  results verified unchanged. T-20 closed.
* **Hardening:** startup access-boundary notice on every entrypoint (warns on a
  non-loopback bind without a token); one unescaped server value escaped.
* **New verification assets:** `scripts/verify_quant.py` (independent
  cross-checks vs pandas/scipy/hand-computed), `scripts/qa_fixture.py`
  (isolated E2E fixture), `docs/RELEASE_READINESS.md`.
* **First multi-journey browser E2E:** all 11 views, 0 console errors; portfolio,
  research and backtest values independently re-derived and matched.

Full suite **2007 passed / 0 failed / 0 errors / 0 skipped**. Safety unchanged:
gate OFF (zero NEPSE requests), production DBs untouched, nothing
committed/pushed/deployed.

---

## Definitive Phases 2–6 audit (2026-10-16, session 17)

An independent, requirement-level completion audit was performed and recorded in
**`docs/PHASES_2_6_COMPLETION_AUDIT.md`**. It re-established ground truth
(suite **2016 passed / 0 failed / 0 errors / 0 skipped**, HEAD `b6c3659`, gate
unset, prod DBs untouched) and verdicted every requirement.

**Verdicts: Phase 2 PARTIAL · Phase 3 PARTIAL · Phase 4 PARTIAL · Phase 5 PARTIAL
· Phase 6 PARTIAL.** No phase is complete.

Headline gaps (full list in the audit):

* **Phase 2** — dashboard §8.1 panels (index/sector summary, sparklines, heatmap,
  circuit counters, market-session context), §8.2 **watchlists** (schema only),
  and §8.3 exportable report are missing.
* **Phase 3** — **Harmonic** and **Elliott** engines are tested but have **no UI**;
  `plotCandlestickMarkers` is **dead code**; pattern/candle annotations not drawn.
* **Phase 4** — research workbench **save/reproduce/compare/export** (§11.5
  steps 8–11) absent; no strategy DSL; no snapshot-id/config-hash. *(Corrects the
  earlier "M4 TESTED-PASS".)*
* **Phase 5** — portfolio has no cash-flow model; alerts have no severity/cooldown;
  fee rate is a labelled placeholder; fundamentals/news/corporate-events
  data-blocked.
* **Phase 6** — **custom formula catalogue** and **research templates** NOT STARTED;
  exportable report/chart missing; handwriting 0/52 pages.
* **M5** — background-job architecture (§12.5) NOT STARTED.

No application code was changed; production untouched; nothing committed/pushed/
deployed.

---

## Session 20 (2026-10-16) — integration sprint

The gaps this file listed as missing have moved. Corrected status at **requirement**
granularity:

| Requirement | Status | Note |
|---|---|---|
| Custom rule builder (+ saved rules) | **TESTED-PASS** | session 19; unchanged this session |
| Dashboard composition (show/hide/reorder/reset) | **TESTED-PASS** | session 19 |
| **Dashboard index / market-context panel** | **TESTED-PASS** | new "Index context" panel, honest "historical, NOT a live feed" wording |
| **Index + relative strength** (endpoint, ratio line, scanner metric, dashboard) | **TESTED-PASS** | `relative_strength` is now the 34th scanner metric; missing benchmark ⇒ ineligible with a reason |
| Candlestick catalogue | **TESTED-PASS** | 18 detectors |
| **Fibonacci / manual chart drawing** | **TESTED-PASS** | user-authored, per-symbol, data coordinates, labelled *not* detector output |
| **Chart-pattern selection + overlays + evidence** | **TESTED-PASS** | window-aligned; fixes B-58 |
| Elliott / harmonic flexibility + Draw | **TESTED-PASS** | sessions 19–20 |
| **Floating AI assistant** | **TESTED-PASS** | two honest actions; nothing executes without the researcher pressing Run |
| **Research templates** | **TESTED-PASS** | declarative; every step asserted to exist and to execute |
| **Alert severity / cooldown / acknowledgement** | **TESTED-PASS** | default behaviour unchanged (once-until-cleared) |
| **Security check pass** | **TESTED-PASS** | `pip-audit` clean, authz boundary pinned, XSS escaping verified in a browser |
| Watchlists | **TESTED-PASS** | session 18 |
| Fundamentals in the **scanner** | **PARTIAL** | records + ratios display; P/E, P/B, dividend and earnings are *reported as unsupported* by the rule grammar, with the reason |
| Portfolio **cash-flow** model | **NOT STARTED** | holdings valuation and risk exist |
| Background jobs (M5 §12.5) | **NOT STARTED** | |
| Live intraday / live news | **BLOCKED** | no rights-cleared machine-readable source |
| NEPSE official API / TMS / YONEPSE apply / friend deploy | **BLOCKED** | owner authorisation required |

**Phases 2–6 remain PARTIAL** at requirement granularity; the remaining gaps are the
rows above marked NOT STARTED/PARTIAL/BLOCKED. Session 20 changed application code and
documentation; production was not signalled, restarted or asked to do anything.


---

## Session 22 (2026-10-16) — actual go-nepse Go library

**Added.** The **actual** `github.com/voidarchive/go-nepse` Go library (module
`v0.2.5`) is integrated behind a process boundary: `tools/gonepse-bridge/` (Go,
pinned module) ↔ `megatool/datasources/gonepse.py` (`GoNepseAdapter`), with a
network-free `GET /api/gonepse/status` route and a `go-nepse` entry in
`GET /api/sources`. Provenance label `DataSource.GONEPSE`.

**Safety posture (unchanged rules, now applied to the library).** TLS verification is
**ON** and never disabled; the exchange certificate is verified valid today
(`docs/evidence/session22-nepse-tls-cert.txt`). The owner authorization gate is
enforced **independently** in the Python adapter (before spawning) and in the Go
bridge (real-host live calls exit `3` without `MEGATOOL_NEPSE_API_AUTHORIZED=1`). The
adapter never sets the variable.

**Verified.** 2150 Python tests pass (0 fail / 0 skip); 9 Go tests pass (real auth
path against a local TLS mock; no NEPSE contact); `ruff` clean; `node --check` clean;
route inventory 100 routes all test-referenced.

**Also this session (Priority 2, low-risk).** A **portfolio cash-flow model**
(`cash_flows()`, `GET /api/portfolio/cash-flow`, embedded in `/api/portfolio` as
`cash_flow`, rendered in the Portfolio panel): signed per-trade net (buy =
`qty×price + fees` out; sell = `qty×price − fees` in), cumulative in ledger order,
totals and per-symbol net — explicitly **not an account cash balance**.

**Live connection: BLOCKED.** The gate is unset; no live NEPSE request was made. The
build/tests passing is **not** evidence that live data works, and is not reported as
such.

**Production untouched.** PID 26596 alive on `127.0.0.1:8710`; prod SQLite mtime
`2026-10-16 10:31:58`; prod DuckDB mtime `2026-10-15 09:24:38`; gate unset.

---

## Session 23 (2026-10-16) — live market data

**Added.** A measured live-data provider layer (`megatool/live.py`) with four
providers — `sharehub` (licensed ~20 s), `official` (gated go-nepse, inert),
`feed` (owner JSON URL), `yonepse` (public hourly fallback) — plus read-only
routes `GET /api/live/status|market|quotes` and an Overview **Live market** strip.
Freshness is measured from the source's own timestamp (`age_seconds`) and reported
separately from request latency; each provider is cached at its publication
cadence; the module never sets the authorization gate.

**Live access: BLOCKED.** Measured: the official API returns `401 WARNING:
UNAUTHORIZED ACCESS` without the anti-bot token (TLS is fine), so the gate is not
the only obstacle; ShareHub needs the owner's licensed credentials; the public
mirror is ~4 days stale and is labelled so. Full evidence and the exact one-step
owner action are in `docs/LIVE_DATA.md`.

**Verified.** 2174 tests pass (0 fail / 0 skip); `ruff` clean; `node --check`
clean; 103 routes all test-referenced; `pip-audit` clean; browser live strip with 0
console errors (`docs/evidence/session23-live-strip.png`). Production untouched.

**Analysis-group status** for all 28 groups: `docs/ANALYSIS_GROUPS_STATUS.md`
(14 TESTED-PASS · 8 PARTIAL · 5 NOT STARTED · 1 BLOCKED).

---

## Session 24 (2026-10-16) — free, current-day NEPSE data (the staleness was a CDN)

**Root cause found and fixed.** The YONEPSE adapter read the **GitHub-Pages mirror**
(CDN-cached, ~4 days stale) instead of the repository's **raw content**, which was
**current** (`status.json` `last_checked` 31 min old; NEPSE index 2,625.93 at
`2026-10-16T13:01`; 328 quotes with in-session last-trade times). `BASE_URLS` now
tries raw first and falls back to Pages only if raw is unreadable, reporting which
mirror answered.

**Freshness is now cadence-aware** (`live` ≤30 s → LIVE_VERIFIED; `delayed` within
the source's own publish cadence; `stale` beyond; `last-close` when closed;
`historical` >5 d). An hourly publisher is correctly `DELAYED` at ~40 min, not
"stale", and never "live".

**Real fundamentals, free:** **21,698 records / 307 symbols** imported from the same
source; ratios stay `unavailable` without a stored price (never invented).

**Diagnostics view:** the Data view now lists every provider with status
(LIVE_VERIFIED/DELAYED/STALE/HISTORICAL/UNAVAILABLE/BLOCKED), observation age,
provider vs receipt time, request latency, securities, and the actual **origin**
mirror. `docs/evidence/session24-live-sources.png`.

**Still blocked:** official API (anti-bot token; gate unset), go-nepse (same),
ShareHub (paid licence/allow-list). None is used or bypassed.

**Verified:** **2179 tests pass** (0 fail/skip); ruff clean; `node --check` clean;
103 routes all test-referenced; production untouched.

---

## Session 25 (2026-10-16) — local release instance at http://localhost:10000

**Running.** `MEGATOOL_DATA_DIR=$PWD/data/dev/release .venv/bin/python -m megatool.cli
serve --host 127.0.0.1 --port 10000` → **PID 75732**, listening on `127.0.0.1:10000`,
`/api/health` 200. Isolated dev storage (`data/dev/release/`), separate from
production (`data/processed/`, PID 26596 untouched on :8710).

**Real data.** 372 symbols / **515,327 bars** / 1995-07-20 → 2026-10-15. Free live
source: YONEPSE raw content with commit walk-back (survives the upstream
merge-conflict incident) — **DELAYED**, age ≈75 min, index 2,625.93, 328 quotes.
Fundamentals: 21,698 records / 307 symbols; **NABIL P/E 19.25, P/B 2.21**.

**Verified.** **2184 tests pass** (0 fail/skip); ruff/format clean; `node --check`
clean; 103 routes all test-referenced; Go bridge tests pass. Browser: 14 views,
**0 console errors**.

---

## Session 26 (2026-10-16) — reference-driven UI overhaul

**Reference audit:** all **106** PNGs in `UI AND FEATURES PHOTO REFERENCE`
inspected (96 distinct clusters) — the collection is **NEPSE Alpha** plus one
TradingView chart. Findings: `docs/ui-redesign/REFERENCE_INVENTORY.md`, with the
feature mapping in `REFERENCE_FEATURE_MATRIX.md` and the target system in
`DESIGN_SYSTEM.md`.

**Shipped:** left **sidebar + top bar** shell with grouped navigation and a global
symbol search; the **Ideas** view (10 methodology cards, 7 computing, 3 honestly
disabled); a dashboard **breadth bar**; `GET /api/ideas[/{model}]`.

**Not shipped (declared, not faked):** the large index hero chart (no index series
stored), the chart-workspace toolbar/overlay manager, portfolio/backtest visual
upgrades, sector/breadth pages, comparators, valuation models (DDM/Graham/Gordon/
Lynch intrinsic value), DuPont, portfolio scoring gauges, chart-scanner thumbnails.

**Verified:** 2199 tests pass; 105 routes all test-referenced; 14 views with 0
console errors on `127.0.0.1:10000`; production untouched.

---

## Session 27 (2026-10-16) — the chart workspace is finished

The Charts page is now a charting terminal, not an admin form.

* **Clean default:** candles + volume. Every analysis layer is opt-in in the
  right-hand **Analysis** drawer and reports how many items it found
  (fib 10, candles 56, patterns 6, elliott 14, harmonic none, S/R 10 of 73).
* **Overlay caps:** ≤10 lines per layer, labels only on the 5 nearest price, so a
  layer can never bury the candles. "Hide all" clears the chart and the list.
* **Compact toolbar:** symbol · timeframe · chart type · Indicators/Draw/Analysis
  popovers · fit / zoom / fullscreen / CSV. The old settings card is gone.
* **Indicator panes work at last** (B-65: `$("rsi-pane")` missed its `#`), and
  reloads no longer accumulate charts (B-67).

**Verified:** 2199 tests pass; 14 views 0 console errors; drawing tools, chart
type, zoom/fit/fullscreen, per-symbol layer persistence all exercised in the
browser. `docs/evidence/session27-chart-*.png`.

**Remaining (declared):** no volume profile, no trendline/horizontal-ray/channel
drawing tools (only fib retracement/extension + horizontal line exist today),
no crosshair mode switch, no multi-chart layout.

---

## Session 28 (2026-10-16) — the dashboard redesign lands (finally, visibly)

The previous session said "dashboard hero done"; it was not — only the sidebar
and live strip had changed, and the Overview still ran the old `loadOverview()`.
**Fixed:** `#view-overview` now renders the new hero KPI strip, a real
official-index chart, breadth, MA participation, 14-sector table, gainers/losers/
active, and a P/E histogram, all wired to `/api/market/dashboard` + `/api/indices`.
**2200 tests pass**, 0 console errors across all 14 views.

Server still running on `127.0.0.1:10000` (PID 56416). Prod (PID 26596) untouched.

---

## Session 28 dashboard completion (final)

Major visible dashboard redesign now deployed on http://127.0.0.1:10000.
Hero: market KPI strip (NEPSE 2,634.17 +0.31%, 199 adv/106 dec, NPR 5.5B turnover, 15.7M volume, status CLOSED as-of), prominent NEPSE index chart (120 bars, 2026-04-22 → 2026-10-16, official; timeframe select works: 60/120/250/750 obs), breadth + MA participation (157/137/92 of 372 above 20/50/200-d MA), sector table (14 sectors), gainers/losers/most-active (8 each), P-E histogram (231, 7 bins). Live strip shows DELAYED + age + origin.

2200 tests pass; ruff clean; 105 routes test-referenced; 14 views 0 console errors.

---

### 2026-10-17 session 24 — relative strength multi-timeframe, 4 new analysis modules

Priority-1 gap closed and extended: the relative-strength "no index consumer"
report was stale (an earlier session already connected the official composite,
6,720 rows). This session added the missing multi-timeframe comparison:
`megatool/rs_timeframes.py` + `lookbacks=` endpoint param + a configurable
lookback table in the UI, browser-verified (NIMB excess +4.48/+3.07/+2.49/
+0.03 pp at 20/60/120/250 bars, matching the API exactly). Sector-relative
remains honestly unavailable — no permitted sector-index source exists
(binayabaral publishes the composite only; official sub-indices are behind
the 401 token; GitHub tree listings proved it).

Four new analysis modules, all endpoints live on real NIMB history and all
browser-verified where a UI exists:
- **Volume profile** (`ta/profile.py`, `/api/bars/{symbol}/volume-profile`,
  chart Analysis layer): overlap-proportional allocation, POC/tie→lower,
  classic 70% value area, strict HVN/LVN. A value-area pointer bug was caught
  by hand-set arithmetic tests before release and fixed.
- **Trailing stops** (`ta/trailing.py`, endpoint + advanced-analysis card):
  chandelier/swing/pct behind one shared up-only ratchet; strictly causal;
  exits need a later bar's low; no open-price fill claimed.
- **Gaps** (`ta/gaps.py`): factual gaps, ATR-scaled rule class with stated
  basis, post-hoc `closed_within_bars` flagged as forward-looking.
- **False breakouts**: rolling-extreme breakouts classified true/false/
  unconfirmed with measured run beyond level.

Gates: full suite **2316 passed / 0 failed** (2273 + 43 new); ruff + format +
`node --check` clean; route inventory **117 routes, all test-referenced**;
Kronos re-verified with real MPS inference (5 steps, 4.65 s, rows labelled
`is_predicted=true`); experiment save→reproduce reproduced −26.1193 exactly
then deleted; `/api/sources` still labels the official API BLOCKED (401,
not bypassed); production :8710 (PID 26596) untouched, health 200; cache
busted to `?v=kronos6`. Docs updated: ANALYSIS_GROUPS_STATUS (rows 5, 6, 18
→ TESTED-PASS), CALCULATION_CATALOG (session 24 additions), FEATURE_STATUS,
TEST_RESULTS (Session 2026-10-17b).

## Session 19 (2026-10-17)
Cache-buster `?v=d19`. Frontend-only. See KNOWN_BUGS B-74…B-83 and
docs/CHARTING_FEATURE_MATRIX.md. Prod :8710 (PID 26596) untouched; dev :10000
restarted? No — static files only, no backend change.

---

## 2026-10-18 workbench session 27 — drawing repairs, honest index candles, palette, Clear, panes

Continues the charting mission on top of the session-26 snapshot. Same safety
envelope: production PID 26596 untouched, production DBs untouched, no commits,
dev on `127.0.0.1:10000` (`data/dev/release`).

### Shipped

* **Global command palette** — `⌕ Search` in the chart toolbar or **Cmd/Ctrl+K**
  from anywhere. One search box over 30+ views, 10 chart types, 39 drawing
  tools, 7 analysis layers, all 81 registered indicators, screenshot presets and
  12 actions; grouped results, keyboard-driven (↑ ↓ ↵ Esc), and every requested
  feature that does not exist is shown **disabled with the reason** so search
  never returns a dead control. `TEST_RESULTS.md` §27 #27–30.
* **Clear button + scoped confirmation dialog** next to Chart settings. Live
  counts per scope (drawings / indicators / analysis); nothing is cleared until
  confirmed; drawings are undoable with Cmd/Ctrl+Z and indicator removals with
  the drawer's Undo; saved layouts, templates and watchlists are out of scope by
  construction.
* **Pane headers** on every custom indicator pane: drag to resize, collapse /
  expand, taller / shorter, ✕ remove (undoable). Height and collapsed state
  persist on the instance.
* **Viewport preservation** — tab switches and same-symbol reloads (adding a
  layer/indicator, applying a template) no longer call `fitContent()`; the
  visible logical range is captured and restored. Fit stays an explicit button.
* **Honest index candlesticks** — chart-type availability is gated by **data**
  (`genuine_ohlc_count` for the index, `hasBody()` for a security). NEPSE now
  renders its **2,217 genuine OHLC rows (2016-11-28 → 2026-10-15)** as real
  candles; placeholder **and** source-flagged `invalid` rows render as
  whitespace gaps (never a fabricated or inconsistent body); Heikin chains only
  across genuine rows and resets at a gap. `/api/indices/{name}/ohlc` now
  returns `genuine_first_date` / `genuine_last_date`.
* **Drawing engine repairs** — body hit-testing for every tool (`ptSegDist`,
  hline/hray full-width, vline full-height, crossline both axes, text-like tools
  as points), **capture-phase** pointer handling so lightweight-charts no longer
  pans during a drag, logical-coordinate drag mapping (`barIndexAtX`) so drags
  work between bars and past the last bar, on-chart selection handles for the
  selected drawing, a typing-guarded **Delete/Backspace** handler, and a
  selection that no longer consumes an undo slot.

### Fixed (see `KNOWN_BUGS.md`)

B-92 eraser only hit anchors · B-93 no Delete/Backspace · B-94 drag also panned
the chart · B-95 no on-chart selection feedback + placement tools hijacked drags
· B-96 selection polluted undo · B-97 index console 404s · B-98 index
close-only restriction + fabricated placeholder OHLC · B-99 `fitContent` reset
the viewport.

### Verified

* Full suite **2,599 passed / 0 failed / 0 errors / 0 skipped, exit 0**
  (`$TMPDIR/full3.log`); `tests/test_index_ohlc_history.py` extended to 15 tests.
* 36 browser interaction cases with **real trusted events** on NABIL (250 bars)
  and NEPSE (750 bars) — full matrix in `TEST_RESULTS.md` §"Session 27".
* Console **0 errors / 0 warnings** on the index and on a stock.
* Screenshots: `docs/evidence/workbench-2026-10-18-{index-candles,palette,clear-dialog,catalog,pane-headers,drawings}.png`.

### Still absent (do not fake — `REMAINING_BLOCKERS.md` §17)

Canvas context menu; multi-symbol grid + pane drag-out; multi-timeframe overlays
/ MTF scan; opt-in auto trendline detection; a named workspace that saves pane
order; non-time-based chart types (Renko/Kagi/P&F); Part 14 pattern names not in
this snapshot; Part 18 unified engine. Pane/canvas behaviours are
browser-verified only (no headless harness; `REMAINING_BLOCKERS.md` §19).

---

## 2026-10-18 workbench session 30 — comprehensive audit, indicator validation, 5 new advanced capabilities

### Shipped

* **Indicator audit** — all 92 indicators examined; 5 references + 11 notes + 36
  param descriptions filled; verification map 49/41/2 → **62/28/2**.
* **25 numeric reference tests** (`tests/test_indicators3.py`) for the 16
  previously invariant-only indicators; scanner promotion rule fixed.
* **5 genuinely new capabilities** (`tests/test_advanced_analysis.py`, 16 tests):
  rolling beta, volatility percentile, MTF confluence, technical rating, S/R
  strength scoring.
* **Search/info audit** — 92/92 ⓘ buttons, "money flow" → CMF + MFI.
* **Fibonacci re-verified** — `{75,175}` → `{75,175}`, 0 console errors.

### Verified

* Full suite **2,701 passed / 0 failed / 0 errors / 8 skipped, exit 0**
  (`$TMPDIR/full_s30.log`).
* Opt-in browser module 8 passed / exit 0.
* `node --check web/static/app.js` exit 0.

### Still absent (do not fake)

UI wiring for the 5 new capabilities; quick-layer persistence; per-marker
suppression persistence; canvas context menu; multi-symbol grid; non-time-based
chart types.

---

## 2026-10-18 workbench session 29 — complete the Objects manager, detector-marker lifecycle, measured Fibonacci viewport

Follows the read-only session-28 verification, which found (a) quick-layer
overlays/panes absent from the Objects manager and (b) detector markers that were
rebuilt/lost on reload. Frontend only; same safety envelope (prod `8710`
untouched, dev `127.0.0.1:10000` + `data/dev/release`, no commits). Cache-buster
`app.js?v=wb23`.

### Shipped / fixed

* **Quick layers are now first-class chart objects** (B-107). `loadChart`
  registers one `state.quickObjects` descriptor per toolbar toggle and the manager
  gained a **Quick layers** group (label / type / owner / visibility + Hide/Show +
  Remove). Hide/Remove act on the real primitive — series `visible`, pane element
  + `chart.remove()`, unchecking the toolbar toggle — and Remove also drops the
  markers a quick layer owns (the swings layer owned 27).
* **Candle-marker cross-symbol leak** (B-108): `destroyCharts()` resets
  `state.candleMarkers` (+ `state.quickObjects`); NABIL 122 → ADBL 0.
* **Pattern markers lost on reload** (B-109): the layer path fetches
  (`loadPatternPanel`) instead of only re-rendering the panel; 9 → reload → 9.
* **Pattern overlay cross-symbol leak** (B-110): `#pattern-overlay` is synced to
  the current symbol's layer flag before `loadChartInsights`; NABIL 9 → ADBL 0.
* **No duplicate objects across reloads** verified over three full reloads.

### Verified (browser, real trusted events; `TEST_RESULTS.md` §29)

* **Fibonacci viewport measured** (the session-28 gap): manual `fib_retracement` /
  `fib_extension` and automatic `fib` each preserved the visible logical range
  byte-for-byte — `{75,175}` in normal mode, `{87,187}` in expanded mode — with
  existing drawings/indicators intact and **0 console errors**.
* New opt-in browser regression module `tests/test_browser_objects_manager.py`
  (8 cases; skipped without `MEGATOOL_BROWSER_TESTS=1`).
* Screenshot `docs/evidence/wb24-objects-quick.png`.

### Honest gaps

Quick-layer toggles remain unpersisted display toggles (so swing-marker quick
layers cannot reconstruct after a reload), and per-marker suppression stays
session-only. Both are deliberate; recorded in `REMAINING_BLOCKERS.md` §23–§24
and `KNOWN_BUGS.md` (session-29 open gaps).
