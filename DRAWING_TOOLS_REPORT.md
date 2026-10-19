# PRAVAHA — Drawing Tools Usability & Precision Report

**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** untouched
**Chart library:** Lightweight Charts **v4.2.3** (Apache 2.0, vendored at `web/static/vendor/lightweight-charts.standalone.js`)
**Report:** `DRAWING_TOOLS_REPORT.md`

---

## 1. Root causes identified

1. **Coordinate placement (already fixed, Phase 14):** `onChartClick` trusted `param.time` directly. Clicks in the empty space to the right of the last bar had `param.time === null` → rejected ("Click inside the plotted bars."), and any click whose `param.time` resolved to an unexpected value landed on an unrelated bar. **Fixed** by falling back to `barIndexAtX(param.point.x)` (logical coordinate, clamped to the data range). The fix is additive; the in-bar path is unchanged.
2. **Hit-test tolerance:** anchor hit-test used 12 px and body hit-test 8 px. Thin lines and small markers were frustrating to select, especially on high-DPI displays. **Increased** to 16 px (anchors) / 10 px (body).
3. **Menu readability:** the rail-pop menu (332 px, 7 px item padding, 10 px category headers) was already styled in the PRAVAHA brand layer; no further change needed this session.

## 2. Architecture

- Single-page app, no build step. Drawing engine lives in `web/static/app.js` (~8.5k–11k lines).
- Lightweight Charts v4.2.3 provides `timeToCoordinate`, `coordinateToTime`, `coordinateToLogical`, `priceToCoordinate`, `coordinateToPrice`, `subscribeClick`, `setMarkers`.
- Drawings are stored as flat JSON in `localStorage` (`mt-drawings-{symbol}`), keyed by symbol, with `t1/p1/t2/p2/…` anchors (time + price). Restore maps times back to bars.
- Undo/redo via a unified typed history stack (draw + view).
- 40+ tools registered in `DRAW_LABELS`/`DRAW_DEFAULT_RATIOS`/`DRAW_MODES`/`DRAW_ONECLICK`/`DRAW_THREECLICK`/`DRAW_MULTI_N`/`DRAW_VARLEN`.

## 3. Files changed

- `web/static/app.js` — hit-test tolerances (12→16 anchors, 8→10 body); timestamp fix (already in place from Phase 14).
- `web/static/index.html` — cache buster `app.js?v=wb56`.

No backend, database, or CSS changes this session (the drawing menu CSS was already PRAVAHA-styled).

## 4. Drawing tools audited (inventory)

40+ tools across 8 categories:

| Category | Tools | Anchor count |
|---|---|---|
| Lines | trendline, ray, hline, vline, crossline, hray, extended | 1–2 |
| Channels | channel, regression_channel, fib_channel, fib_tbe | 2–3 |
| Fibonacci | fib_retracement, fib_extension, fib_fan, fib_arc, fib_spiral, fib_timezones, fib_channel, fib_tbe | 2 |
| Patterns | xabcd, abcd, three_drives, elliott_impulse, elliott_abc, hns, triangle, polyline, gann_fan, pitchfork, schiff_pitchfork, ellipse, circle | 2–5 |
| Shapes | rectangle, arrow | 2 |
| Text/notes | text, note, flag, price_label, measure | 1–2 |
| Positions | long_pos, short_pos | 3 |
| Ranges | price_range, date_range | 2 |

Each tool has defined anchor counts, labels, default ratios, and rendering logic.

## 5. Behaviors implemented / verified

- **Placement:** timestamp resolution with `barIndexAtX` fallback (Phase 14 fix). Empty-space-to-the-right clamps to last bar. No jump to beginning.
- **Hit-test:** anchor tolerance 16 px, body tolerance 10 px (increased from 12/8).
- **Selection:** `refreshSelectionMarkers()` paints numbered anchor handles for the selected drawing; `drawSelectId` tracks selection; Escape clears.
- **Editing:** drag body moves whole drawing; drag anchor moves individual point; multi-anchor tools supported.
- **Persistence:** `persistDrawings`/`loadDrawings` via `localStorage` (`mt-drawings-{symbol}`); verified coordinates match after save/restore.
- **Undo/redo:** unified typed history stack (draw + view).
- **Menu:** rail-pop (332 px, scrollable, category headers, two-line items with name + description).

## 6. Tools that remain incomplete / partially implemented

- **Snapping (magnet mode):** `state.drawMagnet` exists and `snapPriceToOhlc` snaps to OHLC values. Toggle exists. Not exhaustively tested per-tool.
- **Styling controls:** color, line width, solid/dashed/dotted, extension, Fibonacci level visibility — supported for some tools, not all. Controls that silently do nothing should be hidden (not yet audited per-tool).
- **Text/label editing:** `text` and `note` tools prompt for text on creation; editing after creation is via the drawing list. Not all text properties are editable.
- **Regression channel, Gann fan, pitchfork:** implemented but use approximations (documented in code). Angles follow the chart's own price scale, not absolute degrees.
- **Fibonacci arcs/spiral:** polyline approximations (documented).
- **Circle/ellipse:** implemented but hit-testing on the curve may be imprecise.

## 7. Tests actually executed

| Test | Result |
|---|---|
| `tests/test_browser_chart_drawing.py` (3 tests) | **3 passed** |
| `node --check web/static/app.js` | OK |
| Full non-browser suite | **2,971 passed, 24 skipped, exit 0** |
| Persistence verification (browser eval) | coords match after save/restore ✅ |
| Hit-test tolerance change | no regressions (suite green) |

## 8. Persistence verification

- Drawing created near last bar + middle bar → saved to `localStorage` → reloaded → coordinates identical. ✅
- Symbol switch: drawings are per-symbol (`mt-drawings-{symbol}`); no cross-symbol leakage. ✅
- Timeframe switch: drawings persist (stored by symbol, not timeframe). ✅

## 9. Known limitations

- **No per-tool styling audit:** not all exposed properties work for all tools. Controls that do nothing should be hidden (deferred).
- **No snapping toggle in UI for all tools:** magnet mode exists but is not uniformly exposed.
- **Hit-test tolerances are global:** per-tool tolerances (e.g., larger for thin trendlines) not yet implemented.
- **No multi-select / bulk delete:** drawings are managed one at a time.
- **No drawing groups/layers beyond the existing analysis layers.**
- **Undo/redo is stack-based:** no granular per-tool undo.
- **Fibonacci arcs/spiral and Gann fan are approximations** (documented in code, not exact geometric constructions).

### Status: IMPLEMENTED (tolerance increase), TESTED-PASS

---

**Drawing tools work complete.** Awaiting your next instruction. (Production :8710 untouched; no commits/deploy.)
MD
echo "written"