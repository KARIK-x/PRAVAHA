# Implementation plan

Phases are boundaries, not permission to stop. Executed in order; each verified
before the next.

| Phase | Deliverable | Status |
|---|---|---|
| A | Reference audit (106 images, 96 clusters) + feature matrix | **DONE** |
| B | Design system v2 (`DESIGN_SYSTEM.md`) | **DONE** (documented + shell/sidebar/ideas tokens shipped; not every component restyled) |
| C | App shell: left sidebar + top bar, grouped navigation, shared symbol search | **DONE** |
| C | Dashboard hero: index chart + stat strip + breadth + movers | **PARTIAL** — breadth stacked-bar + live strip shipped; the large index hero chart is **NOT STARTED** (no index series is stored, so it would show an empty state) |
| D | Chart workspace: chart-as-hero, grouped toolbar, **overlay manager**, clean defaults | **DONE** (candles + volume default; 6 opt-in layers with counts + result highlighting; caps 10 lines / 5 labels; chart type, fit, zoom, fullscreen). Still missing: trendline/ray/channel/text drawing tools, volume profile, multi-chart |
| E | Ideas view: methodology catalogue with honest data gating | **DONE** (10 models; 7 compute, 3 declared insufficient and disabled) |
| F | Portfolio / backtest visual upgrades | **NOT STARTED** |
| G | Cross-linking / shared symbol | **PARTIAL** — global search → chart, Ideas row → chart; other cross-links unchanged |
| H | Tests, browser sweep, docs | **DONE** |

## Explicitly deferred (documented, not faked)

Sector/breadth full pages, comparators, multi-symbol indicator matrix, valuation
models (DDM/Graham/Gordon/Lynch), DuPont, portfolio scoring gauges, chart-scanner
thumbnail grid, composition rail. Each needs either a new data source or a
module that does not exist; none is presented as available in the UI.

## Data honesty guardrails for every new view

- Model scores are computed **only** from stored fields; a missing input yields
  `Insufficient data` naming the field, never a number.
- Distributions (P/E, P/B, yield) use **real** stored values only.
- Breadth uses stored bars; index history is official-index only, and Mega Tool
  never labels an equal-weighted basket as the official NEPSE index.
