# Task queue

Prioritised next work.

**Status categories** (every task below carries one):

| Category | Meaning | Current members |
|---|---|---|
| **COMPLETED AND VERIFIED** | Built, tested, and exercised end-to-end with evidence recorded | T-A1…T-A12, T-16 *(the validation was run and its result — failure — is verified)*, T-23, T-24, B-17, B-18, route inventory, security pass, **swing/market-structure engine** |
| **IMPLEMENTED BUT NOT FULLY VERIFIED** | The mechanism works and is tested, but has never run on real input | Fundamentals Lab (0 records), Floor-sheet analysis (synthetic only), PDF extraction pipeline (0/52 pages transcribed) |
| **FAILED** | Executed honestly and did not pass | **T-16 ranking validation** — top quantile underperformed the bottom in *every* window; no alternative weighting passed. Recorded, not hidden |
| **BLOCKED BY EXTERNAL INPUT** | Cannot proceed without an owner file, credential, permission or authoritative source | T-09 (image access), T-11 (sector CSV), T-12 (verified tax/fee rates), T-10 (Ollama approval), T-13 (real floor sheet), T-15 (licensing), B-09/B-10/B-11/B-12, OmniRoute key |
| **DEFERRED WITH REASON** | Deliberately parked; reason stated | T-14 (re-check official API), T-17 (needs index data = B-10), T-18 (needs sector data = T-11), T-20, T-21, T-25, News/Events (no machine-readable source, `PROJECT_STATUS` #7), Bounded research agent (web search unavailable, #15) |

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

### T-26 · Fibonacci analysis module — **READY** *(unblocked by T-A12)*

* **User impact:** high. §5 is a mandatory capability and is the natural first
  consumer of the swing engine: retracements and extensions are anchored on
  swing highs/lows.
* **Technical dependency:** `megatool/ta/swings.py` (done). The module is pure
  arithmetic once the anchors exist.
* **Data dependency:** none beyond stored bars.
* **Safe path:** retracements (23.6/38.2/50/61.8/78.6) and extensions
  (127.2/138.2/150/161.8/200/261.8) computed from an explicitly stated anchor
  pair; **the anchoring methodology must be printed in the response** (§5.1),
  and the 50% level labelled a market convention, not a Fibonacci ratio.
* **Validation:** hand-computed levels for a known high/low pair; a test that
  the response states its anchors; confluence reported as overlap, never as
  proof a level will hold (§5.4).
* **Owner decision:** none.

### T-27 · Candlestick pattern engine — **READY**

* **User impact:** medium-high. §8 mandatory. Self-contained (needs only OHLCV),
  so it can proceed independently of T-26.
* **Safe path:** single/two/three-candle patterns with **explicit tolerances**
  and **context** (prior trend, proximity to a swing level) — §8.4 requires
  context rather than isolated labels. Labelled DETECTED.
* **Validation:** hand-built candles for each pattern; a test that a pattern
  in the middle of a range is reported with weaker context than one at a swing
  level.
* **Owner decision:** none.

### T-28 · Elliott Wave / harmonic candidates — **BLOCKED-ON-DESIGN**

* **User impact:** high, but §4/§7 require alternative counts, invalidation
  levels and explicit uncertainty labels. Building this badly would be worse
  than not building it.
* **Technical dependency:** T-A12 (done) supplies the legs; T-26 supplies the
  Fibonacci ratios the harmonic definitions require.
* **Safe path:** after T-26. Report *candidates* with invalidation levels and
  competing interpretations; never a single asserted count.
* **Owner decision:** none to start, but review of the output framing is
  worthwhile before it reaches the UI.

### T-09 · Re-verify the PDF transcription page by page — **IN PROGRESS**

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
