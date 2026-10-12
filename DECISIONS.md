# Decisions

Every decision that shaped Mega Tool, with the evidence behind it and what was
rejected. Newest first.

---

## 2026-10-12 — Research-report integration pass

The project was handed an outside document,
`MEGA_TOOL_RESEARCH_REPORT.md`, as an independent research input. It was
**evaluated, not adopted wholesale**. Claims were checked against the running
code before anything was changed.

### Decision: benchmark extraction methods before believing the report's OCR claim

The report marked "Tesseract/Apple Vision cannot read handwriting" as
**Confirmed**, citing a third-party blog article. That claim had never been
tested against this document — `data/written_pdf/raw_ocr/` contains only
Tesseract output.

A benchmark was run on five representative pages (p02, p09, p11, p18, p21)
against hand-built ground truth:

| Method | Numbers (exact) | Numbers (numeric) | Symbols recovered |
|---|---|---|---|
| Tesseract 5.5.0 | 3.3% | 4.3% | 0 / 46 |
| Apple Vision (as-is) | 73.9% | 92.4% | 33 / 46 |
| **Apple Vision, best of 4 rotations** (`scripts/vision_ocr_batch.swift`) | **75.0%** | **94.6%** | **33 / 46** |

**Decision:** the report's claim is **refuted for this document**. Apple Vision
is already installed, needs no download, and processes a page in 0.8–1.7 s.
It is adopted as the practical first-pass extractor, run over all 52 pages by
`scripts/run_vision_ocr.py`. Orientation detection is kept because it never
scored worse than the as-is pass on any page and lifted page 18's numeric
recall from 74% to 84%. The figures above are against the *corrected* ground
truth; page 21 previously read 83% only because its target was wrong.

**Still true:** ~95% is not good enough to feed accounting directly. Dense
transaction pages still lose digits, so every extracted value stays `OCR_ONLY`
until a human checks it against the page image. Arithmetic self-checks are what
catch that class of error.

Reproduce: `uv run python scripts/score_benchmark.py`.

### Decision: arithmetic may falsify a reading but may never rewrite one

A balancing equation is evidence *about* a transcription, never a licence to
change it. An earlier audit noticed page 21 settlement 9A did not balance and
adopted the one figure that did — `186,129.76` — which is not written anywhere
on the page. The re-read showed the true figures (`77,609.76 / 12,059.43 /
65,550.33`) already balance exactly; the discrepancy had come from a misread
sell, not from the buy.

**Decision:** extraction never substitutes a value to close an equation. A
failing block is marked `discrepancy` and keeps its raw lines; an unreadable
token returns `None`; a correction can only be recorded through
`append_correction`, which requires a stated reason and preserves the original
reading and every earlier entry. Tracked as `KNOWN_BUGS.md` L-07.

### Decision: settlement reconciliation compares magnitudes, not signs

`validate_settlement_reconciliation` computed `sell - buy` and compared it to
the recorded net. Page 21 of the source PDF labels its figure **"Net Payable =
buy − sell"**, so all four *correct* settlements were rejected.

Both pre-existing tests still pass under a magnitude comparison, and a
genuinely wrong net still raises. Fixed with a regression test covering all
four real settlements.

### Decision: no unofficial NEPSE API client, no TLS downgrade

The report recommends `NepseUnofficialApi` and `setTLSVerification(False)`.

* **Rejected — TLS downgrade.** Measured directly: `ssl_verify_result 0`.
  There is no certificate error. The observed failure is an HTTP/2
  `PROTOCOL_ERROR`, and forcing HTTP/1.1 yields an empty reply. The
  recommendation addresses a problem that does not exist.
* **Rejected — reverse-engineered auth.** The official endpoint returns
  `HTTP 401` with body `WARNING: UNAUTHORIZED ACCESS`. Automating a token
  scheme to get past that is an access-control bypass, which this project does
  not do.

### Decision: ShareSansar is reachable but not automated

Single-GET investigation found the company page returns 200 and does expose
`symbol` and `sector` in its HTML — which would fill the currently-empty
`security_master.sector` column. However, the per-company financial reports
are served by a **CSRF-protected AJAX POST**.

**Decision:** no scraper is built. A public page does not imply permission to
automate collection. Sector-relative ranking stays declared-unavailable until
the owner supplies data or authorises collection.

### Decision: ranking is universe-relative, with gaps declared

Because no sector and no published index series exist, the ranker scores
against the whole stored universe and lists five factors under `unavailable`
with reasons (P/E, P/B, dividend yield, index-relative strength, sector
percentile) at zero weight. Silently substituting a proxy would misrepresent
what the score means.

### Decision: Fundamentals Lab is import-driven

No verified fundamentals source is connected, and none may be assumed. The Lab
therefore stores only caller-supplied CSV, and every value carries source,
reporting period, unit and verification level. Ratios refuse unreviewed inputs
and incompatible periods rather than producing a plausible number.

---

## 2026-10-12 — Evidence-based completion audit

### Decision: report findings as measured, and fix only what the evidence supports

The audit's job was to reconcile reported progress against the repository, not
to add features. Three defects were found by measuring rather than reading, and
all three were fixed because each is small, contained, and has **no live caller**
(verified by grep across the repo):

| Defect | Measured before the fix | Fix |
|---|---|---|
| **B-13** lakh parser | 6 of 15 spellings wrong; `"2 lakh"` → `2.0` (**100,000×**) | match `\b(?:lakh?|lac|l)\b` or a digit + `l` |
| **B-14** ratio operands | `ratio_pe(500, revenue_record)` → `0.1000` presented as P/E | `_refuse_wrong_field` / `_refuse_wrong_unit` on all three ratios |
| **B-15** staleness guard | `ratio_pe(500, eps_from_2015)` → `20.00`, no complaint | `price_as_of` made **required**; omission is a `TypeError` |

Not fixed, because each changes observable behaviour and is the owner's call:
**L-05** (median substitution moves 284 of 369 ranks), **L-06** (inverted
factors never reach 100), **B-17** (`invalid` bars reach indicator maths),
**B-18** (renamed-PDF re-import duplicates). Each is documented and pinned by a
test so it cannot regress unnoticed.

### Decision: the ranking's "reproducible by hand" claim is qualified, not repeated

Measured on the real universe: contributions reproduce the score to a **maximum
of 2.0e-4** (median 7.1e-15), because contributions are rounded to 4 decimals
while the score is rounded once from unrounded parts. That is a rounding
artifact, not an error, and it never changes a displayed value — but the honest
statement is "reproduces to 4-decimal rounding", not "sums exactly".

### Decision: arithmetic reconciliation is labelled separately from verification

Settlement 9A's corrected figure (`186,129.76`) is established **by arithmetic
alone**: it is the only value of the three that makes `buy − sell = net`. That
is a self-check of one page against itself. It is *not* independent confirmation
of the digits against the source document, and the validation report now says
so explicitly until T-09 re-reads page 21.

### Decision: data sources are classified by what they delivered, not by HTTP status

* **Verified usable** — `github.com/Aabishkar2/nepse-data`: 514,018 rows,
  372/372 symbols, per-row `source`/`source_url`/`retrieved_at`, and an
  ingestion log with UTC run times, coverage and a `synthetic` flag.
* **Merely reachable** — ShareSansar, nepsedata.com, nrb.org.np return 200.
  A 200 proves nothing about completeness, permission, or usefulness; no field
  of theirs has been ingested.
* **Blocked** — official NEPSE (401, by policy), nepsealpha (403).

Reachability is recorded as reachability.

### Decision: no Ollama change without approval

Inspected read-only: CLI and daemon **0.5.7**, app bundle metadata **0.33.3**,
2 installed models (neither vision-capable), 8 GB RAM. The 412 is Ollama's
own registry gate — it refuses at the manifest **before downloading any
weights** — reproduced without installing anything and with the model list
verified unchanged. Upgrading an installed application is a machine change.

---

## Standing decisions (from earlier sessions)

| # | Decision | Reason |
|---|---|---|
| 1 | Local FastAPI on `127.0.0.1`, GET-only CORS | Personal tool; never expose an interface or accept credentials. |
| 2 | DuckDB for market data, SQLite for state | Analytical scans vs. transactional records; fresh connection per operation. |
| 3 | Real data only from `github.com/Aabishkar2/nepse-data`, git-ignored, per-row attribution | No LICENSE published — personal local use, never redistributed. |
| 4 | Research Assistant is a deterministic rules engine, not an LLM | It must not hallucinate prices; it refuses predictive/prescriptive questions. |
| 5 | Naive baseline leads every forecast | A forecast that hides its baseline overstates its own skill. |
| 6 | PDF extraction is visual transcription with per-value confidence | Automated OCR failed on 42/52 pages; nothing is "verified" until reviewed. |
| 7 | No autonomous trading, no broker/Mero Share credentials | Standing safety rule. |
| 8 | Backtest fee rate labelled PLACEHOLDER | The real NEPSE schedule was not verified against an authoritative source. |
| 9 | Synthetic fixtures never mixed with real records | Every dataset carries origin and timestamp; stale/incomplete stays visible. |
