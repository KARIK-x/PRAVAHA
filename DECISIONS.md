# Decisions

Every decision that shaped Mega Tool, with the evidence behind it and what was
rejected. Newest first.

---

## 2026-10-15 (session 14) — close the index-consumption gap; never assert a capability the data contradicts

**Decision: implement the missing index consumer rather than leave `relative_strength` declared
unavailable.** The store already holds 17 published index series (7,611 rows); the ranking still said
"Index data is unavailable". Two options existed: (a) leave the factor unimplemented and merely soften
the wording, or (b) make availability data-driven and compute the factor against the official
composite. (b) was chosen because the project's Phase 1 scope explicitly includes "relative-strength
readiness", `megatool/index_series.py` invited a consumer, and a stale capability claim in an API
payload is itself the provenance defect the rules target.

**Rejected:** asserting a substitute benchmark (equal-weighted universe average) when the official
series is missing. The equal-weighted proxy already exists in `regime.py` for a different purpose; for
relative strength it would silently mean something else, so a run without the composite reports the
factor **unavailable with a measured reason**.

**Rejected:** adding a request field to choose an arbitrary benchmark index. Only the official NEPSE
composite is permitted; sector sub-indices are not a market benchmark.

**Rejected:** making the factor on-by-default. It stays weight 0 unless a caller weights it, so default
rankings are byte-identical to before — the same treatment as the sector factor.

**Also decided:** `/api/indices` and `/api/indices/{name}` are the sanctioned read/write boundary for
index data (read-only), and are friend-allowlisted (public market data). An unknown index name returns
404, never an empty-but-successful body that could read as a real series.

---

## 2026-10-15 (session 8) — prove the source pipeline on real data; fix the two defects it exposed

**Decision: run the pipeline against the real downloaded snapshots in isolated
databases before asking for a production import**, using the new
`scripts/validate_source_pipeline.py`. An adapter that works on a fixture proves
only that it parses; running it on 649 real securities records, 6,908 real
report rows and 6,718 real index points found two genuine defects that fixtures
would not have.

**Defect 1 — a zero was being read as "missing" (`megatool/fundamentals.py`).**
`records_from_rows` computed `row.get(c, "") or ""`, so a real `0` became `""`
and a genuine `PE == 0` was reported as a missing required column, refusing the
whole file. Replaced with an explicit `_is_blank()` (only `None` or
blank-string is missing). Measured: **169 real `PE == 0` records** now load.
Missing and zero stay different facts.

**Defect 2 — the YONEPSE financial feed repeats reporting periods
(`megatool/datasources/yonepse.py`).** 6,908 published reports collapse to 4,227
real periods. `megatool.fundamentals` *correctly* refuses two different values
for the same `(symbol, field, period_end, source)`, so the whole file was
unloadable. Added `dedupe_financial_reports()`, which groups on the loader's
**own identity** (not the source's labels) because the source labels the
FY-closing figure twice — `Annual Report` and `Fourth Quarter` both map to the
FY end date. Resolution rule, stated and deterministic: exact duplicates
collapse (1,416); conflicts resolve **complete-period figure (annual) beats
quarterly, then latest filing wins** (661 periods, 238 symbols), and every
collapse is recorded in the row's `notes` so it stays auditable.

**Decision: general notices are not dated.** The YONEPSE general-notice
snapshot carries only `expiresAt`. It was being emitted as `published_at`,
which is an expiry, not a publication date — a fabricated timestamp. Those 28
items are now reported by `notices_without_publication_date()` as unusable
rather than dated. 18 `exchange_messages` records that are genuinely undated
upstream are skipped by the news importer with a stated reason.

**Rejected:** inventing a period_end where the source gives none; letting one
duplicate silently overwrite another; importing the duplicate-bearing file
"as is" on the assumption the loader would tolerate it; and treating a green
fixture test as evidence about real data.

**Evidence:** `tests/test_fundamentals.py` (zero-vs-missing regression),
`tests/test_datasources_yonepse.py` (dedupe rules, dated-record gating), plus
`scripts/validate_source_pipeline.py` → `data/review/source_validation/`.
Focused batteries **279** and **308** passed; 169 zero-PE records load.
Production DB, production app DB and the running server untouched.

---

## 2026-10-15 (session 7) — validation pipeline: symbol-format checks, sector-provenance dry-run, metadata gaps report, T-27 lint closure

**Tightened the metadata validation pipeline before any production import.**
Added `is_valid_nepse_symbol()` in `megatool/market_store.py`; both the sector
loader (`megatool/sectors.py`) and the T-M2 dry-run harness
(`megatool/metadata_dryrun.py`) now reject empty, lowercase, spaced or
punctuated symbols with a reason rather than normalising them into the security
master.

**Extended the dry-run to preview sector provenance.** The harness now reads
optional `sector_source`, `sector_retrieved_at` and `sector_observed_date`
columns, validates ISO timestamps/dates, falls back to the generic `source`
column, flags sectors proposed without a source for manual review, and reports
provenance conflicts against the current store. The JSON output gained a
`_DryRunEncoder` so stored `datetime`/`date` provenance values serialise safely.

**Added a read-only metadata-gap report.** `metadata_gaps()` and
`render_gaps_markdown()` in `megatool/metadata_dryrun.py`, exposed as
`megatool metadata gaps`, report counts and symbol lists for missing sector,
missing instrument_type, missing name, unknown status, and merged symbols
without a successor. It uses the same read-only `securities_meta()` path as the
dry-run and writes JSON/Markdown artifacts under `data/review/gaps`.

**Closed the T-27 candlestick lint gate.** `ruff check` and
`ruff format --check` are clean on `megatool/ta/candles.py` and
`tests/test_candles.py`; 104 tests pass.

**Rejected:** duplicating the dry-run logic in a separate sector-only module
(the existing `metadata_dryrun.py` already covers sectors and was extended),
silently coercing invalid symbols to valid-looking ones (e.g. stripping spaces
or lower-casing), adding a new schema migration (columns already exist), and
inventing a default provenance value when the source is omitted.

**Evidence:** `tests/test_sectors.py` 23 passed (2 new symbol-format tests),
`tests/test_metadata_dryrun.py` 29 passed (4 new tests for symbol format,
sector provenance preview, missing sector_source, malformed timestamps/dates,
plus 2 for metadata gaps), focused regression battery
`test_security_metadata.py` + `test_api.py` + `test_scanner.py` +
`test_ranking.py` + `test_sector_factor.py` + `test_ingest.py` +
`test_market_store_concurrency.py` + `test_fundamentals.py` +
`test_portfolio.py` = **401 passed**; `ruff check` and `ruff format --check`
clean on modified files.

---

## 2026-10-15 (session 6) — sector provenance: store source, retrieval time and observed date with every sector assignment

**Closed the honesty gap in the sector loader before any CSV is approved.** The
`security_master` schema now carries `sector_source`, `sector_retrieved_at` and
`sector_observed_date`. `megatool/sectors.py` records provenance from the CSV
(`source`, `retrieved_at`, `observed_date` columns) or from the required
`source` argument and current UTC time; malformed timestamps/dates are refused.
`MarketStore.set_sectors()` writes the provenance alongside the sector, and
`securities_meta()` exposes it so consumers can see when a classification is
unverified or stale. The migration is idempotent `ADD COLUMN IF NOT EXISTS`;
production data was not touched because the server was not restarted.

**Why this matters:** without stored provenance, an imported sector mapping
would look authoritative even if it came from an unofficial dataset. Now the
source is observable in the same row, supporting the R1/B-1/BLK-2 principle that
every imported claim must be traceable and reversible.

**Rejected:** adding a separate provenance table (more joins, no per-row
benefit), hiding provenance behind a debug-only flag (defeats the purpose),
overwriting existing provenance on a bare re-import (blank fields are preserved
by `COALESCE`), and fabricating sector data to make `sector_percentile` work.

**Evidence:** `tests/test_sectors.py` 21 passed (6 new provenance tests),
`tests/test_security_metadata.py` 38 passed, focused regression battery
`test_metadata_dryrun.py` + `test_api.py` + `test_scanner.py` + `test_ranking.py`
+ `test_sector_factor.py` = 282 passed; `ruff check` and `ruff format --check`
clean on modified files.

---

## 2026-10-15 — app.js repair, frontend integration, B-1 evaluation, fee research

**Applied the owner's B-1 partial ruling exactly as written:** candidate datasets may be evaluated for
local personal research and isolated testing subject to their published terms — and nothing further.
Evaluation ran read-only (terms fetched, coverage/duplicates/conflicts measured, T-M2 dry-run against a
DB **copy**); no production import, no redistribution claim, no access-control bypass. Rejected:
treating the ruling as authorization to write dataset values into the production store (BLK-2 still
gates that) and treating MIT-on-compilation as settled underlying-data rights (recorded, not assumed).

**Fixed `app.js` with the smallest cause that removes the defect.** Removed the two orphaned paste
fragments (the syntax error) and deleted the orphan top-level overlay block, replacing it inside
`loadChart` with real `/api/fibonacci` and `/api/levels` fetches (independent try/catch each, before
`fitContent()`), restored `$("#ind-sma").checked` gating, and rewrote `plotSupportResistance` against
the real zone contract (`lower`/`upper`/`center`/`kinds`, green/red/gold by `kinds`). Rejected:
rewriting the parses-fine-but-ugly sections, adding a build step or framework, or touching unrelated
styling — none of them caused the defect.

**Integrated the new backend endpoints into the existing pages** (no new pages, no duplicated backend
logic): regime + alerts on Overview, derived ratios on Fundamentals, session trend on Floorsheet,
tool-agent on Research, risk check on Portfolio, reflection on Journal — each with loading, error and
empty states, and **AI layers default OFF** (explicit opt-in checkbox). Final browser batch: **11/11
tabs, 13/13 checks, 0 console errors.** Rejected: fabricating success
on empty data — NABIL's missing fundamentals and the absent floorsheet sessions render their honest
unavailable reasons instead.

**Fixed the regime date defect at its root** (`megatool/regime.py` now aligns the level index to
`trading_date` when the input has no `DatetimeIndex`) rather than patching the API response — one fix
covers every future wide-matrix consumer. Existing `DatetimeIndex` fixtures untouched; a
production-shape regression test added (`tests/test_regime.py` **14 passed**, ruff clean).

**Restarted the server only through the documented procedure** (twice: once for the route check, once
to load the regime fix); static edits were verified against the running server without restarts.

**Fixed `renderRatioReport` after the browser smoke test caught `r.map is not a function`** — rows are
arrays of cells and the label column (P/E, P/B, Dividend yield %) was restored. Rejected: dropping the
label column to dodge the crash.

**KEPT OPEN (deliberately):** `plotCandlestickMarkers`/`plotElliottWave` remain console-only dead code
(wiring them is feature work, not a defect fix); B-09 (401 by policy), B-2 (owner browser export),
B-4 (owner mapping ruling), T-15/L1 (ShareSansar licensing) and L4 (news scope) unchanged.

**Closed C3 with official sources (session 2 follow-up):** the SEBON regulation PDFs and the enacted
Finance (Economic) Act 2083 were machine-read (Preeti-font PDFs converted span-wise); commission
slabs, the 0.015% SEBON charge, and the CGT rates (7.5% >365d / 10% ≤365d for natural persons on
listed shares, effective साउन १, २०८३ = FY 2083/84, ITA §95क(2)(क) as amended by धारा 57
उप-बिन्दु 21) are now verified against **enacted text on two official hosts** with the official ITA
baseline. Chosen shape: an **opt-in** named schedule `official-2083-84` in `FEE_SCHEDULES` carrying
all four components with provenance — the default `PLACEHOLDER_FEE_RATE`, `BacktestConfig`, and every
unverified label are untouched, so engine behaviour is byte-identical and existing runs keep their
honest "placeholder" label. Focused `tests/test_cost_model.py` (34 tests) pins the numbers and pins
the default's untouchedness. Register BLK-5 → RESOLVED; B-11 → partially resolved (engine-side
adoption remains, decision C3/D-y). Rejected: defaulting the engine to the new schedule (behaviour
change nobody reviewed), storing CGT without its holding-period conditions, and normalizing the
Act's "natural person" wording to "resident".

**C3/D-y (session 3): adopted the verified schedule into the engine's P&L — opt-in, one engine.**
`BacktestConfig.fee_schedule` selects the component schedule; a single pricing path
(`side_transaction_costs`) serves the backtester, its buy-and-hold benchmark, and the new planning
`entry_cost_estimate()` — no second fee engine. Commission is tiered by each side's charged value
with the NPR 10 minimum, effectiveness-dated **per side** around the 2024-05-14 revision (the
officially superseded table from सङ्ग्रह २०८० applies to earlier sides, with a run warning);
SEBON applies per side; the NPR 25 DP charge applies to sells only; affordability is solved against
the tier table by binary search (tiered costs make it implicit). CGT runs only on an **explicitly
declared** `cgt="natural_person"` category — the engine refuses to classify an investor entity —
with holding-period rates (>365d vs ≤365d) and the era tables (pre-2026-07-15 disposals at the
official pre-amendment ITA rates); a loss is never taxed; the gain is taken net of charges with the
unverified §37 deduction basis flagged. Every closed trade now discloses
gross_pnl / transaction_costs / taxable_gain / capital_gains_tax / net `pnl`, reconciling exactly
(charges rounded to NPR 2dp at the source). Rejected: inferring the investor category, taxing a
loss, retroactively applying post-revision rates to earlier sides, rewriting historical results
(flat-fee runs and their records are untouched — recalculation means re-running with the schedule),
and any change to the default path (1543-test behaviour preserved; the flat default remains a
deliberate, labelled choice). Unverifiable inputs stay refused/disclosed, never guessed.

## 2026-10-14 — Backend repair mission

**Implemented harmonic XABCD detection (§7 / Section 13)** — the last
spec-mandatory analytical engine recorded as `NOT IMPLEMENTED`. Task T-28
stated no owner decision was needed to start, only candidate framing. The ratio
bands (Gartley, Bat, Butterfly, Crab, Cypher) follow the canonical Carney
tables, documented in `megatool/ta/harmonic.py` as literature conventions —
not owner data, not validated predictions. Every match reports measured ratios,
the exact bands matched, an invalidation price level, `certainty="low"` and an
uncertainty note; status distinguishes `CANDIDATE_ONLY` / `NO_MATCH` /
`INSUFFICIENT_EVIDENCE`; degenerate legs are skipped, never approximated.
Rejected: claiming these are "signals", inventing a predictive threshold, or
leaving the register's "NOT IMPLEMENTED" line to be repeated as fact.

**Moved the three time-frame/Elliott routes inside `create_app`.** They had been
module-level after `if __name__ == "__main__"`, hard-coded the DuckDB path and
opened a second writer-mode connection per request. Rejected the alternative of
leaving them module-level and pointing them at `Paths`: only `create_app`'s
`get_store()` closure gives a single shared, conftest-isolatable store, which is
what every other route already uses.

**Changed the weekly/monthly response from a bare pandas list to the daily
envelope.** Evidence the old contract was wrong: `loadChart` reads
`data.bars`/`data.symbol`/`data.count`/… for *every* timeframe, so a raw
`trading_date`-keyed list with no wrapper would throw. This is a deliberate,
evidence-backed contract correction, not a cosmetic change.

**Fixed the Elliott route's `find_swings` call** (the `close` array had been
passed as the positional `left` argument) and **removed the broad `except`**
that turned the resulting crash into a `200 {"status":"FAILED"}`.

**Enforced the confirmed-swings rule in `analyze_elliott_extended`.** The
docstring already promised "CONFIRMED swings only"; the code now filters to
`swing.confirmed`, closing a look-ahead hole (a right-edge pivot is not yet
knowable). Rejected substituting a probability for the qualitative `certainty`
label — Elliott output stays `CANDIDATE_ONLY` with an explicit uncertainty note.

**Wired `deduplicate_symbols` into `run_screen`** (it existed but was never
called). Order-preserving `dict.fromkeys` kept so scans stay reproducible.

**Removed `megatool/ta/elliott_extended.py`** — a byte-identical, never-imported
duplicate of canonical `elliott.py`. **Relocated** the stray, broken root
`test_integration_final.py` to `tests/test_full_workflow.py` and repaired it.

**Rewrote three vacuous regression tests** (Elliott, scanner quality, overlay
alignment) against the real interfaces rather than deleting them.

**Investigated the "1000 synthetic datasets" claim: NOT ESTABLISHED** — no such
harness exists in the repo. Did not fabricate one to justify the claim.

**Restarted only this project's server** (port 8710) via a controlled
kill-and-relaunch to load the new routes; verified all three endpoints against
real NABIL data. **Front end deliberately untouched** (deferred to Phase 2).

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
| Apple Vision (as-is) | 73.9% | 92.4% | 33 / 46 |
| **Apple Vision, best of 4 rotations** (`scripts/vision_ocr_batch.swift`) | **75.0%** | **94.6%** | **33 / 46** |

**Decision:** the report's claim is **refuted for this document**. Apple Vision
is already installed, needs no download, and processes a page in 0.8–1.7 s.
It is adopted as the practical first-pass extractor, run over all 52 pages by
`scripts/run_vision_ocr.py`. Orientation detection is kept because it never
scored worse than the as-is pass on any page and lifted page 18's numeric
recall from 74% to 84%. The figures above are against the *corrected* ground
truth; page 21 previously read 83% only because its target was wrong.

**Still true:** ~95% is not good enough to feed accounting directly. Dense
transaction pages still lose digits, so every extracted value stays `OCR_ONLY`
until a human checks it against the page image. Arithmetic self-checks are what
catch that class of error.

Reproduce: `uv run python scripts/score_benchmark.py`.

### Decision: arithmetic may falsify a reading but may never rewrite one

A balancing equation is evidence *about* a transcription, never a licence to
change it. An earlier audit noticed page 21 settlement 9A did not balance and
adopted the one figure that did — `186,129.76` — which is not written anywhere
on the page. The re-read showed the true figures (`77,609.76 / 12,059.43 /
65,550.33`) already balance exactly; the discrepancy had come from a misread
sell, not from the buy.

**Decision:** extraction never substitutes a value to close an equation. A
failing block is marked `discrepancy` and keeps its raw lines; an unreadable
token returns `None`; a correction can only be recorded through
`append_correction`, which requires a stated reason and preserves the original
reading and every earlier entry. Tracked as `KNOWN_BUGS.md` L-07.

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

## 2026-10-12 — Evidence-based completion audit

### Decision: report findings as measured, and fix only what the evidence supports

The audit's job was to reconcile reported progress against the repository, not
to add features. Three defects were found by measuring rather than reading, and
all three were fixed because each is small, contained, and has **no live caller**
(verified by grep across the repo):

| Defect | Measured before the fix | Fix |
|---|---|---|
| **B-13** lakh parser | 6 of 15 spellings wrong; `"2 lakh"` → `2.0` (**100,000×**) | match `\b(?:lakh?|lac|l)\b` or a digit + `l` |
| **B-14** ratio operands | `ratio_pe(500, revenue_record)` → `0.1000` presented as P/E | `_refuse_wrong_field` / `_refuse_wrong_unit` on all three ratios |
| **B-15** staleness guard | `ratio_pe(500, eps_from_2015)` → `20.00`, no complaint | `price_as_of` made **required**; omission is a `TypeError` |

Not fixed, because each changes observable behaviour and is the owner's call:
**L-05** (median substitution moves 284 of 369 ranks), **L-06** (inverted
factors never reach 100), **B-18** (renamed-PDF re-import duplicates). Each is
documented and pinned by a test so it cannot regress unnoticed.

**B-17** (`invalid` bars reaching indicator maths) was in that list and is now
**fixed** — the mission brief authorises correcting verified defects, and an
arithmetically impossible row (`high < low`, price `0.0`) is a defect rather
than a judgement call. Measured impact on the real store: 45 symbols' ATR
changed, 8 symbols' all-time low corrected from `0.0`, **0 symbols lost their
latest price and 0 symbols disappeared**. `suspect` rows are deliberately still
included — uncertain is not impossible. See KNOWN_BUGS B-17.

### Decision: the ranking's "reproducible by hand" claim is qualified, not repeated

Measured on the real universe: contributions reproduce the score to a **maximum
of 2.0e-4** (median 7.1e-15), because contributions are rounded to 4 decimals
while the score is rounded once from unrounded parts. That is a rounding
artifact, not an error, and it never changes a displayed value — but the honest
statement is "reproduces to 4-decimal rounding", not "sums exactly".

### Decision: arithmetic reconciliation is labelled separately from verification

Settlement 9A's corrected figure (`186,129.76`) is established **by arithmetic
alone**: it is the only value of the three that makes `buy − sell = net`. That
is a self-check of one page against itself. It is *not* independent confirmation
of the digits against the source document, and the validation report now says
so explicitly until T-09 re-reads page 21.

### Decision: data sources are classified by what they delivered, not by HTTP status

* **Verified usable** — `github.com/Aabishkar2/nepse-data`: 514,018 rows,
  372/372 symbols, per-row `source`/`source_url`/`retrieved_at`, and an
  ingestion log with UTC run times, coverage and a `synthetic` flag.
* **Merely reachable** — ShareSansar, nepsedata.com, nrb.org.np return 200.
  A 200 proves nothing about completeness, permission, or usefulness; no field
  of theirs has been ingested.
* **Blocked** — official NEPSE (401, by policy), nepsealpha (403).

Reachability is recorded as reachability.

### Decision: no Ollama change without approval

Inspected read-only: CLI and daemon **0.5.7**, app bundle metadata **0.33.3**,
2 installed models (neither vision-capable), 8 GB RAM. The 412 is Ollama's
own registry gate — it refuses at the manifest **before downloading any
weights** — reproduced without installing anything and with the model list
verified unchanged. Upgrading an installed application is a machine change.

---

## 2026-10-13 — the advanced-analysis engine, started from its foundation

### Decision: build the swing point first, not Fibonacci

The primary reference (104-page project overview PDF) marks Elliott Wave (§4),
Fibonacci (§5), chart patterns (§6), harmonics (§7), price action (§9) and
support/resistance (§14) as mandatory. `grep` across `megatool/` for any of
those terms returned **nothing** — only the 28-indicator library existed.

All six modules need the same primitive: a defensible list of turning points.
Implementing each separately would produce six private, disagreeing definitions
of "a swing" — exactly what §28.2 (shared calculation layer) forbids. So the
swing point ships first, once, and the other five consume it.

### Decision: `confirmed_index` is enforced, not merely documented

A swing high at bar *i* is only a swing high once `right` further bars have
failed to exceed it. Acting on bar *i* would be look-ahead — the same class of
error as the one that made the walk-forward ranking untrustworthy. Therefore:

* every swing carries `confirmed_index`, the first bar at which it was knowable;
* the chart draws **only confirmed** swings — an unconfirmed pivot is excluded
  rather than plotted;
* a break of structure is dated at the confirmation bar, never at the pivot;
* the behaviour is pinned by a **prefix-recomputation test**: running the
  detector on the first N bars must reproduce exactly the swings the full series
  had already confirmed by bar N. History cannot rewrite itself.

### Decision: swings are not registered as indicators

`megatool.ta`'s registry holds per-bar *series* (RSI has a value at every bar).
A swing is a discrete *event* with its own identity, confirmation lag and
invalidation. Forcing it into the series registry would misrepresent it, so it
lives in `ta/swings.py` and is re-exported, with its own metadata.

### Decision: label it DETECTED

Fractal pivots under fixed geometric rules are an *algorithmic detection*
(§32.2), not a validated pattern and not a prediction. The API returns
`interpretation: "detected"` and four caveats; the chart note says
"DETECTED from geometry, not a validated signal". No confidence percentage is
invented (§32.7, the spec's explicit rule against arbitrary confidence).

---

## 2026-10-13 (session 2) — six targets: workspace, Fibonacci, candles, S/R, status

### Decision: one Fibonacci convention, printed with every result

Three surfaces need Fibonacci — module, API, chart, tests — and four drifting
definitions of "the 61.8% level" would be worse than no Fibonacci at all. So a
single signed convention is used everywhere: `range = end − start`,
`retracement = end − range·r`, `extension = end + range·r`. It is returned in
the payload as `formula`, not just documented, so a reader can re-derive every
number without trusting us. Direction comes from the sign of `range`, so
swapping anchors mirrors the result rather than requiring a flag. Equal anchors
**raise** instead of returning a table where every level collapses onto one
price. The 50% row carries `family: "convention"` because it is not a
Fibonacci ratio, and labelling it as one would be a small lie that compounds.

### Decision: analysis states are derived from execution, never looked up

Target 6 asks for honest progress. The tempting implementation is a table of
modules and their "status" — which would be a hardcoded claim about code that
may or may not run on the owner's data. Instead every module runs inside a
timer and a `try`, and its state *is* the observed outcome: `COMPLETED`,
`COMPLETED_WITH_WARNINGS`, `FAILED`, `BLOCKED_BY_MISSING_DATA`. A module that
raises carries its real message (`module unavailable: No module named
'megatool.ta.summary'`, `CandleError: invalid OHLC …`) rather than being
omitted. No completion percentage appears anywhere in the payload or the UI,
because none is measurable — and inventing one is exactly what the spec forbids.

### Decision: OHLC-invalid bars are excluded from detection, never repaired

A read-only sweep found **40,568 of 514,018 bars (7.89%)** whose open or close
sits outside `[low, high]`, including 115 with `high < low`. This is real
market data, so the standing rule applies: *never alter real market records
merely to make something work.* The choice was instead to exclude those bars
from candlestick detection — and to do it over **contiguous valid runs**, not by
compacting the arrays. Compacting would let a three-candle pattern "span" a bar
that never traded, i.e. invent adjacency. The excluded count is reported as
`bars_excluded` and `ohlc_violations`, and the repair decision is escalated as
**R1 in the owner-input register** because all three options change published
history.

### Decision: fix the store read race, and say plainly what the fix is not proven to do

`GET /api/status` returned a real HTTP 500 (`ValueError: zip() argument 2 is
longer than argument 1`). The cause: DuckDB keeps the *latest result on the
connection*, and `execute()` released the lock before callers ran
`.fetchone()`/`.df()` — so a second thread could overwrite the pending result.
That is worse than the visible 500: the same window could hand one request
another symbol's bars. Fixed with `query_one`/`query_rows`/`query_df`, which
hold the lock across execute **and** fetch, plus a **source guard test** that
fails if any future `self.execute(...)` reappears outside a lock block.

**Honest limitation:** a multi-threaded reproduction of the original failure
did *not* trigger in the budget tried (8 threads × 40 iterations × 6 read
paths) — the window is microseconds wide. The evidence for the fix is the
**deterministic** demonstration (a 5-column query's fetch returning another
request's 12-column row, producing the exact production error), not the stress
tests. The stress tests are regression guards, and should not be described as
proof the old code always failed.

### Decision: reuse the Research tab, do not build a second dashboard

The specification asks for a unified research page. The obvious move — a new
nav item, a new symbol box, a new chart — would have produced a *second*
dashboard beside the first, which is what the brief explicitly warns against.
The workspace therefore became a card **inside the existing Research tab**,
prefilling from the chart's symbol rather than competing with it, and the
"Open chart for this symbol" button jumps to the chart the terminal already
has. One navigation tree, one symbol source, one chart.

### Decision: the route-coverage gate is reported as what it actually measures

`scripts/route_inventory.py` reports `50 routes … every route is referenced by
at least one automated test`, exit 0. Reading its source: coverage matches on
the **stem before the first `{`**, so every `/api/bars/{symbol}/…` route shares
the stem `/api/bars/`. A brand-new route therefore shows as covered before a
single test is written — which is exactly what happened with
`/fibonacci` and `/levels`. The script documents this as "the honest floor",
but the number has been quoted in reports as "47/47 test-covered" as though it
meant branch coverage. **It does not.** Real API tests were written for both
routes, and this gap is recorded here so the gate is never over-claimed again.

---

### Decision: aggregate statistics and adjacency-sensitive patterns handle a corrupt bar differently

Two modules hit the same wall: one bad bar in 500 (`close` outside `[low, high]`)
made candlesticks raise `CandleError` and the summary raise `SummaryError`. The
first fix applied to both — run on contiguous valid runs — and it was **wrong
for the summary**, so it was changed.

The distinction is what the data structure requires, not convenience.
Candlestick rules need three bars to be genuinely adjacent; compacting the
array would let a pattern "span" a bar that never traded, inventing history.
Trend/momentum/volatility are *aggregate* statistics where skipping one
observation creates no false pattern — but splitting the window at the bad bar
creates a false **claim about recency**. On real ADBL data one corrupt bar at
2026-04-29 cut the summary to 391 bars ending **2026-04-28**, five months
before the latest bar, while presenting itself as the current state. Dropping
the bar instead gives 499 bars ending 2026-10-09, with the omission printed as
`1 of 500 bar(s) … excluded … 499 bars, 2024-07-29 → 2026-10-09`. RSI moved
46.8 → 65.0 as a result, so the staleness was not cosmetic.

Both behaviours are now asserted: candlesticks by `bars_excluded`, and the
summary by a test that its `last_time` equals the latest stored bar.

### Decision: raise a measured client timeout rather than leave a gate flaky

`smoke_live` exited 1: `POST /api/walk-forward` hit the script's flat 60 s
transport bound. Three runs of the identical payload took **58.4 s, 62.8 s and
80.5 s** — the endpoint straddles the bound, so the gate passed or failed on
load.

Before touching the gate, the cause was measured: instrumenting every locked
read showed **373 store reads = 3.71 s (5.9% of wall), 59.04 s (94.1%)
pure computation**. That attribution rules out this session's own B-19 lock
change, which could only affect the 3.71 s, and `walkforward` imports only
`megatool.ranking`, which uses no `megatool.ta.*`, so the parallel worker's
modules are off this path too.

The fix raises the transport bound **for that route only**, with the numbers
printed at the call site. The expected status, shape checks and skip rules are
unchanged: a transport limit is not an assertion, and a gate that fails half
the time gets ignored rather than trusted. This is the one gate whose exit
code was changed by editing the gate, so it is written up as **B-22** with the
original exit 1 preserved — the failure was diagnosed, not deleted.

### Decision: the red-then-green gate history is published, not rewritten

For most of this sprint `ruff check` was **exit 1** (81 errors, then 75, all in
the parallel worker's files) while pytest was green, and the suite briefly went
**exit 1** with 6 failures while `tests/test_summary.py` was still being
written. Those states are recorded in `TEST_RESULTS.md` and
`SESSION_HANDOFF.md` as they happened, because "all gates green" as a bare
final claim would imply they were always green. Nothing was skipped, xfailed,
deselected or excluded to reach the current 1061-passing state.

---

## 2026-10-14 — backend features mega-mission

| # | Decision | Reason |
|---|---|---|
| D-a | `return_pct` / `avg_trade_pct` are **percent**, not fractions | The payload contract (and the frontend's `fmtPct`) expects percent; two units in one contract silently misreported every trade P&L by 100×. Recorded as B-32 with the contract change noted in `TEST_RESULTS.md`. |
| D-b | Equity marking uses the **last usable finite positive close** (entry-price anchor at open), with `stale_marks` + warning | Collapsing to cash on a NaN/zero close fabricated −100% days (B-33). Never mutates the stored row — R1 stays the owner's policy call. |
| D-c | The security master lists **only symbols that delivered bars** | A master row claims "we have data for this"; a failed fetch is not data (B-37). |
| D-d | Ingestion log status: success ⇒ ≥1 succeeded **and** 0 failed; otherwise partial/failed | A `success` row over a zero-row run (e.g. HTTP 401 on the symbol list) is a green light over an empty database (B-38). |
| D-e | Floor-sheet numbers are parsed **verbatim by `float()` first**; separator-stripping is only the fallback | The filter deleted the `e` in `1e5` → 15: a plausible-looking wrong quantity (B-36). |
| D-f | A missing symbol is **never inferred from a filename** | `backup.csv` would silently become symbol BACKUP — a guess attributed to real trades. The importer says so and requires `--symbol`. The old docstring claim was false and is removed (B-39). |
| D-g | Rolling-origin forecasting verdicts must name the baseline result (`BEATS`/`NO DEMONSTRATED SKILL`/`UNDETERMINED`) | A skill score without "compared to what" overstates the model; flat hold-outs are `UNDETERMINED`, never a fake 100% win. |
| D-h | News summaries always state "no live source is connected; nothing is fetched, scraped or sentiment-scored" | The archive must never read as a live feed or a signal (register item 7, L4). |
| D-i | B-31 merged into B-11 | Two numbers for one limitation (fee placeholder) made status ambiguous; B-11 is canonical, B-31 is a pointer. |

## 2026-10-14 — forensic verification pass

| # | Decision | Reason |
|---|---|---|
| D-j | A floor-sheet number that is scientific notation **plus** a currency marker (`"1e5 USD"`, `"Rs 1e5"`) is **rejected, not guessed** | B-36 made the verbatim `float()` path safe, but such a value fell into the separator-stripping fallback, which deleted the `e` and turned `"1e5 USD"` into 15.0 — the same corruption through a second door (B-40). The fallback now refuses any string still holding `e`/`E`; the row is skipped with a reason. |
| D-k | `run_backtest` normalizes `trading_date` (`pd.to_datetime(format="mixed")`) **before** sorting and duplicate detection | The B-34 guard only caught duplicates of one representation; the same session written `"2026-01-08"` and `"2026-01-08 00:00:00"` slipped through. Unparseable dates fail loudly rather than being misordered. |
| D-l | `value_portfolio`'s mark guard is `math.isfinite(close) and close > 0`, matching the backtest engine | The earlier guard used a bare NaN test plus `> 0`, which let `+inf` through and would poison every total and the JSON with infinity. B-33/B-35 now use one consistent "finite and positive" rule everywhere a price becomes a mark. |
| D-m | Correctness of a calculation is verified separately from predictive performance | Rolling-origin and backtest pipelines are proven leak-free and hand-consistent on fixtures; that is **not** a claim of out-of-sample accuracy on NEPSE, which stays NOT-TESTED until genuine historical data is wired in. |

## 2026-10-14 — OpenRouter gateway + Phase 1 blocker code-readiness

| # | Decision | Reason |
|---|---|---|
| D-n | **OpenRouter is the selected hosted AI gateway** (replacing the dormant OmniRouter reference, D2). Decision recorded only — no broad rewrite, no key present, no request made. | The owner chose it; the old OmniRouter integration was a config-only stub with no client behind it, so there is nothing to "repair." Recording the choice is Phase C; integrating it belongs to a later, deliberate task. |
| D-o | The LLM lives behind one stable interface in `megatool/llm.py` and **nothing in the quantitative core calls it**. Default is `DisabledProvider`, which refuses rather than dialling out. | Indicators, scanning, backtesting, Fibonacci, portfolio/risk and cost arithmetic must stay deterministic and key-independent; an LLM must never invent a price or replace a calculation (Phase C). |
| D-p | The API key is read from `MEGATOOL_AI_API_KEY` (env / `.env`), sent only in the `Authorization` header, and **never printed, logged or returned** — status reports presence + length only. One attempt per call (no auto-retry). | Retrying a timed-out hosted request can charge twice; a key in an error or status line is a leak (standing rule: report presence/absence, never the value). |
| D-q | Sector classification, per-component fees and an index series are **loaded from owner files through validated loaders**, not synthesised, and each loader refuses malformed input rather than importing a partial/incorrect result. | T-11/T-12/B-10 need *authoritative* data; the loaders provide the ready pipeline so the moment the owner drops a file the factor turns on — without any fabricated stand-in. |

### OpenRouter / provider architecture (Phase C answers)

1. **Where the abstraction lives:** `megatool/llm.py` — `BaseLLMProvider` (ABC) with `OllamaProvider` (local), `OpenRouterProvider` (hosted), `DisabledProvider` (default), and a `get_provider()` factory. Reuses the pre-existing `MEGATOOL_AI_PROVIDER/_API_KEY/_MODEL` env hooks in `config.py` (previously defined but consumed by nothing).
2. **First consumer:** a narrative feature only — drafting a journal note or summarising a floor sheet/news item — reached via the `megatool ai` CLI. **Not** research/scan/backtest, which stay deterministic. No API route exposes it (avoids a remote, cost-incurring endpoint).
3. **Config & secret mechanism:** the project's existing dotenv pattern (`config.py` loads optional `.env`); secrets come from environment variables and are never hard-coded.
4. **Keeping the key server-side:** it is only ever read into `OpenRouterProvider._secret`, placed in the request header, and scrubbed (`_redact`) from any error text; `provider_status()` reports only `has_api_key` / `api_key_length`.
5. **Local mode stays optional:** with no `MEGATOOL_AI_PROVIDER` the factory returns `DisabledProvider`; the app and the entire 1389-test suite run with zero Ollama/OpenRouter contact (proved by `httpx.MockTransport` handlers that fail on any request).
6. **Model / timeouts / errors / limits / cost:** model from `MEGATOOL_AI_MODEL`; timeout `MEGATOOL_AI_TIMEOUT` (default 60 s) → `LLMUnavailable`; HTTP ≥ 400 / bad JSON → `LLMRequestError`; missing prereqs → `LLMNotConfigured` raised **before** any request; a `MEGATOOL_AI_MAX_TOKENS` default (512) caps spend, and the CLI's hosted `ping` requires an explicit `--allow-hosted` acknowledgement before any credit is consumed.

---

## 2026-10-14 — T-M1: metadata safety (upsert contract + opt-in eligibility)

| # | Decision | Reason |
|---|---|---|
| D-r | `upsert_securities` treats an **omitted or NULL `delisted` as "preserve"**; only a supplied `bool` overwrites; a brand-new row takes the column default (FALSE). Implemented as two SQL statement shapes (one never assigns the column) because DuckDB cannot distinguish "key absent" from "bound NULL" in the excluded row. | The previous `delisted = excluded.delisted` silently reactivated merged/delisted securities on any partial refresh — a data-loss hazard with no test pinning it. Omission must never be a value. |
| D-s | Under an active eligibility filter, **unknown metadata (no row / NULL field) is excluded with an explicit reason** — never silently eligible, never given a guessed classification, and never replaced by a hard-coded symbol list (the 21 merged symbols are *not* special-cased). `delisted` is honoured only when stored `True`; merged ≠ delisted. | A filter the user opted into must be conservative and auditable, but honesty forbids inventing a status. The reason string keeps every exclusion explainable. |
| D-t | The filters are **opt-in and default-off** on `run_screen`, `/api/screen` and `/api/rank`; `rank_universe` stays pure (frames in → ranks out) and the shared pure function `eligibility_from_meta` is the single decision point for scanner and ranking. No schema change, no `status` column, no migration. | Backward compatibility is verified by tests, not assumed: with filters off the metadata is never even queried. Consistency between scanner and ranking comes from one function, not two copies. |

---

## 2026-10-14 — T-M2: dry-run metadata import harness

| # | Decision | Reason |
|---|---|---|
| D-u | One canonical dry-run input schema: `symbol` plus at least one of `name`/`instrument_type`/`sector`/`status`/`delisted` (optional `source`, `requires_manual_review`; other columns ignored and listed). The vocabulary sets (`ALLOWED_INSTRUMENT_TYPES`, `ALLOWED_STATUSES`) are **what this build understands from the reviewed dataset, not an authoritative NEPSE classification** — out-of-vocabulary values are rejected with the reason shown, never coerced into a neighbouring value. Every file value is labelled `source-provided-unverified` (or `unverified-no-provenance`); only stored `security_master` fields count as verified. **No import command exists**: production writing stays a separate, owner-approved operation. | A dry run is only trustworthy if it validates strictly and labels honestly. Rejection with a reason is auditable; guessing a status or sector is fabrication. Keeping the vocabulary explicit and closed prevents a typo from silently becoming metadata, and refusing to implement the write path removes the accident from the critical path. |
| D-v | A record whose proposals have **no stored counterpart** (e.g. `status` only — `security_master` has no listing-status column) is classified `advisory`, never `unchanged`, and **every status proposal is flagged for manual review** (official status needs an owner-supplied source, blocker B-2). Conflicts preserve and report the stored value; additions (symbol with no row) are reported for review, never created; `merged` is never converted to `delisted` (decision D-s / B-4). | Calling an unverifiable proposal "unchanged" would imply the store agreed with it. Flagging every status keeps the file's 465 status rows visibly pending until B-2 supplies an authoritative source, instead of letting unverified listing states pass as reconciled. |
| D-w | Outputs are deterministic — no timestamps, sorted keys and symbols, input `sha256` recorded — and written to a **new** location (`data/review/dry_run/<stem>_dryrun.{json,md}` by default) with a **refusal to overwrite**: an existing target aborts the run with an explicit message. The store is opened `read_only=True` with a probe query forced at open (MarketStore connects lazily), so a missing or locked database fails as a message before any work. | Identical input + identical store state must produce byte-identical reports (requirement: repeatable evidence). Previous reports are evidence too, so the harness never clobbers them. Forcing the connection at open turns DuckDB's lazy `IOException` into a clean error instead of a traceback, and read-only mode guarantees the harness cannot create or modify a database file at all. |
| D-x | `sector_percentile` is defined as the **within-sector percentile of 3-month momentum** (research report §8.2), computed only when usable sector coverage of the ranked universe meets a configurable threshold (default 0.5); it carries **zero default weight** so default rankings are byte-identical until a caller opts in; singleton sectors yield no value (never fabricated). | The factor had no metric and a hard-coded unavailable reason that would go stale the moment sectors were imported (forensic R-4). §8.2 is the only published definition of a sector-relative factor, so it is followed rather than inventing a new one. Zero default weight preserves every existing ranking result; the threshold keeps a 1-of-6-coverage mapping from producing meaningless "percentiles"; a percentile within a group of one is not a statistic. |
| D-y | The fee schedule's **shape** is extended — `FeeTier(ceiling, rate)` for size-tiered commission and `applies_to` (traded_value vs net_gain) for gain-aware CGT — with **every rate left None** until the owner confirms the researched figures (C3). | The researched SEBON schedule is tiered and CGT is levied on net gain; a flat per-side engine cannot honestly represent either. Recording shape without rates keeps the disclosure truthful (boundaries without prices) and prevents a future "verified" claim from resting on numbers nobody confirmed. Applying the shapes to live P&L stays gated on the owner. |
| D-z | AI assistance is an **optional, clearly separated layer**: deterministic tool results and any AI interpretation return in different fields; tools marked private (portfolio risk, journal) are **excluded from the AI prompt by default** and reach a model only on an explicit per-request `include_private`/`authorize_private=true` flag; a refused/absent AI step never changes the deterministic output, and the recipient (local Ollama vs hosted OpenRouter) is named when a call happens. | Guardrails require private journal/portfolio data to stay local without explicit authorization, and tool output must never be rewordable by a model. A per-request flag makes authorization auditable per call instead of a standing ambient permission; naming the recipient keeps the owner aware of where their data went. |
| D-aa | The regime feature labels its input an **equal-weighted market proxy built from stored closes** — never "the NEPSE index" — until blocker B-10 supplies an official index source. | Calling a proxy the official index would misattribute both its level and its history (the real index series is unvalidated pending B-10). An honest label lets every regime statement be checked against what data it actually used. |
| D-ab | Post-trade portfolio weights assume **new capital equal to `units × entry` enters the portfolio at purchase**, stated in the response; with a held symbol but no usable stored close, both weights are refused rather than approximated. | The ledger models no cash (portfolio.py contract), so any funding assumption must be visible in the output instead of hidden in the arithmetic; inventing a price for an unpriced position would fabricate a weight. |

---

## 2026-10-15 — R5 / B-4: merged-security semantics

| # | Decision | Reason |
|---|---|---|
| D-ac | `security_master` stores listing status in a dedicated `status` column (`ACTIVE`/`SUSPENDED`/`MERGED`/`DELISTED`/`UNKNOWN`) **distinct from the legacy `delisted` flag**, plus an optional `successor_symbol`. The schema migration is idempotent (`ADD COLUMN IF NOT EXISTS`) and writes no historical price data; existing rows acquire the column default. | A boolean `delisted` cannot represent `MERGED` or `SUSPENDED` without inventing a `merged → delisted` mapping, which the owner explicitly forbade. Storing status distinctly makes the distinction observable and lets the scanner/rank exclude verified non-tradable securities while keeping `UNKNOWN` symbols visible so missing metadata does not silently erase valid securities. `successor_symbol` retains evidence-based successor relationships without inventing them. |
| D-ad | The scanner and ranking endpoints exclude verified non-tradable securities (`DELISTED`, `SUSPENDED`, `MERGED`) **by default**. `ACTIVE` symbols are allowed. `UNKNOWN` symbols are allowed with an explicit uncertainty note; they are not silently labelled delisted. Callers can pass `exclude_delisted=False` to include every symbol with stored history (the pre-filter behaviour). | The owner prioritises accuracy over inclusion of dead tickers. Unknown status is not evidence of delisting, so excluding unknown symbols would incorrectly remove potentially valid securities solely because metadata is missing. The uncertainty note keeps the gap observable. |
| D-ae | `MERGED` status is **never converted to `DELISTED`** automatically. A merged security is stored as `MERGED`, remains non-tradable, and may carry a `successor_symbol` only when the input supplies one. | The owner rejected the blanket rule equating merged with delisted. Preserving `MERGED` as its own status keeps historical records honest and lets downstream consumers distinguish merger-related disappearance from regulatory delisting. |
| D-af | `eligibility_from_meta` derives a missing/NULL status from the legacy `delisted` flag only as a fallback (`True` → `DELISTED`, otherwise `UNKNOWN`). The stored `status` column is the primary source of truth once populated. | This lets pre-existing rows stay useful without a mass backfill, while ensuring new imports use the canonical status vocabulary. |
| D-ag | The `watchlists` and `experiments` tables are created **lazily inside their own modules** (`CREATE TABLE IF NOT EXISTS` on first use), not added to `db.py`'s `init_app_db`. | The standing rule is not to modify production migrations / db-init to make new features work. Lazy creation in the owning module cannot disturb the running production process and keeps each feature's schema next to its code. `watchlists` already existed in the schema; `experiments` is new and self-contained. |
| D-ah | `/api/backtest` and experiment **reproduce** share ONE code path (`_run_backtest_request`); the experiment's config hash is SHA-256 of canonical (sorted-key) JSON. | Two drifting backtest implementations would make "reproduced" meaningless. A content hash over a canonical form makes "same config" checkable, and comparison reports metric-by-metric deltas with an explicit tolerance rather than asserting success. |
| D-ai | Chart markers are collected from every source (swings, candlesticks, manual Elliott labels, harmonic pivots) into dedicated `state.*Markers` arrays and written in **one** `setMarkers` call. | lightweight-charts' `setMarkers` *replaces* the whole marker set, so per-source calls silently erased one another — that is why `plotCandlestickMarkers` was dead code. One flush makes the overlay composition deterministic. |
| D-aj | **go-nepse is not integrated** (see `docs/GO_NEPSE_INVESTIGATION.md`). **Superseded by D-bc** (session 22); retained as the rationale for rejecting a *naive, ungated* adoption. | The library defeats NEPSE's anti-bot token obfuscation via an embedded WASM blob, impersonates a browser, and documents disabling TLS verification — all of which breach Mega Tool's hard rules. It also targets the gated official API, adds a second (Go) runtime, and is immature (0.2.0, core tests unwritten). |
| D-ak | The new `GET /api/bars/{symbol}/candles` route reuses the workspace's OHLC-validity segmentation: internally impossible bars are **excluded and counted** (`bars_excluded_invalid_ohlc`), never repaired, and a pattern never spans a gap that never traded. | Matches the established, tested convention in `workspace.py`. The dev/QA fixture is deliberately adversarial (243/420 bars have impossible OHLC), and the honest behaviour is to exclude and disclose, not to fabricate. |
| D-al | The candlestick pattern catalogue is 15 names. **`tweezer` and `harami_cross` are absent**; `harami` is present. | The mission's pattern wish-list named tweezer bottoms/tops, which the engine does not implement. Rather than add an untested detector to "tick a box", the gap is recorded as a limitation. |
| D-am | The **custom rule builder has no new evaluation engine**: it composes the existing, already-tested scanner tree (`ScreenNode` / `evaluate_node` / `run_screen`) and executes it through the existing `POST /api/screen`. Persistence is the new, storage-only `megatool/screens.py` over the pre-existing `saved_screens` table (created lazily with `CREATE TABLE IF NOT EXISTS`, per D-ag). A saved rule is stored as the **user JSON tree** and re-parsed on load through `ScreenNode.from_dict` + `validate_tree`; an unknown metric or operator is rejected at save time. The frontend only ever builds a data tree — there is **no `eval`, no `exec`, no browser-supplied SQL, and no arbitrary Python execution**. | A second screening implementation would drift from the tested one and multiply the safety surface. Re-validating on load means a rule saved before a metric changed fails loudly instead of silently screening nothing; and restricting the wire format to the existing screen tree makes "custom rule" and "preset screen" the same audited path. |
| D-an | **Dashboard composition is client-side only.** Panels are shown/hidden and reordered with CSS `order` on the existing Overview `.card` elements, persisted in `localStorage` under `mt-dashboard-layout`; "Reset layout" restores the shipped order and visibility. No backend endpoint, no new persistence table, no decorative cards. | The requirement is a *look* preference for one local user, not shared state; adding a table/route would be production schema churn for zero analytical value. Keeping the markup as the source of truth means the default layout is always recoverable and a hidden panel is simply hidden — never replaced by a placeholder number. |
| D-ao | The candlestick catalogue is widened **15 → 18** by adding three detectors with real, unit-tested rules: `harami_cross` (a harami whose second candle is a doji), `tweezer_bottom` and `tweezer_top` (two candles sharing a low/high within a configurable `tweezer_tolerance_ratio` of their mean price). This **supersedes D-al**. `PATTERN_CANDLE_COUNT` is now derived from grouped name tuples rather than index slices, so the count can never drift from `PATTERN_NAMES`. | D-al deferred these because no tested rule existed; the rule is now written and covered by tests (exact fire, near-miss negative, catalogue/count consistency, configurable tolerance), so the honest state is "implemented and tested", not "advertised but absent". Deriving the candle-count map from the same tuples removes a silent class of bug where a new name lands in the wrong group. |
| D-ap | The Elliott and harmonic routes gained an explicit **analysis window** (`start` / `end` / `limit`), and harmonic gained `slack` (band widening) and `patterns` (subset filter). The frontend passes the **chart's own window** to the engine and to the companion `/structure` and `/api/bars` calls, so the engine's bar indices map onto the bars actually drawn. `slack > 0` results are labelled **approximate**; `slack = 0` means published ratios only. | Without a shared window the engine's pivot indices fell outside the plotted range, so a "Draw" button could appear to do nothing — a real defect (B-56). Asking the engine the same question the chart is showing makes the overlay verifiable, and echoing `slack`/`catalogue`/`patterns_tested` keeps the tolerance and the tested pattern set auditable rather than implied. |

### Session 20 (2026-10-16) — integration, not new research

| # | Decision | Reason |
|---|---|---|
| D-aq | **Manual Fibonacci drawings are the researcher's own work, and are labelled as such.** They are stored per symbol in `localStorage['mt-drawings-<SYM>']`, in **chart data coordinates** (a date and a price per anchor), so they survive indicator toggles, time-frame/range changes and chart rebuilds. The retracement level is `p2 − r·(p2 − p1)` and the extension is `p2 + r·(p2 − p1)`; the list shows the ratios actually used. An unfilled two-click draft is explicitly a draft (`Anchor 1: … click the second anchor`). | A hand-placed Fibonacci study is an annotation the user authored. Storing it in *pixel* space would silently move it when the range changed, and presenting it identically to detector output would make the two impossible to tell apart. Dates+prices are the only representation that is stable and auditable, and the formula is stated so a level can be recomputed by hand. |
| D-ar | The chart-pattern panel calls the patterns endpoint with the **chart's own window** (`?limit=<range>`) and maps each pivot through its **own reported `date`** (falling back to the index only if none is present). This supersedes the earlier "endpoint is called without a window, so indexes are into full history" assumption. | The engine's bar indices are only meaningful relative to the bars it was given. Asking it about a different slice than the one on screen produced breakout/invalidation lines with no pivot polyline — a silently wrong overlay (B-58). The pivot's own date is authoritative and window-independent, so the overlay is now verifiable: the drawn polyline equals the detector's reported pivots. |
| D-as | **`relative_strength` becomes a real scanner metric** (the catalogue grows 33 → 34). It is the stock's `lookback`-bar (default 60) close-to-close return **minus the NEPSE composite's** over the same aligned dates, in percentage points. `run_screen` loads the benchmark **lazily and only when the tree names the metric**, so every other screen is unchanged and pays nothing. A missing or too-short benchmark makes the security **ineligible with the reason** — never a substitute index or a zero. A new read-only route `GET /api/bars/{symbol}/relative-strength` publishes the same calculation with an explicit **inner-join** contract and a ratio line rebased to 100. | "Relative strength" that silently substitutes an invented benchmark, or that quietly returns `0` when the index is absent, is exactly the class of fabricated number this project forbids. Making the benchmark a hard precondition and saying so is more useful than a number that cannot be trusted. Loading the index only when asked keeps a 2000-test suite's hot path unchanged. |
| D-at | The **floating assistant** is one panel with two honest actions: *Send* → `POST /api/agent/run` (deterministic tools over stored data), and *Propose rule* → `POST /api/screens/propose` (the deterministic grammar of D-am). A proposal is rendered for review, with **unmatched clauses listed and explained**, and a *Load into rule builder* button moves the tree into the existing Screener. It only executes when the researcher presses **Run rule** there, through the already-audited `POST /api/screen`. | The chat is a discovery surface, not an execution engine. Routing both actions into code paths that already exist and are already tested means the assistant adds reach without adding a new way for a number to be invented. Reporting the clauses it could *not* understand (P/E, P/B, dividends) is the difference between an honest tool and one that quietly ignores half the question. |
| D-au | Alert **severity**, **cooldown** and **acknowledgement** are additive. `alert_history` gains `severity` (default `warning`), `fire_count` and `acknowledged_at` through the same idempotent `ADD COLUMN` migration already used for `pdf_records`. A re-firing condition **updates** its existing row (new message/time/severity, `fire_count + 1`) instead of inserting, so the table's `UNIQUE (alert_key, symbol)` key and the "one row per condition+symbol" model are preserved. Declaring **no** `cooldown_minutes` keeps the original *once-until-cleared* contract, so existing behaviour is the default. Acknowledging records that the owner saw it; it never deletes history and never re-arms a condition. | Two problems with the old contract: an alert could not say how serious it was, and re-arming meant losing the record that it had fired. Counting fires in place gives re-arming and an audit trail without a second table or a schema rewrite, and keeping once-until-cleared as the default means no existing alert changes meaning because of this session. |
| D-av | **Research templates are declarative** (`megatool/templates.py`): each names an optional agent question plus concrete GET/POST calls against endpoints the application already serves, and the frontend is a **generic runner** that performs them. A test asserts (a) every declared path exists in the application's own OpenAPI route table and (b) every step executes against a fixture store without a 5xx or a 422. Saved copies live in this browser. | "Template" must not become a second analysis implementation that drifts from the tested one, nor a list of titles that do nothing. Tying the catalogue to the live route table means a template physically cannot advertise an analysis the platform lacks. Saved copies are browser-local because the experiments store requires a *backtest payload*; fabricating one to satisfy the schema would be a false record. |
| D-aw | **Read-only tooling must not write the operator's state database.** `Paths.app_db` now honours an `MEGATOOL_APP_DB` environment override (read on every access, unlike `MEGATOOL_DATA_DIR` which is captured at import). `scripts/route_inventory.py` and `scripts/perf_smoke.py` redirect the app store to a temporary file while they build the app, and the test suite's isolation fixture now uses the same override. | `create_app()` runs `init_app_db()`, so merely *building* the app migrates the schema. The route-inventory gate — required by this project's own workflow — was therefore migrating `data/processed/megatool_state.sqlite` on every run (B-59). The fix has to cover route handlers too (`get_conn()` resolves the same property), so an environment override fixes the whole class rather than the one call site that happened to be noticed. |

### Session 21 (2026-10-16) — fix the defects a re-verified frontend exposed

| # | Decision | Reason |
|---|---|---|
| D-ax | `GET /api/bars/{symbol}/fibonacci` answers a **data condition** — too few confirmed swings of both kinds, or anchors that cannot form a study — with **`200 {available: false, unavailable_reason}`**, matching `relative-strength`/`patterns`. A malformed level set (`retracements`/`extensions` not numeric, or negative) stays a **400 client error**, now rejected in `parse_ratios` before any calculation. The success payload gains an explicit `available: true`. Supersedes the 422 contract (B-60). | A symbol with too little history is an answer, not a request error. Returning 422 made an *expected* outcome look like a broken request in the browser console and diverged from the two newer analytics routes. Validating ratios up front keeps the two failure classes distinct: a bad number is the caller's fault (400); thin data is the data's (200 + reason). |
| D-ay | The **Fibonacci chart overlay is drawn from the endpoint's real contract**: `plotFibonacci` flattens `retracements` + `extensions` (rows carry `ratio`, `percent`, `price`, `kind`, `family`), colours retracement vs extension differently, labels each with its percentage and the `convention` tag, and draws **nothing** when `available` is false. | The overlay read a non-existent `data.levels` array, so the API-detected Fibonacci study **never rendered** — a visible control that silently did nothing (§8, B-61). Deriving the overlay from the endpoint's own keys means the two cannot drift. |
| D-az | The scanner's tree evaluator uses **three-valued logic**. A condition whose metric is unavailable is *unknown* and must never be treated as true: an **AND** whose computable clauses all pass but which contains an unknown clause returns *unknown* (→ ineligible, reason surfaced); an **OR** with no clause known true and an unknown clause likewise returns *unknown*. A definite false in an AND, or a definite true in an OR, still resolves. | The old evaluator dropped unknown clauses entirely, so `rsi < 30 AND bars_listed >= 60` **passed** a flat/illiquid symbol by evaluating only the bars clause and losing the RSI clause (B-62). That violates "a missing metric must not silently qualify a security" — a fix, not a preference. |
| D-ba | The `hidden` attribute is **authoritative**: `[hidden] { display: none !important; }` is added to the stylesheet. | `.chat-panel { display: flex }` (class, equal specificity to `[hidden]`) won over the UA rule, so the assistant panel could not be closed — the × and `Esc` set `hidden` but the panel stayed on screen (B-63). One rule fixes the class for every current and future `hidden` element. |
| D-bb | `/api/sources` states `access_method` and `requires_auth` for the snapshot and gated-official entries, and the Data & Quality table renders `available` as **three** states (`yes` / `no` / **not probed**) plus an `authorized` badge and the source's own note. | `available: null` means "we never probed it" (a gated/on-demand source), which is not the same as "down"; showing it as a red "no" mislabelled a gated source as broken. The note now carries the go-nepse position so the UI itself explains why that surface is not used. |

### Session 22 (2026-10-16) — the *actual* go-nepse Go library, integrated behind a process boundary

| # | Decision | Reason |
|---|---|---|
| D-bc | **go-nepse is integrated — the actual Go library, not a Python re-implementation of its protocol** (supersedes D-aj). A small Go program (`tools/gonepse-bridge/`, module pinned at `github.com/voidarchive/go-nepse v0.2.5`) links the real library, reads one JSON request on stdin and writes one JSON envelope on stdout; `megatool/datasources/gonepse.py` (`GoNepseAdapter`) spawns it and parses the result. | The owner directed that the real library be used. A subprocess boundary keeps the library's own HTTP/token/retry code intact (what runs is what upstream wrote), needs Go only at build time, and isolates any crash or hang from the Python app. Re-implementing the protocol in Python is exactly the approach that was rejected. |
| D-bd | **TLS verification stays ON** (`Options.TLSVerification = true`, never cleared), and the exchange's certificate is **diagnosed, not bypassed**: a verified handshake to `nepalstock.com.np:443` succeeds today (DigiCert/GeoTrust chain, valid to 2026-12-10, SAN covers `nepalstock.com.np`); evidence in `docs/evidence/session22-nepse-tls-cert.txt`. The bridge sets `Options.Config.BaseURL` because upstream ignores `Options.BaseURL` for requests. | Upstream's docs recommend disabling verification; the project rule is verification on. Diagnosing the chain showed the documented problem is currently absent, so no insecure mode is needed — and any future certificate failure is reported verbatim instead of masked. |
| D-be | **The owner gate is enforced independently in both layers.** The Python adapter raises `SourceUnavailable` when `MEGATOOL_NEPSE_API_AUTHORIZED != "1"` *before* spawning the bridge; when the target is the real `nepalstock.com.np` the bridge itself refuses and exits `3` with `kind:"unauthorized"` unless the same variable is `1`. A non-default base URL (test server or proxy) is not gated. The adapter never sets the variable. | The gate must not be bypassable by invoking the binary directly, nor by a change on one side. Two independent checks mean an accidental live request needs two separate mistakes. |
| D-bf | **Provenance is its own label:** `DataSource.GONEPSE = "go-nepse (github.com/voidarchive/go-nepse)"`, distinct from `NEPALSTOCK_OFFICIAL`. The adapter exposes `status()` / `GET /api/gonepse/status`, which is **network-free** and reports `bridge_present`, `authorized`, `tls_verification`, the operation list and **every** reason live access is blocked; `/api/sources` gains a `go-nepse` entry. | The data is NEPSE's, but the transport is not — collapsing the labels would erase which client fetched a record. A status endpoint that probed NEPSE to answer "are you up?" would itself be the access the gate exists to withhold, so it answers from build/gate facts only. |
| D-bg | **Tests exercise the real library without touching NEPSE.** The Go suite runs the actual token flow (fetch → embedded-WASM salt parse → `Authorization: Salter …`) and data decoding against a local `httptest` TLS server serving the library's own token fixture, and asserts the auth header was produced. The Python suite fakes only the subprocess boundary and covers malformed/empty/non-envelope output, timeout, `OSError`, provider-error mapping and both gate checks. Verdict: **Go package builds PASS · actual library integrated YES · live connection BLOCKED (gate unset)**. | "The binary builds" and "mock tests pass" are not evidence that live data works, and the mission forbids conflating them. Deterministic fixtures give real coverage of parsing/error/gate behaviour now, while the live result is reported for exactly what it is. |
| D-bh | **The portfolio gains a cash-flow model, not a cash balance.** `cash_flows()` signs every recorded trade (buy = `quantity×price + fees` out; sell = `quantity×price − fees` in), keeps a running `cumulative` in `traded_at, id` order, and reports `total_invested`, `total_proceeds`, `total_fees`, `net_cash_flow` and `per_symbol_net`. It is exposed at `GET /api/portfolio/cash-flow`, embedded in `GET /api/portfolio` as `cash_flow`, and shown in the Portfolio panel. The note states it is the *recorded trades'* net cash effect, **not an account cash balance** (deposits, withdrawals, dividends and interest are not recorded); the valuation note keeps "Cash balances are not modelled". | The owner asked for a cash-flow model built from recorded transactions, qty/costs/fees. Calling the result a "cash balance" would be false — the ledger has no deposits — so the model is bounded to what the data can actually support and says so in both the API note and the UI. Fees are included on both sides because a fee is a real cash effect, not a rounding detail. |

### Session 23 (2026-10-16) — live data: measured, not promised

| # | Decision | Reason |
|---|---|---|
| D-bi | **Live data is a provider layer that measures freshness instead of asserting it** (`megatool/live.py`). Providers: `sharehub` (licensed, ~20 s), `official` (gated go-nepse, near-real-time), `feed` (owner-supplied JSON URL), `yonepse` (public hourly fallback). Every snapshot carries `observed_at` (the source's own newest timestamp), `fetched_at`, `fetch_latency_ms`, `cache_age_seconds` and `age_seconds`, and a `freshness` label ∈ {live, recent, delayed, stale, last-close, unknown}. | The mission's core requirement is that a 100 ms request returning a 20 s-old snapshot must not be called a 100 ms live feed. The only way to guarantee that is to derive freshness from the source's timestamps and surface the request latency separately. A single provider would have hard-coded its weaknesses; a layer makes each source's real cadence visible. |
| D-bj | **The official API stays blocked, and the gate alone is not the blocker.** Measured: `/api/nots/*` returns `401 WARNING: UNAUTHORIZED ACCESS` without a `Salter` token; the public `/api/authenticate/prove` returns `salt1..5` plus an encrypted token, and producing the accepted token means running NEPSE's embedded WASM — an anti-bot bypass this project never performs. TLS is verified and valid, so the certificate is not the cause. The official provider is therefore implemented but inert; opening the gate would not be sufficient and is not done. | Two rules apply independently: never defeat anti-bot controls, and keep the official surface behind the owner gate. Reporting the *precise* cause (anti-bot, not network/TLS/gate) is what lets the owner act sensibly — and the honest answer is that they should use a licensed feed rather than have us bypass the token. |
| D-bk | **Every configured provider is cached at its own publication cadence, and the UI polls only while Overview is visible.** | Polling a 20 s source every second manufactures a request storm and mislabels the ages of the returned rows. Caching at the cadence makes fast UI polling free to the source, and stopping when the tab is hidden removes background churn. |
| D-bl | **Credentials are server-side only and never appear in a URL.** ShareHub auth is a POST body; `MEGATOOL_LIVE_FEED_URL` is read from the environment; the module never sets `MEGATOOL_NEPSE_API_AUTHORIZED`. | A token in a query string leaks into logs, history and referrers. Server-side env keeps the boundary the project already uses for its other secrets, and forbids any code path that could silently enable the official surface. |
| D-bm | **The public fallback is labelled by its real age, and when data cannot be fetched nothing is fabricated.** A missing/invalid price is `null` with a `validation_status`; `high < low` is `suspect`; an unconfigured or unreachable provider yields an explicit reason, and `/api/status` sets `live_feed_connected` true only for an owner-configured source, never for the public mirror. | YONEPSE's market files were ~4 days stale during this session; presenting them as "live" would be the exact fabrication the project forbids. Tying `live_feed_connected` to owner-configured sources keeps the flag meaningful. |

### Session 24 (2026-10-16) — the free source works; the staleness was a CDN

| # | Decision | Reason |
|---|---|---|
| D-bn | **Read the repository's raw content, not the GitHub-Pages mirror.** `yonepse.BASE_URLS = (raw.githubusercontent.com/…/main, shubhamnpk.github.io/yonepse)`; raw is tried first and Pages is a fallback only. | Measured the same minute: Pages served `last_checked 2026-10-12` (~4 days old) while raw served `2026-10-16T07:17` (31 min) with the NEPSE index at 2,625.93 and 328 in-session quotes. The "stale free data" limitation was a CDN cache in front of a healthy source, not the source. |
| D-bo | **Freshness is relative to the source's publication cadence, not an absolute age.** Providers declare `publish_cadence_seconds` separately from the poll `cadence_seconds`; `delayed` covers age ≤ max(1.5 × publish cadence, 90 s), `stale` is beyond it, `last-close` applies when the market is shut, `historical` beyond ~5 days. `LIVE_VERIFIED` requires age ≤ 30 s. | An hourly publisher is normally ~40 min old; calling that "stale" misdescribes a healthy source, while calling it "live" overstates it. Absolute bands cannot express that, so the cadence travels with the provider. |
| D-bp | **A fallback must name the mirror it used.** `fetch_market_snapshot()` returns the base that answered; the snapshot exposes `origin` and adds a note when it is not the raw content. | When the upstream repo briefly served a **git merge-conflict** commit, the adapter fell back to the cached Pages mirror. Reporting `STALE` with `origin = shubhamnpk.github.io/yonepse` keeps provenance truthful; silently labelling it "raw" would have been a lie even though no number was fabricated. |
| D-bq | **Conflict markers are never "repaired" into data.** A non-JSON payload fails the fetch; it is not scrubbed into a guessable value. | Treating `<<<<<<< HEAD` as JSON to salvage would be fabricating an observation from a broken file. Refusing and falling back (or erroring) is the only honest behaviour. |

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
| 10 | Phase completion is judged at **requirement** granularity, not section granularity | A spec section having *some* implementation (e.g. Phase 6) does not make every requirement in it done; the 2026-10-16 audit (`docs/PHASES_2_6_COMPLETION_AUDIT.md`) re-labels Phase 2–6 as PARTIAL and corrects the earlier "M4 TESTED-PASS" / "NOT STARTED: 0". |
| 11 | A capability is not "delivered" until the user can reach it | Harmonic/Elliott engines are tested but have no UI, so they are PARTIAL; UI reachability is part of the acceptance criteria (§38). |

---

### Session 25 (2026-10-16) — resilient free data and a reviewable-ratio path

| # | Decision | Reason |
|---|---|---|
| D-br | **When the branch tip is unreadable, walk back to the newest *parseable* commit — chosen by the payload's own quotes, not by commit order.** `_market_ref()` scores candidate refs by the newest `last_updated` in `live.json`; `_fetch_json_verbose()` tries `main`, then recent commits (GitHub API, cached), then Pages, and returns the ref that answered. | During the incident the newest *clean* commit (`8493293c`) parsed fine but its quotes were a day old, while an older commit (`f8941a30`) had same-day data. "First that parses" would have silently served yesterday's prices; "newest observation wins" serves today's. Commit order is not freshness. |
| D-bs | **Conflict markers are never repaired into data** (restated and now enforced by test): a non-JSON payload fails, and the next ref is tried. | `<<<<<<< HEAD` is not a value. Scraping it into a number would fabricate an observation from a broken file. |
| D-bt | **Fundamentals ratios stay gated on a reviewed level, and review is an explicit, source-scoped operator act** (`fundamentals review --source …`). The guard is unchanged; a new function promotes one named source's `extracted` rows to `reviewed`/`verified` and reports how many. | Deleting the guard to make P/E work would weaken validation for a demo. The guard exists because an unreviewed figure must not drive a ratio; the honest complement is to let the owner say "I trust *this source*", scoped and auditable, rather than trust everything or nothing. |
| D-bu | **The startup access-boundary line and the header freshness text must describe the actual state.** The CLI publishes the effective host/port before serving; the header distinguishes "live feed" from "delayed public source — not a live feed". | A log line naming port 8710 while listening on 10000 is a lie by omission, and a header reading "no live feed" beside a strip showing today's index is confusing. Both are cheap to make true. |

---

### Session 26 (2026-10-16) — reference-driven UI overhaul

| # | Decision | Reason |
|---|---|---|
| D-bv | **Navigation becomes a grouped left sidebar, not a 13-item top bar.** Groups: Market / Discover / Portfolio / Research / Strategy / Data. | The reference terminal uses a left rail with labelled sections; a flat 13-button bar gives no hierarchy and does not scale as tools are added. Grouping keeps every existing view reachable without a mega-menu. |
| D-bw | **An investment model is runnable only when every input it needs is stored; otherwise it is disabled and names the missing fields.** | The reference indexes nine methodologies as cards. Mega Tool stores EPS, P/E, net-worth-per-share, paid-up capital and profit — *not* EBIT, EV, working capital, cash-flow or total assets. Presenting a Magic Formula or Piotroski score from absent inputs would be fabrication; disabling the card with the reason is honest and still discoverable. |
| D-bx | **Per-share inputs are bounds-checked (1 … 1e6 NPR).** A value outside the band is refused, not ranked. | The stored `net_worth_per_share` for one symbol is ~6.7e10 — a unit error (total equity stored per-share). Ranking it would have produced a P/B of 0.0 and a top-of-list nonsense pick. |
| D-by | **A growth ratio requires both endpoints positive.** | `(v_new / v_old) ** (1/years)` on a negative ratio is a *complex* number; it raised inside the endpoint (HTTP 500). A loss-to-loss "growth rate" is not a growth rate, so the correct answer is no score. |
| D-bz | **The model universe is price membership, not "symbols that have filings".** | Restricting momentum and 52-week models to fundamentals-covered names silently shrank their universe and misreported "evaluated N". Each model now reports its own coverage over all priced symbols. |
| D-ca | **Plan statuses are recorded as shipped, including what was *not* done.** | `docs/ui-redesign/IMPLEMENTATION_PLAN.md` was corrected from an optimistic draft to the true state (dashboard hero, chart overlay manager, portfolio/backtest visuals, comparators = NOT STARTED). A plan that overstates progress is worse than no plan. |

---

### Session 27 (2026-10-16) — the chart workspace is finished

| # | Decision | Reason |
|---|---|---|
| D-cb | **The chart is the hero; analysis layers are opt-in and counted.** Candles + volume by default; six layers (S/R, Fibonacci, candlestick patterns, chart patterns, Elliott, harmonic) live in an Analysis drawer, each reporting how many items it found, each persisted per symbol. | Drawing 73 detected support zones on a 6-month chart (B-66) made the chart unreadable, and a control that always draws cannot be turned off. Counting the layer means the user sees the cost of enabling it *before* enabling it, and a layer that found nothing can say so honestly ("harmonic: none"). |
| D-cc | **Overlay layers are capped (10 lines, 5 labels, nearest-price first) and the layer states its own suppression.** | A detector's value is a *candidate set*, and rendering the whole set defeats the purpose. Nearest-first uses price proximity as the relevance rule rather than an arbitrary truncation, and the layer declares that it suppressed the rest instead of hiding it silently. |
| D-cd | **Chart controls are grouped into popovers and a drawer, never a row of checkboxes.** The seven indicator controls and eight drawing controls were relocated into Indicators/Draw popovers; the rest of the analysis panels moved into a collapsed "Advanced analysis" section. | A beginner cannot read a 15-checkbox toolbar, and the reference terminal reaches depth through drawers and menus. Relocating the existing DOM nodes keeps every handler and every id, so no behaviour was rewritten — only repositioned. |
| D-ce | **A missing selector prefix is a bug worth a regression note: `$("rsi-pane")` never matched.** The panes were *silently* unavailable for the life of the feature because `addPane` returned on a null lookup. | The checkbox visibly did nothing, which reads as a broken control even though the code path never ran. Any control that can fail invisibly deserves a guard and a record. |
| D-cf | **Concurrent loads are serialised by a sequence token; only the newest draws.** | `destroyCharts()` ran before each call's `await`, so an older in-flight call's chart survived its own successor's cleanup, accumulating canvases. A token makes load monotonic without a queue, and costs one comparison per load. |
| D-cg | **A hidden container must be unhidden *before* a lightweight-charts chart is created in it.** | lightweight-charts creates no canvas for a zero-sized container, so `display:none → block` must happen first. The previous `:empty { display: none }` CSS made the pane zero-sized exactly while addPane tried to build it, which is why hiding empty panes by CSS silently broke them (B-67's symptom). |
