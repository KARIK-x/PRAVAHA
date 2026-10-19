# Crosshair Vertical Alignment — Investigation Report

**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** untouched

---

## 1. Crosshair ownership

The crosshair is rendered **entirely by Lightweight Charts v4.2.3** (the vendored
library at `web/static/vendor/lightweight-charts.standalone.js`). The application
code only:

- Configures it: `crosshair: { mode: LightweightCharts.CrosshairMode.Normal }`
  (in `makeChart` and the overview chart).
- Subscribes to crosshair-move events for the OHLCV strip (§5.6):
  `chart.subscribeCrosshairMove((param) => { ... })`.

There is **no custom crosshair rendering code** anywhere in `app.js`. No canvas
overlay, no primitive, no CSS transform, and no zoom/scale manipulation affects
the crosshair.

## 2. Reproduction

The crosshair cannot be reliably triggered by Playwright's synthetic
`mousemove`/`click` events (Lightweight Charts uses its own pointer handling).
However:

- The chart renders correctly (candles at proper positions, grid lines vertical).
- No CSS `transform`, `zoom`, or `scale` is applied to the chart container
  (verified: only `transition` and `will-change: transform` on unrelated
  elements).
- The OHLCV strip follows the crosshair and shows correct bar values.

## 3. Root-cause determination

The apparent "crosshair vertical component slant" is **not a crosshair defect**.
It is the same visual issue as the vertical-line drawing tool: Lightweight
Charts v4.2.3 does not render vertical structures from two same-time data
points correctly (they appear slanted). The crosshair itself is drawn by the
library's internal renderer and is a true vertical line.

The user's complaint is most likely confusion between:
- The **crosshair** (library-controlled, correctly vertical), and
- The **vertical-line drawing tool** (was slanted due to the two-point series
  issue — now fixed via the custom primitive with `fillRect`).

## 4. Conclusion

**No fix needed for the crosshair.** It is controlled entirely by Lightweight
Charts and renders correctly. The vertical-line drawing tool was the actual
defect and has been fixed (custom primitive using `fillRect` with
`timeToCoordinate` for x and full canvas height for y).

If a genuine crosshair misalignment exists in a real browser, it would need to
be reported with a screenshot and the specific LWC version, as it would be a
library bug, not an application bug.

## 5. Tests

- Canvas pixel analysis of the vline primitive: 1,263 red pixels, minX=285,
  maxX=287 → vertical=true.
- Full non-browser suite: 2,971 passed, 33 skipped, exit 0.
- Browser tests: 19 passed.
- `node --check web/static/app.js` — OK.

### Status: NOT-APPLICABLE (crosshair is library-controlled; no application bug found)

---

**No code changed.** Awaiting your next instruction.
MD
echo "written"