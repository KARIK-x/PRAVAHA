# Data-Source Reconciliation Report

**Module:** `megatool/reconcile.py`
**API:** `/api/reconciliation/{datasets,profile,run,resolve,history}`
**UI:** KIMI → **Reconciliation** tab
**Tests:** `tests/test_reconcile.py` (20) + `tests/test_phase_api.py` (18, shared)
**Date:** 2026-10-19 · **Data:** `data/dev/release` (real), `data/dev/qa` (standalone)

---

## 1. Purpose and contract

Different sources in this project can disagree: a security's close can differ between
the DuckDB price series and a collected quote, or between two index series. The
reconciliation engine **surfaces** those disagreements for a human to adjudicate. It is
built on four firm rules:

1. **Compute on demand.** Findings are recalculated on every run and are never cached as
   truth. Nothing in the store is modified by a comparison.
2. **Never pick a winner by default.** Newer, more complete or higher-volume is not a
   reason to declare a source correct. A conflict stays open until a human decides.
3. **Persist only decisions.** The single durable artifact is a resolution: who decided
   what, when, and why. Raw sources are never rewritten.
4. **State what the comparison can and cannot see.** A dataset with one source, or none,
   says so; a clean result is not dressed up as a passing cross-check.

---

## 2. Inventory and profile (aggregate-only)

`/api/reconciliation/datasets` returns an inventory built with SQL aggregates only — no
full-table load (early versions loaded whole tables and made the endpoint take seconds;
the current version answers in **0.08 s**):

```
fundamentals      rows=21698  sources=1
price_bars        rows=515327 sources=1
market_quotes     rows=0      sources=0
comparisons = [fundamentals, fundamentals_staleness, index, market_quotes, price_bars]
```

A comparison spanning more than one dataset has no single-dataset profile, and the API
says exactly that rather than inventing one.

---

## 3. Comparisons available

| Comparison | Datasets joined | Checks performed |
|---|---|---|
| `fundamentals` | cross-source | same `(symbol, field, period_end)` value across sources; per-source coverage; duplicate keys |
| `fundamentals_staleness` | `fundamentals` | symbols not updated inside the freshness window |
| `price_bars` | cross-source | same `(symbol, date)` close across sources; OHLC structural validity; timestamp defects; duplicate keys |
| `market_quotes` | cross-source | quote agreement across sources; timestamps; duplicates |
| `index` | DuckDB `index_series` ↔ SQLite `index_ohlc_history` | same `(index, date)` close across the two stores |

Join-key values are normalised (`_keyval`) so a DuckDB `DATE`/`DATETIME` matches the
SQLite ISO text instead of producing thousands of phantom "missing observation" rows.

---

## 4. Findings on the real release dataset

```
fundamentals             findings=0     {}
fundamentals_staleness   findings=28    {'stale': 28}
price_bars               findings=4     {'invalid': 4}
market_quotes            findings=0     {}
index                    findings=539   {'conflict': 539}
```

### 4.1 `price_bars` — 4 aggregated structural findings

| Severity | Subtype | Count | Platform already flags |
|---|---|---|---|
| high | `close <= 0` | 2 | 0 |
| high | `close outside [low, high]` | 414 | 0 |
| high | `high < low` | 115 | 0 |
| low | `open outside [low, high]` | 40,040 | 40,040 (all) |

Aggregation: each **subtype** is one finding carrying its count and up to a few example
`SYMBOL@DATE` rows, so a 40k-row defect does not produce 40k rows of report. The
`open outside [low, high]` subtype is classified **low** and the finding states that the
platform's own validator already flags **all 40,040** rows — this is a documented NEPSE
convention, not a new defect. Classifying it high would drown the three genuine
structural defects above it.

### 4.2 `index` — 539 genuine conflicts

```
id: index:NEPSE:2017-01-30:close   classification: conflict   severity: medium
key: {"match_key": ["NEPSE","2017-01-30"], "field": "close"}
```

539 dates where the two index stores disagree on the close. The engine reports the
sources and both values; it does not choose. Example keys observed:
`2017-01-30`, `2018-12-31`, `2019-01-27`.

### 4.3 Datasets with nothing to reconcile

* `fundamentals` → 0. This is correct: only **one** fundamental source exists
  (`yonepse/financials.json`), so there is no second opinion to cross-check. The result
  is reported as "no cross-source material", not as "verified correct".
* `market_quotes` → 0 because the table holds **0 rows** in this dataset. Absence of data
  is reported as absence of data.

### 4.4 Staleness

28 symbols have no fundamental update inside the freshness window — an actionable
maintenance signal, distinct from a value conflict.

---

## 5. Resolution workflow

`POST /api/reconciliation/resolve` records a decision against a finding key. Observed
resolution:

```json
{
  "id": 1,
  "dataset": "index",
  "finding_key": "index:NEPSE:2017-01-30:close",
  "classification": "conflict",
  "chosen_source": "close:A (binayabaral/NEPSE_INDEX.csv)",
  "resolution": "left_open",
  "note": "Source data was not modified."
}
```

* A resolution requires a known finding key; an unknown key is rejected (400).
* `resolution="left_open"` is a first-class outcome: leaving a conflict open is itself a
  recorded decision.
* No resolution path mutates the market store; the note confirms the source data was not
  modified.
* `GET /api/reconciliation/history` lists runs and resolutions for audit.

---

## 6. Verification

* **Unit:** `tests/test_reconcile.py` — 20 tests covering inventory/profile, equal /
  conflict / tolerance paths, unit mismatch, unperiodised values, missing observation,
  timestamp defects, staleness, cross-source close-vs-quote, aggregated structural
  findings, a duplicate-probe table, index conflict, run/history persistence, resolve
  validation, and the explicit "no auto-resolution / no newer-source preference"
  invariant. **PASS.**
* **API:** `tests/test_phase_api.py` — the reconciliation routes incl. 400/404 cases.
  **PASS.**
* **Browser (dev :10000):** Reconciliation tab → select `index` → Run → 539 findings,
  300 Resolve buttons, no `undefined`; open a finding → choose `left_open` → Save →
  "Decision recorded … Source data was not modified"; history shows `left_open`;
  `price_bars` → 4 aggregated findings. **PASS.**
* **Standalone store:** exercised against `data/dev/qa` (the release store is locked by
  the running dev server).

---

## 7. Limitations (stated, not hidden)

* Reconciliation is **observation-only**. It cannot decide which index source is right;
  that remains a human judgement recorded as a resolution.
* Fields are compared with an explicit tolerance; absolute equality is not assumed for
  floating-point values.
* Cross-source checks require ≥2 sources for a key. Where only one exists the engine says
  so rather than implying agreement.
* Timestamp checks describe the defect (e.g. ingestion time vs trading date); they do not
  silently repair it.
