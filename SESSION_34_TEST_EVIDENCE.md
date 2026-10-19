# SESSION 34 — TEST EVIDENCE

Every command below was actually run in this session. Exit codes and counts are
copied from the run output, not estimated. Nothing marked TESTED-PASS was
skipped.

Environment: `MEGATOOL_DATA_DIR="$PWD/data/dev/release"` (dev). Prod :8710 was
never touched.

---

## 1. Static

| Check | Command | Result |
|---|---|---|
| JS syntax | `node --check web/static/app.js` | exit 0 ("JS SYNTAX OK") |
| Python syntax | `python -c "import ast; ast.parse(open('megatool/api.py').read()); ast.parse(open('megatool/catalog.py').read())"` | exit 0 ("syntax OK") |

## 2. Catalogue unit/API tests (new)

Command:
```
MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest tests/test_catalog.py -q -p no:warnings
```
Result: **44 passed**, exit 0.

Covered: catalogue integrity (unique ids, health, metadata contract, every
scanner tree passes `validate_tree`), search (tag hits, all-terms, category
filter, cross-family), deterministic engines (Monte Carlo seed reproducibility
and ordering, risk-of-ruin bounds + monotonicity in risk), simplex projection,
min-variance beats equal weight, frontier weights long-only/normalised,
store-backed HRP/correlation/signal-outcomes, fundamental tools against seeded
records, honest missing-data states, and the five new API endpoints.

## 3. Algorithm library

Command:
```
.venv/bin/python -m pytest tests/test_backtest.py -q -p no:warnings
```
Result: **all passed**, exit 0. This includes the parameterised
`test_every_workshop_strategy_runs_leak_free`, which now compiles and runs all
**58** strategies on synthetic bars and asserts positions only contain 0/1 and
never reference future bars (the registry test was updated from `== 20` to
`>= 20` because the library grew).

## 4. Full suite (regression)

Command:
```
MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python -m pytest -q -p no:warnings
```
Result: **exit 0**; progress-dot count = **2,791**; collected = **2,799**
(independent `--collect-only` sum); therefore **2,791 passed / 0 failed /
8 skipped**.

Baseline this session was 2,709 collected (2,701 passed + 8 skipped). The delta
of +90 is the new coverage: +52 in `tests/test_catalog.py` (catalogue, engines,
search and the API endpoints) and +38 from the parameterised strategy test
expanding 20 → 58.

Logs: `$TMPDIR/full_s35c.log` (run), `$TMPDIR/full_s35c.exit` (`EXIT=0`). Earlier
intermediate run: `$TMPDIR/full_s35b.log`.

## 5. Browser (Playwright, dev :10000)

Session `kimi35`. Steps and observed results:

| Step | Observed |
|---|---|
| `open http://127.0.0.1:10000/` | page loaded |
| `console error` | `Total messages: 0 (Errors: 0, Warnings: 0)` |
| KIMI tab list | 13 tabs including `catalogues` |
| click Catalogues → scanners | "124 of 124 scanners match." · 124 rows |
| ⓘ Info on first scanner | panel shows "Stable id scan.oversold_rsi · Rule …" |
| search "volume breakout" | "4 of 124 scanners match" · 4 rows |
| Run `scan.breakout_with_volume` | "Channel breakout with volume — 4 of 350 eligible matched"; reasons e.g. `donchian_breakout > 0 -> actual 1 · relative_volume >= 1.5 -> actual 2.742` |
| switch family → algorithms | "73 of 73 algorithms match" (after the 6 Part-C engines were added and the server restarted) |
| Run `algo.sma_cross` | backtest on ACLBSL: `sharpe -0.14 · trades 14 · final_equity 67,852.56` |
| switch family → fundamentals | "32 of 32 fundamentals match" |
| Run `fund.pe_ratio` on ACLBSL | `{"pe_ratio": 33.34, available: true}` |
| `console error` (final) | `Errors: 0, Warnings: 0` |

No console errors at any point. Screenshots/snapshot refs are in the Playwright
session artefacts.

## 6. Endpoint spot checks (curl, dev :10000)

| Request | Result |
|---|---|
| `GET /api/catalog/summary` | scanner 124 · algorithm 73 · fundamental 32 · health.ok true |
| `GET /api/catalog/scanner?q=cheap` | matched 2 of 124 |
| `POST /api/analysis/run {fn:monte_carlo,paths:300,seed:7}` | method gbm, median 104.82, prob_gain 0.553 |
| `POST /api/fundamental/run {fn:pe_ratio,symbol:NABIL}` | value 18.86, available true |

## 7. What is NOT tested

- The full 229-tool catalogue was not clicked end-to-end in the browser; the
  walk was sampled per family (scanner/algorithm/fundamental info + run). Marked
  PARTIAL, not PASS.
- Browser tests for other views run only under `MEGATOOL_BROWSER_TESTS=1` and
  were not needed for this change.
- No live/network provider was exercised (none is configured).
