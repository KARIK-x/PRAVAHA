# Task queue

Prioritised next work. Status: **DONE**, **BLOCKED** (waiting on an external
fact or a human decision), **NEXT**, **BACKLOG**.

---

## Completed

### Evidence-based completion audit (2026-10-12, this session)

| ID | Task | Evidence |
|---|---|---|
| T-A1 | Reconcile state: code, DB, tests, git | Clean tree before changes; 602 → **650** tests then → **707** (17 files), exit 0; real store row counts (journal/portfolio/pdf/fundamentals) all **0** after runs; PDF untouched (SHA `d7ea6fe4…`, mtime 08:33). |
| T-A2 | Verify the ranking claims independently | 372 → **369 ranked + 3 excluded** (CFL 41, CMB 14, SLBBLP 50 bars, all < `min_bars=60`); accounting balances; weights sum to 1.0; dense ranks; scores descending; 0 unavailable factors in contributions or effective weight. |
| T-A3 | Investigate median-substitution bias | **Confirmed not neutral.** 8 gap symbols; removing them changes 361/361 scores and **284/361 ranks**, max 0.61 pts. Recorded as **L-05**, behaviour pinned by test, not silently "fixed". |
| T-A4 | Audit Fundamentals Lab guards | Real store honestly reports **0**. Three defects found and fixed: **B-13** lakh parser, **B-14** field/unit validation, **B-15** opt-in staleness guard. |
| T-A5 | PDF manifest for all 52 pages | **Done, regenerated honestly.** Manifest covers all 52 pages: 51 with machine text, **4 opened by eye** (19/20/21/23), **3 with a settlement read by eye**, **9 settlements verified**, **0/52 pages fully transcribed**, 52/52 still needing review, **0 records in the real store**. The earlier "46 of 52 never transcribed / 64 records" figure was the superseded Tesseract pass. Full manifest in `docs/WRITTEN_DATA_VALIDATION_REPORT.md`. |
| T-A6 | Correct settlement 9A | **REVERSED.** The task said `177,609.76` → `186,129.76`, but `186,129.76` was invented to make an equation balance. Re-reading page 21 by eye showed the page says **Buy 77,609.76 / Sell 12,059.43 / Net 65,550.33**, which balance exactly. The 8,520 NPR discrepancy this task was written for **never existed**. `186,129.76` is withdrawn everywhere and guarded by a test. See B-02 (reversed). |
| T-A7 | Classify data sources | Distinguished **verified usable** (GitHub dataset — proven by 514,018 ingested rows) from **merely reachable** (ShareSansar, nrb.org.np) and **blocked** (official NEPSE 401, nepsealpha 403). |
| T-A8 | Inspect Ollama, no changes made | See T-10 below. Nothing upgraded, nothing pulled (412 refused before download; model list unchanged at 2). |
| T-A9 | Phase 2 financial-correctness tests | New `tests/test_financial_integrity.py` (**33 tests**, all hand-computed fixtures) + **15** added to fundamentals/written_pdf. |

**Test count: 602 → 650, later 650 → 707 (17 files).** Defects: **B-13, B-14,
B-15 fixed**; B-16..B-18 opened; L-05, L-06 documented. **B-01 and B-02 were
reversed by visual reads of pages 19/21/23** — the "bugs" were in the earlier
audit's readings, not the notebook.

---

## NEXT — highest value first

Each blocker below is recorded with user impact, dependencies, the safe path,
how to validate it, and what needs an owner decision.

### T-09 · Re-verify the PDF transcription page by page — **IN PROGRESS**

* **User impact:** highest. The earlier audit reported a transcription error
  that survived review; on re-reading the page by eye the error turned out to
  be in the audit itself (B-02 reversed, no 8,520 NPR discrepancy ever
  existed). The real exposure is that most of the notebook is machine OCR of
  handwriting and **no page is fully transcribed**.
* **Progress (2026-10-12):** all 52 pages OCR'd with Apple Vision +
  orientation detection (**94.6% numeric**, was 4.3% on Tesseract). Pages
  **19, 20, 21, 23** opened by eye; settlements on **19, 21, 23** transcribed
  and visually verified — **9 records**. Page 20 inspected, nothing transcribed
  from it, but its circled labels independently corroborate page 19's block
  grouping. **0 of 52 pages fully transcribed.**
* **Remaining:** pages 20/22/24–33 (the other settlement and transaction
  pages), then the fundamentals pages 1–18 and 34–52.
* **Technical dependency:** `scripts/run_vision_ocr.py` +
  `scripts/vision_ocr_batch.swift`, `megatool/written_transcribe.py`
  (`extract_settlements`, `parse_money`), `scripts/build_transcription.py`.
* **Data dependency:** `WRITTENdata.pdf` only. Never uploaded, never modified.
* **Safe path:** Apple Vision as *first pass* → arithmetic self-checks
  (`buy − sell = net`, totals vs line items) to **flag** disagreements →
  visual read of the page itself → record what the page says, including
  discrepancies, **without changing a figure to make it balance**.
* **Validation:** every settlement/total on every transcribed page either
  reconciles or is marked unreconcilable **with a reason**; `page_fully_transcribed`
  only ever turns true once a whole page has actually been read.
* **Owner decision:** none to start. Review of flagged rows *is* the owner's
  job — that is the point of the review state.

### T-12 · Verify NEPSE cost, tax and settlement assumptions — **BLOCKED**

* **User impact:** every backtest's net return is currently unverifiable; a
  wrong cost figure silently changes whether a strategy looks profitable.
* **Technical dependency:** none — `BacktestConfig.fee_rate` is already a
  configurable, labelled PLACEHOLDER, and `_assumptions()` already surfaces it.
* **Data dependency:** an **authoritative** source (SEBON / NEPSE / broker
  circular) with an effective date, ideally cross-checked against one of the
  owner's own contract notes.
* **Safe path:** when a source exists, make the figures **named presets**,
  each carrying `{source, retrieved_at, effective_from}`; keep the default
  explicitly `UNVERIFIED`.
* **Validation:** a test asserting that no preset without a `source` and a
  date can be selected; a contract-note figure reproduces to the paisa.
* **Owner decision:** **required** — web search is unavailable in this
  environment (B-12), so I cannot verify these myself. **Do not let me
  hard-code the report's numbers.**

### T-11 · Owner decision: sector data — **BLOCKED**

* **User impact:** blocks sector-relative ranking, peer comparison, and the
  `sector_percentile` factor (currently declared `unavailable` at zero weight —
  honestly, not faked). 372 of 372 symbols have `sector = NULL`.
* **Technical dependency:** a small `symbol → sector` importer as a sibling of
  the fundamentals importer; both already have proven import/idempotency patterns.
* **Data dependency:** a symbol→sector mapping with provenance.
* **Safe path:** **preferred — owner supplies a CSV.** Validated format:

  ```csv
  symbol,sector,source,retrieved_at,observed_date
  NABIL,Banks & Finance,owner-manual,2026-10-12,2026-10-12
  NICA,Banks & Finance,owner-manual,2026-10-12,2026-10-12
  ```
  * `symbol` — uppercase, must already exist in `security_master` (rejected otherwise)
  * `sector` — free text, non-empty; trimmed; case preserved
  * `source` — **required**, free text, stored as provenance
  * `retrieved_at` — **required**, ISO-8601 (when the owner obtained it)
  * `observed_date` — **required**, ISO-8601 (the date the classification describes)
  * duplicate `(symbol, observed_date, source)` → last one wins, reported as `updated`
* **Validation:** row count matches accepted + rejected; every accepted symbol
  exists; re-import is idempotent; `sector_percentile` flips from
  `unavailable` to available **only** when coverage exceeds a stated threshold.
* **Owner decision:** **required.** Alternative — authorise ShareSansar
  collection (field is in that site's public HTML). That is still **scraping**
  and needs explicit permission plus a terms check (no LICENSE on the archive
  either). I will not do it unprompted.

### T-10 · Owner decision: Ollama upgrade for a local vision benchmark — **BLOCKED**

**Inspection result (read-only, nothing changed):**

| Item | Value |
|---|---|
| CLI `/usr/local/bin/ollama` | **0.5.7** |
| Running daemon `/api/version` | **0.5.7** |
| `/Applications/Ollama.app` `CFBundleShortVersionString` | **0.33.3** (stale metadata — disagrees with the daemon) |
| Installed models | **2** — `llama3.2:3.2B` (text-only), `nomic-embed-text:137M` |
| Vision-capable model present | **No** |
| RAM / free disk | 8 GB / 16 Gi free |
| Latest upstream | v0.40.3 (per the error message itself) |

**The HTTP 412 explained.** `POST /api/pull {"name":"qwen2.5vl:3b"}` returns
HTTP 500 wrapping the real status:

```
pull model manifest: 412: The model you are attempting to pull requires a
newer version of Ollama. Please download the latest version at:
https://ollama.com/download
```

`412 Precondition Failed` is Ollama's own **model-registry gate**: the server
reads the manifest, compares the manifest's minimum-client requirement against
its own version, and refuses **before downloading a single byte of weights**.
It is not a network, auth, disk, or RAM error — it is a client-version
mismatch. Nothing was installed (model list verified unchanged at 2).

* **User impact:** low for the product; it blocks only the *optional* VLM
  comparison. Apple Vision already benchmarks at 90.2% numeric recall.
* **Technical dependency:** an Ollama ≥ 0.40.3 install; then a vision model
  ≤ 3B (8 GB RAM ⇒ 3B is the ceiling; a 7B will swap).
* **Data dependency:** the same 5 benchmark pages + ground truth.
* **Safe path:** owner upgrades → `ollama pull qwen2.5vl:3b` (~2 GB) →
  `scripts/score_benchmark.py` on the same five pages → compare against
  Apple Vision's 90.2% / 71.7% / 33-of-46 → **adopt only if it wins**.
* **Validation:** same scorer, same ground truth, same pages; report exact,
  numeric and symbol recall side by side.
* **Owner decision:** **required** — upgrading an installed application is a
  machine change (Rule 8). I have not upgraded anything and will not without
  approval.

### T-13 · Import a real floor sheet — **NEXT**

* **User impact:** floor-sheet analysis has only ever run on synthetic CSVs.
* **Safe path:** import one genuinely published sheet; compare row counts and
  totals against the published page.
* **Validation:** totals match source; any discrepancy is explained, not
  absorbed.
* **Owner decision:** none. Needs a real sheet the owner chooses to provide.

### T-14 · Re-check the official NEPSE API — **BACKLOG**

`uv run megatool probe` re-tests the 401. Never work around it; never store
credentials.

---

## BACKLOG

| ID | Task | Note |
|---|---|---|
| T-15 | ShareSansar Scraper bulk import as a second price source | Workbook verified reachable (~41 MB). Needs a **licensing decision first** — no LICENSE on the archive either. Would give a cross-check against the GitHub dataset. |
| T-16 | Walk-forward validation of the ranking (report §8.5) | Rank monthly using only data up to that month, form top/bottom quartiles, measure next-month spread. Chronological only; no look-ahead. Label as research, not evidence of profit. |
| T-17 | Relative-strength factor | Blocked on an index series (B-10). Declared unavailable today. |
| T-18 | News / Events and multi-factor *fundamental* ranking | Both blocked on T-11/T-12. |
| T-19 | Transcribe PDF pages 18–33 | Settlement arithmetic self-checks make these the highest-yield pages (T-09). |
| T-20 | `TASK_QUEUE.md` / `KNOWN_BUGS.md` upkeep | Update with every fix. |
| T-21 | Decide on L-05 (median substitution) | Computing percentiles over **observed values only** is methodologically cleaner but changes every score. Owner's call. |
| T-22 | Decide on B-17 (`invalid` bars in the read path) | Options: filter `invalid` out of `get_bars`; or expose a `include_flagged` switch defaulting to off; or leave and document. 124 invalid + 13,093 suspect rows are currently consumed by indicator maths. |
| T-23 | Decide on B-18 (renamed-PDF re-import duplication) | Dedupe on `content_hash` alone, or filter `query_records` to the newest `import_id`. |
| T-24 | Store `extraction_method` and an append-only correction history | Both missing from `pdf_records` (manifest, field-provenance table). |
| T-25 | Populate the Fundamentals Lab | Import path is complete and tested; waiting on a permitted source. |

---

## Explicitly not doing

* Reverse-engineering the official NEPSE API's token scheme.
* Disabling TLS verification anywhere.
* Scraping ShareSansar without the owner's authorisation.
* Uploading `WRITTENdata.pdf` to any external service.
* Autonomous live trading, broker/Mero Share credentials, invented trading APIs.
* Upgrading Ollama without approval (T-10).
* Hard-coding Nepal tax/fee figures that have not been verified (T-12).
