# Testing

Every claim in this file was verified by executing the named command on the project
 MacBook (macOS, Python 3.12, `uv`-managed environment).

## Baseline (2026-10-13, latest run)

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest -p no:warnings` | **1105 passed**, 48.49 s, exit 0 |
| `node --check web/static/app.js` | clean, exit 0 |
| `python scripts/route_inventory.py` | **50 routes**, all covered, exit 0 |
| `python scripts/smoke_live.py` | **40 probed · 40 expected · 0 unexpected · 10 writes skipped**, exit 0 |
| `ruff check .` | **clean**, exit 0 |
| `ruff format --check .` | **exit 1 — one file**: `AI Trading Nipsy/MEGA_TOOL_RESEARCH_REPORT.md` |

> **The one red gate is not project code.** `AI Trading Nipsy/` is an **untracked
> owner folder** that appeared after the previous baseline; ruff scans every
> `.md`, so it reaches code fences inside that research report. The file was
> **deliberately left unmodified** — reformatting the owner's own untracked
> document in order to turn a gate green is precisely the silent tampering this
> project forbids. Every tracked project file formats clean. If the owner wants
> the gate green, the right fix is to exclude that folder in `pyproject.toml`,
> which is an owner decision, not something to do unilaterally.
>
> Earlier baselines in this file recorded `ruff check` failing with 81 errors in
> the candlestick/summary files. **Those were fixed**; the gate has been clean
> since. That history is kept below rather than rewritten.


### Tests added 2026-10-13 (796 → 982, +186)

| File | Tests | What it covers |
| --- | ---: | --- |
| `tests/test_candles.py` | 104 | 15 candlestick patterns: positives, near-miss negatives, reversed directions, zero-range candles, invalid/non-finite OHLC, short history, tolerance boundaries |
| `tests/test_api.py` | 115 *(was 101)* | +8 Fibonacci/S-R route tests (values round-trip through the shared module, 50% family label, caveats, `min_touches` default, 404/400/422) |
| `tests/test_levels.py` | 24 | S/R zone clustering: hand-worked zones, input-order independence, tolerance boundary, ATR fallback, `min_touches`, no `confidence` key |
| `tests/test_fibonacci.py` | 23 | Levels hand-computed from the formula (not by re-calling the code), anchor mirroring, convention labelling, invalid anchors |
| `tests/test_workspace.py` | 16 | Dated non-live overview, `NOT_STARTED` honesty on filtered modules, failure visibility, no `confidence`/`buy`/`sell` in the payload |
| `tests/test_market_store_concurrency.py` | 5 | **B-19 regression**: locked-helper contract, a source guard forbidding unlocked reads, 8-thread stress asserting no exception and no mixed results |

### Baseline (2026-10-12) — superseded, kept for the progression

| Command | Result |
| --- | --- |
| `uv run pytest` | **796 passed**, ~35 s |
| `ruff check .` | clean |
| `ruff format .` | clean |

Per-file test counts:

| File | Tests | What it covers |
| --- | --- | --- |
| `tests/test_indicators.py` | 132 | 28 indicators, reference values, warm-up, edge cases |
| `tests/test_api.py` | 90 | Route behaviour, validation, error mapping, review endpoint, journal fallback, `/api/rank`, `/api/fundamentals/*` |
| `tests/test_written_transcribe.py` | 57 | Reading rules, one canonical record shape, inspection ≠ transcription, non-reconciling blocks, the withdrawn figure |
| `tests/test_fundamentals.py` | 56 | Provenance, units, periods, verification levels, CSV validation, idempotent storage, ratio guards |
| `tests/test_written_reference.py` | 20 | Secondary-digitization labelling, settlement-block regressions, totals and component cross-checks, CSV encoding |
| `tests/test_audit_a_fixes.py` | 45 | Regression tests for defects found by Audit A and Audit B |
| `tests/test_written_pdf.py` | 46 | PDF extraction, validation, idempotent import, confidence filter, review workflow, settlement reconciliation, extraction_method provenance, append-only correction history, renamed-copy dedup (B-18) |
| `tests/test_financial_integrity.py` | 37 | Hand-computed fixtures for money, P&L and ratio arithmetic; B-17 invalid-bar filtering |
| `tests/test_research.py` | 32 | Cited findings, question routing, refusal of predictions, journal-only answer |
| `tests/test_backtest.py` | 32 | Long/flat engine, fills, fees, assumptions |
| `tests/test_journal.py` | 30 | CRUD, win rate, R multiples, plan adherence, unknown fields |
| `tests/test_portfolio.py` | 29 | Ledger-derived positions, P&L, validation, UTC normalisation |
| `tests/test_forecast.py` | 29 | Six models, hold-out scoring, skill ratio |
| `tests/test_ranking.py` | 27 | Score decomposition, missing-data handling, exclusion reasons, `as_of` truncation, factor polarity |
| `tests/test_floorsheet.py` | 25 | CSV parsing, HHI, counterparties, concentration |
| `tests/test_scanner.py` | 21 | Metrics, presets, filter-tree validation |
| `tests/test_swings.py` | 17 **(new)** | Swing pivots on a hand-built zigzag, **prefix-recomputation causality**, confirmation lag, plateau handling, prominence, structure labels, break-of-structure dating |
| `tests/test_planning.py` | 21 | Position sizing, R multiples, warnings |
| `tests/test_walkforward.py` | 23 | Walk-forward validation: hand-derived spreads, no look-ahead, trim equivalence, staleness, chance baseline |
| `tests/test_cli_floor.py` | 9 | `megatool floor import` / `floor summary` |
| **Total (22 files)** | **796** | |

A separate, non-pytest benchmark measures handwriting extraction on five
ground-truthed PDF pages — see `TEST_RESULTS.md` for the numbers and
`uv run python scripts/score_benchmark.py` to reproduce it.

## How to run

```bash
cd "Downloads/AI trading NEPSE"

uv run pytest                # full suite
uv run pytest -k journal     # subset by name
uv run pytest tests/test_indicators.py -v   # one file, verbose
uv run ruff check .          # lint
uv run ruff format .         # format
```

## Isolation model

An autouse fixture in `tests/conftest.py` redirects **both** databases to a throwaway
directory for every test:

```python
monkeypatch.setattr(Paths, "app_db", property(lambda self: tmp_path / "isolated_state.sqlite"))
monkeypatch.setattr(Paths, "market_db", property(lambda self: tmp_path / "isolated_market.duckdb"))
```

This exists because of a real incident: a test helper once omitted its `db_path` and
wrote 14 synthetic journal rows into the owner's real database during a normal test run.
The fixture makes that class of mistake impossible rather than relying on every test
remembering to pass a path.

The owner's real `data/processed/` databases are never written to by the test suite.
This is verified after every full run by counting rows in every state table.

## What the tests do NOT prove

- **That the app works end to end in a browser.** Unit and API tests exercise the
  Python layer. Browser-level behaviour (chart rendering, click-throughs, console
  errors) was verified separately with Playwright on 2026-10-11 and is recorded in
  `PROJECT_STATUS.md` §2; it is not re-proven by `pytest` passing.
- **That live market data is current.** The data is stored end-of-day closes from a
  third-party GitHub dataset. No live feed exists.
- **That any forecast or backtest predicts the future.** Tests assert the
  *arithmetic* of a backtest or forecast, not its financial accuracy.

## Notable regression tests

These exist because a specific defect was observed and fixed; each names the finding
it pins down so a future reader can tell what it protects against.

| Test | Defect it holds the line on |
| --- | --- |
| `test_indicators.py::test_rsi_flat_series_is_undefined` | RSI reported **100** (max bullish) on a series that never moved — `0/0` treated as `+∞` (B-23) |
| `test_indicators.py::test_mfi_no_money_flow_is_undefined` | MFI reported **100** when there was no money flow at all — same `0/0` shape (B-24) |
| `test_indicators.py::test_rsi_flat_series_is_neither_0_nor_100` | Guards against "fixing" the above by substituting the other directional value |
| `test_indicators.py::test_mfi_rising_prices_report_exactly_100` | Guards against the new `p > 0` guard overreaching into genuine all-positive flow |
| `test_summary.py::test_engine_itself_reports_mfi_as_undefined_not_100` | The summary layer must not be hiding an engine defect behind a mask |
| `test_indicators.py::test_rsi_flat_tail_retains_prior_momentum` | Pins Wilder momentum retention through a flat tail as *intended*, so nobody "fixes" it into a new bug |
| `test_scanner.py::test_flat_symbol_reports_rsi_as_unavailable_not_overbought` | A flat symbol matched `rsi > 70` screens because the engine returned 100 |
| `test_audit_a_fixes.py::test_holdout_dates_stay_attached_to_their_values_when_a_close_is_nan` | Forecast hold-out rows were misdated when a close was NaN |
| `test_audit_a_fixes.py::test_a_typo_field_is_rejected_not_silently_dropped` | A typo'd journal field was accepted with 200 and silently dropped |
| `test_audit_a_fixes.py::test_a_closed_thesis_only_entry_does_not_crash_the_stats_endpoint` | Stats endpoint crashed with 500 on a legal entry |
| `test_audit_a_fixes.py::test_counterparty_share_is_over_the_whole_session` | Shares divided by the shown subset, not the session |
| `test_audit_a_fixes.py::test_a_currency_prefixed_rate_is_parsed_not_mangled` | `Rs. 1,000` parsed as 0.1 |
| `test_audit_a_fixes.py::test_a_negative_exit_price_is_refused` | Impossible exits graded as real outcomes |
| `test_audit_a_fixes.py::test_a_sell_dated_before_its_funding_buy_is_rejected` | Backdated sell corrupted realised P&L |
| `test_audit_a_fixes.py::test_a_bad_journal_edit_is_a_400_with_the_reason_not_a_500` | Bad edit returned 500 instead of 400 |
| `test_audit_a_fixes.py::test_notes_sent_as_an_edit_is_saved_instead_of_discarded` | `notes` alias discarded on PATCH |
| `test_audit_a_fixes.py::test_a_position_priced_on_an_older_day_is_flagged_and_dated` | Valuation mixed prices from different dates |
| `test_written_pdf.py::test_import_records_stores_the_real_page_count` | The PDF's page count was a hardcoded magic `52` (Audit B) |
| `test_written_pdf.py::test_min_confidence_filter_includes_that_level_and_above` | `min_confidence=high` also returned medium records (Audit B) |
| `test_api.py::test_written_pdf_record_type_is_validated_not_a_500` | `?record_type=` returned 500 instead of 400 (Audit B) |
| `test_written_pdf.py::test_review_status_refuses_returning_to_unreviewed` | A checked record could be sent back to `unreviewed`, hiding that it was once reviewed |
| `test_research.py::test_journal_only_answer_survives_a_missing_pdf_table` | A store with no `pdf_records` table raised `sqlite3.OperationalError` instead of answering |
| `test_api.py::test_research_ask_still_404s_when_there_is_nothing_to_answer` | The journal-only fallback must not turn "no data at all" into a 200 |
| `test_written_pdf.py::test_settlement_reconciliation_all_four_page21_settlements` | `validate_settlement_reconciliation` signed its comparison as `sell − buy`, so it rejected **all four correct settlements** on page 21 (labelled "Net Payable = buy − sell"). The magnitude check still raises on a genuinely wrong net |
| `test_ranking.py::test_truncation_works_with_store_column_name` | The look-ahead guard looked for a column named `date`, but `MarketStore.get_bars` returns `trading_date` — so any store-loaded frame silently bypassed the `as_of` cut |
| `test_ranking.py::test_universe_accounting_balances` | Symbols below `min_bars` were dropped before ranking, so `universe_size` no longer equalled `ranked + excluded` (observed: 4 ≠ 3 + 0) |
| `test_api.py::test_rank_reports_when_as_of_leaves_nothing_rankable` | An early `as_of` surfaced a misleading 400 ("no factor has both a positive weight and observed data") instead of an honest empty result |
| `test_fundamentals.py::test_unknown_field_allowed_when_unit_given` | The unknown-field import path was dead code: `records_from_rows` demanded an explicit unit, then `validate()` rejected that same field |
