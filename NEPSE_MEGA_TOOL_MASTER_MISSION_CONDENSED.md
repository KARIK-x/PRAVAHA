# NEPSE MEGA TOOL — MASTER IMPLEMENTATION & VERIFICATION MISSION
## Consolidated Session 31 + Session 32 + Session 34 + KIMI Feature Suite

**Project:** `/Users/ashim/Downloads/AI trading NEPSE`  
**Mode:** Autonomous inspection, implementation, integration, testing, checkpointing, and evidence-based reporting.  
**Core rule:** Every requirement below must be tracked individually. Do not silently skip anything, substitute a smaller task, or claim completion without evidence.

---

# 1. MISSION AND ACCEPTANCE STANDARD

Continue the existing NEPSE Mega Tool / AI Trading Nipsy project. Do **not** rebuild it. Inspect the actual repository, previous reports, implementation, data, tests, and current Git state; verify prior-session claims; then repair and implement the highest-value unfinished requirements across:

1. Charting, indicators, drawings, analysis layers, and visualization correctness.
2. Scanners, algorithms, strategies, and their searchable catalogues.
3. Fundamental analysis, valuation, quantitative research, portfolio tools, and backtesting.
4. A new top-level **KIMI** workspace containing the KIMI research feature suite NF-001–NF-030.
5. Data quality, provenance, corporate actions, point-in-time research, snapshots, methodology, and feature-status foundations.
6. Integration, navigation, persistence, accessibility, browser behavior, regression testing, and source research.

A registry entry, button, route, mock, passing isolated unit test, or rendered graph does not prove that a feature works. Fully verified means all applicable calculation, data, integration, UI/browser, persistence, and regression checks have passed. Keep the overall project marked **INCOMPLETE** while any mandatory requirement remains incomplete, untested, or blocked.

## Prior claims to re-verify, not assume
Session 30 reportedly had 2,701 passed, 0 failed, 8 skipped; 92 indicators (62 numerical reference-tested, 28 invariants-only, 2 sparse); five quantitative capabilities needing UI wiring; approximately 283 changed paths; production port 8710 and development port 10000 returning HTTP 200. Inspect reports, exact indicator identities, tests, code, Git diffs, and actual services to verify these claims. Do not damage or reset the existing changed work.

---

# 2. SAFETY, PRESERVATION, AND BASELINE

Before edits:

- Read `SESSION_30_COMPLETION_REPORT.md`, all available Session 31/32/33/34 reports, checkpoints, mission checklists, architecture/project documentation, test instructions, feature inventories, and relevant research files.
- Inspect repository structure, recent commits, `git status`, staged/unstaged changes, diffs, frontend/backend entry points, APIs, database/schema/migrations, data providers, caches, background jobs, charting, persistence, and test infrastructure.
- Inspect the real implementation behind every important previous claim.
- Establish and record a baseline test run: exact command, counts, skipped tests, warnings, failures, exit status, and log path.
- Keep development separate from production. Safely recheck port 8710 and development port 10000 if appropriate, without changing either service.

**Never:** rebuild from scratch; reset Git; discard/revert the ~283 changed paths without explicit authorization; delete user data, layouts, watchlists, research, drawings, templates, or history; drop/reset databases; make unsafe/destructive migrations; commit, push, deploy, or modify production; change/restart production port 8710; buy APIs or paid infrastructure; start GPU training without approval; fabricate real market data; weaken tests; hide failures; disable TLS verification; bypass authentication/access controls; expose secrets; or introduce unauthorized scraping/integrations.

Use conservative, reversible changes. Inspect migration practices before any schema change. If an operation requires authorization or could be destructive, stop before that operation, document the blocker, and continue with independent safe work.

---

# 3. PERMANENT TRACKING FILES

Create and continuously update the following in the project’s established documentation structure, preserving the specified names and contents.

## Session 31
- `SESSION_31_GAP_AUDIT.md`
- `SESSION_31_CHECKPOINT.md`
- `SESSION_31_COMPLETION_REPORT.md`

The gap audit must compare the original Part A, Part B, and Part C requirements with actual source code, tests, and UI. For every requirement record ID, requested behavior, file/module/API/UI, implementation status, test status, exact evidence/command, limitations, and next action. Use: `IMPLEMENTED`, `TESTED-PASS`, `TESTED-FAIL`, `PARTIAL`, `NOT-IMPLEMENTED`, `BLOCKED`, `NOT-TESTED`. Never mark pass without an executed relevant test.

## Session 32
- `SESSION_32_CORRECTNESS_INVENTORY.md`
- `SESSION_32_TEST_MATRIX.md`
- `SESSION_32_CHECKPOINT.md`
- `SESSION_32_FINAL_REPORT.md`

Inventory every relevant component and record ID, source file/function, formula/algorithm, inputs/units/outputs, data source, assumptions, expected behavior, independent oracle, numerical/property/edge/API/browser tests, status, evidence, limitations, and remaining work.

## Session 34
- `SESSION_34_REQUIREMENTS_REGISTER.md`
- `SESSION_34_IMPLEMENTATION_CHECKLIST.md`
- `SESSION_34_TEST_EVIDENCE.md`
- `SESSION_34_CHECKPOINT.md`
- `SESSION_34_COMPLETION_REPORT.md`

The checklist is the controlling record. Every explicit requirement must have an individual ID and checkbox, exact acceptance criteria, implementation evidence, test command/result, browser evidence where applicable, remaining work, and last verification time. Use `[ ] NOT STARTED`, `[ ] IN PROGRESS`, `[ ] IMPLEMENTED`, `[ ] TESTED`, `[ ] VERIFIED`, `[ ] BLOCKED`. A checked/verified item requires evidence; explain when browser testing is not applicable.

## KIMI
Create `KIMI_IMPLEMENTATION/` containing:
- `KIMI_REQUIREMENTS_REGISTER.md`
- `KIMI_FEATURE_INVENTORY.md`
- `KIMI_IMPLEMENTATION_CHECKLIST.md`
- `KIMI_DATA_DEPENDENCIES.md`
- `KIMI_TEST_EVIDENCE.md`
- `KIMI_CHECKPOINT.md`
- `KIMI_COMPLETION_REPORT.md`

Use the existing documentation convention if better, but preserve all required content. Track NF-001–NF-030 separately, plus sidebar, landing page, routing, shared catalogue, search, information panels, data foundations, integration, accessibility, security, tests, documentation, and regression. KIMI statuses: `NOT STARTED`, `IN PROGRESS`, `IMPLEMENTED`, `TESTED-PASS`, `TESTED-FAIL`, `BLOCKED`, `NOT FEASIBLE WITH CURRENT DATA`, `NOT RECOMMENDED`, `VERIFIED`.

## Checkpoint discipline
After each meaningful implementation batch, update relevant registers, checklist, evidence, and checkpoint. Record current phase/requirement ID, completed/open items, files changed, tests/commands/results/exit codes/logs, failures, known regression risks, data blockers, next exact action, and safety constraints. Do not wait until the end. If runtime/context/provider budget is nearing its limit, save a detailed checkpoint and continue if possible. Do not claim indefinite execution.

---

# 4. CLASSIFY EVERY REQUIREMENT BEFORE IMPLEMENTING

For each feature/tool, establish evidence-based status:
- Exists and verified.
- Exists but incomplete.
- UI-only/disconnected.
- Broken.
- Partially implemented and needing extension.
- Genuinely new.
- Blocked by missing/insufficient data.
- Not feasible under current constraints.
- Not recommended in proposed form.

Record code locations, real data dependencies, tests, and evidence. A proposal or previous report is not proof of implementation. Reuse working features; extend partial ones; repair broken ones; connect UI-only features; and implement feasible foundations for data-blocked features. A data blocker must not stop unrelated work.

---

# 5. PART A — CHARTING AND INDICATORS

## A1. Verify all 92 indicators individually
Inspect exact identities of the reported 28 invariant-only and 2 sparse indicators. For each indicator verify:
- Formula against implementation; input series; parameters/defaults/ranges; initialization, smoothing convention, warm-up period, and numerical precision.
- Missing/invalid data, NaNs, gaps, flat markets, short histories, zero denominators, numerical stability, and output range where mathematically valid.
- Timestamp alignment; no lookahead/future leakage; output schema; settings affect calculation; overlay/pane placement and scale.
- Every line, band boundary, histogram, marker, fill, displacement, legend, tooltip, axis, and visible value.
- Search discovery; correct info panel/formula; add, settings, visibility, remove, duplicate instances, symbol/timeframe changes, missing-data messaging, persistence, and viewport preservation.
- Multiple instances do not overwrite each other; adding/removing does not reset zoom/scroll, drawings, selected symbol, or timeframe.
- Volume-dependent indicators never fabricate volume or treat missing volume as genuine zero.

Prefer independent hand-calculated fixtures, trusted references, separately derived calculations, or differential tests. Do not use production output as its own oracle, duplicate meaningless tests, invent reference values, or hide convention differences. Document smoothing/initialization conventions and suitable absolute/relative tolerances. If no trustworthy oracle exists, retain PARTIAL/NOT-TESTED and explain why. Aim for independent numerical tests of all 92 where feasible, not just invariants.

## A2. Browser rendering of all 92
For each item, verify search → info panel → add → real line/band/histogram/markers/pane → legend/name/parameters → settings → visibility → removal of all owned objects → duplicate behavior → symbol/timeframe changes without stale data → honest missing-data state → viewport preservation. Use existing browser automation and sensible deterministic batches. Keep per-indicator evidence; do not claim all 92 tested after sampling a few.

## A3. Quick Layers
Audit SMA 20/50, EMA 20, Bollinger Bands, Volume, RSI panel, Swing Analysis, close-based pivots, and every other registered preset. Test observable effect, correct layer/pane, active highlight, toggle-off removes only its own objects, per-symbol persistence, template/layout restoration, viewport preservation, and scoped clearing. Fix root causes.

## A4. Analysis layers and patterns
Audit and repair Elliott Wave, classical chart patterns, Gartley/Bat/Butterfly/Crab harmonic patterns where implemented, Fibonacci retracement/extensions, trend context, swing analysis, support/resistance, candlestick patterns, stop/risk visualizations, and all other analysis layers.
- Every control must produce a visible understandable result or explicit no-result/blocker explanation.
- Elliott Wave: validate candidate generation; render valid labels/geometry; explain alternatives, invalidation, confidence limits; candidates are not forecasts; preserve viewport; clear only owned objects.
- Harmonics: validate ratios/tolerances; draw pivots/labels; show measured ratios/invalidation; never show failed patterns.
- Chart patterns: Select All/None, descriptions/tooltips, fixture validation, bounds/invalidation where supported, no lookahead.
- Fibonacci and all chart actions: preserve viewport. No automatic `fitContent`, reset visible range, remount, or zoom changes just because an analysis was added. Explicit zoom-to-analysis is allowed only when requested.

## A5. Chart object manager and cryptic labels
Trace the actual owner of `BO`, `DT`, `INV`, `355`, `372`, `322`, unidentified blue lines, duplicates, stale/orphaned objects, and every other unexplained label/line. Do not guess or remove legitimate analysis/user drawings. Object manager must list drawings, indicators, and automatic analysis separately; use clear names/types; support visibility/settings/removal; show parameters/owner where possible; synchronize manager/chart selection; remove cryptic accidental labels; and scope clearing without deleting saved app data.

## A6. Drawing and chart UX
Verify coordinate conversion, hit testing, selection, eraser, Delete/Backspace, pitchfork geometry, tool selection/active state, Clear location/scope/confirmation, undo/redo where supported, expanded-chart behavior, and viewport preservation.

## A7. Multi-symbol comparison
Verify up to four symbols: visible series, relative-performance mode, overlay/separate synchronized panels if advertised, symbol-specific fetching/timeframes, missing data, primary-symbol swap persistence, colors/legends/scales/labels, removing only the selected series, and reload persistence where promised.

## A8. Wire five quantitative capabilities into existing UI
- Rolling beta.
- Volatility percentile.
- Multi-timeframe confluence.
- Technical rating.
- Support/resistance strength score.

Each needs a discoverable existing-screen entry point, suitable input/parameter controls, formula/data requirements, visible result, correct loading/error/missing-data states, calculation and UI tests. Integrate into existing workflows; do not create five disconnected demo pages.

## A9. Fundamentals graphs and corporate actions
Recheck P/E/P/B graph fixes: bar bounds, axes/units, ordered dates, invalid/missing values, period comparison, and correspondence to stored data. Inspect the real price model and corporate-action support. Do not fabricate adjusted prices. If adjustment data is missing, label raw/unadjusted prices and prevent misleading adjusted-return claims.

## A10. APIs, refresh, and freshness
Verify real data sources/endpoints/modules, update mechanisms, configured intervals, cache, last successful update, market observation timestamp, stale-data behavior, retry/error behavior, and whether refresh is manual, scheduled, or external. Verify prior claims of no crypto/Uniswap integration, manual/on-demand refresh, and no scheduler; do not add crypto. Add a safe scheduler only if the app/source genuinely requires it and it can be tested locally without production changes. Never call historical/file data “live”.

## A11. Settings, import/export, search, persistence
Test actual settings effects; visible favorites; search/recent history; valid settings/chart-state import/export round trips; templates; per-symbol isolation; malformed-import safety; accurate clear scope; preservation of existing layouts/watchlists/templates.

---

# 6. PART B — SCANNERS, ALGORITHMS, STRATEGIES

## B1. Inventory
Inspect every existing scanner and algorithm. Inventory name/ID, purpose, formula/rules, inputs/defaults, data needs, output schema, implementation module, tests, UI entry, persistence, and limitations. Do not count aliases, cosmetic variants, or empty registrations as separate tools.

## B2. Searchable scanner catalogue
Target approximately 100–150 distinct useful scanners only if real implementation/data support it; do not pad counts. Every scanner needs metadata, name/abbreviation/keyword search, category filters, sorting, info panel, configurable parameters, real execution, meaningful result columns, loading/empty/stale/error states, persistence/recent/favorites where supported, and fixture tests. Search should naturally find synonyms (e.g. cash flow, cheap stocks, volume spike, breakout, liquid stocks, high quality) from actual metadata rather than hard-coded examples. Large lists must scroll/page/virtualize correctly.

Categories to audit/implement where data supports them:
- Price/return: daily/weekly/monthly/multi-period returns, gainers/losers, gaps, acceleration, relative strength, highs/lows, moving-average distance, expansion/contraction, range anomalies.
- Trend/momentum: MA alignment/crossovers, trend strength, RSI/MACD/Stochastic conditions, acceleration, multi-timeframe agreement, reversals, exhaustion.
- Volatility: historical-volatility percentile, ATR expansion, contraction, Bollinger compression, range expansion, volatility breakout/anomaly, large candle ranges.
- Volume/turnover/liquidity: spikes, price-volume confirmation/divergence, relative volume, concentration, contraction, unusual turnover, liquidity thresholds, volume quality.
- Breakout/pattern: resistance/support break, consolidation breakout, post-breakout pullback/retest, channels, trendline breaks, range compression, classical patterns, candlesticks.
- Fundamentals: P/E/P/B, yield, revenue/earnings growth, margins, ROE/ROA, debt, coverage, cash-flow quality, financial quality, sector-relative valuation, improvement/deterioration.
- Risk/liquidity: volatility, drawdown, beta, turnover constraints, liquidity-adjusted risk, gap risk, concentration, unstable prices, risk/reward, data-insufficiency.
- Market/sector: relative strength, breadth divergence, leadership changes, cross-sectional momentum, participation, sector anomalies, market-wide activity.
- Events/corporate actions only with reliable source data: dividends, book closure, bonus, rights, financial reports, events, post-event performance.
- Advanced quant where justified: factors, regimes, rolling-beta changes, correlation anomalies, outliers, change points, relative value, residual momentum, factor divergence, historical-event similarity.

Every scanner must have explicit criteria, actual execution and results. Never use fake/static output or claim unsupported data is available.

## B3. Searchable algorithm catalogue
Target approximately 70–150 genuine distinct algorithms where feasible, without aliases/count inflation. Distinguish indicators, scanners, signal-generation algorithms, strategies, portfolio algorithms, statistical tools, research models, and backtesting tools. Each algorithm needs stable ID, name, description, formula/rules, parameters/ranges, inputs/data, execution code, output schema, errors, info panel, tests, and limitations.

Categories:
- Trend following: moving averages, multi-timeframe trend, strength filters, volatility-adjusted trend, breakout confirmation, continuation, exhaustion.
- Mean reversion: MA deviation, z-score, Bollinger/range reversion, relative-strength reversion, residual-based methods when justified.
- Momentum: time-series/cross-sectional, relative strength, persistence, acceleration, volatility filters, multi-timeframe.
- Breakout/pullback: range/consolidation breakout, volume confirmation, continuation, retest, failed breakout, ATR risk, invalidation.
- Relative value: sector-relative performance, pair/spread/residual analysis and correlation-based discovery only with defensible assumptions; do not assume stationarity from correlation.
- Risk management: volatility/ATR targeting, max-risk-per-trade sizing, exposure/concentration limits, drawdown reduction, liquidity constraints, stop distance, scenarios.
- Portfolio: minimum variance, mean-variance, risk budgeting, equal-risk contribution, HRP only if correct, rebalancing/drift/exposure balancing/drawdown/liquidity constraints.
- Statistical/quant: rolling regression/beta/correlation, factors, regimes, change points, residuals, bootstrap, event studies, anomaly detection.
- Strategy research: parameter sensitivity, walk-forward/out-of-sample, benchmark, robustness, attribution, drawdown, expectancy, slippage sensitivity, multiple-testing diagnostics.
- Research/valuation: DCF, relative/scenario valuation, growth projections, sensitivity, quality scoring, sector-normalized ratios, attribution, risk decomposition.

## B4. Strategy catalogue / My Algorithms UX
Audit existing pages and fix unstructured scrolling, unexplained strategies, unexplained parameters, hard-to-find search, disconnected runs, and confusion between signals and full strategies. Provide search, filters, distinction, per-item info button, detail panel, configurable validated parameters, real run/apply, selected/active state, loading/results/error/empty states, save/recent/favorites where supported, execution status, formula/limitations, related tools, and browser/integration tests. Distinguish selected/configured/running/completed/failed/saved/backtested/out-of-sample tested. Never add live order execution or call a backtest proof of profitability.

## B5. Backtest/scanner correctness
Check no lookahead, timestamp timing, fees/slippage where supported, liquidity/missing data, reproducibility, train/test separation, survivorship bias limitations, accounting, corporate actions, and output. Historical signals must not change when future observations are appended unless explicitly retrospective/repainting. Use chronological/point-in-time evaluation. Official reference for lookahead methodology: urlFreqtrade lookahead-analysis documentationturn0search0.

## B6. Market ribbon and research navigation
Verify actual ticker/ribbon. If data supports, show NEPSE gainers/losers, turnover/volume leaders, unusual activity, index/breadth context; do not leave foreign indices as the only meaningful ribbon when NEPSE data exists. Show source, timestamp, stale status. Verify research ideas/models navigate to results; search results actionable; saved screens/templates/recent items persist; scanner results open for inspection; missing data/inputs are explained.

---

# 7. PART C — QUANTITATIVE RESEARCH, VALUATION, AND VISUALIZATION

## C1. End-to-end data-to-visual pipeline
For important outputs trace source → ingestion → parsing/validation → storage → cleaning → unit conversion → calculation → API → frontend state → series → coordinate transformation → rendered graph → visible value/tooltip. Check rounding/precision, integer division, percentage/currency scaling, units, date/timezones, duplicates, sorting, missing observations, aggregation/resampling, stale caches, double transforms, NaN/null behavior, misaligned arrays, wrong labels, coordinates, and axes.

## C2. Mathematical standard
For each calculation document exact formula, variables, units, defaults/ranges, initialization, warm-up, smoothing, precision, missing-data behavior, boundaries, assumptions, and limitations. Where practical use two genuinely independent methods (production implementation plus hand calculation/reference/independent implementation); add a third for critical calculations where feasible. Wrappers around the same function are not independent. Investigate disagreement; document legitimate convention differences. Use justified tolerances; never invent or loosen expected values to hide defects.

## C3. All charts and graph types
Audit every visualization and its underlying values:
- OHLC candles: timestamp/O/H/L/C/volume; High ≥ Open/Close, Low ≤ Open/Close, High ≥ Low; valid prices; ordering, duplicates, missing sessions, malformed candles/session boundaries. Never synthesize OHLC/volume from close-only data.
- Lines: every x/y pair, ordering, gaps, interpolation, segmentation, units/scales, last point, tooltip, refresh, zoom/scroll; do not connect gaps misleadingly.
- Areas/fills/clouds/channels/confidence bands: exact upper/lower series, sign/direction, start/end, nulls, intersections, zero crossings, positive/negative regions, clipping, viewport, colors/legend. Test equal boundaries, crossings, missing one/both, negatives, near-zero, gaps, and viewport boundaries.
- Multi-line indicators: Bollinger/Keltner/Donchian/Ichi and all others: every line/boundary/shift/fill; verify displacement and no future leakage in signals.
- Histograms: sign, baseline, orientation, magnitude, width, timestamps, zero versus missing.
- Scatter: every x/y pair, units, identity, filtering, tooltips, missing observations.
- Pie/distributions: values, denominators, normalization, totals, percentages/rounding, bins/counts/exclusions.
- Geometry: axis domains/ticks, linear/log transforms, zero baselines, auto limits, clipping, canvas size, device-pixel ratio, responsive resize, margins, pan/zoom, crosshair, tooltip, visibility, multi-axis scales.
- State: adding indicators/layers/drawings/comparisons must not reset zoom/scroll, change symbol, corrupt drawings, duplicate stale series, change units, duplicate objects, or break synchronized panes.
- Financial graphs: P/E/P/B, revenue, earnings, margins, cash flow, debt, valuation, returns, equity curves, drawdowns, volatility, correlation, beta, allocation, efficient frontier, Monte Carlo/fan charts, forecasts, scanner rankings, breadth, turnover/volume, risk/reward, backtest stats/performance comparisons. Verify source data, units, periods, denominators, aggregation, currency, missing values, outliers, labels, tooltips, bounds, totals, valuation inputs, return compounding, drawdown peaks, weights/constraints, distribution bins/counts/exclusions.

For each major graph type use deterministic fixtures; verify full data arrays/coordinates, axis transformations, labels/tooltips, missing-data behavior, and responsive layout. Screenshots supplement—not replace—data verification.

## C4. DCF, valuation, and ownership
Implement/verify historical financial inputs; revenue/expense assumptions; FCF projections; discount rate/WACC; discount factors; terminal value; EV; debt/cash/other supported adjustments; equity value; shares; per-share intrinsic value; sensitivities/scenarios; source/freshness. Check units, signs, negative FCF, terminal assumptions, periods, and missing data. Validate `market cap = price × shares`; `EV = market cap + debt − cash`, with only supported/documented adjustments (short/long debt, cash, NCI, preferred equity, other supported items). EV is not automatically acquisition price. Normalize thousands/millions/billions. Ownership/disclosure facts require source/date; do not imply full institutional coverage or invent holders/changes.

## C5. Monte Carlo, statistics, and portfolio optimization
- Monte Carlo: deterministic seeds; GBM where appropriate; historical/bootstrap where appropriate; volatility/time steps/units/annualization; fan/percentile bands; probabilities reconciled to simulation counts; gain/loss probabilities under explicit assumptions; extremes and limitations. Paths are scenarios, not forecasts.
- Statistical validation: confidence intervals, bootstrap/permutation, Sharpe/Sortino, walk-forward/out-of-sample, multiple-testing correction, Deflated Sharpe, probability of backtest overfitting only if correctly implemented; distinguish descriptive from inferential.
- Portfolio optimization: returns/covariance/correlation, expected returns, minimum variance, efficient frontier, maximum Sharpe where assumptions permit, position/concentration limits, costs/liquidity, risk contributions, HRP/Black-Litterman only if correct, missing history/unstable covariance/solver status. Independently recompute risk/return from weights and data. Explain sensitivity to expected returns.

## C6. Breakouts, liquidity, and multi-timeframe
Verify consolidation/breakout/volume confirmation, retest depth, ATR risk, invalidation, event studies, forward returns without lookahead. Volume profile/VWAP require appropriate volume. Never fabricate order book, aggressor direction, footprint/delta, or institutional flow. Inspect actual floorsheet/broker/time-and-sales schemas and coverage. Verify rolling beta, volatility percentile, multi-timeframe confluence, technical rating, support/resistance strength UI/calculation, symbol/timeframe linkage, stale data, unequal history, and missing index data.

## C7. Industry research/reports
Verify research reports, pitches, valuation summaries. Every report must include inputs/assumptions, sources, last update, calculations, scenario/sensitivity, data gaps, and clear separation of facts vs estimates. Never claim external research not actually conducted.

---

# 8. SEARCHABLE CATALOGUES AND UNIVERSAL INFORMATION PANELS

The existing indicator catalogue is the UX reference. Inspect and reuse its search, clear-search, categories, sorting, list, info button, panel/modal/popover, parameter controls, add/apply, active state, favorites/recents, loading/error/empty states, keyboard/accessibility, spacing, typography, styling, data model, APIs, and browser tests.

Complete a coherent searchable catalogue experience for **indicators, scanners, algorithms, strategies, and fundamental-analysis tools**. Users must search by name, abbreviation, keywords, purpose, category, and meaningful synonyms; filter/sort; open item-specific details; configure parameters; run real calculations; inspect results; see correct status; save/reopen/recent/favorite where supported; and understand missing/stale/error states. Support long catalogues via scrolling/pagination/virtualization. Avoid hard-coded search examples.

Every item must have a small eye/info button beside it. Opening it must not execute the tool and must preserve search, parameters, settings, and results when closed. Show relevant details:
- Full name/ID/category/description/purpose/problem solved.
- Exact formula/rules and variable definitions.
- Defaults, parameter ranges, configuration.
- Required inputs/data/source/provenance and freshness.
- Timeframe/frequency and expected output/schema.
- Interpretation, assumptions, limitations, failure modes, biases.
- Implementation/test/verification/availability status.
- Related tools and real references.
- Type-specific fields: indicator lines/placement/smoothing; scanner conditions/universe/filters/ranking/results; strategy entry/exit/sizing/risk/execution assumptions; fundamental inputs/periods/units/valuation/sensitivity.

Formula and description must match code. Never fabricate formulas or citations; say when unverified. Panel Run/Add must call the same real execution path as the primary action. Distinguish selected/configured/running/completed/failed/saved/backtested/out-of-sample tested. Test every registered item in deterministic batches: discoverability, info button, correct panel/metadata, close preserves state, parameter controls, primary action, visible real output or honest blocked state, active state, no console errors, and numerical fixture where applicable.

## Genuine catalogue targets (not quotas)
- Scanners: approximately 100–150 distinct useful implementations if supported.
- Algorithms: approximately 70–150 genuinely distinct implementations if supported.
- Fundamental-analysis tools: approximately 50–100 distinct tools if supported.
Report registered, distinct-after-deduplication, implemented, numerically tested, browser-tested, info-panel coverage, parameter coverage, data-blocked, and not-implemented counts. Do not pad counts with aliases, parameter variations, empty registrations, or cosmetic differences.

---

# 9. KIMI WORKSPACE: SIDEBAR, ROUTES, LANDING PAGE, AND SHARED CATALOGUE

Add a new visible top-level sidebar section named **KIMI**—not hidden inside unrelated sections, and not a competing sidebar. Use existing icons/design system and preserve navigation. It must support direct routes, back/forward, refresh, route guards, state, responsive layout, keyboard navigation, and existing persistence.

Landing page explains KIMI as a NEPSE research workspace for data quality, market intelligence, corporate actions, quantitative research, company fundamentals, portfolio/risk, and evidence-based AI. It must be functional and show:
- Overview, searchable catalogue, categories.
- Recently used/favorites/pinned tools if existing architecture supports them.
- Real data quality/freshness and feature availability.
- Features requiring more data.
- Recent snapshots if present.
- Links to existing symbol pages, charts, scanners, strategies, and fundamentals.
- Operational/incomplete/blocked status.

No fake metrics, fabricated opportunities, unsupported “smart money” claims, fake live status, or fake dashboard counts. Empty databases get useful honest empty states.

Target navigation (adapt to canonical existing routes; no duplicate tools or dead links):

- **Overview**
- **Market Intelligence:** Broker/Floorsheet; Liquidity/Unusual Activity; Turnover Concentration/Breadth; Market Regimes; Events/Corporate Calendar; IPO/Rights.
- **Data Quality:** Quality Dashboard; Provenance; Coverage Explorer; Source Discrepancies; Financial Revisions.
- **Corporate Actions:** Ledger; Adjusted Price History; Total Return; Reconciliation.
- **Fundamental Research:** Sector Metric Packs; Statement Forensics; Factor Research; Company Research.
- **Quant Research:** Signal Outcomes; Strategy Robustness; Experiment Manager; Point-in-Time Data; Explainable Research Charts.
- **Portfolio & Risk:** Attribution; Risk of Ruin; Stress Testing; Trading Costs/Capacity; Portfolio Ledger/Reconciliation; Benchmark Comparison.
- **Research Desk:** Evidence-Bound AI; Natural-Language Data Query; Research-to-Decision Journal.
- **Alerts:** Unified Alert Center.
- **Reports & Snapshots:** Calculation Snapshots; Reproducible Reports.
- **Settings & Methodology:** Methodology Registry; Data Source Configuration; Feature Availability; KIMI Documentation.

Every entry must open a functional page or a truthful data-blocked state that explains purpose, required/available/missing data, supported calculations, blocked functions, and how to verify. No heading-only/“coming soon” placeholders where meaningful work is possible. Use a shared feature registry with unique ID, name, description, category, route, dependencies, availability/implementation/test status, data needs, methodology, and limitations. Status must reflect evidence, not hard-coded optimism. Search by name, abbreviation, keywords, category, purpose, related metrics; filters should include available, requires data, incomplete, experimental, favorites/recent where supported.

Connect KIMI to existing symbol pages, charts, scanner results, fundamental metrics/data sources, portfolio holdings/risk, data-quality warnings/affected calculations, and snapshots. Avoid circular navigation and duplicate implementations.

---

# 10. KIMI FEATURE REGISTER — NF-001 THROUGH NF-030

Each NF ID must be individually inventoried, classified, implemented as far as feasible, tested, and reported. Record prior state, changes, actual source/data, tests, real external connectivity, incomplete/blocked status, evidence, and next action.

## NF-001 — Broker/Floorsheet Intelligence
Use only actual available floorsheet/transaction records and inspected schema. Where supported: broker activity by symbol, buyer/seller-side summaries, quantity/turnover, concentration, participation over time, changes, lookback, cross-symbol comparison, time series, export, historical event studies. Show turnover/quantity shares, concentration, activity changes, forward returns after predefined events, sample size and uncertainty. Account for missing/duplicate/corrected records and possible self-trades. Broker is intermediary, not necessarily owner/client/institution. Never claim beneficial ownership, insider activity, or certain “smart money.” Define events using information available at event time. Document historical coverage.

## NF-002 — Corporate-Action-Adjusted Total Return Engine
Preserve raw prices and separately represent raw traded price, split/bonus-adjusted price, dividend-adjusted return, total return, and portfolio cash/share effects. Ledger bonus, rights, cash dividends, splits/consolidations, and other supported actions with security, type, dates, terms, source/document, verification, methodology, effective date, warnings. Where supported propagate to share quantity, cash, cost basis, continuity, returns, indicators, backtests, portfolios. No generic factor for every action; no invented terms. Reconcile against source/independent calculations. Test bonus, split/consolidation, dividends, rights if terms/method justified, missing/duplicate/conflicting/unverified actions, date boundaries. Flag suspicious returns for review rather than automatically declaring errors.

## NF-003 — Sector-Specific Fundamental Metric Packs
Build reusable packs for actual sectors represented. Banks: EPS, P/E, P/B, ROE, capital adequacy, NPL/asset quality, deposit/lending, NIM where reliable, dividends. Development banks: same relevant banking metrics. Finance companies: EPS, valuation, ROE, financial strength. Microfinance: EPS/valuation, portfolio quality/NPL/lending where reported. Hydropower: EPS/valuation, capacity, generation/utilization, project stage, debt/cash flow when verified. Insurance: EPS/valuation, premiums, claims, profitability. Other sectors use suitable available metrics; do not force banking ratios onto other industries. Every ratio identifies formula, period, source, missing inputs, comparability. Peer ranks only for sufficiently comparable data.

## NF-004 — Financial Reporting/Corporate Calendar
Source-linked financial reporting periods/publication dates, AGMs, book closures, dividend dates, rights, IPO events, other supported events. Record company/security, type, date/range, source/reference, verification, last checked, and confirmed/estimated/historical/unknown. Never invent dates or treat estimates as confirmed.

## NF-005 — Liquidity Drought/Unusual Activity
Use real daily OHLCV, turnover, transaction data. Rolling volume/turnover percentiles, historical-relative activity, unusually low/high turnover, deterioration, price relative to turnover, configurable windows, cross-sectional rankings. Distinguish unusual activity from direction; daily-only data cannot support intraday claims. Handle missing sessions, zero volume, suspensions, new listings, corporate actions, insufficient history.

## NF-006 — Turnover Concentration/Market Breadth
Where data supports: advancers/decliners/unchanged, turnover concentration and top-security shares, sector concentration, participation, breadth divergence/time series, universe filters. Define eligible universe and missing-price denominator treatment. No certainty claims.

## NF-007 — Financial Statement Forensics
Evidence-based flags: receivables/revenue, accrual indicators where inputs exist, working capital, margins, interest coverage, debt growth, cash-flow/earnings divergence, inventory/sales, YoY changes, statement inconsistencies, missing/revised values. Show exact values, formula, source, reporting period. Flags mean review, not fraud. Avoid unsupported allegations and inappropriate/zero/missing denominators.

## NF-008 — Cross-Sectional Factor Research
Value, momentum (explicit lookback/skip), quality, low-volatility, size, dividend yield, and supported factors. Universe, sector-neutralization where appropriate, ranks, historical factor portfolios/returns, IC, stability, out-of-sample, benchmarks, costs, missingness, export. Use point-in-time inputs. Show sample size, uncertainty/confidence intervals, multiple-testing/selection-bias warnings; no claims based on one sample.

## NF-009 — Market Regime Detection
Interpretable up/down/range/high-/low-volatility or other explicitly defined states. Specify inputs, windows, thresholds, rules, effective date, point-in-time availability, limits. Start transparent/testable; separate fitting and evaluation; regime history/conditioned stats only with sufficient data. No prediction certainty or lookahead.

## NF-010 — Portfolio Return/Risk Attribution
Reuse existing portfolio architecture and actual holdings/transactions. Where supported: portfolio return, security/sector contribution, defensible allocation effects, benchmark-relative results, drawdown contribution, mathematically valid risk contribution, concentration, historical holdings/exposures. Reconcile return contributions under documented accounting. Never sum individual volatilities as portfolio volatility. Disclose cash, fees, dividends, corporate actions, external flows, changing weights, missing prices, currency.

## NF-011 — Risk-of-Ruin/Losing-Streak Simulator
Configurable trade-return distribution, risk/trade, sizing, drawdown, streaks, capital depletion, Monte Carlo, trade-order shuffle, scenarios/sensitivity. Distinguish historical replay, IID Monte Carlo, block bootstrap/dependence-aware methods, hypothetical scenarios. State independence/exchangeability assumptions; deterministic seeds; reproducible results; no guaranteed future outcomes.

## NF-012 — Portfolio Stress Testing
Configurable market declines, sector/security shocks, liquidity haircuts, volatility changes, correlation breakdown, historical replay, combined scenarios. Distinguish historical vs hypothetical. Use actual holdings or clearly labeled hypothetical portfolios without writing fake real holdings. Disclose limits; simple price shocks are not complete liquidity/impact models.

## NF-013 — Data Quality & Provenance Dashboard (FOUNDATIONAL)
Real dataset inventory, source provenance, latest observation and ingestion, freshness, missingness, duplicates, invalid numbers/dates, impossible OHLC, invalid negative volume/turnover, suspicious repeated snapshots/outliers, corporate-action inconsistencies, cross-source discrepancies, symbol/date/field coverage, validation results, unverified records, ingestion failures, known limits. Distinguish observation time from ingestion time. For each dataset record source, collection/update mechanism, expected frequency if known, latest observation, last successful ingestion, rules, gaps, verification. Trace outputs to input records. Create deterministic seeded-corruption fixtures; detect every defined class and measure false positives on valid fixtures. Do not claim all possible corruption is detectable.

## NF-014 — Calculation Snapshots/Reproducibility
Store suitable snapshot ID, feature, calculation time, observation cutoff, input hash/version, dataset IDs, universe, parameters, methodology/code version, outputs, warnings, data-quality state, source refs, seed and assumptions. No secrets. Reproducibility claim requires recoverable inputs/code; reopen/inspect/rerun where supported; disclose unrecoverable environment.

## NF-015 — Evidence-Bound AI Research Desk
Use actual project data and verified sources. Potential technical/fundamental/quant/risk/market-intelligence/skeptical perspectives only if each has a distinct useful function; do not fake multiple agents. Numerical facts link to source, calculation/snapshot, period, assumptions. Distinguish fact, calculated metric, estimate, hypothesis, interpretation, unknown. Skeptical review checks contradictions, missing data, alternatives, lookahead, overfit, assumptions, source conflicts. Never claim unconsulted sources/live queries. AI provider failure must not discard local calculations; deterministic tools do not require AI.

## NF-016 — Natural-Language Query Over Local Data
Support only questions the real schema can answer. Show dataset, calculation plan/query where practical, filters/date ranges, source-backed results, insufficient-data explanations, reruns. Read-only DB, schema/function allowlist, parameterized queries, time/row/memory limits; no arbitrary SQL execution without validation, shell, unrestricted filesystem, production writes, secret exposure, or authorization bypass. Explain unsupported/unsafe questions.

## NF-017 — Signal-Outcome Tracker
Track signal definition, symbol/time, input cutoff, entry timing/price method, horizon (5/10/20 sessions/configurable), exit method, corporate-action/cost assumptions, outcome, snapshot/status. Separate retrospective backtest, prospective recorded signal, paper trading. No future close as entry if signal only known after close; no fabricated future prices. Handle suspensions, delistings, missing future data, actions, overlap, duplicates, incomplete windows; report eligible/excluded counts and do not silently drop failures.

## NF-018 — Unified Alert System
Integrate price, volume, turnover, breakout, corporate action, staleness/data quality, portfolio drawdown/risk, financial-report alerts where supported. Only claim delivery paths that exist and were tested (in-app/email/export). Manual refresh is not continuous monitoring; scheduled alerts require real scheduler. Prevent duplicate spam; explain trigger; edit/enable/disable/review. If no scheduler, support honest manual/on-demand flow.

## NF-019 — Explainable Chart Layer
Reuse existing chart. Add supported corporate-action markers, data-quality warnings, signals, regimes, factors, liquidity events, broker summaries, research annotations with explanation and verified inputs. Correct timestamp/price mapping, missing candles, symbol/timeframe/refresh, removal, zoom/scroll preservation. No arbitrary coordinates or unverified markers.

## NF-020 — IPO/Rights/Allotment Tracker
Source-linked actual issue announcements, application/allotment dates, terms, company, sources, verification. User-entered application/allotment records only if supported. No implied access to private accounts; no fabricated upcoming events; separate official from unverified secondary data.

## NF-021 — Capital Gains/Tax Ledger
Inspect transaction/portfolio structures. Record buys/sells, quantity/price/date, fees, dividends, corporate actions, cost basis, realized/unrealized gains/losses, source documents. Nepal tax rules must be researched from authoritative current sources, with source/effective date, transaction applicability, unresolved interpretations, and known examples. Version rules. Do not invent rates or assert legal certainty. If uncertain, provide ledger and configurable labeled estimates only.

## NF-022 — Strategy Robustness/Overfitting Lab
Parameter sensitivity, walk-forward/out-of-sample, time-aware splits, performance degradation, costs, trade concentration, regimes, stability, multiple-testing. No same-sample “robust” claims; prevent leakage; show periods/assumptions.

## NF-023 — Trading Costs/Strategy Capacity Lab
Position size, turnover, brokerage/fees, modeled slippage, liquidity, average turnover, frequency, holding period, market-impact assumptions. Distinguish actual costs, user configuration, modeled slippage, hypothetical capacity. Do not claim modeled costs equal actual execution; thin liquidity limits capacity.

## NF-024 — Portfolio Ledger/Reconciliation
Actual user-entered/imported transactions, quantities, cash flows, dividends, corporate actions, fees, basis, realized/unrealized gains, discrepancies. Preserve source records; corrections auditable, not destructive. Reconcile totals under chosen accounting method.

## NF-025 — Point-in-Time Research Data
Distinguish reporting, publication, ingestion, effective, revision, and availability dates. Reporting-period end is not publication date. Historical tests cannot use later-published values. If publication/revision history is absent, disclose and do not claim fully point-in-time-correct research.

## NF-026 — Research Experiment Manager
Record question, hypothesis, dataset version, universe, dates, feature/strategy, parameters, benchmark, costs, code/methodology version, results, tests, limits, interpretation, status. Compare only compatible universes/data/assumptions; link snapshots where possible.

## NF-027 — Benchmark/Performance Attribution Lab
Actual NEPSE Index, sector indices, user benchmarks, buy-and-hold/equal-weight only where supported. Cumulative/annualized returns, volatility, max drawdown, relative performance, tracking error and supported metrics. Disclose minimum sample, short/incomplete annualization, and price-only vs total-return mismatch.

## NF-028 — Financial Data Revision/Discrepancy Monitor
Where history exists, show previous/new values, source, period, revision/ingestion times, change magnitude, affected ratios, verification. Do not claim revisions from one observation; preserve conflicts and provenance.

## NF-029 — Research-to-Decision Journal
Hypothesis, supporting/contradictory evidence, entry date, holding horizon, invalidation, risk, snapshots, chart annotations, decision, outcome, lessons. No automatic trade orders; preserve edit history where practical.

## NF-030 — Data Coverage/Feasibility Explorer
Before running a tool, show required/available datasets, symbol/date/field coverage, missingness, corporate-action coverage, source verification, freshness, limits, expected scope. Classify Ready, Ready with limitations, Partial, Blocked by data, Blocked by integration, or Blocked pending verification. Table existence alone is not readiness. Link to feature and quality dashboard.

---

# 11. ADDITIONAL CROSS-CUTTING REQUIREMENTS

Track these separately in the register/checklist:

1. **Corporate-action-aware technical analysis:** identify raw vs adjusted series used by every indicator/strategy; document behavior; support justified adjusted data without silently changing existing indicator meaning; prevent action discontinuities being misread when action data is available.
2. **Data-source reconciliation:** preserve original source, collection/observation time, raw/normalized values, verification, conflict history; do not silently select plausible-looking conflicting values; document justified precedence or flag.
3. **Methodology registry:** formula/algorithm, inputs, parameters, assumptions, version, tests, limits for significant calculations; share tested services rather than conflicting duplicated formulas.
4. **Feature-status registry:** stable ID, name, description, category, route, dependencies, availability/implementation/test status, data needs, methodology, limits; status reflects evidence, not optimistic hard-coding.
5. **Universal feature details:** every KIMI tool has a functioning info panel and accurate method; no empty buttons; disclose incomplete explanation.
6. **Cross-workflow integration:** symbol→KIMI; chart→analysis; scanner result→snapshot; fundamental metric→source; portfolio holding→risk; data warning→affected calculations; research result→company page. Avoid circular navigation and duplicate implementations.
7. **UX:** coherent design, search/filter, loading/progress, useful empty/error/data-unavailable/stale states, result summaries/tables, charts only where valuable, exports/save/reopen where supported, tooltips/accessibility. No clutter or arbitrary decorative charts.
8. **Performance:** lazy/asynchronous data loading, existing cache patterns, no heavy work on every render, progress/cancel where feasible, duplicate-submit prevention, bounded queries/memory, no scheduler solely for appearance.
9. **Source/license verification:** for every new dependency/source, record official source, access requirements, license, maintenance, security, actual connectivity verification, unresolved concerns. Public repository does not imply permissive license. No copying without license review.
10. **Research audit:** original mission targeted about 60 distinct websites/documents and 20 Reddit discussions. Audit whether that was actually achieved; if not, research relevant topics where access permits. Record exact title, author/publisher, URL, access date, subject, implementation decision supported, source type, license/maintenance where relevant. Do not claim counts without distinct reviewed sources. Prefer primary/official, academic, maintained, authoritative sources; Reddit is supplementary, not proof of mathematics.

---

# 12. NUMERICAL, DATA, AND SECURITY RULES

For each calculation define formula, units, required fields, missing/invalid behavior, boundaries, deterministic fixtures, independently calculated expected values, edge cases, and limitations. Use hand calculations, separate reference implementations, identities, reconciliation, property/metamorphic/differential tests as appropriate. Never use the implementation as its only oracle.

Avoid:
- Lookahead/future leakage.
- Survivorship bias claims when historical universe is missing.
- Double-counting dividends/actions.
- Treating missing as zero.
- Annualization mistakes.
- Mixing decimal and percent returns.
- Division by zero.
- Silent conversion of invalid values into plausible numbers.
- Unexplained rounding/precision loss.
- Fabricated OHLC, volume, ownership, fundamentals, events, source records, signal outcomes, backtests, holdings, or research.

Synthetic data is allowed only in isolated tests, clearly labeled, never in production analysis. For every output show provenance/coverage/status where relevant. Do not call mocked integration “live”. No new source without access/license/security review. No TLS bypass or access-control bypass.

For natural-language queries, enforce read-only access, allowlisted schemas/functions, parameterization, bounded resources, no arbitrary shell/filesystem/production writes/secrets.

For alerts, distinguish manual from scheduled/continuous execution. For AI, distinguish sourced facts from calculated values, estimates, hypotheses, interpretations, and unknowns.

---

# 13. TESTING AND EVIDENCE

Inspect existing testing infrastructure first; avoid unnecessary frameworks/dependencies. Baseline and final results must include exact commands, pass/fail/skipped counts, exit codes, logs, and what each test actually proves.

Use applicable combinations of:
1. Independent numerical reference tests.
2. Hand-calculated deterministic fixtures.
3. Property tests.
4. Boundary/edge tests.
5. Metamorphic tests.
6. Differential tests.
7. Regression tests.
8. API integration tests.
9. Browser/UI tests.
10. End-to-end data-to-graph tests.
11. Performance/stability tests.

Test data lifecycle, formulas, APIs, frontend series, coordinates, visible values, tooltip, labels, stale states, errors, persistence, import/export, and user workflows. For every defect: preserve failing case, identify root cause, fix, add regression test, rerun target and related tests, verify browser behavior where applicable, document evidence.

Mandatory test groups include:
- All 92 indicators and their visuals.
- Quick Layers, patterns, Fibonacci, object manager, drawings, comparisons.
- Scanner/algorithm/strategy/fundamental catalogue search/info/configure/run/results.
- DCF/EV/ownership/Monte Carlo/statistics/portfolio optimization.
- Data provenance, seeded corruption and false positives, coverage/readiness, corporate actions, snapshots/reproducibility, point-in-time/revisions, signal outcomes, portfolio reconciliation, risk simulation, alerts, read-only query security.
- KIMI sidebar/routes/refresh/back-forward/responsive navigation and all NF features’ supported/blocked behavior.
- API contracts, stale/error/empty/loading states, console/backend errors, settings/persistence/templates/import-export.
- Full existing regression suite where practical.

Do not hide failures, delete/weaken tests, change expected values without independent proof, claim suite pass if it did not finish, or mark a mocked integration as live. Every skipped test needs a reason. Every item’s test status must be recorded.

---

# 14. IMPLEMENTATION ORDER

Work in this order while continuously updating checklists/checkpoints. Do not stop after planning or documentation.

## Phase 0 — Discovery/baseline
Inspect repo, all reports, sidebar/routes/catalogues/data/schema/calculations/tests; establish baseline; create registers/inventories/data dependencies/checkpoint; classify every requirement and NF-001–030.

## Phase 1 — KIMI core
Add sidebar/routes/landing page/shared feature registry/searchable catalogue/common details panel; loading/empty/error/blocked states; connect navigation; test routes and existing navigation. No placeholder destinations.

## Phase 2 — Data foundation
NF-013 quality/provenance; NF-014 snapshots; NF-030 coverage/feasibility; NF-025 point-in-time foundation; NF-028 revisions/discrepancies; methodology and feature-status registries. Establish actual data coverage and traceability.

## Phase 3 — Corporate actions and market intelligence
NF-002 actions/adjustments; NF-001 broker/floorsheet; NF-004 calendar; NF-005 liquidity; NF-006 breadth/concentration; NF-009 regimes; NF-020 IPO/rights. Use only real data; test numerics.

## Phase 4 — Fundamentals/factors
NF-003 sector packs; NF-007 forensics; NF-008 factor research; complete NF-028 as needed. Reuse company/financial/valuation systems.

## Phase 5 — Signals/strategy research
NF-017 outcomes; NF-022 robustness; NF-023 costs/capacity; NF-026 experiments; NF-019 explainable chart layer. Prevent lookahead and preserve viewport.

## Phase 6 — Portfolio/risk
NF-010 attribution; NF-011 risk of ruin; NF-012 stress tests; NF-024 ledger/reconciliation; NF-027 benchmarks; NF-021 tax ledger only to extent current rules verified.

## Phase 7 — Research desk/alerts
NF-015 evidence-bound AI; NF-016 safe natural-language queries; NF-018 alerts; NF-029 journal. Deterministic analysis must work without AI; no false continuous-alert claims.

## Parallel/continuous catalogue work
Do not postpone catalogue UX until the end. Inspect indicator catalogue early; reuse/fix shared UX; implement and verify scanner, algorithm, strategy, and fundamental catalogues alongside other phases. Keep Part A, B, C all progressing; do not focus on one part and abandon the others.

## Phase 8 — Integration/regression
Check every route/feature/info panel/run action/dependency/status, all existing navigation/charts/indicators/scanners/algorithms/strategies/fundamentals/portfolio/data ingestion, no dead routes, empty handlers, fake results, duplicates, inconsistent formulas, stale states, console/runtime/network errors, broken imports or API contracts. Fix mission-caused issues.

## Phase 9 — Final audit
Audit each requirement and NF-001–030 individually; compare prompt against register; conduct independent checklist pass for implementation, tests, browser behavior, and omissions. Report exact statuses/evidence; do not claim completion if anything is incomplete.

After each substantial batch: run tests, inspect failures, fix root causes, rerun, update evidence/checkpoint, continue to next unfinished item. If blocked, document evidence and continue independent tasks.

---

# 15. FINAL REPORTS AND COUNTS

Produce all required reports listed in Section 3. Final reports must include:

- Executive summary and baseline comparison.
- Every requirement ID and final status.
- Completed/verified, implemented-unverified, partial, not implemented, blocked, not feasible, not recommended counts separately.
- Part A/B/C coverage and evidence.
- Indicator-by-indicator mathematical/reference/browser status, including exact identities of the 28 invariant-only and 2 sparse items.
- Distinct scanner/algorithm/strategy/fundamental counts after deduplication; registered/implemented/numerically tested/browser-tested/info-panel/parameter/data-blocked/not-implemented counts.
- KIMI sidebar and final route tree.
- NF-001–NF-030 individually: prior state, change, working behavior, actual source, tests, real external connectivity status, limitations, blocker, next action.
- Components and chart/visualization types audited; numerical/property/browser/API/end-to-end test counts.
- Every defect found, fix, regression evidence, unresolved defect.
- Exact commands, test counts, skips/reasons, exit codes, logs, tolerances, oracle/source, and what tests prove.
- Data-source and freshness limitations, research sources actually reviewed, license/security/dependency findings.
- Files changed, database/migrations, current Git status, production safety confirmation.
- Manual browser verification actually performed.
- Exact next steps for every incomplete requirement.

Do not claim “all 92 verified,” “all graphs correct,” “all algorithms correct,” “60 sources,” “20 Reddit discussions,” or “all three parts complete” unless itemized evidence supports it. A route returning HTTP 200, UI rendering, test file existence, registry entry, or mock does not establish functional correctness.

---

# 16. NON-SKIPPING / RESUME RULE

Every explicit requirement above must have a distinct tracked item. Do not omit, silently merge, remove, or downgrade requirements to improve completion percentages. Do not stop after creating a checklist, writing reports, passing one suite, or implementing the easy parts.

For every blocker:
1. Record ID and exact evidence.
2. Explain the dependency.
3. Implement all safe independent work.
4. Test supported behavior and blocked-state explanation.
5. State the precise remaining dependency.
6. Add next action and checkpoint.

Before stopping, save the current requirement ID, files changed, tests and results, known failures/regression risks, remaining work, and exact next action. Continue as long as the real environment permits, but never pretend execution can be indefinite.

## Start now
Read prior reports and repository state; inspect actual code and tests; establish baseline; create the registers, inventory, checklist, and checkpoint; then implement and test the highest-value unfinished work immediately. Keep ticking every item only when its acceptance criteria and evidence are satisfied. Preserve existing work and production. The goal is a real, integrated, mathematically defensible, searchable, reproducible, tested NEPSE Mega Tool with a functional KIMI workspace—not a polished report or a collection of empty buttons.
