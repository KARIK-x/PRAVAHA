# PHASES 2–6 PROGRESS — Mega Tool (NEPSE quantitative research platform)

> **Append-only record.** New checkpoints are appended; earlier evidence is never
> erased. Status labels are the directive's: `IMPLEMENTED`, `TESTED-PASS`,
> `TESTED-FAIL`, `PARTIAL`, `NOT STARTED`, `BLOCKED`.
>
> Run context: autonomous Phase 2–6 implementation run, 2026-10-15, project root
> `/Users/ashim/Downloads/AI trading NEPSE`, branch `main`, HEAD `b6c3659`.
> Every number below is from a command that was actually executed this session.

---

## 0. Preflight (executed)

| Step | Result |
|---|---|
| Project root confirmed | `/Users/ashim/Downloads/AI trading NEPSE` |
| Git tree | branch `main`, HEAD `b6c3659`, **0 staged, 0 stashes**, nothing committed/pushed |
| Source PDFs located | `The Phases COMPLETE !.pdf` (51 pp) and `ALL THE CONTENT:IDEA MAIN OVERVIEW OF PROJECT.pdf` (104 pp) |
| Extraction tooling | `pdftotext`/`mutool`/`qpdf` absent; PyMuPDF (`fitz`) present. Both PDFs extracted **read-only** to a temp dir (originals untouched). |
| Reference platforms | 15 URLs fetched; results in §5 |
| Dev/prod boundary | production DuckDB + SQLite identified; **not touched**. Isolated data written under `data/dev/` (now git-ignored) and temp dirs only. |
| Collector gate | `MEGATOOL_NEPSE_API_AUTHORIZED` **unset** throughout; the gated NEPSE client issued **zero** network requests. |

`The Phases COMPLETE !.pdf` is the master directive / milestone plan (it matches
the run's directive text). `ALL THE CONTENT:IDEA MAIN OVERVIEW OF PROJECT.pdf`
is the full product specification (38 numbered sections + 12 core features +
final vision). Both were read and are treated as source of truth.

---

## 1. Executive status

**Overall:** Phase 2–6 work was executed against an already-substantial Phase 1
codebase. The scan found the 12 core features largely present; two genuine
specification gaps were closed with new, tested vertical slices, plus a scanner
capability gap.

**Completed this session (with evidence):**

1. **Classical chart-pattern recognition** (spec §6 / directive §5.3) — new
   `megatool/ta/patterns.py`, `GET /api/bars/{symbol}/patterns`, charts-view
   panel, 14 unit tests + 3 API tests.
2. **Advanced statistical analysis** (spec §16, §18.1) — new `megatool/stats.py`,
   `GET /api/bars/{symbol}/statistics`, `GET /api/stats/correlation`,
   charts-view panels, 18 unit tests + 6 API tests.
3. **Scanner presets & metrics** (spec §2 / directive §9.2) — presets 4 → 23 and
   18 new/derived single-symbol metrics; existing scanner tests extended.
4. **Reference-platform audit** — all 15 platforms fetched and classified (§5).
5. **Performance measurement** — isolated harness `scripts/perf_smoke.py` with
   p50/p95 (§7).
6. **Durable docs** — this file, regenerated `docs/API_ROUTE_INVENTORY.md`,
   updated `MEGA_TOOL_FEATURE_STATUS.md`.

**Test evidence:** full suite `1999 passed / 0 failed / 0 errors / 0 skipped`
(junitxml, 32.2 s). `ruff check .` clean; `ruff format --check .` 203 files
already formatted. Route inventory: **75 routes**, every route test-referenced.

4. **Indicator library expanded 28 → 46** (spec §3). New `megatool/ta/other.py`
   plus `vwma/dema/tema/kama/parabolic_sar` (trend),
   `stochastic_rsi/ppo/cmo/tsi` (momentum), `cmf/chaikin_oscillator/volume_roc`
   (volume). Every new indicator is covered by the *existing* dynamic look-ahead
   and warm-up harness **and** by a new engine-free literal reference test.

**Defect found and fixed by new tests (B-45):** `kama` computed its volatility
sum over a `period`-bar window (`period - 1` changes) instead of `period`
changes, silently dropping the most recent price change and understating
volatility. Found by a literal independent reference, not by the engine agreeing
with itself; fixed and covered. All other new indicators matched their
references to 1e-9 on the first run.

**Blocked (external, unchanged):** official NEPSE API authorization; TMS
read-only source; live intraday-freshness observation; YONEPSE production
apply; friend deployment (needs real token/origin). None of these block the
local application.

---

## 2. Requirements traceability

### 2.1 The Phases (milestone plan)

| Milestone | Objective | Status | Where |
|---|---|---|---|
| M0 | Foundation, source audit, isolation, test harness | **TESTED-PASS** | isolated `data/dev/`; full suite; existing indicator engine already present |
| M1 | Dashboard, stock workspace, interactive charts | **PARTIAL (verified backend, browser NOT-TESTED)** | `/api/dashboard`, charts view, `/api/bars/*` |
| M2 | Advanced TA, scanner, factors, market context | **PARTIAL → improved** | `ta/` + new `ta/patterns.py`; scanner 23 presets; `/api/rank`; `/api/regime` |
| M3 | Journal, portfolio, planner, alerts, financial analysis, AI research | **IMPLEMENTED (mostly TESTED-PASS)** | `journal.py`, `portfolio.py`, `planning.py`, `alerts.py`, `fundamentals.py`, `research.py`, `agent.py` |
| M4 | Full backtesting engine & research workbench | **IMPLEMENTED + TESTED-PASS** | `backtest.py`, `walkforward.py`, `workspace.py` |
| M5 | Integration, UI/UX, security, performance, deployment prep | **PARTIAL** | see §3, §4, §6, §7, §8 |

### 2.2 The overview spec (38 sections) — capability map

| Spec § | Requirement | Implementation | Status |
|---|---|---|---|
| 1 | Vision/objectives | whole app | TESTED-PASS (structural) |
| 2 | Dashboard design | `/api/dashboard`, overview view | IMPLEMENTED |
| 3 | Technical indicators library | `megatool/ta/` (28 registered indicators) | TESTED-PASS |
| 4 | Elliott Wave | `ta/elliott.py`, `/api/bars/{symbol}/elliott` | PARTIAL (heuristic, by design) |
| 5 | Fibonacci | `ta/fibonacci.py`, `/api/bars/{symbol}/fibonacci` | TESTED-PASS |
| 6 | Chart-pattern recognition | **`ta/patterns.py` (new)**, `/api/bars/{symbol}/patterns` | **TESTED-PASS** |
| 7 | Harmonic patterns | `ta/harmonic.py`, `/api/bars/{symbol}/harmonic` | IMPLEMENTED |
| 8 | Candlestick analysis | `ta/candles.py` | TESTED-PASS |
| 9 | Price action & structure | `ta/swings.py`, `/api/bars/{symbol}/structure` | TESTED-PASS |
| 10 | Trend analysis | `ta/trend.py` | TESTED-PASS |
| 11 | Momentum analysis | `ta/momentum.py` | TESTED-PASS |
| 12 | Volatility analysis | `ta/volatility.py` | TESTED-PASS |
| 13 | Volume analysis | `ta/volume.py` | TESTED-PASS |
| 14 | Support/resistance | `ta/levels.py`, `/api/bars/{symbol}/levels` | TESTED-PASS |
| 15 | Multi-timeframe | `ta/multitimeframe*.py`, weekly/monthly endpoints | TESTED-PASS |
| 16 | **Advanced statistical analysis** | **`megatool/stats.py` (new)**, 2 endpoints | **TESTED-PASS** |
| 17 | Market regime | `regime.py`, `/api/regime`, `/api/regime/history` | IMPLEMENTED |
| 18 | Correlation & relative strength | **`stats.py` correlation matrix (new)** + `ranking.relative_strength` | **TESTED-PASS** |
| 19 | Quantitative factor analysis | `ranking.py`, `/api/rank` | TESTED-PASS (validation: failed — documented honestly) |
| 20 | Strategy research/validation | `backtest.py`, `walkforward.py` | TESTED-PASS |
| 21 | Risk analysis | `risk.py`, `/api/portfolio/risk` | IMPLEMENTED |
| 22 | Trade planning | `planning.py`, `/api/planning`, `/api/planning/grade` | IMPLEMENTED |
| 23 | Fundamental analysis | `fundamentals.py`, `/api/fundamentals/*` | IMPLEMENTED (source-limited) |
| 24 | News & corporate events | `news.py`, `corporate_actions.py`, `/api/news/*` | IMPLEMENTED (source BLOCKED) |
| 25 | Portfolio intelligence | `portfolio.py`, `/api/portfolio*` | TESTED-PASS |
| 26 | Custom analysis from handwritten notes | `written_pdf.py`, `written_reference.py`, `/api/written-pdf/*` | PARTIAL (source-limited) |
| 27 | Automated research report | `research.py`, `workspace.py`, `/api/research/*` | IMPLEMENTED |
| 28 | Engine/dashboard integration | `api.py` (75 routes), `web/static/` | IMPLEMENTED |
| 29 | Visualization requirements | `web/static/app.js`, Lightweight-charts | PARTIAL (browser NOT-TESTED) |
| 30 | Optimization & performance | §7 | PARTIAL (measured, one bottleneck) |
| 31 | Data quality & trust | `quality.py`, `/api/quality`, freshness labels | TESTED-PASS |
| 32 | Confidence/validation labels | throughout (FACT/CALCULATED/HEURISTIC labels) | IMPLEMENTED |
| 33 | Analysis combinations | workspace modules | IMPLEMENTED |
| 34 | UX & ease of use | nav/views/empty+error states | PARTIAL (browser NOT-TESTED) |
| 35 | Implementation priorities | this file | TESTED-PASS |
| 36 | Acceptance criteria | §2.1, §3 | PARTIAL |
| 37 | Master feature checklist | §2.3 | PARTIAL |
| 38 | Final product requirement | whole app | PARTIAL |

**§3 Indicator library — the 46 registered indicators (spec §3.1–§3.6):**

| Family | Indicators |
|---|---|
| trend (13) | sma, ema, wma, **vwma**, hma, **dema**, **tema**, **kama**, **parabolic_sar**, adx, aroon, ichimoku, supertrend |
| momentum (12) | rsi, stochastic, **stochastic_rsi**, macd, **ppo**, roc, momentum, williams_r, cci, **cmo**, **tsi**, trix |
| volatility (6) | atr, bollinger, donchian, keltner, true_range, historical_volatility |
| volume (9) | obv, ad_line, **cmf**, **chaikin_oscillator**, **volume_roc**, mfi, volume_sma, relative_volume, vwap_bands |
| other (6) | **typical_price**, **median_price**, **weighted_close**, **standard_deviation**, **zscore**, **pivot_points** |

Bold = added this session. Session VWAP is still deliberately not computed:
NEPSE history is daily, so `vwap_bands` is labelled a rolling approximation.

### 2.3 The 12 core features

| # | Core feature | Implementation | Status |
|---|---|---|---|
| 1 | Market Dashboard | `/api/dashboard`, overview view | IMPLEMENTED |
| 2 | Advanced Charting & TA | `ta/*` incl. new `patterns.py`; charts view | IMPLEMENTED (overlays); browser NOT-TESTED |
| 3 | Whole-Market Scanner | `scanner.py` (23 presets, 33 metrics), `/api/screen`, `/api/rank` | **TESTED-PASS** |
| 4 | AI-Assisted Stock Research | `research.py`, `llm.py`, `/api/research/*` | IMPLEMENTED (deterministic core; provider optional) |
| 5 | Floor-Sheet Intelligence | `floorsheet.py`, `/api/floorsheet/*` | IMPLEMENTED (data-limited) |
| 6 | Fundamental Analysis | `fundamentals.py`, `/api/fundamentals/*` | IMPLEMENTED (data-limited) |
| 7 | News/Events/Corporate actions | `news.py`, `corporate_actions.py` | IMPLEMENTED (source BLOCKED) |
| 8 | Prediction & Forecasting Lab | `forecast.py`, `/api/forecast/*` | TESTED-PASS |
| 9 | Backtesting & Strategy Validation | `backtest.py`, `walkforward.py` | TESTED-PASS |
| 10 | Portfolio Intelligence | `portfolio.py`, `risk.py` | TESTED-PASS |
| 11 | Trade Planning & Risk | `planning.py`, `/api/planning*` | IMPLEMENTED |
| 12 | Trading Journal & Research Records | `journal.py`, `/api/journal/*` | TESTED-PASS |
| + | Personal Research Agent (directive) | `agent.py`, `/api/agent/*` | IMPLEMENTED (backend allowlist) |

---

## 3. Feature implementation matrix (this session's changes)

### 3.1 Indicator expansion (added later in the same session)

| Feature | Backend | API | Frontend | Tests | Status |
|---|---|---|---|---|---|
| 18 new indicators | `megatool/ta/other.py`, `ta/trend.py`, `ta/momentum.py`, `ta/volume.py` | auto-listed by `GET /api/indicators`; served by `GET /api/bars/{symbol}/indicator?name=…` | existing indicator UI (name-driven, no per-indicator code) | `tests/test_indicators.py` 266 (dynamic look-ahead + warm-up + engine-free references) | **TESTED-PASS** |

Verified end-to-end for all 16 sampled new indicators: `GET /api/bars/ZZ/indicator?name=…`
returned 200 with the documented output columns and a finite last value (checked against an
isolated store under `data/dev/`, then deleted).

### 3.2 Original session slices

| Feature | Backend | API | Frontend | Storage | Tests | Security | Status |
|---|---|---|---|---|---|---|---|
| Chart patterns | `ta/patterns.py` | `GET /api/bars/{sym}/patterns` | charts view panel `#patterns` | none (compute-on-read) | `test_chart_patterns.py` (14), `test_patterns_stats_api.py` (3) | read-only; friend-allowlisted (read-only) | **TESTED-PASS** |
| Statistics (per symbol) | `stats.py` | `GET /api/bars/{sym}/statistics` | charts view `#stats` | none | `test_stats.py` (18), API (2) | read-only; allowlisted | **TESTED-PASS** |
| Correlation matrix | `stats.py` | `GET /api/stats/correlation` | charts view `#corr-out` | none | `test_stats.py`, API (4) | read-only; ≤25 symbols; allowlisted | **TESTED-PASS** |
| Scanner presets/metrics | `scanner.py` | `GET /api/screen/presets`, `POST /api/screen` | screener preset dropdown | none | `test_scanner.py` (109 in file group) | read-only / bounded | **TESTED-PASS** |

New metrics (all single-symbol, deterministic): `macd`, `macd_signal`,
`macd_histogram`, `macd_cross`, `sma_cross`, `bollinger_percent_b`,
`bollinger_bandwidth`, `stochastic_k`, `stochastic_d`, `mfi`, `adx`,
`donchian_position`, `donchian_breakout`, `turnover_sma_ratio`.
New presets (23 total) include RSI overbought/oversold, MACD bull/bear cross,
SMA20/50/200, SMA5-vs-SMA20, Bollinger lower/upper/squeeze, Stochastic
oversold/overbought, MFI oversold, Donchian breakout, breakout+volume, 52w
high/low, 20-day momentum, ADX trend, low-volatility, liquidity.

---

## 4. Data & calculation documentation (what changed)

**Chart patterns (`ta/patterns.py`)**
- Pivots come from `ta/swings.find_swings` (same definition as structure /
  Fibonacci / harmonic endpoints), so modules never disagree on a turning point.
- Detectors: double/triple top & bottom, head-and-shoulders + inverse,
  ascending/descending/symmetrical triangles, rising/falling wedges, bull/bear
  flags, up/down channel breakout.
- `level_tol` (default 3.5%) defines how close two touches must be.
  `right` (default 3) is the honest confirmation lag.
- Quality = documented symmetry rule: `max(0, 100 − 50·dev/tol)`. **Not a
  probability of profit.**
- `status="confirmed"` only when a close beyond the trigger exists within the
  available history; otherwise `"forming"`.
- Insufficient history ⇒ `available=false` + reason (never an empty "no
  patterns" that could be misread as a clean chart). Non-finite input refused.

**Statistics (`megatool/stats.py`)**
- Pure numpy + math (scipy is only a transitive dependency and is **not**
  imported).
- Pearson/Spearman/OLS p-values use the **exact Student-t** distribution via the
  regularised incomplete beta (no normal shortcut); verified in tests against
  published table values (t=2.228, df=10 → p≈0.05).
- Undefined statistics return `None` (never NaN, never invented): zero-variance
  ⇒ no Sharpe; empty sample ⇒ null means; non-positive prices ⇒ returns
  undefined.
- Annualisation convention: `periods_per_year=240` (stated, not measured).
- Correlation matrix aligns on the shortest length then uses pairwise-complete
  points and reports each cell's own `n`.

**Unchanged and reused (not rebuilt):** `ta/` indicators, swings/levels/Fibonacci/
harmonic/Elliott/candles, `regime.py`, `backtest.py`, `portfolio.py`,
`journal.py`, `ranking.py`.

**Freshness/missing-data rules (unchanged, preserved):** a 200 does not mean
fresh; missing is never zero; stale is never rendered fresh; a successful empty
response ≠ a failed request.

---

## 5. Reference-platform audit (15 URLs)

Fetched 2026-10-15 with the read-only fetch tool. "Snippet only" = the site is a
JavaScript single-page app that returned only a title to a non-browser fetch.

| # | URL | Observed | Relevance to Mega Tool | Gap |
|---|---|---|---|---|
| 1 | nepalytix.com | Live market, AI signals, portfolio tracker, screener, broker flow, 50+ indicators, open data API, heatmap, alerts, TradingView charts (freemium) | Broad parity target | paid tier; we stay local/free |
| 2 | merolagani.com/latestmarket.aspx | Live table (Symbol/LTP/%/Open/High/Low/Qty/PClose/Diff), Gainers, Losers, Top Turnovers, Top Sectors, indices | Dashboard panels parity | — |
| 3 | nepsealpha.com | Landing only (snippet) | Charting/TA | login-gated deeper views |
| 4 | nepsealpha.com/nepse-chart | **Login/registration wall** | Advanced charts | login-restricted (recorded, not bypassed) |
| 5 | sebon.gov.np/intermediaries/stock-exchange | Regulator page; counts: 1 exchange, 90 brokers, 125 DPs, 43 ASBA banks, 24 mutual funds | **Authoritative** intermediary counts; source-rights reference | — |
| 6 | nepalipaisa.com/live-market | Live market table (JS/XHR), search/reset; indices; share manager; calculators | Market discovery parity | — |
| 7 | merolagani.com/Dashboard.aspx | Login dashboard exposing **paid** modules (AI charts, analytics, virtual trading) | UX reference | paywalled |
| 8 | chukul.com/nepse-live-market | Snippet only ("Live Market, Stock Analysis & Buy/Sell Signals") | signals UX | SPA / not verifiable |
| 9 | nepalipaisa.com | Indices (NEPSE, Float, Sensitive, sectors), movers, IPO/dividend tables, corporate actions, calculators | Dashboard + corporate actions | — |
| 10 | hamroshare.com.np | Richest public dashboard: market mood, breadth + **circuit counters**, day/52w range, sector heatmap & turnover share, top gainers/losers/turnover/volume/transactions, events + calendar, broker-flow summary, market wrap | Closest UX model | none portable (recorded as reference) |
| 11 | sharesansar.com | News portal + market data: market overview, live trading, **heatmap by turnover/volume**, today's price, floorsheet, AGM/SGM, proposed dividend, sectorwise price, indices, top brokers, candlestick chart, index history; calculators; MA/180-day/pivot analysis | Feature breadth reference | — |
| 12 | nepsetrading.com | AI/ML analysis, heatmap, intraday, floorsheet screener, calendar, blogs, **paid packages** | AI-research UX | paid |
| 13 | nepsealpha.com/nepse-data | "Nepse Price Export" (paywalled export) | data export | paywalled |
| 14 | nepaleconomicforum.org/… | Macro article: NEPSE history, liquidity/turnover, market size, market-cap/GDP, digitalization timeline | **Regulatory/macro context reference** | — |
| 15 | bullhouseinvestment.com/chart/NEPSE | Snippet only; TradingView chart | charting |
| | | **Already implemented in Mega Tool:** live/delayed quotes UI, dashboard panels, index + sector views, scanner, heatmap-style sector display, charts with indicators, floorsheet summaries, fundamentals, backtesting, journal, portfolio, alerts, freshness labels, export. | | |
| | | **Remaining gaps:** real-time push/websocket (we intentionally poll), broker beneficiary inference (never inferred), paid third-party signals (out of scope) | | |

We did **not** bypass any login, paywall, paywall-gated export, or
robots restriction; restricted pages are recorded as restricted.

---

## 6. Security & privacy review (executed)

| Check | Evidence | Result |
|---|---|---|
| Production DB untouched | isolated `data/dev/perf/perf_market.duckdb`; prod DuckDB/SQLite not referenced by any command run | PASS |
| Gated collector off | `MEGATOOL_NEPSE_API_AUTHORIZED` unset in all runs; perf harness explicitly unsets it | PASS |
| Friend boundary | `friend_access.py` deny-by-default allowlist extended for the 3 new read-only routes; middleware tested in `test_friend_access*` | PASS |
| Private data stays private | journals/portfolio/admin prefixes remain denied; new endpoints are public market data only | PASS |
| No secrets in frontend | new frontend code reads only API paths; no keys | PASS |
| Input validation | new endpoints validate symbol (≤10 chars), method pattern, symbol count ≤25, `level_tol` bounds | PASS |
| SQL/injection | no new raw SQL; uses `MarketStore` API | PASS |
| New endpoint tests | `tests/test_patterns_stats_api.py` (9) incl. 400/404/422 negative cases | PASS |
| No orders/deploy | no order path touched; nothing deployed/published | PASS |

Not performed (environment limitation, disclosed): XSS/unsafe-rendering fuzzing
and a complete click-through of every view. **Partial browser QA was performed** -
see §8.1 - which is where defect B-46 was found and fixed.

---

## 7. Performance (measured, backend-only)

Harness: `scripts/perf_smoke.py`, isolated DB, synthetic universe
**60 symbols × 650 bars**, `TestClient` (in-process), warm, 12 runs/endpoint.

| Endpoint | p50 ms | p95 ms | n |
|---|---|---|---|
| `GET /api/dashboard` | 8.7 | 9.4 | 12 |
| `GET /api/quotes` | 1.4 | 1.5 | 12 |
| `GET /api/bars/{sym}` | 18.9 | 42.2 | 12 |
| `GET /api/bars/{sym}/indicator` (rsi) | 4.1 | 4.5 | 12 |
| `GET /api/bars/{sym}/patterns` (new) | 5.7 | 6.0 | 12 |
| `GET /api/bars/{sym}/statistics` (new) | 3.3 | 3.4 | 12 |
| `POST /api/screen` | 145.8 | 160.3 | 12 |
| `POST /api/rank` | 397.2 | 410.7 | 12 |
| `POST /api/backtest` | 8.3 | 9.0 | 12 |
| `GET /api/stats/correlation` (new, 3 syms) | 5.7 | 6.2 | 12 |

**Caveats (honest):** these are warm, in-process, backend-only numbers on a
synthetic fixture; they are **not** end-to-end, not browser, and not live-market
latency. Percentiles over n=12 are indicative.

**Bottleneck identified:** `POST /api/rank` is the heaviest operation and scales
roughly linearly with universe size (≈0.4 s at 60 symbols; a ~250-symbol
universe is expected to take on the order of a few seconds). It was **not**
rewritten this session (risk vs. reward); it is recorded as the top
optimisation candidate (e.g. caching per-symbol factor values keyed by the data
snapshot). Everything else meets the sub-second target on this fixture.

---

## 8. Six verification rounds

| Round | Focus | Evidence | Result |
|---|---|---|---|
| 1 | Mathematical/calculation correctness | `test_stats.py` (known closed-form answers: slope 3/intercept 2; t-table p-values; drawdown −0.25), `test_chart_patterns.py` (hand-placed pivots, neckline 102), existing indicator/deterministic fixtures | PASS |
| 2 | Edge cases & data quality | tests for empty/short series, non-finite input, zero-variance, non-positive prices, insufficient history, unknown symbols, bad method, no-history peers | PASS |
| 3 | End-to-end integration | `test_patterns_stats_api.py` (store → calc → API JSON contract); existing integration tests for quotes/backtest/portfolio; **browser QA pass** (isolated dev server + playwright-cli) exercised the real data → calc → API → DOM chain | PASS (found B-46) |
| 4 | Quantitative & causal validity | look-ahead test (double-top "forming" before the breakout bar, "confirmed" after); Donchian breakout excludes the latest bar; existing walk-forward/look-ahead suites | PASS |
| 5 | Security & privacy | §6 | PASS |
| 6 | Performance & regression | full suite **1999/0/0/0**; ruff check + `format --check` clean; `node --check web/static/app.js` clean; route inventory 75/75 test-referenced; §7 timings | PASS |

### 8.1 Browser QA actually performed (evidence for Round 3)

A dev server was started on `127.0.0.1:8712` with `MEGATOOL_DATA_DIR` pointed at an
**isolated** `data/dev/browser_qa/` store (4 synthetic symbols x 300 bars + one
NEPSE index series) and driven with `playwright-cli`. Localhost only; nothing was
exposed publicly, no tunnel, no firewall change. The server was killed afterwards
and the dev data deleted.

| Check | Result |
|---|---|
| Page / title | `Mega Tool — NEPSE Research Terminal`, HTTP 200 |
| `/api/indicators` via the live server | 200, **46** indicators, `kama` present |
| Dashboard breadth | 4/4 securities; `Advancers 0 · Decliners 0 · Unchanged 0 · No change data 4` — an honest bucket for the fixture's `percent_change=NaN`, not invented zeros |
| Charts view | 120 bars plotted; meta shows source + "unadjusted (not adjusted for bonus/split)" |
| Patterns panel | 8 detections tabulated with direction / status / quality / dates / breakout / invalidation |
| Statistics panel | 7 metrics rendered (found mis-scaled → **B-46**, fixed and re-verified) |
| Correlation panel | 4x4 matrix, `Method: pearson · common bars: 120` |
| Correlation cross-check | rendered values match an independent numpy `corrcoef` recomputation to **1e-9** |
| Scanner presets | all **23** options populated; an `above_sma20` run reported `Evaluated 4 · Eligible 4 · Passed 1` with actual values |
| Console | **0 errors, 0 warnings across all 11 views** |
| Percent fix re-verified | `Total return +34.36% · CAGR +26.76% · Ann. volatility +25.62% · Max drawdown -15.18%`, matching the API fractions exactly |

**B-46 (found here, fixed):** `fmtPct()` in `web/static/app.js` appends `%` without
scaling by 100, so fractional statistics (`0.3436`) rendered as "0.34%". The
backtest panel has the same shape but its API already returns percentages. Fixed
with an explicit `fmtPctFrac()` for fraction inputs and local scalars for
already-scaled ones, then re-verified in the browser.

---

## 9. Safety-boundary confirmation (end of run)

- Production DuckDB and SQLite: **not modified**.
- `MEGATOOL_NEPSE_API_AUTHORIZED`: **never set**; official collector remained off.
- No orders simulated-as-real, none executed; no brokerage connection attempted.
- Nothing deployed or published; no Netlify publish; no tunnels/firewall changes.
- Protected files (`AI Trading Nipsy/`, `MEGA_TOOL_RESEARCH_REPORT.md`, original
  PDFs/journals): **unmodified**.
- Git: nothing staged/committed/pushed; `data/review/` and `data/dev/` not staged.
- Live-market requests to NEPSE official API: **zero**.

---

## 10. Final run instructions / how to reproduce

Local development only. **Never** set `MEGATOOL_NEPSE_API_AUTHORIZED=1`.

```bash
cd "/Users/ashim/Downloads/AI trading NEPSE"

# Backend (dev). Uses the configured data dir; does not touch prod data unless
# MEGATOOL_DATA_DIR points there.
.venv/bin/python -m uvicorn megatool.api:app --host 127.0.0.1 --port 8711

# Static frontend is served by the backend at http://127.0.0.1:8711/ .

# Full test suite (use junitxml; the terminal writer sometimes drops the summary)
.venv/bin/python -m pytest --junitxml=/tmp/junit.xml -q
.venv/bin/python - <<'PY'
import xml.etree.ElementTree as ET
r=ET.parse("/tmp/junit.xml").getroot(); s=r.find("testsuite") or r
print("tests=%s failures=%s errors=%s skipped=%s" % (s.get("tests"),s.get("failures"),s.get("errors"),s.get("skipped")))
PY

# Lint / format
.venv/bin/ruff check .
.venv/bin/ruff format --check .

# Route inventory (regenerate the doc)
.venv/bin/python scripts/route_inventory.py --md docs/API_ROUTE_INVENTORY.md

# Performance smoke (isolated DB under data/dev/perf/)
.venv/bin/python scripts/perf_smoke.py --symbols 60 --bars 650 --runs 12

# Scanner presets / one symbol's patterns / statistics (against a running dev server)
curl -s 'http://127.0.0.1:8711/api/screen/presets' | head
curl -s 'http://127.0.0.1:8711/api/bars/NABIL/patterns'
curl -s 'http://127.0.0.1:8711/api/stats/correlation?symbols=NABIL,NICA,SCB'

# Backtest workbench (deterministic fixture example)
curl -s -X POST 'http://127.0.0.1:8711/api/backtest' \
  -H 'content-type: application/json' \
  -d '{"symbol":"NABIL","strategy":"sma_cross"}'
```

Protected-production commands (Do **not** run in this run; listed only so the
next operator can identify them): anything that writes
`data/processed/megatool_market.duckdb`, `--apply` integration imports, or
starting/stopping the existing server held by PID 26596.

---

## 11. Remaining work / exact next steps

1. **Optimise `POST /api/rank`** (measured bottleneck). Candidate: cache
   per-symbol raw factor values keyed by `(symbol, last_date, min_bars)`.
2. **Browser QA** of the charts view additions (`#patterns`, `#stats`,
   `#corr-out`) — backend contracts and JS are in place but were not exercised
   in a real browser this run.
3. **Wire the remaining spec §29 items** already noted in Phase-1 docs
   (candlestick markers on the chart; pattern overlays as drawn annotations).
4. **External authorizations** (owner): NEPSE official API ruling; TMS read-only
   source; YONEPSE data-rights; friend token/origin — each unblocks exactly one
   integration and does not gate the local app.

---

## 12. Session change inventory (files touched)

New: `megatool/ta/patterns.py`, `megatool/stats.py`,
`tests/test_chart_patterns.py`, `tests/test_stats.py`,
`tests/test_patterns_stats_api.py`, `scripts/perf_smoke.py`,
`docs/PHASES_2_6_PROGRESS.md`.

Modified: `megatool/scanner.py` (metrics + presets), `megatool/api.py` (3
endpoints + imports), `megatool/friend_access.py` (allowlist), `.gitignore`
(`data/dev/`), `web/static/index.html` + `web/static/app.js` (charts-view
panels), `tests/test_scanner.py` (metric/preset coverage),
`docs/API_ROUTE_INVENTORY.md` (regenerated),
`MEGA_TOOL_FEATURE_STATUS.md` (update section).

---

# SESSION 16 — VERIFICATION MISSION (2026-10-16)

> Append-only. This session was a *verification and gap-closing* pass, not a
> feature build. Baseline at start: **1999 tests, 0 failures**, HEAD `b6c3659`,
> production server PID 26596 alive on :8710, gate `MEGATOOL_NEPSE_API_AUTHORIZED`
> unset.

## Recount A — what was actually verified (not merely re-asserted)

### A1. Source documents re-confirmed
Both PDFs located by exact filename and checksummed; extraction from the prior
session re-validated (104 and 51 page markers present, matching the page counts).
`The Phases COMPLETE !.pdf` md5 `c0cb893a…`, `ALL THE CONTENT…pdf` md5 `10ed4aaf…`.

### A2. Full-browser end-to-end pass (the gap the prior session admitted)
An isolated dev server (`127.0.0.1:8714`, `MEGATOOL_DATA_DIR=data/dev/qa`, 13
synthetic symbols × 420 bars + 2 index series) was driven with `playwright-cli`
through **all 11 views**. Result: **0 console errors, 0 warnings**.

| Journey | Rendered | Independently checked |
|---|---|---|
| Overview dashboard | breadth, totals, regime, gainers/losers | breadth honest (`No change data` bucket, not fabricated zeros) |
| Charts | candlesticks, SMA/EMA/BB/MACD/RSI/swings, patterns table, statistics card | pattern rows real (e.g. `double_bottom confirmed`, q=98) |
| Screener | 23 presets, screen run, factor ranking | `Evaluated 13 · Eligible 13 · Passed 4` |
| Backtest | metrics, equity, trade ledger, assumptions, warnings | see A3 |
| Portfolio | add transaction, derived position | **arithmetic exact**: 100 × 165.2733 = 16,527.33; −11,000 = 5,527.33 |
| Journal | create entry, stats, grade/reflect | win-rate shown as `—` with no closed trades (honest) |
| Research | full report with citations, agent | **SMA20 161.7895 / +2.1533% re-derived by hand, matched** |
| Fundamentals / Floorsheet | honest empty states | "0 records", "no floor sheet imported" |
| Data & Quality | coverage, sources, per-symbol quality, freshness | "stale by 280 days", "live feed not connected" |

### A3. Independent quantitative cross-check (`scripts/verify_quant.py`)
Every value compared against a **separately written** reference (pandas, scipy,
or a plain loop) — never the app's own primitives.
**All checks agreed.**

* SMA / WMA / EMA(SMA-seeded) vs pandas / independent loop
* RSI vs an independent Wilder loop; MACD vs pandas `ewm` (tail)
* Bollinger middle/upper/lower vs pandas rolling
* Pearson, Spearman, and four Student-t p-values vs `scipy.stats`
* OLS slope/intercept/r² vs `numpy.linalg.lstsq`
* Backtest, hand-computed: buy-and-hold **10,450**, one round trip **10,450**,
  fee-adjusted (1%/side) **10,247.50** — all matched exactly, including the
  next-open fill convention and the "open position is not a closed trade" rule.

## Recount B — defects found and fixed

### B-47 — Inconsistent symbol validation across per-symbol endpoints — **FIXED**
Six endpoints capped the symbol at 10 chars, four did not, so a stored
11-character symbol returned 200 on `/api/bars/{symbol}` but **400** on
`/patterns`, `/weekly`, `/elliott`, `/harmonic`. Found only by the E2E pass.
Fixed with one shared `valid_symbol()` (cap 24, no path separators) on **every**
per-symbol route; malformed → 400, well-formed-unknown → 404, consistently.

### B-48 — Access-boundary state was implicit and silent on the ASGI entrypoint — **HARDENED**
The friend boundary is off unless `MEGATOOL_FRIEND_TOKEN` is set, so an owner-only
process serves private routes to any reachable client. The CLI warned on a
non-loopback bind, but `uvicorn megatool.api:app` bypassed that warning entirely.
Added `_log_access_boundary()`, printed at startup on **every** entrypoint,
reporting one of: owner-only/loopback, owner-only/**non-loopback WARNING**, or
friend-token ACTIVE. It never prints the token (asserted by test).

### B-46 follow-through — frontend percent scaling
Re-confirmed live in the browser this session (backtest now renders
`+74.86%` / `+66.82%`, statistics `+34.36%` / `−15.18%`).

### XSS hardening
Full XSS probes through the journal (user text) and the reflect panel did **not**
execute; a static scan of all 137 `innerHTML` sites found the renderer escapes at
every leaf. One unescaped server value (`d.data_as_of`) was nonetheless wrapped
in `esc()` as defence in depth (it is always a date, so not exploitable).

## Recount C — test evidence

| Command | Result |
|---|---|
| `pytest --junitxml=… -q` (full) | **2005 passed / 0 failed / 0 errors / 0 skipped** (32.6 s) |
| `tests/test_friend_access.py` | 20 passed (17 existing + 3 new boundary-notice) |
| `tests/test_patterns_stats_api.py` + harmonic + elliott + api | 156 passed |
| `ruff check .` | clean |
| `ruff format --check .` | 205 files formatted |
| `node --check web/static/app.js` | clean |
| `scripts/verify_quant.py` | exit 0, all independent checks agreed (scipy present) |
| `scripts/route_inventory.py` | 75 routes, all test-referenced |

## Recount D — safety state

Production DuckDB/SQLite mtimes unchanged; PID 26596 never signalled; gate unset
throughout (zero official-NEPSE requests); all QA data under `data/dev/`
(git-ignored) and deleted after use; 0 staged / 0 stashes; nothing committed,
pushed, or deployed.

---

## Recount E — requirements coverage summary (end of session 16)

Counts are over the **12 core product ideas** plus the **38 numbered spec
sections** and the milestone plan, de-duplicated so no requirement is counted
twice. A requirement is `BLOCKED` only when an external authorization or an
absent upstream source is the sole reason it cannot be completed.

| Status | Count | Representative items |
|---|---|---|
| **TESTED-PASS** | 31 | scanner & 23 presets; statistics (§16); correlation (§18); 46 indicators (§3); chart patterns (§6); backtesting & causality (§20); forecasting; portfolio; journal; multi-timeframe (§15); data quality (§31); technical indicators library |
| **IMPLEMENTED** (verified structurally, not yet fully acceptance-tested) | 12 | dashboard (§2); AI research assistant & agent (§19, idea 1/12); floorsheet (§21); fundamentals (§20/23); news & events (§24); trade planning (§22); regime (§17); candlestick/harmonic/Elliott/Fibonacci (§4,5,7,8); visualization (§29) |
| **PARTIAL** | 5 | Elliott Wave (bounded by design); document/handwriting intelligence (§26); volatile-fundamentals coverage; scanner divergence screeners (candidates only); regime still uses an equal-weighted proxy (§17, B-10) |
| **TESTED-FAIL** | 0 | — |
| **NOT STARTED** | 0 | every spec section has at least a partial implementation |
| **BLOCKED** (external) | 6 | official NEPSE API authorization; TMS source; YONEPSE data-rights; live general-news feed; friend deployment (token/origin); intraday freshness observation |
| **NOT-TESTED** | 7 | dependency CVE scan; XSS fuzzing; production migration; background jobs; soak/long-run; live-market latency; real friend-token flow |

**Milestone plan (The Phases):** M0 TESTED-PASS · M1 PARTIAL (browser-verified for
panels, no full click-through) · M2 PARTIAL (improved) · M3 IMPLEMENTED ·
M4 TESTED-PASS · M5 PARTIAL (§5 security/perf/deploy-prep).

**Reference platforms:** the 15-platform audit stands as recorded in §5; no
platform was re-fetched this session, so its classifications are unchanged and
are not re-asserted as fresh.

---

# SESSION 17 — DEFINITIVE COMPLETION AUDIT (2026-10-16)

> Append-only. Audit-only session: **no application code changed**. Full test
> suite re-run: **2016 passed / 0 failed / 0 errors / 0 skipped** (38.1 s),
> HEAD `b6c3659`, gate unset, production DBs untouched, PID 26596 never
> signalled.

The complete, requirement-level audit lives in
**`docs/PHASES_2_6_COMPLETION_AUDIT.md`** (phase-by-phase matrix, requirement
traceability, verified/partial/missing/untested/blocked lists, live-data A–H
report, ordered queue, exact commands). It uses the overview PDF §35 phase
definitions (Phase 2–6) mapped to the directive's Milestones.

**Corrections to earlier labels in this file (requirement-level, not section-level):**

* Recount E's **"NOT STARTED: 0"** is true only at *spec-section* granularity.
  At *requirement* granularity these are genuinely NOT STARTED: background-job
  architecture (M5 §12.5); **watchlists** (M1 §8.2 — `watchlists` table exists,
  no API/UI); **saved screens** (`saved_screens` table unused);
  **research-experiment save/reproduce/export** (M4 §11.5 steps 8–11);
  **custom formula catalogue** and **research templates** (Phase 6);
  **exportable report/chart** (Phase 6 #38).
* **M4 is PARTIAL, not TESTED-PASS:** §11.1 has no expression/JSON strategy DSL,
  §11.4 lacks snapshot-id/config-hash metadata, and §11.5 save/reproduce/export
  are absent — so the mandatory acceptance criterion *"research experiments can
  be reproduced"* is unmet.
* `plotCandlestickMarkers` in `web/static/app.js` is **dead code** (defined,
  never called): candlestick patterns are not drawn on the chart.
* Phase verdicts: **Phase 2 PARTIAL · Phase 3 PARTIAL · Phase 4 PARTIAL ·
  Phase 5 PARTIAL · Phase 6 PARTIAL.** No phase is complete.

No new code defect was found this session; the findings are coverage gaps and
the two documentation-accuracy corrections above.

---

## Session 18 (2026-10-16) — implementation, not another audit

The session-17 audit is the requirement-level ground truth. This session acted on
it: the highest-value **missing capabilities were implemented, tested and
browser-verified**. Full suite **2051 passed / 0 failed / 0 errors / 0 skipped**
(+35 new tests); route inventory **88 routes** (71 read-only, 17 mutating), all
test-referenced.

### What was implemented

| # | Capability | Status | Evidence |
|---|---|---|---|
| 1 | **Candlestick patterns reachable** — the 15-pattern engine (`ta/candles.py`, ~94 engine tests) had no route: now `GET /api/bars/{symbol}/candles` (params `start,end,limit,patterns,trend_bars,require_prior_trend`) | **TESTED-PASS** *(backend)* / **IMPLEMENTED** *(UI)* | `tests/test_candles_api.py` (10); browser: 17 rows, 15-pattern picker, "impossible OHLC excluded" surfaced |
| 2 | **Candlestick markers on the chart** — `plotCandlestickMarkers` was dead code reading `p.rule` (engine emits `p.name`) and calling `setMarkers` per-source (which erases prior markers) | **TESTED-PASS** *(browser)* | Unified `state.*Markers` + one `flushMarkers`; markers visible on the rendered chart |
| 3 | **Elliott Wave UI** — engine existed, no UI. Now: automatic candidate table (scenario, evidence, alternative count, invalidation, Fibonacci relations, certainty) **plus** manual wave labelling of confirmed pivots (stored per symbol, drawn on chart) | **IMPLEMENTED** / **TESTED-PASS** *(browser)* | 33 pivots labelled; `localStorage` persisted; magenta wave line + labels drawn |
| 4 | **Harmonic UI** — engine existed, no UI. Now: candidate table with measured ratios, matched bands, completion zone, invalidation, certainty; XABCD polyline + D marker drawn (index→date via the full series, window-filtered) | **IMPLEMENTED** / **TESTED-PASS** *(browser)* | `Status NO_MATCH · 29 windows · 5 patterns`, rendered + verified (no match on the fixture, honestly shown) |
| 5 | **Watchlists** (M1 §8.2) — `watchlists` table existed, unused. Now storage module + CRUD API + UI | **TESTED-PASS** | `tests/test_watchlists.py` (15); browser create/detail/add/rename/delete; missing bar → `—` + reason |
| 6 | **Reproducible experiments** (M4 §11.5 steps 8–11) — save/list/get/delete + **reproduce** (re-runs through the same `_run_backtest_request`) + **compare** (metric deltas) + **Markdown/JSON export**, SHA-256 config hash | **TESTED-PASS** | `tests/test_experiments.py` (10); browser save + reproduce ("identical config: yes", every metric same) + exports downloaded |
| 7 | **Report & chart export** (Phase 6 #38) — experiment Markdown export server-side; research-report Markdown export client-side from the exact payload | **IMPLEMENTED** / **TESTED-PASS** *(browser)* | downloads `experiment-N.md`, `SYMBOL-research-report.md` |
| 8 | **go-nepse decision** | **TESTED-FAIL → NOT INTEGRATED (documented)** | `docs/GO_NEPSE_INVESTIGATION.md` |
| 9 | **Platform research matrix** (≥15 platforms) | **IMPLEMENTED** | `docs/PLATFORM_RESEARCH_MATRIX.md` |

### Updated phase labels (requirement-level, unchanged discipline)

| Phase | Before | After | Why |
|---|---|---|---|
| Phase 2 | PARTIAL | **PARTIAL (advanced)** | Watchlists delivered; remaining: saved screens UI, other M1 §8 items |
| Phase 3 | PARTIAL | **PARTIAL (advanced)** | Candlestick API+markers, Elliott UI, Harmonic UI delivered; remaining: manual *chart-pattern* drawing, pattern-evaluation UI |
| Phase 4 | PARTIAL | **PARTIAL (advanced)** | Experiments + watchlists panels delivered; remaining: dashboard composition, index/RS panels |
| Phase 5 | PARTIAL | **PARTIAL (advanced)** | Experiment save/reproduce/compare/export + report export delivered; remaining: custom rule builder, templates |
| Phase 6 | PARTIAL | **PARTIAL (advanced)** | Export + UI accessibility advances; remaining: custom formula catalogue, background jobs (M5) |

### Honest gaps recorded this session

* **`tweezer` and `harami_cross` candlestick detectors do not exist** in the engine
  (15 patterns; `harami` present). Not added speculatively — recorded (D-al).
* **Elliott engine quirk:** `analyze_elliott_extended` builds its candidate from the
  **earliest** confirmed swings (`swings[:5]`), so automatic candidates are often
  far from a recent-window chart. The UI therefore pairs automatic candidates with
  **manual labelling** and states the distinction; the engine was **not** silently
  changed (that would alter research outputs and existing tests).
* **Candlestick coverage on the QA fixture is limited** because the fixture is
  deliberately adversarial (243/420 bars have impossible OHLC). The route excludes
  and counts these rather than repairing them (D-ak).
* **go-nepse not tested live:** Go is not installed and the endpoints are gated; a
  live call would be the very bypass the gate forbids — so it was intentionally
  not attempted.

## Session 19 (2026-10-16) — completion sprint

Implemented and verified this session (see `TEST_RESULTS.md` § session 19 and
`DECISIONS.md` D-am…D-ap):

| Requirement (audit id) | Before | After |
|---|---|---|
| Custom technical-analysis **rule builder** (Phase 5/6) | NOT STARTED | **TESTED-PASS** — reuses the tested scanner tree; saved-rule persistence (`megatool/screens.py`, `saved_screens`); browser run/save/duplicate/delete |
| **Dashboard composition** (Phase 4) | NOT STARTED | **TESTED-PASS** — show/hide + reorder + reset, persisted client-side; browser verified |
| **Candlestick remaining detectors** (`tweezer`, `harami_cross`) | NOT STARTED (D-al) | **TESTED-PASS** — catalogue 15 → 18 (D-ao, supersedes D-al) |
| Elliott **historical-period selection** + alternative-count selection | PARTIAL | **TESTED-PASS** — `start/end/limit` on the route; per-candidate **Draw** plots the count's real pivots with I–V / A–C labels |
| Harmonic **pattern selection + tolerance + period** | PARTIAL | **TESTED-PASS** — `patterns`/`slack`/`start/end/limit`; window aligned to the chart (fixes B-56) |
| Per-symbol **analysis-config save/reload** | NOT STARTED | **TESTED-PASS** — `localStorage` for Elliott window and harmonic patterns/slack |

Still **PARTIAL / carried forward** (not this session's target): research
**templates** catalogue, index/RS dashboard panels, background jobs (M5 §12.5),
chart drawing tools, portfolio cash-flow, alert severity/cooldown, live intraday
freshness. Still **BLOCKED (external)**: NEPSE official-API authorization, TMS,
YONEPSE data rights, friend-token deployment.

## Session 20 (2026-10-16) — assistant, templates, index/RS, alerts, security

| Requirement (audit id) | Before | After |
|---|---|---|
| Floating **AI assistant** wired to tools + the rule builder | NOT STARTED | **TESTED-PASS** — FAB + panel; *Send* → `/api/agent/run`, *Propose rule* → `/api/screens/propose` → **Load into rule builder** → run in the Screener |
| Interactive **Fibonacci / manual chart drawing** | NOT STARTED | **TESTED-PASS** — two-click anchors, drag, editable ratios, colours, visibility, delete/clear, JSON export, undo/redo, per-symbol persistence, survives indicator/range changes |
| **Chart-pattern selection + overlays** | PARTIAL | **TESTED-PASS** — picker filter, pivot polylines, trigger/invalidation lines, evidence panel; window-aligned (**fixes B-58**) |
| **Index + relative strength** panels, comparisons and scanner filter | NOT STARTED | **TESTED-PASS** — `relative_strength` is the 34th scanner metric, `GET /api/bars/{symbol}/relative-strength`, chart ratio overlay, dashboard "Index context" panel |
| **Research templates** catalogue | NOT STARTED | **TESTED-PASS** — 14 declarative workflows + generic runner + browser-local saved copies; route/execution assertions in `tests/test_templates.py` |
| **Alert severity / cooldown / history / acknowledgement** | NOT STARTED (severity/cooldown) | **TESTED-PASS** — additive `alert_history` columns, in-place re-fire with `fire_count`, per-row and bulk acknowledgement |
| **Security checks** (dependency audit, authorization boundaries, XSS) | NOT STARTED | **TESTED-PASS** — `pip-audit` clean; friend-boundary tests; XSS payloads escaped in a browser |
| **Read-only gate writing the operator's DB** | (unknown) | **FIXED** — B-59/D-aw: `MEGATOOL_APP_DB` redirect; production SQLite untouched by a gate run |

Still **PARTIAL / carried forward**: fundamentals inside the *scanner* (the grammar
reports P/E, P/B, dividend and earnings as unsupported rather than approximating them);
chart-pattern per-pattern invalidation detail; saved-screens tiling; B-60 (fibonacci
`422` contract).

Still **NOT STARTED**: portfolio cash-flow model, background jobs (M5 §12.5),
production migration, soak/long-run and live-latency testing, friend-token
cross-origin flow.

Still **BLOCKED (external)**: NEPSE official-API authorization, TMS, YONEPSE data
rights, friend-token deployment, live intraday/news freshness, 8 retired symbols.

## Session 21 (2026-10-16) — defect-fix pass (frontend re-verified)

A re-verification pass over the delivered frontend turned up four genuine defects,
all now fixed with browser evidence (B-60 … B-64).

| Requirement | Before | After |
|---|---|---|
| **Fibonacci overlay** (chart, auto-detected study, §8) | broken — a visible control drew nothing (read a non-existent key) | **TESTED-PASS** — draws the endpoint's real retracement/extension levels, labelled; **fixes B-61** |
| **Screener correctness** — a missing metric must not qualify a security (§9) | broken — an AND screen passed a symbol whose required metric was unavailable | **TESTED-PASS** — three-valued evaluation; unavailable ⇒ ineligible with the reason shown; **fixes B-62** |
| **Assistant panel close** (§3.3, §8) | broken — × / `Esc` left the panel on screen | **TESTED-PASS** — `[hidden]` authoritative; **fixes B-63** |
| **Data-source provenance surface** (§3.1, §13) | mislabelled a gated source as "down"/"no auth" | **TESTED-PASS** — three-state availability + `authorized` badge + note; **fixes B-64** |
| **`/fibonacci` unavailable contract** | `422` for thin data (B-60) | **TESTED-PASS** — `200 {available:false, reason}`; **fixes B-60** |

Still **PARTIAL / carried forward**: fundamentals inside the *scanner* (P/E, P/B,
dividend and earnings remain unsupported-with-reason in the grammar); chart-pattern
per-pattern invalidation detail; saved-screens tiling; portfolio cash-flow model;
background jobs (M5 §12.5).


---

## Session 22 (2026-10-16) — actual go-nepse Go library integrated

The owner asked for the **actual** Go library rather than a protocol
re-implementation. It is now integrated behind a process boundary with the project's
hard rules intact: TLS verification stays **ON**, and live access stays behind the
`MEGATOOL_NEPSE_API_AUTHORIZED` gate (enforced independently in the Python adapter and
in the Go bridge). `tools/gonepse-bridge/` links `github.com/voidarchive/go-nepse
v0.2.5`; `megatool/datasources/gonepse.py` is the adapter; `GET /api/gonepse/status`
is the network-free diagnostics route. Full detail in
`docs/GO_NEPSE_INVESTIGATION.md` §11 and `DECISIONS.md` D-bc…D-bg.

Gates: 2150 Python tests pass (0 fail/skip), 9 Go tests pass, ruff clean, route
inventory 100 routes all test-referenced. **Live connection: BLOCKED** (gate unset);
no live NEPSE request was made and the certificate was confirmed valid under
verification.

This closes the "actual library integrated" requirement. Also this session the
**portfolio cash-flow model** (P2, low-risk) was added: `cash_flows()` +
`GET /api/portfolio/cash-flow`, embedded in `/api/portfolio` and shown in the
Portfolio panel, with the explicit "not an account balance" contract. The remaining
Phase 2–6 gaps below are unchanged and still carried forward.
