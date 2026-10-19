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

### B-17 — Bars marked `invalid` are not filtered from the read path — **FIXED (2026-10-12)**

**Was:** `get_bars` had no `validation_status` predicate, so flagged rows flowed
into every indicator, scan, backtest and forecast.

**Fix:** `get_bars`, `latest_bars` and `all_closes` now exclude
`validation_status = 'invalid'` by default (`_NOT_INVALID` in `market_store.py`).
Each accepts `include_invalid=True`, and `GET /api/bars/{symbol}` exposes it as
`include_flagged` so flagged rows stay diagnosable rather than vanishing.

The predicate uses `COALESCE(validation_status,'valid') <> 'invalid'` because
`NULL <> 'invalid'` is `NULL`, not true — a stray `NULL` would silently drop an
entire symbol and read as "no data".

**Why `invalid` and not `suspect`:** `invalid` is the `hard` severity in
`quality.py` — physically impossible rows (`high < low`, negative or zero price,
missing OHLC). `suspect` is `review` severity — uncertain, not impossible.
Dropping ~2.5% of history because a volume spike looked odd would smooth away
the very events being researched, so `suspect` still flows through.

**Measured impact on the real store** (514,018 rows; `valid` 500,801,
`suspect` 13,093, `invalid` 124 — of which 115 `high_low_inverted` and 9
`zero_price`):

| check | result |
|---|---|
| symbols losing their latest (dashboard/portfolio) price | **0** |
| symbols removed entirely | **0** |
| symbols containing invalid rows | 45 |
| full-history ATR changed | **45 / 45** (CMB −15.09%, SMATA −1.49%, BBC −1.20%) |
| all-time lowest low corrected | **8 / 45** — `0.0` → real value |
| recent (14-bar) windows affected | 0 — every invalid row is historical |

The lowest-low corrections are the clearest harm removed: CMB `0.0 → 22.0`,
SMATA `0.0 → 411.0`, STC `0.0 → 200.0`, NICL `0.0 → 190.0`, RLFL `0.0 → 106.0`,
GMFIL `0.0 → 110.0`, PFL `0.0 → 91.0`, MPFL `0.0 → 53.0`. Support/resistance and
distance-from-low metrics on those symbols were measuring the corruption.

**Pinned by** `test_invalid_bars_are_filtered_from_the_read_path`,
`test_a_zero_price_row_cannot_set_a_symbols_all_time_low`,
`test_snapshot_and_cross_sectional_reads_also_exclude_invalid`.

### B-18 — Re-importing the PDF under a different filename duplicates records — **FIXED**

`import_records` deduped on `(source_file, content_hash)`. Re-importing the
same path was idempotent (verified: `0 inserted, 2 updated`), but a **renamed
copy of identical bytes** created a second `import_id`, and `query_records`
filtered by no import — so `SELECT *` returned both copies (verified: 4 rows
across 2 imports).

**Fixed** by deduplicating on `content_hash` alone: identical sha256 bytes *are*
the same document, so a renamed copy now reuses the original `import_id`
instead of shadowing it. A genuinely different file (different bytes → different
hash) still gets its own import. Verified by two new tests: a renamed copy of
identical bytes reuses the import (`0 inserted, 4 updated`, query returns each
record once), and two different documents keep separate imports.

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

### S-06 — Page 28, 12C: RESOLVED by a second reading, original kept

Originally read `77,793.55 − 68,832.46 = 8,961.09` against a written net of
**8,963.09**. Arithmetic proved one of the three readings was wrong but could
not say which, so the gap was recorded and nothing was changed.

Resolved 2026-10-12. The NotebookLM digitization of the same page
(`digitized_trading_ledger_and_notes.md`, December ledger: *"12 Dec: Buy ENL
(60 x 1291.33) = NPR 77,795.55"*) reads **77,795.55**, and
`77,795.55 − 68,832.46 = 8,963.09` — the net read by eye on that page. Two of
the three by-eye figures side with the second reading against the by-eye buy.

`buy_total` is now `77,795.55`, `net_matches_written_totals` is `True`, and
`verification_status` is **`corrected_verified`**, not `verified`. The original
`77,793.55` is preserved in `superseded_readings` with the reason; it is never
deleted. **No cause is assigned** to the underlying qty/price oddity, and the
red Paid cloud remains `None`.

The correction rests on a second independent reading of the page, corroborated
by arithmetic — not on arithmetic alone. Arithmetic still cannot say what a
number says; it can only tell you when two readings disagree.

---

### S-07 — Page 30, 12D: the 0.01 sits in the written total, not a component

The buy components read by eye sum to **283,457.43**; the page writes
**283,457.42**. Originally this could have been a misread component.

The reference file's four December day totals for those exact dates
(98,889.26 · 95,841.88 · 75,943.63 · 12,782.66) match every component read by
eye — and they too sum to .43. With all four independently confirmed, the
discrepancy is localised to the **written total**.

Still not repaired. `buy_total` remains `283,457.42` as written, the gap stays
in `source_discrepancies`, and both readings are reported side by side in
`reference_component_cross_check.csv`. The total is what the notebook says;
that does not become `.43` because `.43` balances.

---

### S-08 — The reference file's quantity × price does not equal its own totals

`digitized_trading_ledger_and_notes.md` states line totals that its own
`qty × price` does not reproduce: `60 × 1291.33 = 77,479.80` against a stated
`77,795.55`; `10 × 1257.0 = 12,570.00` against a stated `12,497.86`;
`90 × 1142 + 100 × 234.27 = 126,207.00` against a stated `131,261.64`.

**No cause is assigned** — a fee or charge structure would explain a consistent
upward drift, but transaction-cost rates are an open blocker (T-12, B-12) and
this document is not evidence for them.

Practical consequence: only the file's **stated totals** are treated as
evidence, and only for cross-checking. Its `qty`/`price` columns are never used
to derive, fill or correct a figure anywhere in this codebase.

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

---

## Session 19 — chart workspace, Kronos, replay, autosave (fixed)

**B-74 — the OHLCV strip opened empty on a fresh load.** `bindOhlcvLegend(chart)` was called before `state.chartBars` was assigned, so the fallback "last bar" render read an empty/previous array and the strip stayed hidden until the first crosshair move. Fix: bind after `state.chartBars = bars`, so the strip opens on the last bar. Also added the timeframe label (`Daily/Weekly/Monthly`) and a per-bar change guard so a moving pointer does not rebuild the strip dozens of times per second.

**B-75 — the drawing-rail popover described tools inside their name.** `RAIL_GROUPS` jammed the description into `name` ("Ray — extends right through anchor 2") and the popover rendered a single line. Fix: split into `name` + `d`, render a two-line left-aligned item (name + description), widen to 332 px, add open animation (skipped under `prefers-reduced-motion`), thin scrollbar, head count.

**B-76 — the per-drawing "Visible" checkbox did nothing.** `renderDrawings()` and `anchorHitAt()`/`drawingBodyHit()` never read `d.hidden`, so hiding an individual drawing left it on screen and still grabbable. Fix: skip hidden drawings in all three places. A master "Hide drawings" switch (`state.drawVisible`) was already wired to the drawer checkbox; a matching toolbar button was added to the Draw popover (§6).

**B-77 — forecast candles were amber-only.** `drawForecastOverlay` painted every forecast candle `#f7b500`/`#b47800`, so a predicted candle never read as bullish/bearish. Fix: bodies use the app's native `#26a69a`/`#ef5350` with amber wicks/borders, plus a fixed `#kf-chip` "PREDICTED" badge on the chart stage.

**B-78 — the main-chart Kronos run had no stale guard.** A forecast finishing after a symbol reload painted on the new chart. Fix: a `state.kronosSeq` token incremented on every reload/run; stale responses are dropped with an explicit status line, and `drawForecastOverlay` also rejects a symbol mismatch. Timeframe is now enforced (daily only) with an honest block message.

**B-79 — fullscreen hid the toolbar.** `requestFullscreen` targeted `#chart-stage`, leaving every chart control unreachable while expanded. Fix: fullscreen targets `#view-charts`, so the toolbar, popovers, drawer and stage all stay usable; chart height recomputed on change; Esc exits.

**B-80 — indicator catalog had no favourites or templates.** Fix: ★ toggle per row persisted in `mt-ind-favs`; a `favs` filter category; save/apply/delete template buttons persisted in `mt-ind-templates` (checkbox sets only, no computation).

**B-81 — no replay or autosave surface.** Fix: `#pop-replay` rebuilds a candles+volume-only chart whose rendered series contains only bars up to the cursor (future bars are simply absent), with Start/Play/Pause/Step/Back/Stop; `#pop-chartset` exposes an explicit autosave switch (`mt-autosave-enabled`) that restores the last symbol/timeframe/range/style only when on.

**B-82 — chart style only offered candles/line.** Fix: `#chart-type` now offers Candles, Bars (OHLC), Line, Area — all native series types, all still drive drawings, the legend and panes.

**B-83 — new drawing tools (Schiff pitchfork, Gann fan).** Schiff pitchfork: handle price halved toward mid(BC) (flattened fork, documented). Gann fan: leg-relative rays at 1/8 fractions of the anchor leg — angles follow the chart's own price scale, NOT absolute degrees (honestly documented as an approximation; NEPSE charts have no uniform bar/price ratio).

**B-84 — custom indicator formula editor (§28).** Sandboxed DSL: recursive-descent parser + AST evaluator, whitelisted functions only (sma, ema, rsi, atr, bb_upper, bb_lower, abs, min, max) and series (close, open, high, low, volume). No eval, no arbitrary code — unknown identifiers rejected at parse time. Test/plot, save per symbol, auto-apply on chart load. `window.alert(1)` correctly rejected ("Error: invalid number").

**B-85 — loadSymbols overwrote typed symbols.** `loadSymbols()` unconditionally set `#symbol-input` to the first security, racing with the user's typed input and `page.fill`. Fixed: only set the default when the input is empty.

**B-86 — research dashboard init crash.** `#totals` element was missing from index.html but `loadMarketOverview()` wrote to it → "Cannot set properties of null". Fixed: added the element + null guard. Verified: overview loads, 4 totals, 11 gainers/losers/active, 0 console errors.

**B-87 — Kronos flat forecast caused by greedy decoding.** `forecast()` and `evaluate()` used `top_k=1` when `sample_count==1` (greedy), causing autoregressive model collapse to the mean after ~3 steps (forecast return std 0.99% vs historical 1.52%, 26 consecutive equal closes at context 256). Fix: changed to `top_k=0` (nucleus sampling, `top_p=0.9`) in both functions. Verified: unique closes 29→48, consec equal 12→0, return std 0.9882%→1.1818%, inference 2.146s→0.749s. All 2331 tests pass. `sample_count>1` (multi-sample averaging) worsens collapse (0.579% std) — do not use. Temperature T=1.0 is appropriate (T=1.2 overshoots to 2.337%).

**B-88 — Kronos frontend did not expose temperature/sample_count controls.** The UI only sent `symbol, variant, context_len, pred_len`. Temperature and sample_count defaulted to T=1.0, sample_count=1. The backend now uses nucleus sampling by default (top_k=0), so the default forecast is no longer flat. UI controls for temperature/sample_count remain a future enhancement.

---

## 2026-10-18 — chart workbench session 26 (fixed)

**B-89 — chart view HTML carried parse-level defects.** The chart work exposed
three structural defects in `web/static/index.html`: a duplicated `chart-meta`
element id, a malformed `</h2>` terminator, and a missing `</nav>` (plus a
stray `</footer>`). Fix: repaired all four sites; the document now parses with
0 errors and element cross-checks run clean. No behaviour changed beyond
restoring valid markup.

**B-90 — trend indicators with non-band output names were routed to panes.**
After the display-hint rewrite, the placement fallback keyed on output names
(`mid|middle|upper|lower|value`), so single-output `ema`/`sma`/`wma`… landed in
their own pane instead of overlaying price. Fix: documented `indPlacement()`
rules — momentum/volume → pane; trend → overlay except ADX/Aroon/linreg-slope/
supertrend; volatility overlays only for pure upper+middle+lower band groups
(Bollinger's ratio outputs keep it in a pane so they cannot wreck the price
scale); price-unit "other" series overlay. Browser-verified matrix: 28 overlay
/ 53 pane across all 81 indicators; `ema` on NABIL now draws 1 overlay series,
0 panes.

**B-91 — a hidden indicator's pane was force-visible after reload.** `addPane`
force-unhides a pane container to measure it before constructing the chart, so
a hidden instance's pane became visible until the next reload. Fix: `drawPane`
re-applies `el.hidden = !visible` after the pane loop. Browser-verified: a
layout with a hidden `rsi(9)` instance renders its pane hidden while the
visible `ema(33)` instance overlays price.

(Caught before shipping, no register entry: `swing_workbench` initially
assigned the `find_breaks(...)` output to the structure field — a list-vs-dict
bug found while reading the swing interfaces; fixed before the first test run.)

---

## 2026-10-18 — chart workbench session 27 (fixed)

All seven entries below were found by reading the drawing/chart code and then
reproduced with real trusted pointer and keyboard events in a live browser
(playwright-cli) on NABIL and the NEPSE index. Statuses are from that run.

**B-92 — the eraser only hit-tested anchors, so drawings appeared not to erase.**
The eraser path in `onChartClick` called `anchorHitAt(x, y, 16)` and nothing
else, so the user had to click a ~2px target at a line's start (and single-anchor
tools — hline/hray/vline/crossline/text/note/flag/price_label — had a target
only at their single anchor). Fix: `drawingBodyHit()` now tests *visible
geometry* with per-tool handling (hline/hray span the pane width from the
anchor, vline spans the pane height, crossline both axes, text-like tools are a
point, every other tool is its anchor-to-anchor segment chain using a shared
`ptSegDist`), and the eraser picks the nearest of body and anchor.
Verified: clicking the middle of a NABIL trendline deletes it (1 → 0), status
"Drawing erased (Undo restores it)."

**B-93 — there was no Delete/Backspace handler for drawings.** The only delete
affordances were the eraser and the drawing-list × button. Fix: a document
keydown handler deletes the selected drawing, or — with nothing selected — the
drawing under the pointer; it is guarded so it never fires while typing
(INPUT/TEXTAREA/SELECT/contenteditable), only inside the chart view, and only
when something is actually targeted; locked drawings refuse and say so.
Verified: Delete removed the selected drawing; Delete and Backspace with
`#symbol-input` focused changed nothing.

**B-94 — dragging a drawing also panned the chart, so lines slid away from the
cursor.** `bindDrawings()` attached `mousedown` in the bubble phase, by which
time lightweight-charts had already begun its own pan for the same gesture: the
drawing moved *and* the chart scrolled. The drag mapping also used
`coordinateToTime()`, which returns null between bars and in the empty space
right of the last bar — so a drag near the edge silently stopped. Fix: the
listener is capture-phase and takes the gesture with
`preventDefault + stopPropagation` when a drawing is hit; the move path uses
`barIndexAtX()` (logical coordinate, rounded and clamped to the data range)
instead of exact time matching.
Verified: a three-step drag moved the anchors (t1 2026-01-27 → 2026-05-19,
p1 503.43 → 549.54) while the visible logical range stayed 0 → 249, unchanged.

**B-95 — a selected drawing had no on-chart feedback, and placement tools
hijacked drags.** `state.drawSelectId` was rendered only as a "selected" pill in
the drawing list. Fix: `refreshSelectionMarkers()` paints numbered anchor
handles for the selected drawing (merged into the single `flushMarkers()` call,
since lightweight-charts allows one marker batch per series), and
`drawPointer` refuses to start a drag while a placement tool or the eraser is
active — a mousedown near an existing anchor now plants the next anchor instead
of moving the old drawing. Escape clears the selection.
Verified: select → 2 selection markers; drag with a placement tool active does
not move the drawing.

**B-96 — merely selecting a drawing pushed a no-op undo entry.**
`drawPointer("down")` called `pushDrawHistory()` on every mousedown, so a click
that only selected a drawing consumed an undo slot and cleared the redo stack.
Fix: the snapshot is taken on the first real move (`state.drawDrag.pushed`), and
the release message distinguishes "selected" from "moved".
Verified: select leaves the undo stack at 1 and the redo stack at 0;
erase → Cmd+Z → Cmd+Shift+Z each behave.

**B-97 — the index chart threw two 404s into the browser console.**
`loadChartInsights()` asked `/api/bars/NEPSE/patterns` and
`/api/bars/NEPSE/statistics`, which serve individual securities.
Fix: the index is answered directly ("n/a for the index" with the reason) and the
patterns panel renders an explanatory empty state instead of requesting.
Verified: console reads **0 errors / 0 warnings** after loading the NEPSE index
and then NABIL.

**B-98 — the index was blanket-restricted to close-only chart types, and
placeholder rows were fabricated into O = H = L = C candles.** Two coupled
defects. (a) `INDEX_ALLOWED_TYPES` disabled candlesticks/bars/hollow/Heikin for
the index even though `index_ohlc_history` holds **2,217 genuine OHLC rows
(2016-11-28 → 2026-10-15, each with turnover)**. (b) The frontend mapping turned
every placeholder row (`open = null`) into `open = high = low = close`, which the
close-only chart types merely hid — exactly the "do not present fabricated
receipts as genuine candles" failure mode, and it also fed the OHLC legend,
magnet snapping and indicator inputs. Fix: the mapping preserves NULL OHLC and
`ohlc_status`; candle/bar/hollow/Heikin render placeholder rows **and** rows the
source flagged `invalid` as whitespace (a gap, never a fabricated or
inconsistent body); Heikin Ashi chains only across genuine rows and resets at a
gap; chart-type availability is now driven by the data
(`genuine_ohlc_count` for the index, `hasBody()` for a security) with the reason
in the option tooltip; the legend shows "no OHLC body (close-only/invalid row)"
and labels the index's owned turnover `T/O`. The API now also returns
`genuine_first_date` / `genuine_last_date` and the meta line quotes them.
Verified: NEPSE renders **750 / 750 genuine** candles over 3 years, meta reads
"index · 2217 OHLC / 3079 close-only · candles from 2016-11-28", 20 in-window
`invalid` rows are gaps, and `tests/test_index_ohlc_history.py` covers the new
fields (15 tests pass).

**B-99 — the viewport was reset by unrelated actions.** `showView()` called
`fitContent()` every time the user navigated to Charts, and `loadChart()` ended
with an unconditional `fitContent()`, so toggling an analysis layer or adding an
indicator discarded the zoom. Fix: navigation no longer fits (autoSize covers a
container-size change; Fit is an explicit button) and `loadChart()` captures the
visible logical range when the symbol + timeframe are unchanged and restores it
after the rebuild.
Verified: zoom to {81.8, 167.2} → toggle Support/Resistance (10 lines drawn of
73 zones) → range byte-identical.

## 2026-10-18 — chart workbench session 28 (fixed)

**B-100 — adding an indicator re-framed the chart.** `addPane()` subscribed the
pane's time scale to the price chart **and** the price chart to the pane, so the
first `setData()` on a new pane (or the pane's own fit) pushed its range back
onto the price chart and threw away the user's zoom — observed `{76.53, 165.67}` →
`{165.67, …}`. The pane↔price sync is now **one-directional** (price → pane,
seeded by `syncPaneToPrice()` after `setData`), and `addToChartFromCatalog()`
captures and restores `getVisibleLogicalRange()` around every add. No
`fitContent` on add. Verified: zoom `{80,200}` → add overlay `ma_cross` → range
byte-identical; add pane `percent_b` → range byte-identical; then pan and the
pane follows (`{120.98,230}`). `docs/evidence/wb21-viewport-preserved.png`.

**B-101 — support/resistance and Fibonacci axis labels overlapped.** When many
levels sat within a few percent, their price-axis labels stacked and became
illegible. Fix: caps `MAX_OVERLAY_LINES=8`, `MAX_OVERLAY_LABELS=4`,
`OVERLAY_LABEL_MIN_GAP=0.012` so nearby levels are thinned and separated.
Verified: `resistance @ 554 [550-556]` and `zone @ 562` no longer collide.

**B-102 — the verification generator could silently promote every indicator to
`reference`.** `scripts/generate_indicator_info.py` scored a test as "numeric
reference" by block text, so a naive helper defined next to the global
`@pytest.mark.parametrize("name", ALL_INDICATORS)` invariant tests caused the
whole registry to be labelled `reference`. Fix: an explicit `INVARIANT_TESTS`
set forces those tests to coverage-only, and `verification_map()` also parses
`SPARSE_PIVOT_INDICATORS` so sparse exclusions are declared, never silent.
Regenerated: **49 reference / 41 invariants / 2 sparse / 0 none**.

**B-103 — the catalogue/audit generator was not reproducible.** It hard-asserted
`sum == 81` and `28 overlay / 53 pane`, so after the registry grew to 92 it would
fail (or, if the asserts were bypassed, emit an 81-row doc). Fix: counts,
placement and the verification split are computed from the live registry; the
placement mirror is still asserted, now against the browser-verified
`{overlay: 33, pane: 59}`; and the catalogue's **Verification** section is emitted
from the same scanner the UI uses, so the doc and the UI can never disagree.

**B-104 — the market ticker showed placeholder text, not stored values.**
`renderTicker()` printed a hard-coded demo string. Fix: a real
`GET /api/market/ribbon` (most recent stored trading day) feeds a horizontally
scrolling strip with category headers, a freshness badge, pause/resume
(`localStorage['mt-ribbon-paused']`) and click-to-load; categories with no honest
source are returned in `unavailable` with a stated reason. 8 API tests added.

**B-105 — the Elliott Wave controls did nothing visible.** The buttons toggled
state but drew nothing. Fix: `runElliottAndDraw()` claims a candidate
(`CANDIDATE_ONLY`, stating pivot count and confidence) and draws the 5 wave
labels + connecting line, with a status line and an erase action; the viewport is
unchanged and manual labels survive `eraseElliottAnnotations()`. Never fabricates
wave labels.

**B-106 — objects on the chart could not be enumerated or removed once drawn.**
Markers/lines from patterns, candles, S/R, pivots, Elliott and harmonics had no
single owner view. Fix: a unified `Objects` manager (`#obj-pane`, draggable and
resizable) lists every visible object with its owner and a full plain-language
description, plus Hide/Remove; marker provenance is stored in `state.markerMeta`
(keyed `time|position|shape|text`) so LWC renderer payloads are untouched.

### Session-28 defects and gaps still open (not fixed)

* **No persistent right composition rail.** The reference NEPSE Alpha chart page
  (#94, #99) keeps an indicator/analysis/composition panel docked at the right;
  here those live in drawers and popovers. Reachable, just not a docked rail.
* **No chart-scanner thumbnail grid.** The pattern *detector* computes
  double top/bottom, H&S etc. per symbol; the reference (#50, #51) shows a tiled
  grid of detected-pattern thumbnails, which is not built.
* **No canvas context menu** on a drawing (edit is via the drawing list / a
  prompt), and no multi-chart grid or pane drag-out (unchanged from session 27).
* **Ribbon symbol names**: `security_master` is empty in the dev store, so the
  ribbon shows tickers without company names — the API is correct, the name
  source is absent (data-dependency, not a fabricated value).
* **Ribbon freshness is daily only.** NEPSE has no intraday feed here, so the
  badge reads "NEPSE <date> · delayed" rather than a live tick; the `relvol`
  category is honestly `unavailable` (no intraday volume baseline).

### Session-27 defects and gaps still open (not fixed)

* **Pane layout is per-instance, not per-workspace.** Height and collapsed state
  persist on the indicator instance; pane **order** cannot be changed and panes
  cannot be dragged into a separate window. Nothing is faked — there is no
  drag-drop and no "mobile pane" toggle in the UI.
* **Four independent `Escape` listeners** (chat panel, drawing cancel/selection,
  drawers + fullscreen, palette/clear modal). Each has a distinct, idempotent
  effect and they run in a fixed order, but they are not centralised in one
  dispatcher.
* **Palette catalogue entries without an implementation** (Stock Heat Map,
  Alpha Rider, Multi Chart, Foot Print, Smart Money Holding, Trading Simulator,
  Minervini, CAN-SLIM, Draw To Scan, MTF Scan, Trade Monitor, Divergences, the
  three AI-signal entries, Shareholder Watchlist, Chart Share, Chart Calendar,
  Smart Money Holding) are listed **disabled with the reason** rather than
omitted, so the search stays honest and their absence is discoverable.

## 2026-10-18 — chart workbench session 30 (fixed / upgraded)

* **Scanner promotion rule** — `scripts/generate_indicator_info.py` only promoted an
  indicator to `reference` when its covering block was `numeric=True` AND the
  indicator had never been covered by an earlier (invariant) test. The
  `test_no_lookahead_full_series_equals_prefix` block covers every registered
  indicator first, locking them all at `invariants`, so later numeric tests could
  never promote. Fixed: a numeric test now always promotes, even over an earlier
  invariant result. Verification map moved 49/41/2 → **62/28/2**.
* **Aroon warm-up index** — `test_aroon_exact` asserted the first valid bar at
  index 4, but aroon's warm-up is `period` (first valid at index 5). Corrected
  to index 5 (up=100, down=0 on a rising series).
* **Metadata gaps filled** — 5 empty references (`median_price`, `standard_deviation`,
  `typical_price`, `weighted_close`, `zscore`), 11 empty notes, and 36 parameter
  names without a `VARIABLES` description. Regenerated `indicator_info.js`: 92
  entries, 0 empty references/notes/formulas.
* **5 genuinely new advanced-analysis capabilities** added and tested:
  rolling beta (`megatool/stats.py`), time-series volatility percentile
  (`megatool/stats.py`), multi-timeframe confluence table
  (`megatool/ta/multitimeframe.py`), descriptive technical rating
  (`megatool/ta/confluence.py`, new module), S/R strength scoring
  (`megatool/ta/levels.py`). `tests/test_advanced_analysis.py` (16 tests, all pass).

### Session-30 open gaps

* 3 indicators remain at the invariants level (`adx`, `keltner`, `supertrend`) —
  only finite/first-valid checks, no hand-computed reference value.
* The 5 new capabilities are pure functions + tests; they are not yet wired to a
  frontend view or API route (backend-ready, integration pending).
* Quick-layer toggles and per-marker suppression remain session-only (carried
  from session 29).

## 2026-10-18 — chart workbench session 29 (fixed)

**B-107 — the quick-layer overlays and oscillator panes were invisible to the
Objects manager.** The chart-toolbar toggles (`SMA 20/50`, `EMA 20`, `Bollinger`,
`Volume`, `RSI pane`, `MACD pane`, `Swings`, `Close-based pivots`) created real
Lightweight-Charts series and panes, but `addOverlay`/`addPane` returned them to
callers that discarded the handles, so nothing tracked them and
`collectChartObjects()` never listed them — verified missing by the session-28
read-only pass. Fix: `loadChart` now registers one `state.quickObjects` descriptor
per toolbar toggle (`{id,label,type,owner,checkbox,series|seriesList|paneId|markerOwner}`),
and the manager gained a **Quick layers** group wired to `quickObjectHidden`,
`toggleQuickObject` and `removeQuickObject`. Hide flips the real series/pane
visibility; Remove unchecks the toggle, deletes the real primitive
(`removeSeries` / pane `chart.remove()` + element cleared), drops the markers it
owns and refilters `state.markers`. Browser-verified: `quick-rsi` remove → pane
chart gone + element hidden + checkbox off + row gone; `quick-swings` owned 27
markers, Hide hid them, Remove dropped all 27 and the toggle.
`docs/evidence/wb24-objects-quick.png`.

**B-108 — candlestick markers leaked across symbols.** `state.candleMarkers` was
only reset inside `runCandles()`, so a symbol with the candlestick layer **off**
inherited the previous symbol's letters (stale objects in the manager, letters
armed for dates the new symbol never traded). Fix: `destroyCharts()` resets
`state.candleMarkers` (and `state.quickObjects`). Verified: NABIL (layer on) → 122
candle markers; load ADBL (no layers) → 0.

**B-109 — pattern markers were lost on reload.** `applyChartLayers()` re-rendered
the panel with `renderPatternPanel()`, which needs an in-memory scan
(`patternData`); after a reload `patternData` is null, so a persisted `patterns`
layer drew **nothing**. Fix: the layer path now calls `loadPatternPanel(symbol)`
(fetch + draw). Verified: enable `patterns` → 9 markers/9 series → **full page
reload** → 9 markers/9 series reconstructed from the persisted layer flag.

**B-110 — the pattern overlay checkbox leaked across symbols.** `applyChartLayers`
set `#pattern-overlay.checked = true` when the layer was on but never cleared it,
and `loadChartInsights()` always loads the pattern panel, so leaving a symbol with
patterns on and opening one with the layer off still drew the new symbol's
markers. Fix: the checkbox is synced to **this** symbol's flag (`checked =
!!L.patterns`) before `loadChartInsights` runs. Verified: NABIL (patterns on) → 9
markers; switch to ADBL (no layers) → 0 markers, overlay unchecked.

**B-111 — the object manager's duplicate/orphan safety was unmeasured.** Repeated
reloads could in principle accumulate objects. Verified across three full page
reloads: `quick`/`markers`/`candle`/`pat`/`groups` counts byte-identical each run.

### Session-29 defects and gaps still open (not fixed)

* **Quick-layer toggles are not persisted per symbol**, so a **swing-marker**
  quick layer cannot reconstruct after a reload (its own configuration is not
  stored; the toolbar checkboxes reset to their HTML defaults). This is honest
  behaviour, not a fabricated restore: the *persistent* equivalent is the
  right-hand analysis layers (candles / patterns / Elliott / harmonic / S/R /
  Fib / profile), which **do** reconstruct from `mt-chart-layers-<symbol>`
  (verified, B-109). Reported in `REMAINING_BLOCKERS.md` §23.
* **Per-marker suppression is session-only.** Hiding or removing an individual
  detector marker is not persisted; a reload rebuilds the detector's full set from
  its persisted layer flag. Persisting individual suppressions would store
  transient UI state against recomputed output, which requirement 6 forbids, so it
  is deliberately not persisted and labelled as such.
* **The Fib-specific viewport behaviour is now measured** (B-107..B-111 family):
  manual `fib_retracement`/`fib_extension` and automatic `fib` were each measured
  in normal **and** expanded chart mode (see `TEST_RESULTS.md` §29). It is still
  **browser-measured**, not covered by the offline pytest suite.
