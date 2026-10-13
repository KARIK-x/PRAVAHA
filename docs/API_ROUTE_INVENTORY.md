| Method | Path | Purpose | Class | Tests | Status |
|---|---|---|---|---|---|
| POST | `/api/backtest` | Backtest | read-only | api | TEST |
| GET | `/api/bars/{symbol}` | Bars | read-only | api | TEST |
| GET | `/api/bars/{symbol}/indicator` | Indicator | read-only | api | TEST |
| GET | `/api/dashboard` | Dashboard | read-only | api, audit_a_fixes | TEST |
| POST | `/api/floorsheet/import` | Floorsheet Import Route | mutating | api | TEST |
| GET | `/api/floorsheet/sessions` | Floorsheet Session List | read-only | api | TEST |
| GET | `/api/floorsheet/summary` | Floorsheet Summary Route | read-only | api | TEST |
| POST | `/api/forecast` | Forecast | read-only | api | TEST |
| POST | `/api/forecast/compare` | Forecast Compare | read-only | api | TEST |
| GET | `/api/forecast/models` | Forecast Models | read-only | api | TEST |
| POST | `/api/fundamentals/import` | Fundamentals Import Endpoint | mutating | api | TEST |
| GET | `/api/fundamentals/summary` | Fundamentals Summary Endpoint | read-only | api | TEST |
| GET | `/api/fundamentals/{symbol}` | Fundamentals For Symbol | read-only | api | TEST |
| GET | `/api/health` | Health | read-only | api | TEST |
| GET | `/api/indicators` | Indicators | read-only | api | TEST |
| GET | `/api/journal` | Journal Entries | read-only | api, audit_a_fixes | TEST |
| POST | `/api/journal` | Journal New | mutating | api, audit_a_fixes | TEST |
| GET | `/api/journal/stats` | Journal Statistics | read-only | api, audit_a_fixes | TEST |
| DELETE | `/api/journal/{entry_id}` | Journal Delete Entry | mutating | api, audit_a_fixes | TEST |
| GET | `/api/journal/{entry_id}` | Journal One | read-only | api, audit_a_fixes | TEST |
| PATCH | `/api/journal/{entry_id}` | Journal Patch | mutating | api, audit_a_fixes | TEST |
| GET | `/api/journal/{entry_id}/grade` | Journal Grade Entry | read-only | api, audit_a_fixes | TEST |
| POST | `/api/planning` | Planning | read-only | api | TEST |
| POST | `/api/planning/grade` | Planning Grade | read-only | api | TEST |
| GET | `/api/portfolio` | Portfolio | read-only | api | TEST |
| POST | `/api/portfolio/manual` | Portfolio Manual | mutating | api | TEST |
| DELETE | `/api/portfolio/manual/{symbol}` | Portfolio Delete Manual | mutating | api | TEST |
| GET | `/api/portfolio/transactions` | Portfolio Transactions | read-only | api | TEST |
| POST | `/api/portfolio/transactions` | Portfolio Add Transaction | mutating | api | TEST |
| DELETE | `/api/portfolio/transactions/{tx_id}` | Portfolio Delete Transaction | mutating | api | TEST |
| GET | `/api/quality` | Quality | read-only | api | TEST |
| POST | `/api/rank` | Rank | read-only | api | TEST |
| POST | `/api/research/ask` | Research Ask | read-only | api | TEST |
| GET | `/api/research/topics` | Research Topics | read-only | api | TEST |
| GET | `/api/research/{symbol}` | Research Symbol | read-only | api | TEST |
| POST | `/api/screen` | Screen | read-only | api | TEST |
| GET | `/api/screen/export.csv` | Screen Export | read-only | api | TEST |
| GET | `/api/screen/presets` | Screen Presets | read-only | api | TEST |
| GET | `/api/securities` | Securities | read-only | api, audit_a_fixes | TEST |
| GET | `/api/sources` | Sources | read-only | api | TEST |
| GET | `/api/status` | Status | read-only | api | TEST |
| GET | `/api/strategies` | Strategies | read-only | api | TEST |
| POST | `/api/walk-forward` | Walk Forward Endpoint | read-only | api | TEST |
| GET | `/api/written-pdf/records` | Written Pdf Records | read-only | api | TEST |
| POST | `/api/written-pdf/review` | Written Pdf Review | mutating | api | TEST |
| GET | `/api/written-pdf/summary` | Written Pdf Summary | read-only | api | TEST |
