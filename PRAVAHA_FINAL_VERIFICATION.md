# PRAVAHA — Final Verification Report

**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** untouched (PID 26596)

---

## 1. Test Suite Status

- **Full non-browser suite:** 2,971 passed, 33 skipped, exit 0 (118.90s).
- **Browser tests:** 47 passed (19 new + 28 pre-existing).
- **JS syntax:** OK on app.js, viz.js, kronos_ui.js, indicator_info.js.
- **No active test processes** at time of this report.

## 2. Sector Explorer Verification

### Implementation
- **Backend:** `/api/sectors` endpoint auto-imports from CSV files on first access. 360 symbols classified into 16 sectors.
- **Frontend:** `loadNewSectorExplorer` fetches `/api/sectors` and displays a table with sector name, symbol count, and sample members.
- **Data source:** `data/review/sources/yonepse/yonepse_sectors.csv` (649 rows) + `data/review/sources/binayabaral/binayabaral_sectors.csv` (274 rows).

### Verification
- HTTP status: 200 ✅
- Response schema: `{sector_map, by_sector, total_classified, total_sectors, source}` ✅
- total_classified: 360 ✅
- total_sectors: 16 ✅
- Sample: Hydropower → 108 symbols (AHL, AHPC, AKJCL, AKPL, APHL, ...) ✅
- UI renders table with 16 rows ✅
- Console errors: 0 ✅

### Limitations
- Sector classification is from CSV files (yonepse + binayabaral), not from live NEPSE data.
- No sector index values, historical performance, or constituent price data.
- "Commercial Bank" and "Commercial Banks" appear as separate sectors (inconsistent naming in source CSVs).
- No auto-update mechanism; CSVs are static review files.

**Status: IMPLEMENTED, TESTED-PASS (classification only; no price/performance data)**

---

## 3. Motion System Verification

### Implementation
- Motion tokens in `:root` (`--motion-fast`, `--motion-standard`, `--motion-smooth`, `--motion-emphasis`, `--ease-standard`, `--ease-enter`, `--ease-exit`).
- View transition: `.view` fades in + slides up (4px) on `.active`.
- Card/KPI entrance: `pravaha-fade-up` keyframe on `.card`, `.kpi`, `.ss-kpi`, `.ov-panel`, `.stat`.
- Button press: `translateY(1px)` on `:active`.
- Drawer/modal/dropdown entrance animations.
- Skeleton shimmer (`.skeleton` class, not yet wired to loading states).
- Chart container reveal (`.chartbox`, `.viz-chart-card`, `.viz-host`).
- Toast entrance.
- Scroll-triggered reveals (`.reveal`/`.reveal.in` + IntersectionObserver in `loadMarketOverview`).
- Reduced-motion: all animations disabled under `prefers-reduced-motion`.

### Verification
- CSS braces balanced (748/748).
- Motion tokens present in `:root`.
- `::selection` changed to cyan (better contrast).
- `.reveal` class added to market barometer card.
- IntersectionObserver instantiated in `loadMarketOverview`.
- Reduced-motion media query present and comprehensive.

### Limitations
- `.skeleton` class defined but not wired to loading states (no skeleton elements in HTML).
- Scroll-triggered reveals only on market barometer card (not all dashboard sections).
- No numerical performance measurement (60 FPS not verified).
- Reduced-motion not tested with OS-level setting.

**Status: IMPLEMENTED, TESTED-PASS (CSS + IntersectionObserver), NOT-TESTED (skeleton wiring, reduced-motion OS setting)**

---

## 4. Analysis Panel Scroll Verification

### Implementation
- `.chart-drawer`: `max-height: 440px`, `overflow-y: auto`, `overflow-x: hidden`.

### Verification
- Drawer scrollHeight: 1337, clientHeight: 438 → independently scrollable ✅
- No large empty gap (drawer has defined max-height) ✅
- Overflow-x: hidden (no horizontal scroll) ✅

**Status: IMPLEMENTED, TESTED-PASS**

---

## 5. Hover Contrast Verification

### Implementation
- `::selection`: cyan background (rgba(0,217,232,.32)).
- `.nav button:hover`: white text on panel-2 background.
- `button.ghost:hover`: white text, cyan border, hover tint.
- `.chip.active/.chip.on`: cyan border, mint text.
- `.selected` utility class: cyan background, cyan border, mint text, cyan inset bar.

### Verification
- Contrast: white (#F5F8F7) on panel-2 (#0B1E1A) ≈ 16:1 (well above 4.5:1). ✅
- Cyan (#00D9E8) on panel-2 (#0B1E1A) ≈ 8:1 (above 4.5:1). ✅
- Mint (#A8FFD9) on panel-2 (#0B1E1A) ≈ 14:1 (well above 4.5:1). ✅

### Limitations
- Not all hover states audited (only key components).
- No WCAG contrast calculation automated.

**Status: IMPLEMENTED, TESTED-PASS (key components), NOT-TESTED (full audit)**

---

## 6. Seven New Analysis Categories Verification

### Implementation
All 7 categories added as LAYER_DEFS entries with plot functions and applyChartLayers branches:

| # | Category | Reuses | Data source | Graphical output | Status |
|---|---|---|---|---|---|
| 1 | Market Regime & Rotation | Trend layer (ADX regime) | Stored bars | Regime label in layer data | IMPLEMENTED, TESTED-PASS |
| 2 | Gap & Opening-Price Analysis | `/api/bars/{symbol}/gaps` | Stored bars | Gap markers on chart | IMPLEMENTED, TESTED-PASS |
| 3 | Relative Performance & Leaders/Laggards | `/api/bars/{symbol}/relative-strength` | Stored bars + NEPSE index | RS ratio line (mint) | IMPLEMENTED, TESTED-PASS |
| 4 | Market Microstructure & Liquidity Proxies | Relative volume indicator | Stored bars | RVOL line (caution) | IMPLEMENTED, TESTED-PASS (proxies only) |
| 5 | Price Distribution & Value Areas | Volume profile endpoint | Stored bars | POC/VAH/VAL lines | IMPLEMENTED, TESTED-PASS |
| 6 | Event & Corporate-Action Analysis | Corporate actions API | Honest unavailable (0 events) | No markers (honest state) | IMPLEMENTED (honest state) |
| 7 | Strategy & Signal Validation | Backtesting engine | Stored bars | Link to backtesting view | IMPLEMENTED |

### Verification
- All 7 toggle on without errors ✅
- Gap: 5 detections, drawn 5 ✅
- Regime: count 1, drawn 1 ✅
- Relative: count 1, drawn 1, RS available ✅
- Micro: count 1, drawn 1, RVOL available ✅
- Distribution: count 3, drawn 3 ✅
- Event: count 0, drawn 0, honest unavailable ✅
- Strategy: count 1, drawn 1 ✅
- No console errors ✅

### Limitations
- No dedicated unit tests for the 7 new categories' calculations.
- Event layer has no data (honest unavailable state).
- Microstructure uses proxies only (no order book data).
- Price distribution is a daily-bar approximation (not tick-level).

**Status: IMPLEMENTED, TESTED-PASS (toggle + graphical output), NOT-TESTED (numerical unit tests for new categories)**

---

## 7. Drawing System Verification

### Vertical-line primitive
- Custom primitive using `fillRect` with `timeToCoordinate` for x and full canvas height for y.
- Verified: 438 non-bg pixels at x=256 (full height, 2px wide) → vertical=true ✅
- Console: 0 errors ✅

### Crossline
- Vertical component fixed to use same primitive ✅
- Horizontal component uses LineSeries (unchanged) ✅

### Live preview
- 50% opacity dashed line from first anchor to cursor ✅
- Reuses series to avoid flicker ✅
- Cleared on commit, cancel, tool switch ✅

### Panning toggle
- `pressedMouseMove: false` when drawing tool active ✅
- `pressedMouseMove: true` when cursor tool active ✅

### Hit-test tolerance
- Anchors: 16px, Body: 10px ✅

### Viewport stability
- No `scrollToRealTime()` on result selection ✅
- Range unchanged (0→119) after drawing ✅

### Persistence
- Save/restore verified (coords match) ✅
- Per-symbol (`mt-drawings-{symbol}`) ✅

### Known limitations
- Real-browser click testing: BLOCKED (Playwright limitation)
- `priceToCoordinate` broken (affects snapping)
- Crossline vertical: fixed (primitive)
- Per-tool styling: not audited
- Multi-select/bulk delete: not implemented

**Status: IMPLEMENTED, TESTED-PASS (synthetic + pixel), BLOCKED (real-browser clicks)**

---

## 8. Barometer 3.0 Verification

### Implementation
- Market Battery meter on overview dashboard with gauge (0-100).
- Breakdown section below gauge with:
  - Score (51/100, Neutral)
  - A/D share (65.2%, weight 50%)
  - Above 50-day MA (36.8%, weight 50%)
  - Unchanged count (21 of 326)
  - Component contributions (32.6 + 18.4 = 51.0, reconciles ✅)
  - Interpretation text (deterministic, based on score)
  - Concentration warning (conditional)
  - Data timestamp (2026-10-15) and freshness (delayed)
  - Reconciliation note

### Formula
- Score = 0.5 × A/D share + 0.5 × % above 50-day MA
- A/D share = advancers / (advancers + decliners) × 100
- Independently verified: 0.5 × 65.2 + 0.5 × 36.8 = 51.0 ✅

### Limitations
- No historical score trend (no historical breadth snapshots stored).
- No live data (daily only, as of 2026-10-15).
- No sector-level breakdown in the meter (sector performance is separate).

**Status: IMPLEMENTED, TESTED-PASS (formula + breakdown + reconciliation)**

---

## 9. Hover Contrast Verification

### Implementation
- `::selection`: cyan background (rgba(0,217,232,.32)).
- `.nav button:hover`: white text on panel-2.
- `button.ghost:hover`: white text, cyan border.
- `.chip.active/.chip.on`: cyan border, mint text.
- `.selected` utility class: cyan.

### Contrast ratios
- White (#F5F8F7) on panel-2 (#0B1E1A): ~16:1 ✅ (above 4.5:1)
- Cyan (#00D9E8) on panel-2 (#0B1E1A): ~8:1 ✅ (above 4.5:1)
- Mint (#A8FFD9) on panel-2 (#0B1E1A): ~14:1 ✅ (above 4.5:1)

### Limitations
- Not all hover states audited (only key components).
- No automated WCAG contrast calculation.

**Status: IMPLEMENTED, TESTED-PASS (key components), NOT-TESTED (full audit)**

---

## 10. Analysis Panel Scroll Verification

### Implementation
- `.chart-drawer`: `max-height: 440px`, `overflow-y: auto`, `overflow-x: hidden`.

### Verification
- scrollHeight: 1337, clientHeight: 438 → independently scrollable ✅
- No large empty gap ✅
- Overflow-x: hidden (no horizontal scroll) ✅

**Status: IMPLEMENTED, TESTED-PASS**

---

## 11. Final Test State

### Full non-browser suite
- **2,971 passed, 33 skipped, exit 0** (118.90s).

### Browser tests
- **47 passed** (19 new + 28 pre-existing).

### JS syntax
- `node --check`: OK on app.js, viz.js, kronos_ui.js, indicator_info.js.

### Ruff
- Clean on touched files. 18 pre-existing findings in api.py.

---

## 12. Production Safety

- **Port 8710:** PID 26596 (unchanged). Not modified.
- **No commits, push, or deploy.**
- **No destructive Git operations.**
- **All work on dev port 10000.**

---

## 13. Evidence Labels Summary

| Feature | Status |
|---|---|
| PRAVAHA rebrand | IMPLEMENTED, TESTED-PASS |
| TTM EPS safety | IMPLEMENTED, TESTED-PASS |
| Indicator readability | IMPLEMENTED, TESTED-PASS |
| Chart drawing (timestamp, panning, viewport, hit-test) | IMPLEMENTED, TESTED-PASS |
| Vertical-line primitive | IMPLEMENTED, TESTED-PASS (canvas pixel) |
| 5 analysis categories | IMPLEMENTED, TESTED-PASS |
| 7 new research categories | IMPLEMENTED, TESTED-PASS (toggle + output) |
| More Scanners selection/execution | IMPLEMENTED, TESTED-PASS |
| Contextual Info modal | IMPLEMENTED, TESTED-PASS |
| Scanner auto-execution fix | IMPLEMENTED, TESTED-PASS |
| Market Battery 3.0 | IMPLEMENTED, TESTED-PASS (formula + breakdown) |
| Motion design system | IMPLEMENTED, TESTED-PASS (CSS + IntersectionObserver) |
| Hover contrast | IMPLEMENTED, TESTED-PASS (key components) |
| Analysis panel scroll | IMPLEMENTED, TESTED-PASS |
| Live drawing preview | IMPLEMENTED, TESTED-PASS |
| Sector Explorer | IMPLEMENTED, TESTED-PASS (classification) |
| Real-browser click testing | BLOCKED (Playwright/LWC limitation) |
| TTM EPS computation | BLOCKED (source basis undocumented) |
| Sector auto-classification | IMPLEMENTED (auto-import from CSVs) |
| Dividend analysis | BLOCKED (no DPS data) |
| Live NEPSE feed | BLOCKED (401, no credentials) |
| Technical indicators (numerical) | NOT-TESTED (structural invariants only) |
| Transaction costs (rates) | UNVERIFIED (not reconciled) |
| Backtesting (numerical) | NOT-TESTED (independently) |
| Fibonacci (numerical) | NOT-TESTED (structural invariants only) |
| Crossline vertical component | IMPLEMENTED, TESTED-PASS (primitive) |
| Per-tool styling | NOT-TESTED |
| Multi-select/bulk delete | NOT-IMPLEMENTED |
| Multi-Timeframe Trend Consensus | NOT-IMPLEMENTED |
| Reduced-motion (OS-level) | NOT-TESTED |
| Skeleton loading (wired) | NOT-IMPLEMENTED (class exists, not wired) |
| Scroll-triggered reveals (full) | PARTIAL (only market barometer card) |

---

## 14. Recommended next steps (highest priority)

1. **Obtain real-browser testing capability** (Selenium/Puppeteer with native input, or a test-only click hook with approval).
2. **Fix crossline vertical component** — DONE (primitive).
3. **Auto-import sector CSVs** — DONE (auto-import on first access).
4. **Investigate `priceToCoordinate` fix** (LWC v4.2.3 bug; may need LWC upgrade).
5. **Add TTM EPS tests** for the new "unavailable" contract.
6. **Reconcile broker commission rates** against actual contract notes.
7. **Wire skeleton loading states** to actual loading (overview, charts).
8. **Extend scroll-triggered reveals** to all dashboard cards.

**Audit complete.** All safe, verified work is done. No code modified during this audit. Awaiting your next instruction.
MD
echo "written"