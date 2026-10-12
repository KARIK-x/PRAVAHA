# Written Data.pdf — Cross-Validation Report

## Method

Values extracted by visual inspection of the 52-page handwritten journal were compared
against the independent price history stored in Mega Tool's database
(`github.com/Aabishkar2/nepse-data`, 60 symbols, 1995-07-20 → 2026-10-09).

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

## Fundamentals vs. stored prices

The journal records prices at specific dates. The stored database has closes for
60 symbols. A direct comparison is only possible when:

1. The symbol is in the stored dataset (60 of ~372 NEPSE symbols).
2. The journal date falls within the stored coverage period.
3. No corporate action occurred between the journal date and the stored date.

These conditions are rarely met simultaneously. The journal's most recent dated page
(page 11, 4 July 2025) records prices for banking stocks; the stored data ends
2026-10-09, so a 15-month gap exists during which corporate actions may have occurred.

| Symbol | Journal price (page, date) | Stored close (nearest date) | Date gap | Status |
| --- | --- | --- | --- | --- |
| SCB | 624 (p.11, 2025-07-04) | not in stored set | — | **NOT-CHECKED** |
| SBI | 409 (p.11, 2025-07-04) | not in stored set | — | **NOT-CHECKED** |
| EBL | 649 (p.11, 2025-07-04) | not in stored set | — | **NOT-CHECKED** |
| NABL | 498 (p.11, 2025-07-04) | not in stored set | — | **NOT-CHECKED** |
| ADBL | 85 (p.6, undated) | 316.00 (2026-10-09) | unknown | **NOT-CHECKED** |

None of the symbols on the dated fundamentals page are in the stored 60-symbol set.
The stored set (ADBL, NABIL, NICA, etc.) does not overlap with the banking stocks
recorded on page 11.

## EPS values

EPS figures in the journal cannot be validated against the stored price data (which
has no fundamentals). No independent EPS source was accessible without authentication.

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
3. **No price or EPS value can be cross-validated** against the stored dataset because
   there is no symbol overlap on dated pages.
4. **All extracted values remain UNREVIEWED** and must be confirmed by a human reader
   before any financial use.

## Verified symbols present in the stored dataset

The stored dataset covers 60 symbols. The journal references many symbols; those
present in the stored set can have their **current** prices shown alongside the
journal's historical prices, with the date gap stated:

| Symbol | In stored set? | Stored coverage |
| --- | --- | --- |
| ADBL | Yes | 2010-09-16 → 2026-10-09 |
| NABIL | Yes | (in 60-symbol set) |
| NICA | Yes | (in 60-symbol set) |
| ENL | Yes | (in 60-symbol set) |
| EBL | No | — |
| SCB | No | — |
| SBI | No | — |
| NABL | No | — |
| TPC | No | — |
| SAHAS | No | — |

This overlap is the basis for the PDF integration in the Research Assistant: when the
assistant answers a question about a symbol that appears in both the journal and the
stored data, it can show both the journal's historical value and the stored price,
clearly labelled with their different dates and sources.
