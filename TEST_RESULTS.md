# Test results

**Last run:** 2026-10-12 · **650 passed, 0 failed, 0 skipped** · 33.93 s · exit 0
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
| `test_fundamentals.py` | 56 **(+12)** |
| `test_written_pdf.py` | 39 **(+3)** |
| `test_financial_integrity.py` | 33 **(new)** |
| `test_research.py` | 32 |
| `test_backtest.py` | 32 |
| `test_journal.py` | 30 |
| `test_portfolio.py` | 29 |
| `test_forecast.py` | 29 |
| `test_ranking.py` | 27 |
| `test_floorsheet.py` | 25 |
| `test_scanner.py` | 21 |
| `test_planning.py` | 21 |
| `test_cli_floor.py` | 9 |
| **Total** | **650** |

Progression: 511 (13 files) → 602 → **650** (16 files).

---

## What the new tests cover

### `test_financial_integrity.py` (33, new) — Phase 2 of the completion audit

Every expected value in this file is worked out by hand, in comments, from a
fixture written by hand. Nothing asks the module under test for its own
expected value.

| Area | What is asserted |
|---|---|
| Settlement arithmetic | The four page-21 nets verified by ordinary subtraction *before* calling the validator; both sign conventions; an exactly-representable tolerance boundary; and the real B-02 transcription error (177,609.76) proven to be caught |
| Percentile math | Distinct values → 33.33/66.67/100; ties → average rank; n fully tied → `(n+1)/(2n)×100` (62.5 at n=4, 50.135 at n=369) |
| Ranking scores | A 4-symbol fixture whose scores are computed by hand in the source comment: **71.875 / 63.125 / 54.375 / 45.625**, all reproduced exactly |
| Directionality | Volatility inverted so the calmest symbol ranks best; and the L-06 asymmetry pinned (best scores `100 − 100/n`, never 100) |
| Unavailable factors | P/E, P/B, yield, index-relative and sector-relative absent from both contributions and effective weights |
| Substitution | Substituted value equals the cross-sectional median; symbol disclosed as incomplete; **and scores do move** when the gap symbol is present (L-05) |
| Portfolio ledger | Hand-replayed 4-trade ledger → avg cost 555.50, realized P&L exactly **20,075**, fees counted once per side, oversell refused without mutating the ledger |
| Backtest costs | Round trip hand-computed → fees **398.40**, final equity **99,601.60**, and `initial − final == fees` exactly |
| Backtest timing | `next_open` fills at the bar *after* the signal (entry 40.0, not the signal bar's close of 10.0); `same_close` buys at the signal bar and must be labelled |
| Duplicate trades | Rapid signal toggling → distinct `(entry, exit)` pairs, none duplicated, none ending before they start |
| Market data | Per-row provenance present; `(symbol, date)` unique; and B-17's unfiltered `invalid` rows pinned as current behaviour |

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
