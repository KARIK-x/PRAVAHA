# MASTER MISSION CHECKLIST — NEPSE Mega Tool

Consolidated Session 31 + 32 + 34 + KIMI Feature Suite
(source: `NEPSE_MEGA_TOOL_MASTER_MISSION_CONDENSED.md`).

Statuses: `[ ]` NOT-IMPLEMENTED · `[~]` PARTIAL · `[!]` BLOCKED · `[-]` NOT-TESTED ·
`[x]` IMPLEMENTED · `[x✓]` TESTED-PASS (test actually run and passed).

Baseline (2026-10-19, established this session):
- git HEAD `b6c3659`, 286 changed paths, 0 staged.
- Tests: **2701 passed / 0 failed / 0 skipped=8, exit 0** — log `$TMPDIR/baseline_s35.log`,
  independently re-counted by progress dots (2701).
- Prod :8710 HTTP 200 (untouched). Dev :10000 HTTP 200.

> HONESTY RULE: an item is `[x]` only when the code exists; `[x✓]` only when a
> test/browser check actually ran and passed. No item is marked done merely
> because a registry entry exists.

---

## 0. SAFETY / BASELINE
- [x✓] SAFE-1 Baseline suite run recorded (2701/0/8, exit 0)
- [x✓] SAFE-2 Prod :8710 HTTP 200, never signalled
- [x✓] SAFE-3 No commit/push/deploy; HEAD b6c3659; 0 staged
- [x✓] SAFE-4 git status captured (286 changed paths)
- [x✓] SAFE-5 Dev :10000 HTTP 200

## 1. TRACKING FILES (mission §3, §9, §10)
- [x] TRK-1 `MASTER_MISSION_CHECKLIST.md`
- [ ] TRK-2 `SESSION_31_GAP_AUDIT.md`
- [x] TRK-3 `SESSION_31_CHECKPOINT.md`
- [x] TRK-4 `SESSION_31_COMPLETION_REPORT.md` (from prior session)
- [ ] TRK-5 `SESSION_32_CORRECTNESS_INVENTORY.md`
- [ ] TRK-6 `SESSION_32_TEST_MATRIX.md`
- [x] TRK-7 `SESSION_32_CHECKPOINT.md`
- [ ] TRK-8 `SESSION_32_FINAL_REPORT.md`
- [x] TRK-9 `SESSION_34_REQUIREMENTS_REGISTER.md`
- [x] TRK-10 `SESSION_34_IMPLEMENTATION_CHECKLIST.md`
- [x] TRK-11 `SESSION_34_TEST_EVIDENCE.md`
- [x] TRK-12 `SESSION_34_CHECKPOINT.md`
- [ ] TRK-13 `SESSION_34_COMPLETION_REPORT.md`
- [x] TRK-14 `KIMI_IMPLEMENTATION/KIMI_REQUIREMENTS_REGISTER.md`
- [ ] TRK-15 `KIMI_IMPLEMENTATION/KIMI_FEATURE_INVENTORY.md`
- [ ] TRK-16 `KIMI_IMPLEMENTATION/KIMI_IMPLEMENTATION_CHECKLIST.md`
- [ ] TRK-17 `KIMI_IMPLEMENTATION/KIMI_DATA_DEPENDENCIES.md`
- [ ] TRK-18 `KIMI_IMPLEMENTATION/KIMI_TEST_EVIDENCE.md`
- [ ] TRK-19 `KIMI_IMPLEMENTATION/KIMI_CHECKPOINT.md`
- [ ] TRK-20 `KIMI_IMPLEMENTATION/KIMI_COMPLETION_REPORT.md`

## 2. PART A — CHARTING AND INDICATORS (§5) — status carried from sessions 30–31, re-verified

### A1 — Indicators
- [x✓] A1-1 92 indicators in registry (`ta.available()`)
- [x✓] A1-2 Verification map 62 reference / 28 invariants / 2 sparse
- [~] A1-3 Numerical reference tests for the 28 invariants-only indicators
- [!] A1-4 Sparse pivots (zigzag, williams_fractal) — no independent oracle
- [x✓] A1-5 Registry formula == implemented formula
- [x✓] A1-6 Warm-up / missing-data behaviour documented
- [x✓] A1-7 Overlay/pane placement (33 overlay / 59 pane)
- [~] A1-8 No-lookahead tests (partial coverage)

### A2 — Browser rendering of 92
- [~] A2-1 Batched browser add/info/remove for all 92
- [x✓] A2-2 Info button present for all 92 (session-30 pass)
- [~] A2-3 Legend/params/visibility/duplicate/symbol-change checks

### A3 — Quick Layers
- [x✓] A3-1 Per-symbol persistence `mt-quick-layers-<symbol>`
- [x✓] A3-2 Restore on load; save on toggle/remove/clear
- [~] A3-3 All presets verified in browser

### A4 — Analysis layers & patterns
- [x✓] A4-1 Fibonacci + viewport preservation {75,175}
- [x] A4-2 Elliott Wave candidate generation
- [x] A4-3 Harmonic patterns
- [x] A4-4 Classical chart patterns
- [x] A4-5 Candlestick patterns
- [x] A4-6 Support/resistance + strength scoring
- [x] A4-7 Trend context / swing analysis
- [~] A4-8 Per-pattern removal + invalidation display

### A5 — Object manager & cryptic labels
- [x✓] A5-1 Object manager groups
- [~] A5-2 Trace cryptic labels (BO/DT/INV/355/372/322)
- [x✓] A5-3 Quick layers group in object manager
- [x✓] A5-4 Scoped clearing

### A6 — Drawing/chart UX
- [x✓] A6-1 Coordinate conversion / hit testing / eraser
- [x✓] A6-2 Delete/Backspace handling
- [x] A6-3 Pitchfork geometry
- [~] A6-4 Undo/redo coverage
- [x✓] A6-5 Viewport preservation on analysis actions

### A7 — Multi-symbol comparison
- [x✓] A7-1 Up to 4 symbols overlay
- [x✓] A7-2 Relative-performance mode fix
- [x✓] A7-3 Primary-swap persistence
- [x✓] A7-4 Timeframe-aware compare fetch
- [~] A7-5 Separate synchronized panels mode

### A8 — Wire 5 quant capabilities into UI
- [x✓] A8-1 `rolling_beta` (`megatool/stats.py`)
- [x✓] A8-2 `volatility_percentile`
- [x✓] A8-3 `mtf_confluence`
- [x✓] A8-4 `technical_rating`
- [x✓] A8-5 S/R strength scoring
- [~] A8-6 Surface all 5 in existing UI panels (KIMI surface exists; dedicated panels PARTIAL)

### A9 — Fundamentals graphs / corporate actions
- [x✓] A9-1 P/E bars height-normalised
- [x✓] A9-2 P/B panel added
- [x✓] A9-3 ISO-date period comparison
- [!] A9-4 Corporate-action adjustment (all `unadjusted`; no verified action data)
- [x✓] A9-5 Missing/invalid values not silently converted

### A10 — APIs, refresh, freshness
- [x✓] A10-1 Data-source audit documented
- [x✓] A10-2 No Uniswap/crypto integration confirmed
- [!] A10-3 Auto-refresh/scheduler (none in-app)
- [x✓] A10-4 Stale-data honesty

### A11 — Settings, import/export, search, persistence
- [~] A11-1 Settings actually change behaviour
- [x✓] A11-2 Indicator favourites + recents
- [~] A11-3 Import/export schema validation
- [~] A11-4 Recent-search dropdown
- [x✓] A11-5 Per-symbol state isolation
- [x✓] A11-6 Malformed imports fail safely

## 3. PART B — SCANNERS, ALGORITHMS, STRATEGIES (§6)

### B1 — Inventory (verified this session)
- [x✓] B1-1 Scanner metric registry: **41 metrics** (`scanner.METRIC_HELP`)
- [x✓] B1-2 Scanner presets: **31 presets** (`scanner.PRESET_SCREENS`)
- [x✓] B1-3 Strategies: **58** (`backtest.STRATEGIES`; 20 original + 38 added)
- [x✓] B1-4 Indicators: **92** (registry)

### B2 — Searchable scanner catalogue (target 100–150)
- [x✓] B2-1 Scanner catalogue metadata (formula/tags/limits) — `megatool/catalog.py`
- [x✓] B2-2 **124** genuine scanner presets (mission target 100–150) — TESTED-PASS
- [x✓] B2-3 ⓘ info panel per scanner (formula/params/tags/limits/data-needs/status) — browser-verified
- [x✓] B2-4 Search by name/tag/keyword/formula + multi-term — browser-verified ("volume breakout" → 4 matches)
- [x✓] B2-5 Real execution path (`/api/screen`) — ran live: 4 matches with per-condition reasons
- [x✓] B2-6 Categories + filters in UI (10 categories) — browser-verified

### B3 — Searchable algorithm catalogue (target 70–150)
- [x✓] B3-1 Algorithm metadata (rules/tags/limits) — `megatool/catalog.py`
- [x✓] B3-2 **77** algorithms (58 backtest + 19 analysis; includes NF-005/007/008/030 engines), target 70–150 — TESTED-PASS
- [x✓] B3-3 ⓘ info panel per algorithm — browser-verified
- [x✓] B3-4 Search + category filters — browser-verified ("reversion" → 13)
- [x✓] B3-5 Real execution (`/api/backtest` + `/api/analysis/run`) — ran live (sma_cross on ACLBSL)

### B3b — Fundamental tool catalogue
- [x✓] B3b-1 **32** fundamental tools over stored data — TESTED-PASS
- [x✓] B3b-2 Honest blocked state for dividend yield (DPS has 0 records) — TESTED-PASS
- [x✓] B3b-3 Real execution (`/api/fundamental/run`) — ran live (P/E on ACLBSL = 33.34)

### B4 — Strategy catalogue / My Algorithms UX
- [~] B4-1 Searchable strategy catalogue in UI
- [~] B4-2 Selected/configured/running/completed/failed states
- [ ] B4-3 Saved configurations
- [~] B4-4 Strategy/algorithm distinction

### B5 — Backtest/scanner correctness
- [x✓] B5-1 No future leakage (signal timing)
- [x✓] B5-2 Fees/slippage supported
- [x✓] B5-3 Reproducibility
- [x✓] B5-4 Trade accounting reconciliation
- [!] B5-5 Survivorship bias (no historical universe membership)

### B6 — Market ribbon & research navigation
- [x✓] B6-1 NEPSE ribbon
- [~] B6-2 Source/timestamp/stale display
- [x✓] B6-3 Research navigation to results

## 4. PART C — QUANT RESEARCH, VALUATION, VISUALIZATION (§7)

### C1–C2 — Pipeline & math standard
- [x✓] C1-1 Pipeline traced (source→API→frontend→chart)
- [x✓] C1-2 Independent oracles present for key calcs
- [~] C2-1 Math-standard docs per calculation

### C3 — Charts and graph types
- [x✓] C3-1 OHLC/candle invariants
- [x✓] C3-2 Line charts
- [x✓] C3-3 Area/fill bands (BB/Keltner/Donchian/Ichimoku)
- [x✓] C3-4 Histograms
- [~] C3-5 Scatter/pie/distribution graphs
- [x✓] C3-6 Graph geometry (axis/transform)
- [x✓] C3-7 Chart state preservation
- [~] C3-8 Financial graphs (P/E, P/B, returns, drawdown, allocations)

### C4 — DCF, valuation, ownership
- [x✓] C4-1 DCF engine (FCF projection, WACC, terminal value) — hand-computed test
- [x✓] C4-2 Reverse DCF / implied growth (bisection) — round-trip test
- [x✓] C4-3 Enterprise value / equity value — in DCF output
- [x✓] C4-4 Sensitivity analysis (WACC × terminal-growth grid) — TESTED-PASS
- [~] C4-5 Sector-specific valuation methods
- [!] C4-6 Ownership (promoter/public holding = 0 records) — BLOCKED

### C5 — Monte Carlo, statistics, portfolio optimization
- [x✓] C5-1 Monte Carlo (reproducible seeds, GBM + bootstrap) — TESTED-PASS
- [x✓] C5-2 Bootstrap/historical simulation — TESTED-PASS
- [x✓] C5-3 Statistical validation (deflated Sharpe; skew/kurtosis/trials) — TESTED-PASS
- [x✓] C5-4 Covariance/correlation — TESTED-PASS
- [x✓] C5-5 Min-variance / max-Sharpe / efficient frontier — TESTED-PASS (long-only, simplex projection)
- [x✓] C5-6 HRP (hierarchical risk parity) — TESTED-PASS
- [x✓] C5-7 Risk-of-ruin / losing-streak simulator — TESTED-PASS (monotone in risk)
- [x✓] C5-8 Market-shock stress test (beta-based) — TESTED-PASS
- [x✓] C5-9 Event study (CAR, next-session entry) — TESTED-PASS

### C6 — Breakouts, liquidity, MTF
- [x✓] C6-1 Breakout/consolidation criteria
- [~] C6-2 Pullback/retest depth
- [x✓] C6-3 Volume-confirmed breakouts
- [x✓] C6-4 MTF confluence + relative strength
- [!] C6-5 Floorsheet/order-flow (empty in dev)

### C7 — Industry research/reports
- [~] C7-1 Company/industry research projects
- [~] C7-2 Valuation summaries with inputs/assumptions
- [x✓] C7-3 No fabricated industry datasets

## 5. KIMI WORKSPACE (§9, §10)

### Sidebar / routes / landing
- [x✓] KIMI-1 Sidebar top-level "KIMI" section
- [x] KIMI-2 KIMI routes resolve; no dead entries
- [x] KIMI-3 Landing page with feature catalogue + data status
- [x✓] KIMI-4 Searchable feature catalogue — **Catalogues tab**, 124 scanners / 77 algorithms / 32 fundamental tools (233 tools, health OK)
- [x✓] KIMI-9 Every KIMI tab backed by a real engine (no placeholders): liquidity, forensics, factors, signals, monte carlo, valuation/DCF, portfolio (frontier/HRP/ruin/stress), research desk, data quality, reconciliation, snapshots, AI research, ask-the-data, corporate events — browser-verified, 0 "undefined" across all 17 tabs
- [x✓] KIMI-5 Shared information-panel component (ⓘ formula/params/tags/limits/data-needs)
- [x✓] KIMI-6 Loading/empty/error/blocked states
- [x] KIMI-7 Connect KIMI to existing navigation
- [x✓] KIMI-8 Catalogues tab runs real engines in-place (screen / backtest / analysis / fundamental) — browser-verified, 0 console errors

### NF-001..NF-030 (honest current status)
- [x~] NF-001 Broker/Floorsheet Intelligence — engine + import + API + CLI present, TESTED-PASS (74 tests); 0 rows ingested in dev (DATA-DEPENDENT, needs a supplied file/credentialed collector)
- [~] NF-002 Corporate-Action-Adjusted Total Return
- [~] NF-003 Sector-Specific Fundamental Metric Packs
- [x~] NF-004 Financial Reporting & Corporate Calendar — `megatool/corporate_events.py`, API `/api/corporate-events/*`, KIMI → Corporate Events; attested registry projected (21 actions) + typed notice import; dividend/bonus/AGM feed absent, TESTED-PASS (17 tests)
- [x✓] NF-005 Liquidity Drought & Unusual Activity — `run_liquidity_drought` + KIMI → Liquidity, TESTED-PASS
- [~] NF-006 Turnover Concentration & Market Breadth
- [x✓] NF-007 Financial Statement Forensics — `run_fundamental_forensics` + KIMI → Forensics, TESTED-PASS
- [x✓] NF-008 Cross-Sectional Factor Research — `run_factor_snapshot` + KIMI → Factors, TESTED-PASS
- [~] NF-009 Market Regime Detection (backend implemented)
- [~] NF-010 Portfolio Return & Risk Attribution
- [x✓] NF-011 Risk-of-Ruin & Losing-Streak Simulator — wired to KIMI → Portfolio, TESTED-PASS
- [x✓] NF-012 Portfolio Stress Testing — wired to KIMI → Portfolio, TESTED-PASS
- [x✓] NF-013 Data Quality & Provenance Dashboard — coverage explorer + store facts, browser-verified
- [x✓] NF-014 Calculation Snapshots & Reproducibility — `megatool/snapshots.py`, API `/api/snapshots*`, KIMI → Snapshots, TESTED-PASS (15 unit + browser)
- [x✓] NF-015 Evidence-Bound AI Research Desk — `megatool/research_desk.py`, API `/api/research-desk/*`, KIMI → AI Research, TESTED-PASS (15 unit + browser; explicit error when no provider)
- [x✓] NF-016 Natural-Language Query (read-only) — `megatool/nlquery.py`, API `/api/query/*`, KIMI → Ask the Data, TESTED-PASS (27 unit + browser)
- [x✓] NF-017 Signal-Outcome Tracker — `run_signal_outcomes` + KIMI → Signals, TESTED-PASS
- [x~] NF-018 Unified Alerts — on-demand rule engine + history + cooldown + API TESTED-PASS; one-shot `megatool alerts evaluate` CLI for an external scheduler; autonomous scheduler NOT IMPLEMENTED (needs an OS timer)
- [~] NF-019 Explainable Chart Layer
- [x~] NF-020 IPO/Rights/Allotment Tracker — `ipo`/`rights`/`allotment` are first-class types in the corporate-event calendar (import + coverage, starts empty and says so); no live feed exists, TESTED-PASS (17 tests, shared)
- [~] NF-021 Capital-Gains/Tax Ledger
- [~] NF-022 Strategy Robustness Lab (deflated Sharpe + walk-forward exist)
- [~] NF-023 Trading Cost & Capacity Lab
- [~] NF-024 Portfolio Ledger & Reconciliation
- [x~] NF-025 Point-in-Time Research Data — ingestion-time knowledge view (`query_symbol_as_of`) + coverage disclosure; publication-date archive NOT IMPLEMENTED (no data), TESTED-PASS
- [~] NF-026 Research Experiment Manager
- [~] NF-027 Benchmark & Performance Attribution
- [x~] NF-028 Financial Revision Monitor — going-forward old→new logging in `import_records` + `revision_monitor`; pre-existing history unrecoverable and stated, TESTED-PASS
- [~] NF-029 Research-to-Decision Journal
- [x✓] NF-030 Data Coverage & Feasibility Explorer — `run_coverage_explorer` + KIMI → Research Desk/Data Quality, TESTED-PASS

### §6 additional
- [~] 6.1 Corporate-action-aware technical analysis
- [x✓] 6.2 Data source reconciliation — `megatool/reconcile.py`, API `/api/reconciliation/*`, KIMI → Reconciliation; findings on demand, human-only resolutions, TESTED-PASS
- [x✓] 6.3 Methodology registry — KIMI → Research Desk
- [x✓] 6.4 Feature status registry — KIMI → Overview
- [x✓] 6.5 Universal feature details (ⓘ for all 233 catalogue tools) — browser-verified entry-by-entry, 233/233, see `CATALOGUE_BROWSER_AUDIT.md`
- [x✓] 6.6 Connect KIMI to existing workflows (reuses /api/screen, /api/backtest, /api/analysis/run, /api/fundamental/run)

## 6. RESEARCH AUDIT (§10)
- [~] RES-1 Sources: **83 entries logged** in `RESEARCH_SOURCES.md` (50 registered + 5 endpoints + 12 re-verified + 17 newly surfaced + 11 prior); target ~60 met at entry level (overlaps noted honestly)
- [~] RES-2 Reddit: **15 entries** (1 subreddit + 14 threads/wiki); target ~20 NOT met — shortfall stated

## 7. TESTING & EVIDENCE (§9)
- [x✓] T-1 `node --check web/static/app.js`
- [x✓] T-2 Full suite baseline (2709 collected)
- [x✓] T-3 Catalogue tests (`tests/test_catalog.py`) — **52 tests**, exit 0
- [x✓] T-4 Algorithm catalogue tests (58 strategies leak-free in `test_backtest.py`)
- [x✓] T-5 Fundamental catalogue tests — TESTED-PASS
- [x✓] T-6 KIMI backend tests + API endpoints (incl. store-backed analysis via provider) — TESTED-PASS
- [x✓] T-7 Browser: KIMI 17 tabs + all 34 views, 0 "undefined", 0 console errors
- [x✓] T-8 Full suite after changes — **see `POST_IMPLEMENTATION_COMPLETION_REPORT.md` for the final counts (0 failed, 0 errors, 8 skipped opt-in browser tests, exit 0)**
- [x✓] T-9 Browser: full catalogue walk — **all 233 entries opened via ⓘ, verified entry-by-entry** (see `CATALOGUE_BROWSER_AUDIT.md`)

## 8. REFERENCE-BASED COMPLETENESS & VISUALISATION PASS (P1–P4)

Reference material: `NEPSE_Mega_Tool_106_Screenshot_Analysis.md` (106 records, read in
full) + the 106 readable PNGs in `PHOTOS/` (the same images compiled into the 4.9 MB
PDF, which the model cannot read as text). Evidence labels follow the same honest
scheme used elsewhere in this checklist.

### P1 — reference visualisations (most important)
- [x✓] Reference inventory + feature-gap matrix built from the MD and ~21 screenshots inspected visually — see `FINAL_REFERENCE_IMPLEMENTATION_AND_REMAINING_GAPS_REPORT.md` §B/§C
- [x✓] `web/static/viz.js` — dependency-free SVG primitives (`line`, `bars`, `donut`, `gauge`, `sparkline`, `scatter`, `empty`), theme-aware, accessible (`role="img"` + aria-label + `<title>`), hover readout, resize-aware. TESTED-PASS (browser)
- [x✓] Overview: market **barometer gauge** (deterministic transform of advance-share and % above 50-day MA; labelled as computed, not an external feed). TESTED-PASS
- [x✓] Overview: **sector performance bars** (avg % change per sector, signed colours, click → Sector Explorer). TESTED-PASS
- [x✓] Overview: **sector turnover donut** (share of session turnover; empty sectors omitted). TESTED-PASS
- [x✓] Overview: **fundamental map scatter** (P/E × P/B, coloured by sector, click → chart). TESTED-PASS
- [x✓] Breadth view: **indicator chart** with 7 selectable metrics (net new highs, A/D ratio, A/D line, A/D volume line, Arms index/TRIN, % above SMA 50, % above SMA 200), zero line, area fill, hover readout and the endpoint's own definition echoed beneath. TESTED-PASS
- [x✓] Seasonality view: **month-of-year**, **weekday** and **quarter** bar charts (signed colours, count-weighted mean line; quarter compounded from month returns and documented). TESTED-PASS
- [x✓] `styles.css` — viz host/legend/tooltip/donut/gauge/empty-state + compact indicator-row styles
- [x✓] The previously-listed "remaining reference visuals" are **built and browser-verified in §9 below** (table sparklines, PE/PB multi-pane historical chart, Support/Resistance + risk-reward table, dividend analysis, sector-rotation workspace, valuation-model suite, backtest-vs-Buy&Hold comparison + returns histogram). See `FINAL_REFERENCE_IMPLEMENTATION_AND_REMAINING_GAPS_REPORT.md` §C1.

### P2 — the seven actionable tasks
- [x✓] 2.1 python-dotenv CVE upgrade — RESOLVED: installed and locked at **1.2.4** (above the recommended 1.2.2); `REMAINING_BLOCKERS.md` §11 and `BLOCKED_FEATURES_AUDIT.md` updated (they were stale)
- [x✓] 2.2 NF-001 floorsheet import — implemented + tested (`tests/test_floorsheet.py`, 20+ cases on synthetic input); still needs a real external document to populate (documented)
- [x~] 2.3 NF-018 autonomous scheduling — on-demand engine + one-shot CLI done and TESTED-PASS; the timer itself needs an OS-level scheduler (documented blocker, not a coding task)
- [x✓] 2.4 NF-025 point-in-time data — ingestion-time view + explicit coverage disclosure; TESTED-PASS (`tests/test_fundamentals_pit_revisions.py`)
- [x✓] 2.5 NF-028 revision monitor — going-forward old→new logging; pre-existing history is unrecoverable and stated; TESTED-PASS
- [x~] 2.6 other actionable gaps — remaining blockers re-checked against code and docs; no unblockable coding gap left open
- [x✓] 2.7 regression — full suite **2,933 collected / 0 failed / 0 errors / 14 skipped (opt-in browser) / exit 0** this session

### P3 — scanner & algorithm information panels
- [x✓] Reusable `toolInfoHtml()` model — 11 implementation-derived sections (purpose, implemented rule, default parameters, required data, timeframe, output, interpretation, execution path, keywords, limitations, stable id); derived lines labelled as derived, never fabricated per entry. TESTED-PASS
- [x✓] Inline ⓘ in the KIMI catalogue now uses the same renderer (scanners ×124, algorithms ×77, fundamentals ×32)
- [x✓] New floating `#tool-info` modal; ⓘ buttons added beside the screener **preset** selector and the backtest **strategy** selector (map to the real catalogue entry via `run.strategy` / preset key)
- [x✓] Opening the ⓘ does not change the selection or run anything; missing metadata and very long text degrade gracefully. TESTED-PASS

### P4 — technical-indicator selector cleanup
- [x✓] Compact row is icon + name + ⓘ + essential actions (Hide / ⚙ / ✕); parameters, Apply/Reset/Rename, Duplicate and draw-order moved behind the ⚙ toggle (`.ii-extra`). TESTED-PASS
- [x✓] All indicators, instances, parameters, overlays, calculations and the information pane preserved (category text moved into the expanded panel)
- [x✓] Long/short names truncate cleanly; multiple instances unaffected

### Verification artifacts
- [x✓] `tests/test_ui_viz_assets.py` (6 static wiring guards) — part of the normal suite
- [x✓] `tests/test_browser_viz_toolinfo.py` (6 opt-in browser cases) — render checks, tool-info content + graceful degradation, compact-row behaviour
- [x✓] `node --check web/static/app.js` and `node --check web/static/viz.js` clean; `ruff check` + `ruff format --check` clean on the new test files

---

## 9. SASTO SHARE WORKSPACE + P2/P3/P4 RE-VERIFICATION PASS

### 9.1 New top-level workspace (Sasto Share)
- [x✓] New sidebar group **Sasto Share**, immediately below KIMI Research — 7 nav items that all open a working destination: Market Pulse, Movers & Sparklines, Valuation, Risk & Volatility, Sector Rotation, Dividends, Strategy vs Buy & Hold. No dead links, no empty placeholders, no duplicates. TESTED-PASS (browser, all 7 open, 0 console errors)
- [x✓] `SS_TAB_TO_NAV` / `SS_NAV_TO_TAB` + a single `ssSubTab()` keep the sidebar item and the in-view sub-tab row provably in sync
- [!] Honest limitation: the S-A-S-T-O / S-H-A-R-E wordplay would be 10 nav items; there are 7, because every nav item must open a real destination. Padding to 10 would create dead links.

### 9.2 P1 features (all from stored data; nothing fabricated)
- [x✓] (A) Table **sparklines** — per-row inline SVG from 20 stored closes; labelled "stored daily closes, not a live tick feed"
- [x✓] (B) **52-week range bar** — low/high + position marker; a flat window states that a position is undefined
- [x✓] (C) **Historical P/E + P/B multi-pane** chart (price / P/E / P/B) built from bars + the fundamentals period series aligned at `period_end`; publication-date limitation disclosed
- [x✓] (D) **Support/Resistance + risk-reward**, daily **and** weekly, from `swing_workbench`; a "mixed" structure is reported as mixed, not invented
- [x✓] (E) **Volatility projection** cone (1σ/2σ, 4 horizons) + realised vol + 3-month beta against the stored NEPSE index series
- [x✓] (F) **Sector rotation workspace** — equal-weight derived sector index, 1w/1m/3m/6m returns, RSI(14), MACD(12,26,9), 2×2 regime label, ranking table; caveat states it is not the exchange's index
- [x✓] (G) **Dividend analysis** — yield/payout/safety + scenario calculator; renders an explicit blocker (no `dps`, 0 corporate-event rows) rather than a fabricated yield
- [x✓] (H) **Valuation models** — Graham number, margin of safety, Gordon growth, PEG, each with formula/value/inputs; unavailable models name the missing input
- [x✓] (I) **Backtest vs Buy & Hold** — cumulative return, drawdown, return histogram, final value, built from the real `POST /api/backtest` payload
- [x✓] (J) **Fundamental-map market-cap size encoding** — **opt-in** checkbox; cap is derived (`paid_up_capital / 100 × last close`) and labelled; symbols without a cap draw at minimum radius with the count disclosed
- [x✓] (K) **Market Pulse** — barometer, sentiment (% above 50/200-day MA), golden cross, per-sector MA participation, P/E / P/B / price distribution ranges by sector; every ratio prints its denominator

### 9.3 P2 — chart-analysis rendering defects (found by reproduction, fixed at source)
- [x✓] Elliott/harmonic **layer toggles now detect AND draw** (`runElliott()` + `drawElliottCandidate(symbol, 0)` / `drawHarmonicCandidate(0)`) — previously the panel filled and the chart stayed empty
- [x✓] Analysis window defaults to **"Same as chart range"** so a drawn candidate is on-screen; `revealChartDates()` scrolls only the time scale (never reloads bars, never rescales price)
- [x✓] Range-change viewport gate: a logical window is restored only when symbol + timeframe + requested `#range` are unchanged; otherwise `fitContent()`
- [x✓] `/api/bars/{symbol}/elliott` now attaches per-candidate `pivots` (date/kind/price/confirmed_date) + `renderable` + `window` + `minimum` + `message`; `/api/bars/{symbol}/harmonic` attaches `date` per X/A/B/C/D point + `pivots` + `window` + `minimum` + `renderable`
- [x✓] Layer badges distinguish detection from ink: `N found · drawn` / `N found · M drawn` / `N found · not drawn`; verified for all 7 controls at 750 bars (sr 73·8, fib 8, profile 3, candles 200·15, patterns 6, elliott 2, harmonic 1)
- [x✓] Rapid successive toggles (150 ms) persist every flag — no toggle lost
- [x✓] Display-mode presets verifiably change the ink (standard 15 / minimal 0 / detailed 40 / research all markers); the "minimal" preset no longer leaves the candle-cap selector reading a number it does not draw (a real `none (minimal)` option was added and the handler no longer coerces `0` to `15`)
- [x✓] Minimum-bar requirements established and explained instead of silently failing: Elliott needs 3/5 confirmed swings, harmonic needs 5; a 30-bar API window returns `INSUFFICIENT_EVIDENCE` with the exact pivot deficit
- [x✓] Fibonacci verified across ~30 / 60 / 120 / 250 / 750 bars — 5 levels at every range; anchor provenance printed
- [x✓] Classical candlestick patterns: 0 @30, 2 @60, 6 @120+ (marker cap applies on top and is reported)

### 9.4 P3 — information controls (ⓘ)
- [x✓] All 31 screener presets and all 57 backtest strategies map to a catalogue id; the ⓘ opens the correct implementation-derived title **without** changing the selection or running anything; Escape closes
- [x✓] Catalogue counts confirmed 124 scanners / 77 algorithms / 32 fundamentals
- [x✓] KIMI catalogue ⓘ now opens the shared floating `#tool-info` modal (the inline panel sat 6,214 px below the button)
- [x✓] Sparse tool object and a 2,000-character description render without throwing; buttons carry `type="button"` + aria-labels

### 9.5 P4/P5 — re-verification (found and fixed two real defects)
- [x✓] **DEFECT FIXED:** the KIMI **Breadth** tab rendered "Nothing to show" while 5,200 real sessions were available — it read a non-existent `history` key. Now renders 10 sessions with Advancers / Decliners / Unchanged / % above SMA 50 / A/D line and the universe definition
- [x✓] **DEFECT FIXED:** the historical **P/E** pane was dominated by a near-zero EPS period (a 6,674× spike). The outlier is now flagged (`suspect_periods`) with its period label, the axis is capped with a gap (never a clamp) and a stated count, and a "full range" toggle shows everything
- [x✓] Growth rate now uses **annual** periods only and names which condition failed (too few periods vs a non-positive base)
- [x✓] **DEFECT FIXED in the module:** a sector with one short-history member was dropped entirely; members without the 60-bar minimum are now excluded individually and the counts are reported
- [x✓] Overview gauge / sector bars / donut / fund-map each render 1 SVG (14 sector bars); breadth (after Load) 1 SVG / 5,200 sessions with a working metric switch; seasonality 3 SVGs / 12 month bars / 12 table rows
- [x✓] All 18 KIMI tabs exercised (17 feature tabs + overview), including Run buttons; 0 console errors

### 9.6 Tests
- [x✓] Full suite **2,970 collected / 0 failed / 0 errors / 14 skipped / exit 0** (previous baseline 2,933; delta +37 = `tests/test_sastoshare.py`)
- [x✓] `tests/test_sastoshare.py` — **37 passed** (synthetic + offline; the live securities feed behind the sector map is monkeypatched)
- [x✓] Opt-in browser modules `MEGATOOL_BROWSER_TESTS=1` — **14 passed**, exit 0
- [x✓] `node --check web/static/app.js` clean; `ruff check` + `ruff format` clean on the files touched
- [x✓] Non-Sasto-Share browser workflow checks (7 layer toggles, KIMI tabs, ⓘ controls, overview/breadth/seasonality) done by hand in the browser, because a passing unit suite did not catch either §9.5 defect

### 9.7 Still blocked / not done (honest)
- [!] Intraday sentiment / live sparklines / live sector gain — live NEPSE API 401 with no intraday feed; stored data is daily only
- [!] Dividend **history** — no `dps` field and 0 corporate-event rows in dev; the calculator and the blocker are implemented, the history is not
- [!] Quant model portfolios, Dupont / F-Score / G-Score / Z-Score, per-symbol news in the chart panel — would need fields or constituent lists the stores do not hold; not fabricated
- [!] No commit / push / deploy; production `:8710` untouched; all work on dev `:10000`

## 10. PRAVAHA BRAND TRANSFORMATION & FRONTEND REDESIGN

### 10.1 Phase 0 — discovery
- [x✓] `PRAVAHA.pdf` (14 pages) extracted with PyMuPDF → palette, typography, component rules, copy, phases
- [x✓] Supplied logo located: `logoFimage.png` (1254×1254, **no alpha**, solid gradient background) — left intact
- [x✓] Architecture confirmed: single-page app, no build step, no framework; `index.html` + `styles.css` + `app.js` + `viz.js` + `kronos_ui.js` + `indicator_info.js`; vendored Lightweight Charts; FastAPI `StaticFiles` mount at `/`
- [x✓] Baseline: 40 nav destinations, 25 view sections, 11 CSS custom properties, 45 unique hexes in `styles.css`, 18 in `app.js`
- [x✓] Baseline screenshots captured → `docs/screenshots/pravaha-before/` (11 views)

### 10.2 Phase 1 — brand foundation
- [x✓] Central token system in `:root` — 11 brand colours + derived surfaces/states/shadows/gradients + typography + 8-px spacing + radii + motion
- [x✓] Legacy aliases (`--bg … --info`) re-pointed at the new tokens, so **no existing selector was rewritten**
- [x✓] Logo variants derived (LANCZOS, no stretch/recolour): `pravaha-symbol{,-128,-64}.png`, `pravaha-appicon-192.png`, `pravaha-logo.png`, `pravaha-logo-full.png`
- [x✓] Browser title, `application-name`, `theme-color`, description, favicon (symbol crop, **not** the square lockup), `apple-touch-icon`
- [x✓] Sidebar lockup (mark + PRAVAHA + "NEPSE Analytics Platform") and footer brand line + tagline
- [x✓] App still starts; `/` → 200

### 10.3 Phase 2 — shared components
- [x✓] Brand layer re-skins buttons, inputs, tables, tabs, pills, chips, modals, drawers, toasts, tooltips, empty/error states, scrollbars, focus rings
- [x✓] `.data-status` chips for LIVE / DELAYED / STALE / HISTORICAL / ESTIMATED / SIMULATED / UNAVAILABLE
- [x✓] `prefers-reduced-motion` respected; `:focus-visible` rings in cyan
- [x✓] Obsolete `.logo` / `.side-brand .logo` (old "MT" chip) removed after grep-verifying no HTML/JS reference

### 10.4 Phases 3–4 — workspaces and remaining modules
- [x✓] All 40 destinations / 25 sections inherit the system; overview, charting, scanner, Quant Lab, Strategy Lab, Research Desk, fundamentals, portfolio, market intelligence, floorsheet, journal, PDF journal, data, KIMI (18 tabs), Sasto Share (7 panels) re-skinned
- [x✓] Chart colours consolidated into a single `PRAVAHA` palette object in `app.js`; `viz.js` reads the CSS custom properties at runtime so charts and chrome cannot drift
- [x✓] Legacy static dashboards (`/dashboard.html`, `/market_dashboard.html`, `/research.html`) were reachable and showed hard-coded unverified figures → replaced with branded redirect stubs (routes still 200, fabricated numbers gone)

### 10.5 Phase 5 — responsiveness & accessibility
- [x✓] ≤900 px: the app's original single-row horizontally scrollable nav strip is **preserved** (my first media query wrongly wrapped it — reverted to re-skin-only)
- [x✓] Verified at 760×900: `flex-direction: row`, `overflow-x: auto`, 66 px tall, brand tag hidden
- [x✓] Focus rings, disabled states, reduced-motion, keyboard-navigable controls

### 10.6 Phase 6 — functional regression
- [x✓] Full suite **2,970 collected / 0 failed / 0 errors / 14 skipped / exit 0**
- [x✓] Opt-in browser modules **14 passed**
- [x✓] `node --check` clean on all four JS files
- [x✓] Nav sweep in a real browser: **40/40 destinations, 0 JS errors, 0 `showView` failures**
- [x✓] Console over all captured screenshots: **0 errors, 0 warnings**
- [x✓] Real NABIL daily chart renders with the new palette (candles, volume, levels, OHLCV legend)

### 10.7 Phase 7 — audits
- [x✓] **Audit A (brand/visual):** PRAVAHA logo in nav; no user-facing "Mega Tool" string remains (only internal identifiers — `megatool-api-base`, `MEGATOOL_API_BASE`, `megatool_friend_token`, `megatool.*` module paths, real CLI commands); consistent tokens everywhere; no broken images; no overflow
- [x✓] **Audit B (functionality/data integrity):** routes work, controls work, charts work, API requests unchanged, data status still honest (DELAYED / historical), no new console errors, tests pass
- [x✓] One assertion updated and disclosed: `tests/test_api.py::test_ui_is_served` pinned `"Mega Tool"` → now asserts `"PRAVAHA"` present and `"Mega Tool"` absent

### 10.8 Honest limitations / not done
- [!] Fonts degrade to system families unless Space Grotesk / Inter / JetBrains Mono are installed — no external font dependency was added (offline-first)
- [!] The supplied logo has no transparency; a flood-filled transparent variant was produced and **rejected** (visible white fringe). The mark is presented in a rounded container instead
- [!] No login / auth / About / loading screens exist in this application — those brand slots are N/A
- [!] `LIVE` status chip is styled but unproven (no live feed in this environment)
- [!] 18 pre-existing ruff findings in `megatool/api.py` (market-intelligence routes) left untouched — unrelated churn
- [!] No commit / push / deploy; production `:8710` untouched (PID 26596 unchanged); all work on dev `:10000`

### 10.9 Evidence
- [x✓] `docs/screenshots/pravaha-before/` (10) and `docs/screenshots/pravaha-after/` (15, incl. `charts-loaded.png`, `narrow-overview.png`, `legacy-redirect-stub.png`)
- [x✓] `PRAVAHA_REBRAND_REPORT.md` — full A–M report
