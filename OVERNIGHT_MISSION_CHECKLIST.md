# Overnight mission checklist — NEPSE Mega Tool

Baseline: Session 30, HEAD b6c3659, 282 uncommitted paths, dev :10000, prod :8710 untouched.

Status legend: TODO / IN_PROGRESS / DONE / BLOCKED / N/A

## Part A — Existing application, charting, indicators, data, UI/UX

### A1 Full application inventory
- A1.1 Inventory all sidebar sections, panels, tools — DONE (sessions 26-30)
- A1.2 Record routes, source files, data deps — DONE

### A2 Indicator registry and mathematics
- A2.1 Audit all 92 indicators — DONE (session 30: 62 reference / 28 invariants / 2 sparse)
- A2.2 Add numeric reference tests for invariant-only — DONE (test_indicators3.py, 25 tests)
- A2.3 Fix scanner promotion rule — DONE

### A3 Indicator visualization
- A3.1 Audit overlay vs pane placement — DONE (33/59 browser-verified)
- A3.2 Info button coverage 92/92 — DONE

### A4 Indicator information buttons
- A4.1 Fill metadata gaps (refs/notes/params) — DONE (session 30)

### A5 Catalogue and search
- A5.1 Search by name/abbr/keyword — DONE (verified "money flow" → CMF, MFI)

### A6 Quick layers and saved config
- A6.1 Per-symbol quick-layer persistence — IN_PROGRESS
- A6.2 Remove does not leak between symbols — TODO
- A6.3 Close-swings in templates/layouts — TODO

### A7 Drawings and chart objects
- A7.1 Manager lists quick layers — DONE (session 29)
- A7.2 No orphaned primitives on remove — DONE (session 29)
- A7.3 Fibonacci viewport reverified — DONE (session 30)

### A8 Fibonacci, Elliott, Harmonic, Chart/Candle patterns
- A8.1 Fibonacci manual+auto viewport — DONE (session 29/30)
- A8.2 Elliott visible draw/erase — DONE (session 28)
- A8.3 Harmonic ratio verification — TODO
- A8.4 Chart pattern detector audit — TODO
- A8.5 Candlestick pattern audit — TODO

### A9 Compare-symbol workspace
- A9.1 Fix primary-switch save-key bug — TODO
- A9.2 Fix relative-mode break→continue — TODO
- A9.3 Await async in object-manager toggles — TODO
- A9.4 Stale-load render fix — TODO
- A9.5 Empty state before chart load — TODO
- A9.6 Test 1-4 symbols, modes, reload — TODO

### A10 Settings and UI/UX
- A10.1 Add meaningful settings with real behavior — TODO
- A10.2 Fix clipped text/overflow/axis ranges — TODO

### A11 Dashboard graphs
- A11.1 Fix P/E distribution overshoot/misformat — TODO
- A11.2 Fix fundamentals bar graph — TODO
- A11.3 Audit other dashboard charts — TODO

### A12 Data, API, refresh, deployment
- A12.1 Audit data sources (done in session 30 sub-agent) — DONE
- A12.2 Document refresh/scheduler reality — TODO
- A12.3 Implement safe refresh mechanism (opt-in) — TODO

### A13 Import/export/persistence
- A13.1 Recent-search dropdown — TODO
- A13.2 Validate import schemas — TODO

## Part B — Scanners, algorithms, strategy research

### B1 Inventory
- B1.1 Scanner registry inventory — TODO
- B1.2 Algorithm registry inventory — TODO

### B2 Scanner info buttons
- B2.1 Every scanner has info button — TODO

### B3 Scanner catalogue/search
- B3.1 Polished catalogue like indicators — TODO

### B4 Scanner candidate catalogue
- B4.1 Implement genuinely distinct scanners (target subset) — TODO

### B5 Algorithm library
- B5.1 Expand algorithm library (target subset) — TODO

### B6 Strategy engine
- B6.1 User-defined conditions — TODO

### B7 Breakout/pullback/market scans
- B7.1 Unified scanning workspace — TODO

### B8 Market ribbon
- B8.1 Re-verify ribbon — DONE (session 28)

### B9 Advanced analysis layers
- B9.1 15+ analysis layers — TODO

## Part C — Quantitative finance, valuation, portfolio, Monte Carlo

### C1 Company valuation workbench
- C1.1 DCF/valuation module — TODO

### C2 Fundamental data and ownership
- C2.1 Ownership intelligence — TODO

### C3 Monte Carlo engine
- C3.1 GBM/bootstrap/correlated simulation — TODO

### C4 Statistical strategy validation
- C4.1 Hypothesis testing, bootstrap, walk-forward — TODO

### C5 Portfolio optimization
- C5.1 Efficient frontier, HRP, Black-Litterman — TODO

### C6 Multi-timeframe and relative strength
- C6.1 Verify MTF confluence + rolling beta — DONE (session 30)

### C7 Breakout/pullback/event studies
- C7.1 Event study framework — TODO

### C8 Volume/floorsheet/microstructure
- C8.1 Volume profile (exists) — DONE

### C9 Risk management
- C9.1 Risk workspace — TODO

### C10 Industry deep dives
- C10.1 Industry workspace — TODO

### C11 DCF and equity research projects
- C11.1 Research project workflow — TODO

## Cross-part integration
- INT.1 Indicators searchable in chart workspace — DONE
- INT.2 Info panels show correct formulas — DONE
- INT.3 Params affect calculations — DONE
- INT.4 Indicators render in right place — DONE
- INT.5 Scanners use canonical calcs — TODO
- INT.6 Scanner outputs explain rules — TODO
- INT.7 Algorithms use correct input data — TODO
- INT.8 Chart analysis inspectable/removable — DONE
- INT.9 New objects in manager — DONE
- INT.10 Saved layouts preserve prefs — TODO
- INT.11 Quick layers persist — IN_PROGRESS
- INT.12 Compare mode works — TODO (broken, fix A9)
- INT.13 Fibonacci viewport preserved — DONE
- INT.14 Elliott visible — DONE
- INT.15 Harmonic ratios correct — TODO
- INT.16 Chart patterns detected — TODO
- INT.17 Candlestick patterns explained — TODO
- INT.18 Dashboard graphs corrected — TODO
- INT.19 Market data honest freshness — DONE
- INT.20 API refresh matches deployment — TODO
- INT.21 Valuation preserves units — TODO
- INT.22 Monte Carlo reproducible — TODO
- INT.23 Statistical tools no lookahead — TODO
- INT.24 Portfolio calcs correct — TODO
- INT.25 Scanner/algo search works — TODO
- INT.26 Every new module has info button — TODO
- INT.27 Every visible control has real behavior — TODO
- INT.28 Missing data handled — DONE
- INT.29 No existing feature broken — TODO
- INT.30 No production changes — DONE

## Research
- R.1 60+ distinct sources inspected — IN_PROGRESS
- R.2 20+ Reddit threads — TODO
- R.3 Source log with URL/date/reliability — TODO