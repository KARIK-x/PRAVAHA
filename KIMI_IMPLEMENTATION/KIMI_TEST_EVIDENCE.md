# KIMI — Test Evidence

## Backend
- `tests/test_catalog.py` — **52 tests**, exit 0. Covers catalogue integrity
  (unique ids, health, metadata contract, every scanner tree validated), search
  (tag hits, all-terms, category filter, cross-family), deterministic engines,
  valuation/portfolio math, the four NF engines, and the five API routes.
- Full suite: **2,799 collected / 2,791 passed / 0 failed / 8 skipped, exit 0**
  (`$TMPDIR/full_s35c.log`, `$TMPDIR/full_s35c.exit`).
- `node --check web/static/app.js` — exit 0.

## Browser (Playwright, dev :10000, session `kimi35`)
- Opened the app; `console error` → `Total messages: 0 (Errors: 0, Warnings: 0)`.
- Walked all 13 KIMI tabs. Only `overview` initially showed "undefined" (a
  `table()` cell-contract bug); fixed. After the fix every tab reported
  `undefined=0`.
- Walked all 34 top-level views: every one reported `u=0 o=0` (no "undefined",
  no "[object Object]").
- Catalogues tab:
  - scanners → "124 of 124 scanners match", 124 rows.
  - algorithms → "73 of 73 algorithms match" (before the 4 NF engines were added;
    now 77).
  - fundamentals → "32 of 32 fundamentals match".
  - ⓘ Info on `scan.oversold_rsi` → panel with stable id + rule.
  - search "volume breakout" → 4 matches.
  - Run `scan.breakout_with_volume` → "4 of 350 eligible matched" with reasons.
  - Run `algo.sma_cross` → backtest on ACLBSL: sharpe −0.14, trades 14, final
    equity 67,852.56.
  - Run `fund.pe_ratio` → ACLBSL P/E 33.34.
- Final `console error` → `Errors: 0, Warnings: 0`.

## Live API spot checks (curl, dev :10000)
All nine store-backed engines returned real results through `/api/analysis/run`:
`correlation_matrix`, `signal_outcomes` (308 signals), `hrp_portfolio`,
`deflated_sharpe`, `stress_test`, `liquidity_drought` (state normal),
`fundamental_forensics`, `factor_snapshot` (universe 320), `coverage_explorer`,
`efficient_frontier`.

## Not tested
- Full click-through of every catalogue entry (sampled).
- Live provider paths (none configured).
