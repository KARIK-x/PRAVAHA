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
| **Apple Vision** (macOS, `VNRecognizeTextRequest`) | **71.7%** | **90.2%** | **33 / 46** |

**Decision:** the report's claim is **refuted for this document**. Apple Vision
is already installed, needs no download, and processes a page in 0.8–1.7 s.
It is adopted as the practical first-pass extractor.

**Still true:** ~90% is not good enough to feed accounting directly. Apple
Vision dropped digits from page 21's largest settlement (read `77609.76` for
`186129.76`). Arithmetic self-checks are what catch that class of error.

Reproduce: `uv run python scripts/score_benchmark.py`.

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
