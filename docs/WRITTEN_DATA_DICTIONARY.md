# Written Data.pdf — Data Dictionary

Field definitions for the 52-page handwritten journal. Every field carries
the page(s) where it appears, its inferred unit, and a confidence level.

**Nothing here is verified market data.** These are the author's personal
records and observations. Confidence describes how clearly the AI could read
the handwriting, not whether the value is correct.

## Core field definitions

| Field | Pages | Unit | Definition | Confidence |
| --- | --- | --- | --- | --- |
| `price` | 2, 4-6, 9-11, 16, 34-52 | NPR | Share price recorded by the author at the page's date | MEDIUM — handwritten digits |
| `eps` | 1-2, 4-5, 9-11, 16, 34-52 | NPR | Earnings per share for the reporting period visible on the page | MEDIUM |
| `net_worth` | 2, 4-5, 9-11, 16, 34-52 | NPR | Net worth per share (book value per share) | MEDIUM — could be total equity in some rows |
| `float` | 2, 4-5, 9-11, 16, 34-52 | shares, `cr`, or `L` | Public float. Unit varies by row: plain number, `cr` (crore), or `L` (lakh) | LOW — unit is inconsistent across rows |
| `dps` | 2, 4 | NPR | Dividend per share | MEDIUM |
| `p/e` | 9-10, 52 | ratio | Price-to-earnings ratio | MEDIUM |
| `npl` | 38, 40, 52 | ratio or % | Non-performing loans (banking pages only) | MEDIUM |
| `holdings` | 2, 4, 50-51 | broker code + quantity | Entries like `62(66)`: a broker/dealer code with a quantity in parentheses | LOW — broker codes are not decoded |
| `accumulation` | 7-8, 11-15 | quantity | Shares accumulated over a period (1yr / 6m / 1m columns) | LOW |
| `price_monthly` / `price_weekly` / `price_daily` / `price_15min` | 6-8 | NPR | Price observed at that timeframe | MEDIUM |

## Trading-record fields

| Field | Pages | Unit | Definition | Confidence |
| --- | --- | --- | --- | --- |
| `settlement_id` | 19-21, 23, 26, 28, 30, 32-33 | text | Settlement batch label (e.g. `8C`, `9A`, `12D`) | HIGH — printed-looking |
| `buy_date` / `sell_date` | 18-33 | date | Transaction date within the settlement period | MEDIUM |
| `buy_amount` / `sell_amount` | 18-33 | NPR | Total value of buys/sells on that date | MEDIUM |
| `net_payable` / `net_receivable` | 19-21, 23, 26, 28, 30, 32-33 | NPR | `sell_total − buy_total`; the author's own reconciliation | HIGH — arithmetic verified |
| `quantity` | 18-33 | shares | Shares traded | MEDIUM |
| `rate` | 18-33 | NPR | Price per share on the trade | MEDIUM |

## Conventions

| Convention | Meaning | Evidence |
| --- | --- | --- |
| `(value)` in parentheses | Negative number | Appears on EPS columns where a loss is expected; e.g. `(6.13)` next to a bank with negative earnings |
| `cr` | Crore = 10,000,000 | `2.2cr` appears as a float value |
| `L` / `lac` | Lakh = 100,000 | `17L` appears as a float value |
| `NPL check` | A column verifying the non-performing-loan figure against another source | Pages 38, 40 headers |

## Sector sections found

| Sector | Pages |
| --- | --- |
| Hydropower | 1, 4, 13, 16, 35-37, 49-50 |
| Commercial Banking | 2, 10-11, 40 |
| Development Bank | 4, 41 |
| Microfinance | 4, 9, 12, 38 |
| Finance | 12, 39 |
| Life Insurance | 13, 42 |
| Non-Life Insurance | 13-14, 43 |
| Hotels | 14, 44 |
| Investment | 15, 45 |
| Manufacturing | 5, 14, 46 |
| Others | 14, 47 |
| Tradings | 15, 48 |

## Unresolved terms

| Term | Where | Status |
| --- | --- | --- |
| "network flow" | mentioned in the project brief | **NOT FOUND** in any of the 52 pages. The brief listed it as a possibility; the document does not contain it. |
| Broker codes in `holdings` | 2, 4, 50-51 | **UNDECODED** — `62`, `74`, `50` etc. are not mapped to broker names without an external broker-code table. |
| `Float` unit inconsistency | 2, 4-5, 9-11 | Some rows carry `cr`, some `L`, some a bare number. The bare numbers may be shares, lakhs, or crores — **unresolved**. |

## Record types in the database

| `record_type` | Meaning |
| --- | --- |
| `fundamental` | A fundamentals-table cell (eps, net_worth, float, price, p/e, dps, npl) |
| `price` | A price-tracking cell (monthly/weekly/daily/15min) |
| `trade` | An individual buy or sell from a trading-record page |
| `settlement` | A settlement reconciliation row |
| `accumulation` | An accumulation-ranking entry |
| `note` | A technical-analysis checklist or other free text |
| `other` | Anything that does not fit the above |
