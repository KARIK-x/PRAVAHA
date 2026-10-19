# End-to-End Chart Drawing Workflow Audit (Read-Only)

**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** untouched (PID 26596)
**Mode:** Read-only inspection and testing. No application code modified.

---

## 1. Executive summary

**Overall status: PARTIAL**

The drawing system has been substantially repaired (vertical-line primitive,
panning toggle, viewport stability, hit-test tolerance). Synthetic tests and
canvas-pixel analysis confirm the vline primitive renders a true vertical line.
However, **real-browser click interactions could not be exercised** because
Playwright's synthetic mouse events do not trigger Lightweight Charts'
`subscribeClick` handler. The audit therefore relies on synthetic `onChartClick`
calls and canvas-pixel verification, not real pointer interaction.

**Real-browser workflows tested: NO** (Playwright limitation — `subscribeClick`
does not fire from synthetic events).

---

## 2. Verified bugs (from prior sessions, all fixed)

| ID | Bug | Fix | Evidence |
|---|---|---|---|
| V1 | Vertical lines slanted (LWC limitation) | Custom primitive with `fillRect` | 1,263 red pixels, minX=285, maxX=287 → vertical=true |
| V2 | Chart panning during drawing | `pressedMouseMove` toggle | Browser eval: false (tool active), true (cursor) |
| V3 | Viewport jump on result selection | Removed `scrollToRealTime()` | Before/after range unchanged (0→119) |
| V4 | Price reading garbage for out-of-range y | Fallback to bar OHLC | Synthetic test: price read correctly |

## 3. Potential bugs (not reproduced, needs further verification)

| ID | Issue | Status |
|---|---|---|
| P1 | Crossline vertical component still slanted (same LWC limitation as vline was) | NOT-FIXED (deferred) |
| P2 | Vline primitive color/width not editable after creation | NOT-TESTED |
| P3 | `priceToCoordinate`/`coordinateToPrice` broken in LWC v4.2.3 (affects snapping, price reading) | WORKAROUND (bar OHLC fallback) |
| P4 | Playwright cannot test real canvas clicks (`subscribeClick` doesn't fire from synthetic events) | BLOCKED (infrastructure limitation) |
| P5 | Multi-touch/trackpad interactions not tested | NOT-TESTED (no touch device) |

## 4. Capability gaps (missing features, not bugs)

- Snapping toggle not uniformly exposed per tool.
- No multi-select or bulk delete for drawings.
- Per-tool styling controls not audited (some may silently do nothing).
- No drawing groups/layers beyond the existing analysis layers.
- Undo/redo is stack-based (no granular per-tool undo).

## 5. Test results

### Exact commands executed
1. `MEGATOOL_DATA_DIR=… .venv/bin/python -m pytest -q -p no:warnings` → **2,971 passed, 33 skipped, exit 0**
2. `MEGATOOL_BROWSER_TESTS=1 … pytest tests/test_browser_chart_drawing.py tests/test_browser_chart_structure.py tests/test_browser_chart_trend.py tests/test_browser_chart_momentum.py tests/test_browser_chart_volatility.py tests/test_browser_chart_volume.py tests/test_browser_objects_manager.py tests/test_browser_viz_toolinfo.py` → **47 passed** (19 new + 28 pre-existing)
3. `node --check web/static/app.js` → OK
4. Canvas pixel analysis (browser eval) → vertical=true, 0 errors
5. Panning toggle verification (browser eval) → pressedMouseMove=false (tool), true (cursor)
6. Viewport stability (browser eval) → range unchanged
7. Save/restore (browser eval) → coords match

### Browser test counts by file
| File | Tests | Category |
|---|---|---|
| `test_browser_chart_structure.py` | 3 | Market Structure & Liquidity |
| `test_browser_chart_trend.py` | 4 | Trend Strength & Regime |
| `test_browser_chart_momentum.py` | 3 | Momentum, Divergence & RS |
| `test_browser_chart_volatility.py` | 3 | Volatility & Breakout |
| `test_browser_chart_volume.py` | 3 | Volume & Accumulation |
| `test_browser_chart_drawing.py` | 3 | Chart Drawing fix |
| `test_browser_objects_manager.py` | 14 | Pre-existing |
| `test_browser_viz_toolinfo.py` | 14 | Pre-existing |
| **Total** | **47** | |

### Scenarios that remain NOT-TESTED
- Real mouse clicks on the canvas (Playwright limitation — `subscribeClick` doesn't fire from synthetic events).
- Multi-touch/trackpad interactions.
- Snapping on/off toggle (not exposed in UI for all tools).
- Per-tool styling controls (not audited).
- Crossline vertical component rendering (deferred).

## 6. Regression assessment

- All 12 analysis layers (7 original + 5 new) load simultaneously with 0 console errors. ✅
- Symbol switch (NABIL → NICA) works with all layers active. ✅
- Timeframe switch (120 → 250 bars) works. ✅
- Toggle on/off works for all 5 new layers (markers cleared on off). ✅
- `alignIndicatorToBars()` helper aligns by trading date (verified: BB raw 3517 bars → aligned 120). ✅
- TTM EPS, indicator names, scanner selection, Info modal, chart drawings all verified. ✅
- No regressions detected in existing drawing tools. ✅

## 7. Persistence assessment

- Drawing created near last bar + middle bar → saved to `localStorage` → reloaded → coordinates identical. ✅
- Symbol switch: drawings are per-symbol (`mt-drawings-{symbol}`); no cross-symbol leakage. ✅
- Timeframe switch: drawings persist (stored by symbol, not timeframe). ✅
- Deleted drawings do not reappear (verified via synthetic test). ✅

## 8. Production safety

- Production port 8710: PID 26596 (unchanged from session start). **Not modified.**
- No commits, push, or deploy performed.
- No destructive Git operations.
- All work on dev port 10000.

## 9. Prioritized next steps

1. **High:** Fix crossline vertical component (same primitive approach as vline).
2. **Medium:** Add styling controls for vline primitive (color, width).
3. **Medium:** Per-tool hit-test tolerances.
4. **Medium:** Investigate real-browser click testing (Playwright limitation).
5. **Low:** Primitive cleanup on chart destroy.
6. **Low:** Multi-select / bulk delete for drawings.

### Status labels
- Vertical-line primitive: **IMPLEMENTED, TESTED-PASS** (canvas pixel analysis)
- Panning toggle: **IMPLEMENTED, TESTED-PASS**
- Viewport stability: **IMPLEMENTED, TESTED-PASS**
- Price-reading fallback: **IMPLEMENTED, TESTED-PASS**
- Crossline vertical: **NOT-FIXED** (deferred)
- Real-browser click testing: **BLOCKED** (Playwright limitation)
- Multi-touch/trackpad: **NOT-TESTED**

**STOP.** No code modified during this audit. Awaiting your next instruction.
MD
echo "written"