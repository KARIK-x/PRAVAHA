# Test results

**Last run:** 2026-10-13 · **774 passed, 0 failed, 0 skipped** · 52.49 s · exit 0
**Lint:** `ruff check` clean · `ruff format --check` clean (62 files)
**Front end:** `node --check web/static/app.js` clean

Reproduce (this run used the `.venv` interpreter directly — same suite, `addopts` supplies `-q`):

```bash
cd "/Users/ashim/Downloads/AI trading NEPSE"
.venv/bin/python -m pytest -p no:warnings      # or: uv run pytest
uv run ruff check megatool/ tests/ scripts/
uv run ruff format --check megatool/ tests/ scripts/
node --check web/static/app.js
python scripts/route_inventory.py              # exits non-zero if a route lacks tests
```

> `addopts` already contains `-q`. Adding another `-q` suppresses the summary
> line and makes it look like no result was printed.

---

## Per-file counts

| File | Tests |
|---|---:|
| `test_indicators.py` | 132 |
| `test_api.py` | 96 |
| `test_written_transcribe.py` | 57 |
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
| `test_floorsheet.py` | 25 |
| `test_walkforward.py` | 23 |
| `test_scanner.py` | 21 |
| `test_planning.py` | 21 |
| `test_written_reference.py` | 20 |
| `test_cli_floor.py` | 9 |
| `test_cli_serve.py` | 3 **(new)** |
| `test_route_inventory.py` | 3 **(new)** |
| **Total (21 files)** | **774** |

### Added this session (766 → 774)

| Test | File | Why |
|---|---|---|
| `test_portfolio_delete_transaction_removes_it_from_the_ledger` | `test_api.py` | **API coverage gap:** `DELETE /api/portfolio/transactions/{tx_id}` had only a 404 test. Asserts the row actually leaves the ledger (count drops, id gone, re-delete 404s) — a delete returning 200 while leaving the row would corrupt realised P&L |
| `test_walk_forward_report_loader_applies_the_invalid_filter` | `test_financial_integrity.py` | **§2.4 defect:** `walk_forward_report.py` read `price_bars` with raw SQL and bypassed B-17's filter, so the canonical research tool fed 124 impossible rows into the walk-forward. Asserts `load_frames()` and `get_bars()` agree exactly |
| 3 × serve bind warning | `test_cli_serve.py` | Non-loopback bind warns about no authentication; loopback stays quiet; unset host falls back to config |
| 3 × route classification | `test_route_inventory.py` | `smoke_live.py` and `route_inventory.py` must agree on which POSTs mutate, every named mutating POST must exist, and no DELETE/PATCH may ever be classed read-only |

Progression: 511 (13 files) → 602 → 650 → 707 → 709 → 729 → 731 → 759 → 764 → 766 → **774** (21 files).

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
