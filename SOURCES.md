# Data Sources

Every source the application can use, with its **verified** status as of 2026-10-12.
Statuses reflect what was actually executed and observed, not what was hoped for.

| Status | Meaning |
| --- | --- |
| `IN USE` | Successfully retrieved and stored this session |
| `BLOCKED` | Reachable but refuses access without authentication |
| `INSPECTED` | Reachable; publishes pages, not a machine-readable API |
| `FAILED` | Attempted and did not work |

## In use

### `github.com/Aabishkar2/nepse-data`

| Attribute | Value |
| --- | --- |
| Status | `IN USE` |
| Type | Third-party GitHub repository (community-maintained) |
| URL | https://github.com/Aabishkar2/nepse-data |
| Symbols available | 372 |
| Symbols imported | 60 |
| Rows stored | 89,580 daily OHLCV bars |
| Coverage | 1995-07-20 → 2026-10-09 |
| Licence | **No LICENSE file published.** Treated as personal local use only, with per-row attribution. `data/` is git-ignored so nothing is redistributed. |
| Update frequency | Unknown; `retrieved_at` is stored per row |
| Known limitations | End-of-day closes only; **unadjusted** for bonus/rights; no index data; no corporate actions; no fundamentals |

This is the only market-data source actually wired into the app. It is downloaded by
`megatool fetch` and stored in DuckDB under a per-row `source` label and
`retrieved_at` timestamp.

## Blocked

### Official NEPSE API

| Attribute | Value |
| --- | --- |
| Status | `BLOCKED` |
| Base URL | https://www.nepalstock.com/api/nots/ |
| Evidence | `megatool probe` on 2026-10-12: HTTP 401 on `/api/nots/nepse-data/market-open`. 11 endpoints probed during the session; all returned 401. |
| Reason | Requires an authenticated NEPSE user session |
| Response | Not used. No credential handling, no token reverse-engineering, no bypass attempts. A `probe()` helper is kept so the block can be re-checked rather than re-argued. |

The UI states on every surface that prices are **stored** end-of-day closes, not live
quotes. No index value is shown because no index source is available.

## Inspected, not wired

These were inspected during research (see `docs/RESEARCH_REGISTER.md`) and found to
publish human-readable pages rather than documented APIs:

| Source | URL | What it offers | Why not wired |
| --- | --- | --- | --- |
| NEPSE floor sheet | https://www.nepalstock.com/floor-sheet | Session trade prints | Page-based; import used instead (`megatool floor`) |
| NEPSE listed companies | https://www.nepalstock.com/company | Company profiles | Page-based |
| SEBON | https://www.sebon.gov.np/ | Fundamentals, disclosures | Publications, not an API |
| CDSC | https://cdsc.com.np/ | Settlement data | Fetch timed out |
| Nepal Rastra Bank | https://www.nrb.org.np/ | Macro/sector data | Not attempted for market data |
| merolagani / sharesansar | — | Fundamentals, news | Page-based |

## Local import (always available)

`megatool import FILE` accepts a user-provided local CSV or Parquet file and validates
it before storing. This is the guaranteed fallback when no network source is reachable,
and is documented in `docs/DATA_SOURCES.md` §1.2.

## Provenance rules

- Every stored price bar carries `source` and `retrieved_at`.
- Test fixtures are labelled `SYNTHETIC-TEST-FIXTURE` and are never mixed with real data.
- Floor-sheet imports record the source label and a content hash, so re-importing the
  same file cannot double-count a session.
- Records from `WRITTENdata.pdf` (when integrated) carry a page reference and
  extraction confidence, and are marked as extracted, not authoritative.

See `docs/DATA_SOURCES.md` for the full detail and `docs/WRITTEN_DATA_PDF_AUDIT.md`
for the PDF extraction record.
