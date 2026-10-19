# Session 27 — strict completion report (2026-10-18)

Scope: continue the NEPSE Mega Tool charting / TA / research workbench mission on
top of session 26. **No rebuild, no reversal of prior work, no new disconnected
frontend.** The existing app is the source of truth; working features, data and
user configs were preserved.

Safety envelope actually held:

* Production uvicorn **PID 26596 untouched** (uptime `03-07:04:54` at session
  end, still serving `http://127.0.0.1:8710/` → 200). No kill / restart / modify.
* Production DBs untouched; dev work served from `data/dev/release` on
  `http://127.0.0.1:10000/` → 200.
* **No commits, no pushes, no deploys.** ~270 files remain uncommitted on `main`
  (HEAD `b6c3659`). No destructive git operations.
* No secrets written to logs or reports. No paid APIs, no infra changes.

Status labels used exactly: **IMPLEMENTED** · **TESTED-PASS** · **TESTED-FAIL** ·
**NOT-TESTED** · **BLOCKED** · **APPROXIMATION** · **DATA-DEPENDENT** ·
**NOT IMPLEMENTED (backlog)**.

---

## The 18 items

| # | Item | Status | What backs it |
|---|------|--------|---------------|
| 1 | **A1** Drawing tools: cursor-follow, selection, accurate geometry (pitchfork, Fibonacci) | **IMPLEMENTED + TESTED-PASS** for cursor-follow / hit-testing / drag; **NOT-TESTED** this session for pitchfork & Fibonacci *geometry* | Browser: body hit-test at a trendline midpoint returns `dist 0`; drag moves anchors with the cursor. Pitchfork/Fib geometry was not re-exercised this session and is not claimed. |
| 2 | **A2** Selection, eraser click-to-delete, Delete key, undo/redo, selection not polluting history | **IMPLEMENTED + TESTED-PASS** | Browser on NABIL: select (2 handles) → drag → eraser on body deletes → Cmd+Z restores → Delete deletes → Cmd+Z → Shift+Cmd+Z redo; selection leaves undo stack at 1. `KNOWN_BUGS.md` B-92…B-96; `TEST_RESULTS.md` §27 #11–23. |
| 3 | **A3** Clear button next to Settings + confirmation dialog (drawings / indicators / both); never silently deletes layouts/templates/watchlists; undo where practical | **IMPLEMENTED + TESTED-PASS** | Browser: dialog lists 3 scopes with live counts (drawings 1 / indicators 4 / analysis 1); drawings-only confirm → drawings 0 while indicators 3 and layers `{sr:true}` untouched; Cmd+Z restored the drawing; modal closes with an honest status. Layouts/templates/watchlists are structurally out of scope. Screenshot `-clear-dialog.png`. |
| 4 | **B1** Indicator discoverability — expose the full implemented set (report said 81, UI looked like ~10–15) | **TESTED-PASS — not a defect** | Browser: catalog modal reports **"81 of 81 registered"** (82 rows incl. header). The ~10–15 was the quick-layer checkbox subset, not the indicator set. Screenshot `-catalog.png`. |
| 5 | **B2** Indicator search / favourites / recents / categories; picker works in expanded chart mode | **PARTIAL** — search + 7 categories **TESTED-PASS**; favourites & recents present but **NOT re-clicked** this session; expanded-mode picker **NOT-TESTED** | Browser: filters all/favs/trend/momentum/volatility/volume/other; indicator search returns hits. `mt-ind-recents` / `mt-ind-templates` keys exist and are written. |
| 6 | **B3** Correct overlay-vs-pane placement + indicator identity tooltips | **IMPLEMENTED + TESTED-PASS** | Browser: `sma` → overlay on price; `macd` and `rsi` → own synced panes below (2 panes, 2 headers). Session-26 matrix 28 overlay / 53 pane unchanged. |
| 7 | **C1** Genuine candlesticks when valid OHLC exists | **IMPLEMENTED + TESTED-PASS** | Browser: NEPSE index renders **750 / 750 genuine candles**, `#chart-type=candles` enabled, meta `index · 2217 OHLC / 3079 close-only · candles from 2016-11-28`. Screenshot `-index-candles.png`. |
| 8 | **C2** Never fabricate OHLC or volume; chart types gated to available data | **IMPLEMENTED + TESTED-PASS** | Placeholder rows (open NULL) and rows the source flagged `invalid` are preserved as NULL and drawn as **whitespace gaps** (candle/bar/hollow/Heikin), never `O=H=L=C`; Heikin chains only across genuine rows and resets at a gap; type availability is driven by `genuine_ohlc_count` (index) / `hasBody()` (stock) with the reason in the option tooltip. Browser: 20 in-window `invalid` rows shown as gaps. `KNOWN_BUGS.md` B-98. |
| 9 | **C3** Close-only series labelled and drawn line/area; Renko/Kagi/P&F/range honest | **IMPLEMENTED + TESTED-PASS** for the label & gap path; **NOT IMPLEMENTED (backlog)** for the non-time-based types | Legend shows "no OHLC body (close-only/invalid row)" and the index's owned turnover as `T/O`, never `V`. Renko/Kagi/P&F/range bars remain absent by design (`REMAINING_BLOCKERS.md` §2) — not imitated. |
| 10 | **D1** Analysis overlays on the chart with **mandatory viewport preservation** (no auto fitContent) | **IMPLEMENTED + TESTED-PASS** | Browser: zoom `{81.8, 167.2}` → toggle Support/Resistance (10 lines of 73 zones) → range byte-identical. `KNOWN_BUGS.md` B-99; `TEST_RESULTS.md` §27 #9–10. |
| 11 | **D2** Analysis manager; honest Elliott labels / invalidation / alternative counts | **NOT-TESTED this session** (carried over) | The analysis drawer and the Elliott module exist from earlier sessions and were not re-exercised now. Not claimed as verified for this session. |
| 12 | **E** Global search / command palette covering the required surfaces, actionable, no dead controls | **IMPLEMENTED + TESTED-PASS** | Cmd/Ctrl+K or `⌕ Search`: 80 results for `trend`, grouped over views / chart types / 39 drawing tools / analysis / all 81 indicators / screener presets / 12 actions; `rsi`, `horizontal line`, `elliot`, `seasonality`, `support`, `clear`, `candle` all resolve; alpha-coder-class requests appear **disabled with the reason**; an action ran end-to-end (RSI added → pane created → status). `TEST_RESULTS.md` §27 #27–30. Screenshot `-palette.png`. |
| 13 | **F** App-level undo/redo restoring real prior state | **IMPLEMENTED + TESTED-PASS** | Drawing history (depth 40) verified round-trip after erase, Delete and Clear; indicator history verified via the drawer Undo after a pane ✕ removal (restored all instances + 2 headers). |
| 14 | **G** Flexible, clean workspace — panels resize / collapse, move analysis to a separate panel/tab, saved layouts; no fake drag-drop | **PARTIAL** | Pane **drag-resize, collapse/expand, taller/shorter, ✕ remove** all **TESTED-PASS** and persisted per instance (screenshot `-pane-headers.png`). Moving panes between tabs/windows and named named-workspace pane-order saving are **NOT IMPLEMENTED** and not faked; layout JSON v1 covers chart config only. |
| 15 | **H** Verify the math of every touched indicator / algorithm | **TESTED-PASS** (nothing numeric changed; touched path is the OHLC display mapping) | No indicator formula was modified this session. Reference-value coverage re-run: `tests/test_indicators.py` (SMA exact, EMA seed = SMA of first period, OBV hand-computed, Bollinger **population** σ, RSI **Wilder published example**, VWMA naive reference, OHLC inputs honoured, MACD validation) + `tests/test_indicators2.py` (34 literal-formula tests incl. Balance of Power) + `tests/test_candles.py` (18 patterns) → **562 tests, exit 0**. The Heikin-Ashi/gap mapping is a display transform over unmodified stored rows and uses only past bars (no look-ahead). A standalone `atr` registry entry does not exist (ATR is an internal primitive), so none is claimed. |
| 16 | **I** Real interaction testing (30 enumerated cases) on the NEPSE index + ≥1 security, not mock-only | **TESTED-PASS** | 36 cases with **real trusted events** driven through `playwright-cli` (mousemove/mousedown/mouseup, key events) on NABIL (250 bars) and NEPSE (750 bars). Full matrix: `TEST_RESULTS.md` §"Session 27". |
| 17 | **J** Screenshot-based visual verification before/after | **TESTED-PASS** | `docs/evidence/workbench-2026-10-18-{index-candles,palette,clear-dialog,catalog,pane-headers,drawings}.png`; index-candles and palette inspected visually. |
| 18 | **K & L** Small safe batches; no whole session lost to docs; strict completion report | **TESTED-PASS** | Work delivered in small batches (drawing engine → viewport → index candles → Clear → palette → pane headers), each `node --check`ed and browser-verified before the next; full suite re-run at the end (**2,599 passed / 0 failed / 0 errors / 0 skipped, exit 0**, `$TMPDIR/full3.log`). This report is the Part L deliverable. |

---

## Honest summary of what is *not* done

* **NOT IMPLEMENTED:** non-time-based chart types (Renko/Kagi/P&F/range),
  multi-symbol grid, pane drag-out / pane reordering, multi-timeframe overlays,
  MTF scan, opt-in auto trendline detection, a named workspace that saves pane
  order, the Alpha Coder natural-language assistant, a single unified Part-18
  engine.
* **NOT-TESTED this session:** Elliott labels/invalidation/alternatives,
  pitchfork & Fibonacci geometry, favourites/recents clicks, expanded-chart-mode
  indicator picker, and the session-26 feature areas listed at the end of
  `TEST_RESULTS.md`.
* **BLOCKED / owner-gated:** Kronos NABIL GPU run (awaiting explicit approval),
  independent source verification (community source has no LICENSE),
  `python-dotenv` CVE upgrade, commit / push authorization.
* **DATA-DEPENDENT:** corporate actions (all prices unadjusted), holiday
  seasonality (no holiday entries), source-flagged `invalid` index rows (54).

## Compliance with the standing rules

* No fabricated tests, market data, indicator results or completions — every
  claim above names a command, a log, or a screenshot.
* Runtime behaviour was trusted over reports: the index 404s, the fabricated
  placeholder candles, the anchor-only eraser, the pan-during-drag and the
  viewport reset were all found by watching the live app, not by reading docs.
* No destructive git operations; app stayed runnable throughout (dev 200,
  prod 200).
* Documents updated: `IMPLEMENTATION_STATUS.md`, `CHART_UX_AUDIT.md`,
  `TEST_RESULTS.md`, `KNOWN_BUGS.md`, `CHANGELOG.md`, `CURRENT_PROJECT_STATE.md`,
  `REMAINING_BLOCKERS.md`. `INDICATOR_CATALOGUE.md` and
  `INDICATOR_SOURCE_AND_LICENSE_AUDIT.md` are unchanged because no indicator was
  added, removed or re-licensed this session.

## Dev-state note (left for the owner)

The dev browser profile keeps: `mt-custom-inds-NABIL` (sma, macd, rsi — `rsi`
was added while verifying the palette), `mt-drawings-NABIL` (one trendline that
proves the drawing flow), `mt-chart-layers-NABIL` (`{sr:true}`), plus the
indicator templates/recents. A stray `mt-chart-layers-NABI` typo key from an
earlier test was removed. To reset the workspace use the **Clear** button
(scoped, undoable) — no data or user config needs to be touched.
