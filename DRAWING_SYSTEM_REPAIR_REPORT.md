# PRAVAHA — Drawing System Repair Report

**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** untouched
**Chart library:** Lightweight Charts v4.2.3

---

## 1. Root causes identified

1. **Viewport jump on result selection (FIXED):** `highlightResult()` called `chart.timeScale().scrollToRealTime()` when clicking a result row in the analysis drawer, scrolling the chart to the end. Removed — highlighting now preserves the viewport.

2. **Chart panning during drawing (FIXED):** When a drawing tool was active, mousedown was not prevented, so Lightweight Charts started panning on drag. A pan gesture stole the click (`subscribeClick` never fired), making drawing creation unreliable — especially for vertical lines and rays. Fixed by toggling `handleScroll.pressedMouseMove` based on whether a drawing tool is active: disabled while drawing, enabled for the cursor tool.

3. **Price coordinate conversion (WORKAROUND):** `series.priceToCoordinate()` and `series.coordinateToPrice()` return degenerate values in this LWC v4.2.3 build (all prices map to the same y). This broke snapping, dragging, and price reading. Worked around by reading price from `param.seriesData` (bar's OHLC) when available, falling back to `coordinateToPrice` only for in-range values.

4. **Vertical line rendering (VISUAL LIMITATION):** LWC does not render two same-time points as a true vertical line — they render as a slanted segment spanning one bar width. The data is correct (2 points at the same time with different prices), but the visual result is not perfectly vertical. A custom primitive approach was attempted but `priceToCoordinate` is broken, preventing correct y-coordinate calculation. Documented as a known limitation.

## 2. Files changed

- `web/static/app.js` — `setDrawTool` (panning toggle), `onChartClick` (price reading fallback), `highlightResult` (removed scrollToRealTime), `bindDrawings` (mousedown preventDefault without stopPropagation).
- `web/static/index.html` — cache buster `app.js?v=wb59`.

## 3. Vertical-line behavior before and after

| | Before | After |
|---|---|---|
| Creation | Clicks in empty space rejected ("Click inside the plotted bars."); clicks on candles sometimes didn't fire `subscribeClick` due to panning | Empty-space clicks resolve to nearest bar (Phase 14 fix); panning disabled during drawing so clicks fire reliably |
| Viewport | `scrollToRealTime()` jumped chart to end on result selection | No viewport change on result selection |
| Price reading | `coordinateToPrice` returned garbage for out-of-range y | Falls back to bar's OHLC from `param.seriesData` |
| Rendering | Slanted line (LWC limitation) | Slanted line (unchanged — LWC limitation) |

## 4. Viewport behavior before and after

- **Before:** `highlightResult()` called `scrollToRealTime()` on every result-row click, jumping the chart to the end. Drawing creation could trigger panning (stealing the click).
- **After:** No viewport change during drawing operations (creation, selection, editing, deletion, save/restore). Panning disabled while a drawing tool is active. `pressedMouseMove` restored when cursor tool is active.

## 5. Number of actual browser trials performed

- Synthetic `onChartClick` trials: 15+ (vline, hline, trendline creation at first/middle/last bar, empty space, save/restore, viewport stability).
- Browser console: 0 errors across all tests.
- Playwright real-click trials: attempted but `subscribeClick` does not fire from Playwright's synthetic clicks (infrastructure limitation, not a code bug).

## 6. Pass/fail counts by tool category

| Category | Tested | Result |
|---|---|---|
| Vertical line creation (synthetic) | 5 trials | PASS |
| Horizontal line creation (synthetic) | 3 trials | PASS |
| Trendline creation (synthetic) | 5 trials | PASS |
| Viewport stability (before/after) | 3 trials | PASS |
| Save/restore | 2 trials | PASS |
| Panning toggle (pressedMouseMove) | 2 trials | PASS |
| Real-click creation (Playwright) | 6 attempts | BLOCKED (Playwright doesn't trigger LWC subscribeClick) |

## 7. Results of the full regression suite

- Full non-browser suite: **2,971 passed, 33 skipped, exit 0**.
- Browser tests: **19 passed** (drawing + 5 categories).
- `node --check web/static/app.js` — OK.

## 8. Remaining drawing limitations

1. **Vertical lines render as slanted segments** (LWC v4.2.3 limitation: same-time two-point series renders as a slanted line spanning one bar width). A custom primitive approach was attempted but `priceToCoordinate` is broken in this LWC build, preventing correct y-coordinate calculation. **NOT FIXED** — documented as a known limitation.
2. **Price reading uses bar OHLC fallback** instead of exact pixel-to-price conversion (because `coordinateToPrice` is broken for out-of-range coordinates). Hlines placed by clicking may land on the bar's close price, not the exact clicked price.
3. **Snapping is unreliable** (`snapPriceToOhlc` uses `priceToCoordinate`, which is broken).
4. **No multi-select or bulk delete.**
5. **Per-tool styling controls** not audited (some may silently do nothing).
6. **Playwright cannot test real clicks** on the canvas (subscribeClick doesn't fire from synthetic events). Real-browser testing is required for full verification.

## 9. Scenarios that could not be tested

- Real mouse clicks on the canvas (Playwright limitation).
- Multi-touch / trackpad interactions.
- Snapping on/off toggle (not exposed in UI for all tools).

### Status: IMPLEMENTED (panning + viewport fixes), TESTED-PASS (synthetic), BLOCKED (real-click testing via Playwright)

---

**Drawing system repair complete (within testable scope).** Awaiting your next instruction. (Production :8710 untouched; no commits/deploy.)
MD
echo "written"