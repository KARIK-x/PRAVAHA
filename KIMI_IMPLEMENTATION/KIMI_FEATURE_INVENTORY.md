# KIMI — Feature Inventory

The KIMI workspace is a top-level sidebar section (not a competing sidebar). It
has 13 tabs, all of which now load real data or a real engine.

| # | Tab (`data-tab`) | What it shows | Engine / endpoint |
|---|---|---|---|
| 1 | `overview` | Workspace summary + feature status registry | `/api/status`, `/api/securities` |
| 2 | `catalogues` | Searchable catalogue of all 229 tools with ⓘ info + Run | `/api/catalog/*` then screen/backtest/analysis/fundamental |
| 3 | `dataquality` | Data-quality + provenance + coverage explorer | `/api/status`, `/api/securities`, `coverage_explorer` |
| 4 | `regime` | Market regime for a symbol | `/api/bars/{symbol}` |
| 5 | `liquidity` | Liquidity drought / Amihud proxy | `liquidity_drought` |
| 6 | `breadth` | Latest breadth sessions | `/api/breadth/history` |
| 7 | `forensics` | Price checks + stored-fundamental forensics | `/api/bars/{symbol}` + `fundamental_forensics` |
| 8 | `factors` | Cross-sectional factor ranking | `factor_snapshot` |
| 9 | `signals` | Signal outcome tracker (next-bar entry) | `signal_outcomes` |
| 10 | `montecarlo` | GBM or historical bootstrap | `monte_carlo` |
| 11 | `valuation` | Stored fundamentals + DCF + sensitivity | `/api/fundamentals`, `dcf_valuation` |
| 12 | `portfolio` | Frontier, HRP, risk of ruin, stress test | `efficient_frontier`, `hrp_portfolio`, `risk_of_ruin`, `stress_test` |
| 13 | `researchdesk` | Methodology registry + coverage explorer | static registry + `coverage_explorer` |

## Catalogue families

| Family | Count | Execution |
|---|---|---|
| Scanners | 124 | `/api/screen` (real condition trees) |
| Algorithms | 77 | `/api/backtest` (58) + `/api/analysis/run` (19) |
| Fundamental tools | 32 | `/api/fundamental/run` |

Every tool carries: id, name, category, description, formula, default params,
tags, limitations, data requirements, executing engine and status. The ⓘ panel
shows them without executing; the Run button executes.

## Honest states
- Missing data returns an explicit reason (e.g. dividend yield → not stored),
  never a fabricated zero.
- Blocked features (floorsheet, events, DPS, ownership) are labelled BLOCKED.
