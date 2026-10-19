# KIMI — Data Dependencies

What each KIMI capability needs, what is actually present, and the resulting
state. A missing dependency is reported, never simulated.

| Capability | Needs | Present? | State |
|---|---|---|---|
| Overview counts | securities + bars | yes (372 securities, ~515k bars) | live |
| Catalogues | catalogue metadata + engines | yes (229 tools, health ok) | live |
| Data quality | `/api/status`, securities | yes | live |
| Coverage explorer | market store + app db | yes | live |
| Regime | daily close | yes | live (proxy index for market regime) |
| Liquidity drought | daily close + genuine volume | yes | live; refuses if volume missing/all-zero |
| Breadth | daily bars | yes | live |
| Forensics (price) | daily OHLCV | yes | live |
| Forensics (fundamental) | stored fundamentals | yes (21,698 records, 307 symbols, 5–6 fields) | live |
| Factors | daily close + volume | yes | live |
| Signals | daily close (+ volume for spike) | yes | live |
| Monte Carlo (GBM) | none (assumptions) | — | live |
| Monte Carlo (bootstrap) | daily close | yes | live |
| Valuation (fundamentals) | stored fundamentals | yes | live |
| DCF / reverse DCF | user assumptions | — | live |
| Portfolio (frontier/HRP) | daily close for ≥2 symbols | yes | live |
| Risk of ruin | user trade stats | — | live |
| Stress test | daily close + NEPSE composite | yes (2,217 genuine index bars) | live |
| Broker/floorsheet | `floorsheet_trades` rows | **0 rows** | BLOCKED |
| Corporate events / IPO / rights | sourced event calendar | **none** | BLOCKED |
| Dividend yield | DPS records | **0 records** | BLOCKED (explicit reason) |
| Ownership | promoter/public holding | **0 records** | BLOCKED |
| Total-return / adjustment | verified corporate-action ledger | not available | PARTIAL (prices unadjusted) |
| Alerts / auto-refresh | external scheduler | none in-app | BLOCKED (needs cron/launchd/systemd) |
| Point-in-time research | publication dates | **none** | BLOCKED |
| Revision monitor | revision history | **none** | BLOCKED |
| Live / intraday | live feed credential | gated (401) | BLOCKED; daily data only |
