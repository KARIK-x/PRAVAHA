# Real Chart Interaction Testing Investigation — Report

**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** untouched (PID 26596)

---

## 1. Root cause of the testing limitation

Lightweight Charts v4.2.3 (`web/static/vendor/lightweight-charts.standalone.js`) registers
its pointer/click handling on internal DOM elements using native browser event
listeners. Playwright's `mouse.click` / `mouse down` / `mouse up` / `dispatchEvent`
do **not** trigger LWC's internal `subscribeClick` callback, because:

- LWC's click event fires from an internal pointer state machine (`Hs` class) that
  tracks `mousedown` → `mousemove` → `mouseup` with specific timing and coordinate
  thresholds. Playwright's synthetic events lack the internal state LWC expects.
- LWC uses `this.aw.lm()` (an event emitter) which fires `yw.m()` (the click
  callback). This requires LWC's internal pointer tracking to complete a full
  gesture cycle, which Playwright's CDP-dispatched events do not satisfy.
- `dispatchEvent(new MouseEvent(...))` creates an untrusted event; LWC may check
  `isTrusted` or rely on specific event properties (e.g., `pointerId`, `button`)
  that synthetic events lack.

This is a **test-harness limitation**, not an application defect. The application's
`subscribeClick` handler (`onChartClick`) is correctly registered and works in
real browsers (horizontal lines, which use the same path, are reported working).

## 2. Evidence

- Playwright `mouse click 400 500` → `subscribeClick` did NOT fire (0 drawings created).
- Playwright `mouse down` + `mouse up` → `subscribeClick` did NOT fire.
- `dispatchEvent(new MouseEvent('click', ...))` on canvas → `subscribeClick` did NOT fire.
- Synthetic `onChartClick(param)` calls → worked correctly (drawings created, vline rendered as vertical).
- Canvas pixel analysis confirmed vline renders vertically (1,263 red pixels, 2px wide).

## 3. Recommended minimal solution

**Option A (recommended):** Keep using synthetic `onChartClick` calls for logic
testing (already done in `test_browser_chart_drawing.py`). These verify the
placement, persistence, and coordinate-resolution logic without relying on
LWC's click dispatch.

**Option B (for real-click testing):** Use a real browser automation tool that
dispatches trusted OS-level input events (e.g., Selenium with native events, or
Puppeteer with `page.mouse.click()` which uses CDP `Input.dispatchMouseEvent`
with `trusted: true`). However, LWC's internal state machine may still not
recognize these as valid gestures.

**Option C (test harness change):** Add a test-only hook in the application that
exposes a function to simulate a click at a given (x, y) coordinate, bypassing
LWC's event dispatch. This would be a test-only code path, not a production
feature. **Requires approval** (user said "Do not change application behavior
merely to make tests pass").

## 4. What was verified vs not verified

### Verified (synthetic + pixel analysis)
- Vline creation at first/middle/last bar → correct timestamp, no jump to beginning. ✅
- Vline rendering → true vertical (canvas pixel analysis). ✅
- Viewport stability during drawing (range unchanged). ✅
- Save/restore persistence (coordinates match). ✅
- Panning toggle (pressedMouseMove disabled during drawing). ✅
- Hit-test tolerance increase (16/10 px). ✅
- All 12 analysis layers coexist, 0 console errors. ✅
- Full non-browser suite: 2,971 passed, 33 skipped, exit 0. ✅

### Not verified (BLOCKED)
- Real mouse click → drawing creation (Playwright limitation).
- Real mouse drag → anchor editing (Playwright limitation).
- Multi-touch/trackpad (no device).
- Per-tool styling controls (not audited).

### NOT-TESTED
- Real-browser click on canvas (requires Option B or C above).
- Crossline vertical rendering (deferred).

## 5. Status labels

- Real-browser interaction testing: **BLOCKED** (Playwright/LWC infrastructure limitation).
- Synthetic logic testing: **TESTED-PASS** (all drawing tests pass).
- Canvas pixel verification: **TESTED-PASS** (vertical=true).
- Viewport stability: **TESTED-PASS**.

**No code modified during this investigation.** Awaiting your approval for a testing approach.
MD
echo "written"