# NF-016 — Natural-Language Query Over Local Data (read-only)

**Module:** `megatool/nlquery.py`
**API:** `/api/query/{run,history}`
**UI:** KIMI → **Ask the Data** tab
**Table:** `nl_query_runs` (schema v10)
**Tests:** `tests/test_nlquery.py` (27)
**Date:** 2026-10-19

---

## 1. Purpose and constraints

Let a user ask a plain-English question about the project's **own** stored data, and
answer it without ever handing free-form SQL to the database. Hard requirements, all
enforced in code:

* **Read-only.** Only `SELECT` against an allowlist; no writes of any kind.
* **Allowlisted.** Only these tables (and only their real columns) are reachable:
  `securities`, `fundamentals`, `collector_quotes`, `price_bars`, `index_series`.
* **Parameterised.** Every value is a bound parameter — never string-concatenated.
* **Bounded.** Every query carries a LIMIT and a scan guard; an over-large requested
  limit is rejected.
* **No unrestricted surface.** No SQL, shell, filesystem or secrets access; no writes.
* **Refuse over invent.** An unsupported question is rejected with the list of supported
  shapes — it never guesses at data.
* **Rule-based.** No LLM is involved in parsing; the grammar is explicit.

---

## 2. Supported question shapes

```
how many securities
list securities [in <sector>]
price of <SYMBOL>
close of <SYMBOL> on <YYYY-MM-DD>
average close of <SYMBOL> over last <N> days
highest/lowest close of <SYMBOL> in <YYYY>
how many bars for <SYMBOL>
date range for <SYMBOL>
top <N> symbols by volume/turnover/close
<field> of <SYMBOL>
<field> history of <SYMBOL>
close of <INDEX> index
```

Field words are excluded from symbol detection, so `eps of NABIL` parses the field, not
a symbol named "eps".

---

## 3. Verification battery (live, dev :10000)

| Question | Status | Rows |
|---|---|---|
| how many securities | ok | 1 |
| price of NABIL | ok | 1 |
| close of NABIL on 2025-06-16 | ok | 1 |
| highest close of NABIL in 2025 | ok | 1 |
| average close of NABIL over last 30 days | ok | 1 |
| how many bars for NABIL | ok | 1 |
| top 5 symbols by volume | ok | 5 |
| eps of NABIL | ok | 1 |
| eps history of NABIL | ok | 19 |
| close of NEPSE index | ok | 5 |
| **drop table price_bars** | **rejected** | — |
| **select * from users** | **rejected** | — |
| **list everything from information_schema.tables** | **rejected** | — |
| **what is the meaning of life** | **rejected** | — |

Refusal reason (recorded verbatim in the audit table):

> unsupported question. Supported shapes: how many securities; list securities
> [in <sector>]; price of <SYMBOL>; close of <SYMBOL> on <YYYY-MM-DD>; average close of
> <SYMBOL> over last <N> days; highest/lowest close of <SYMBOL> in <YYYY>; how many bars
> for <SYMBOL>; date range for <SYMBOL>; top <N> symbols by volume/turnover/close;
> <field> of <SYMBOL>; <field> history of <SYMBOL>; close of <INDEX> index

---

## 4. Security tests

| Attack / edge | Expected | Covered by |
|---|---|---|
| SQL metacharacters (`;`, `--`, `/*`, quotes, backslash) anywhere in the question | refused outright | `tests/test_nlquery.py` |
| Unauthorised table (`users`, `information_schema.tables`) | rejected | ✓ |
| Unauthorised column | rejected | ✓ |
| Excess requested limit | rejected | ✓ |
| Invalid symbol | rejected | ✓ |
| Invalid date | rejected | ✓ |
| Empty result set | reported as `missing` (not as zero/absent) | ✓ |
| Allowlist surface | asserted exhaustively | ✓ |

An **empty result is never rendered as zero**: it is a `missing` state that says what is
missing.

---

## 5. Auditability

Every run — including refusals — is written to `nl_query_runs` with the question, status,
reason, row count and duration. 19 rows observed during verification, the 4 refusals
among them carrying their reason. `GET /api/query/history` lists them.

The stored plan is the *safe* form (table + chosen columns + bound params + limit), which
is what makes a past query re-readable without re-parsing.

---

## 6. Verification summary

* **Unit:** `tests/test_nlquery.py` — 27 tests: supported intents, empty-result `missing`,
  injection refusal, unauthorised table/column, excess limit, invalid symbol/date,
  allowlist assertion, provenance, history incl. rejections. **PASS.**
* **API:** `tests/test_phase_api.py`. **PASS.**
* **Browser (dev :10000):** Ask the Data tab → a valid query renders a Plan + result rows;
  an injection attempt shows "Refused: …". **PASS.**

---

## 7. Limitations

* The vocabulary is deliberately narrow: it answers the shapes above and refuses
  everything else. It is not a general SQL assistant, by design.
* It queries stored data only. A question about the live market cannot be answered from
  stored data and will be refused rather than improvised.
* Numeric results are normalised to JSON-safe values; very large result sets are bounded
  by the limit rather than truncated silently.
