# Mega Tool

Local NEPSE quantitative research, technical analysis, and trading-analytics terminal.

> **Personal research software.** Mega Tool does not place trades, does not store broker
> or Mero Share credentials, and does not provide investment advice. Backtests and model
> forecasts describe historical or experimental results only and are **not** evidence of
> future performance. Verify all data independently before making financial decisions.

## Status

See `PROJECT_STATUS.md` for the verified feature matrix and `SESSION_HANDOFF.md` for
the current state and next task.

## Quick start

```bash
cd "Downloads/AI trading NEPSE"
uv sync                      # install dependencies into ./.venv
uv run megatool init         # create the local databases
uv run megatool fetch        # download real NEPSE history (network)
uv run megatool serve        # start the web terminal at http://127.0.0.1:8710
```

Run the test suite:

```bash
uv run pytest                # 490 tests, ~20s
```

Stop the server with `Ctrl-C`.

## What it does

| Area | What you get |
| --- | --- |
| **Data** | 89,580 real daily bars across 60 symbols (1995 → 2026-10-09), every row carrying its source and retrieval time |
| **Charting** | Candles, volume and 28 indicators, aligned to price by trading date |
| **Scanner** | 19 metrics, 4 presets, composable AND/OR filter trees |
| **Backtesting** | Own long/flat engine: next-bar-open fills, fees and slippage, a buy-and-hold benchmark, and every assumption printed with the result |
| **Research assistant** | A deterministic rules engine that answers *descriptive* questions with the window and definition behind every number, and refuses to predict or recommend |
| **Forecasting** | Six transparent models, each scored on an unseen hold-out against the naive "last value" baseline, with a plain-words verdict |
| **Portfolio** | Positions derived from your own transaction ledger, valued at the latest stored close |
| **Journal & planning** | Trade journal with win rate, R multiples and plan adherence; a planner that turns entry/stop/target into a position size for a risk budget |
| **Floor sheet** | Import a session's CSV (`megatool floor import`, or the API) and see buyer/seller concentration and counterparties, described as broker codes rather than as people. `megatool floor summary` prints the analysis with its limits |

## What it deliberately does not do

- **No live trading, ever.** No broker integration, no order routing, no credentials.
- **No live market feed.** The official NEPSE API requires an authenticated session
  (HTTP 401 on all probed endpoints), so every price shown is a stored end-of-day close
  and the UI says so.
- **No predictions.** Forecasting output is labelled with its assumptions, and a model
  that cannot beat "use yesterday's close" is reported as having demonstrated no skill.
- **No scraping.** Competitor sites publish pages, not APIs; floor-sheet and fundamentals
  analysis are import-based instead.
- **No synthetic data in real datasets.** Test fixtures are written to throwaway paths
  and are labelled `SYNTHETIC-TEST-FIXTURE`.

## Layout

| Path | Purpose |
| --- | --- |
| `megatool/` | Application package (data layer, indicators, scanner, backtest, forecast, research, portfolio, journal, planning, floor sheet, API) |
| `web/static/` | Web terminal front end (no build step required) |
| `scripts/` | Maintenance / data-collection helpers |
| `tests/` | Automated tests (pytest) |
| `docs/` | Architecture, data sources, decisions, research register, screenshots |
| `data/` | Local databases and downloads (git-ignored) |

## Data provenance

Every stored price bar carries a `source` label and a `retrieved_at` timestamp. Records
originating from test fixtures are labelled `SYNTHETIC-TEST-FIXTURE` and are never mixed
into real datasets. Imported floor sheets record the file's source label and a content
hash, so re-importing the same file cannot double-count a session. See
`docs/DATA_SOURCES.md`.
