# PRAVAHA — Final Audit Evidence Review (Read-Only)

**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** PID 26596 (unchanged)
**Mode:** Read-only. No code modified.

---

## 1. Calculation verification (independently checked)

| # | Calculation | File:Line | Formula (implemented) | Independent reference | Test input | Expected | Actual | Tolerance | Result |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Market barometer | `app.js:12006` | `0.5×(adv/(adv+dec)×100) + 0.5×pctAbove50` | Reproduced from `/api/market/dashboard` breadth data | adv=199, dec=106, pctAbove50=36.8 | 51.0 | 51.0 | exact | TESTED-PASS |
| 2 | TTM EPS (old) | `fundamentals.py:1014` (pre-fix) | `sum(4 most recent EPS rows)` | Compared sum vs annual EPS across 324 symbol-FY pairs | NABIL FY2024-25: Qs 24.05+25.05+26.34+26.09 | Should ≈ annual (21.89) | 101.53 (4.65×) | 5% | TESTED-FAIL |
| 3 | TTM EPS (new) | `fundamentals.py:1014` | Returns `None` + reason | N/A (honest unavailable) | Any symbol with EPS records | `None` | `None` | N/A | IMPLEMENTED, TESTED-PASS |
| 4 | EPS growth | `fundamentals.py:1051` | Annual periods only; names failed condition | Verified against NABIL/ACLBSL data | ACLBSL: earliest annual EPS -7.08 | `None` + reason | `None` + reason | N/A | TESTED-PASS |
| 5 | P/E series | `sastoshare.py` | Daily re-rating; gaps capped points (never clamps) | ACLBSL: 159 points above cap, largest 6673× | ACLBSL close 2025-02-20, EPS 0.19 | Flagged suspect | Flagged (2 periods) | N/A | TESTED-PASS |
| 6 | Swing detection | `swings.py:96` | Fractal pivot (left/right window) | 32 hand-built zigzag tests | Zigzag with peaks/troughs 5 bars apart | 6 swings | 6 swings | exact | TESTED-PASS |
| 7 | FVG detection | `swings.py` (new) | `low[t] > high[t-2]` (bullish) | 8 hand-built tests | 5-bar series with known gap | 1 FVG | 1 FVG | exact | TESTED-PASS |
| 8 | Equal H/L | `swings.py` (new) | Consecutive same-kind swings within tolerance | 3 hand-built tests | Two highs at 100.0 and 100.05, tol 0.001 | 1 pair | 1 pair | exact | TESTED-PASS |
| 9 | Regime classification | `app.js` (classifyTrendRegime) | ADX ≥25 trending, <20 ranging, else transition; direction from +DI/-DI | 4 browser eval tests | ADX=30,+DI=25,-DI=15 | trending/bullish | trending/bullish | exact | TESTED-PASS |
| 10 | Divergence detection | `app.js` (detectDivergence) | Price LL + RSI HL = bullish; price HH + RSI LH = bearish | 3 browser tests | NABIL 120 bars | 2 divergences | 2 divergences | exact | TESTED-PASS |
| 11 | Backtest costs | `backtest.py` | Tiered commission + SEBON + DP + CGT | Official SEBON PDF (published 2025-07-20) | NPR 100k buy | NPR 360 commission + NPR 15 SEBON | As computed | N/A | UNVERIFIED (rates not reconciled against contract notes) |

**Note:** Tests #6-#10 use hand-built fixtures with known expected values, not just comparing implementation to itself. Test #11's rates are from an official PDF but not reconciled against actual contract notes.

---

## 2. Unverified calculations

| Calculation | File | Why unverified | Status |
|---|---|---|---|
| TTM EPS | `fundamentals.py:1014` | Source basis undocumented; summing gives 4.65× annual | BLOCKED (returns None) |
| Technical indicators (RSI, MACD, Bollinger, ATR, ADX, etc.) | `megatool/ta/*.py` | No independent cross-check against reference library; covered by structural invariants only | NOT-TESTED (numerically) |
| Transaction costs (broker commission, SEBON, DP, CGT) | `backtest.py` | Rates from SEBON PDF but not reconciled against actual contract notes | UNVERIFIED |
| Backtesting (win rate, drawdown, Sharpe) | `backtest.py` | No independent reference implementation to compare against | NOT-TESTED (independently) |
| Position sizing | `planning.py` | No independent reference | NOT-TESTED |
| Fibonacci retracements/extensions | `fibonacci.py` | No independent reference; 38 tests pass (structural) | NOT-TESTED (numerically) |
| Harmonic patterns | `harmonic.py` | No independent reference; candidate detection only | NOT-TESTED |
| Elliott Wave | `elliott.py` | No independent reference; candidate detection only | NOT-TESTED |
| Quantitative scoring (ranking) | `ranking.py` | No independent reference | NOT-TESTED |
| Portfolio valuation | `portfolio.py` | No independent reference | NOT-TESTED |
| Market breadth | `breadth.py` | No independent reference | NOT-TESTED |
| Seasonality | `seasonality.py` | No independent reference | NOT-TESTED |
| Volume profile | `profile.py` | No independent reference | NOT-TESTED |
| SMC/liquidity | `levels.py`, `gaps.py` | No independent reference | NOT-TESTED |
| Confluence scoring | `confluence.py` | No independent reference | NOT-TESTED |

---

## 3. Data freshness

### Sources and status

| Source | Method | Last successful | Latest market date | Status |
|---|---|---|---|---|
| YONEPSE (OHLCV) | HTTP GET (public mirror) | Unknown (not tracked in UI) | 2026-10-15 | Operational, delayed |
| NEPSE official API | HTTP GET (requires Salter token) | Never (401) | N/A | Blocked |
| ShareHub | HTTP GET (needs Bearer token + IP allow-list) | Never (unconfigured) | N/A | Unconfigured |
| Fundamentals (yonepse/financials.json) | Local file import | 2026-08-06 (latest filing) | N/A | Operational |
| Sector CSVs | Manual import | N/A | N/A | Manual only |
| Corporate events | None | N/A | N/A | Empty (0 rows) |
| Trading calendar | None | N/A | N/A | Holidays empty |

### Scheduled jobs
- **No in-app scheduler.** Refresh is via external schedulers (cron/launchd) running `megatool fetch`, `megatool collector-loop`, or `megatool ingest`.
- The app runs no background thread (`_cmd_collector_loop` is invoked externally).
- `live.py` measures freshness honestly: a 90ms request returning a 4-day-old snapshot is reported as 4-day-old, never as "live".

### HTTP 401 handling
- NEPSE official API returns 401 without Salter token. Project will not defeat anti-bot obfuscation. Documented in `live.py` and `BLOCKED_FEATURES_AUDIT.md`.
- All surfaces label data as DELAYED/historical, never LIVE.
- `live_feed_connected: false` in `/api/status`.

---

## 4. Frontend and aesthetics

### Pages rendered and visually inspected in browser
Screenshots captured for: overview, charts (with NABIL loaded), screener, backtest, kimi, sastoshare, fundamentals, portfolio, data, marketintel, breadth, forecaster, narrow-overview (760px), legacy-redirect-stub, charts-loaded.

### Confirmed layout/interaction/accessibility defects
| Defect | Status | Evidence |
|---|---|---|
| Indicator names clipped (ellipsis) | FIXED | `styles.css:.ii-name` now wraps |
| Responsive nav wrapped into rows (brand in middle) | FIXED | Media query reverted to horizontal strip |
| `#tool-info` modal hidden inside view-charts | FIXED | Moved to shell level; verified visible (760×900) on backtest |
| Scanner auto-execution on selection | FIXED | Verified: selecting doesn't run; Run Screen does |
| Vertical line slanted rendering | FIXED | Custom primitive; 1,263 red pixels, vertical=true |
| Chart panning during drawing | FIXED | `pressedMouseMove` toggle verified |
| Viewport jump on result selection | FIXED | Range unchanged (0→119) |

### Not tested
- Screen reader / OS-level reduced motion (CSS present but not exercised).
- `LIVE` status chip (no live feed in environment).
- Login/auth/About/loading screens (do not exist in this app).

---

## 5. Drawing system

### Tested via real browser mouse interactions
**NONE.** Playwright's synthetic mouse events do not trigger Lightweight Charts' `subscribeClick` handler. This is a test-harness limitation, not an application defect.

### Tested synthetically (via `onChartClick` calls + canvas pixel analysis)
| Tool | Creation | Placement | Persistence | Viewport stability | Result |
|---|---|---|---|---|---|
| Vertical line | ✅ (synthetic) | ✅ (last bar clamp) | ✅ (coords match) | ✅ (range unchanged) | TESTED-PASS (synthetic) |
| Horizontal line | ✅ (synthetic) | ✅ | ✅ | ✅ | TESTED-PASS (synthetic) |
| Trendline | ✅ (synthetic) | ✅ | ✅ | ✅ | TESTED-PASS (synthetic) |
| All 40+ tools | ❌ | ❌ | ❌ | ❌ | NOT-TESTED (no real click) |

### Real-browser interaction: BLOCKED
- `subscribeClick` does not fire from Playwright's synthetic events.
- LWC uses an internal pointer state machine that Playwright's CDP-dispatched events don't satisfy.
- Recommended: Selenium with native events, or a test-only click hook (requires approval).

### Canvas pixel verification
- Vline primitive: 1,263 red pixels, minX=285, maxX=287 → vertical=true. ✅
- This proves rendering, not interaction.

---

## 6. Final test state

### Full non-browser suite
- **2,971 passed, 33 skipped, exit 0** (118.90s).
- Skipped: 33 (opt-in browser tests + environment-dependent).

### Browser tests
- **47 passed** (19 new + 28 pre-existing).
- 0 failures.

### JS syntax
- `node --check`: OK on app.js, viz.js, kronos_ui.js, indicator_info.js.

### Ruff
- Clean on touched files. 18 pre-existing findings in api.py (market-intelligence routes).

### Active test processes
- None at time of this report (last run completed).

---

## 7. Safety

- **Port 8710:** PID 26596 (unchanged from session start). Not modified, restarted, or contacted.
- **No commits, push, or deploy.**
- **No destructive Git operations.**
- **All work on dev port 10000.**
- **No secrets introduced** in logs or reports.

---

## 8. Evidence labels summary

| Feature | Status |
|---|---|
| PRAVAHA rebrand | IMPLEMENTED, TESTED-PASS |
| TTM EPS safety | IMPLEMENTED, TESTED-PASS |
| Indicator readability | IMPLEMENTED, TESTED-PASS |
| Chart drawing (timestamp, panning, viewport, hit-test) | IMPLEMENTED, TESTED-PASS |
| Vertical-line primitive | IMPLEMENTED, TESTED-PASS (canvas pixel) |
| 5 analysis categories | IMPLEMENTED, TESTED-PASS |
| More Scanners selection/execution | IMPLEMENTED, TESTED-PASS |
| Contextual Info modal | IMPLEMENTED, TESTED-PASS |
| Real-browser click testing | BLOCKED (Playwright/LWC limitation) |
| TTM EPS computation | BLOCKED (source basis undocumented) |
| Sector auto-classification | NOT-IMPLEMENTED (manual CSV only) |
| Dividend analysis | BLOCKED (no DPS data) |
| Live NEPSE feed | BLOCKED (401, no credentials) |
| Technical indicators (numerical) | NOT-TESTED (structural invariants only) |
| Transaction costs (rates) | UNVERIFIED (not reconciled against contract notes) |
| Backtesting (win rate, drawdown, Sharpe) | NOT-TESTED (independently) |
| Fibonacci (numerical) | NOT-TESTED (structural invariants only) |
| Real-browser interaction | BLOCKED (Playwright limitation) |

---

## 9. Recommended next steps (highest priority)

1. **Obtain real-browser testing capability** (Selenium/Puppeteer with native input, or a test-only click hook with approval).
2. **Fix crossline vertical component** (same primitive approach as vline).
3. **Auto-import sector CSVs** (649 + 274 rows available on disk).
4. **Investigate `priceToCoordinate` fix** (LWC v4.2.3 bug; may need LWC upgrade).
5. **Add TTM EPS tests** for the new "unavailable" contract.
6. **Reconcile broker commission rates** against actual contract notes.

**Audit complete.** No code modified during this audit. Awaiting your next instruction.
MD
echo "written"