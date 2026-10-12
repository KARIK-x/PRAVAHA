# Written Data.pdf — Cross-Validation Report

## Method

Values extracted by visual inspection of the 52-page handwritten journal were compared
against the independent price history stored in Mega Tool's database
(`github.com/Aabishkar2/nepse-data`, **372 symbols**, 1995-07-20 → 2026-10-09).

> **Revised 2026-10-12** after the store was expanded from 60 to 372 symbols
> (`uv run megatool fetch`). The first version of this report concluded there was
> *no symbol overlap*, which was true of the 60-symbol set. With the full dataset,
> **36 of the 47 symbols in the extracted sample are now stored**, so the dated
> banking prices on page 11 became cross-checkable for the first time. The EPS
> conclusion is unchanged: the store holds prices, not fundamentals.

The comparison is **date-aware**: a price written in the journal at a given date is
compared to the stored close **on or near that date**, not to the latest stored close.
Corporate actions (bonus, rights) are not adjusted for in the stored data, so
differences are expected and noted rather than treated as errors.

## Settlements (pages 19-21, 23, 26, 28, 30, 32-33)

These are internal reconciliations: buy totals, sell totals, and net payable/receivable.
They can be validated **arithmetically** without any external source.

| Settlement | Page | Buy total | Sell total | Net (recorded) | Net (computed) | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 8C | 19 | 168,147.83 | 226,359.28 | 58,211.45 | 58,211.45 | **ARITHMETIC-VERIFIED** |
| 8D | 19 | 111,993.22 | 111,175.43 | 817.79 | 817.79 | **ARITHMETIC-VERIFIED** |
| 9A | 21 | ~~177,609.76~~ → **186,129.76** | 120,579.43 | 65,550.33 | 65,550.33 | **ARITHMETIC-VERIFIED** (corrected, see below) |
| 9C | 21 | 189,763.58 | 157,168.39 | 32,595.19 | 32,595.19 | **ARITHMETIC-VERIFIED** |
| 9D | 21 | 54,157.24 | 45,035.39 | 9,121.85 | 9,121.85 | **ARITHMETIC-VERIFIED** |

> **Correction history — settlement 9A (2026-10-12).** The buy total was first
> transcribed as `177,609.76`. Against the recorded net that gives
> `177,609.76 − 120,579.43 = 57,030.33`, which does **not** equal the recorded
> `65,550.33` — a discrepancy of `8,520.00`. The value `186,129.76` reconciles
> exactly: `186,129.76 − 120,579.43 = 65,550.33`. The corrected figure was found
> **by arithmetic alone** (defect B-02) and is pinned by
> `test_settlement_catches_the_transcription_error_that_was_actually_found`.
>
> **What this does and does not prove.** It proves the three figures on that row
> are mutually consistent. It is **not** independent verification of the digits
> against page 21 — no one has re-read the page since the correction. That
> re-read is **T-09**, and until it is done this row is *arithmetic-reconciled,
> visually unconfirmed*. The distinction matters: a transcription error of
> 8,520 that only arithmetic caught is also the reason to re-read rather than
> trust the reconciliation.

The settlement arithmetic is internally consistent where both sides are legible. This
is a **strong positive signal** about the reliability of the handwritten records:
the author's own reconciliation arithmetic is correct.

## Dated prices vs. stored closes (page 11, 2025-07-04)

The journal's dated fundamentals page records banking prices. A direct comparison
requires the symbol to be stored, the journal date to fall inside stored coverage,
and no corporate action between the two.

**Now checkable** (since the store holds 372 symbols):

| Symbol | Journal price (p.11, 2025-07-04) | Stored close (nearest trading day) | Gap | Reading |
| --- | --- | --- | --- | --- |
| SBI | 409 | 410.28 (2025-07-03) | **−0.31%** | consistent |
| EBL | 649 | 656.82 (2025-07-03) | **−1.19%** | consistent |
| SCB | 624 | 643.10 (2025-07-03) | **−2.97%** | consistent, but the largest gap |
| NABL | 498 | not stored | — | **NOT-CHECKED** |
| ADBL | 85 (p.6, undated) | 316.00 (2026-10-09) | unknown | **NOT-CHECKED** (no date, and ADBL trades far above 85 — an undated figure cannot be compared) |

**What this does and does not show.** All three differences are under 3%, and the
nearest stored date is 2025-07-03 rather than 07-04, so a single session of movement
plus the difference between whatever the author noted (LTP, open, or close) accounts
for gaps of this size. This is *consistent with a correct transcription* — a
mis-read digit would show a far larger error — but it is **not a confirmation**:
nothing here matches exactly, and no transcription can be certified from a ±3% band.

The undated ADBL figure on page 6 is **not** a check: it has no date, so any stored
close would be a guess.

## EPS values

EPS figures in the journal cannot be validated against the stored price data (which
has no fundamentals). No independent EPS source was accessible without authentication.
Symbol overlap no longer matters here — the obstacle is the *kind* of data.

| Symbol | Journal EPS (page) | Status |
| --- | --- | --- |
| TPC | 46.0 (p.1) | **UNVERIFIABLE** |
| SAHAS | 39.0 (p.1) | **UNVERIFIABLE** |
| SADBIM | 21.2 (p.2) | **UNVERIFIABLE** |
| SCB | 28.0 (p.11) | **UNVERIFIABLE** |
| NABL | 25.0 (p.11) | **UNVERIFIABLE** |

## What can be concluded

1. **The settlement arithmetic is correct.** This is verifiable internally and passes.
2. **The handwriting is internally consistent.** Settlement totals reconcile, which
   suggests the individual transaction amounts are likely correct.
3. **Three dated prices now sit within 3% of the independent stored close** — the
   first external corroboration these records have ever had. It supports the
   transcription; it does not certify it.
4. **No EPS value can be cross-validated** — the store has no fundamentals and no
   authenticated source was reachable.
5. **All extracted values remain UNREVIEWED** and must be confirmed by a human reader
   before any financial use.

## Symbols present in the stored dataset

Of the **47** distinct symbols in the extracted sample, **36** are now stored:

| Symbol | In stored set? | Stored coverage |
| --- | --- | --- |
| ADBL | Yes | 2010-09-16 → 2026-10-09 (3,659 bars) |
| NABIL | Yes | 2011-05-15 → 2026-10-09 (3,513 bars) |
| NICA | Yes | 2013-07-29 → 2026-10-09 (3,014 bars) |
| ENL | Yes | 2022-03-06 → 2026-10-09 (1,064 bars) |
| EBL | Yes | 2011-05-26 → 2026-10-09 (3,512 bars) |
| SCB | Yes | 2011-06-02 → 2026-10-09 (3,513 bars) |
| SBI | Yes | 2011-03-29 → 2026-10-09 (3,513 bars) |
| TPC | Yes | 2021-12-08 → 2026-10-09 (1,119 bars) |
| SAHAS | Yes | 2021-12-08 → 2026-10-09 (1,122 bars) |
| NABL | **No** | — |

Nine of these ten are now stored (they were not when this report was first
written). The remaining limitation is no longer *which symbols exist* but that
the journal's price pages are mostly undated, and only page 11 carries a date.

This overlap is the basis for the PDF integration in the Research Assistant: when the
assistant answers a question about a symbol that appears in both the journal and the
stored data, it can show both the journal's historical value and the stored price,
clearly labelled with their different dates and sources.

---

## Extraction manifest — all 52 pages

Counts below are read from the artefacts on disk, not asserted from memory.
Regenerate the OCR column with `uv run megatool pdf list`.

### Coverage

| Measure | Count | Notes |
| --- | ---: | --- |
| Pages in `WRITTENdata.pdf` | **52** | derived from the document itself, never a hard-coded constant |
| Pages rendered to PNG | 52 | `data/written_pdf/raw_pages/` |
| Pages OCR was **attempted** on | 52 | `data/written_pdf/raw_ocr/` |
| …produced empty output | 28 | handwriting has no glyph boundaries |
| …produced readable text | 17 | page furniture, not the tabular content |
| …produced gibberish | 7 | non-empty but unusable |
| Pages with **transcribed records** | **6 of 52** | pages 1, 2, 6, 11, 17, 52 |
| **Pages never transcribed** | **46 of 52** | — |
| Records in the sample file | 64 | `data/written_pdf/extracted_sample.json` |
| Records in the **real store** | **0** | `pdf_records`, verified on `:8710` |

### Per-page detail (the six transcribed pages)

| Page | Records | OCR bytes | OCR usable? | Review state |
| ---: | ---: | ---: | --- | --- |
| 1 | 12 | 0 | empty | 12 `unreviewed` |
| 2 | 9 | 0 | empty | 9 `unreviewed` |
| 6 | 15 | 171 | text only | 15 `unreviewed` |
| 11 | 16 | 274 | text only | 16 `unreviewed` |
| 17 | 2 | 0 | empty | 2 `unreviewed` |
| 52 | 10 | 0 | empty | 10 `unreviewed` |

All other 46 pages: 0 records.

### Records by review state

| State | Count |
| --- | ---: |
| `extracted` / `reviewed` / `corrected` | **0** |
| `uncertain` | **0** |
| `rejected` | **0** |
| **`unreviewed`** | **64** |
| **Unprocessed (no records at all)** | **46 pages** |

Every extracted record in this build is `unreviewed`. Nothing has been promoted
by a human reader, and nothing may enter portfolio accounting or current
fundamentals in that state.

### Field-level provenance actually preserved

| Requested | Where it lives | Status |
| --- | --- | --- |
| page | `pdf_records.page` | IMPLEMENTED |
| table / row | `pdf_records.source_ref` | IMPLEMENTED (populated as `"table, row/column"` where identifiable) |
| source text | `pdf_records.raw_text` | IMPLEMENTED in schema — **absent from `extracted_sample.json`** |
| normalised value | `pdf_records.value` (JSON) | IMPLEMENTED |
| confidence | `pdf_records.confidence` (`high`/`medium`/`low`/`uncertain`) | IMPLEMENTED |
| review state | `pdf_records.review_status` | IMPLEMENTED |
| **extraction method** | — | **NOT IMPLEMENTED** — no column records Vision vs Tesseract vs transcription |
| **correction history** | `pdf_records.note` only | **PARTIAL** — no append-only audit trail; an overwrite via `ON CONFLICT … DO UPDATE` leaves no prior value |
| page integrity | `pdf_imports.content_hash` + `page_sha256()` | IMPLEMENTED |

`re-run → no duplicates` holds **for the same filename** (verified: 0 inserted,
2 updated). A renamed copy of identical bytes creates a second `import_id` and
`query_records` has no import filter — see B-18.

The original `WRITTENdata.pdf` is never written to: SHA-256
`d7ea6fe42ad3427fc12b8b19…`, mtime unchanged since 08:33 on 2026-10-12, and the
file is git-ignored.
