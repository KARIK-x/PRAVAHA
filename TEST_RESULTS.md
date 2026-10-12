# Test results

**Last run:** 2026-10-12 · **602 passed, 0 failed, 0 skipped** · 18.55 s
**Lint:** `ruff check` clean · `ruff format --check` clean (48 files)
**Front end:** `node --check web/static/app.js` clean

Reproduce:

```bash
cd "/Users/ashim/Downloads/AI trading NEPSE"
uv run pytest
uv run ruff check megatool/ tests/ scripts/
uv run ruff format --check megatool/ tests/ scripts/
node --check web/static/app.js
```

> `addopts` already contains `-q`. Adding another `-q` suppresses the summary
> line and makes it look like no result was printed.

---

## Per-file counts

| File | Tests |
|---|---:|
| `test_indicators.py` | 132 |
| `test_api.py` | 90 |
| `test_audit_a_fixes.py` | 45 |
| `test_fundamentals.py` | 44 **(new)** |
| `test_written_pdf.py` | 36 **(+3)** |
| `test_research.py` | 32 |
| `test_backtest.py` | 32 |
| `test_journal.py` | 30 |
| `test_portfolio.py` | 29 |
| `test_forecast.py` | 29 |
| `test_ranking.py` | 27 **(new)** |
| `test_floorsheet.py` | 25 |
| `test_scanner.py` | 21 |
| `test_planning.py` | 21 |
| `test_cli_floor.py` | 9 |
| **Total** | **602** |

Previous run: 511 (13 files). +91 tests across 3 new/extended files.

---

## What the new tests cover

### `test_ranking.py` (27) — multi-factor ranking

Score decomposition (contributions reproduce the score exactly), percentile
bounds, determinism, weight/`min_bars`/`max_missing_fraction` validation,
missing-factor median substitution, exclusion with a stated reason, universe
accounting (`ranked + excluded == universe`), `as_of` truncation including the
store's `trading_date` column name, volatility inversion, and JSON
serialisation.

### `test_fundamentals.py` (44) — Fundamentals Lab

Record validation (source required, finite values, unit conformance, symbol and
verification formats), CSV row parsing (bad dates, non-numeric values,
duplicates, row-numbered errors), storage idempotency including unknown-period
rows, two-source retention, and the ratio guards.

### `test_written_pdf.py` (+3) — settlement regression

All four page-21 settlements must reconcile, both sign conventions accepted,
and a wrong net must still raise.

### `test_api.py` (+17) — `/api/rank` and `/api/fundamentals/*`

Ordered scores with explanations, unavailable factors at zero weight, "not a
prediction" disclaimer, 400s for bad weights, 404 for unknown symbols, `as_of`
truncation, the nothing-rankable case, CSV import/query/idempotency,
malformed-CSV rejection, and `dry_run` writing nothing.

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
| **Apple Vision** | **71.7% (66/92)** | **90.2% (83/92)** | **33/46** | 0.79–1.73 s |

Per page (Apple Vision): p02 88%/97%, p09 81%/100%, p11 92%/92%,
p18 32%/74%, p21 58%/83%.

`data/written_pdf/benchmark/` holds the ground truth and raw outputs. That
directory is **git-ignored** because the ground truth transcribes the owner's
private handwritten records.

---

## Live verification (real store, not fixtures)

Checked against the running server on `127.0.0.1:8710`:

| Check | Result |
|---|---|
| `/api/health` | 514,018 bars · 372 symbols |
| `/api/rank` on the real universe | 372 requested → 369 ranked, 3 excluded with reasons |
| Score integrity on real data | 0 of 369 had contributions that did not sum to the score |
| Median substitution flagged | 8 symbols marked incomplete (all `momentum_6m`) |
| Schema migration v3 → v4 | `fundamentals` table created, 0 rows |
| Fundamentals dry-run in browser | "Valid: 2 rows — nothing written"; real store still 0 rows |
| Console across all 11 tabs | 0 errors, 0 warnings |

Screenshots: `docs/screenshots/ranking-panel.png`,
`docs/screenshots/fundamentals-tab.png`.
