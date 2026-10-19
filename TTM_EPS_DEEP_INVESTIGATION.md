# TTM EPS — Deeper Investigation (Safe Implementation Planning)

**Status:** READ-ONLY. No code, tests, config, docs, or data changed.
**Date:** 2026-10-19.

---

## 1. Evidence about the reporting convention

The source (`yonepse/financials.json`) labels reports as "First/Second/Third/Fourth Quarter (Nepali FY YYYY-YYYY)" and "Annual Report (Nepali FY YYYY-YYYY)". It does **not** document whether quarterly EPS is per-quarter, cumulative (YTD), or trailing-12-month.

Empirical tests over 307 symbols / 4,343 EPS rows:

| Hypothesis | Test | Result |
|---|---|---|
| Per-quarter (sum of 4 ≈ annual) | sum(Q1..Q4) vs Annual, same FY | **3 / 324 within 5%** (median 3.73×) |
| Cumulative (Q4 ≈ annual) | Q4 vs Annual, same FY | **131 / 454 within 5%** (median 1.01×) |
| Cumulative (Q4 ≥ Q3) | Q4 vs Q3, same FY | **471 / 832 = 56.6%** |
| Trailing-12-month (Q1(FY X) ≈ Annual(FY X-1)) | Q1/prev-annual ratio | median 0.70 (not 1.0) |
| Per-quarter (Q1 ≈ annual/4) | Q1/annual ratio | median 0.82 (not 0.25) |

**Conclusion: no single convention fits.** The quarterly values are not consistently per-quarter, cumulative, or trailing-12-month. The source exposes **insufficient evidence** to distinguish the convention. Deriving individual-quarter EPS by subtraction is **not reliable** (43.4% of cases have Q4 < Q3, which contradicts cumulative; subtraction would yield negative quarter EPS in those cases).

## 2. Representative multi-company validation table

| Symbol | FY | Q1 | Q2 | Q3 | Q4 | Annual | Q4≥Q3? | sum/annual |
|---|---|---|---|---|---|---|---|---|
| NABIL | 2024-25 | 24.05 | 25.05 | 26.34 | 26.09 | 21.89 | No | 4.65× |
| NICA | 2022-23 | 60.00 | 57.00 | 47.00 | 40.00 | 38.44 | No | 5.34× |
| ACLBSL | 2024-25 | 23.44 | 17.79 | 22.27 | 25.72 | 23.98 | Yes | 3.72× |
| ADBL | 2023-24 | -28.83 | 17.73 | 17.93 | 20.62 | 19.12 | Yes | 1.44× |
| AHL | 2023-24 | -0.07 | -6.75 | -14.37 | -16.41 | -17.24 | No | 2.18× |

In every case, summing the four quarters produces a value 1.4–5.3× the annual EPS. The quarterly basis is ambiguous and inconsistent.

## 3. Count of defensible vs unavailable

- Total EPS records: 4,343 across 307 symbols.
- Cases with all 4 quarters + annual: 324.
- Cases where sum reconciles with annual (within 5%): **3 (0.9%)**.
- Cases where Q4 ≈ annual (within 5%): 131 (28.9%).
- Cases where Q4 ≥ Q3 (cumulative-consistent): 471/832 (56.6%).

**Defensible TTM EPS results: 0** under any single, verifiable convention. Every computation (sum, latest, subtraction) requires an undocumented assumption.

## 4. Smallest safe implementation proposal

Do **not** sum 4 quarterly values (demonstrably wrong). Do **not** subtract (not cumulative). Do **not** assume trailing-12-month (unverified).

Instead, modify `compute_ttm_eps` to:

1. Keep the existing period-type + fiscal-year consistency checks (already partially there).
2. Add a **reconciliation guard**: if an Annual Report EPS exists for the same fiscal year, require `abs(sum − annual) / abs(annual) < 0.15`. (This will fail for all current data, by design.)
3. When the guard fails (or no annual exists to validate), return `ttm_eps: None` with reason: `"quarterly EPS basis is not documented by the source (sum of reported quarters does not reconcile with the annual report); TTM EPS cannot be computed reliably from the available data"`.
4. Include the raw quarterly + annual records in the response (already returned as `quarters`) plus the annual figure, so users see what is available.
5. Update the frontend hint in `loadNewTtmEps()` to explain the basis issue.

**Scope:** `megatool/fundamentals.py` (`compute_ttm_eps` only), `web/static/app.js` (hint text), and new unit tests. No schema, API contract, or dependency changes. No valuation model is affected (none uses TTM EPS).

## 5. Required regression tests

1. Four valid quarterly records, same FY, sum reconciles with annual → TTM = sum (synthetic fixture with sum ≈ annual).
2. Missing quarters (only 3) → `None`, reason mentions missing quarter.
3. Cumulative YTD records (Q4 = annual) → must NOT sum; returns `None` with basis reason.
4. Annual-only records → `None`, reason "no quarterly records".
5. Mixed fiscal years → `None`, reason "mixed fiscal years".
6. Duplicate/restated records (same symbol/FY/quarter, two filing dates) → latest filing date wins; no double-count.
7. Fewer than 4 EPS rows → `None`, reason "fewer than 4 EPS records".
8. Zero EPS → `None`, reason "zero EPS in period".
9. Negative EPS → handled (sum valid but flagged).
10. Missing (null) EPS → skipped, not zero-filled.

**Not testable (blocked):** trailing-12-month basis — cannot be distinguished from the data; no test can assert it.

## 6. API/UI compatibility concerns

- `GET /api/fundamentals/{symbol}/ttm-eps` response shape is unchanged (`ttm_eps`, `reason`, `quarters_used`, `quarters`). Only the *value* changes (from a misleading number to `null`).
- Frontend `loadNewTtmEps()` already renders `—` and a caution hint for `null`. The hint text should be updated to explain the basis issue.
- No other consumer uses TTM EPS (valuation models use point-in-time EPS).
- No database or API contract change.

## 7. Status labels

- Current `compute_ttm_eps`: **TESTED-FAIL** (verified to produce misleading values).
- Proposed fix: **NOT-IMPLEMENTED** (awaiting approval).
- Data basis documentation: **BLOCKED** (source does not document it).
- Post-fix TTM availability: **NOT-VERIFIED** (would become available only if a source documents the quarterly basis, or if a reconciling subset is found).

**STOP.** No code, tests, config, documentation, or data was changed. Awaiting approval before implementing.
MD
echo "written"; wc -l TTM_EPS_DEEP_INVESTIGATION.md