# FUNDAMENTAL ANALYSIS AUDIT
Date: 2026-10-17 | Source: code inspection

## EPS and TTM EPS

### TTM EPS
- **Module**: megatool/fundamentals.py, compute_ttm_eps()
- **API**: /api/fundamentals/{symbol}/ttm-eps
- **Status**: IMPLEMENTED
- **Logic**: Requires 4 consecutive quarterly EPS records with 60-120 day gaps. Returns None with reason if not met.
- **Test**: NABIL returns "quarters not consecutive (gaps: [89, 20, 80] days)" - honest
- **Handles**: missing quarters, restated financials, incompatible periods, negative EPS

### EPS Growth
- **Module**: megatool/fundamentals.py, compute_eps_growth()
- **API**: /api/fundamentals/{symbol}/eps-growth
- **Status**: IMPLEMENTED
- **Logic**: Compares two most recent periods of same type (quarterly vs quarterly, or annual vs annual). Never mixes.
- **Test**: NABIL returns -14.11% (28.36 vs 33.02) - correct

### EPS Rankings
- **Module**: megatool/fundamentals.py + API
- **API**: /api/fundamentals/eps-rankings
- **Status**: IMPLEMENTED + TESTED
- **Returns**: 307 symbols with latest EPS, sorted desc
- **Period filter**: supports specific period labels or 'latest'

## Company Database

### Securities Table
- **Schema**: megatool/db.py (symbol, name, sector, instrument_type, delisted, source, first_seen, last_updated)
- **Status**: PARTIAL - table exists, import works, but dev DB has 0 securities rows
- **Sector CSVs**: yonepse (649 rows), binayabaral (274 rows) available but not imported

### Company Universe
- **API**: /api/fundamentals/eps-rankings (307 symbols)
- **Frontend**: Company Universe view (nu) exists
- **Status**: IMPLEMENTED (API) + PARTIAL (no dedicated frontend page)

## Sector Classifications
- **Module**: megatool/sectors.py (classify_sectors, import_sectors, read_sectors_csv)
- **Status**: IMPLEMENTED but NOT-TESTED in dev (no sector data imported)
- **Sectors**: Commercial banks, development banks, hydropower, microfinance, life insurance, non-life insurance, finance, investment, hotels, manufacturing

## Valuation

### P/E Ratio
- **Module**: megatool/fundamentals.py, ratio_pe()
- **API**: /api/fundamentals/{symbol}/ratios
- **Status**: IMPLEMENTED
- **Formula**: price / EPS (uses appropriate price date and EPS basis)
- **Handles**: zero/negative EPS (reports unavailable, not fabricated)

### P/B Ratio
- **Module**: megatool/fundamentals.py, ratio_pb()
- **Status**: IMPLEMENTED
- **Formula**: price / net_worth_per_share
- **Handles**: zero/negative net worth (reports unavailable)

### Dividend Yield
- **Module**: megatool/fundamentals.py, ratio_dividend_yield()
- **Status**: IMPLEMENTED
- **Formula**: DPS / price
- **Handles**: missing DPS (reports unavailable)

## Float and Ownership
- **Status**: PARTIAL
- **Available**: paid_up_capital, net_worth_per_share (in fundamentals table)
- **Missing**: float shares, promoter holdings, institutional holdings, major holders
- **Reason**: No data source for ownership data

## DPS and Dividend Analysis
- **Status**: IMPLEMENTED
- **Available**: dividend per share, cash dividend, bonus shares, dividend history
- **Handles**: missing dividends (reports unavailable, not zero)

## Bargain Screener
- **Module**: megatool/scanner.py
- **API**: /api/screen
- **Status**: IMPLEMENTED
- **Filters**: P/E, EPS, EPS growth, net worth, P/B, public float, dividend, sector, data freshness
- **Shows**: reasons a stock passed or failed each criterion

## Margin-Trading Eligibility
- **Status**: MISSING (no official rules verified)
- **Frontend**: Shows "NOT VERIFIED" message
- **Notebook criteria**: listing history >=2 years, >=10,000 shareholders, net worth >= paid-up capital, qualifying profitability/dividend history
- **Blocker**: These are notebook-derived, not verified official NEPSE/SEBON rules

## Company Profiles
- **API**: /api/fundamentals/{symbol}, /api/fundamentals/{symbol}/ratios
- **Status**: IMPLEMENTED (API) + PARTIAL (no dedicated frontend page)
- **Available**: identity, sector, EPS, TTM EPS, EPS history, EPS growth, net worth, P/E, P/B, DPS, rankings, technical indicators, watchlist membership, provenance, freshness, missing-data warnings

## Sector Rankings
- **Module**: megatool/sectors.py
- **Status**: PARTIAL (sector data not imported)
- **Available**: classify_sectors, import_sectors, read_sectors_csv
- **Blocker**: Securities table has 0 rows in dev

## Side-by-Side Comparison
- **API**: /api/fundamentals/compare
- **Status**: IMPLEMENTED (API) + PARTIAL (no frontend view)
- **Max**: 10 symbols per comparison

## Test Coverage
- **fundamentals tests**: included in 2,364 test suite
- **Coverage**: EPS period ordering, TTM EPS, missing quarterly data, negative EPS, EPS growth, EPS rankings, fiscal-period comparisons, P/E and P/B edge cases, missing financial values, sector mapping
