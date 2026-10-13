# Session Handoff

This file exists so the next session (or the owner) can pick the project up without
re-deriving anything. It records **what was executed and observed**, not what was intended.

Last updated: 2026-10-12.

---

## 1. How to run it

```bash
cd "Downloads/AI trading NEPSE"
uv sync                     # dependencies into ./.venv (Python 3.12.3)
uv run megatool init        # create/upgrade the local databases
uv run megatool fetch       # download real NEPSE history (network)
uv run megatool serve       # web terminal at http://127.0.0.1:8710
uv run pytest               # 796 tests, ~35 s
```

The server binds `127.0.0.1` only. Nothing listens on the network interface.

## 2. What exists now

| Layer | Files |
| --- | --- |
| Data | `megatool/config.py`, `db.py` (SQLite, schema v2), `market_store.py` (DuckDB), `quality.py`, `datasources/`, `ingest.py` |
| Indicators | `megatool/ta/` — 28 indicators, decorator registry, per-output warm-up; `ta/swings.py` — swing points, market structure, breaks of structure |
| Analysis | `scanner.py`, `backtest.py`, `forecast.py`, `research.py`, `floorsheet.py` |
| Personal state | `portfolio.py` (ledger-derived), `journal.py`, `planning.py` |
| Interface | `api.py` (FastAPI, 47 routes), `cli.py` (incl. `megatool floor import|summary`, `megatool walk-forward`), `web/static/` (11 tabs) |
| Tests | `tests/` — 796 tests across 22 files |
| Docs | `docs/ARCHITECTURE.md`, `DATA_SOURCES.md`, `TECH_STACK_DECISIONS.md`, `RESEARCH_REGISTER.md`, `PROJECT_STATUS.md`, `TESTING.md`, `SOURCES.md`, `DECISIONS.md`, `KNOWN_BUGS.md`, `TEST_RESULTS.md`, `TASK_QUEUE.md`, this file |

### Data actually in the store

- **514,018 real daily bars, 372 symbols** (all of them), coverage 1995-07-20 →
  2026-10-09. Expanded from 60 symbols on 2026-10-12 with `uv run megatool fetch`.
- Source: `github.com/Aabishkar2/nepse-data` (372 symbols available; **no LICENSE file**,
  so: personal local use, per-row attribution, `data/` git-ignored, nothing redistributed).
- Official NEPSE API is **BLOCKED** (HTTP 401 on all 11 probed endpoints) — see
  `docs/DATA_SOURCES.md` §2.1. `megatool/datasources/nepalstock_official.py` keeps a
  `probe()` so the block can be re-checked, not re-argued.
- Quality sweep of the real rows: `open` outside the day range in ~15% of rows, `close`
  outside in 2 of 9,561, overall suspect rate 1.31%, AHPC has 9 `high_low_inverted` rows.
  Problems are **flagged, never deleted**.

### The PDF

- `WRITTENdata.pdf` (52 pages, 7.3 MB) sits in the project root. It was moved there
  from `~/Downloads/AI Trading Nipsy/Written Data.pdf`.
- It is a **handwritten, fully scanned** document with **no text layer**.
- Automated OCR was run on all 52 pages with tesseract 5.5.0 and **failed on 42**
  — tesseract is built for printed text, not handwriting. Records are transcribed
  visually; the AI inspected **all 52 pages** and inventoried each one.
- It is git-ignored: private trading records, never committed.
- **Extraction infrastructure is complete and tested** (`docs/`):
  - `megatool/written_pdf.py` — page rendering (PyMuPDF), `ExtractedRecord`
    provenance (page, source_ref, confidence, review status), validators
    (symbol/price/quantity/EPS/settlement reconciliation), idempotent
    `import_records` + `query_records`.
  - schema v3 — `pdf_imports`, `pdf_records`; every record carries its source
    page, extraction confidence, and review status.
  - CLI — `megatool pdf import|summary|list`.
  - API — `GET /api/written-pdf/records`, `GET /api/written-pdf/summary`.
  - **PDF Journal tab** (9th tab) — summary, records table, filters, empty state,
    plus per-row **review / reject** buttons wired to `POST /api/written-pdf/review`.
  - **Floor Sheet tab** (10th tab) — paste-and-import, session / symbol / Top-N
    filters, and panels for totals, buyers, sellers, symbols, pairs, HHI
    concentration, sessions and imports.
  - Research assistant — includes *reviewed* PDF records as cited findings.
  - 24 tests in `tests/test_written_pdf.py`.
- The **real store holds 0** `pdf_records` — nothing was imported. The
  64-record `extracted_sample.json` is a git-ignored preliminary artifact of
  the superseded Tesseract pass and is not a data source; nothing enters the
  portfolio or journal without explicit validated entry.
- Docs: `docs/WRITTEN_DATA_PDF_AUDIT.md` (page inventory),
  `WRITTEN_DATA_DICTIONARY.md`, `WRITTEN_DATA_VALIDATION_REPORT.md`,
  `WRITTEN_DATA_IMPORT_GUIDE.md`.

## 3. Commits this session

| Commit | Contents |
| --- | --- |
| `3e02461` | Phase 0–5: config, SQLite schema, DuckDB store, quality checks, 3 source adapters, ingest |
| `b84ffa5` | Indicator engine, 28 indicators |
| `16156cc` | Scanner, HTTP API, CLI, web UI |
| `6ee4f27` | Architecture / data-source / decision / research-register docs |
| `361eb22` | Backtesting Lab |
| `56f369b` | Portfolio ledger, trading journal, trade planning |
| `e33680b` | Forecasting Lab and Research Assistant |
| `e94baa0` | Floor-sheet import and analysis |
| `f2e644f` | Web UI: Research, Portfolio and Journal tabs; two silent-data-loss fixes |
| `12a2ec3` | `megatool floor` CLI (import / summary) |
| `3e53cbd` | Fix every confirmed finding from Audit A and Audit B (2 CRITICAL, 4 HIGH, M/L items) |
| `2446e6a` | Expose `comparable` (win-rate denominator) in journal stats; fix vacuous test |
| `2b390a8` | Docs: create `TESTING.md` and `SOURCES.md`; refresh all stale counts |
| `b90eda5` | Written Data.pdf: extraction module, schema v3, tests |
| `9b2e2fb` | `megatool pdf import\|summary\|list` CLI |
| `d22a95b` | Written Data.pdf cross-validation report |
| `b2c0548` | Research assistant includes PDF records as cited findings |
| `927be9f` | `/api/written-pdf/records` and `/api/written-pdf/summary` |
| `5f11ce9` | Web UI: PDF Journal tab (9th tab) |
| `f400a54` | **Audit B fixes**: real page count, confidence filter, `record_type` 400 |
| `5f16f03` | PDF **review workflow** + **journal-only research** fallback; fixes 2 bugs I introduced |
| `a05a2c3` | **Floor Sheet tab** (10th tab); defines the missing `.good`/`.bad` cell classes |
| `f708210` | **CLI**: `megatool pdf review --ids ... --status ...` (third review surface) |
| `9714ec5` | **Full-market fetch**: 60 → **372 symbols** (514,018 bars); docs + PDF cross-validation re-run |
| `092ce95` | **Multi-factor ranking** (`megatool/ranking.py`, `POST /api/rank`, Screener panel) + **settlement-sign defect** fix (B-01) |
| `2806181` | **Fundamentals Lab** (`megatool/fundamentals.py`, schema v3→v4, 3 endpoints, 11th tab) |
| *(prior commits)* | … plus the T-09/T-16/T-24/B-17/B-18 and docs commits listed in `TASK_QUEUE.md` |
| `23fba2e` | **Route inventory**: closed the last API coverage gap (`DELETE /api/portfolio/transactions/{tx_id}` success path), added `scripts/route_inventory.py` (in-process, exits non-zero if any route lacks tests) and `docs/API_ROUTE_INVENTORY.md` |
| `dc6cb97` | **Tradeability gate** — excluded symbols last traded >30 days before T from the walk-forward universe. A genuine defect fix that made the result **worse**, reported as such |
| `329501c` | **Report loader defect (§2.4)** — `walk_forward_report.py` bypassed the B-17 invalid-row filter, contaminating every headline number; corrected figures + `docs/RANKING_VALIDATION_REPORT.md` + `RESEARCH_REGISTER` D12 |
| *(this commit)* | Serve-bind auth warning, route-classification sync tests, rank-panel validation banner, corrected stale counts across docs |
| *(primary-reference session)* | Read the 104-page project overview PDF in full; feature-by-feature audit of the 12 core areas |
| *(this commit)* | **Swing-point & market-structure engine** — `megatool/ta/swings.py`, `GET /api/bars/{symbol}/structure`, **Swings** chart overlay, 22 new tests (796 total), route inventory 46 → 47 |

### Work done this session that is *not* a code commit

The research report `MEGA_TOOL_RESEARCH_REPORT.md` was evaluated claim by claim
against the running code. Findings (all reproduced in `DECISIONS.md`):

| Report claim | Verdict |
| --- | --- |
| "64 OCR attempted extractions" | **Refuted** — 64 is the row count of the git-ignored visual-transcription sample; the real store has 0. `raw_ocr/` holds 52 files, 24 non-empty, all gibberish. |
| "Tesseract/Apple Vision cannot read handwriting — Confirmed" | **Refuted for this document** — benchmarked: Apple Vision 90.2% numeric recall vs Tesseract 4.3%. The report cited a blog post; the claim had never been tested here. |
| "`setTLSVerification(False)`" | **Rejected** — measured `ssl_verify_result 0`; there is no certificate error. The failure is HTTP/2 `PROTOCOL_ERROR`. |
| "Use `NepseUnofficialApi`" | **Rejected** — the official endpoint answers 401 `WARNING: UNAUTHORIZED ACCESS`; automating a token scheme to pass that is an access-control bypass. |
| "Adopt `backtesting.py`" | **Moot** — `megatool/backtest.py` with 32 tests already exists and is honest about its placeholder fee. |
| nepsedata.com has index data 2003–2026 | **Not verified** — the host is reachable (200), but the index claim was not confirmed. Listed as a candidate, not a source. |

Also: the 4 documents the report claimed existed (`TASK_QUEUE.md`,
`TEST_RESULTS.md`, `KNOWN_BUGS.md`, `DECISIONS.md`) did not — they are now
created. The "web search failure" the report diagnosed was this harness's own
tool returning `unknown: "Web search cancelled"` three times, not an app config
problem.

## 4. Decisions worth not re-litigating

1. **DuckDB access is serialised with an `RLock`.** Empirically necessary: 8 concurrent
   threads without it produced 95 bad reads out of 3,200; with it, zero.
2. **`get_bars(limit=N)` means the most recent N bars**, returned ascending.
3. **Indicators align to price by trading date, never by array index.** The index-aligned
   version plotted an SMA across ~1,600 points against a 857-point price series.
4. **Positions are derived from the transaction ledger.** `portfolio_positions` exists
   only for holdings that predate the tool and have no trade history; a conflict is
   flagged, and the ledger wins.
5. **The Research Assistant is a rules engine, not an LLM.** No key exists in this
   project and no local model fits 8 GB RAM. Shipping anything that called itself an AI
   would be dishonest labelling.
6. **Forecasting leads with the naive baseline.** A smooth projected line is easy to
   produce and easy to misread, so the headline number is the RMSE ratio against "use
   yesterday's close", and a model at or above 1.0 says `NO DEMONSTRATED SKILL`.
7. **Backtesting fills at the next bar's open by default** and refuses shorting (NEPSE
   has no retail shorting). A `same_close` mode exists but is labelled optimistic.
8. **Both databases are redirected to a throwaway path for every test** by an autouse
   fixture in `tests/conftest.py`.

## 5. Defects found and fixed (all observed, not theorised)

### From the two audits (2026-10-12)

| # | Defect | How it surfaced | Fix |
| --- | --- | --- | --- |
| A1 | Forecast hold-out rows were misdated when a stored close was NaN | Audit A, re-verified by hand | dates masked with the same finite mask as values |
| A2 | PATCH /api/journal/{id} with invalid data returned 500 | Audit A, executed | route catches `JournalError` → 400 |
| A3 | NaN/infinity passed validation; inf was stored and poisoned derived figures | Audit A, executed | `math.isfinite` guards on price, fees, avg_cost, capital, journal numerics |
| A4 | `notes` alias discarded on PATCH when `outcome_notes` already existed | Audit A, executed | alias resolved before the merge |
| A5 | `update_entry` skipped the cross-field validation `create_entry` enforces | Audit A, executed | validation extracted to `_validate`, called by both |
| A6 | Valuation mixed prices from different dates with no per-position date | Audit A, executed | `price_as_of` on each position + staleness flag |
| A7 | `/api/securities?q=(` → 500; unescaped regex | Audit A, executed | `re.escape` |
| A8 | One absurd quantity aborted a whole floor-sheet import | Audit A, executed | per-row skip + plausibility bound |
| A9 | Same file re-imported under a different session label double-counted | Audit A, executed | loud warning |
| A10 | `traded_at` on import was unvalidated free text | Audit A, executed | ISO validation → 400 |
| A11 | `stored_trades` meant two different things | Audit A, executed | both paths return the session total |
| A12 | Fractional CSV quantities silently rounded | Audit A, executed | per-row warning |
| A13 | Negative `limit`/`top` silently dropped rows | Audit A, executed | `ge=1` bounds |
| A14 | `followed_plan: 1.7` truncated to 1 | Audit A, executed | require exactly 0/1 |
| A15 | `high_252`/`low_252` computed over 250 sessions | Audit A, executed | renamed to `high_250s`/`low_250s` |
| A16 | `directional_accuracy_pct` measured against naive but not named so | Audit A, executed | renamed `directional_accuracy_vs_naive_pct` |
| B1 | Journal stats crashed with 500 on a legal thesis-only entry | Audit B, re-verified | unpriced entries counted separately, excluded from win rate, explained |
| B2 | Counterparty shares divided by the shown subset, not the session | Audit B, re-verified | denominator is the whole scope |
| B3 | `Rs. 1,000` parsed as 0.1 | Audit B, re-verified | currency prefix stripped, validated |
| B4 | Impossible exit (−5, NaN) graded as a real stop | Audit B, re-verified | validated → PlanError → 400 |
| B5 | Backdated sell accepted, corrupting realised P&L | Audit B, re-verified | validated against holdings as of `traded_at` |
| B6 | Typo'd journal field silently dropped | Audit B, re-verified | unknown fields rejected by name |
| B7 | Sizing gave no signal when the budget cannot buy one unit | Audit B, re-verified | explicit warning |
| B8 | Affordability cap did not disclose that fees are excluded | Audit B, re-verified | warning states it |

### From this session's Audit B (2026-10-12) — new PDF module

| # | Defect | How it surfaced | Fix |
| --- | --- | --- | --- |
| P1 | `import_records` stored a magic number `52` as the PDF's page count | reading the code against the document | derived from the PDF itself; regression test reads `pdf_imports.page_count` |
| P2 | `min_confidence` filter always included `high` + `medium`, so `min_confidence=high` returned medium records | walked the ordered-level logic | proper ordered filter: the requested level and everything above it; 4-level test |
| P3 | `GET /api/written-pdf/records?record_type=...` passed a raw string to code that calls `.value` on it → **HTTP 500** on every request | executed against a running server | endpoint validates the type → **400** naming valid types; CLI already exits 1 |

### From this session's robustness pass (2026-10-12)

| # | Defect | How it surfaced | Fix |
| --- | --- | --- | --- |
| R1 | The unreviewed-PDF warning was **inverted**: it claimed "none are reviewed yet" for records that *were* reviewed, because `pdf_findings` only ever holds reviewed rows | reading the code after wiring it to the UI | query all records, surface reviewed, count the rest; warning now names the actual unreviewed count |
| R2 | The ternary sat **inside** the list literal, so an empty case appended `[]` to `warnings` — the UI rendered an empty bullet | same read-through | moved the conditional outside the list |
| R3 | `pdf_findings` were returned by the API but **never rendered** — the whole integration was invisible in the Research tab | grepped `app.js` for `pdf_findings` | `renderPdfFindings()`; wired into both the ask and report paths |
| R4 | A symbol in the handwritten PDF but not in the 60-symbol store (TPC, SAHAS) returned a bare **404**, making the journal unreachable for exactly those names | tested the review flow on TPC | `journal_only_answer()`; states "No stored price history" rather than hiding it. Symbols with neither still 404 (regression test) |
| R5 | A store with no `pdf_records` table raised a raw `sqlite3.OperationalError` (a 500 waiting to happen) | unit test hit it directly | catches *only* "no such table" → treated as "nothing extracted yet"; other errors still raise |
| R6 | `.good` / `.bad` cell classes were **never defined in styles.css** — the PDF table's confidence and review colouring did nothing | wrote the same classes into the Floor Sheet tab | defined `.good { color: var(--up) }` and `.bad { color: var(--down) }` |
| R7 | The research report head rendered `as of null · 0 bars since undefined` for a journal-only symbol | traced the journal-only path through the UI | head text branches on `d.journal_only` |

### From earlier in the session

| # | Defect | How it surfaced | Fix |
| --- | --- | --- | --- |
| 1 | A test helper omitted its `db_path`, so **14 synthetic journal rows were written into the owner's real database** during a normal test run | `test_journal.py` failures led to inspecting the real DB | Rows identified and deleted; the helper now requires the path; an autouse fixture makes the whole class of mistake impossible. A full suite run afterwards leaves the real DB empty — verified |
| 2 | A stub `GET /api/portfolio` was still registered **before** the real implementation and silently answered instead of it | ruff F811, then reading the route order | Stub deleted; the route table in `ARCHITECTURE.md` §5 records that literal paths must precede `{param}` patterns |
| 3 | Indicator values were aligned to the visible window **by array index** | browser check against pandas | aligned by trading date (`web/static/app.js` `alignedSeries`) |
| 4 | `get_bars(limit=N)` returned the **oldest** N bars, so every chart range showed decade-old history | browser verification | semantics changed to most-recent N |
| 5 | 8 threads sharing one DuckDB connection: **95 bad reads / 3,200** | concurrency test | store-level `RLock` |
| 6 | Seasonal-naive minimum-data guard was computed from the **full** series, so it passed and then crashed once the hold-out was sliced off | forecast test | requirement is now `period + holdout`; clear `ForecastError` |
| 7 | The 3-month relative-strength figure was measured from each symbol's **first stored value**, silently turning it into a lifetime figure | research test | measured from the first valid value inside the window; regression test added |
| 8 | `update_entry` raised on a missing id instead of returning `False` | journal test | returns `False`; the API maps it to 404 |
| 9 | Backtest POST without a `Content-Type` returned a 422 that the UI rendered as `[object Object]` | browser | request sets the header; errors are flattened for display |
| 10 | `megatool init` under a running server produced a raw DuckDB traceback | CLI test | friendly explanation, exit 1 |

### My own bugs, caught by the audit process

| # | Defect | How it surfaced |
| --- | --- | --- |
| M1 | My regression test asserted `body["comparable"] == 2 if "comparable" in body else True` — passes vacuously when the key is missing. The key **was** missing | Reading the module's actual return dict |
| M2 | My first live re-check returned 500 and I nearly reported a defect | It was the stale server process running pre-fix code. Confirmed the fix was in source, restarted, re-ran |

## 6. Known gaps — the honest list

1. ~~60 of 372 symbols imported.~~ **RESOLVED**: all 372 are in (514,018 rows);
   the fetch is repeatable and idempotent.
2. ~~Multi-factor ranking is not built.~~ **RESOLVED (2026-10-12)**:
   `megatool/ranking.py` + `POST /api/rank` + a Screener panel. 369 of the 372
   real symbols rank; every score decomposes into per-factor contributions that
   sum back to it. **Still missing:** the factors are price/volume only — P/E,
   P/B, dividend yield, index-relative and sector-relative rank are all *declared
   unavailable at zero weight* rather than faked.
3. **Fundamentals Lab: mechanism built, store empty.** CSV import, provenance,
   reporting periods, units, verification levels and ratio guards are built and
   tested (schema v4, 11th tab), but the store holds **0 records** because no
   verified source is connected — and ShareSansar's per-company reports sit
   behind a CSRF-protected AJAX POST, so nothing is scraped. **News/Events** are
   still not implemented at all.
4. **Floor-sheet analysis is implemented but has never been run on a real sheet** — it is
   unit-tested against synthetic CSVs only. It now has a **Floor Sheet web tab** (paste,
   import, filter, all seven panels), verified in-browser with a synthetic 5-row sheet;
   it has never been exercised against a real published floor sheet. Import a real session
   to close this.
5. **`security_master.sector` is NULL for every one of the 372 symbols.** The source
   dataset is OHLCV only and `ingest.py:148` hard-codes `None`, which blocks
   sector-relative ranking and peer comparison. ShareSansar company pages *do* expose
   `sector` in their HTML — collecting 372 pages is a scraping decision for the owner,
   not for me (`TASK_QUEUE.md` T-11).
6. **Bounded Research Agent is not built, and cannot be.** Web search returned
   `unknown: "Web search cancelled"` on all three attempts — an environment limitation,
   not an auth or config problem (that hypothesis was tested and disproved). The
   deterministic rules engine works and refuses predictive questions correctly, but it
   has no live-data path.
7. **No index or sector data anywhere**, because no source is available. The dashboard
   deliberately shows no index value.
8. **Prices are unadjusted** for bonus and rights issues, so every "return" in the
   forecast, research and scanner output is a price change, not a total return.
9. **The backtest's NEPSE cost/tax assumptions are a labelled placeholder.** The report
   quotes 0.24–0.36% commission, 0.015% SEBON, Rs 25 DP charge, 7.5%/10% capital gains
   tax and T+2 — **none verified**, and web search is unavailable here, so none was
   hard-coded. Needs an authoritative source (`TASK_QUEUE.md` T-12).
10. **A fabricated correction was found and reversed in the PDF work.** An earlier
    audit recorded page 21 settlement 9A as buy `177,609.76` / sell `120,579.43`,
    found they did not balance to the recorded net of `65,550.33`, and "corrected" the
    buy to `186,129.76` *because that value balanced*. Re-reading the page image on
    2026-10-12 gives **77,609.76 / 12,059.43 / 65,550.33**, which balance exactly.
    The 8,520 NPR discrepancy never existed. `186,129.76` is withdrawn everywhere
    (`KNOWN_BUGS.md` B-02, closed B-16).
11. **Extracted values are not safe for accounting.** Against the corrected ground
    truth Apple Vision scores **94.6% numeric / 75.0% exact** over the 5 benchmark
    pages (Tesseract: 4.3% / 3.3%). It still drops digits on dense pages — page 18 is
    84% numeric. Arithmetic self-checks are the mitigation, and item 10 is the reason
    they must flag a row and never edit it (`KNOWN_BUGS.md` L-07).
12. **Local vision-language models remain untested.** Ollama 0.5.7 refuses every vision
    model with `412: requires a newer version` (latest v0.40.3). Updating an installed
    application is a machine change I left to the owner.
13. **The third-party dataset licence is unresolved.**
14. **PDF transcription is the open work** — the extraction infrastructure is
    complete and tested (render → transcribe → validate → import → review), and
    Apple Vision now reads all 52 pages as a first pass (**94.6% numeric**,
    versus Tesseract's 4.3%). Human verification is what remains: **6 of 52**
    pages have been opened by eye (19, 20, 21, 23, 28, 30), **5 of 52** have a
    settlement transcribed from them, **15 settlements** are `verified`, and
    **0 of 52 pages are fully transcribed**. Page 20 was inspected and yielded
    no record; its sample records were never imported — the real store holds
    **0** `pdf_records`. Two read blocks disagree with themselves (pages 19 and
    28) and are recorded as written rather than repaired. See
    `docs/WRITTEN_DATA_VALIDATION_REPORT.md` and the S-01…S-06 findings in
    `KNOWN_BUGS.md`. The benchmark gives the practical route: Apple Vision as a
    first pass, arithmetic checks to flag disagreements, human reading of the
    page itself before anything is called verified.

## 7. Verification evidence

- `.venv/bin/python -m pytest -p no:warnings` — **796 passed, 0 failed** (2026-10-13), 22 test files.
- `.venv/bin/python scripts/smoke_live.py` — live server, real store: **36 of 46 routes
  probed, 36 expected, 0 unexpected, exit 0**; the 10 mutating routes are skipped by design.
- `ruff check` and `ruff format` — clean.
- All **ten** web tabs exercised in a real browser (Playwright) with **0 console errors**;
  the refusal path, the oversell rejection, the empty-journal "—" and the PDF tab's
  empty state were each read back from the DOM. Screenshots in `docs/screenshots/`.
- Floor-sheet analysis and the PDF import verified end-to-end against **throwaway**
  `MEGATOOL_DATA_DIR` stores (second server instance), so the owner's store stayed clean.
- The **PDF review workflow** and the **journal-only research answer** were exercised in
  the browser as well as the API: a row's review button moved reviewed 1 → 2, and asking
  about TPC (no bars) answered from the journal while ZZZZ (no bars, no records) still
  returned 404.
- Live endpoints exercised with `curl` against the running server. Full evidence table in
  `PROJECT_STATUS.md` §5.
- Two audit passes on the PDF module: Audit A (functional — every workflow executed)
  and Audit B (independent correctness review — 3 defects found and fixed, each with a
  regression test). Earlier audits: 45 regression tests in `tests/test_audit_a_fixes.py`.

## 8. What the next session should do, in order

Mirrors `TASK_QUEUE.md`, which carries the same list with acceptance criteria.

0. **Continue the advanced-analysis engine (T-26 → T-27 → T-28).** The swing
   and market-structure engine shipped this session (T-A12) and is the shared
   primitive the specification's mandatory Fibonacci (§5), Elliott Wave (§4),
   harmonic (§7), chart-pattern (§6) and support/resistance (§14) modules all
   need. In order: **T-26 Fibonacci** (pure arithmetic on top of the swings;
   print the anchoring methodology and label 50% a market convention, not a
   Fibonacci ratio), then **T-27 candlestick patterns** (self-contained; needs
   explicit tolerances and *context*, not isolated labels), then **T-28
   Elliott/harmonic candidates** (report competing counts with invalidation
   levels, never one asserted count). Every one of these must stay labelled
   **DETECTED**, never a validated signal.
1. **Continue the page-by-page PDF transcription (T-09).** Page 21 is done — its
   four settlements are visually verified, and the re-read overturned a fabricated
   correction (gap 10). The measured route now works end to end: run Apple Vision
   across all 52 pages (`scripts/run_vision_ocr.py`, orientation-aware, resumable),
   let the settlement/total arithmetic self-checks flag disagreements, and visually
   review only the flagged rows. Pages 18–33 (the trading records) are the highest
   yield because their arithmetic self-checks; pages 19 and 23 are already parsed
   and queued for review, and 20, 22, 24–33 are not yet extracted.
2. **Ask the owner about an Ollama upgrade (T-10)** — the one part of the
   handwriting benchmark left undone. Ollama 0.5.7 refuses every vision model
   with `412`; latest is v0.40.3. Updating an installed application is a machine
   change, so it needs approval. If approved, benchmark a small vision model on
   the *same five pages* against Apple Vision before adopting anything.
3. **Ask the owner about sector data (T-11)** — `security_master.sector` is NULL
   for all 372 symbols, which blocks sector-relative ranking and peer
   comparison. Preferred: the owner supplies a `symbol → sector` CSV (import
   path is a small sibling of the fundamentals one). Alternative: the owner
   authorises ShareSansar collection; the field is in that site's public HTML.
4. **Verify the NEPSE cost/tax/settlement assumptions against an authoritative
   source (T-12)** — SEBON, NEPSE or a broker notice, ideally cross-checked
   against one of the owner's own contract notes. Then make them named,
   configurable presets carrying a source and a date. **Do not hard-code the
   report's figures**; they remain unverified and the backtest's fee rate is
   still a placeholder.
5. **Import a real floor sheet (T-13)** and check the analysis against the
   published page. It has only ever run on synthetic CSVs.
6. **Populate the Fundamentals Lab.** The mechanism is complete and tested; it
   needs a real, permitted source. Whatever is imported must carry reporting
   period, unit, source and verification level — the ratio guards will refuse
   anything else by design.
7. ~~Walk-forward validation of the ranking (T-16).~~ **Done 2026-10-12–13, and
   the ranking failed.** Top quantile underperformed the bottom in every window;
   no alternative factor weighting passed either. Three defects were found and
   fixed along the way (tradeability gate, exact-date forward returns, the
   report loader's missing invalid-row filter) — each left the result unchanged
   or *worse*, never better. Nothing here is a trading signal. Read
   `docs/RANKING_VALIDATION_REPORT.md` before touching the ranking. The one
   open research thread: low-volatility was the only positive factor, but it is
   positive only in the window it was found in, so testing it needs **fresh
   out-of-sample data** (a later period or another market) — do not re-test it
   on 2018–2026 and call the answer validation.
8. ~~Widen coverage to all 372 symbols.~~ **Done 2026-10-12** — all 372 are in
   (514,018 rows). Re-run `uv run megatool fetch` to refresh; stop the server first,
   since DuckDB allows only one writer.
9. **Re-check the official NEPSE API with `probe()` occasionally** — do not work
   around it, and never store credentials.
