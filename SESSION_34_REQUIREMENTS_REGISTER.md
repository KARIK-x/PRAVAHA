# SESSION 34 — REQUIREMENTS REGISTER

Session 34 is the consolidated implementation/verification pass for the NEPSE Mega
Tool (Session 31 + Session 32 + Session 34 + KIMI feature suite).

Source of truth: `NEPSE_MEGA_TOOL_MASTER_MISSION_CONDENSED.md`.
Live checklist with every item and its tick state: `MASTER_MISSION_CHECKLIST.md`.

Status vocabulary (never inflated):

| Label | Meaning |
|---|---|
| IMPLEMENTED | Code exists and is reachable from the app |
| TESTED-PASS | A named test/browser check ran and passed (command recorded) |
| PARTIAL | Some sub-cases work; the remainder is listed |
| NOT-IMPLEMENTED | Does not exist |
| BLOCKED | Cannot be built because the required data/source is absent |
| NOT-TESTED | Exists but no test has covered it yet |

Baseline at session start (verified this session):
- git HEAD `b6c3659`, branch `main`, 286 changed paths, **0 staged**.
- Full suite: 2,701 passed / 0 failed / 8 skipped, exit 0 (progress-dot count = 2,701).
- Prod uvicorn :8710 = HTTP 200 (never signalled). Dev :10000 = HTTP 200.

---

## Part A — Charting & indicators

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| A1 | Verify all 92 indicators individually | TESTED-PASS | 62 reference / 28 invariants / 2 sparse map; `tests/test_indicators*.py` |
| A2 | Browser rendering of all 92 | PARTIAL | info button for all 92 verified (session 30); batched add/remove walk partial |
| A3 | Quick Layers | TESTED-PASS | per-symbol `mt-quick-layers-<symbol>` persistence |
| A4 | Analysis layers & patterns | TESTED-PASS | Fibonacci/Elliott/harmonic/classical/candlestick/levels tests |
| A5 | Object manager & cryptic labels | PARTIAL | groups + scoped clearing tested; BO/DT/INV label trace partial |
| A6 | Drawing / chart UX | TESTED-PASS | hit-testing/eraser/delete/viewport tests |
| A7 | Multi-symbol comparison | TESTED-PASS | up to 4 overlay, relative mode, swap persistence, timeframe-aware |
| A8 | Wire 5 quant capabilities into UI | PARTIAL | backend TESTED-PASS; dedicated panels PARTIAL (surfaced in KIMI Catalogues) |
| A9 | Fundamentals graphs & corporate actions | PARTIAL | P/E/P/B + ISO period compare TESTED-PASS; adjustment BLOCKED (unadjusted) |
| A10 | APIs, refresh, freshness | PARTIAL | source audit done; in-app scheduler BLOCKED (needs external cron) |
| A11 | Settings, import/export, search | PARTIAL | favourites/recents/isolation tested; import validation + recent dropdown partial |

## Part B — Scanners, algorithms, strategies

| ID | Requirement | Target | Actual | Status |
|---|---|---|---|---|
| B1 | Inventory | — | 92 indicators, 41 metrics, 31 presets, 20 strategies | TESTED-PASS |
| B2 | Searchable scanner catalogue | 100–150 | **124** | TESTED-PASS |
| B3 | Searchable algorithm catalogue | 70–150 | **73** (58 backtest + 15 analysis) | TESTED-PASS |
| B3b | Fundamental tool catalogue | 50–100 where data supports | **32** | IMPLEMENTED |
| B4 | Strategy catalogue UX (info/search/run) | — | Catalogues tab, ⓘ + Run | TESTED-PASS |
| B5 | Backtest/scanner correctness | — | no-leak, fees, reproducibility, accounting | TESTED-PASS |
| B6 | Market ribbon & research navigation | — | NEPSE ribbon; source/stale display partial | PARTIAL |

## Part C — Quant research, valuation, visualisation

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| C1 | Data-to-visual pipeline traced + oracles | TESTED-PASS | `tests/_naive_helpers.py`, independent numeric tests |
| C2 | Math standard per calculation | PARTIAL | formula strings per tool; prose standard partial |
| C3 | Charts & graph types | PARTIAL | OHLC/line/bands/histogram tested; scatter/pie partial |
| C4 | DCF / valuation | TESTED-PASS | DCF + reverse DCF + sensitivity; hand-computed test; ownership BLOCKED |
| C5 | Monte Carlo / statistics / portfolio | TESTED-PASS | GBM+bootstrap, deflated Sharpe, frontier, HRP, risk-of-ruin, stress test, event study |
| C6 | Breakouts, liquidity, MTF | PARTIAL | breakout/volume-confirmed/MTF tested; floorsheet BLOCKED |
| C7 | Industry research/reports | PARTIAL | valuation summary inputs/assumptions; industry datasets not fabricated |

## KIMI workspace

| ID | Requirement | Status |
|---|---|---|
| K1 | Native top-level KIMI section, no competing sidebar | TESTED-PASS |
| K2 | Every visible nav item reaches a real page | IMPLEMENTED |
| K3 | Searchable feature catalogue | TESTED-PASS (Catalogues tab) |
| K4 | Shared information panel per tool | TESTED-PASS |
| K5 | Honest empty/blocked states | TESTED-PASS |
| NF-001..NF-030 | see `KIMI_IMPLEMENTATION/KIMI_REQUIREMENTS_REGISTER.md` | mixed (see file) |

## §6 data-source items

| ID | Requirement | Status |
|---|---|---|
| 6.1 | Corporate-action-aware TA | PARTIAL (documented; all prices unadjusted) |
| 6.2 | Data-source reconciliation | NOT-IMPLEMENTED |
| 6.3 | Methodology registry | IMPLEMENTED |
| 6.4 | Feature status registry | IMPLEMENTED |
| 6.5 | Universal feature details | TESTED-PASS |
| 6.6 | Connect KIMI to existing workflows | IMPLEMENTED |

## Research & testing

| ID | Requirement | Status |
|---|---|---|
| RES-1 | ≥60 distinct sources reviewed | PARTIAL (see `RESEARCH_SOURCES.md`) |
| RES-2 | ≥20 Reddit threads | PARTIAL |
| T-1..T-9 | Layered test protocol | see `SESSION_34_TEST_EVIDENCE.md` |

## Known blockers (all data/source driven)

1. `floorsheet_trades` has 0 rows in dev → NF-001, C6-5, order-flow BLOCKED.
2. No sourced corporate-event / IPO / rights calendar → NF-004, NF-020 BLOCKED.
3. `dps` field has 0 records → dividend yield returns not-available (never zero).
4. `promoter_holding` / `public_holding` have 0 records → ownership BLOCKED.
5. All prices `adjustment_status='unadjusted'`; no verified action ledger → total-return features PARTIAL.
6. No in-app scheduler → alerts/refresh need an external cron/launchd/systemd (documented, not faked).
7. Live NEPSE API 401 / gated; no intraday series → live/microstructure features BLOCKED.
