# Blocked-Features Audit

**Date:** 2026-10-19
**Scope:** NF-001, NF-004, NF-018, NF-020, NF-025, NF-028 — the six features previously
marked blocked, re-audited to separate **"not implemented in code"** from **"implemented
but has no data / needs an external runner"**, and to implement whatever useful,
accurately-scoped part remained possible.

**Governing rule applied:** a feature is not called blocked merely because one optional
source is missing. If an honestly-scoped implementation is possible, it is built and the
data gap is stated in-product.

Status vocabulary: IMPLEMENTED · PARTIAL · BLOCKED · NOT-IMPLEMENTED · TESTED-PASS ·
DATA-DEPENDENT.

---

## Summary table

| Feature | Code today | Data today | Status |
|---|---|---|---|
| NF-001 Broker/Floorsheet | engine + import + API + CLI present, 74 related tests pass | 0 floorsheet rows in dev | **IMPLEMENTED / TESTED-PASS / DATA-DEPENDENT** |
| NF-004 Financial reporting & corporate calendar | attested retirement/merger registry + new typed event import + calendar + coverage | no dividend/bonus/AGM feed | **PARTIAL** (registry projected with real dates; notices import-based) |
| NF-018 Unified alerts | full rule engine + history + cooldown + API + new one-shot CLI | none needed (on demand) | **IMPLEMENTED**; autonomous scheduler is external (PARTIAL) |
| NF-020 IPO/Rights/Allotment | new typed import surface + calendar + coverage | no event source | **PARTIAL** (ready; starts empty) |
| NF-025 Point-in-time research | ingestion-time knowledge view + coverage disclosure | no publication dates | **PARTIAL** (publication-date archive NOT-IMPLEMENTED) |
| NF-028 Revision/discrepancy monitor | going-forward old→new logging + monitor; reconciliation covers discrepancies | no pre-existing revision history | **PARTIAL** (prior history unrecoverable, stated) |

---

## NF-001 — Broker / Floorsheet Intelligence

**Audit finding: this was never blocked in code.**
`megatool/floorsheet.py` provides `import_floorsheet`, `list_sessions`, `summary`,
`trend`. API routes exist (`POST /api/floorsheet/import`, `GET /api/floorsheet/sessions`,
`…/summary`, `…/trend`). CLI commands exist (`floor-import`, `floor-summary`). The schema
tables `floorsheet_imports` and `floorsheet_trades` exist with indexes.

```
floorsheet_trades  = 0
floorsheet_imports = 0
```

The only obstacle is that **no floor-sheet file has been ingested** in this dataset.
Import is document-based (a supplied CSV), so it needs a credentialed collector run or a
supplied file — not more code. `tests/test_floorsheet.py` + `tests/test_alerts.py` +
`tests/test_corporate_actions.py` = **74 tests, 0 failures**.

**Status:** IMPLEMENTED / TESTED-PASS / DATA-DEPENDENT. Not BLOCKED.

---

## NF-004 — Financial Reporting & Corporate Calendar

The project holds no licensed feed for dividend, bonus, AGM or reporting notices, and
such notices are not derivable from prices. However, an **attested retirement/merger
registry with real observed dates** already exists (`megatool/corporate_actions.py`).

Implemented this session (`megatool/corporate_events.py`, `corporate_events` table,
schema v11):

* a typed event **import surface** (CSV/rows) with mandatory `source` and evidence, and
  a validator that **refuses to guess a date** — a notice with no effective date is
  rejected rather than placed on the calendar at an invented date;
* a **projection** of the attested registry into the same calendar shape
  (`event_type ∈ {merger, retirement}`, `grade="attested"`, real `last_trade_date` /
  `successor_first_date`);
* a `calendar` view, a per-type `summary`, and an explicit `coverage` that names the
  missing notice types;
* API `/api/corporate-events/{import,calendar,coverage}`, a CLI `events` group, and a
  KIMI **Corporate Events** tab.

Observed on the real dataset:

```
coverage: stored 0, registry 21, missing ['allotment','bonus','rights','ipo', …]
calendar: 2023-07-13 SRBL merger attested ; PLI merger attested ; LBL merger attested
```

**Status:** PARTIAL — the historically-attested part is real and usable; the
notice-driven part is an import surface that starts empty and says so. `tests/
test_corporate_events.py` = 17 tests, PASS.

---

## NF-018 — Unified Alerts

The rule engine is complete: `make_alert_key`, `validate_condition`,
`condition_severity`, `condition_cooldown`, `alert_is_active`, `alert_last_fired`,
`cooldown_elapsed`, `evaluate_conditions`, `list_alerts`, `acknowledge_alerts`,
`clear_alerts`, and the `alert_history` table with per-condition cooldown/dedup and
fire-count semantics. API routes for evaluate/acknowledge/history/clear exist.

What is genuinely missing is **autonomous scheduling** — a background timer. The
application intentionally owns no background thread; scheduling belongs to the platform.

Implemented this session: a one-shot `megatool alerts evaluate <file.json>` CLI command,
which is the unit an external scheduler (cron / launchd / systemd timer / Windows Task
Scheduler) runs. Verified live against the unlocked QA store:

```
evaluated=1 fired=1 already_active=0 rejected=0
  warning  QABANK2  QABANK2 closed at 227.57, above the 0.0001 threshold (2026-01-09)
```

Two honest behaviours were enforced:

* an invalid condition is **rejected and counted**, not silently ignored;
* if the market store cannot be opened (e.g. held by a running server), the command
  **fails loudly with a non-zero exit** rather than reporting "no fire", because
  "no fire" and "no data" must not look alike.

**Status:** IMPLEMENTED (on-demand engine + CLI runner) / scheduler external (PARTIAL).

---

## NF-020 — IPO / Rights / Allotment Tracker

No IPO/rights/allotment data source is registered and none is derivable from prices.

Implemented this session: `ipo`, `rights` and `allotment` are first-class types in the
typed corporate-event calendar (same import surface, calendar, coverage and API as
NF-004). A row records the source and evidence and defaults to `grade="reported"`
(unverified) until checked. Coverage explicitly lists these three as **missing** until a
document is supplied — an empty list means "no notice imported", never "no event
occurred".

**Status:** PARTIAL — import surface + storage ready and tested; data-dependent;
NOT-IMPLEMENTED as a live feed (none exists).

---

## NF-025 — Point-in-Time Research Data

The obstacle is real: the project has **no publication dates** for fundamentals. It has
ingestion timestamps (`retrieved_at`) only. Reconstructing a true point-in-time view
would require inventing publication dates, which is not acceptable.

Implemented this session (`megatool/fundamentals.py`):

* `query_symbol_as_of(symbol, as_of)` — returns only records whose **ingestion time** is
  at or before `as_of` (a knowledge-time view), and
* `point_in_time_coverage()` — states exactly what the view does and does not represent,
  i.e. that it is a knowledge-time approximation, **not** a publication-date archive.

Verified behaviour: as-of before NABIL's `retrieved_at` (2026-10-16T08:20:54+00:00)
correctly returns **0 rows** rather than claiming data existed earlier.

**Status:** PARTIAL — ingestion-time knowledge view implemented and disclosed; a true
publication-date archive is NOT-IMPLEMENTED (would require data that does not exist).

---

## NF-028 — Revision / Discrepancy Monitor

Two of the three ingredients already existed; the durable revision log did not.

Implemented this session:

* `import_records` now writes an **old → new** row to `fundamental_revisions` whenever a
  stored value changes (and only then), with the honest inserted/updated split, per
  source;
* `query_revisions(symbol?)` and `revision_monitor()` expose the log;
* API `/api/fundamentals/revisions`;
* the reconciliation engine (see `DATA_SOURCE_RECONCILIATION_REPORT.md`) independently
  covers the **discrepancy** half.

The honest limit, stated in-product: the log starts **now**. Revisions that happened
before this feature existed are **unrecoverable** from the current store and are not
back-filled or guessed.

**Status:** PARTIAL — going-forward monitoring implemented and tested; pre-existing
history unrecoverable and disclosed.

---

## What remains genuinely blocked (cannot be solved by code alone)

| Item | Why it stays blocked |
|---|---|
| Floorsheet/IPO/notice **facts** | need an external document or a credentialed collector run |
| Autonomous alert **scheduling** | needs an OS-level timer; the unit of work (`alerts evaluate`) is done |
| Fundamentals **publication dates** | the data does not exist; inventing them is forbidden |
| **Pre-existing** revision history | was never recorded; cannot be reconstructed reliably |
| Kronos NABIL GPU run | awaits explicit owner approval (out of scope here) |
| python-dotenv CVE upgrade | **RESOLVED** — installed and locked at 1.2.4 (above the recommended 1.2.2); see `REMAINING_BLOCKERS.md` §11 |
| commit / push / deploy | owner decision; not performed (by rule) |

Every one of these is stated in the product or its reports rather than papered over with
fabricated data.

---

## Verification

* `tests/test_floorsheet.py` + `tests/test_alerts.py` + `tests/test_corporate_actions.py`
  = **74 tests, 0 failures** (NF-001/NF-018 engines).
* `tests/test_corporate_events.py` = **17 tests, 0 failures** (NF-004/NF-020 surface).
* `tests/test_fundamentals_pit_revisions.py` = **10 tests, 0 failures** (NF-025/NF-028).
* CLI smoke: `events coverage/import/list` and `alerts evaluate` exercised on an isolated
  data dir and on the unlocked QA store.
* No production database was written; the app DB used was the dev DB.
