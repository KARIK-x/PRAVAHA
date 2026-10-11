# Data Sources

Every stored row carries `source` (who published it) and `retrieved_at` (when we fetched
it). Nothing in this file is inferred — items marked **NOT VERIFIED** were not confirmed
this session and are labelled as such.

---

## 1. Sources actually in use

### 1.1 Public GitHub NEPSE daily dataset — **AVAILABLE, IN USE**

| Field | Value |
| --- | --- |
| URL | `https://github.com/Aabishkar2/nepse-data` |
| Access | HTTPS GET of raw CSV files, no key, no session |
| Checked | 2026-10-11 (fetched); re-checked 2026-10-11 |
| Status | **AVAILABLE** |

What it provides:

- ~**372** symbols with daily `open/high/low/close`, `volume`, `turnover`, `%change`
- history back to **1995**; the newest rows observed were dated **2026-10-09**
- one CSV per symbol, updated by the upstream project

How Mega Tool uses it:

- adapter `megatool/datasources/nepse_data_repo.py`, verified live
- `megatool fetch --limit 12` loaded **23,102** rows across 12 symbols, coverage
  2009-11-25 → 2026-10-09 (per-symbol spans differ; the earliest is 2009 because those
  are the symbols fetched, not because 1995 data is absent upstream)

**Licensing caveat (unresolved).** The repository publishes **no LICENSE file**. The data
is therefore used for personal, local research only, with attribution kept on every row
(`source` column) and repeated in the UI (chart header + Data & Quality tab). It is not
redistributed by this tool: `data/` is git-ignored, and CSV export produces files only on
the owner's machine. If upstream ever adds a licence that forbids this use, ingestion must
stop — see `TECH_STACK_DECISIONS.md` §4.

**Known characteristics of this dataset** (measured, not assumed — 9,561 sampled rows):

| Observation | Rate | Handling |
| --- | --- | --- |
| `open` falls outside the day's `low..high` range | **~15%** of rows | flagged `open_outside_range`, severity **`info`** (too common to be a per-row error — it is how this source publishes) |
| `close` outside `low..high` | 2 of 9,561 rows | flagged `close_outside_range`, severity `review` |
| overall "suspect" rate | **1.31%** | kept, flagged, visible in the UI |
| `high < low` (impossible) | 9 rows in symbol AHPC | flagged `high_low_inverted`, severity `invalid` |
| long-horizon volume outliers | common | flagged `volume_spike`, severity `review` |

Price **adjustment**: this dataset is **unadjusted** for bonus/rights issues. The UI says
so next to every chart. Any long-horizon return computed from it is a price return, not a
total return.

---

### 1.2 Local file import — **AVAILABLE, GUARANTEED FALLBACK**

| Field | Value |
| --- | --- |
| Source | any CSV/Parquet the owner provides |
| Access | local filesystem |
| Status | **AVAILABLE** |

`megatool import <path>` loads a file through the same validation and provenance path as
network ingestion. This is the offline/guaranteed path: if the GitHub dataset disappears
or changes format, imported files still work. Labelled with the file path as `source`.

---

## 2. Sources deliberately NOT used

### 2.1 Official Nepal Stock Exchange API — **BLOCKED**

| Field | Value |
| --- | --- |
| URL | `https://www.nepalstock.com/api/nots/` |
| Checked | 2026-10-11 |
| Status | **BLOCKED — HTTP 401 on every endpoint probed** |

The public site is an Angular SPA. Its own bundle (`main.*.js`) calls a REST API rooted at
`/api/nots/`. Endpoints found in that bundle:

```
GET  api/nots                        daily index
GET  api/nots/securities
GET  api/nots/company/list
GET  api/nots/sector
GET  api/nots/nepse-data/market-open
GET  api/nots/lives-market
GET  api/nots/nepse-data/marketdepth/{securityId}
POST api/nots/nepse-data/floorsheet
POST api/nots/nepse-data/today-price
GET  api/nots/news/notices
GET  api/nots/news/media/company-news
```

Each was probed directly with plain HTTPS GET and returned:

```
HTTP 401  <html><head><title>Error</title></head>
          <body>WARNING: UNAUTHORIZED ACCESS</body></html>
```

The site obtains a bearer token from
`storageService.getCurrentUser().accessToken`, refreshed through
`authenticate/refresh-token` — that token belongs to a **logged-in NEPSE user**.

**Why we do not fetch it.** Getting that token would mean either using the owner's exchange
credentials or reverse-engineering the client-side token generator to get around an access
control. Mega Tool does neither. The adapter (`nepalstock_official.py`) is written and has
a `probe()` that reports this status, but `fetch()` raises `SourceUnavailable`.

**What this costs the product (honest list):**

| Missing capability | Consequence |
| --- | --- |
| NEPSE index / sector indices | the dashboard shows **no index value at all** rather than a fake one |
| official floor sheets | floor-sheet analysis must run on **imported** files only, and will say so |
| live prices / market depth | nothing in this app is real-time; every panel is dated `data_as_of` |
| official company disclosures | fundamentals/news must come from elsewhere |

This is the single biggest limitation of the project. If NEPSE publishes a documented
public API with terms permitting personal use, `nepalstock_official.py` can be completed
against it without touching any other module — that is the point of the adapter interface.

---

## 3. Sources checked but not wired in

| Source | Checked | Finding | Design influence |
| --- | --- | --- | --- |
| `https://www.sebon.gov.np/` | 2026-10-12 | Reachable. Regulator portal: statutes/acts/circulars, IPO & FPO listings, right-share and bonus-share registers, prospectuses, "Quarterly Statistics" and annual reports as **publications**. Content largely in Nepali. **No machine-readable market API observed.** | Fundamentals/disclosures cannot be scraped from a documented API → the Fundamentals Lab must accept **manual/CSV entry** and record provenance per field rather than promising automatic disclosure updates. |
| `https://www.cdsc.com.np/` | attempted 2026-10-12 | **NOT VERIFIED** — HTTP fetch timed out. | none yet; do not rely on CDSC data until actually fetched |
| Web search (this session) | 3 attempts | **BLOCKED** — the search tool returned "Web search cancelled" three times. | the research register is limited to sources fetched directly; nothing was invented to fill gaps |

---

## 4. Provenance & labelling rules (enforced in code)

1. **No row without origin.** `source` and `retrieved_at` are `NOT NULL` in the schema and
   required by `upsert_bars`.
2. **Synthetic never mixes with real.** Fixtures are labelled `SYNTHETIC-TEST-FIXTURE`
   and written only to throwaway databases created by `tmp_path` in tests.
3. **Everything is dated.** API responses carry `data_as_of`; the UI shows
   "Data as of … / no live feed — historical dataset only" in the header on every screen.
4. **Stale and incomplete are visible.** `GET /api/status` reports `live_feed_connected:
   false`; the Data & Quality tab shows first/last bar, last retrieval time, and a
   per-symbol flag breakdown.
5. **Flags are never silently deleted.** `quality.py` only annotates.
6. **Attribution travels with the data.** Every chart repeats its source, and the footer
   links to the Data & Quality tab.

---

## 5. Current store (as of 2026-10-11)

| Metric | Value |
| --- | --- |
| Symbols stored | 12 |
| Bars stored | 23,102 |
| First bar | 2009-11-25 |
| Latest bar | 2026-10-09 |
| Last retrieved | 2026-10-11 |
| Symbols available upstream | ~372 |
| Live feed | **not connected** |

The store currently holds the first 12 symbols alphabetically (ACLBSL … AVYAN). Symbols
such as NABIL/NICL/NMB are **not** stored, so `/api/bars/NABIL` correctly returns 404 —
that is a coverage limit, not a bug. Widen it with `megatool fetch --limit 60`.
