# TTM EPS — Read-Only Investigation Report

**Status:** READ-ONLY investigation (no code, tests, config, docs, or data changed).
**Date:** 2026-10-19 · **Source:** `yonepse/financials.json` → `megatool_state.sqlite` (`fundamentals` table).

---

## 1. Files and functions inspected

- `megatool/fundamentals.py` — `compute_ttm_eps()` (line 1014), `compute_eps_growth()` (1051), `_num()` (1115), `FundamentalRecord`, `records_from_rows()`, `_refuse_*` guards.
- `megatool/api.py` — `fundamentals_ttm_eps()` route `GET /api/fundamentals/{symbol}/ttm-eps` (line 2477).
- `web/static/app.js` — `loadNewTtmEps()` (line 13815), frontend consumer of `/ttm-eps`.
- `megatool/datasources/yonepse.py` — `financials_to_fundamental_rows()` (line 659), `_FINANCIAL_FIELDS` (line 424), `_filed_at()`, `_filing_values()`, `recover_filing_dates()`, `_fiscal_period_end()`.
- `megatool/sastoshare.py` — `_is_annual_label()` (line 230) — the convention used elsewhere for annual vs quarterly.
- `PRAVAHA_PHASE0_INSPECTION.md` §8 (prior defect note).
- SQLite schema + live data in `data/dev/release/processed/megatool_state.sqlite` (read-only).

## 2. Actual source-data format and evidence

### Schema
`fundamentals(symbol, field, value, unit, period_end, period_label, source, source_ref, retrieved_at, verification, notes)`,
`UNIQUE(symbol, field, period_end, source)`. `period_end` = filing/publication date (not the fiscal period end). `period_label` = source's own words, e.g. `"Fourth Quarter 2022-2023 (Nepali FY 2022-2023)"`, `"Annual Report (Nepali FY 2022-2023)"`.

### Source labelling (from `yonepse/financials.json`)
Each report carries `type` ("Annual Report" or a quarter name), `quarter` ("First/Second/Third/Fourth Quarter" or null), `fy` ("2022-2023"). `financials_to_fundamental_rows` builds `period_label = "{quarter} {fy} (Nepali FY {fy})"` or `"Annual Report (Nepali FY {fy})"`. No field documents whether a quarterly EPS is per-quarter, cumulative (YTD), or trailing-12-month.

### Empirical basis check (read-only SQL over 307 symbols / 4,343 EPS rows)

| Hypothesis | Test | Result |
|---|---|---|
| Quarterly EPS is per-quarter (sum of 4 quarters ≈ annual) | sum(Q1..Q4) vs Annual, same FY | **3 / 324 cases within 5%** (median ratio sum/annual = 3.73) |
| Quarterly EPS is cumulative (Q4 ≈ annual) | Q4 vs Annual, same FY | **131 / 454 cases within 5%** |
| Quarterly EPS is trailing-12-month | not directly testable from the data | plausible but undocumented |

**Conclusion: neither "per-quarter" nor "cumulative" is supported by the data.** The quarterly EPS values' basis is **undocumented by the source**. Summing 4 quarterly values is therefore not grounded in evidence.

### Gap analysis of `compute_ttm_eps`
- Selects the 4 most recent EPS rows by `period_end DESC`.
- Dedupes by `period_end`.
- Checks gap days 60–120 between consecutive periods.
- **Does NOT check `period_label` / period type** — it never verifies the records are quarterly, let alone from the same fiscal year.
- Sums the 4 values and returns `ttm_eps`.
- The frontend hint says "TTM EPS requires 4 consecutive quarterly EPS records from the same fiscal year" — but the code does not enforce "same fiscal year" or "quarterly".

### Additional defects in the current implementation
1. **No period-type verification** — annual and quarterly rows are mixed in one column; a symbol with 4 annual reports in a row would be summed as if quarterly.
2. **No fiscal-year consistency check** — "First Quarter 2023-2024" and "Fourth Quarter 2022-2023" could both be selected if their filing dates are the 4 most recent.
3. **No duplicate/restatement handling beyond `period_end` dedupe** — the `UNIQUE(symbol, field, period_end, source)` key means a restated figure with the same filing date overwrites; a restatement with a new filing date creates a second row, and the `seen_periods` set dedupes by `period_end` only, so a restated value with a different filing date for the same period could be double-counted.
4. **No negative/zero handling beyond arithmetic** — negative EPS summed is arithmetically fine but economically meaningless as a "trailing" figure; zero EPS produces a TTM of 0 with reason "ok".

## 3. Root cause and reproducible example

**Root cause:** `compute_ttm_eps` assumes the 4 most recent EPS records are per-quarter, independent, same-fiscal-year values and sums them. The source data does not support this assumption: summing 4 quarters does not reconcile with the annual report in 321/324 cases (median ratio 3.73×). The function can therefore return a TTM EPS that is ~3–4× the actual annual EPS, or negative, or composed of mixed fiscal years.

**Reproducible example (verified, not fabricated):**
- Symbol `NABIL`, `compute_ttm_eps` selects the 4 most recent EPS rows by filing date: 2026-08-06 (Q4 FY2025-2026, 28.36), 2026-04-28 (Q3, 33.02), 2026-01-29 (Q2, 35.04), 2025-11-06 (Q1, 25.49). Sum = 121.91. The annual report for FY2025-2026 does not yet exist in the data, but the prior annual (FY2024-2025) = 21.89. Even for FY2024-2025: Qs 24.05+25.05+26.34+26.09 = 101.53 vs annual 21.89 (4.6×). The reported "TTM EPS" of ~101 is not a plausible trailing-12-month earnings figure.

This is a verified finding from the live database, not a hypothetical.

## 4. Proposed minimal fix (NOT implemented — awaiting approval)

**Recommended approach:** Make `compute_ttm_eps` honest about what it can and cannot do.

Option A (recommended, smallest safe change):
1. Add a period-type check: only consider rows whose `period_label` indicates a quarterly report (using the same convention as `_is_annual_label` in `sastoshare.py`, inverted — i.e. a label containing "Quarter" and not "Annual Report").
2. Require the 4 quarters to belong to the **same fiscal year** (extract "Nepali FY YYYY-YYYY" from the label and require all 4 to match).
3. Add a **reconciliation guard**: if an Annual Report EPS exists for that fiscal year, require `abs(sum - annual) / abs(annual) < 0.15` (15% tolerance for audit adjustments). If it fails, return `ttm_eps: None` with reason `"quarterly EPS does not reconcile with the annual report (sum=X, annual=Y); basis may be cumulative or trailing-12-month, not per-quarter"`.
4. Return the selected quarterly records in the response (already done) plus the annual figure for transparency.
5. Handle restatements: dedupe by `(symbol, fiscal_year, quarter)` keeping the latest `period_end` (filing date), so a restated figure with a newer filing date replaces the older one.

Given the data (0.9% reconciliation rate), this would make TTM EPS **unavailable for essentially all symbols** — which is the honest answer. The frontend already renders `—` and a caution hint for `null`, so no UI breakage.

Option B (more conservative): skip the reconciliation guard and simply return `ttm_eps: None` with reason `"quarterly EPS basis is not documented by the source; cannot verify per-quarter vs cumulative vs trailing-12-month"` for all symbols, since no case reconciles. This is the most defensible but removes the feature entirely.

**Affected consumers:**
- `GET /api/fundamentals/{symbol}/ttm-eps` — response shape unchanged (`ttm_eps`, `reason`, `quarters_used`, `quarters`), but `ttm_eps` would be `None` for all current data.
- Frontend `loadNewTtmEps()` — already handles `null` with a caution hint; the hint text should be updated to explain the basis issue.
- No valuation model uses TTM EPS (Graham number uses point-in-time EPS), so no cascade.

**No database schema change. No API contract change. No new dependencies.**

## 5. Regression-test plan

Tests to add (unit, using in-memory SQLite fixtures — no network):

1. **Four valid quarterly EPS records** — same FY, 4 quarters, sum reconciles with annual → TTM = sum. (Supported by schema; needs a synthetic fixture where sum ≈ annual.)
2. **Missing quarters** — only 3 quarters → `ttm_eps: None`, reason mentions missing quarter.
3. **Cumulative year-to-date EPS** — 4 "quarterly" rows where values are cumulative (Q4 = annual) → must NOT sum; return None with basis reason. (Supported: the real data behaves this way; the test fixture mimics it.)
4. **Annual-only EPS** — 4 annual reports, no quarters → `ttm_eps: None`, reason "no quarterly records".
5. **Mixed reporting periods** — quarters from two different fiscal years → `ttm_eps: None`, reason "mixed fiscal years".
6. **Duplicate periods / restatements** — same (symbol, FY, quarter) with two filing dates → use the latest filing date; verify the older value is not double-counted.
7. **Insufficient source data** — fewer than 4 EPS rows → `ttm_eps: None`, reason "fewer than 4 EPS records".
8. **Zero / negative / missing EPS values** — zero EPS → reason "zero EPS in period, TTM not meaningful"; negative → handled (sum is arithmetically valid but flagged); missing (null) → skipped, not zero-filled.

**Cases NOT supported by the schema/source and therefore not tested:**
- "Trailing-12-month" quarterly EPS cannot be distinguished from per-quarter without documentation; no test can assert it.
- Restatement semantics are not documented by the source; the "latest filing date wins" rule is our convention, not the source's.

## 6. Remaining uncertainties and risks

- **The quarterly EPS basis is undocumented.** We cannot determine from the data whether values are per-quarter, cumulative, or trailing-12-month. Any TTM computation is therefore an assumption. The proposed fix makes this explicit rather than silent.
- **The reconciliation tolerance (15%) is a judgment call.** Audit adjustments between quarterly and annual reports are real but unquantified in this dataset. 3/324 cases reconcile within 5%; the tolerance could be widened, but that risks accepting non-per-quarter data.
- **Frontend hint text** says "TTM EPS requires 4 consecutive quarterly EPS records from the same fiscal year" — accurate as a requirement, but should also explain the reconciliation failure reason.
- **No existing tests** cover `compute_ttm_eps`, so the change cannot regress a test. New tests (per §5) should be added as part of the implementation.
- **Risk of over-correction:** if the source's quarterly values ARE per-quarter for some symbols (3 cases) but not others, the fix would correctly compute TTM for those 3 and return None for the rest. That's the honest outcome.

## 7. Status labels

- `compute_ttm_eps` current behavior: **TESTED-FAIL** (verified to produce misleading values; no test exists, but empirically wrong).
- Proposed fix: **NOT-IMPLEMENTED** (awaiting approval).
- Data basis documentation: **BLOCKED** (source does not document it; cannot be resolved from available evidence).
- TTM EPS availability after fix: **NOT-VERIFIED** (would become available only if/when a source documents the quarterly basis).

**STOP.** No code, tests, config, documentation, or data was changed. Awaiting approval before implementing.
MD
echo "written"; wc -l TTM_EPS_INVESTIGATION.md