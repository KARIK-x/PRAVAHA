# NF-015 — Evidence-Bound AI Research Desk

**Module:** `megatool/research_desk.py`
**API:** `/api/research-desk/{evidence,run,review,history}`
**UI:** KIMI → **AI Research** tab
**Tables:** `research_runs` (schema v10)
**Tests:** `tests/test_research_desk.py` (15)
**Date:** 2026-10-19

---

## 1. The rule

The research desk answers a question **only from evidence it has actually assembled
from the store**, and it refuses to substitute general knowledge for that evidence. If a
model provider is unavailable, it says so explicitly and the evidence + review tooling
still works. It never places a trade and never modifies the portfolio ledger.

---

## 2. Evidence bundle (real, per symbol)

`GET /api/research-desk/evidence?symbol=NABIL` returned **15 items, 0 missing**:

```
kind         label                                  value                     source
fact         Latest stored close                    546.0 NPR                 price_bars
fact         Stored bars                            3517 bars                 price_bars
fact         History range                          2011-05-15..2026-10-15    price_bars
fact         Price source                           github.com/Aabishkar2/…   price_bars
fact         Adjustment status                      unadjusted                price_bars
calculation  Price-row validation                   17 suspect / 3517 rows    megatool.quality
calculation  Technical rating (bearish)             25.0 0-100                megatool.catalog
calculation  Volatility percentile                  81.35 %                   megatool.catalog
fact         Fundamental: eps                       28.36 NPR                 yonepse/…
fact         Fundamental: pe                        18.86 ratio               yonepse/…
fact         Fundamental: paid_up_capital           27056996729.0 NPR         yonepse/…
fact         Fundamental: profit                    7905796000.0 NPR          yonepse/…
fact         Fundamental: net_worth_per_share       247.28 NPR                yonepse/…
fact         Fundamental records                    95 records                fundamentals
… (15 total)
```

Every item carries `source`, `calculation`, `dataset`, `quality` and `as_of`/limitations
where relevant. A value that cannot be produced is a **`missing`** entry with a reason —
never a zero and never a silent `None`.

### Defect found and fixed during this audit

The bundle previously read a key (`rating`) that the technical-rating engine does not
return, producing `Technical rating = None` — which reads like a genuine measurement of
nothing. The extraction now maps each engine's real headline key explicitly
(`technical_rating → score`, `volatility_percentile → percentile`) and, if a key is
absent, emits a `missing` entry instead. It now shows
`Technical rating (bearish) = 25.0 0-100`.

---

## 3. Run with no provider (the honest default)

`POST /api/research-desk/run {"question":"Is NABIL expensive?","symbol":"NABIL"}`:

```
available : false
error     : No AI provider is configured…
review    : verdict + checks (rule-based, still produced)
```

* The **error is explicit** — no fabricated narrative, no general-knowledge answer.
* The evidence bundle and the rule-based review are still returned, so the desk is useful
  without a model.
* A provider is only called when one is configured; provider success, failure, empty
  response and timeout paths are each tested.

---

## 4. Skeptical review (rule-based)

The review parses the model text (when present) and structurally checks it against the
evidence:

| Check | What it catches |
|---|---|
| unmatched numbers | a number in the text that appears nowhere in the evidence |
| overclaim | certainty/absolutes ("guaranteed", "certainly") not supported by inputs |
| causal claim | causal language the evidence cannot support |
| unsupported claim | assertions with no corresponding evidence item |
| structural risk | missing/limited inputs, unadjusted prices, single-source fundamentals |

The review runs even with no model, over the bundle alone.

---

## 5. Safety

* A test asserts **no portfolio/order code path is reachable** from the module — the desk
  cannot place a trade or edit the ledger.
* Persistence is to `research_runs` (evidence + model text only; **never a key**). A
  persistence failure is surfaced as `persist_error` rather than swallowed, so a run is
  never silently lost.
* `GET /api/research-desk/history` re-opens past questions.

---

## 6. Verification

* **Unit:** `tests/test_research_desk.py` — 15 tests: real evidence present, missing
  inputs reported, unadjusted limitation surfaced, review flags (unmatched numbers,
  overclaim, causal), structural-risk checks, provider unavailable/success/failure/empty,
  unsupported claims, no-portfolio-code assertion, persistence. **PASS.**
* **API:** `tests/test_phase_api.py`. **PASS.**
* **Browser (dev :10000):** AI Research tab shows an explicit
  "AI unavailable: No AI provider is configured…" message **and** the evidence bundle.
  **PASS.**

---

## 7. Limitations

* Without a configured provider there is **no AI-written analysis** — only evidence and a
  rule-based review. This is intentional; the alternative would be fabricated analysis.
* The rule-based review catches structural red flags, not every factual error.
* Evidence depth is bounded by the data that exists: single-source fundamentals,
  unadjusted prices, daily granularity, no intraday.
* The desk is decision **support**, not advice, and it never trades.
