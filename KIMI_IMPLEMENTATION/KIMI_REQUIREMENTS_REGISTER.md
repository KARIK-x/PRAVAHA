# KIMI Requirements Register

Source: Session 34 mission prompt (NF-001..NF-030 + Section 6 additional + Section 7 UX).

Statuses: NOT STARTED / IN PROGRESS / IMPLEMENTED / TESTED / VERIFIED / BLOCKED / NOT FEASIBLE WITH CURRENT DATA / NOT RECOMMENDED

Truth rule: a feature is IMPLEMENTED only when code exists and is reachable from
the app; TESTED only when a named test/browser check actually ran. Missing data
is reported as missing, never filled with a placeholder.

## NF-001 through NF-030

| ID | Feature | Current state | Target | Data dependency | Status |
|---|---|---|---|---|---|
| NF-001 | Broker/Floorsheet Intelligence | FloorSheet collection exists (floorsheet.py, `/api/floorsheet/*`); no rows in dev | Real broker activity analysis | floorsheet_trades table (0 rows in dev) | BLOCKED (no floorsheet data) |
| NF-002 | Corporate-Action-Adjusted Total Return | Corporate actions documented (corporate_actions.py); no price adjustment | Adjustment engine + ledger | corporate_actions verified data | PARTIAL (docs only) |
| NF-003 | Sector-Specific Fundamental Metric Packs | Sector classification exists | Sector packs with ratios | fundamentals + sector map | PARTIAL |
| NF-004 | Financial Reporting & Corporate Calendar | None | Source-linked calendar | event data (none) | BLOCKED (no event data) |
| NF-005 | Liquidity Drought & Unusual Activity | `run_liquidity_drought` in catalog.py, wired to KIMI → Liquidity | Daily-data liquidity tool | OHLCV (available) | IMPLEMENTED (backend + UI), TESTED |
| NF-006 | Turnover Concentration & Market Breadth | Breadth exists (breadth.py, KIMI → Breadth) | Concentration + breadth | price_bars (available) | PARTIAL |
| NF-007 | Financial Statement Forensics | `run_fundamental_forensics` in catalog.py, wired to KIMI → Forensics | Forensic screening tool | fundamentals (available) | IMPLEMENTED, TESTED |
| NF-008 | Cross-Sectional Factor Research | `run_factor_snapshot` in catalog.py, wired to KIMI → Factors | Factor research workspace | price_bars (available) | IMPLEMENTED, TESTED |
| NF-009 | Market Regime Detection | regime module + KIMI → Regime | Interpretable regime tool | price_bars (available) | IMPLEMENTED (backend) |
| NF-010 | Portfolio Return & Risk Attribution | portfolio module exists | Attribution workspace | holdings (user) | PARTIAL |
| NF-011 | Risk-of-Ruin & Losing-Streak Simulator | `run_risk_of_ruin`, wired to KIMI → Portfolio | Risk simulator | trade returns (user) | IMPLEMENTED, TESTED |
| NF-012 | Portfolio Stress Testing | `run_stress_test`, wired to KIMI → Portfolio | Stress workspace | holdings (user) | IMPLEMENTED, TESTED |
| NF-013 | Data Quality & Provenance Dashboard | KIMI → Data Quality (store facts + coverage explorer) | Comprehensive DQ dashboard | all stores | IMPLEMENTED |
| NF-014 | Calculation Snapshots & Reproducibility | None | Snapshot mechanism | all | NOT STARTED |
| NF-015 | Evidence-Bound AI Research Desk | LLM provider optional (llm.py) | Research assistant | LLM provider | NOT STARTED |
| NF-016 | Natural-Language Query over Local Data | None | Read-only NL query | DB schema | NOT STARTED |
| NF-017 | Signal Outcome Tracker | `run_signal_outcomes`, wired to KIMI → Signals | Signal tracker | price_bars (available) | IMPLEMENTED, TESTED |
| NF-018 | Unified Alert System | Alerts API exists; no scheduler | Alert centre | scheduler (none) | BLOCKED (no in-app scheduler) |
| NF-019 | Explainable Chart Layer | Chart annotations exist | KIMI chart layer | chart workspace | PARTIAL |
| NF-020 | IPO, Rights & Allotment Tracker | None | Event tracker | event data (none) | BLOCKED (no data) |
| NF-021 | Capital-Gains & Tax Ledger | Journal + cost model exist | Tax ledger | transactions (user) | PARTIAL |
| NF-022 | Strategy Robustness & Overfitting Lab | `run_deflated_sharpe` + walk-forward exist | Robustness lab | price_bars (available) | PARTIAL |
| NF-023 | Trading Cost & Strategy Capacity Lab | Cost model exists | Cost/capacity lab | user inputs | PARTIAL |
| NF-024 | Portfolio Ledger & Reconciliation | Portfolio exists | Ledger engine | user transactions | PARTIAL |
| NF-025 | Point-in-Time Research Data | None | PIT foundation | publication dates (none) | BLOCKED (no pub dates) |
| NF-026 | Research Experiment Manager | Experiments table exists | Experiment manager | experiments table | PARTIAL |
| NF-027 | Benchmark & Performance Attribution | Ranking/benchmark exist | Attribution lab | price_bars (available) | PARTIAL |
| NF-028 | Financial Data Revision Monitor | None | Revision tracker | revision history (none) | BLOCKED (no history) |
| NF-029 | Research-to-Decision Journal | Journal exists | Research journal | user entries | PARTIAL |
| NF-030 | Data Coverage & Feasibility Explorer | `run_coverage_explorer`, wired to KIMI → Research Desk + Data Quality | Data-readiness explorer | all stores | IMPLEMENTED, TESTED |

## Section 6 additional requirements

| ID | Requirement | Status |
|---|---|---|
| 6.1 | Corporate-action-aware technical analysis | PARTIAL (docs only; prices unadjusted) |
| 6.2 | Data source reconciliation | NOT STARTED |
| 6.3 | Methodology registry | IMPLEMENTED (KIMI → Research Desk) |
| 6.4 | Feature status registry | IMPLEMENTED (KIMI → Overview) |
| 6.5 | Universal feature details (info panels) | IMPLEMENTED (ⓘ for all 229 catalogue tools) |
| 6.6 | Connect KIMI to existing workflows | IMPLEMENTED (KIMI reuses /api/screen, /api/backtest, /api/analysis/run, /api/fundamental/run) |

## Section 7 UX requirements

Covered per feature in implementation. Status tracked in checklist.

## Where each feature is executed

Every catalogue tool names a real engine in `megatool/catalog.py`, and
`catalog_health()` fails if any tool's execution path is missing. The KIMI
**Catalogues** tab surfaces all 229 tools with search, category filter, an ⓘ
information panel and a Run button that dispatches to the correct engine.
