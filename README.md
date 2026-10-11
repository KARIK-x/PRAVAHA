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
uv run pytest
```

Stop the server with `Ctrl-C`.

## Layout

| Path | Purpose |
| --- | --- |
| `megatool/` | Application package (data layer, indicators, scanner, backtest, API) |
| `web/static/` | Web terminal front end (no build step required) |
| `scripts/` | Maintenance / data-collection helpers |
| `tests/` | Automated tests (pytest) |
| `docs/` | Architecture, data sources, decisions, research register |
| `data/` | Local databases and downloads (git-ignored) |

## Data provenance

Every stored price bar carries a `source` label and a `retrieved_at` timestamp. Records
originating from test fixtures are labelled `SYNTHETIC-TEST-FIXTURE` and are never mixed
into real datasets. See `docs/DATA_SOURCES.md`.
