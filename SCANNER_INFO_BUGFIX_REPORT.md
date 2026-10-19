# More Scanners: Selection, Execution, and Info Context — Bug Fix Report

**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** untouched

---

## Bug 1 — Selecting a scanner ran it automatically

### Root cause
`updatePresetDesc()` defined an inner `run` async function that both updated the
description **and** executed the scan (`api("/api/screen", ...)`), then called
`run()` unconditionally at the end. Since `updatePresetDesc` was wired to BOTH
the `#preset` change handler AND the `#run-screen` click handler, selecting a
scanner triggered a full scan.

### Fix
Split into two functions:
- `updatePresetDesc(presets)` — updates `#preset-desc` text only; also shows a
  stale-results banner (`#screen-stale`) so leftover results are clearly marked as
  belonging to a previous run.
- `runScreen()` — finds the preset, sets `currentScreenTree`, calls the API,
  renders summary + results, hides the stale banner.

Wiring: `#run-screen` → `runScreen()`; `#preset` change → `updatePresetDesc()`
(description only). Init calls `updatePresetDesc(p.presets)` (description only,
no scan).

### Files changed
- `web/static/app.js` — split `updatePresetDesc`/`runScreen`; updated wiring.
- `web/static/index.html` — added `#screen-stale` banner; cache buster `wb49`.

## Bug 2 — Scanner Info opened in Charting

### Root cause
The `#tool-info` modal was nested inside `<section id="view-charts">` (lines 312–1045).
When any non-charts view was active, `view-charts` had `display: none`, which
hid the modal entirely (0×0 bounding box). Clicking Info on the screener/backtest
page set `modal.hidden = false` but the element was invisible; navigating to
Charting then revealed it — appearing as "info displays in Charting."

### Fix
Moved `#tool-info` out of `view-charts` to the shell level (after the chat
aside, before `</main>`), so it overlays every view. No JS logic changed.

### Files changed
- `web/static/index.html` — relocated `#tool-info` modal to shell level.

## Verification (browser)
- Selecting "Money Flow oversold" (`mfi_oversold`): summary empty, results empty, stale banner visible. **No scan ran.**
- Pressing "Run Screen": summary + results populated, stale banner hidden. **Exactly one scan.**
- Info on screener: modal visible (width 760), active view stays `view-screener`, title "Oversold momentum scanner".
- Info on backtest: modal visible, active view stays `view-backtest`, title reflects selected strategy.
- Closing Info preserves the selected scanner and its configuration.

## Tests executed
- Full non-browser suite: running in background (2,956 passed last run).
- `node --check web/static/app.js` — OK.

## Status
- Bug 1: **IMPLEMENTED, TESTED-PASS**
- Bug 2: **IMPLEMENTED, TESTED-PASS**

## Limitations
- No dedicated regression test file added yet for these two bugs (verified via browser eval). A focused browser test could be added in a follow-up.
- The `#cmdk` modal remains inside `view-charts` and has the same latent issue; not fixed here (out of scope).
MD
echo "written"