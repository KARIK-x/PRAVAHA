# Ranking Validation Report — T-16

**Date:** 2026-10-13
**Status:** The ranking **fails** walk-forward validation. No alternative tested passed.
**Reproduce:** `python scripts/walk_forward_report.py` · `megatool walk-forward` · `POST /api/walk-forward`

This report is the Priority-Two deliverable. Every number below was executed
against the real store (514,018 bars, 372 symbols) and is reproducible from the
commands above. No figure was tuned to improve a result: both defect fixes made
during this investigation left the outcome **unchanged or worse — never
better** — and each is recorded here rather than hidden.

---

## 1. Why the ranking failed

The default ranking weights are 50% momentum (3-month + 6-month), 20%
proximity to the 52-week high, 15% volume trend, and 15% low-volatility.
When each factor is ranked alone over Q 2018–2026, four of the five are
negative:

| Factor (alone) | Mean spread | Hit rate | Cum long | Cum bench |
|---|---:|---:|---:|---:|
| composite (default) | **−3.25%** | 40.0% | 103.41% | 200.81% |
| momentum_3m | −1.79% | 37.1% | 106.56% | 200.72% |
| momentum_6m | **−3.50%** | 34.3% | 95.70% | 198.84% |
| volume_trend | −1.84% | 45.7% | 136.50% | 200.81% |
| near_52w_high | −2.03% | 40.0% | 135.46% | 200.81% |
| volatility (low-vol) | **+0.73%** | 57.1% | 217.94% | 200.81% |

*(Q 2018–2026, tradeability gate applied and invalid rows filtered — the same
code path as §5, so the composite row matches §5 exactly.)*

**The failure is not one bad factor.** It is that the two factors carrying half
the weight (both momentum measures) were among the worst, and the remaining
price/volume factors were also negative. Over these windows NEPSE rewarded the
*opposite* of what a momentum-heavy ranking selects: the top quantile
underperformed the bottom quantile in every window tested. This is a documented
market property (short-term reversal dominates in some markets), not a bug in
the arithmetic.

## 2. Implementation defects found

Auditing the methodology against the standard checklist surfaced **two genuine
defects this session** (§2.1, §2.4), plus two corrected in the previous session
(§2.2, §2.3). Neither of this session's fixes improved the result — §2.1 made
it measurably worse, and §2.4 changed only the absolute levels by a few
hundredths of a point while leaving every conclusion intact.

### 2.1 Untradeable symbols in the universe (FIXED — `dc6cb97`)

The staleness tracking covered only the *end* price. A symbol ranked at `T`
whose last bar was months or years before `T` was still ranked:

- its momentum factor was computed over the gap (a "3-month momentum" measured
  from data ending 2+ years earlier), and
- its "forward return" was measured from that stale price to `T′` — a
  multi-year return from a price the portfolio never held.

**Measured (Q 2018–2026):** of 1,856 ranked symbol-periods, **20.3%** had a
start price older than 30 days. Gap p90 = **692 days**, p99 = 1,793 days,
max = 3,402 days (~9 years). One period was 100% stale.

This is *incorrect universe construction* plus an *unrealistic execution
assumption*: you could not have bought a suspended symbol at `T`'s close.

**Fix:** a symbol whose last bar is older than `STALE_DAYS` (30) before `T` is
excluded from that period's universe — dropped, not ranked, never in either
tail or the outcome pool. The count is surfaced in the period note. No weight,
threshold or factor direction changed: this is universe construction, not a
strategy parameter.

**Honest before/after — both sides measured with the invalid-row filter
applied, so the only difference is the gate itself:**

| Window | Before (no gate) | After (gate) | Direction |
|---|---:|---:|---|
| Q 1995–2007 | −11.80% | −11.80% | unchanged |
| Q 2008–2017 | −0.16% | **−1.04%** | worse |
| Q 2018–2026 | −2.90% | **−3.25%** | worse |
| Q 1995–2026 | −3.17% | **−3.70%** | worse |
| M 2015–2026 | −1.33% | −1.28% | marginally better |

Four of five windows got worse; the fifth improved by 0.05pp, which is
reported rather than rounded away. Hit rate fell in the same direction
(Q 2018–2026: 45.7% → 40.0%; Q 1995–2026: 41.3% → 38.0%).

Had the fix improved the result, that would have been reported with the same
prominence. Overall it did not. **The negative spread is robust to the
correction.**

### 2.2 Forward returns required an exact date match (fixed previously)

Requiring a close on the exact rebalance day silently dropped 9.5% of a
period's symbols — the suspended names, i.e. a non-random, biased subset.
Corrected to last-observation-carried-forward with staleness flagged.

### 2.3 The chance baseline used one global tail size (fixed previously)

Because the ranked universe grows over history, a single global tail size was
too large for early periods and abandoned the whole baseline for want of one
period. Corrected to each period's own tail size.

### 2.4 The report script bypassed the B-17 invalid-row filter (FIXED)

Found while reconciling two runs of the same window that disagreed
(Q 2018–2026: −3.30% vs −3.25%, hit rate 37.1% vs 40.0%). The cause was not
nondeterminism — the two paths loaded bars differently:

* `scripts/walk_forward_report.py` used raw SQL, `SELECT ... FROM price_bars`,
  with **no** `validation_status` predicate;
* every other read path goes through `get_bars`, which applies the B-17
  `_NOT_INVALID` filter.

So the *canonical reproduction tool* — the one this report, `RESEARCH_REGISTER`
D11, and the README all point at — was feeding the 124 physically impossible
rows (115 inverted high/low, 9 zero prices, including 8 fake all-time lows)
into the walk-forward, while the API and CLI excluded them.

**Fix:** `load_frames()` now imports `_NOT_INVALID` from `market_store` and
applies it in the query, so the bulk load and `get_bars` share one predicate
that cannot drift apart. Coverage/quality queries in `market_store` that
*count* invalid rows were left alone — filtering those would hide the very
thing they report.

This defect was live in every number published earlier in this session; §5 is
the corrected table. All windows remain negative.

## 3. What was corrected

| Change | Effect on result |
|---|---|
| Tradeability gate (§2.1) | **Worse** (−3.17% → −3.70% full history) |
| LOCF forward returns (§2.2) | Enabled the chance baseline; added symbols back |
| Per-period tail size (§2.3) | Chance baseline now computable for all windows |

None of the three made the ranking look better and then was presented as the
headline. The headline remains: **the ranking fails.**

## 4. Alternatives tested

Per the mission (only factors that exist in the data; no ML), six weightings
were evaluated — the default composite plus each of the five factors alone —
using the same walk-forward harness, same dates, same metrics.

### 4.1 Does low-volatility rescue it? No.

Low-vol was the only positive factor, so it was tested across the other
windows. **It is positive only in the window it was found in:**

| Window | default | low-vol |
|---|---:|---:|
| Q 1995–2007 | −11.80% | −3.58% |
| Q 2008–2017 | −1.04% | **−7.44%** |
| Q 2018–2026 | −3.25% | **+0.73%** ← selected here |
| M 2015–2026 | −1.28% | −1.12% |

Low-vol is negative in 3 of 4 windows, including **−7.44%** in 2008–2017 where
the default was only −1.04%.

### 4.2 Why this is not evidence for low-vol

**There is no untouched hold-out.** 2018–2026 was examined during factor
attribution *before* any alternative was nominated, so it cannot serve as an
out-of-sample test for a hypothesis formed on it. Testing six weightings over
five windows and reporting the best is multiple-comparisons selection; the
single positive cell is what that process produces by chance.

The honest reading: low-vol is a *candidate hypothesis* that would require
fresh out-of-sample data (a later period, or a different market) to test. It is
not a validated method and must not be presented as one.

## 5. Metrics obtained

Post-gate, **with the B-17 invalid-row filter applied** (reproduce: `python
scripts/walk_forward_report.py`):

| Window | Periods | Mean spread | Hit rate | Cum long | Cum bench | Chance p95 | Pctile |
|---|---:|---:|---:|---:|---:|---:|---:|
| Q 1995–2007 | 16 | −11.80% | 37.5% | 213.0% | 397.5% | 10.87% | 0.020 |
| Q 2008–2017 | 39 | −1.04% | 35.9% | 134.1% | 297.2% | 4.32% | 0.340 |
| Q 2018–2026 | 35 | −3.25% | 40.0% | 103.4% | 200.8% | 1.11% | 0.000 |
| Q 1995–2026 | 92 | −3.70% | 38.0% | 174.6% | 1346.5% | 3.36% | 0.010 |
| M 2015–2026 | 140 | −1.28% | 48.6% | 61.2% | 181.0% | 0.34% | 0.000 |

Determinism: two independent full runs are bit-for-bit identical except
`elapsed_seconds` wall-clock timings (verified by JSON diff).

> **Correction notice.** Numbers published earlier in this session for these
> windows were computed *before* the §2.4 loader defect was found, so they were
> contaminated by 124 invalid rows (e.g. Q 2018–2026 was reported as −3.30% and
> Q 1995–2026 as −3.71%). The table above is authoritative. The corrections are
> small and **do not change any conclusion** — every window remains negative.
>
> Separately, a figure of −0.16% for Q 2008–2017 that circulated in the first
> session is the **pre-gate** value: it remains correct as the "before" column
> of §2.1, but it is not the current number, which is −1.04%.

## 6. Did any method pass validation?

**No.**

- The default composite is negative in all five windows; the long portfolio
  underperformed the equal-weight benchmark in every window.
- The observed spread sits at or below the 5th percentile of the
  random-selection distribution in 4 of 5 windows — significantly *worse* than
  chance, not noise.
- Low-vol, the only positive factor, is positive in 1 of 4 windows and that
  window is where it was selected.

No strategy is profitable, validated, or recommended by this report. Nothing
here is a trading signal or evidence of future return.

## 7. What remains uncertain

1. **Survivorship bias.** The store holds companies still listed today;
   delisted names are missing from their own history. Every figure here is
   optimistic by an unknown amount. Not fixable without delisted-symbol data.
2. **No transaction costs.** `BacktestConfig.fee_rate` is a PLACEHOLDER
   (KNOWN_BUGS B-11); verified Nepal rates are unavailable (T-12/B-12). Gross
   only. Costs would make these results worse, not better.
3. **Price/volume factors only.** P/E, P/B, dividend yield, index-relative and
   sector-relative factors are declared unavailable and carry zero weight. This
   validates five price/volume factors and nothing else.
4. **Equal-weight, close-to-close.** Assumes every holding trades at the period
   close — now bounded by the tradeability gate, but still a simplification.
5. **No untouched hold-out** remains for any hypothesis formed during this
   investigation (§4.2).

## 8. Product honesty

The interface does not present the ranking as predictive:

- `POST /api/rank` returns: *"A ranking is a research view over past data. It
  is not a prediction, a recommendation, or a trading signal, and it does not
  indicate expected profit."*
- `POST /api/walk-forward` returns all five caveats with every result and the
  same disclaimer.
- README, RESEARCH_REGISTER (D11/D12), and this report all state the failure
  explicitly.
- Classification: **research ranking**, not validated strategy, not live
  observation. No trading is enabled.
