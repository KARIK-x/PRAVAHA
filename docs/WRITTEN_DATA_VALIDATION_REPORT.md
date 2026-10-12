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
| 8C | 19 | 168,147.83 | 226,359.28 | 58,211.45 | 58,211.45 | **VERIFIED** |
| 8D | 19 | 111,993.22 | 111,175.43 | 817.79 | 817.79 | **VERIFIED** |
| 9A | 21 | 177,609.76 | — | 65,550.33 | — | Partial (sell side illegible) |
| 9C | 21 | 189,763.58 | 157,168.39 | 32,595.19 | 32,595.19 | **VERIFIED** |
| 9D | 21 | 54,157.24 | 45,035.39 | 9,121.85 | 9,121.85 | **VERIFIED** |

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
