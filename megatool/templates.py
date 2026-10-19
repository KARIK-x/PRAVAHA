"""Reusable research **workflow** templates.

A template is a *configuration of existing tools*, never new logic and never
generated code. Each one names:

* ``question`` — an optional plain-language question for the existing
  deterministic agent (:mod:`megatool.agent`), which routes it to the tools it
  already has. No model is required for this to work;
* ``steps`` — concrete GET calls against existing endpoints, each with the
  parameters to pass and a one-line statement of what it contributes.

The catalogue is the single source of truth: the frontend is a generic runner
that reads these declarations, so a template can never silently advertise an
analysis the platform does not have. ``tests/test_templates.py`` pins the two
properties that matter — every ``path`` exists in the application's own route
table, and every step executes against a fixture store without a server error.

Nothing here executes a trade, and nothing here asserts an index value, a live
quote, or a detection that the underlying engine did not compute.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DEFAULT_LIMIT = 250


@dataclass(frozen=True, slots=True)
class TemplateStep:
    """One declarative call inside a workflow."""

    label: str
    path: str
    why: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Template:
    """A reusable analytical workflow."""

    id: str
    title: str
    summary: str
    view: str
    steps: tuple[TemplateStep, ...]
    question: str | None = None
    group: str = "Technical"
    inputs: tuple[str, ...] = ("symbol",)  # "symbol" and/or "symbols"
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["steps"] = [asdict(s) for s in self.steps]
        d["inputs"] = list(self.inputs)
        d["notes"] = list(self.notes)
        return d


def _bars_steps(symbol_placeholder: str = "{symbol}") -> list[TemplateStep]:
    return [
        TemplateStep(
            "Stored OHLCV",
            f"/api/bars/{symbol_placeholder}",
            "The actual stored bars the rest of the workflow reads (dates, closes, volume).",
            {"limit": DEFAULT_LIMIT},
        )
    ]


TEMPLATES: tuple[Template, ...] = (
    Template(
        id="technical_review",
        title="Technical stock review",
        summary="One symbol's stored history, computed statistics and swing structure.",
        view="research",
        question="research {symbol}",
        steps=tuple(
            _bars_steps()
            + [
                TemplateStep(
                    "Return statistics",
                    "/api/bars/{symbol}/statistics",
                    "Total return, annualised volatility, Sharpe, max drawdown over stored bars.",
                ),
                TemplateStep(
                    "Swing structure",
                    "/api/bars/{symbol}/structure",
                    "Confirmed swing highs/lows the pattern detectors also use.",
                ),
            ]
        ),
        notes=("Statistics are descriptive history, not a forecast.",),
    ),
    Template(
        id="trend_momentum",
        title="Trend and momentum analysis",
        summary="Moving averages, RSI, MACD and ADX computed from stored closes.",
        view="charts",
        question="research {symbol}",
        steps=tuple(
            _bars_steps()
            + [
                TemplateStep(
                    "RSI(14)",
                    "/api/bars/{symbol}/indicator",
                    "Wilder-smoothed RSI over stored closes.",
                    {"name": "rsi"},
                ),
                TemplateStep(
                    "MACD",
                    "/api/bars/{symbol}/indicator",
                    "MACD line against its signal line.",
                    {"name": "macd"},
                ),
                TemplateStep(
                    "ADX(14)",
                    "/api/bars/{symbol}/indicator",
                    "Trend strength — not direction.",
                    {"name": "adx"},
                ),
            ]
        ),
        notes=("Indicators are computed, not fetched; no live value is asserted.",),
    ),
    Template(
        id="breakout_research",
        title="Breakout research",
        summary="Distance from the trailing high/low plus the support/resistance zones.",
        view="charts",
        steps=tuple(
            _bars_steps()
            + [
                TemplateStep(
                    "Support / resistance zones",
                    "/api/bars/{symbol}/levels",
                    "Where the swing pivots clustered, as price bands.",
                ),
                TemplateStep(
                    "Swing structure",
                    "/api/bars/{symbol}/structure",
                    "The pivots the zone bands were formed from.",
                ),
            ]
        ),
        notes=("A level is a description of stored pivots, not a prediction of a break.",),
    ),
    Template(
        id="candlestick_review",
        title="Candlestick pattern review",
        summary="Single- and multi-candle formations detected on stored bars.",
        view="charts",
        steps=(
            TemplateStep(
                "Candlestick detections",
                "/api/bars/{symbol}/candles",
                "Rule-based candle formations with the bars that formed them.",
                {"limit": DEFAULT_LIMIT},
            ),
        )
        + tuple(_bars_steps()),
        notes=("A detected candle is descriptive; it carries no probability of profit.",),
    ),
    Template(
        id="chart_pattern_review",
        title="Chart-pattern review",
        summary="Geometric patterns over confirmed swings, with triggers and invalidation.",
        view="charts",
        steps=(
            TemplateStep(
                "Chart patterns",
                "/api/bars/{symbol}/patterns",
                "Pattern matches with pivots, breakout level, invalidation level and evidence.",
                {"limit": DEFAULT_LIMIT},
            ),
        )
        + tuple(_bars_steps()),
    ),
    Template(
        id="elliott_review",
        title="Elliott Wave review",
        summary="Candidate impulse/zigzag counts with rule checks over confirmed pivots.",
        view="charts",
        question="research {symbol}",
        steps=(
            TemplateStep(
                "Elliott candidates",
                "/api/bars/{symbol}/elliott",
                "Candidate counts, the pivots they use, and the rule each one violates.",
                {"limit": DEFAULT_LIMIT},
            ),
            TemplateStep(
                "Swing structure",
                "/api/bars/{symbol}/structure",
                "The confirmed pivots the candidate counts are built from.",
            ),
        ),
        notes=("Counts are heuristic candidates from pivots; they are not a prediction.",),
    ),
    Template(
        id="harmonic_review",
        title="Harmonic-pattern review",
        summary="Gartley/Bat/Butterfly/Crab band matches with the measured ratios.",
        view="charts",
        steps=(
            TemplateStep(
                "Harmonic candidates",
                "/api/bars/{symbol}/harmonic",
                "Measured XABCD ratios against the published bands (slack = 0 by default).",
                {"limit": DEFAULT_LIMIT},
            ),
        )
        + tuple(_bars_steps()),
        notes=(
            "A band match is a candidate. A potential reversal zone is not proof of a reversal.",
        ),
    ),
    Template(
        id="fundamental_review",
        title="Fundamental company review",
        summary="Stored fundamental records and the ratios derived from them.",
        view="fundamentals",
        steps=(
            TemplateStep(
                "Fundamental records",
                "/api/fundamentals/{symbol}",
                "Every stored record with its period end, source and verification status.",
            ),
            TemplateStep(
                "Derived ratios",
                "/api/fundamentals/{symbol}/ratios",
                "Ratios computed only where the required inputs are stored and verified.",
            ),
        ),
        notes=(
            "Coverage is whatever has been imported; missing fields are reported, never estimated.",
        ),
    ),
    Template(
        id="valuation_compare",
        title="Valuation comparison",
        summary="Side-by-side stored fundamentals for a handful of symbols.",
        view="fundamentals",
        inputs=("symbols",),
        steps=(
            TemplateStep(
                "Fundamental comparison",
                "/api/fundamentals/compare",
                "One row per symbol with only the fields that are stored and verified.",
                {"symbols": "{symbols}"},
            ),
        ),
        notes=("A ratio is shown only when its inputs are stored; no peer estimate is invented.",),
    ),
    Template(
        id="sector_compare",
        title="Sector and factor comparison",
        summary="Cross-sectional factor ranking of the stored universe.",
        view="screener",
        steps=(
            TemplateStep(
                "Factor ranking",
                "/api/rank",
                "Percentile factor scores across the whole stored universe (POST with default weights).",
                {"_method": "POST", "weights": {}},
            ),
        ),
        notes=("Relative strength is only computed when the composite index series is loaded.",),
    ),
    Template(
        id="stock_vs_index",
        title="Stock versus index",
        summary="Relative-strength ratio line and excess return against a stored index.",
        view="charts",
        steps=(
            TemplateStep(
                "Relative strength",
                "/api/bars/{symbol}/relative-strength",
                "Ratio (rebased to 100 on the first aligned date) and window excess return.",
                {"window": 60},
            ),
            TemplateStep(
                "Stored index series",
                "/api/indices",
                "Which published index series exist, and the composite benchmark.",
            ),
        ),
        notes=("Aligned on the inner join of both series; missing dates are counted, not filled.",),
    ),
    Template(
        id="historical_strategy",
        title="Historical strategy research",
        summary="Registered backtest strategies and how each one is configured.",
        view="backtest",
        steps=(
            TemplateStep(
                "Registered strategies",
                "/api/strategies",
                "The strategies that can be backtested, with their parameters and defaults.",
            ),
            TemplateStep(
                "Saved experiments",
                "/api/experiments",
                "Previously run experiments that can be reopened and reproduced.",
            ),
        ),
        notes=("A backtest uses stored history only; results are not evidence about the future.",),
    ),
    Template(
        id="portfolio_risk",
        title="Portfolio risk review",
        summary="Holdings-derived concentration, drawdown and volatility checks.",
        view="portfolio",
        inputs=(),
        steps=(
            TemplateStep(
                "Portfolio risk",
                "/api/portfolio/risk",
                "Concentration, drawdown and volatility limits against the stored holdings.",
            ),
            TemplateStep(
                "Portfolio",
                "/api/portfolio",
                "The holdings and their latest stored valuation the risk checks read.",
            ),
        ),
        notes=("Risk metrics use stored bars; missing prices are reported, not filled in.",),
    ),
    Template(
        id="custom_screen",
        title="Custom screen",
        summary="Run a saved condition set, or start from a shipped preset.",
        view="screener",
        steps=(
            TemplateStep(
                "Screen presets",
                "/api/screen/presets",
                "The shipped, documented condition sets.",
            ),
            TemplateStep(
                "Saved rules",
                "/api/screens",
                "Your own saved rules, plus the metric catalogue they may use.",
            ),
        ),
        notes=("Screens evaluate stored bars; an ineligible symbol is reported with its reason.",),
    ),
)

_BY_ID = {t.id: t for t in TEMPLATES}


def get_template(template_id: str) -> Template | None:
    """One template by id, or ``None``."""
    return _BY_ID.get(template_id)


def template_catalogue() -> dict[str, Any]:
    """The whole catalogue plus the integration contract the runner relies on."""
    return {
        "templates": [t.to_dict() for t in TEMPLATES],
        "count": len(TEMPLATES),
        "placeholder_rules": {
            "{symbol}": "the symbol typed by the user, upper-cased",
            "{symbols}": "the comma-separated symbol list typed by the user",
        },
        "how_it_runs": (
            "The runner performs each declared call against the same read-only "
            "endpoints the rest of the application uses, then displays what came "
            "back. Templates configure a workflow; they add no new calculation."
        ),
        "notes": [
            "A template never executes a trade and never asserts a live quote.",
            "If a step's data is absent the step reports that instead of a value.",
        ],
    }


__all__ = [
    "DEFAULT_LIMIT",
    "TEMPLATES",
    "Template",
    "TemplateStep",
    "get_template",
    "template_catalogue",
]
