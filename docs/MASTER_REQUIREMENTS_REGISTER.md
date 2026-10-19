---
name: master-requirements-register
description: Master requirements register recovered from source spec (104-page idea overview + 52-page written data)
metadata:
  type: reference
  updated: 2026-10-14
---

MASTER REQUIREMENTS REGISTER — Mega Tool (NEPSE quantitative research)
Source: ALL THE CONTENT:IDEA MAIN OVERVIEW OF PROJECT.pdf (104 pages, primary spec)
Secondary: WRITTENdata.pdf (52 pages, written-data audit spec)

12 FEATURE AREAS (source-derived):
1. Market Dashboard (Section 8) — IMPLEMENTED + PARTIAL (index unavailable B-10)
2. Advanced Charting (Section 9) — IMPLEMENTED + PARTIAL (overlays partial)
3. Stock Scanner (Section 18) — IMPLEMENTED + QUALITY FILTER ADDED
4. AI-Assisted Research (Section 19) — IMPLEMENTED (deterministic rules)
5. Floor-Sheet Intelligence (Section 21) — PARTIAL (synthetic only; T-13 blocked)
6. Fundamental Analysis (Section 20) — PARTIAL (0 records; B-08 blocked)
7. News / Events (Section 22) — LOCAL LAYER IMPLEMENTED + SOURCE BLOCKED (import/validate/dedup/summarise, schema v6, `POST /api/news/import` + `GET /api/news/summary`, 22 tests; no machine-readable source — L4/T-15; nothing fetched, scraped or fabricated)
8. Forecasting (Section 22/Forecast) — IMPLEMENTED + TESTED (honest baseline comparison **plus rolling-origin walk-forward evaluation**, `POST /api/forecast/rolling`, leakage-probed)
9. Backtesting (Section 15 / 23) — IMPLEMENTED + TESTED structural/fixture (24 lifecycle + cost-model tests; B-11 fee placeholder end-to-end labelled; live-data run NOT-TESTED)
10. Portfolio (Section 12 / 24) — IMPLEMENTED
11. Trading Journal (Section 11/12/30) — IMPLEMENTED
12. Document Intelligence (Section 15 / 14 / 30) — PARTIAL (0/52 fully transcribed)

KEY REQUIREMENTS TRACEABLE TO CODE:
- Multi-timeframe (Section 17): weekly/monthly aggregation implemented in megatool/ta/multitimeframe.py; API routes /weekly + /monthly verified
- Fibonacci (Section 11): megatool/ta/fibonacci.py verified; chart plot fixed (bar times)
- Support/Resistance (Section 12 / 16): megatool/ta/levels.py verified; plot fixed (bar times)
- Candlestick (Section 12 / 14): megatool/ta/candles.py verified (104 tests); plot fixed
- Elliott Wave (Section 10 / Section 7): IMPLEMENTED + verified 2026-10-14 — bounded module `megatool/ta/elliott.py` returns CANDIDATE_ONLY with alternative counts, invalidation and uncertainty note; confirmed-swings look-ahead closed; live `GET /api/bars/{symbol}/elliott` 200
- Harmonic (Section 13): IMPLEMENTED (candidates) 2026-10-14 — `megatool/ta/harmonic.py` XABCD detection for Gartley / Bat / Butterfly / Crab / Cypher on published ratio bands (Carney conventions, documented in-module); every match carries measured ratios, matched bands, an invalidation price and certainty="low"; `GET /api/bars/{symbol}/harmonic` live-verified 200 (NO_MATCH/CANDIDATE_ONLY/INSUFFICIENT_EVIDENCE semantics)
- Data Integrity (Section 30): B-20/B-21/B-23/B-24 preserved; quality.py flags maintained
- Research Workspace (Section 17): workspace.py verified (24 tests)

REMAINING BLOCKERS (documented, not fabricated):
- T-11: sector mapping CSV required (B-07)
- T-12: verified fee/tax rates required (B-11)
- T-13: real floor-sheet data required
- T-10: Ollama upgrade (blocked — not authorized)
- T-09: PDF visual review deferred by owner
- L4: news/events source — licensing unresolved (T-15); local processing layer
  is complete and tested, so a source is the only missing piece
- B-08: verified fundamentals source; B-10: index series

NOT INVENTED: sectors, fees, fundamentals, floor-sheet, index values, market predictions, news headlines
