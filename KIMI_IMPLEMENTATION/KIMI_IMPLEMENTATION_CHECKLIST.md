# KIMI — Implementation Checklist

Legend: ✅ done & verified · 🟡 partial · ⛔ blocked · ⬜ not done

## Workspace
- ✅ Top-level sidebar section; no competing sidebar.
- ✅ 13 tabs, each loading a real panel.
- ✅ Landing (overview) lists feature status and live store facts.
- ✅ Shared ⓘ information panel for all catalogue tools.
- ✅ Loading / empty / error / blocked states everywhere.

## Catalogues tab
- ✅ Family selector (scanners / algorithms / fundamentals).
- ✅ Category filter populated from the returned category map.
- ✅ Multi-term search over name / tag / formula / description / key.
- ✅ ⓘ Info: formula, params, tags, data requirements, executing engine, status,
  limitations — without executing.
- ✅ Run dispatches to the correct real engine.
- 🔴 Full click-through of all 229 tools: sampled per family (PARTIAL).

## Engine wiring
- ✅ Liquidity → `liquidity_drought`.
- ✅ Forensics → `fundamental_forensics` (plus price checks).
- ✅ Factors → `factor_snapshot`.
- ✅ Signals → `signal_outcomes`.
- ✅ Monte Carlo → `monte_carlo` (GBM + bootstrap).
- ✅ Valuation → `dcf_valuation` + stored fundamentals.
- ✅ Portfolio → `efficient_frontier`, `hrp_portfolio`, `risk_of_ruin`,
  `stress_test`.
- ✅ Research desk → methodology registry + `coverage_explorer`.
- ✅ Data quality → `coverage_explorer`.

## Bugs fixed while wiring
- ✅ `table()` was called with raw string cells in Overview and Data Quality,
  rendering "undefined" for every cell — fixed.
- ✅ Duplicate `bindKimiSection` removed.
- ✅ Store-backed analysis through the API (provider hook).

## Blocked (data)
- ⛔ Floorsheet intelligence (0 rows).
- ⛔ Corporate-event / IPO / rights calendar (none).
- ⛔ Ownership (0 rows).
- ⛔ Alerts scheduler (none).
- ⛔ Point-in-time (no publication dates), revision monitor (no history).
