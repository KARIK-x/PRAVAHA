# Task queue

Prioritised next work. Status: **DONE**, **BLOCKED** (waiting on an external
fact or a human decision), **NEXT**, **BACKLOG**.

---

## Completed this session (2026-10-12)

| ID | Task | Evidence |
|---|---|---|
| T-01 | Verify the report's claim that "64 PDF records" were OCR output | **Refuted.** 64 = rows in git-ignored `data/written_pdf/extracted_sample.json`, a *visual transcription* sample. The real store has **0** PDF records. `raw_ocr/` holds 52 files, 24 non-empty, all gibberish. |
| T-02 | Benchmark handwriting extraction on 5 pages | **Done.** Apple Vision 90.2% numeric vs Tesseract 4.3%. Report's "Apple Vision cannot read handwriting — Confirmed" is **refuted for this document**. |
| T-03 | Diagnose the web-search failure | **Diagnosed.** 3/3 attempts → `unknown: "Web search cancelled"`. Not an auth error, not "tool not found". Environment limitation. |
| T-04 | Investigate the HTTP 401 | **Confirmed** as 401 with body `WARNING: UNAUTHORIZED ACCESS`. The report's `setTLSVerification(False)` fix rejected — measured `ssl_verify_result 0`, no certificate error. |
| T-05 | Test recommended data sources | ShareSansar 200, nepsedata.com 200, ShareSansar Scraper 200, nrb.org.np 200, nepsealpha 403. Bulk workbook `Data/combined_excel.xlsx` verified: HTTP 200, ~41 MB, last-modified 2026-10-11. |
| T-06 | Multi-factor ranking (report §8) | **DONE.** `megatool/ranking.py` + `POST /api/rank` + UI panel. 27 unit + 10 API tests. |
| T-07 | Fundamentals Lab (report §7) | **DONE (mechanism).** `megatool/fundamentals.py`, schema v4, 3 endpoints, 11th tab. 44 unit + 7 API tests. |
| T-08 | Fix settlement sign defect | **DONE.** See `KNOWN_BUGS.md` B-01. |

Test count: 511 → **602**. Two commits: `092ce95`, `2806181`.

---

## NEXT — highest value first

### T-09 · Re-verify the PDF transcription page by page
B-02 proved a real 8,520 NPR transcription error existed in the earlier audit
and was only caught by arithmetic. The audit document still carries the old
number.

*Approach:* re-run `scripts/score_benchmark.py`'s method across all 52 pages —
Apple Vision as first pass, then arithmetic self-checks (`buy − sell = net`,
totals vs. line items) to flag disagreements, then visual review of only the
flagged rows.
*Acceptance:* every settlement/total on every transcribed page either
reconciles or is marked unreconcilable with a reason.

### T-10 · Owner decision: Ollama upgrade
Local VLM benchmarking is the one part of Priority 2 left undone. Ollama 0.5.7
rejects every vision model with `412`. Latest is v0.40.3.
*Needs the owner* — updating an installed application is a machine change
(Rule 8). If approved: pull a small vision model (≈2 GB, fits 8 GB RAM with a
3B variant, not a 7B), benchmark against the same five pages, compare with
Apple Vision before adopting anything.

### T-11 · Owner decision: sector data
`security_master.sector` is NULL for all 372 symbols (B-07), which blocks
sector-relative ranking and peer comparison. Two legitimate routes:
1. Owner supplies a CSV mapping symbol → sector (preferred — import path
   already exists in principle for fundamentals, would need a small sibling).
2. Owner authorises ShareSansar collection; the field is present in that
   site's public company-page HTML.

### T-12 · Verify NEPSE cost, tax and settlement assumptions
The backtest fee rate is a labelled PLACEHOLDER (B-11). The report quotes
0.24–0.36% commission + 0.015% SEBON + Rs 25 DP charge, 7.5%/10% capital gains
tax, T+2 settlement — **none verified this session**, and web search is
unavailable. Do not hard-code any of them.
*Needs:* an authoritative source (SEBON / NEPSE / broker notice) and ideally
the owner's own contract note as ground truth. Then make them named,
configurable presets with a source and date attached.

### T-13 · Import a real floor sheet
Floor-sheet analysis has only ever run on synthetic CSVs. Import one real
published sheet and check the summary against the published page.
*Acceptance:* row counts and totals match the source; discrepancies explained.

### T-14 · Re-check the official NEPSE API
`uv run megatool probe` re-tests the 401. Never work around it; never store
credentials.

---

## BACKLOG

| ID | Task | Note |
|---|---|---|
| T-15 | ShareSansar Scraper bulk import as a second price source | Workbook verified reachable (~41 MB). Needs a licensing decision first — no LICENSE on the archive either. Would give a cross-check against the GitHub dataset. |
| T-16 | Walk-forward validation of the ranking (report §8.5) | Rank monthly using only data up to that month, form top/bottom quartiles, measure next-month spread. Chronological only; no look-ahead. Label as research, not evidence of profit. |
| T-17 | Relative-strength factor | Blocked on an index series (B-10). Declared unavailable today. |
| T-18 | News / Events and multi-factor *fundamental* ranking | Both blocked on T-11/T-12. |
| T-19 | Transcribe PDF pages 18–33 | Settlement arithmetic self-checks make these the highest-yield pages (T-09). |
| T-20 | `TASK_QUEUE.md` / `KNOWN_BUGS.md` upkeep | Created this session; update with every fix. |

---

## Explicitly not doing

* Reverse-engineering the official NEPSE API's token scheme.
* Disabling TLS verification anywhere.
* Scraping ShareSansar without the owner's authorisation.
* Uploading `WRITTENdata.pdf` to any external service.
* Autonomous live trading, broker/Mero Share credentials, invented trading APIs.
