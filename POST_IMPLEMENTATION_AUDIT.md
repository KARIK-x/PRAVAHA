# Post-Implementation Audit

**Date:** 2026-10-19
**Scope:** The four newly implemented capabilities (data-source reconciliation, NF-014
snapshots, NF-015 evidence-bound research, NF-016 natural-language query) plus the
previously "blocked" features NF-001/004/018/020/025/028, audited against the live
development instance and the real release dataset.
**Method:** source inspection + direct engine calls + HTTP API calls + browser
interaction (playwright-cli) + the full pytest suite. Every number below is a
recorded observation, not an estimate.

---

## 1. State at audit time

| Item | Value | How observed |
|---|---|---|
| Git HEAD | `b6c36595d20d6a32f55b4bc2538067434c6886ec` | `git rev-parse HEAD` |
| Branch | `main` | `git status` |
| Changed paths | 317 (262 untracked, 55 modified) | `git status --porcelain` |
| Staged | 0 | `git diff --cached --name-only` |
| Commits made this session | none | not authorised |
| Dev server | `127.0.0.1:10000` → HTTP 200 | `curl` |
| **Production server** | `127.0.0.1:8710` → HTTP 200, **PID 26596 untouched** | `lsof`/`curl` |
| App DB schema | 11 | `init_app_db()` |
| Catalogue | 124 scanners + 77 algorithms + 32 fundamentals = **233**, health OK | `catalog_health()` |

The release dataset was used for all live checks:
372 securities, 515,327 genuine OHLC bars, 2,217 genuine NEPSE-index bars (plus 3,079
close-only placeholder bars), 21,698 fundamental records over 307 symbols, all prices
`unadjusted`, daily granularity only.

> Note on the market store: it is a single-writer DuckDB file. While the dev server
> holds it read-write, a **separate** process cannot open it (DuckDB raises
> `Conflicting lock`). Live checks therefore go through the HTTP API (which shares the
> server's connection), and standalone checks use the unlocked `data/dev/qa` copy. This
> is recorded, not worked around by disabling the lock.

---

## 2. Delivered this session

| Capability | Module | API | UI | Tests |
|---|---|---|---|---|
| Data-source reconciliation | `megatool/reconcile.py` | `/api/reconciliation/*` | KIMI → **Reconciliation** | `tests/test_reconcile.py` (20) |
| NF-014 snapshots | `megatool/snapshots.py` | `/api/snapshots*` | KIMI → **Snapshots** | `tests/test_snapshots.py` (15) |
| NF-015 evidence research | `megatool/research_desk.py` | `/api/research-desk/*` | KIMI → **AI Research** | `tests/test_research_desk.py` (15) |
| NF-016 natural-language query | `megatool/nlquery.py` | `/api/query/*` | KIMI → **Ask the Data** | `tests/test_nlquery.py` (27) |
| NF-025 point-in-time | `megatool/fundamentals.py` | `/api/fundamentals/as-of` | (in-stage) | `tests/test_fundamentals_pit_revisions.py` (10) |
| NF-028 revision monitor | `megatool/fundamentals.py` | `/api/fundamentals/revisions` | (in-stage) | same file |
| NF-004/020 corporate events | `megatool/corporate_events.py` | `/api/corporate-events/*` | KIMI → **Corporate Events** | `tests/test_corporate_events.py` (17) |
| NF-018 external-scheduler command | `megatool/cli.py` | `megatool alerts evaluate` | (CLI) | exercised in CLI smoke |

API surface tests: `tests/test_phase_api.py` (18). All new endpoints have a 400/404
path tested.

**Schema change:** `SCHEMA_VERSION` 9 → 10 → **11**. New tables are additive
(`CREATE TABLE IF NOT EXISTS`), applied unconditionally by `init_app_db()`, and safe/
reversible: `reconciliation_runs`, `reconciliation_resolutions`, `calculation_snapshots`,
`fundamental_revisions`, `research_runs`, `nl_query_runs`, `corporate_events`.

---

## 3. Reconciliation — observed behaviour (release data)

`POST /api/reconciliation/run` per bucket:

| Bucket | Findings | Classification | Meaning |
|---|---|---|---|
| `fundamentals` | 0 | — | only one fundamental source exists (`yonepse/financials.json`), so there is nothing to cross-check |
| `fundamentals_staleness` | 28 | `stale` | 28 symbols with no fundamental update inside the window |
| `price_bars` | 4 | `invalid` | aggregated structural defects (below) |
| `market_quotes` | 0 | — | `market_quotes` holds 0 rows in this dataset |
| `index` | **539** | `conflict` | genuine close-value conflicts between DuckDB `index_series` and SQLite `index_ohlc_history` |

`price_bars` structural detail (aggregated per subtype, with counts + examples):

| Severity | Subtype | Count | Already flagged by platform |
|---|---|---|---|
| high | `close <= 0` | 2 | 0 |
| high | `close outside [low, high]` | 414 | 0 |
| high | `high < low` | 115 | 0 |
| low | `open outside [low, high]` | 40,040 | **40,040 (all)** |

Design decisions verified in behaviour:

* Findings are **computed on demand** — no discrepancy is cached as truth.
* Only a durable human decision is persisted (`reconciliation_resolutions`), with
  author and timestamp: 1 resolution observed
  (`index:NEPSE:2017-01-30:close`, `resolution="left_open"`, note "source data was not
  modified").
* Per-subtype aggregation avoids thousands of duplicate rows.
* `open outside [low, high]` is low severity **because** the platform's own validator
  already flags every one of the 40,040 rows (NEPSE convention), and this is stated in
  the finding rather than hidden.
* The engine does **not** auto-declare a winner by recency or completeness — a conflict
  stays a conflict until a human resolves it.
* Raw sources are untouched by any comparison or resolution.

---

## 4. NF-014 snapshots — observed behaviour

4 snapshots recorded through the API during verification, all classified
`fully_reproducible` (2 × `technical_rating`, 2 × `monte_carlo`). Rerun of
`snap-20261019T022925-ddeb536a` returned `reproduced=True` with no diff.

* Reproducibility is classified **by the module** (`fully_reproducible` /
  `partially_reproducible` / `unrecoverable`), not asserted by the caller.
* Secret-like parameter keys are scrubbed with whole-token matching *before* the engine
  runs, and no secret is ever written to a snapshot.
* `compare` reports parameter/result/version diffs; a rerun that cannot be reproduced is
  **refused** rather than reported as equal.

---

## 5. NF-015 evidence research — observed behaviour

`/api/research-desk/evidence?symbol=NABIL` returned **15 evidence items, 0 missing**,
each with a source and a stated calculation, e.g.:

```
fact         Latest stored close = 546.0 NPR          (price_bars, last stored close)
calculation  Price-row validation = 17 suspect / 3517 rows  (megatool.quality)
calculation  Technical rating (bearish) = 25.0 0-100  (megatool.catalog)
calculation  Volatility percentile = 81.35 %          (megatool.catalog)
fact         Fundamental: eps = 28.36 NPR             (yonepse/financials.json)
```

`/api/research-desk/run` with **no provider configured** returns `available=false`, an
explicit error, and still the full evidence bundle plus a rule-based review
(verdict + checks). The research tools remain usable when the model is unavailable, and
the app never substitutes general knowledge for evidence. No code path touches the
portfolio ledger or places a trade (asserted by a test).

A defect found *during* this audit and fixed: the evidence bundle previously read a
non-existent key from the technical-rating engine and emitted `Technical rating = None`,
which reads like a real measurement of nothing. It now maps each engine's headline key
explicitly and, when a key is absent, records a **"missing"** entry instead of `None`.

---

## 6. NF-016 natural-language query — observed behaviour

`POST /api/query/run` battery (14 questions):

| Question | Status | Rows |
|---|---|---|
| how many securities | ok | 1 |
| price of NABIL | ok | 1 |
| close of NABIL on 2025-06-16 | ok | 1 |
| highest close of NABIL in 2025 | ok | 1 |
| average close of NABIL over last 30 days | ok | 1 |
| how many bars for NABIL | ok | 1 |
| top 5 symbols by volume | ok | 5 |
| eps of NABIL | ok | 1 |
| eps history of NABIL | ok | 19 |
| close of NEPSE index | ok | 5 |
| drop table price_bars | **rejected** | — |
| select * from users | **rejected** | — |
| list everything from information_schema.tables | **rejected** | — |
| what is the meaning of life | **rejected** | — |

* Parsing is **rule-based (no LLM)** over an explicit table/column allowlist
  (`securities`, `fundamentals`, `collector_quotes`, `price_bars`, `index_series`).
* Parameters are always bound; every query is bounded by a LIMIT and a scan guard;
  excess limits and unknown symbols/dates are rejected.
* Questions containing SQL metacharacters (`;`, `--`, `/*`, quotes, backslash) are refused
  outright.
* Every run — including refusals — is written to `nl_query_runs` for audit: 19 rows
  observed, with the 4 refusals recorded with their reason.

---

## 7. Formerly "blocked" features — audit outcome

| Feature | Audit finding | Status after this session |
|---|---|---|
| NF-001 floorsheet | engine, import, API, CLI all present; 74 related tests pass; **0 rows ingested** in dev | IMPLEMENTED / TESTED-PASS, DATA-DEPENDENT (not code-blocked) |
| NF-004 corporate calendar | no dividend/bonus/AGM feed; an **attested retirement/merger registry exists with real dates** | PARTIAL — registry projected + typed import surface added |
| NF-018 unified alerts | full rule engine + history + cooldown + API present; **no scheduler** | IMPLEMENTED (on-demand) + one-shot `alerts evaluate` CLI for an external scheduler |
| NF-020 IPO/rights/allotment | no event data source, no table | PARTIAL — typed import surface + calendar added, starts empty |
| NF-025 point-in-time | no publication dates exist | PARTIAL — ingestion-time knowledge view + explicit disclosure (publication-date archive NOT IMPLEMENTED) |
| NF-028 revision monitor | no pre-existing history | PARTIAL — going-forward old→new logging + monitor; prior history unrecoverable and stated |

Full detail in `BLOCKED_FEATURES_AUDIT.md`.

---

## 8. Regression and browser evidence

* **Full suite:** `tests=2921 failures=0 errors=0 skipped=8` (98.5 s, exit 0), run via
  `pytest --junitxml` with `MEGATOOL_DATA_DIR=data/dev/release`.
* **Skipped 8** are the opt-in browser tests in `tests/test_browser_objects_manager.py`;
  re-run with `MEGATOOL_BROWSER_TESTS=1` against the live dev server: **8 passed, exit 0**.
* **Catalogue browser audit:** all **233** catalogue entries opened in the browser — 124
  scanners, 77 algorithms, 32 fundamentals — each information panel verified to show its
  own id, name and Limitations section, with a Run action present. See
  `CATALOGUE_BROWSER_AUDIT.md`.
* **New KIMI tabs** (7 added/rewired; KIMI now has 17 catalogues-adjacent tab buttons):
  Reconciliation, Snapshots, AI Research, Ask the Data, Corporate Events — all render
  with correct tab tracking, no `undefined`/`[object Object]`/error text, and their Run /
  Capture / Import flows work end-to-end.

---

## 9. Open items (honest)

* Reconciliation was verified through the API against the release dataset; standalone
  store-backed reconciliation was verified against `data/dev/qa` (release store is
  locked by the dev server). Two datasets have no cross-source material in this install
  (`fundamentals` single source, `market_quotes` empty) — that is a data fact, not a
  hidden failure.
* NF-004/020 notices and NF-001 floorsheet rows require an external document/credentialed
  collector run; the import + storage paths exist and are tested with synthetic input.
* NF-018 autonomous scheduling requires an OS-level timer (cron/launchd/systemd); the app
  intentionally runs no background thread. The unit of work is now a tested CLI command.
* NF-025 publication dates and NF-028 pre-existing revision history cannot be
  reconstructed from the data that exists; both are stated in-product.
* No commit, push, staging or deploy was performed. Production (PID 26596, :8710) was not
  touched at any point.
