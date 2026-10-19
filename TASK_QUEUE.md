# Task queue

Prioritised next work.

**Status categories** (every task below carries one):

| Category | Meaning | Current members |
|---|---|---|
| **COMPLETED AND VERIFIED** | Built, tested, and exercised end-to-end with evidence recorded | T-A1…T-A12, T-16 *(the validation was run and its result — failure — is verified)*, T-23, T-24, B-17, B-18, route inventory, security pass, **swing/market-structure engine** |
| **IMPLEMENTED BUT NOT FULLY VERIFIED** | The mechanism works and is tested, but has never run on real input | Fundamentals Lab (0 records), Floor-sheet analysis (synthetic only), PDF extraction pipeline (0/52 pages transcribed) |
| **FAILED** | Executed honestly and did not pass | **T-16 ranking validation** — top quantile underperformed the bottom in *every* window; no alternative weighting passed. Recorded, not hidden |
| **BLOCKED BY EXTERNAL INPUT** | Cannot proceed without an owner file, credential, permission or authoritative source | T-11 data (sector CSV; loader is ready), T-12 (verified tax/fee rates), T-10 (Ollama approval), T-13 (real floor sheet), T-15 (licensing), B-09/B-10/B-11/B-12, OmniRoute key |
| **DEFERRED WITH REASON** | Deliberately parked; reason stated | **T-09 (deferred by owner 2026-10-13 — digitized documents are the working references; extraction gaps recorded as limitations, see T-09)**, T-14 (re-check official API), T-17 (needs index data = B-10), T-18 (needs sector data = T-11), T-20, T-21, T-25, News/Events (no machine-readable source, `PROJECT_STATUS` #7), Bounded research agent (web search unavailable, #15) |

---

## Completed

### Evidence-based completion audit (2026-10-12, this session)

| ID | Task | Evidence |
|---|---|---|
| T-A1 | Reconcile state: code, DB, tests, git | Clean tree before changes; 602 → **650** tests then → **709** then → **729** (18 files), exit 0; real store row counts (journal/portfolio/pdf/fundamentals) all **0** after runs; PDF untouched (SHA `d7ea6fe4…`, mtime 08:33). |
| T-A2 | Verify the ranking claims independently | 372 → **369 ranked + 3 excluded** (CFL 41, CMB 14, SLBBLP 50 bars, all < `min_bars=60`); accounting balances; weights sum to 1.0; dense ranks; scores descending; 0 unavailable factors in contributions or effective weight. |
| T-A3 | Investigate median-substitution bias | **Confirmed not neutral.** 8 gap symbols; removing them changes 361/361 scores and **284/361 ranks**, max 0.61 pts. Recorded as **L-05**, behaviour pinned by test, not silently "fixed". |
| T-A4 | Audit Fundamentals Lab guards | Real store honestly reports **0**. Three defects found and fixed: **B-13** lakh parser, **B-14** field/unit validation, **B-15** opt-in staleness guard. |
| T-A5 | PDF manifest for all 52 pages | **Done, regenerated honestly.** Manifest covers all 52 pages: 51 with machine text, **6 opened by eye** (19/20/21/23/28/30), **5 with a settlement read by eye**, **15 settlements verified** (of 19 candidate blocks the parser found), **0/52 pages fully transcribed**, 52/52 still needing review, **0 records in the real store**. The earlier "46 of 52 never transcribed / 64 records" figure was the superseded Tesseract pass. Full manifest in `docs/WRITTEN_DATA_VALIDATION_REPORT.md`. |
| T-A6 | Correct settlement 9A | **REVERSED.** The task said `177,609.76` → `186,129.76`, but `186,129.76` was invented to make an equation balance. Re-reading page 21 by eye showed the page says **Buy 77,609.76 / Sell 12,059.43 / Net 65,550.33**, which balance exactly. The 8,520 NPR discrepancy this task was written for **never existed**. `186,129.76` is withdrawn everywhere and guarded by a test. See B-02 (reversed). |
| T-A7 | Classify data sources | Distinguished **verified usable** (GitHub dataset — proven by 514,018 ingested rows) from **merely reachable** (ShareSansar, nrb.org.np) and **blocked** (official NEPSE 401, nepsealpha 403). |
| T-A8 | Inspect Ollama, no changes made | See T-10 below. Nothing upgraded, nothing pulled (412 refused before download; model list unchanged at 2). |
| T-A9 | Phase 2 financial-correctness tests | New `tests/test_financial_integrity.py` (**33 tests**, all hand-computed fixtures) + **15** added to fundamentals/written_pdf. |

**Test count: 602 → 650, later 650 → 709, later 709 → 729 (18 files).** Defects:
**B-13, B-14, B-15 fixed**; B-16..B-18 opened; L-05, L-06 documented. **B-01 and
B-02 were reversed by visual reads of pages 19/21/23** — the "bugs" were in the
earlier audit's readings, not the notebook.

### Autonomous engineering session (2026-10-12, continuation)

| ID | Task | Evidence |
|---|---|---|
| T-A10 | Reconcile the reported terminal state | Commits `6065623` / `6088232` present, tree clean, `main`. **729 passed** reproduced before touching anything. PDF SHA `d7ea6fe4…` and mtime `Oct 12 08:33:12` unchanged. App DB 16 tables (only `ingestion_log` 5, `schema_meta` 1 non-empty). DuckDB **514,018 bars / 372 symbols** but locked by the still-running prior-session server (PID 54377) — stopped it, confirmed the lock released, restarted with the changed code (PID 10082). |
| T-22 | Decide on B-17 (`invalid` bars in the read path) | **FIXED — invalid rows filtered from all three read paths.** `_NOT_INVALID` applied to `get_bars`, `latest_bars`, `all_closes`, each with an `include_invalid` opt-in, plus `include_flagged` on `GET /api/bars/{symbol}`. `suspect` deliberately kept. Measured: 124 rows excluded, **45/45** symbols' full-history ATR changed, **8** all-time lows corrected from `0.0`, **0** symbols lost a latest price, **0** removed. Tests 729 → **731**. |
| T-A11 | Live end-to-end route verification | New `scripts/smoke_live.py` builds its probe list from the server's own `/openapi.json` so it cannot drift: **36 of 46 routes probed (27/27 GET, 9/9 read-only POST), 36 expected, 0 unexpected, exit 0**; 10 mutating routes skipped by design. First run found **3 probe defects, 0 product defects** — the script was wrong (bad entry_id placeholder, missing `exit_price`), not the API. |
| T-16 | Walk-forward validation of the ranking | **Done — and the ranking failed the test.** New `megatool/walkforward.py` ranks at each period end using only data then available, holds the top/bottom quantiles, and measures the forward return against the universe benchmark and a random-selection baseline. **Every window tested has a negative mean spread** (Q 1995–2007 −11.80%, Q 2008–2017 −1.04%, Q 2018–2026 −3.25%, Q 1995–2026 −3.70%, M 2015–2026 −1.28%; post-tradeability-gate, invalid rows filtered); the long portfolio underperformed the equal-weight benchmark in every window; the observed spread is at/below the **5th percentile of the random distribution in 4 of 5 windows**. Exposed as `POST /api/walk-forward` and `megatool walk-forward`; reproduced by `scripts/walk_forward_report.py`. Finding recorded in `docs/RESEARCH_REGISTER.md` D11 with its caveats; the Priority-Two defect audit and factor attribution are in `docs/RANKING_VALIDATION_REPORT.md` (D12) — **no method passed validation**. |
| T-23 | Decide on B-18 (renamed-PDF re-import duplication) | **FIXED — deduplicated on `content_hash` alone.** Identical sha256 bytes are the same document whatever the file is called, so a renamed copy now reuses the original `import_id` instead of shadowing it; two different files (different bytes) still get separate imports. No schema migration needed. Verified by two new tests (renamed copy → `0 inserted, 4 updated`, query returns each record once; different documents → separate imports). |
| T-24 | Store `extraction_method` and an append-only correction history | **Already implemented — and now tested.** The schema-v5 provenance columns (`extraction_method`, `verification_status`, `original_reading`, `corrected_value`, `correction_history`) and `append_correction` existed in `written_pdf.py`/`db.py` but had **zero test coverage**. Added 5 tests: method stored verbatim (empty stays empty); correction preserves the original reading and appends to history; history is append-only across multiple corrections; a reasonless correction is rejected and an accepted one is marked `corrected_verified`; a correction to a missing record fails loudly. |

**Test count: 729 → 731 (B-17) → 759 (T-16) → 764 (T-24) → 766 (B-18) → 774 (route inventory + serve warning + loader regression) → 796 (swing engine).** No product
defect was found by the live probe; the defects found and fixed this session were
B-17, B-18, and the missing test coverage on the T-24 provenance columns.

### Advanced-analysis engine (2026-10-13)

The specification's repeatedly emphasised **comprehensive technical-analysis
engine** (Elliott Wave §4, Fibonacci §5, chart patterns §6, harmonics §7, price
action §9, support/resistance §14) did not exist: `grep` across `megatool/` for
`elliott|fibonacci|harmonic|gartley|butterfly|candlestick|doji|engulfing`
returned **nothing**. Only the conventional indicator library (28 indicators)
was present.

A feature-by-feature audit against the primary reference
(`ALL THE CONTENT:IDEA MAIN OVERVIEW OF PROJECT.pdf`, 104 pages, read in full)
identified the **swing point** as the shared primitive all six mandatory
modules need. Implemented it once, per §28.2 (shared calculation layer):

| ID | Task | Evidence |
|---|---|---|
| T-A12 | Swing-point & market-structure engine | `megatool/ta/swings.py`, `GET /api/bars/{symbol}/structure`, and a **Swings** chart overlay. Documented fractal rule (strictly above the left window, `>=` the right — so a plateau yields exactly one pivot); alternating HH/HL/LH/LL labels; trend; break-of-structure. **The look-ahead rule is enforced, not merely intended**: every swing carries `confirmed_index`, only confirmed swings are drawn, and an unconfirmed pivot is excluded rather than guessed. Verified by a hand-built zigzag, a **prefix-recomputation causality test**, and the API contract. Tests **774 → 796**; route inventory **46 → 47 routes**, all test-covered; live smoke **37 probed · 37 expected · 0 unexpected · exit 0**. Real store: ADBL 250 bars → 23 swings, every `confirmed_index >= index` |

This is labelled **DETECTED** everywhere — a candidate turning point under
fixed geometric rules, not a validated signal and not a prediction. It unblocks
the next four mandatory modules (Fibonacci, Elliott, harmonics, chart patterns),
each of which now consumes one shared, tested definition instead of inventing
its own.

---

## NEXT — highest value first

Each blocker below is recorded with user impact, dependencies, the safe path,
how to validate it, and what needs an owner decision.

### T-26 · Fibonacci analysis module — **DONE (2026-10-13)** → `TESTED-PASS`

* **Shipped:** `megatool/ta/fibonacci.py`, `GET /api/bars/{symbol}/fibonacci`,
  `tests/test_fibonacci.py` (23) + 8 API tests. See `PROJECT_STATUS.md` #18.
* **One convention, stated once** so no two surfaces can drift: `range = end −
  start` (signed), `retracement = end − range·r`, `extension = end + range·r`.
  Returned as `formula` in every response.
* **Anchor methodology is printed** (§5.1): `anchor_policy` states the rule
  ("most recent confirmed swing high and low"), with `start/end` price, date,
  bar index and high/low kind.
* **50% labelled `family: "convention"`**, never `fibonacci`.
* **Confluence is overlap, never proof** — caveats say *CALCULATED: arithmetic
  on two chosen swing anchors, not a prediction and not evidence any level
  will hold.*
* Hand-verified live on ADBL (range −13.7; 61.8% → 311.7666 ✓; 161.8% → 281.1334 ✓).
* **Owner decision:** none.

### T-27 · Candlestick pattern engine — **DONE (2026-10-13)** → `TESTED-PASS`

* **Shipped:** `megatool/ta/candles.py` + `tests/test_candles.py` (104), wired
  into the workspace's `candlesticks` module. See `PROJECT_STATUS.md` #20.
* **15 patterns** with executable definitions documented in the module
  docstring; `measurements` carry the actual numbers that triggered each one;
  `near_support` is `null` rather than fabricated.
* Context is present as a field (`prior_trend`, `bars_before_pattern`) but the
  "weaker context away from a swing level" acceptance criterion is **only
  partially met**: proximity-to-level context is `null` because this module has
  no access to support analysis. That is stated, not faked.
* **Lint gate closed (session 7):** `ruff check` and `ruff format --check` clean
  on `candles.py` / `test_candles.py`.
* **Owner decision:** none.

### T-29 · Trend / momentum / volatility combined summary — **DELIVERED (2026-10-13)** → `IMPLEMENTED` · `TESTED-PASS` *(module's own suite in flight)*

* **Shipped:** `megatool/ta/summary.py` (parallel worker) + the workspace's
  `trend_momentum_volatility` module, which composes existing `ta/` indicators
  rather than reimplementing them. See `PROJECT_STATUS.md` row 23.
* **The failure was reported, not hidden.** While it was mid-construction the
  workspace showed that module `FAILED` with the real `TypeError` and let the
  other seven complete. That is the Target-6 behaviour working as designed.
* **Two separate data walls, one root cause (B-20).** The module first failed
  on `TypeError`, then on `SummaryError: invalid OHLC` — the same single
  corrupt bar out of 500 that stopped candlestick detection. Two independent
  modules failing on the same record is evidence the fault is in the data.
* **Design decision worth recording:** candlesticks and this summary handle
  that corrupt bar *differently on purpose*. Candlesticks need genuine
  2-3 bar adjacency, so they run on contiguous valid runs only. This summary
  is aggregate statistics, so it drops the bad bar instead — because splitting
  at it would have been worse: on real ADBL data one bad bar at 2026-04-29 cut
  the summary to 391 bars ending **2026-04-28**, five months stale, while
  reporting itself as current. Dropping it yields 499 bars ending 2026-10-09
  with the omission stated as `1 of 500 bar(s) … were excluded … 499 bars,
  2024-07-29 → 2026-10-09`. RSI moved 46.8 → 65.0 as a result, so the staleness
  was not cosmetic.
* **Validation:** 8 integration tests in `test_workspace.py`. Expected values
  are recomputed from **textbook definitions inside the test** — Wilder RSI
  seeded from the SMA of the first 14 moves, SMA 10/30, ROC12, TR-based ATR —
  not by calling the implementation twice. A round-trip check would pass even
  if the smoothing were wrong, because a wrong-but-plausible RSI still lands
  in 30–70.
* **Outstanding:** `tests/test_summary.py` (the module's own unit suite) was
  still being written by the parallel worker and had **6 failing tests** at
  the time of this record. Not counted as green.
* **Owner decision:** none.

### T-30 · OHLC inconsistencies in 7.9% of stored bars — **CLOSED BY OWNER DECISION (document, do not modify data)**

* **User impact:** high and broad — any indicator or candlestick rule reading
  `high`/`low` inherits the distortion, and this is what made candlestick
  detection raise on real ADBL data.
* **Evidence:** 40,568 of 514,018 bars violate OHLC self-consistency. The store
  **already detects** them — `flags` carries `open_outside_range` /
  `close_outside_range` / `high_low_inverted`, and all 115 fully-inverted
  (`high < low`) rows are already `invalid` and excluded. The gap is **40,446
  rows where `open` or `close` sits outside `[low, high]` that stay readable**
  (38,483 marked `valid`, 1,963 `suspect`). See B-20 for the corrected
  breakdown; the earlier "only 124 rows flagged" note was wrong and is
  withdrawn.
* **Owner decision (2026-10-13): document the source convention; change no data
  and no validation rule.** The 40,568 "violators" decompose into **40,013** rows
  that follow the source's `open = previous close` convention (98.5% of them carry
  the previous close exactly, against a 29.5% baseline) and only **555** that are
  genuinely inconsistent — of which 115 (`high < low`) are already `invalid` and
  437 stay readable as `suspect`. Split/bonus mis-adjustment was tested and
  disproved. Evidence and rationale: `docs/DATA_SOURCES.md` §1.1.1; B-20 closed.
  The earlier option (b) — *"mark these 40,446 rows `invalid`"* — is **withdrawn
  as destructive**; it would have deleted 40,013 usable bars.
* **Residual, accepted:** anything reading `open` (candle bodies, gap detection,
  open-fill backtests) sees a substituted open on 7.78% of bars, concentrated in
  2015–2017. Close/high/low indicators are unaffected.


### T-28 · Elliott Wave / harmonic candidates — **DONE (2026-10-14)**

* **Resolved:** the bounded Elliott module (`megatool/ta/elliott.py`) now
  filters to confirmed swings and the harmonic module (`megatool/ta/harmonic.py`)
  implements all five requested definitions — Gartley, Bat, Butterfly, Crab,
  Cypher — on documented published ratio bands, reporting candidates with
  measured ratios, matched bands, invalidation price levels, and
  `certainty="low"` plus an explicit uncertainty note. API routes
  `/api/bars/{symbol}/elliott` and `/api/bars/{symbol}/harmonic` verified live.
* **Design review before UI:** the output-framing review the queue asked for is
  satisfied by the candidate-only contract; a frontend phase should still
  review how these candidates are *displayed* before they reach the dashboard.

### T-09 · Re-verify the PDF transcription page by page — **DEFERRED BY OWNER (2026-10-13)**

> **Owner decision, 2026-10-13:** the original 52-page visual review is
> **deferred**. It is no longer an active blocker for the current development
> phase, and page 29 is no longer the active first target. Do not spend time
> reprocessing those pages unless the owner explicitly asks.
>
> **Working references are the existing digitized documents** — to be used as
> they are, never regenerated, overwritten or reprocessed:
> `WRITTENdata.pdf`, `Written_Data_All_52_Pages_Digitized.xlsx`,
> `Written_Data_Full_Transcription.xlsx`, `trading_ledger_master_data.xlsx`,
> `digitized_trading_ledger_and_notes.pdf` / `.md`, and the derived reference
> CSVs in `data/written_pdf/transcription/`. All verified present, readable and
> correctly git-ignored on 2026-10-13.
>
> **Known extraction gaps — recorded as limitations, not blockers:**
>
> | gap | file | affected information |
> |---|---|---|
> | Page 10 | `Written_Data_Full_Transcription.xlsx` | `ocr_status=gibberish` (60 chars), `transcription_status=none`, `verification_status=not_started` — the one page with **no** usable machine text; a stock/fundamental table |
> | Page 20 | same | `inspected_not_transcribed` — opened by eye, nothing transcribed from it |
> | Page 29 | both workbooks | marked *"OCR FIRST PASS — NOT VERIFIED"*; the raw OCR is gibberish, so settlement figures there are **not** extractable from machine text |
> | 0 of 52 pages fully transcribed | same | 45 partial/OCR-only, 5 with settlements read by eye (19, 21, 23, 28, 30), 1 not started (10), 1 inspected (20) |
> | OCR accuracy unverified on 45 pages | same | the workbook's own warning: benchmarked **~84%** on dense transaction pages; *"every row not listed as read-by-eye … is WRONG often enough to matter"* |
> | Provenance | `Written_Data_All_52_Pages_Digitized.xlsx` | ~~cites a nonexistent `WRITTENdata(1).pdf`~~ **RESOLVED 2026-10-13 — no owner input needed.** Only `WRITTENdata.pdf` exists (exhaustive `find` + Spotlight); it has **52 pages** (Spotlight `kMDItemNumberOfPages` *and* the raw PDF `/Count 52`), **7,281,475 bytes** (matching `docs/WRITTEN_DATA_PDF_AUDIT.md`), and the derivative workbook holds exactly 52 page images. The *authoritative* workbook already names `WRITTENdata.pdf (52 pages, authoritative)` as source and calls the All_52 workbook "preliminary, NOT verified". The `(1)` is a duplicate-download artefact. **Canonical reference: `WRITTENdata.pdf`.** Evidence: `docs/WRITTEN_DATA_PDF_AUDIT.md` §Source-document provenance |
>
> None of these blocks the current phase. They become live again only if a
> specific required figure turns out to be unavailable from the digitized set.
> The history below is preserved as recorded.

* **User impact:** highest. The earlier audit reported a transcription error
  that survived review; on re-reading the page by eye the error turned out to
  be in the audit itself (B-02 reversed, no 8,520 NPR discrepancy ever
  existed). The real exposure is that most of the notebook is machine OCR of
  handwriting and **no page is fully transcribed**.
* **Progress (2026-10-12):** all 52 pages OCR'd with Apple Vision +
  orientation detection (**94.6% numeric**, was 4.3% on Tesseract). Pages
  **19, 20, 21, 23, 28, 30** opened by eye; settlements on **19, 21, 23, 28,
  30** transcribed and visually verified — **15 records** out of the 19
  candidate blocks the parser found. Page 20 inspected, nothing transcribed
  from it, but its circled labels independently corroborate page 19's block
  grouping. **0 of 52 pages fully transcribed.**
* **Progress (2026-10-12, reference pass):** the owner's NotebookLM/ChatGPT
  outputs are now parsed by `megatool/written_reference.py` and cross-checked
  against the eye reads — **27/27 settlement total fields agree, 11/11 readable
  component sides agree, 0 disagreements**. Page 28's 12C was **resolved** on
  that evidence (`buy_total` 77,793.55 → **77,795.55**, original kept in
  `superseded_readings`, status `corrected_verified`); page 30's 12D 0.01 is now
  localised to the written total (S-07). **Nothing was imported into the DB**
  and no visually read figure was changed to make a sum close.
* **Remaining:** pages 22/24/26/27/29/31/32/33 (the other settlement and
  transaction pages), then the fundamentals pages 1–18 and 34–52. The visual
  read pass needs image access, which was off for the reference pass.
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

### T-11 · Owner decision: sector data — **BLOCKED (data) · IMPLEMENTED (loader)**

* **User impact:** blocks sector-relative ranking, peer comparison, and the
  `sector_percentile` factor (currently declared `unavailable` at zero weight —
  honestly, not faked). 372 of 372 symbols have `sector = NULL`.
* **Technical dependency:** `megatool/sectors.py` + `MarketStore.set_sectors()`
  implemented and tested (session 6). The loader stores `sector_source`,
  `sector_retrieved_at` and `sector_observed_date` and refuses malformed dates.
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

## Owner-input register

Exactly what is needed from the owner, in the order it blocks work. Nothing
here is re-requested if it already exists on disk — check before supplying.
Every path is under the project root
`/Users/ashim/Downloads/AI trading NEPSE/`. `data/raw/` is git-ignored, so
nothing dropped there can be committed by accident.

### Required now

Blocks work that is already built or currently in flight.

| # | What | Exact path / form | Schema or values | Blocks | If not supplied |
|---|---|---|---|---|---|
| R1 | **Non-positive price policy** (B-21 / T-31) — *partially decided; one answer still required* | Exact answer needed: **does the 2026-10-13 owner decision ("document the source convention; change no data and no validation rule", made for the `open = previous close` / OHLC-range question, B-20 — closed) also cover `F_NON_POSITIVE`?** Either (a) *confirm* it does — B-21 closes as-is, severity stays `review`, ~10 zero-price rows remain readable and flagged; or (b) *explicitly promote* `non_positive_price` from `review` to `hard`/`invalid` — those rows would then be excluded from calculations (indicators, scans, backtests) but never deleted | B-21 / T-31; `quality.py` `FLAG_SEVERITY`; no historical rows modified either way | Nothing changes silently — rows stay flagged `review` and included; B-21 stays open | *Withdrawn sub-option:* the earlier OHLC-range option **B "mark the 40,568 rows `invalid`" was destructive and is retracted** (only 437 rows were ever genuine candidates; 40,013 are the publishing convention). B-20/T-30 are **closed** by the 2026-10-13 decision recorded in `docs/DATA_SOURCES.md` §1.1.1 — do not re-open them |
| R2 | **Sector mapping** (T-11 / B-07) | `data/raw/sectors.csv` | Header exactly `symbol,sector`. One row per symbol; `symbol` must match the `security_master.symbol` form (e.g. `ADBL`, not `Adbl`). Values are free text NEPSE sector names. Extra columns ignored | 372/372 `security_master.sector` are NULL; blocks **T-18** (sector grouping), sector filtering in the Screener, and sector-relative ranking | Sector features stay absent. **Does not block the six sprint targets** — none of them needs a sector |
| R3 | **Real NEPSE tax & fee rates** (T-12 / B-11) | A message with the numbers, or a file at `data/raw/fees.csv` | Per side: `broker_commission_pct`, `sebon_fee_pct`, `settlement_fee_pct`, `capital_gains_tax_pct`, plus `effective_from` (date) and `source` (URL or document name). **Nepal rates are jurisdiction- and date-specific, so a source is part of the value** | `BacktestConfig.fee_rate = 0.004` is a `PLACEHOLDER` (confirmed in `megatool/backtest.py:41`, and the code says so in its own output). Blocks **S-08 cost attribution** | Backtests keep the placeholder, which the API already prints as `PLACEHOLDER - confirm real …` on every run. Results are never presented as net-of-real-cost |
| R4 | **Official listing-status export** (B-2 / register BLK-3) | Export the company list from `nepalstock.com/company` using your own browser session, saved under `data/raw/` (any format the site offers) | One row per symbol with its official listing/trading status; no schema is imposed — whatever the site exports is recorded as-is with provenance | Official `status` for the security master; authoritative input for **R5** (B-4). Until then eligibility stays conservative: unknown stays unknown, and floorsheet-derived "traded on 2026-10-13" evidence stays labelled *unofficial* | Nothing changes silently. `eligibility_from_meta()` keeps deciding without a status column (tested) |
| ~~R5~~ | ~~**`merged` semantics ruling** (B-4 / register BLK-10)~~ | ~~Owner ruling received and implemented~~ | ~~Evidence-based status distinction; `MERGED` stored as its own non-tradable status, never converted to `DELISTED`; scanner/rank exclude `DELISTED`/`SUSPENDED`/`MERGED` by default~~ | ~~Eligibility treatment of the 21 merged symbols~~ | ~~Implemented; no production data changed~~ |

**`price_bars` schema** (context for the withdrawn OHLC-range options under old-R1/B-20;
retained for reference) — must match the store exactly:
`symbol` (VARCHAR), `trading_date` (DATE), `open`/`high`/`low`/`close` (DOUBLE),
`volume` (BIGINT), `turnover` (DOUBLE), `percent_change` (DOUBLE), `source`
(VARCHAR), `retrieved_at` (TIMESTAMP), `validation_status` (VARCHAR:
`valid`|`suspect`|`invalid`). Row-validity constraints the old options had to respect:
`high >= max(open, close)`, `low <= min(open, close)`, `high >= low`.

### Later feature

Needed for a feature that is *not* yet started; supplying early is fine but
nothing waits on it today.

| # | What | Exact path / form | Blocks | Notes |
|---|---|---|---|---|
| L1 | **ShareSansar bulk workbook** + licensing answer (T-15) | Decision first (yes/no to bulk import), then the workbook under `data/raw/` | A second price source for cross-checking the GitHub dataset | The archive has no LICENSE either, so this is a rights question before it is a data question |
| L2 | **A real floor sheet** (T-13) | Any published NEPSE floor-sheet CSV at `data/raw/floor_YYYY-MM-DD.csv` | Running floor-sheet analysis on real data | The whole import/validation/analysis path is built and tested, but **only ever exercised on a synthetic 5-row sheet** |
| L3 | **Index series** (B-10) | `data/raw/index_nepse.csv` with header `date,close` | **T-17** relative strength; an index line on the dashboard | Dashboard currently shows *no* index figure rather than a stale or invented one |
| L4 | **A news/events source** (§24) | A permitted machine-readable feed or export under `data/raw/` | The News/Events module (feature #7) | No source was found (A7/A8). Nothing is scraped |

### Deferrable

Convenient, blocks nothing.

| # | What | What it unblocks | Condition |
|---|---|---|---|
| D1 | **Ollama upgrade authorisation** (T-10) | Nothing currently depends on it — the 412 gate is unmet | Only if a local model is genuinely wanted. **8 GB RAM is the binding constraint**; no upgrade is attempted without explicit approval |
| D2 | **OmniRoute API key** | Nothing — the project runs fully offline by design | HTTP 401 `AUTH_002` on every attempt. No key is stored, and none is required for any feature above |

### No longer needed

Recorded so they are not asked for again.

| # | Earlier request | Why withdrawn |
|---|---|---|
| N1 | **Official NEPSE API credentials / session token** (B-09) | HTTP 401 on all 11 probed endpoints. Reverse-engineering the token scheme is on the explicit not-doing list. Not sought |
| N2 | **Broker or Mero Share credentials** | On the explicit not-doing list. The tool is read-only research; it never places orders |
| N3 | **A live price feed** | The store is historical and every price is dated. The UI states `historical close (stored bars, not a live price)` rather than implying liveness |
| N4 | ~~Manual transcription of PDF pages 1–18 / 34–52~~ | **No longer needed for the current phase.** T-09 was deferred by the owner on 2026-10-13, so the "page 29 first" sequencing rule is void. The existing digitized documents are the working references, and the known extraction gaps (pages 10, 20, 29) are recorded as limitations in T-09. Do not supply pages out of order, or at all, unless the owner reopens the task |

---

## BACKLOG

| ID | Task | Note |
|---|---|---|
| T-31 | Add a `non_positive_price` check to the quality sweep | **B-21.** 10 bars carry `low=0` or `open=0` yet read as `valid`, and 2 of them (KRBL 2024-12-01, GRDBL 2023-06-25) carry **no flag at all** because the sweep only tests whether `open`/`close` fall outside `[low, high]` — it never asks whether a price is positive. Adding the check only *adds* a flag, it deletes nothing, so it is safe to do without an owner decision. Whether the 10 rows should be excluded is a separate question, folded into **R1**. |
| T-15 | ShareSansar Scraper bulk import as a second price source | Workbook verified reachable (~41 MB). Needs a **licensing decision first** — no LICENSE on the archive either. Would give a cross-check against the GitHub dataset. |
| T-17 | Relative-strength factor | Blocked on an index series (B-10). Declared unavailable today. |
| T-18 | News / Events and multi-factor *fundamental* ranking | Both blocked on T-11/T-12. |
| T-19 | Transcribe PDF pages 18–33 | Settlement arithmetic self-checks make these the highest-yield pages (T-09). |
| T-20 | `TASK_QUEUE.md` / `KNOWN_BUGS.md` upkeep | Update with every fix. |
| T-21 | Decide on L-05 (median substitution) | Computing percentiles over **observed values only** is methodologically cleaner but changes every score. Owner's call. |
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

---

## Update 2026-10-14 (backend repair mission)

**Completed and verified this run**
- Weekly / monthly / Elliott API endpoints: 404 root-cause fixed (routes moved
  inside `create_app`, `get_store()`-wired), verified live against real NABIL data
  (200 OK; errors 404/400). **B-25/B-26 fixed.**
- Elliott look-ahead: `analyze_elliott_extended` now uses confirmed swings only.
  **B-27 fixed.**
- Scanner de-duplication wired into `run_screen`. **B-28 fixed.**
- Three vacuous regression tests rewritten; stray root `test_integration_final.py`
  relocated to `tests/test_full_workflow.py` and repaired. **B-29/B-30 fixed.**
- Full suite **1176 passed / 0 failed** (was 1136/1-failed).

**Still open (backend)**
- **R1 (owner decision):** promote `non_positive_price` from `review` to hard-invalid?
  No historical rows altered.
- **B-31 (limitation):** backtest `fee_rate` is a configurable placeholder awaiting
  **T-12** (verified NEPSE fee/tax rates).
- **"1000 synthetic datasets":** NOT ESTABLISHED — no harness exists; do not cite it.

**Deferred to Phase 2 (frontend — not touched)**
- `app.js` SyntaxError ~line 1972 (orphaned block) — the whole UI is currently dead.
- Overlay plot calls pass empty placeholder data; console.log markers.
- Duplicate `dashboard.html` / `market_dashboard.html`.
- No browser-level verification (Playwright absent).

**External blockers unchanged:** T-10, T-11 data, T-12, T-13, T-15, B-09, B-10. *(T-11 sector loader implemented in session 6; still blocked on the owner CSV.)*

## Update 2026-10-14 (backend features mega-mission)

**Completed and verified this run** (all backend; frontend untouched)

- **Backtest engine.** New `tests/test_backtest_lifecycle.py` (24
  hand-computed lifecycle tests) exposed and pinned fixes **B-32** (returns now
  percent, contract-consistent), **B-33** (equity marks use the last usable
  close + `stale_marks` warning instead of collapsing to cash), **B-34**
  (duplicate trading dates rejected). New `realized_pnl` / `unrealized_pnl`
  metrics; unaffordable signals now warned, not silently dropped.
- **Cost model (B-11 hardening).** `PLACEHOLDER_FEE_RATE`,
  `fee_source`/`fee_effective_from` provenance (both-or-neither),
  `cost_status()` → verified/placeholder/custom, `cost_model` block on every
  result, status-aware assumptions text, `/api/strategies` exposes
  `fee_rate_status`. API runs can never be "verified" (no provenance input).
  Nine new tests (`tests/test_cost_model.py`). B-31 merged into B-11 (it was
  a duplicate number).
- **Forecasting.** New `rolling_origin()` walk-forward evaluation
  (chronological expanding windows, per-origin model-vs-naive RMSE, honest
  verdict BASELINE/UNDETERMINED/BEATS/MIXED/NO DEMONSTRATED SKILL) + 
  `POST /api/forecast/rolling`. Leakage probes prove no origin sees data
  beyond its own window and hold-out perturbation never moves predictions.
  Thirteen engine tests (`tests/test_forecast_rolling.py`) + 3 API tests.
- **Portfolio.** **B-35 fixed**: non-positive/missing latest closes leave a
  position unvalued with a cause-specific flag; weights/valued totals exclude
  it; 3 new tests.
- **Floor-sheet.** **B-36 fixed** (scientific-notation mangling), plus 4 new
  parse tests (symbol upper-casing, broker trimming, fractional-quantity
  warning, overflow skip).
- **Integrations.** New `tests/test_datasources.py` (20 tests, zero network):
  adapter contract, offline cache paths proven by making any HTTP attempt
  fail, official-API refusal without credentials, token never leaks into
  reported payloads. B-10 dashboard honesty now test-pinned ("no index value
  is shown"; no index key in payload).
- **News / Events (register item 7).** Local processing layer **IMPLEMENTED**
  and tested (schema v6: `news_items` + `news_item_symbols`): parse CSV/JSON,
  timestamp normalisation with future/pre-1900 rejection, per-row skip
  reasons, dedup by item identity (idempotent re-import), symbol association,
  provenance per item, staleness-flagged summaries with an explicit "no live
  source is connected; nothing is fetched, scraped or sentiment-scored" note.
  Routes `POST /api/news/import` (mutating, classified in both scripts) and
  `GET /api/news/summary`. Nineteen engine tests + 3 API tests. **The source
  itself stays BLOCKED (L4 / T-15 licensing).**
- **Ingestion audit.** **B-37** (failed symbols in security master) and
  **B-38** ("success" logged for zero-row runs) fixed; `tests/test_ingest.py`
  (9 tests) — previously the module had zero coverage.

**Full suite: 1196 → 1307 passed / 0 failed, exit 0**; `ruff check` 0,
`ruff format --check` 0 (126 files). Route inventory regenerated: **57/57
routes classified and test-referenced**. 0 staged, 0 commits, HEAD `b6c3659`;
protected paths (frontend, `AI Trading Nipsy/`, `WRITTENdata.pdf`) untouched.

**Still open (backend)**
- **R1 (owner decision):** non-positive price policy — unchanged, no rows
  modified; only the unambiguous calculation-layer guards were added (B-33,
  B-35).
- **B-11 / T-12:** real fee/tax rates still owner-supplied; placeholder
  labelled end-to-end.
- NOT-TESTED on real data: backtest (structural + fixture verified only),
  forecasting out-of-sample evidence, portfolio on real ledgers, floor-sheet
  (0 real records), news (no source), browser/E2E (Phase 2).

## Phase 1 blocker verification (2026-10-14 — investigation pass, no code changed)

A read-only verification pass re-established the current baseline and re-checked
all nine open external blockers against the **actual code, config and files on
disk** (not prior reports). No backend code was modified; no credential was
exposed; no authentication, licence or paywall was bypassed; nothing was
downloaded, upgraded or purchased.

### Baseline reproduced (not trusted from history)
| Gate | Command | Exit | Result |
|---|---|---|---|
| Tests | `.venv/bin/python -m pytest -o addopts= -p no:warnings tests/` | 0 | **1322 passed, 0 failed, 0 skipped** (20.61 s) |
| Lint | `.venv/bin/ruff check .` | 0 | clean |
| Format | `.venv/bin/ruff format --check .` | 0 | 126 files |
| Routes | `.venv/bin/python scripts/route_inventory.py` | 0 | 57 routes |

Git unchanged: `main` @ `b6c3659`, **0 staged, 0 commits**; frontend diff
pre-existing (+252/−5, untouched); `AI Trading Nipsy/`, `WRITTENdata.pdf`,
historical data/DBs untouched.

### Sanitized configuration findings (no values printed)
* **Ollama** — executable present (`/usr/local/bin/ollama`), CLI **and** daemon
  both report **0.5.7**, local service responds on `localhost:11434`. Installed
  models (list-only, nothing pulled): **`llama3.2` (1.88 GiB, text-only)** and
  **`nomic-embed-text` (0.26 GiB)**. **No vision-capable model present.** RAM
  **8 GiB** (the binding constraint; 3B is the practical model ceiling). *Note:*
  the binary is a symlink into a bundle literally named
  `Ollama 8.39.31 AM.app` — cosmetic, not a functional issue. **No `megatool`
  code references Ollama or any model/endpoint at all** — there is no Ollama
  integration in the application; T-10 concerns only the *optional* PDF vision
  benchmark (deferred at T-09).
* **OmniRouter (D2)** — **no OmniRouter/OpenAI/API-key environment variables are
  present in this process** (checked by name, values never printed). No `.env`
  file at the project root; **no endpoint, model name, or client code** exists
  anywhere in the repo. Nothing in the project calls OmniRouter; the app runs
  fully offline by design. A "minimal test request" was therefore **not possible
  — there is no configured endpoint or key to test against.** The existence of an
  env var in the owner's own shell (if any) is not visible to, and cannot be
  validated by, this pass.

### Blocker matrix
`RESOLVED` is used **only** where actual evidence demonstrates resolution. None
of the nine qualifies. Configuration-present ≠ configuration-tested ≠
authorization-established ≠ data-obtained ≠ data-validated ≠ feature-verified.

| # | Blocker | Status | Current evidence (this pass) | Prevents | Exact action required from owner |
|---|---|---|---|---|---|
| 1 | **B-09** NEPSE API 401 | **BLOCKED** | Live re-probe (1 unauthenticated GET, UA-only) → **HTTP 401** on `…/nepse-data/market-open`; adapter is an honest stub that refuses without credentials | Real-data ingest from the official feed (the GitHub dataset already covers 372 symbols) | None sought: request **N1 withdrawn** — a logged-in NEPSE session is required and reverse-engineering the token is on the not-doing list. Provide only if you later decide to grant a read-only session token |
| 2 | **T-11 / R2** sector CSV | **ACTION REQUIRED** (data) · loader ready | `data/raw/sectors.csv` **ABSENT**; 372/372 `security_master.sector` NULL; importer built and tested (session 6) | Sector grouping, Screener sector filter, `sector_percentile` factor (declared `unavailable`) | Supply `data/raw/sectors.csv`, header `symbol,sector` (symbols matching `security_master`, e.g. `ADBL`); richer provenance form (`symbol,sector,source,retrieved_at,observed_date`) documented at T-11. Import via `megatool/sectors.py` |
| 3 | **T-12 / R3** fee/tax rates | **ACTION REQUIRED** | `PLACEHOLDER_FEE_RATE = 0.004` confirmed at `megatool/backtest.py:36`; `cost_status()` enforces source+date before `verified`; labelled `PLACEHOLDER` in every API run. **No authoritative rate present** | Net-of-cost backtest returns; S-08 cost attribution | Supply `data/raw/fees.csv` **or** a message with: `broker_commission_pct`, `sebon_fee_pct`, `settlement_fee_pct`, `capital_gains_tax_pct`, **`effective_from`** and **`source`** (SEBON/NEPSE circular or broker contract note). Nepal rates are date- and segment-specific, so the source is part of the value. Do **not** let the placeholder be hard-coded as real |
| 4 | **T-13** real floor sheet | **ACTION REQUIRED** | 0 real records; import path built+tested (`megatool floor import FILE --date YYYY-MM-DD`); parser expects REQUIRED `symbol,buyer,seller,quantity,rate` (amount optional; NEPSE published headers accepted via aliases) | First real floor-sheet validation (currently synthetic-only) | Provide any published NEPSE floor-sheet CSV at `data/raw/floor_YYYY-MM-DD.csv` (or any path) with at least those columns |
| 5 | **T-15 / L1** ShareSansar | **ACTION REQUIRED** | Workbook reachable (~41 MB) but **no LICENSE** on the archive; nothing scraped; **no importer wired** | A second price source for cross-checking the GitHub dataset | A **licensing decision first** (yes/no to bulk import), then the workbook under `data/raw/`. Scraping without authorisation is on the not-doing list |
| 6 | **L4** news source | **ACTION REQUIRED** | Local layer built+tested (`POST /api/news/import`, schema v6, idempotent, honest "no live source" summaries); **no source connected**; nothing fetched/scraped/sentiment-scored | Any news/event records (feature #7 stays at "no records") | Supply a **permitted** machine-readable feed or export under `data/raw/` |
| 7 | **B-10 / L3** index series | **ACTION REQUIRED** | `data/raw/index_nepse.csv` **ABSENT**; **no index reader built yet**; dashboard deliberately shows *no* index figure (B-10 honesty test-pinned) rather than a stale/invented one | T-17 relative strength; an index line on the dashboard | Supply `data/raw/index_nepse.csv`, header `date,close`, covering the index name(s) and date range you want. A reader + T-17 would then be built |
| 8 | **T-10 / D1** Ollama | **BLOCKED** *(optional, deferrable)* | v0.5.7 installed; only `llama3.2` + `nomic-embed-text`; **no vision model**; 8 GiB RAM ceiling; prior `pull` of a VLM returned Ollama's own **412 client-version gate** (nothing downloaded; model list unchanged). **No Ollama code exists in the app** | Only the *optional* PDF VLM benchmark (Apple Vision already at 90.2% recall; T-09 deferred) — **blocks nothing in Phase 1** | Explicit approval to upgrade Ollama (≥0.40.3) **and** download a ≤3B vision model (~2 GB). Not attempted without permission (Rule 8) |
| 9 | **D2** OmniRouter | **NOT TESTED** | No env vars in this process, no `.env`, no endpoint/model/client code anywhere; **nothing to test against**; nothing depends on it; app runs offline | Nothing — no feature requires it | If you want it wired: supply the endpoint + model + a key (never committed), and confirm the account has credit. Otherwise it can stay dormant |

**No blocker was resolved by this pass** — all nine depend on owner-supplied
data, a licensing/auth decision, or an approved machine change. Every blocked
*feature* is either honest-and-absent (no index figure, no news records,
`unavailable` sector factor, `PLACEHOLDER` fee) or covered by the always-available
GitHub dataset, so nothing fabricates data while the blockers stand.

---

## Phase D code-readiness pass (2026-10-14 — loaders + LLM provider built)

Follow-on to the investigation above. Safe, locally-solvable code work only:
no external access, no secrets, no data fabricated, no protected files touched.
**1389 tests pass, `ruff check` 0, `ruff format --check` 0, 57 routes, HEAD
`b6c3659`, 0 staged.**

### Status changes (code built this pass)

| # | Blocker | Status now | What was built (IMPLEMENTED + TESTED-PASS) | Still required from owner |
|---|---|---|---|---|
| 8 | **T-10 / D1** Ollama app integration | **RESOLVED (local mode)** · hosted NOT-TESTED | `megatool/llm.py` (BaseLLMProvider + `OllamaProvider`/`OpenRouterProvider`/`DisabledProvider` + `get_provider()`), `config.py` AI knobs (endpoint/ollama-host/timeout/max-tokens), `megatool ai status\|ping`, **26 mock-transport tests**, and a **live local ping** (`Pong`, exit 0). App runs with **zero AI contact** when unselected (full suite is offline). | Nothing for local mode. For **hosted**: supply `MEGATOOL_AI_PROVIDER=openrouter`, `MEGATOOL_AI_MODEL`, and `MEGATOOL_AI_API_KEY` via env/`.env` (never committed) — then `megatool ai ping --allow-hosted`. |
| 2 | **T-11 / R2** sector CSV | **ACTION REQUIRED** (data) · loader done + provenance | `megatool/sectors.py` (`read_sectors_csv`/`classify_sectors`/`import_sectors`) + `MarketStore.set_sectors()` (touches only sector columns, never clobbers name/`delisted`); stores `sector_source`/`sector_retrieved_at`/`sector_observed_date`; **21 tests** (15 validation + 6 provenance). Refuses missing columns/empty file/bad dates; ambiguous sector → no winner; unknown symbol reported, **never created**. | Drop `data/raw/sectors.csv`, header `symbol,sector` (provenance columns `source,retrieved_at,observed_date` optional), symbols matching `security_master`. Import via the loader. |
| 3 | **T-12 / R3** fee/tax rates | **ACTION REQUIRED** (data) · structure done | `FeeSchedule`/`FeeComponent`/`FEE_SCHEDULES`/`fee_uncertainty()` in `backtest.py` — the four register components (`broker_commission`, `sebon_fee`, `settlement_fee`, `capital_gains_tax`) with `rate=None` until provenance arrives; **+10 tests**. Default `PLACEHOLDER_FEE_RATE` and `cost_status` **unchanged**. | Per-component rates **+ basis + `source` + `effective_from`** (SEBON/NEPSE circular or broker contract note). Until then the schedule honestly reports `placeholder` with all components unknown. |
| 7 | **B-10 / L3** index series | **ACTION REQUIRED** (data) · loader done | `index_series` table (DuckDB, idempotent DDL) + `MarketStore.upsert_index_rows`/`index_closes` + `megatool/index_series.py` (`read_index_csv`/`import_index_series`); **16 tests**. Strict: unparseable date / non-finite / non-positive / duplicate date **abort the whole import (nothing written)**. | Drop `data/raw/index_nepse.csv`, header `date,close`, for the index name(s)+range you want. No reader consumer is wired yet (T-17 remains future work). |
| 9 | **D2** OmniRouter | **SUPERSEDED** | OpenRouter recorded as the selected hosted gateway (decision `D-n`/`D-o`/`D-p` in `DECISIONS.md`). No client was ever built for OmniRouter; nothing depended on it. | None — supply an OpenRouter key via env when you want hosted mode (see D1 row). |

### Unchanged (external / permission-bound — still BLOCKED)

- **B-09** NEPSE API 401 — official feed needs an authenticated session; N1 withdrawn, no reverse-engineering. GitHub dataset (372 symbols) still covers local needs.
- **T-13** real floor sheet — parser ready + synthetic-labelled tests; needs a published floor CSV for real validation. Repeatable procedure: place `data/raw/floor_YYYY-MM-DD.csv` → `megatool floor import FILE --date YYYY-MM-DD` → compare stored rows vs the file's totals; report skipped/mismatched rows.
- **T-15 / L1** ShareSansar — licensing decision first; nothing scraped, no importer wired, integration stays disabled.
- **L4** news source — local layer built; needs a **permitted** machine-readable feed/export under `data/raw/`.
- **T-10** Ollama *upgrade* (vision benchmark) — separate from D1; still needs explicit approval (Rule 8). Blocks nothing in Phase 1.

**Nothing was auto-started into Phase 2.** Deterministic modules (indicators,
scan, backtest, Fibonacci, portfolio/risk, cost arithmetic) were not modified and
require no key. No API key was created, printed, committed, or requested pasted
into any file.

## Update 2026-10-14 (T-M1: eligibility plumbing + upsert safety)

**DONE → `IMPLEMENTED` · `TESTED-PASS`.** Closed the two code hazards flagged by
the forensic closure report (`data/review/FORENSIC_CLOSURE_REPORT.md` §7 R-1/R-2)
before any metadata import happens:

1. `upsert_securities` no longer resets `delisted` when a row omits the key
   (omitted/NULL preserves; a supplied `bool` overwrites; new rows default FALSE).
2. `MarketStore.securities_meta()` — the first reader for `security_master`
   (one query; unknown stays explicitly unknown).
3. Opt-in, default-off eligibility filters (`exclude_delisted`,
   `instrument_types`) on `run_screen`, `POST /api/screen` and `POST /api/rank`,
   sharing the pure decision function `eligibility_from_meta` so scanner and
   ranking always agree. Default behaviour is byte-compatible (verified by tests).

**+32 tests** (27 in `tests/test_security_metadata.py`, 5 route tests); suite
**1421 passed**, lint/format green. No schema change, no production write, no
migration. Next per roadmap: **T-M2** (dry-run import harness, owner-gated).

## Update 2026-10-14 (T-M2: dry-run security-metadata import harness)

**DONE → `IMPLEMENTED` · `TESTED-PASS`.** The reviewed-metadata pipeline now has
its validation stage; nothing imports and nothing can:

1. `megatool/metadata_dryrun.py` — validates one canonical CSV schema
   (`symbol` + ≥1 metadata column), rejects malformed rows with explicit
   reasons (blank symbol, out-of-vocabulary `instrument_type`/`status`,
   non-boolean `delisted`), collapses identical duplicates, flags conflicting
   duplicates as ambiguous, and reconciles every surviving symbol against
   `securities_meta()` (T-M1 reader) classifying **additions / updates /
   unchanged / advisory / conflicts / no-proposal** with `requires_manual_review`
   per record.
2. Honesty rules enforced by tests: blank cells stay blank (never a guessed
   sector/type/status/flag), every file value is labelled unverified, stored
   values win every conflict and are shown side-by-side, `merged` never becomes
   `delisted`, and every `status` proposal is flagged (no listing-status column
   exists — B-2).
3. `megatool metadata dry-run --input FILE [--db PATH] [--out-dir DIR]` —
   opens the store **read-only** (probe query forced at open; missing/locked DB
   → clean error + hint), writes `<stem>_dryrun.{json,md}` under
   `data/review/dry_run/`, and **refuses to overwrite** existing artifacts.
   Output is deterministic (no timestamps, sorted keys/symbols, input sha256).

**+22 tests** (`tests/test_metadata_dryrun.py`); CLI-adjacent battery **58
passed**; `ruff check .` 0; `ruff format --check .` 0 (138 files = 136 + the
two new `.py` files). Full suite **not rerun** (additive change; last full run
1421 at T-M1 — `NOT-TESTED` this session by explicit instruction). Production
DB untouched (mtime `2026-10-12 12:35:29`), `data/review/` unchanged, staged
index empty. **No import command exists** — per requirement 14 the production
write path remains a future, separately approved task. Roadmap next:
**T-M3** or owner review of a dry-run report, not started.

## Update 2026-10-14 (T-M3: data-driven `sector_percentile`)

**DONE → `IMPLEMENTED` · `TESTED-PASS`.** The sector factor's availability is now
derived from the sector data actually supplied for each run — the hard-coded
"sector is NULL for every symbol" reason (forensic R-4) is gone:

1. `rank_universe(..., sectors=None)` accepts an optional symbol→sector mapping
   (keyword-only; all existing callers unchanged). Blank/NULL values are
   ignored — a symbol is classified only by a non-empty sector string.
2. `sector_availability()` computes one of three explainable states:
   **unavailable data** (no usable mapping), **insufficient coverage** (measured
   coverage vs the configurable `sector_min_coverage`, default 0.5), or
   **available**. Reasons always carry the measured numbers.
3. When available, the factor computes **within-sector percentiles of 3-month
   momentum** (research report §8.2). Singleton sectors yield `None` — a
   percentile within a group of one is never fabricated; those symbols are
   median-substituted and flagged missing like any other missing factor.
4. Default weight stays 0.0, so default rankings are byte-identical to before;
   the API route now passes stored sectors and emits the computed `unavailable`
   dict (same keys/shape as before).

**+13 tests** (`tests/test_sector_factor.py`); affected existing batteries all
green: `test_ranking` + `test_financial_integrity` + `test_walkforward` **88
passed**, API rank routes **13 passed**; `ruff check` 0; `ruff format --check`
0. Full suite not rerun (blast radius is ranking.py + its three test files +
the rank route, all covered). No production data touched. Next per the
execution plan: **A2/A3** (pure code/docs), then the B-batch validations.

## Update 2026-10-14 (A2 + A3: B-3 evidence addendum; fee-model shape extension)

**A2 — `IMPLEMENTED` (documentation).** `data/review/UNIVERSE_RECONCILIATION.md`
gained a dated addendum recording the B-3 proof: all 7 missing equities have
current daily prices in the MIT-licensed binayabaral dataset (BNL through
2026-10-09, SGHL through 2026-10-14, verified live), and six of the seven
(MEPDL, SGHL, KAHL, SAPIL, ECL, NBL) appear as traded symbols in socrateai's
2026-10-13 floor sheet. Evidence complete; the import still awaits the owner's
B-1 ruling. Production universe unchanged (372).

**A3 — `IMPLEMENTED` · `TESTED-PASS` (structure only, zero rates).**
`megatool/backtest.py`: `FeeComponent` now carries `tiers` (tuple of
`FeeTier(ceiling, rate)` — broker-commission size steps) and `applies_to`
(``"traded_value"`` vs ``"net_gain"`` — CGT is levied on the gain at disposal
and cannot be expressed as a per-side rate); a tiered component is `known`
only when every tier carries a rate; `component_report()` exposes both fields.
The placeholder schedule's CGT component declares the gain-aware shape with
no rate. The engine still runs on the aggregate PLACEHOLDER_FEE_RATE — no
real rate entered production, and applying tiered/gain-aware components to
live P&L stays gated on the owner's C3 confirmation (decision **D-y**).

**+6 tests** appended to `tests/test_cost_model.py` (28 total, all green);
`tests/test_backtest.py` **32 passed**; `ruff check` 0; `ruff format
--check` 0. Next per the execution plan: the **B-batch** read-only dataset
validations — research tasks, not pure-code, so implementation pauses here;
imports wait on the owner's B-1 ruling.

## Update 2026-10-15 — B-batch DONE; Phase 2 features F1/F3–F6/F8–F12 delivered

**B-batch (read-only validations) — `DONE`.** B1–B4 executed read-only and
marked ✅ DONE in `PHASE1_EXECUTION_PLAN.md`; evidence in
`data/review/DATASET_VALIDATION_2026-10-15.md`. No imports were made — B-3
import still awaits the owner's **B-1** ruling.

**Phase 2 (backend, UI-independent) — per-feature status:**

| # | Feature | Status | Evidence |
|---|---|---|---|
| F1 | Research-assistant LLM wiring | **IMPLEMENTED · TESTED-PASS** | `/api/research/ask` gains `interpret`/`include_private`/`provider`; AI text appended beside (never replacing) the deterministic payload; stale `/api/research/topics` text replaced with real `ai_status`; `tests/test_agent.py`, `tests/test_research.py`, `tests/test_api.py` |
| F2 | Scanner / multi-factor ranking | IMPLEMENTED (pre-existing) | unchanged this session |
| F3 | Floor-sheet multi-session trend | **IMPLEMENTED · TESTED-PASS** | `floorsheet.trend()` (observed activity + hand-computed broker net flow, `insufficient_sessions` status) + `GET /api/floorsheet/trend`; `tests/test_floorsheet.py` 37 passed |
| F4 | News event categorisation / relevance | **IMPLEMENTED · TESTED-PASS** | `categorize_headline` (closed vocabulary, keyword evidence, word boundaries), `relevance_for` (named vs mapped), `story_key` repeated-coverage grouping — all read-time, no schema change, explicitly not sentiment/impact; `tests/test_news.py` 25 passed |
| F5 | Journal AI reflection | **IMPLEMENTED · TESTED-PASS** | `journal.reflect()`: deterministic context always local; **no model call at all** without `authorize_private=true`; recipient (local Ollama vs hosted) named when authorized; `POST /api/journal/{id}/reflect`; `tests/test_journal.py` 38 passed |
| F6 | Portfolio risk manager | **IMPLEMENTED · TESTED-PASS** | `megatool/risk.py` + `GET /api/portfolio/risk`; `tests/test_risk.py` 7 passed |
| F7 | Backtest + walk-forward | IMPLEMENTED (pre-existing) | unchanged this session |
| F8 | Market-regime detection | **IMPLEMENTED · TESTED-PASS** | `megatool/regime.py` (equal-weighted proxy — **not** the official NEPSE index, B-10), causal labels, warmup handling; `GET /api/regime[/history]`; `tests/test_regime.py` 13 passed |
| F9 | Explanatory alerts | **IMPLEMENTED · TESTED-PASS** | `megatool/alerts.py`; alert_history in the **app SQLite DB**, fire-once dedup keyed on condition+symbol+params, re-arm only via `DELETE /api/alerts/clear`; `tests/test_alerts.py` 10 passed |
| F10 | Financial-statement assistant | **IMPLEMENTED · TESTED-PASS** | `compute_symbol_ratios` + `GET /api/fundamentals/{symbol}/ratios` and `/compare` (registered before `/{symbol}`); reported-vs-derived explicit, every refusal reason surfaced; `tests/test_fundamentals.py` 61 passed |
| F11 | Trade-planning portfolio integration | **IMPLEMENTED · TESTED-PASS** | `planning.constraint_check()` (current/post-trade weights, stated funding assumption, explicit refusals without a price) wired into `POST /api/planning` via optional `symbol`/`max_weight_pct`; `tests/test_planning.py` 33 passed |
| F12 | Research-agent orchestration | **IMPLEMENTED · TESTED-PASS** | `megatool/agent.py`: deterministic keyword routing, per-tool statuses (`ok/empty/blocked/error`) with honest reasons (news→L4, floorsheet→B-1/T-13, backtest→needs explicit params), private tools excluded from AI prompt unless `include_private=true`; `POST /api/agent/run`, `GET /api/agent/tools`; `tests/test_agent.py` 17 passed |

Real defects found and fixed en route: `all_closes()` carries a datetime
`trading_date` column (broke `pct_change` — numeric selection added); the
`/api/research/topics` stale "no LLM key exists" claim; the missing `params`
binding in the news repeated-coverage query; `eps` matching inside "nepse".

Verification: full suite **1542 passed / 0 failed** (end-of-session
checkpoint), `ruff check .` and `ruff format --check .` both clean (151
files). Test evidence per feature in `TEST_RESULTS.md` (Run 2026-10-15).

**Not done / still gated (unchanged at the time of writing that section):**
every import and data-rights task awaits **B-1**; fee-preset changes await
**C3**; official listing status awaits **B-2**; no permitted news feed
(**L4**). *(Superseded on the same date: the uvicorn server was restarted via
the documented procedure and all new routes verified live — see the session-2
update below.)*

## Update 2026-10-15 (session 2) — frontend integration, B-1 evaluation, C3 closed with official sources

**Frontend integration (done, verified).** The Phase-2 backend endpoints were
wired into the existing pages with no rebuild/framework and no duplicated
backend logic: regime + alerts (Overview), derived ratios (Fundamentals),
session trend (Floorsheet), tool-agent (Research), risk check (Portfolio),
reflection (Journal). Each surface handles loading/error/empty honestly; AI
layers are explicit opt-in (default OFF). `app.js` kept the smallest-cause
fix; `node --check` exit 0; browser smoke **13/13 checks, 11/11 tabs, 0
console errors**. Known anomaly recorded (pre-existing, not fixed):
`/api/fundamentals/ratios?symbol=X` shadow-matches `/api/fundamentals/{symbol}`
→ 200-empty; the real route is `/api/fundamentals/{symbol}/ratios`.

**B-1 evaluation (done, read-only).** Candidate datasets evaluated for local
personal research/isolated testing per published terms only; T-M2 dry-run on a
DB **copy**: 465 records, 93 additions, 372 updates, 0 conflicting, nothing
imported (`data/review/dry_run_2026-10-15/`). Production import still gated on
**BLK-2** (owner ruling). binayabaral coverage 372/372 = 100%; socrateai meta
eliminated (404; `meta/` only `.gitkeep`).

**C3 closed — fee/tax rates officially verified; BLK-5 → RESOLVED.** SEBON
Regulation 2064 (6th amendment) Schedules 14/15 machine-read: commission slabs
0.36/0.33/0.31/0.27/0.24 % (min Rs 10; exchange may set lower), SEBON charge
0.015% each buy+sell, DP Rs 25 per sell. CGT verified against the **enacted**
आर्थिक ऐन, २०८३ (Law Commission gazette + IRD identical copy) amending ITA
§95क(2)(क): natural persons on listed shares 7.5% >365 days / 10% ≤365 days,
effective साउन १, २०८३ (FY 2083/84); companies 10%, others 25%. Shipped as the
opt-in named schedule `official-2083-84` (`FEE_SCHEDULES`); default
`PLACEHOLDER_FEE_RATE`/labels untouched; `tests/test_cost_model.py` **34
passed**; register §3 + BLK-5 + KNOWN_BUGS B-11 updated. Engine-side adoption
of tiered/gain-aware components remains a separate task (decision C3/D-y).

**Session-2 verification:** full suite **1543 passed / 0 failed** (23.76s),
`ruff check .` exit 0, `ruff format --check .` 153 files, route inventory
**69/69 TEST**, element cross-check 179 ids / 0 missing, endpoint smoke 200 on
correct routes, git **113/0/0** at `b6c3659` (nothing staged/committed/pushed).
Record correction: `/api/regime.last_date` = **2026-10-09** (store's newest
bar; an earlier note said 2026-10-14 — wrong, corrected in records not data).

**Asks unchanged:** R1 owner B-1 production-import ruling (BLK-2); R2 sector
CSV provenance; R3 superseded by C3 resolution (fee rates now official);
R4 = B-2 owner manual browser export; ~~R5 = B-4 merged-semantics ruling~~
(**closed — implemented 2026-10-15**); L1 = ShareSansar licensing; L4 = no
permitted news feed; N1 = B-09 401 by policy (no retries).

## Update 2026-10-15 (session 3) — C3/D-y DONE: verified schedule adopted engine-side

**Engine adoption (implemented, tested, verified).** One fee engine, one pricing path
(`side_transaction_costs` in `megatool/backtest.py`) now serves the backtester, its buy-and-hold
benchmark, and trade planning (`planning.entry_cost_estimate()` → `cost_estimate` in
`POST /api/planning`). Opt-in per run via `BacktestConfig(fee_schedule="official-2083-84", cgt=...)`:

* commission tiered by each side's charged value (0.36/0.33/0.31/0.27/0.24 % slabs), NPR 10 minimum,
  effectiveness-dated **per side** around the 2024-05-14 revision (earlier sides use the officially
  superseded सङ्ग्रह २०८० table, counted in a run warning);
* SEBON 0.015% per side; NPR 25 DP per sell; affordability solved against the tier table;
* CGT only on an explicitly DECLARED `cgt="natural_person"` category: holding-period rates
  (>365d vs ≤365d), era tables (pre-2026-07-15 disposals at the official pre-amendment ITA rates),
  a loss never taxed, gain net of charges (§37 deduction basis flagged as unverified);
* every closed trade exposes gross_pnl / transaction_costs / taxable_gain / capital_gains_tax /
  net `pnl` (2dp-consistent); `metrics.capital_gains_tax_paid` is `None` when not computed;
* the flat-fee default path is byte-identical (existing 1543-test behaviour preserved); API
  contracts extended additively only (`fee_schedule`/`cgt` request fields; 400 on ambiguity).

**Verification:** focused batteries **325 passed / 0 failed** (test_backtest + test_cost_model +
test_planning + test_api + test_backtest_lifecycle + test_financial_integrity); ruff check + format
clean on all seven changed files; live server restarted via the documented procedure and smoke-verified
(defaults unchanged; NABIL schedule run honest about the pre-revision buy side and the open position).
The full suite was not rerun (owner instruction; default path untouched). Evidence: `TEST_RESULTS.md`
Run 2026-10-15 (session 3).

**Files changed:** `megatool/backtest.py`, `megatool/planning.py`, `megatool/api.py`,
`tests/test_backtest.py`, `tests/test_cost_model.py`, `tests/test_planning.py`, `tests/test_api.py`
(+ records: this file, DECISIONS, KNOWN_BUGS B-11 → RESOLVED, SESSION_HANDOFF, TEST_RESULTS,
PHASE1_BLOCKER_REGISTER BLK-5/§3).

**Still unverifiable by the engine (refused/disclosed, never guessed):** investor category (must be
declared per run), the §37 acquisition-cost deduction basis (net-of-charges treatment flagged), and
the effective dates of the SEBON/DP charges (applied throughout, disclosed in assumptions).

**Asks unchanged:** R1/BLK-2 production-import ruling; R4 = B-2 browser export;
~~R5 = B-4 merged semantics~~ (**closed — implemented 2026-10-15**); L1
ShareSansar; L4 news feed; N1 = B-09 401 by policy.

## Update 2026-10-15 (session 5) — R5 / B-4 DONE: merged-security semantics implemented

**R5 implementation (implemented, tested).** Owner ruling: evidence-based status distinction,
no blanket `merged = delisted`.

* Added `status` (`ACTIVE`/`SUSPENDED`/`MERGED`/`DELISTED`/`UNKNOWN`) and optional `successor_symbol`
  columns to `security_master` via an idempotent migration.
* `eligibility_from_meta()` uses canonical status; `MERGED` and `SUSPENDED` are non-tradable.
* `run_screen()`, `/api/screen`, and `/api/rank` exclude verified non-tradable securities **by default**;
  `UNKNOWN` symbols remain visible with an observable uncertainty note.
* T-M2 dry-run reconciles status/successor proposals and flags merged/delisted tension.
* Focused regression tests added for `ACTIVE`, `SUSPENDED`, `MERGED`, `DELISTED`, `UNKNOWN`, and
  successor-symbol scenarios.

**Verification:** focused batteries **143 passed / 0 failed** (`test_security_metadata`,
`test_metadata_dryrun`, affected API eligibility routes, `test_scanner`,
`test_scanner_quality_filter`, `test_ranking`, `test_sectors`); ruff check + format clean on all
modified files. Production DuckDB untouched; server not restarted.

**Files changed:** `megatool/market_store.py`, `megatool/scanner.py`, `megatool/api.py`,
`megatool/metadata_dryrun.py`, `tests/test_security_metadata.py`, `tests/test_metadata_dryrun.py`,
`tests/test_api.py` (+ records: DECISIONS.md, SESSION_HANDOFF.md, TEST_RESULTS.md,
PHASE1_BLOCKER_REGISTER.md, this file).

**Still unverifiable by the engine (refused/disclosed, never guessed):** the 21 merged symbols keep
`status=UNKNOWN` until an owner-approved import supplies evidence; no successor mappings are invented.

**Remaining ask:** R1/BLK-2 production-import ruling.

---

### T-30 · Source-pipeline validation on real snapshots (YONEPSE + binayabaral) — **DONE (2026-10-15)** → `TESTED-PASS`

* **Shipped:** `scripts/validate_source_pipeline.py`, which runs all five data blockers against the
  real downloaded snapshots and writes evidence to `data/review/source_validation/`. It only ever
  **reads** the production DuckDB (to copy it into a temp dir) and creates its SQLite app DB under a
  temp dir; it prints `production db written: False`.
* **Measured (see `PHASE1_BLOCKER_REGISTER.md` §3b for the full table):**
  * sectors: 360/372 symbols classified (96.77%), provenance on all 360, idempotent;
  * ranking: 58/60 ranked symbols with a computed within-sector percentile, 10 real sectors;
  * index: 6,718 rows, 1997-07-20 → 2026-10-14, cross-check vs socrateai identical to the cent;
  * fundamentals: 21,128 records / 307 symbols loaded;
  * news: 334 dated items imported, 18 upstream-undated skipped with reasons, 28 undated general
    notices deliberately not dated.
* **Two genuine defects the real-data run exposed and fixed:**
  1. `megatool/fundamentals.py` treated a real `0` as a *missing* column (`row.get(c, "") or ""`),
     so a genuine `PE == 0` refused the whole file — replaced with `_is_blank()`. 169 real zero-PE
     records now load.
  2. `megatool/datasources/yonepse.py` emitted duplicate reporting periods (6,908 reports → 4,227 real
     periods), which `megatool.fundamentals` correctly refuses. Added `dedupe_financial_reports()`
     grouping on the loader's own identity `(symbol, period_end)`, resolving exact duplicates (1,416)
     and conflicts (661 periods, 238 symbols) by **complete-period figure > latest filing**, recorded
     in each row's `notes`. General notices (no publication date, only `expiresAt`) are no longer
     dated.
* **Verification:** focused batteries **279** and **308** passed (0 failed); ruff check + format clean.
* **Remaining ask:** unchanged — R1/BLK-2 production-import ruling. Blocker 6 (official API 401)
  remains blocked by policy and was not bypassed.

---

## 2026-10-15 (session 14) — Phase 1 closure

**Status changes:**

| Item | Was | Now | Evidence |
|---|---|---|---|
| B-10 / BLK-8 index consumption | BLOCKED (data stored, no consumer) | **COMPLETED AND VERIFIED** | `relative_strength` factor + `/api/indices`; `tests/test_index_consumer.py` 15 passed |
| `relative_strength` static "unavailable" claim | stale/incorrect | **FIXED** | data-driven `index_availability()`; B-44 in `KNOWN_BUGS.md` |
| Full-suite baseline | 1578 → 1805 | **1820 passed / 0 failed** | `TEST_RESULTS.md` session-14 run |

**Still BLOCKED BY EXTERNAL INPUT (unchanged, exact prerequisites):**
* **B-09 / BLK-1 — NEPSE official API authorization**: owner ruling; gate stays OFF. Enables
  `MEGATOOL_NEPSE_API_AUTHORIZED=1` and the live benchmark.
* **TMS (Source B)**: broker name + TMS platform URL + read-only access basis.
* **YONEPSE production import**: data-rights ruling (R1/BLK-2), plus the single-writer server lock.
* **8 retired-symbol successors** (`BOKL,CBL,CCBL,NBB,NCCB,SFCL,SHBL,ULI`): authoritative evidence.

**Still NOT-TESTED (external observation only):**
* Intraday source cadence / ~3-second target — requires the Sun 2026-10-18 11:00–15:00 NPT benchmark
  (`scripts/benchmark_market_hours.py --source nepse`). Until then request latency (ms) is measured but
  point-to-point event latency is **UNMEASURABLE** (no trustworthy source-event timestamp).
* Friend deployment — needs a real `MEGATOOL_FRIEND_TOKEN` + `MEGATOOL_FRIEND_ORIGIN`.

**Deferred to Phase 2 (do not reopen without new evidence):** regime rewire to the official index,
B-10 index consumption in the *frontend* charting layer, B-2 listing-status export, L1/T-15 licensing,
L4 general-news feed, retired-symbol successors.

---

## Session-15 update (2026-10-15) — Phase 2–6 autonomous run

**Done (evidence in `docs/PHASES_2_6_PROGRESS.md`):**
* Chart-pattern recognition (`ta/patterns.py`, endpoint, panel, 14+3 tests).
* Statistical analysis (`stats.py`, 2 endpoints, panels, 18+6 tests).
* Scanner presets 4 → 23 + 18 new metrics (scanner tests extended).
* Reference audit (15 platforms), performance harness, durable docs.
* Indicator library 28 → 46 (with engine-free reference tests); B-45 fixed.
* Full suite **1999/0/0/0**; ruff clean; 75 routes all test-referenced.

**New TASK-QUEUE items (Phase 2 follow-ups, not yet done):**
* T-20 Optimise `POST /api/rank` — **DONE (2026-10-16)**: the cost was
  `rolling_std`'s per-window `np.std` loop (89% of runtime). Vectorised it
  (B-50): p50 391.7 ms → 113.6 ms (3.45×) with no caching and no change in
  results. Verified against pandas and an independent loop.
* T-21 Browser QA of charts-view `#patterns` / `#stats` / `#corr-out` —
  **DONE**: exercised against an isolated store; 0 console errors; values
  cross-checked against the API; B-46 found and fixed. Remaining: a full
  click-through of every view and XSS/rendering fuzzing (not performed).
* T-22 Render candlestick markers / pattern overlays on the chart (spec §29).

**Still BLOCKED BY EXTERNAL INPUT:** unchanged from above (B-09/BLK-1 NEPSE
authorization; TMS source; YONEPSE data-rights; friend token/origin; live
market-hours observation).

---

## Session 17 audit queue (2026-10-16) — ordered by importance

From `docs/PHASES_2_6_COMPLETION_AUDIT.md` §11. All local items need **no**
external authorization.

| # | Task | Requirement | Status |
|---|---|---|---|
| 1 | UI panels for **Harmonic + Elliott**; call or delete `plotCandlestickMarkers` | Phase 3 §7/§4, §29 | OPEN |
| 2 | Research workbench **save / reproduce / compare / export** (§11.5 steps 8–11) | Phase 4 acceptance | OPEN |
| 3 | **Watchlists** API + UI (schema already in `db.py`) | M1 §8.2 | OPEN |
| 4 | Dashboard panels: index summary, sector index + heatmap, market-session context, corporate-actions feed | M1 §8.1 | OPEN |
| 5 | **Exportable research report (MD/JSON)** | Phase 6 #38 | OPEN |
| 6 | **Background-job architecture** (§12.5), disabled by default, run history | M5 §12.5 | OPEN |
| 7 | **Strategy DSL** (entry/exit expressions, versioned JSON) + config hash/snapshot id | M4 §11.1/§11.4 | OPEN |
| 8 | Portfolio **cash-flow**; alert **severity + timed cooldown** | M3 §10.2/§10.5 | OPEN |
| 9 | **Custom formula catalogue** + **research templates** | Phase 6 | OPEN |
| 10 | Chart **line/area + benchmark/RS overlay + drawing tools** | M1 §8.4 | OPEN |
| 11 | Owner inputs: NEPSE auth, TMS, YONEPSE rights, fee-rate source, sector CSV, news source | BLOCKED (external) | BLOCKED |
| 12 | Test gaps: pip-audit, XSS fuzzing, soak, browser re-run, authorized live-latency | §16 | OPEN |

---

## Session 18 (2026-10-16) update

Moved into **COMPLETED AND VERIFIED** this session:

| Item | Evidence |
|---|---|
| Candlestick API (`GET /api/bars/{symbol}/candles`) | `tests/test_candles_api.py` (10) + browser |
| Candlestick chart markers (dead-code repair, unified marker flush) | browser screenshot; node --check |
| Elliott Wave UI (auto candidates + manual labelling) | browser: 33 pivots labelled + drawn |
| Harmonic UI (XABCD candidates + overlay) | browser: table + overlay verified |
| Watchlists (storage + CRUD API + UI) | `tests/test_watchlists.py` (15) + browser CRUD |
| Reproducible experiments (save/reproduce/compare/export) | `tests/test_experiments.py` (10) + browser |
| Report & chart export | browser downloads verified |
| go-nepse investigation + decision | `docs/GO_NEPSE_INVESTIGATION.md` |
| Platform research matrix (20 platforms) | `docs/PLATFORM_RESEARCH_MATRIX.md` |

Still **BLOCKED BY EXTERNAL INPUT** (unchanged): NEPSE official-API authorization,
TMS broker source, YONEPSE data rights, friend-token deployment, 8 retired symbols.

Still **NOT STARTED** (unchanged, carried forward): custom technical-analysis rule
builder + templates (Phase 5/6), background-job architecture (M5 §12.5), saved
screens UI, dashboard composition (index/RS panels), live intraday freshness.

---

## Session 19 (2026-10-16) update

Moved into **COMPLETED AND VERIFIED** this session:

| Item | Evidence |
|---|---|
| **Custom rule builder** (AND/OR tree, nested groups, add/remove, run, save/load/duplicate/rename/delete) | `tests/test_screens.py` (14) + browser: ran `rsi < 40` → 4/15 matched; save→duplicate→delete round-trip in Chromium |
| Saved-rule persistence + API (`GET/POST /api/screens`, `GET/PATCH/DELETE /api/screens/{id}`, `POST /api/screens/{id}/duplicate`) | `tests/test_screens.py`; `route_inventory.py` 94 routes all test-referenced |
| **Dashboard composition** (show/hide + reorder + reset, persisted) | browser: 7 panels; hide → `display:none`; reorder → `style.order`; reset restored; `localStorage['mt-dashboard-layout']` |
| Candlestick catalogue **15 → 18** (`harami_cross`, `tweezer_bottom`, `tweezer_top`) | `tests/test_candles.py` (+6); browser picker 18 entries; fires on `QAFLAT`/`QAMICRO2` |
| Elliott **analysis-period selector** + per-candidate **Draw** (pivots + wave labels) | `tests/test_analysis_window_api.py` + browser: 2 Draw buttons → 5 markers + line |
| Harmonic **pattern subset** + **tolerance** + per-candidate **Draw**; window aligned to the chart (fixes B-56) | `tests/test_analysis_window_api.py` + browser: Gartley-only NO_MATCH honest; slack 0.2 → 5 candidates → Draw → 1 series + 1 marker |
| Per-symbol analysis-config persistence (Elliott window, harmonic patterns/slack) | browser `localStorage` (`mt-elliott-cfg-*`, `mt-harmonic-cfg-*`) |

Still **BLOCKED BY EXTERNAL INPUT** (unchanged): NEPSE official-API authorization,
TMS broker source, YONEPSE data rights, friend-token deployment, 8 retired symbols.

Still **NOT STARTED / carried forward**: research **templates** catalogue (distinct
from the now-shipped saved rules), background-job architecture (M5 §12.5), index/RS
dashboard panels, saved-screens *tiling* into a screen, live intraday freshness,
chart drawing tools (manual trendline/Fib anchors), portfolio cash-flow model,
alert severity/cooldown.

---

## Session 20 (2026-10-16) update

Moved into **COMPLETED AND VERIFIED** this session:

| Item | Evidence |
|---|---|
| **Floating AI assistant** (discoverable FAB, panel, history, clear/close, examples, loading, errors, keyboard, responsive) | browser: FAB → panel, provider line, 6 chips, `⌘/Ctrl+Enter`, `Esc` closes, `localStorage['mt-chat-open']` persists; **0** console errors |
| Assistant → **tool run** wired to real data | browser: question routed to the `research` tool, `33 findings … over 420 stored bars` with provenance |
| Assistant → **Propose rule** → rule builder → run | `tests/test_screens.py` (+6) + browser: proposal rendered for review, unmatched clause named, **Load into rule builder** → Screener → edited → **Run rule** → *3 of 16 eligible* |
| **Fibonacci manual drawings** (multi-anchor, multiple drawings, invert, editable ratios, colour, visibility, per-symbol persistence, drag to adjust, undo/redo, delete, clear, JSON export, survives indicator/range changes) | browser: level maths equal to `p2 − r·(p2 − p1)`; drag hit-test `0.23 px`; undo/redo; per-symbol isolation; survives a chart rebuild |
| **Chart-pattern selection + overlays + evidence** | `tests/test_patterns_stats_api.py` (+1) + browser: 24 overlay series, polyline identical to reported pivots, **None**/*all* filters, fixes B-58 |
| **Index + relative strength** — scanner metric, endpoint, chart overlay, dashboard panel | `tests/test_index_consumer.py` (+7); metric catalogue 33 → **34**; `GET /api/bars/{symbol}/relative-strength` (inner join, explicit contract, rebased ratio); browser verdicts incl. the *insufficient history* path; *"historical, NOT a live feed"* labelling |
| **Research templates** catalogue + generic runner + saved copies | `tests/test_templates.py` (7, new); 14 templates; new **Templates** view; browser: multi-step run, POST step, save/load a copy |
| **Alert severity / cooldown / acknowledgement** | `tests/test_alerts.py` (+10); additive `alert_history` migration; browser: severity pills, `cooldown_minutes: 0` re-fire with `fire_count 2`, per-row and *all* acknowledgement |
| **Security checks** — dependency audit, authz boundary, XSS | `uvx pip-audit` → no known vulnerabilities; `tests/test_friend_access.py` (+2); browser XSS payloads escaped (0 injected nodes) |
| **Read-only tooling can no longer write the operator's state DB** | `tests/test_route_inventory.py` (+2); production SQLite `mtime` unchanged by a gate run; fixes B-59 |

Still **BLOCKED BY EXTERNAL INPUT** (unchanged): NEPSE official-API authorization, TMS
broker source, YONEPSE data rights, friend-token deployment, 8 retired symbols, live
intraday/news freshness.

Still **NOT STARTED / carried forward**: portfolio **cash-flow** model; background-job
architecture (M5 §12.5); saved-screens *tiling* into one screen; production migration;
soak/long-run and live-market latency tests; friend-token cross-origin flow;
chart-pattern per-pattern invalidation detail; B-60 (fibonacci 422 contract).

## Update 2026-10-16 (session 21) — defect-fix pass after re-verifying the frontend

A re-verification of the delivered frontend (not a new-feature pass) found four genuine
defects and one contract inconsistency; all fixed and re-verified in a real browser.

| Task | Status | Evidence |
|---|---|---|
| **Fibonacci auto-overlay never rendered** (read a non-existent payload key) | **FIXED** (B-61 / D-ay) | `web/static/app.js` `plotFibonacci`; browser: QABANK2 draws 5 retracement + 6 extension levels, labelled (`docs/evidence/session21-fib.png`); instrumented call received `{available:true, ret:5, ext:6}` |
| **A screen passed a security whose required metric was unavailable** (unknown clauses dropped) | **FIXED** (B-62 / D-az) | `megatool/scanner.py` three-valued `evaluate_node`; `tests/test_scanner.py` (+2); browser: flat EDGEFLAT/EDGENAN now *ineligible · "rsi unavailable"*; genuinely oversold names still pass (`session21-screener-nan.png`) |
| **Assistant panel could not be closed** (`.chat-panel{display:flex}` beat `[hidden]`) | **FIXED** (B-63 / D-ba) | `web/static/styles.css` `[hidden]{display:none!important}`; browser: computed `display` is `none` when hidden, `flex` when opened |
| **`/api/sources` mislabelled a gated source as down / unauthenticated** | **FIXED** (B-64 / D-bb) | `megatool/api.py` provenance fields; Data & Quality table now 3-state + `authorized` badge + note (`session21-sources.png`) |
| **`/fibonacci` returned `422` for thin data** | **FIXED** (B-60 / D-ax) | `200 {available:false, unavailable_reason}`; malformed ratio stays `400`; `tests/test_api.py` (+3) |

Gates re-run: `pytest` **2121 passed / 0 failed / 0 errors / 0 skipped**; `ruff check`
pass; `ruff format --check` 221 files; `node --check` exit 0; `route_inventory.py`
**98 routes (21 mutating, 77 read-only), all test-referenced**; 13/13 views, 0 console
errors/warnings. Git `main` @ `b6c3659`, 0 staged, 0 committed, 0 stashes; production
PID 26596 untouched; production SQLite `mtime` unchanged.

**go-nepse status (unchanged, D-aj):** the Go library is **NOT integrated**; its protocol
is covered by the gated, TLS-on `megatool/datasources/nepse_official_live.py`, and the
Data & Quality source note now says so. Live access remains **BLOCKED** on the owner
authorization gate.

Still **NOT STARTED / carried forward** (after session 21): fundamentals inside the
*scanner* (P/E, P/B, dividend, earnings remain unsupported-with-reason); portfolio
**cash-flow** model; background jobs (M5 §12.5); saved-screens *tiling*; chart-pattern
per-pattern invalidation detail; production migration + soak/live-latency tests.


---

## Session 22 (2026-10-16) — actual go-nepse integration

**DONE (Priority 1 of this mission).**
* The **actual** `github.com/voidarchive/go-nepse` library is integrated via the Go
  bridge `tools/gonepse-bridge/` (module `v0.2.5`) and the Python `GoNepseAdapter`.
* TLS verification is **ON** and the certificate is verified to be valid today;
  the owner gate is enforced in **both** layers; provenance label
  `DataSource.GONEPSE` added; `GET /api/gonepse/status` + a `/api/sources` entry.
* Gates green: 2150 Python tests pass (0 fail/skip); 9 Go tests pass; ruff clean;
  route inventory 100 routes all test-referenced.
* **Live connection remains BLOCKED** (gate unset) — reported, not worked around.

**DONE (Priority 2, low-risk).**
* **Portfolio cash-flow model** (`cash_flows()` + `GET /api/portfolio/cash-flow`,
  embedded in `/api/portfolio` and shown in the Portfolio panel). Signed per-trade
  net (buy = `qty×price + fees` out; sell = `qty×price − fees` in), cumulative in
  ledger order, totals and per-symbol net. States plainly that it is the recorded
  trades' net cash effect, **not an account balance**.

**Carried forward — Priority 2/3/4 of this mission (not started this session).**
* Fundamentals → screener field mapping (lead with an explicit
  present/absent contract; never treat missing as 0). Still **0 verified
  fundamentals records** and P/E, P/B, dividend, EPS remain unsupported-with-reason.
* SMC/ICT — order-block and fair-value-gap detectors with explicit, tested rules
  (no such module exists today; `levels.py` is S/R zones only).
* Wyckoff — accumulation/distribution evidence **without forcing** a classification.
* Saved-screen tiling + background jobs (M5 §12.5).
* Chart-pattern **per-pattern invalidation** detail.
* Valuation/intrinsic value only where inputs are verifiable (blocked on fundamentals).
* Index data → frontend where semantics are verified (index consumer tests exist;
  confirm end-to-end UI reachability).
* Relative-strength: already gated on a valid benchmark + aligned dates (D-as);
  extend only where a real benchmark is available.

**Blocked (unchanged).**
* NEPSE official API authorization (owner ruling) — gate remains unset.
* TMS (Source B) — owner must supply broker + read-only URL + policy basis.
* YONEPSE production apply / data-rights; friend deployment (needs real token/origin).
* 8 retired symbols with no evidence-backed successor.

---

## Session 23 (2026-10-16) — live market data

**DONE.**
* **Live provider layer** (`megatool/live.py`): `sharehub` (~20 s licensed),
  `official` (gated, inert), `feed` (owner JSON URL), `yonepse` (public hourly
  fallback). Freshness is **measured** from the source's own timestamp, cached at
  each provider's cadence, and shown separately from request latency.
* **Routes** `GET /api/live/status|market|quotes`; `/api/status` reports a real
  `live_feed_connected`.
* **Frontend** Overview "Live market" strip with a freshness badge + observed age.
* **Evidence** `docs/LIVE_DATA.md`; `docs/evidence/session23-live-strip.png`.

**Blocked — owner action required for actual live data.**
* **ShareHub** (best legitimate source, ~20 s): needs a licensed Data API account
  (`MEGATOOL_SHAREHUB_EMAIL` + `MEGATOOL_SHAREHUB_PASSWORD`) and a server-IP
  allow-list entry. Implemented + fixture-tested; live path NOT-TESTED without a
  licence.
* **Official NEPSE API**: BLOCKED by the anti-bot token control (measured 401),
  not only by the gate. Not enabled and not to be bypassed; use a licensed feed.
* **`nepseapi.com`**: early access by email. **`NepseAPI-Unofficial`** hosted:
  down (HTTP 522). **YONEPSE** market files: stale (~4 days) at time of writing.

**Carried forward (unchanged).** Fundamentals → screener mapping (still 0 verified
records); SMC/ICT (order blocks, FVG) — no module; Wyckoff — no module; valuation
— no module; saved-screen tiling + background jobs; chart-pattern per-pattern
invalidation detail.

---

## Session 24 (2026-10-16) — free current-day data

**DONE.**
* **Fixed the data source**: YONEPSE now reads the repository's **raw content**
  (current) instead of the stale **GitHub-Pages** mirror; Pages is a labelled
  fallback. Measured: raw `last_checked` 31 min old, NEPSE 2,625.93, 328 quotes.
* **Cadence-aware freshness + status vocabulary** (LIVE_VERIFIED / DELAYED /
  STALE / HISTORICAL / last-close / unknown) so an hourly source is never
  mislabelled.
* **Live data-source diagnostics** in the Data view (status, age, provider vs
  receipt time, latency, securities, origin mirror).
* **Real fundamentals ingested**: 21,698 records / 307 symbols (EPS, P/E,
  net-worth/share, capital, profit); ratios correctly unavailable without a price.
* Tests 2174 → **2179**, all passing.

**Carried forward.** SMC/ICT + order blocks + FVG; Wyckoff; valuation/DCF;
historical daily ingest to give every symbol a stored price (then P/E computes);
saved-screen tiling + background jobs; chart-pattern per-pattern invalidation.

---

## Session 25 (2026-10-16) — local release on :10000

**DONE.**
* Resilient free data: YONEPSE commit walk-back past the upstream merge-conflict
  commit (reporting the ref used); never repairs conflict markers.
* Real universe: 372 symbols / 515,327 bars (1995→2026-10-15) in the dev store.
* `fundamentals review --source …` unlocks ratios on reviewed inputs; P/E and P/B
  now derive (NABIL P/E 19.25).
* Startup port log + header freshness wording corrected.
* Dev instance verified on `127.0.0.1:10000`; 2184 tests pass.

**Remaining (genuine).**
* SMC/ICT + order blocks + FVG, Wyckoff, valuation/DCF — NOT STARTED.
* Dividend yield unavailable (no DPS records in the free source).
* Historical intraday / true second-level feed — BLOCKED (no permitted free source).
* Public deployment — BLOCKED (TLS termination, auth layer, secure cookies, friend token).
* Background collector lifecycle (scheduler/supervisor) — PARTIAL (in-process cache only).

---

## Session 26 (2026-10-16) — UI overhaul

**DONE.** Left-sidebar shell + global search; **Ideas** view (10 models, honest
gating); dashboard breadth bar; `GET /api/ideas[/{model}]`; reference + design +
plan docs; 2199 tests pass.

**NEXT (highest value, in order).**
1. **Chart workspace** — grouped toolbar + **overlay manager** so the clean default
   is enforced and overlays are opt-in (the reference's chart is uncluttered).
2. **Index hero chart** — requires loading `index_series` (official index only).
3. **Dashboard hero** — large index/price chart above the fold.
4. Portfolio & backtest visual upgrades (equity curve, returns histogram, trade
   donut, allocation).
5. Sector/breadth pages; comparators; valuation models (needs new inputs);
   chart-scanner thumbnails.

---

## Session 27 (2026-10-16) — chart workspace

**DONE.** Chart-as-hero layout + compact grouped toolbar; clean default
(candles+volume); opt-in analysis drawer with per-layer counts and result
highlighting; overlay caps (10 lines / 5 labels, nearest-first); indicator +
drawing popovers; chart type (candles/line), fit, zoom, fullscreen; per-symbol
layer persistence; collapsed "Advanced analysis" section. B-65…B-68 fixed.
2199 tests pass; 14 views 0 console errors.

**NEXT.**
1. Drawing tools: trendline, horizontal ray, vertical line, channel, text
   annotation, rectangle (only fib + hline exist).
2. Volume profile; crosshair-mode switch; multi-chart layout.
3. Dashboard index hero chart (needs `index_series` loaded).
4. Portfolio / backtest visual upgrades; comparators; valuation models.
5. Further S/R zone clustering (merge overlaps rather than dropping them).
