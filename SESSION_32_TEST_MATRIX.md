# SESSION 32 — TEST MATRIX

Layered protocol. A layer is only marked covered when the named command ran.

| Layer | Scope | Command | Result |
|---|---|---|---|
| Static | JS syntax | `node --check web/static/app.js` | exit 0 |
| Static | Python syntax | `python -c "ast.parse(...)"` on edited modules | exit 0 |
| Unit | Catalogue integrity/search | `pytest tests/test_catalog.py` | 52 passed |
| Unit | Indicators | `pytest tests/test_indicators*.py` | passed |
| Unit | Backtest strategies | `pytest tests/test_backtest.py` | passed (58 leak-free) |
| Independent numeric | Indicators vs oracles | `tests/_naive_helpers.py` + indicator tests | passed |
| Independent numeric | DCF hand-computed | `tests/test_catalog.py::test_dcf_matches_a_hand_computed_value` | passed |
| Property / metamorphic | percentile ordering, risk monotonicity, trials monotonicity, simplex validity, benchmark-required refusal, next-bar entry | `tests/test_catalog.py` | passed |
| API | catalogue + analysis + fundamental routes | `tests/test_catalog.py` (TestClient) + live curl | passed |
| Browser | KIMI tabs (all 13) + all 34 views | Playwright session `kimi35` | 0 undefined, 0 console errors |
| Regression | Full suite | `pytest -q` | see SESSION_34_TEST_EVIDENCE.md |
| End-to-end | screen → catalogue Run, backtest Run, fundamental Run, analysis Run | browser + API | passed |

## Not covered (stated, not hidden)
- Full click-through of all 229 catalogue entries (sampled per family).
- Multi-symbol comparison under every timeframe in the browser (logic tested in
  unit tests, not exhaustively in the browser).
- Live provider paths (none configured; network-free by design).
