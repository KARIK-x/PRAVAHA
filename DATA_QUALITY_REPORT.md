# MEGA TOOL — DATA QUALITY REPORT
Audit date: 2026-10-17

## Market data
- Source: stored NEPSE daily OHLCV (data/dev/release, 515,327 bars). Provider label: yonepse (delayed public source).
- Freshness: data_as_of 2026-10-15 (stale by ~2 days relative to audit date). Staleness is shown in the UI.
- Live feed: gated (17 sources review_required). Not activated. Honest labeling in UI ("delayed public source — not a live feed").
- Intraday/tick: NOT AVAILABLE. No intraday data collected. Footprint/tick charts BLOCKED.
- OHLC validation: bars filtered for non-null close; invalid OHLC handled (open/high/low default to close).
- Corporate actions: prices are unadjusted (stated in chart meta).

## Relative strength
- Benchmark: NEPSE index series (published files, not live). Available (1 series). 1382 aligned bars for NABIL. Coverage 2020-07-29 → 2026-10-15.
- Excess = stock return - index return (percentage points, never annualised or labelled alpha).

## Fundamentals
- Source: CSV import (written PDF / manual). Reporting-period metadata tracked. Missing data distinguished from zero.

## Kronos input
- Only eligible observed bars supplied. Chronologically ordered. OHLC validated. Missing bars handled. Context limit respected per variant.

## Limitations
- No intraday data → no footprint/tick/intraday analysis.
- Live feed gated → no real-time quotes.
- Retired tickers: no successor mappings guessed; require evidence.
- Some market-data exports exist but are not consumed by price features (documented, not integrated).