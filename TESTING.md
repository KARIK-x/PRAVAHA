# Testing

Every claim in this file was verified by executing the named command on the project
 MacBook (macOS, Python 3.12, `uv`-managed environment).

## Baseline (2026-10-12)

| Command | Result |
| --- | --- |
| `uv run pytest` | **511 passed**, ~20 s |
| `ruff check .` | clean |
| `ruff format .` | clean |

Per-file test counts:

| File | Tests | What it covers |
| --- | --- | --- |
| `tests/test_api.py` | 73 | Route behaviour, validation, error mapping, review endpoint, journal fallback |
| `tests/test_audit_a_fixes.py` | 45 | Regression tests for defects found by Audit A and Audit B |
| `tests/test_backtest.py` | 32 | Long/flat engine, fills, fees, assumptions |
| `tests/test_cli_floor.py` | 9 | `megatool floor import` / `floor summary` |
| `tests/test_floorsheet.py` | 25 | CSV parsing, HHI, counterparties, concentration |
| `tests/test_forecast.py` | 29 | Six models, hold-out scoring, skill ratio |
| `tests/test_indicators.py` | 132 | 28 indicators, reference values, warm-up, edge cases |
| `tests/test_journal.py` | 30 | CRUD, win rate, R multiples, plan adherence, unknown fields |
| `tests/test_planning.py` | 21 | Position sizing, R multiples, warnings |
| `tests/test_portfolio.py` | 29 | Ledger-derived positions, P&L, validation, UTC normalisation |
| `tests/test_research.py` | 32 | Cited findings, question routing, refusal of predictions, journal-only answer |
| `tests/test_scanner.py` | 21 | Metrics, presets, filter-tree validation |
| `tests/test_written_pdf.py` | 28 | PDF extraction, validation, idempotent import, confidence filter, review workflow |

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
