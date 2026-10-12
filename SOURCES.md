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
| Symbols imported | **372 (all)** — full fetch 2026-10-12 |
| Rows stored | **514,018** daily OHLCV bars |
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

Re-checked with a single informational GET each on **2026-10-12**. Reachability is
recorded because a future session should not have to re-derive it; nothing was
downloaded in bulk and no source was scraped.

| Source | URL | Status | What it offers | Why not wired |
| --- | --- | --- | --- | --- |
| ShareSansar company pages | `sharesansar.com/company/<SYMBOL>` | **HTTP 200** (265 KB) | The HTML itself exposes `symbol` and **`sector`** per company (e.g. `NABIL` → `Commercial Bank`) | Per-company financial reports are served by a **CSRF-protected AJAX POST**. A public page does not imply permission to automate collection, so nothing is scraped. Filling `sector` from here is an owner decision (`TASK_QUEUE.md` T-11) |
| ShareSansar Scraper archive | `omitnomis.github.io/ShareSansarScraper` | **HTTP 200** | Bulk OHLCV workbook `Data/combined_excel.xlsx` — ~41 MB, `Last-Modified: 2026-10-11`, no login or paywall | **No LICENSE on the archive either.** A candidate cross-check for the GitHub dataset once licensing is settled (`TASK_QUEUE.md` T-15) |
| nepsedata.com | `nepsedata.com` | **HTTP 200** | The report claims an index series 2003–2026 | **That index claim was not verified.** Listed as a candidate, not as a source |
| Nepal Rastra Bank | `nrb.org.np` | **HTTP 200** | Macro/sector data | Not attempted for market data |
| nepsealpha.com | `nepsealpha.com` | **HTTP 403** | — | Refuses the request |
| SEBON | `sebon.gov.np` | not retested | Fundamentals, disclosures | Publications, not an API |
| CDSC | `cdsc.com.np` | not retested | Settlement data | Fetch timed out previously |
| merolagani | — | not retested | Fundamentals, news | Page-based |

**Rejected outright, with the evidence:**

| Candidate | Report's claim | Why it was rejected |
| --- | --- | --- |
| `setTLSVerification(False)` | Needed to reach the official API | Measured `ssl_verify_result 0` — there is **no certificate error**. The observed failure is an HTTP/2 `PROTOCOL_ERROR`, and forcing HTTP/1.1 yields an empty reply. The recommendation addresses a problem that does not exist |
| `NepseUnofficialApi` | Would get past the 401 | The official endpoint answers `401 WARNING: UNAUTHORIZED ACCESS`. Automating a token scheme to pass that is an access-control bypass, which this project does not do |

## Local import (always available)

`megatool import FILE` accepts a user-provided local CSV or Parquet file and validates
it before storing. This is the guaranteed fallback when no network source is reachable,
and is documented in `docs/DATA_SOURCES.md` §1.2.

## Provenance rules

- Every stored price bar carries `source` and `retrieved_at`.
- Test fixtures are labelled `SYNTHETIC-TEST-FIXTURE` and are never mixed with real data.
- Floor-sheet imports record the source label and a content hash, so re-importing the
  same file cannot double-count a session.
- Records from `WRITTENdata.pdf` carry a page reference and extraction confidence,
  and are marked as extracted, not authoritative. Every settlement or total is
  self-checked against its own arithmetic, and disagreements are flagged rather than
  smoothed over.
- Fundamentals carry `source`, `source_ref`, `period_end`, `unit` and a
  `verification` level (`extracted` → `reviewed` → `verified`). A record with no
  source cannot be stored at all, and the ratio guards refuse unreviewed inputs.
- Nothing in this project scrapes. ShareSansar's `sector` field is *known to be
  available* in its public HTML, and is still not collected, because reachability
  is not permission.

See `docs/DATA_SOURCES.md` for the full detail and `docs/WRITTEN_DATA_PDF_AUDIT.md`
for the PDF extraction record.
