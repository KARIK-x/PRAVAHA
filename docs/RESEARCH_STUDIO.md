# Research Studio, report jobs and the range forecast

This document describes the three features added on 2026-10-20:

1. the **Research Studio** in the Research tab (multi-symbol reports);
2. the **background job** lifecycle behind it;
3. the **next-session range forecast** and risk-budget sizing.

It also records the guarantees the code enforces, so a future change can be
checked against them instead of against a screenshot.

Nothing here places an order, predicts direction, or fills a missing number with
an estimate.

---

## 1. Research Studio

### Selection model

A report is a list of **component ids** from the single registry in
`megatool/report_builder.py` (200 components, 16 categories A–P). The Research
Studio exposes every **public** category:

| Category | Examples |
|---|---|
| A Company information | profile, coverage, data quality |
| B Market information | price summary, market cap, 52-week range |
| C Fundamentals | EPS, net worth/share, revenue, profit, ROE/ROA, P/E, P/B |
| D Quarterly | Q1–Q4 results, YoY/sequential growth, comparability |
| E Valuation | P/E and P/B bands, dividend yield, valuation limits |
| F Eligibility | eligibility result and failed criteria |
| G Sector | sector overview, outliers |
| H Comparison | cross-symbol comparison (single-symbol jobs omit it) |
| I Technical | trend, moving averages, RSI, MACD, levels, patterns, MTF |
| J Dividends | history, cash, bonus, consistency |
| M Risk | volatility, drawdown, distribution, downside, gaps, liquidity |
| N Charts | price, volume, EPS/profit/revenue trends, dividends, risk, technical |
| O Data quality | sources, freshness, coverage, missing data, formulas |
| P Custom notes | user notes |

Categories **K (journal)** and **L (portfolio)** are private. They are removed
from the catalog for a non-owner client, stripped from any non-owner request
server-side, and never included in a research job. A caller cannot obtain them
by guessing a component id.

Five presets are provided: `snapshot` (17), `fundamental` (46), `technical` (35),
`risk` (19) and `full` (80). The user can also tick any combination manually.

Bounds are enforced on the **raw** request before de-duplication:
`MAX_RESEARCH_SYMBOLS = 25`, `MAX_RESEARCH_COMPONENTS = 80`.

### Outputs

| Artifact | Contents |
|---|---|
| `research-report.pdf` | cover, every selected symbol and section, real chart images, unavailable analyses with reasons |
| `research-report.xlsx` | single symbol: one sheet per component; many symbols: one sheet per component with a `Symbol` column; native Excel charts; `Report` and `Unavailable` sheets |
| `research-report.json` | the assembled bundle |
| `research-package.zip` | README, combined PDF/XLSX/JSON, a ZIP of one CSV per component per symbol, and `<SYMBOL>/<SYMBOL>-research.{xlsx,pdf}` |
| `research-data.zip` | inside the package: CSVs + `_manifest.txt` + `_unavailable.csv` |

Guarantees:

* an unselected section is **never computed** and **never appears** in any file;
* a selected section with no data appears as **unavailable with its real
  reason** — never as zero, blank, or a substitute;
* charts are drawn only from the rows the compute hook returned;
* prices are labelled end-of-day, never as live quotes.

The PDF writer (`megatool/pdfwriter.py`) is dependency-free. Text pages are
positioned with absolute `Tm` matrices; images are `FlateDecode` `DeviceRGB`
XObjects produced by `megatool/chartimg.py`. PNGs for XLSX are encoded with the
standard library (`zlib` + `struct`), so no plotting library is required.

### API

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/baba/research/catalog` | categories, components, presets |
| `POST` | `/api/baba/research/jobs` | start a build; returns the job |
| `GET` | `/api/baba/research/jobs` | recent builds (refresh/resume) |
| `GET` | `/api/baba/research/jobs/{id}` | status, progress, stage, artifacts |
| `GET` | `/api/baba/research/jobs/{id}/download/{fmt}` | `pdf`, `xlsx`, `json` or `zip` |

The start body is:

```json
{
  "symbols": ["NABIL", "SCB"],
  "preset": "full",
  "components": null,
  "risk_budget": 5000,
  "capital": 200000,
  "title": "Research report: NABIL, SCB",
  "notes": null
}
```

If `components` is present it wins; otherwise `preset` is expanded. Unknown
component ids and invalid symbols are rejected with HTTP 400.

Downloads send `Cache-Control: no-store, no-cache, must-revalidate, private`,
`Pragma: no-cache` and `X-Content-Type-Options: nosniff`. They are not cacheable
at the edge.

### Progress semantics

Progress is **completed steps / total steps**, never elapsed time:

```
steps = symbols × 3 + 4
        1 per symbol assembled
        2 per symbol (workbook, then PDF)
        + combined PDF, combined XLSX, JSON, ZIP
```

The job record stores `steps_done`, `steps_total`, `stage`, a human message and
the derived `progress`. A symbol that fails is reported in
`quality.missing_symbols`; the other symbols still complete. If no symbol can be
assembled, the job fails with the collected reasons.

Jobs are persisted as JSON under `data/jobs/`. `GET /api/baba/research/jobs`
therefore survives a page refresh. If the server stops while a job is RUNNING,
the next process marks it **INTERRUPTED** and says its partial output was
discarded — it is never shown as still running.

Artifacts live under `data/exports/research/<job-id>/`. Download resolution
requires the id to be exactly 32 hex characters and the file to be inside that
job's directory, so a traversal or a hand-written filename is refused.

Job records and exports are swept after 48 hours (or when more than 40 jobs
exist).

---

## 2. Range forecast (`megatool/volatility.py`)

### What is forecast

The **size of the next stored session's high-low range**, not its direction and
not a price. All inputs are available at the prior close.

### Models

| Name | Definition |
|---|---|
| `naive` | previous session's high-low range (the baseline) |
| `ewma_tr` | EWMA of true range, λ = 0.94 |
| `har` | ridge-stabilised OLS of `log(range[t])` on the previous 1, 5 and 22 session log ranges (Corsi, 2009), re-fitted at every origin |
| `blend` | mean of `ewma_tr` and `har` |

### Evaluation

Expanding-origin, one-step-ahead, strictly chronological. For target session
`t`, every model sees bars `0..t-1` only. There is no shuffle, no random split
and no future bar in a feature.

Reported for each model: observations, MAE, RMSE, median absolute percentage
error, mean APE, improvement vs naive, and **measured 80% interval coverage**.
Each model's band is calibrated from *its own* previous out-of-sample
prediction/actual ratios (10th–90th percentile), so the coverage number is not
inflated by fitting the band on the same observations it is scored on.

If no model beats naive, the result says so. No figure from another market is
copied in.

### Sizing

`position_sizing(price, risk_budget, expected_range, stop_multiple, capital)`
computes:

```
stop_distance = stop_multiple × expected_range
shares        = floor(risk_budget / stop_distance)
notional      = shares × price
max_loss      = shares × stop_distance
```

with an optional cap at `capital × max_position_percent`. Four rows are shown:
0.5×, 1×, 1.5× and 2× the expected range. The note states that NEPSE board lots
must be rounded down before an order is entered. **No order is created.**

API: `GET /api/baba/volatility/{symbol}?risk_budget=5000&capital=200000`.

Example on real stored NABIL bars (2026-10-20, 2,961 bars):

| Model | MAE (points) | Improvement vs naive | 80% coverage |
|---|---|---|---|
| naive | 18.68 | — | — |
| ewma_tr | 16.43 | 12.0% | — |
| **har** | **14.59** | **21.9%** | **83.4%** |
| blend | 15.07 | 19.3% | — |

---

## 3. Cloudflare edge and YONEPSE

The Worker at <https://pravaha-edge.aadarshakarki.workers.dev> serves the same
static frontend and proxies `/api/*` to Render. A `*/10` cron performs two
independent jobs:

1. refresh the public YONEPSE JSON (inside Mon–Fri 11:00–16:00 NPT only);
2. ping `ORIGIN_URL/api/health` with a 60-second budget to prevent Render Free's
   ~15-minute idle spin-down.

The refresh validates every payload, keeps the **last good snapshot** on
failure, separates `source_updated_at` from `retrieved_at`, records consecutive
failures, and never converts the LTP board into OHLCV.

The Data tab's **Scheduled ingestion** card shows last check, last success,
consecutive failures, source freshness and the run count. See
`pravaha-edge/README.md` for deployment and rollback.

---

## 4. Verification

```bash
# Python
.venv/bin/python -m pytest tests/test_research_studio.py tests/test_report_builder.py -q
.venv/bin/python -m pytest -q                     # 3,191 passed, 43 skipped

# Worker
cd pravaha-edge && npx vitest run                 # 92 passed

# Browser (needs a live dev server on :10000)
MEGATOOL_BROWSER_TESTS=1 MEGATOOL_BROWSER_BASE=http://127.0.0.1:10000/ \
  .venv/bin/python -m pytest tests/test_browser_*.py -q
```

Known pre-existing browser failures (not introduced here): two in
`test_browser_draw_drag.py` (missing `state.panEnabled` in `web/static`) and two
in `test_browser_search_destinations.py` (`mfi_oversold` preset absent). They
are unrelated to the Research Studio and remain unfixed.
