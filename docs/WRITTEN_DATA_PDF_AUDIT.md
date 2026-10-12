# Written Data.pdf — Extraction Audit

## Document facts

| Attribute | Value |
| --- | --- |
| Filename | `WRITTENdata.pdf` (moved from `~/Downloads/AI Trading Nipsy/Written Data.pdf`) |
| Location | Project root: `/Users/ashim/Downloads/AI trading NEPSE/WRITTENdata.pdf` |
| Size | 7,281,475 bytes (7.3 MB) |
| Pages | 52 |
| PDF version | 1.7 |
| Text layer | **None** — fully scanned/handwritten |
| Orientation | Mixed: pages 1-25 landscape (842×595 pt), pages 26-52 portrait (595×842 pt) |
| OCR tool | tesseract 5.5.0 (eng/osd/snum) via PyMuPDF 1.28.2 rendering at 300 DPI |

## OCR result

Automated OCR was run on all 52 pages. **It failed for 42 of 52 pages** (empty or
gibberish output). Tesseract is designed for printed text, not handwriting. The 10
pages that produced output were largely unreadable noise.

| Outcome | Pages |
| --- | --- |
| Empty OCR output | 42 |
| Gibberish / unusable | 8 |
| Partially readable | 2 |

**Conclusion: automated OCR is not viable for this document.** The extraction below is
based on direct visual inspection of each page by the AI assistant, with confidence
levels assigned per value. This is the honest maximum that can be achieved without
manual transcription by a human.

## Confidence levels

| Level | Meaning |
| --- | --- |
| `HIGH` | Value is clearly legible; symbol, digits, and decimal points are unambiguous |
| `MEDIUM` | Value is legible but one character could be misread (e.g. `1` vs `7`, `0` vs `8`) |
| `LOW` | Value is partially legible or the handwriting is ambiguous; recorded for review |
| `UNCERTAIN` | Cannot be read reliably; recorded as a placeholder for human review |

## Page-by-page inventory

| Page | Orientation | Content | Extraction |
| --- | --- | --- | --- |
| 1 | Landscape | "Hydro 01 EPS" — hydropower stock symbols with EPS values in 4 columns | Partially extracted |
| 2 | Landscape | Fundamentals table (Stocks, EPS, Net worth, Float, DPS, Holdings) — Commercial Banking section | Partially extracted |
| 3 | Landscape | Stock symbol list (UNLB, MBHL, KBSH, HATHY, ECFC, MFIL, RSML, RLEL, ECL, CORBL, KHPL, UHEWA, SWASTIK) | Extracted (symbols only) |
| 4 | Landscape | Fundamentals table — Hydropower, Microfinance, Dev. Bank sections | Partially extracted |
| 5 | Landscape | "Fundamental Stocks" (Sep/Nov 2021) — sector groupings with prices | Partially extracted |
| 6 | Landscape | Price tracking table (Monthly/Weekly/Daily/15min columns) | Partially extracted |
| 7 | Landscape | Price tracking table continued + "Mostly Accumulated" section | Partially extracted |
| 8 | Landscape | Price tracking table continued + "Mostly Accumulated" section | Partially extracted |
| 9 | Landscape | Microfinance fundamentals table (Price, Float, EPS, Net worth, P/E, Accumulation) | Partially extracted |
| 10 | Landscape | "Banking Sector" fundamentals table (Stock, Price, EPS, Net worth, P/E) | Partially extracted |
| 11 | Landscape | Banking fundamentals table (Price, Scrips, Float, EPS, Net worth, P/E, Accumulation) — dated 4 July 2025 | Partially extracted |
| 12 | Landscape | "Most Accumulation" rankings — Commercial Bank, Microfinance, Finance, Dev Banks (1yr/6m/1m) | Partially extracted |
| 13 | Landscape | "Most Accumulation" — Life Insurance, Non-Life Insurance, Hydropower | Partially extracted |
| 14 | Landscape | "Most Accumulation" — Manufacturing, Hotels, Others | Partially extracted |
| 15 | Landscape | "Most Accumulation" — Tradings, Investment | Partially extracted |
| 16 | Landscape | Hydropower fundamentals table (Price, EPS, Networth, Float) | Partially extracted |
| 17 | Landscape | Technical analysis notes (MACD, Bollinger Band checklists) — rotated 90° | Not extracted (notes) |
| 18 | Landscape | Trading record (August 2024) — Buy/Sell columns with quantities, prices, settlement amounts | Partially extracted |
| 19 | Landscape | Settlement reconciliation (8C, 8D, 8E) — buy/sell totals, net payable/receivable | Partially extracted |
| 20 | Landscape | Trading record (August 2024) continued | Partially extracted |
| 21 | Landscape | Settlement record (9A, 9B, 9C, 9D) — rotated | Partially extracted |
| 22 | Landscape | Trading record (27 Aug – 16 Sep) | Partially extracted |
| 23 | Landscape | Settlement record (9E, 9F) — rotated | Partially extracted |
| 24 | Landscape | Trading record (18 Sep – 29 Sep) | Partially extracted |
| 25 | Landscape | Trading record (October) | Partially extracted |
| 26 | Portrait | Trading record — rotated 90° (settlement 104, buy/sell dates and amounts) | Partially extracted |
| 27 | Portrait | Trading record (26 Nov – 3 Dec) | Partially extracted |
| 28 | Portrait | Settlement record (12A, 12B, 12C, 12D) | Partially extracted |
| 29 | Portrait | Trading record (8 – 18 Dec) | Partially extracted |
| 30 | Portrait | Settlement record (12D, 12E, 12F) | Partially extracted |
| 31 | Portrait | Chart/diagram page (mostly illegible) | Not extracted |
| 32 | Portrait | Settlement record (17A, 17B, 17C) | Partially extracted |
| 33 | Portrait | Settlement record (17D, 17E, 17F) | Partially extracted |
| 34 | Portrait | Fundamentals table (BPS, Net worth, Float, EPS) | Partially extracted |
| 35 | Portrait | Hydropower EPS/Net worth/Float table (Feb-May 2025) | Partially extracted |
| 36 | Portrait | Hydropower EPS/Net worth/Float table (Oct-Dec 2024) | Partially extracted |
| 37 | Portrait | Hydropower EPS/Net worth/Float table (Feb-May 2025) | Partially extracted |
| 38 | Portrait | "Micro Check" table (NPL check, EPS, Networth, Float) | Partially extracted |
| 39 | Portrait | "Finance" table (Stocks, EPS, Networth, Float) | Partially extracted |
| 40 | Portrait | "Banking" table (Price, Stock, NPL check, EPS, Networth, Float) | Partially extracted |
| 41 | Portrait | "Dev Banks" table (Price, Stocks, EPS, Networth, Float) | Partially extracted |
| 42 | Portrait | "Life Insurance" table (Price, Stocks, EPS, Networth, Float) | Partially extracted |
| 43 | Portrait | "Non-Life Insurance" table (Price, Stocks, EPS, Networth, Float) | Partially extracted |
| 44 | Portrait | "Hotels" table (Price, Stocks, EPS, Networth, Float) | Partially extracted |
| 45 | Portrait | "Investment" table (Price, Stocks, EPS, Networth, Float) | Partially extracted |
| 46 | Portrait | "Manufacturing" table (Price, Stocks, EPS, Networth, Float) | Partially extracted |
| 47 | Portrait | "Others" table (Price, Stocks, EPS, Networth, Float) | Partially extracted |
| 48 | Portrait | "Tradings" table (Price, Stocks, EPS, Networth, Float) | Partially extracted |
| 49 | Portrait | "Hydropower" table (Price, Stocks, EPS, Networth, Float) | Partially extracted |
| 50 | Portrait | "Hydropower" table (Price, Stocks, EPS, Net worth, Float, Holdings) | Partially extracted |
| 51 | Portrait | "Cheapest Stocks" table (Stocks, EPS, Net worth, Float, Holdings) | Partially extracted |
| 52 | Portrait | "New IPOs" table (Stocks, EPS, NPL, P/E) | Partially extracted |

## Data categories discovered

| Category | Pages | Description |
| --- | --- | --- |
| Fundamentals tables | 1-6, 9-16, 34-52 | Sector-grouped tables with EPS, Net worth, Float, Price, P/E, DPS, Holdings, Accumulation |
| Price tracking | 6-8 | Monthly/Weekly/Daily/15min price columns per stock |
| Accumulation rankings | 12-15 | "Most Accumulation" by sector with 1yr/6m/1m columns |
| Trading records | 18-25, 27-29 | Buy/Sell columns with dates, quantities, prices, settlement amounts |
| Settlement records | 19-21, 23, 26, 28, 30, 32-33 | Settlement reconciliations with buy/sell totals, net payable/receivable |
| Technical notes | 17 | MACD and Bollinger Band checklists |
| Stock lists | 3 | Plain symbol lists |
| New IPOs | 52 | IPO tracking with EPS, NPL, P/E |

## Abbreviations and conventions

| Term | Likely meaning | Confidence |
| --- | --- | --- |
| EPS | Earnings Per Share | HIGH |
| Net worth | Net worth per share (NPR) | MEDIUM — could be total net worth |
| Float | Public float (shares or crore) | MEDIUM — unit unclear (cr vs lac) |
| DPS | Dividend Per Share | HIGH |
| P/E | Price-to-Earnings ratio | HIGH |
| NPL | Non-Performing Loans (for banks) | HIGH |
| Holdings | Broker code with quantity in parentheses, e.g. `62(66)` | MEDIAN |
| Numbers in parentheses | Negative values | HIGH |
| `cr` | Crore (10 million) | HIGH |
| `lac` / `L` | Lakh (100 thousand) | HIGH |
| Scrips | Share quantity | MEDIUM |

## Extraction status summary

| Metric | Count |
| --- | --- |
| Total pages | 52 |
| Pages visually inspected | 52 |
| Pages with any structured data extracted | 48 |
| Pages with no extractable data (notes, charts, illegible) | 4 |
| Automated OCR viable | 0 (0%) |
| Manual human transcription needed | All extracted values require review |

## Honest assessment

This document is a **rich personal trading journal** with sector fundamentals, price
tracking, accumulation rankings, and detailed trading/settlement records spanning
2021-2025. The content is valuable for:

1. **Historical fundamentals** — EPS, net worth, float for ~100+ stocks across sectors
2. **Trading records** — buy/sell transactions with dates, quantities, prices, and settlement amounts
3. **Accumulation rankings** — which stocks were being accumulated over time
4. **Price tracking** — historical price levels at monthly/weekly/daily intervals

However, **every extracted value requires manual review** by someone who can read the
handwriting. The AI assistant's visual inspection provides a starting point, not a
verified dataset. The extraction infrastructure (schemas, validation, import pipeline)
is built and ready; the data must be reviewed before it is used for any financial
calculation or import into the portfolio/journal.
