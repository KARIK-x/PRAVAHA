# PRAVAHA — Phase 1 Report (TTM EPS + Inspection)

**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** untouched

---

## Part A — TTM EPS safety fix: IMPLEMENTED & TESTED

### Files changed
- `megatool/fundamentals.py` — `compute_ttm_eps()` rewritten (no summing).
- `web/static/app.js` — `loadNewTtmEps()` hint text (removed misleading "requires 4 consecutive quarters" claim).
- `tests/test_ttm_eps.py` — new (8 focused tests).

### Behavior before
Returned `ttm_eps = round(sum of 4 most recent EPS rows, 4)` with a gap-day check but **no period-type, fiscal-year, or basis verification**. Verified to overstate: NABIL FY2024-2025 summed 101.53 vs annual 21.89 (4.6×).

### Behavior after
- `ttm_eps` is **always `None`** (never a misleading number).
- `reason` explains the undocumented basis.
- All available EPS records (with period labels) are returned in `quarters` for transparency.
- `quarters_used` = count of distinct records.
- Response shape preserved (`symbol`, `ttm_eps`, `reason`, `quarters_used`, `quarters`).

### Why no threshold / reconciliation guard
The proposed 15% threshold was not used because **no case reconciles** (0.9% within 5%). A threshold would be an arbitrary cutoff on data that doesn't support any computation. The defensible approach: don't compute at all; return None with reason. This matches the mission's instruction: "If the data is insufficient to calculate true TTM EPS, clearly indicate that status."

### Tests
- `tests/test_ttm_eps.py` — **8 passed** (no records, any records → None, transparency, zero/negative, null-skip, shape, uppercase, dedup).
- `node --check web/static/app.js` — OK.
- Full suite — **2,956 passed, 17 skipped, exit 0**.
- Live endpoint verified: `/api/fundamentals/NABIL/ttm-eps` → `ttm_eps: null`, reason explains basis issue.

### Status: IMPLEMENTED, TESTED-PASS

---

## Part C — Indicator name readability: IMPLEMENTED

### Change
`.ind-inst .ii-name` in `web/static/styles.css`: changed `white-space: nowrap; overflow: hidden; text-overflow: ellipsis;` to `white-space: normal; overflow-wrap: anywhere; word-break: break-word;` with `line-height: 1.35`. Long indicator names now wrap instead of being clipped. The `.ii-head` flex layout (gap 6px, actions `margin-left: auto`) accommodates the taller row.

### Files changed
- `web/static/styles.css` (1 rule)
- `web/static/index.html` (cache buster `wb11`)

### Status: IMPLEMENTED, TESTED-PASS (visual verification via browser; no console errors)

---

## Part D — Contextual Info panels: NOT REPRODUCED

### Investigation
- `#tool-info` modal is a global overlay (`position: fixed; inset: 0`) mounted inside `<main id="views">` but outside any view section. It overlays whatever view is active.
- `openToolInfo()` and `bindToolInfoModal()` do not call `showView`. Verified by browser test: Info in backtest shows the selected strategy's title and the active view stays `view-backtest`. Same for screener.
- Cache keys are namespaced by kind (`algorithm:`, `scanner:`), so no cross-context collision.
- Could not reproduce "Info displays in Charting instead of Algorithms" with the available interactions (backtest Info, screener Info, indicator catalog Info, KIMI catalogue Info all tested).

### Status: NOT-VERIFIED (bug not reproducible; may be intermittent or require a specific interaction sequence not yet identified)

### Recommendation
If the issue persists, please provide the exact steps (which view, which Info button, what appears). The smallest reliable fix, if confirmed, would be to ensure `openToolInfo` never triggers a view change and to scope the modal's content to the calling context — but no change was made because the defect could not be reproduced and the instruction is to not change working features.

---

## Part B — Five additional analysis categories: INSPECTION COMPLETE, IMPLEMENTATION NOT STARTED

### What already exists (do not duplicate)
The indicator registry already has 92 indicators, many of which cover the proposed categories:

| Proposed category | Existing indicators | Existing analysis modules |
|---|---|---|
| Market Structure & Liquidity | swings (via `swings.py`), levels (`levels.py`), gaps (`gaps.py`), confluence (`confluence.py`) | LAYER_DEFS: `sr`, `patterns` |
| Trend Strength & Regime | `adx`, `supertrend`, `ichimoku`, `parabolic_sar`, `aroon`, `vortex` | `trend.py`, `trend2.py` |
| Momentum, Divergence & Relative Strength | `rsi`, `macd`, `roc`, `cci`, `stochastic`, `williams_r`, `momentum` | `momentum.py`, `momentum2.py` |
| Volatility & Breakout | `bollinger`, `keltner`, `atr`, `historical_volatility`, `choppiness`, `donchian` | `volatility.py`, `volatility2.py` |
| Volume & Accumulation | `obv`, `cmf`, `ad_line`, `volume_oscillator`, `relative_volume`, `mfi`, `vwap_bands` | `volume.py`, `volume2.py`, `profile.py` |

### Assessment
The 5 new analysis categories would be **curated overlays/panes** that organize existing indicators into the Analysis drawer, NOT new calculations. Each would:
- Add a `LAYER_DEFS` entry
- Add a render function plotting the relevant indicators
- Support toggle, timeframe, and missing-data handling
- Reuse existing `ta.*` calculations (no new math)

This is substantial but feasible. It does not duplicate — it curates.

### Status: NOT-IMPLEMENTED (awaiting approval to begin; estimated 5 increments, one per category, each with tests)

---

## Summary of this session

| Part | Status |
|---|---|
| A — TTM EPS safety fix | IMPLEMENTED, TESTED-PASS |
| C — Indicator name readability | IMPLEMENTED, TESTED-PASS |
| D — Info panels | NOT-REPRODUCED (no change made) |
| B — 5 new analysis categories | INSPECTION COMPLETE, NOT-IMPLEMENTED |

### Tests
- `tests/test_ttm_eps.py` — 8 passed
- Full suite — 2,956 passed, 17 skipped, exit 0
- Browser tests (chart drawing) — 17 passed
- ruff clean on touched files

### Files changed this session
- `megatool/fundamentals.py` (TTM EPS safety fix)
- `web/static/app.js` (TTM EPS hint text)
- `web/static/styles.css` (indicator name wrapping)
- `web/static/index.html` (cache busters)
- `tests/test_ttm_eps.py` (new, 8 tests)

### Safety
- Production `:8710` untouched (PID 26596).
- No commit, push, or deploy.
- No destructive Git operations.

**STOP.** Awaiting your approval for Part B (5 analysis categories) and any additional specifics for Part D.
MD
echo "written"