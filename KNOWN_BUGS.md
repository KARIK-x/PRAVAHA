# Known bugs and defects

Status is one of **FIXED** (code changed + regression test), **OPEN** (present,
documented), or **LIMITATION** (inherent, not a code defect).

---

## This session (2026-10-12)

### B-01 — Settlement reconciliation used the wrong sign — **FIXED**

*Where:* `megatool/written_pdf.py`, `validate_settlement_reconciliation`
*Symptom:* the function computed `sell − buy` and compared it signed against
the recorded net. Page 21 of `WRITTENdata.pdf` labels its figure
**"Net Payable = buy − sell"**, so it rejected all four settlements that are in
fact correct:

```
9A: RAISED -> sell 12059.43 - buy 77609.76 = -65550.33, but net recorded as 65550.33
9B: RAISED -> sell 88169.68 - buy 106186.34 = -18016.66, but net recorded as 18016.66
9C: RAISED -> ... 9D: RAISED -> ...
```

*Fix:* reconciles `|buy − sell|` against `|net|`, so either direction
(payable or receivable) is accepted while a genuinely wrong net still raises.
*Tests:* `test_settlement_reconciliation_all_four_page21_settlements`,
`..._accepts_net_payable_convention`,
`..._still_rejects_wrong_net_when_buy_exceeds_sell`.
*Impact if unfixed:* every valid settlement would be flagged, so the
arithmetic self-check would have been unusable.
*Evidence note (2026-10-12):* the 9A figures above were re-read directly from
`raw_pages/page_21.png` and are correct. An earlier revision of this entry
showed `186129.76` / `120579.43` for 9A; both were wrong — see B-02.

---

### B-02 — A fabricated "correction" was applied to settlement 9A — **REVERSED**

*Where:* `docs/WRITTEN_DATA_VALIDATION_REPORT.md`, `KNOWN_BUGS.md`,
`PROJECT_STATUS.md`, `SESSION_HANDOFF.md`, `TASK_QUEUE.md`,
`tests/test_financial_integrity.py`,
`data/written_pdf/benchmark/ground_truth.json`
*What actually happened:* an earlier audit recorded 9A's buy as `177,609.76`
and its sell as `120,579.43`, noticed those did not produce the recorded net
of `65,550.33`, and "corrected" the buy to **`186,129.76`** because that value
happened to balance. That is exactly the forbidden move — re-reading a figure
so an equation closes.

*What the page actually says* (direct visual read of `raw_pages/page_21.png`,
2026-10-12):

| Settlement | Date | Buy | Sell | Net Payable | Paid |
|---|---|---|---|---|---|
| 9A | 11 sep / 1 sep | **77,609.76** | **12,059.43** | 65,550.33 | 65,550.33 on 12th Sep |
| 9B | 16 sep / 16 sep | 106,186.34 | 88,169.68 | 18,016.66 | 18,016.66 on 22nd Sep |
| 9C | 18 sep / 18 sep | 189,763.58 | 157,168.39 | 32,595.19 | 32,595.19 on 24th Sep |
| 9D | 22 sep / 22 sep | 54,157.24 | 45,035.39 | 9,121.85 | 9,121.85 on 25th Sep |

`77,609.76 − 12,059.43 = 65,550.33` — exact to the paisa, as do 9B, 9C and 9D.
**There was never an 8,520 NPR discrepancy on this page.** It was an artefact
of the misread sell figure (`120,579.43` for `120,59.43`/`12,059.43`).

*Consequences:* the `186,129.76` figure is withdrawn everywhere it appeared and
must never be imported. Apple Vision's page-21 numeric recall, measured
against the corrected ground truth, is **100%** (12/12) rather than the 83%
previously reported — the OCR had read 9A correctly all along, and the
benchmark target was wrong, not the engine.
*Impact if left:* a fabricated number would have entered the notebook's
digital record as "arithmetic-verified".

---

### B-03 — `rank_universe` raised a misleading error when nothing was rankable — **FIXED**

*Where:* `megatool/ranking.py`
*Symptom:* setting `as_of` early enough that no symbol met `min_bars` raised
`no factor has both a positive weight and observed data`, surfacing as HTTP 400
— i.e. a normal, reportable outcome looked like a malformed request.
*Fix:* returns an empty result with every symbol in `excluded` and a note
explaining that nothing could be ranked.
*Test:* `test_rank_reports_when_as_of_leaves_nothing_rankable`.

---

### B-04 — Look-ahead guard could be silently skipped by a column name — **FIXED**

*Where:* `megatool/ranking.py`, `_truncate`
*Symptom:* truncation looked for a column literally named `date`, but
`MarketStore.get_bars` returns **`trading_date`**. Any frame loaded from the
store would have bypassed the `as_of` cut without warning.
*Fix:* `_date_column` accepts either name.
*Test:* `test_truncation_works_with_store_column_name`.

---

### B-05 — Symbols with too little history vanished from results — **FIXED**

*Where:* `megatool/ranking.py`
*Symptom:* symbols below `min_bars` were dropped before ranking, so
`universe_size` no longer equalled `ranked + excluded` (observed: universe 4,
ranked 3, excluded 0).
*Fix:* they are returned in `excluded` with a stated reason.
*Test:* `test_universe_accounting_balances`.

---

### B-06 — Unknown-fundamental import path was dead code — **FIXED**

*Where:* `megatool/fundamentals.py`
*Symptom:* `records_from_rows` demanded an explicit unit for an unrecognised
field, then `validate()` rejected that same field outright. The branch was
unreachable.
*Fix:* unrecognised fields are accepted when a unit is stated; known fields
still must carry their declared unit.
*Tests:* `test_unknown_field_allowed_when_unit_given`,
`test_empty_unit_rejected`.

---

## Open

### B-07 — `security_master.sector` is NULL for every symbol — **OPEN**

*Where:* `megatool/ingest.py:148` always writes `"sector": None`; the source
dataset (`Aabishkar2/nepse-data`) carries only OHLCV columns.
*Effect:* sector-relative percentile ranking (report §8.2) is impossible;
`/api/securities` has no sector field; peer comparison is unavailable.
*Possible sources:* ShareSansar company pages expose `sector` in HTML, but
collecting 372 pages would be scraping without established permission.
*Workaround in place:* the ranker declares `sector_percentile` unavailable at
zero weight rather than faking it.

### B-08 — No verified fundamentals source — **OPEN**

ShareSansar serves per-company reports via a CSRF-protected AJAX POST. No
automated source is wired up. The Fundamentals Lab is import-driven and
currently holds **0 records** in the real store.

### B-09 — Official NEPSE API returns HTTP 401 — **OPEN (by policy)**

`https://www.nepalstock.com/api/nots/nepse-data/market-open` →
`401 WARNING: UNAUTHORIZED ACCESS` (verified via the app's own httpx client,
2026-10-12). `megatool probe` re-checks this. Not worked around.

### B-10 — NEPSE index and sector indices unavailable — **OPEN**

The dashboard therefore shows **no index value at all** rather than a
substitute.

### B-11 — Backtest fee rate is a PLACEHOLDER — **OPEN**

`BacktestConfig.fee_rate` is explicitly labelled a placeholder in output and
in `_assumptions()`. The report quotes 0.24–0.36% broker commission + 0.015%
SEBON + Rs 25 DP charge, but these were **not** verified against an
authoritative source this session, so they were not hard-coded.

### B-12 — Web search unavailable in this environment — **OPEN**

Three attempts returned `unknown: "Web search cancelled"` — not an auth error
and not "tool not found" (the tool exists and returns a structured error).
This is an environment limitation; it is why no claim in this project's
documentation rests on a web search.

---

## Found by the evidence-based completion audit (2026-10-12)

### B-13 — `parse_nepse_number` returned `2.0` for `"2 lakh"` — **FIXED**

The unit branch tested `"lac"` (with a **c**) and `r"\dL\b"` (uppercase **L**
only). The word `lakh` contains neither, so a real Nepali amount scaled by
nothing: `"2 lakh"` → `2.0`, a **100,000×** understatement. `"Rs 2.5 lakh"` →
`2.5`. `"2l"` and `"2 L"` failed for the same reason.

Measured before the fix — 6 of 15 spellings wrong:

| input | correct | returned |
|---|---|---|
| `2 lakh` | 200,000 | **2.0** |
| `Rs 2.5 lakh` | 250,000 | **2.5** |
| `2 lac` | 200,000 | 200,000 ✓ |
| `2L` | 200,000 | 200,000 ✓ |
| `15L` | 1,500,000 | 1,500,000 ✓ |
| `2.2cr` | 22,000,000 | 22,000,000 ✓ |

**Exposure:** none live — the function has no caller outside `tests/`
(verified by grep across the repo). Latent, but it is the parser the OCR
pipeline will use.

**Fix:** match `\b(?:lakh?|lac|l)\b` or a digit followed by `l`. Regression
tests pin 11 spellings plus the crore case and the no-unit case.

### B-14 — A ratio could be computed from the wrong field or unit — **FIXED**

`KNOWN_FIELDS` documents *"Units are stored explicitly so a ratio can refuse
to divide mismatched quantities."* Nothing enforced it. Measured before the
fix:

```
ratio_pe(500.0, revenue_record)  -> 0.1000   presented as a P/E
ratio_pe(500.0, rec(unit="shares")) -> 20.0
ratio_pe(500.0, dps_record)      -> 20.0
```

A plausible-looking number with no meaning, and Python does not enforce the
`eps: FundamentalRecord` annotation.

**Exposure:** none live — no endpoint or CLI computes a ratio. **Fix:**
`_refuse_wrong_field` / `_refuse_wrong_unit` on all three ratios; P/E accepts
only `eps`, P/B only `net_worth_per_share`/`book_value_per_share`, yield only
`dps`, all in `NPR`.

### B-15 — The staleness guard was opt-in — **FIXED**

`price_as_of` defaulted to `None`, and the age check only ran `if
price_as_of is not None`. So:

```
ratio_pe(500.0, eps_from_2015)  ->  20.00     (no complaint)
```

**Exposure:** none live (no caller). **Fix:** `price_as_of` is now a required
keyword argument on `ratio_pe`, `ratio_pb` and `ratio_dividend_yield`; omitting
it is a `TypeError`, not a silent pass-through. Dividend yield gained the
staleness and unknown-period checks it never had.

### B-16 — `docs/WRITTEN_DATA_VALIDATION_REPORT.md` still showed the wrong 9A figure — **CLOSED (2026-10-12)**

Line 30 read `177,609.76`, and the "correction" applied to it (`186,129.76`)
was itself fabricated — see B-02. Closed by re-reading page 21 directly from
`raw_pages/page_21.png`: the figures are **77,609.76 / 12,059.43 / 65,550.33**
and all four settlements on the page reconcile exactly. The report now carries
the verified table plus the correction history.

### B-17 — Bars marked `invalid` are not filtered from the read path — **OPEN**

`get_bars` has no `validation_status` predicate, so flagged rows flow into
every indicator, scan, backtest and forecast. The real store holds:

| status | rows |
|---|---|
| `valid` | 500,801 |
| `suspect` | 13,093 |
| `invalid` | 124 |

including **115 `high_low_inverted`** rows and 555 rows whose close is outside
`[low, high]`. The status is stored per row and surfaced by the API, but it is
informational only. Pinned by `test_invalid_bars_are_still_returned_by_the_read_path`
so the limitation cannot be forgotten.

### B-18 — Re-importing the PDF under a different filename duplicates records — **OPEN**

`import_records` dedupes on `(source_file, content_hash)`. Re-importing the
same path is idempotent (verified: `0 inserted, 2 updated`), but a **renamed
copy of identical bytes** creates a second `import_id`, and `query_records`
filters by no import — so `SELECT *` returns both copies (verified: 4 rows
across 2 imports).

---

## Findings in the source document (not code defects)

These are things the notebook itself does. They are recorded, never repaired:
the transcription keeps what is written and reports the disagreement.

### S-01 — Page 19, 8C: sell components exceed the written total by 1.00

`154,824.76 + 71,535.52 = 226,360.28`, but the page's sell total reads
**226,359.28**. Both numbers are what the page says, so both are stored —
`sell_total` stays `226_359.28` and the 1.00 gap sits in
`source_discrepancies`. **No figure was changed to close it.** The written net
(58,211.45) equals `buy − written sell`, so the page is internally consistent
with its own total.

### S-02 — Page 19, 8C: received amount is 8.03 below the net receivable

Net receivable **58,211.45**; the page records receipt of **58,203.42**.
Recorded as a discrepancy with no cause assigned — a fee, a rounding, a
partial receipt and a misreading all fit the evidence equally, so none of them
is asserted.

### S-03 — Page 19, 8E: the author corrected the page themselves

The notebook strikes `148,503.38` and writes **148,478.38** for the sell
total, and strikes `73,872.10` for a component where **23,847.10** now appears.
The earlier readings are kept in `superseded_readings` with both values, so the
author's own correction history survives alongside ours. `148,503.38` is
superseded, not wrong to have been read.

### S-04 — The working copy's Index misdescribes page 20

Index says *"Settlement calculations and payable amounts"*. The page is a
transaction detail table: `symbol → quantity × price` per date, with the day's
total in a cloud and a circled settlement label. The observed description is
kept in `content_type_observed`; the Index text stays in `content_type`. Pages
22, 24, 27, 29 and 31 carry the same Index label and have **not** been checked.

### S-05 — Page 21 has content outside the settlement blocks

An edge column of boxed figures (27, 28, 29, 15, 11.5, 16) sits beside the four
blocks and is **not transcribed**. This is why `page_fully_transcribed` is false
for page 21 despite all four settlements being read and verified.

---

## Limitations (inherent, not defects)

### L-01 — Apple Vision drops digits on large figures

Benchmark evidence (5 pages with hand-built ground truth), with the rotation
pass and the corrected page-21 targets:

| page | numbers exact | numbers numeric | symbols |
|---|---|---|---|
| 18 (transactions) | 7/19 (37%) | 16/19 (84%) | 9/11 |
| 21 (settlements) | 9/12 (75%) | 12/12 (100%) | 0/0 |
| **all 5** | **69/92 (75.0%)** | **87/92 (94.6%)** | **33/46 (71.7%)** |

Page 18 remains the weakest because dense transaction lines lose characters in
totals such as `140,966.07`; page 21 is now perfect after the ground truth was
corrected (B-02).

**Consequence:** extracted values must never enter accounting without review.
Arithmetic self-checks (`buy − sell = net`, totals vs. line items) are the
practical mitigation, and they are what flagged page 19's sell column.

---

### L-07 — Arithmetic can falsify a reading but cannot supply one

A balancing equation is *evidence about* a transcription, never a licence to
change it. B-02 is the worked example: with a misread sell figure, the only
"correction" that balanced was a fabricated buy figure, and adopting it would
have put an invented number into the ledger labelled as verified.

**Consequence:** `megatool/written_transcribe.py` never rewrites a figure to
close an equation. A block that fails a check is marked `discrepancy` and
keeps its raw lines; a figure that cannot be parsed is returned as `None`
rather than guessed; and a correction can only be recorded through
`append_correction`, which requires a stated reason and preserves the original
reading and every earlier entry.

### L-02 — Local vision-language models not tested

Ollama is installed at **0.5.7**; `qwen2.5vl:3b`, `qwen2.5vl:1b`, `gemma3:4b`
and `llama3.2-vision:11b` all refuse with
`412: The model you are attempting to pull requires a newer version of Ollama`
(latest release is v0.40.3). Updating Ollama is a machine change and was left
to the owner.

### L-03 — Third-party dataset has no LICENSE

`github.com/Aabishkar2/nepse-data` publishes no license. Data stays git-ignored
with per-row attribution and is used for private research only.

### L-04 — Automated OCR cannot read this document

42 of 52 pages produced empty output; the 24 non-empty files are gibberish.
Not fixable by preprocessing — handwriting has no character boundaries for a
glyph-segmentation engine.

### L-05 — Median substitution is not ranking-neutral

A symbol missing a factor gets the cross-sectional median, and that synthetic
value is then included in the distribution every percentile is computed from.
Measured on the real 372-symbol universe: 8 symbols lack `momentum_6m`
(70–119 bars, below the >120 that `return_120d` needs). Removing them changes
**361 of 361 scores** and **284 of 361 ranks**, largest score shift 0.61
points, top-10 membership unchanged (one adjacent pair swaps).

On a small universe the effect is much larger — the audit's 5-symbol fixture
moves a complete symbol's score by 4.875 points, bounded by that one factor's
weight (0.25 × 100).

**Disclosure is present** (`complete=False`, note `median-substituted for: …`),
and the behaviour is pinned by `test_substitution_moves_other_symbols_scores`.
**Not fixed:** computing percentiles only over observed values would be the
methodologically cleaner choice, but it changes every score, so it is the
owner's call.

### L-06 — Inverted factors never reach the 100th percentile

Directionality is applied as `100 - p` rather than a true reverse rank
`(n + 1 - r) / n × 100`. Every inverted percentile is therefore understated by
exactly `100/n`. Order on that factor is unaffected (the shift is a constant
for all symbols), so **ranks do not change**, but the factor's contribution is
depressed by `weight × 100/n` for everyone:

* n = 4 (test fixture): best volatility scores **75**, not 100 — worth 3.75
  score points against a true reverse rank.
* n = 369 (real store): 0.27 percentile points → **0.04** score points.

Pinned by `test_inverted_factor_never_reaches_100_for_the_best_symbol`.
