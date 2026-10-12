# Project Status

Every row below is labelled with what was **actually executed and observed**. Nothing is
marked working because the code exists. The labels mean:

| Label | Meaning |
| --- | --- |
| `TESTED-PASS` | Feature exists, its tests were run and passed, and it was exercised end-to-end |
| `PARTIAL` | Some of the module works and is tested; a named part of it does not exist |
| `BLOCKED` | Cannot be completed here for a reason outside this codebase |
| `NOT-IMPLEMENTED` | Deliberately not built. The reason is stated |
| `NOT-TESTED` | Code exists but has not been executed/observed |

Test suite: **511 passed, 0 failed** (`uv run pytest`, 2026-10-12). `ruff check` and
`ruff format` clean. Live server verified in a real browser via Playwright.

---

## 1. Feature matrix

| # | Module | Status | Evidence |
| --- | --- | --- | --- |
| 1 | **Data foundation** (ingest, canonical schema, provenance, quality flags) | `TESTED-PASS` | 9,561→89,580→**514,018 real rows / 372 symbols** stored; full-market `fetch` run 2026-10-12 (**372/372 succeeded**, 424,438 new rows, no errors); idempotent re-ingest inserts 0 duplicates; quality sweep **flags, never deletes**: 51,700 rows (10.06%) carry a flag — 40,026 `open_outside_range`, 12,444 `volume_spike`, 417 `close_outside_range`, 204 `price_jump`, 109 `high_low_inverted` |
| 2 | **Market Dashboard** | `TESTED-PASS` | Breadth/movers/most-active render in the browser; the response carries `is_live: false` and shows **no index value** because no index source is available |
| 3 | **Charting Terminal** | `TESTED-PASS` | Candles + volume + 28 indicators; verified in-browser against pandas (SMA 1014.485 / 877.87 matched exactly) |
| 4 | **Stock Scanner** | `TESTED-PASS` | 19 metrics, 4 presets, filter-tree validation with plain-English 400s; 21 scanner tests + 65 API tests |
| 5 | **Multi-Factor Engine** | `PARTIAL` | The scanner's filter tree **is** the multi-factor engine (AND/OR composition, 19 metrics). A ranked/scored factor model with normalisation and weights is **not built** |
| 6 | **Fundamentals Lab** | `NOT-IMPLEMENTED` | SEBON publishes fundamentals as publications, not an API (research register A5). Design is CSV/manual import with per-field provenance. **No fundamental data has ever been fetched**, so no ratio is computed anywhere |
| 7 | **News / Events** | `NOT-IMPLEMENTED` | No machine-readable news source was found (A7/A8). Nothing is scraped |
| 8 | **AI Research Assistant** | `TESTED-PASS` (as a rules engine) | **There is no LLM** — no key, and no local model fits 8 GB RAM. What ships is a deterministic rules engine that cites the window and definition behind every number, and **refuses** predictive/prescriptive questions. 28 unit + 6 API tests |
| 9 | **Forecasting Lab** | `TESTED-PASS` | 6 models, all scored on an unseen hold-out against the naive baseline, with a plain-words verdict (`NO DEMONSTRATED SKILL` where true). 29 unit + 5 API tests |
| 10 | **Backtesting Lab** | `TESTED-PASS` | Long/flat engine, next-bar-open fills, shorting refused, fees+slippage, benchmark and assumptions in every response. 32 tests + a real-data run (ADBL sma_cross 20/50, 3,659 bars, +223.48% vs buy-and-hold +168.95%, maxDD −54.41%, Sharpe 0.43, 44 trades, 9 assumptions) |
| 11 | **Portfolio Intelligence** | `TESTED-PASS` | Positions **derived from the transaction ledger** (the two can never disagree); manual holdings allowed only where no ledger exists; valuation marks to the latest *stored* close and leaves unpriced symbols unvalued and flagged. 29 unit + 8 API tests, plus a live smoke test |
| 12 | **Trade Planning / Risk** | `TESTED-PASS` | R multiples, risk:reward, position size for a fixed fractional risk (rounded down, affordability-capped). A stop above the entry is rejected — NEPSE has no retail shorting. 21 unit + 4 API tests |
| 13 | **Trading Journal** | `TESTED-PASS` | CRUD, win rate, R multiples, plan adherence, per-strategy breakdown; trades without a complete plan are counted in win rate but excluded from R stats **and both are reported**. 30 unit + 5 API tests |
| 14 | **Floor-sheet Intelligence** | `PARTIAL` | Import, validation and analysis are **implemented and tested** (25 unit + 5 API + 9 CLI tests). Reachable three ways: `megatool floor import FILE --date YYYY-MM-DD` / `megatool floor summary`, `POST /api/floorsheet/import`, and the **Floor Sheet web tab** (paste-and-import, session/symbol/Top-N filters, all seven panels). Verified end-to-end against an **isolated** database (second server instance and a throwaway `MEGATOOL_DATA_DIR`) with a synthetic 5-row sheet — totals, HHI and the symbol filter each recomputed by hand — so the owner's store stayed clean. It has **never been run on a real floor sheet** — only on synthetic CSVs |
| 15 | **Bounded Research Agent** | `NOT-IMPLEMENTED` | The web-search tool failed on every attempt this session (register B1–B3). No autonomous agent loop was built; the deterministic Research Assistant (#8) is what exists instead |
| 16 | **PDF records (Written Data.pdf)** | `PARTIAL` | Extraction infrastructure is complete and tested: `megatool/written_pdf.py` (rendering, `ExtractedRecord` provenance, validation, idempotent import, **review workflow**), schema v3 (`pdf_imports`/`pdf_records`), CLI (`megatool pdf import\|summary\|list`), API (`/api/written-pdf/*` incl. `POST /review`), a **PDF Journal tab** with per-row review/reject buttons, and 28 tests. Automated OCR **failed on 42 of 52 pages** (tesseract vs handwriting), so records are transcribed visually; all 52 pages inspected and inventoried (`docs/WRITTEN_DATA_PDF_AUDIT.md`). 64 sample records imported as **unreviewed**. It has **never been run on a fully transcribed sheet**, and no record has entered the portfolio or journal |

## 2. Web UI

Ten tabs, all exercised in a real browser (Playwright) with **0 console errors**.
Screenshots in `docs/screenshots/`.

| Tab | Status |
| --- | --- |
| Overview, Charts, Screener, Backtest, Data | `TESTED-PASS` — earlier browser run; screenshot evidence committed |
| Research | `TESTED-PASS` — cited report rendered for ADBL (33 findings, every row showing value + window + definition, no `[object Object]`, no `undefined`); a predictive question is refused verbatim and does **not** fall back to the full report; forecast comparison shows `NO DEMONSTRATED SKILL` on every model at or above 1.0 |
| Portfolio | `TESTED-PASS` — empty state explicit; a buy valued at the latest stored close with that stated on screen; **oversell rejected with the server's plain-English message** ("cannot sell 500 of ADBL: only 10 held in the ledger"); a symbol with no stored price shows as unvalued with a warning rather than being carried at cost |
| Journal | `TESTED-PASS` — with no closed trades the win rate, avg R and adherence render as **"—", never as 0%**; with real entries, stats/per-strategy/grading work and an ungradable entry shows the server's explanation; the planner returns risk/share, R:R, units, cash used and actual risk |
| Floor Sheet | `TESTED-PASS` — 10th tab. Session/symbol/Top-N filters, paste-and-import box, and all seven panels (totals, buyers, sellers, symbols, pairs, concentration, sessions, imports). Verified on an isolated store with a 5-row synthetic sheet: totals 870 qty / 323,920 amount match the CSV by hand, symbol filter narrows to NICA 450/112,800, buyer HHI 3341 recomputed by hand, import reports "5 of 5 rows (0 skipped)". Real store shows the empty state |
| PDF Journal | `TESTED-PASS` — summary card (records / types / pages covered / reviewed vs unreviewed), an explicit warning that unreviewed records are descriptive not verified, a records table with page + confidence + review status, working symbol / type / page / reviewed-only filters, and per-row **review / reject buttons** (verified: reviewed 1 → 2 in-browser). Empty state reads "Import with: megatool pdf import FILE.json". Verified in-browser on the isolated store (64 records) and the real store (empty state) |

Test rows created during browser verification were deleted through the UI and the API:
the owner's journal, ledger and floor-sheet tables are empty.

## 3. Data sources

| Source | Status |
| --- | --- |
| Official NEPSE API (`nepalstock.com/api/nots/*`) | **BLOCKED** — HTTP 401 on all 11 probed endpoints; a logged-in session is required. No credential use, no token reverse-engineering |
| `github.com/Aabishkar2/nepse-data` | **IN USE** — **372/372 symbols imported** (514,018 rows, 1995-07-20 → 2026-10-09), fetched 2026-10-12. **No LICENSE file**: personal local use with per-row attribution only; `data/` is git-ignored so nothing is redistributed |
| Local CSV import | **AVAILABLE** — the guaranteed fallback, documented in `docs/DATA_SOURCES.md` §1.2 |
| NEPSE index / sector indices | **UNAVAILABLE** — the dashboard deliberately shows no index figure rather than a stale or invented one |
| SEBON / NRB / merolagani / sharesansar | **INSPECTED, NOT WIRED** — reachable, but publish pages and publications, not documented APIs |
| `cdsc.com.np` | **FAILED** — fetch timed out |

## 4. Known issues, in priority order

1. ~~Only 60 of 372 available symbols are imported.~~ **RESOLVED 2026-10-12**:
   `uv run megatool fetch` imported all **372/372** (514,018 rows). The scanner
   now evaluates 372 symbols and relative-strength ranks against 334 peers.
   Kept in the list for history; it is no longer open.
2. **Third-party data licensing is unresolved.** The dataset has no LICENSE file. This is
   acceptable for personal local analysis with attribution and is the reason `data/` is
   git-ignored — but it is not resolved, and the data must not be redistributed.
3. **No live feed, no index.** Everything is end-of-day and delayed by whatever the source
   publishes. The UI says so on every surface that shows a price.
4. **Prices are unadjusted** for bonus and rights issues, so every "return" in the
   Forecasting Lab, Research Assistant and scanner is a *price* change, not a total return.
   NEPSE corporate actions are not available in the imported data.
5. **Fundamentals and News/Events do not exist** (rows 6 and 7), and the **floor sheet
   has never been run on real data** — it is unit-tested against synthetic CSVs only.
   Nothing about real published floor-sheet headers has been proven.
6. **Backtest fills are optimistic at the bar level.** Next-bar-open is honest about
   *when* you could trade, but it assumes the open was available in full size. Liquidity
   and impact are not modelled.
7. **The relative-strength ranking compares the 372 locally stored symbols**, not the
   whole NEPSE market, and uses unadjusted prices. The UI states this. (Before
   2026-10-12 this compared only 60 symbols; the limit is now breadth of the
   market, not a handful of names.)
8. **PDF extraction is transcription-gated.** All 52 pages were inspected and
   inventoried, but automated OCR failed on 42 of them (handwriting defeats
   tesseract), so records enter one page at a time through visual transcription.
   The infrastructure (render → transcribe → validate → import → review) is
   tested end-to-end; 64 sample records are imported as **unreviewed**. The
   remaining work is transcription, not code. See
   `docs/WRITTEN_DATA_PDF_AUDIT.md`.

## 5. Verification log

Evidence, not assertions. Everything below was executed and observed.

| What | How | Result |
| --- | --- | --- |
| Full test suite | `uv run pytest` | **511 passed, 0 failed**, ~20 s |
| Lint / format | `ruff check .`, `ruff format .` | clean |
| Real data in the store | `GET /api/status` on the running server | **514,018 bars, 372 symbols**, 1995-07-20 → 2026-10-09 (was 89,580 / 60 before the 2026-10-12 fetch) |
| Every browser tab | Playwright, clicking through all tabs (8 at the time of this audit) | **0 console errors** |
| Research assistant honesty | Asked "will ADBL go up tomorrow?" | Refused verbatim, listed what it can answer instead, showed no numbers |
| Research citations | Read the rendered table from the DOM | 33 findings for ADBL, every row carrying value + unit + window + definition; zero `undefined`, zero `[object Object]` |
| Portfolio oversell | Sold 500 ADBL while holding 10 | Rejected: "cannot sell 500 of ADBL: only 10 held in the ledger" |
| Journal empty state | Read the stats cells with no closed trades | "—" for win rate, avg R and adherence — not 0% |
| Planning | entry 300 / stop 285 / target 340, 100,000 at 1% | risk/share 15.00, R:R 2.6667, 66 units, 19,800 cash, 990 actual risk (0.99%) |
| Backtest on real data | ADBL sma_cross(20,50), 3,659 bars | +223.48% vs buy-and-hold +168.95%, maxDD −54.41%, Sharpe 0.43, 44 trades, 9 assumptions listed |
| Floor-sheet analysis | Second server instance with `MEGATOOL_DATA_DIR` pointing at a throwaway directory | import 3 rows, re-import adds 0, HHI 5000.0 / 7222.22 **matching the hand calculation**, bad file → 400 naming the missing columns |
| Database isolation | Inspected the real SQLite after every test run and every browser session | journal, ledger, positions and floor-sheet tables all empty |
| CLI under a running server | `megatool init` while `serve` holds the DuckDB lock | friendly explanation instead of a traceback, exit code 1 |
| Journal stats on a legal thesis-only entry | POST then GET /api/journal/stats | **200** with `closed_without_entry_price` and an explanatory warning (was HTTP 500) |
| Counterparty share denominator | 12 buyers × 100 + one × 700, top=10 | BIG reads **36.84%** (was 43.75%); shown shares sum to 84.21%, not a forced 100% |
| Currency-prefixed rate | `Rs. 1,000` in a floor-sheet CSV | parsed as 1000, amount 100,000 (was 0.1 → 10,000) |
| Impossible exit | exit_price −5 and NaN | 400 naming the field (was graded as a real stop) |
| Backdated sell | sell dated before its funding buy | 400 with the reason (was accepted, corrupting realised P&L) |
| Typo'd journal field | `entry_prc` | 400 listing the unknown field (was 200, data silently dropped) |
| PDF page count | import the sample, read `pdf_imports.page_count` | 52, **read from the document** (was a hardcoded magic number) |
| PDF confidence filter | `query_records(min_confidence=high)` on a mixed-confidence set | returns only `high` (was returning `medium` too) |
| PDF record type via API | `GET /api/written-pdf/records?record_type=fundamental` / `garbage` | 200 with 62 records / **400** naming the valid types (was 500) |
| PDF tab, isolated store | Playwright, click the PDF Journal tab | summary 64 records / 6 pages, table renders, symbol filter → 1 TPC row, reviewed-only → "No records match", **0 console errors** |
| PDF tab, real store | Playwright, click the PDF Journal tab | empty state: "No records extracted yet. Import with: megatool pdf import FILE.json", **0 console errors** |
| All 9 tabs, real server | Playwright click-through on :8710 | **0 console errors**; store intact at 89,580 bars / 60 symbols |
| All 10 tabs, real server | Playwright click-through on :8710 after the Floor Sheet tab | **0 console errors**; floor sheet and PDF both correctly empty |
| All 10 tabs after the 372-symbol fetch | Playwright click-through on :8710, then the screener | **0 console errors**; screener returned 29 rows with per-condition explanations |
| Floor Sheet import (UI) | paste a 5-row synthetic sheet, click Import | "Imported 5 of 5 rows (0 skipped)"; totals 870 / 323,920 match the CSV by hand |
| Floor Sheet HHI (UI) | buyers B1 300, B2 300, B4 270 of 870 | HHI **3341** rendered — recomputed by hand as 34.48²+34.48²+31.03² = 3340.7 |
| Floor Sheet filter (UI) | symbol = NICA | totals narrow to 2 prints / 450 qty / 112,800 — matches the CSV rows by hand |
| PDF review (UI) | click a row's "✓ review" | summary moves reviewed 1 → 2, unreviewed 63 → 62; **0 console errors** |
| Research: journal-only (UI) | ask about TPC (no bars, has a journal record) | answers from the journal, headed "No stored price history for TPC"; redundant "No findings." suppressed |
| Research: still 404s | ask about ZZZZ (no bars, no records) | 404 `no stored history for ZZZZ` — the fallback does not weaken it |
| Research: unreviewed hidden | ask about SAHAS (3 unreviewed records) | `pdf_findings: []` plus warnings naming the 3 unreviewed records |
| Cell colouring | `.good` / `.bad` classes used by the PDF table | **were undefined in styles.css** — confidence/review colour did nothing; now defined |
| Full-market fetch | `uv run megatool fetch` (real store, server stopped first) | **372/372 succeeded**, 514,018 rows, 424,438 new, 0 errors, coverage 1995-07-20 → 2026-10-09 |
| Store after fetch | `GET /api/health` | `bars_stored: 514018`, `symbols_stored: 372` |
| Scanner breadth | `POST /api/screen` with `bars_listed >= 60` | **evaluated 372**, eligible 371, passed 369 (was 60 evaluated) |
| Relative-strength breadth | `POST /api/research/ask` ADBL "relative strength" | `peer_median_3m_pct` cites **"median across 334 other stored symbols"** (was 59) |
| PDF ↔ market overlap | 47 sample symbols ∩ stored set | **36 overlap** (was 0 with the 60-symbol set) |
| Journal price vs stored close | p.11 dated 2025-07-04, nearest stored day 2025-07-03 | SBI −0.31%, EBL −1.19%, SCB −2.97% — consistent with the transcription, **not a confirmation** |
| DuckDB single-writer | second process opened the store while the server held it | refused with `Conflicting lock is held` — server stopped before every fetch; no corruption |

## 6. How to run it

```bash
cd "Downloads/AI trading NEPSE"
uv sync
uv run megatool init      # create the databases
uv run megatool fetch     # download real history (network)
uv run megatool serve     # http://127.0.0.1:8710
uv run pytest             # 511 tests
```
