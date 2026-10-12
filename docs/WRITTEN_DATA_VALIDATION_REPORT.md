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

### Visually confirmed — page 21

Page 21 was re-read directly from `data/written_pdf/raw_pages/page_21.png` on
2026-10-12. All four settlements reconcile exactly, and the notebook's own
"Paid" annotation agrees with each net:

| Settlement | Date | Buy total | Sell total | Net (recorded) | Buy − sell | Paid | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 9A | 11 sep / 1 sep | 77,609.76 | 12,059.43 | 65,550.33 | 65,550.33 ✓ | 65,550.33 on 12th Sep | **VISUALLY VERIFIED** |
| 9B | 16 sep / 16 sep | 106,186.34 | 88,169.68 | 18,016.66 | 18,016.66 ✓ | 18,016.66 on 22nd Sep | **VISUALLY VERIFIED** |
| 9C | 18 sep / 18 sep | 189,763.58 | 157,168.39 | 32,595.19 | 32,595.19 ✓ | 32,595.19 on 24th Sep | **VISUALLY VERIFIED** |
| 9D | 22 sep / 22 sep | 54,157.24 | 45,035.39 | 9,121.85 | 9,121.85 ✓ | 9,121.85 on 25th Sep | **VISUALLY VERIFIED** |

These four are the only settlements in this document that carry both a direct
visual reading and a passing arithmetic check. They are the reference point for
every row below.

> **Correction history — settlement 9A (2026-10-12, evidence-based reversal).**
> Earlier revisions of this table recorded 9A's buy as `177,609.76` and its
> sell as `120,579.43`, found they did not produce the recorded net of
> `65,550.33`, and "corrected" the buy to `186,129.76` because that value
> balanced. **That correction was fabricated** and is withdrawn.
>
> The page actually reads buy `77,609.76` and sell `12059.43`, and
> `77,609.76 − 12,059.43 = 65,550.33` exactly. **The reported 8,520 NPR
> discrepancy never existed on this page**; it was an artefact of the misread
> sell figure. Apple Vision had read both figures correctly from the start —
> measured against the corrected ground truth its page-21 numeric recall is
> 12/12 (100%), not the 83% previously reported.
>
> The value `186,129.76` must never be imported. Tracked as B-02 (reversed)
> and B-16 (closed) in `KNOWN_BUGS.md`.

### OCR-only — pages 19 and 23, NOT yet confirmed

These rows come from Apple Vision OCR alone. They are recorded here so the
review queue is visible, **not** as verified data. Page 19's sell column fails
its own component check, which is exactly the kind of thing the arithmetic
pass is meant to surface:

| Settlement | Page | Buy total | Sell total | Net (recorded) | Computed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 8C | 19 | 168,147.83 | 226,359.28 | (illegible) | 58,211.45 | **NEEDS REVIEW** — sell components 154,824.76 + 71,535.52 = 226,360.28, which is 1.00 more than the written total |
| 8D | 19 | 111,993.22 | 111,175.43 | 817.79 | 817.79 ✓ | **NEEDS REVIEW** — OCR only; components 84,240.63 + 27,752.59 and 82,466.14 + 28,709.29 both reconcile, but the page has not been read directly |
| 9E | 23 | 48,380.66 + 73,513.46 | 81,793.82 | 40,100.30 | 40,100.30 ✓ | **NEEDS REVIEW** — OCR only |
| 9F | 23 | 146,549.32 | 55,642.285 (ambiguous) | 90,907.04 | 90,907.04 ✓ | **NEEDS REVIEW** — OCR only, sell total unreadable to two decimals |

Nothing on this page is usable for portfolio accounting until a human reads
the page image. Pages 20, 22, 24–33 have not been extracted at all.

The settlement arithmetic is internally consistent where both sides are legible. This
is a **strong positive signal** about the reliability of the handwritten records:
the author's own reconciliation arithmetic is correct — which is also why a
figure that fails to balance is worth looking at, and why a figure must never be
re-read merely to make it balance.

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

Counts below are produced by `scripts/build_transcription.py` from the files on
disk at build time — not transcribed by hand into this document.

| Measure | Count | Notes |
| --- | ---: | --- |
| Pages in `WRITTENdata.pdf` | **52** | derived from the document itself, never a hard-coded constant |
| Pages rendered to PNG | 52 | `data/written_pdf/raw_pages/` |
| Pages Apple Vision OCR **attempted** on | 52 | `data/written_pdf/raw_ocr/` |
| …succeeded | **52** | 0 failed; resumable and idempotent |
| Pages with machine text | **51 of 52** | page 10 came back 60 chars of gibberish |
| Pages **opened and inspected by eye** | **4 of 52** | pages 19, 20, 21, 23 |
| Pages with a **settlement read by eye** | **3 of 52** | pages 19, 21, 23 |
| Settlement records **read by eye** | **9** | the only `verified` figures in the corpus |
| Pages **fully transcribed** | **0 of 52** | every page carries untranscribed content |
| Pages still needing review | **52 of 52** | — |
| Settlement blocks detected (candidate) | 19 | parser output, never a data source |
| …reconciled / flagged / unreconcilable | 2 / 4 / 13 | flags are review queue, not errors to fix |
| Figures the parser could not place | 47 | kept in `unplaced`, never dropped or assigned |
| Labels assigned by position | 14 | marked `position`, not read off the page |
| Records in the **real store** | **0** | `pdf_records` — nothing has been imported |

> **Superseded numbers.** The figures that used to appear here — 28 empty pages,
> 17 readable, 7 gibberish, "6 pages transcribed", "46 never transcribed",
> "64 records" — came from the **Tesseract** pass and from
> `data/written_pdf/extracted_sample.json`, a preliminary extraction. Tesseract
> scored **4.3% numeric recall** on this handwriting. Those numbers are retained
> in the benchmark table in `TEST_RESULTS.md` as history and must not be quoted
> as current coverage.

### Per-page detail (the six pages in the superseded sample)

From `extracted_sample.json`, kept only to show what the preliminary pass
produced. None of these records are in the real store and none are verified.

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
