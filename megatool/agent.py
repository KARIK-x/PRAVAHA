"""Personal trading research agent (Phase 2, feature 12).

A deterministic orchestration layer over the existing services — it does not
re-implement a single calculation. Routing is keyword-based and transparent:
the response shows which tools were chosen, what each returned, and why any
tool is blocked. The optional AI interpretation step is kept strictly separate
from tool output:

* ``tool_results`` are deterministic, carry provenance, and are never
  rewritten by a model;
* ``ai_interpretation`` is nullable, clearly labelled, and only ever
  *explains* the tool results — it cannot contribute numbers.

Privacy contract (non-negotiable): tools marked ``private`` (portfolio risk,
journal statistics) are **excluded from the AI prompt by default**. Private
data reaches a hosted model only when the caller passes
``include_private=True`` — the explicit authorization the guardrails require.
Private results are always returned to the caller locally either way.

No automatic trading: the agent only reads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from megatool import DISCLAIMER

#: Per-tool JSON budget in the AI prompt; beyond this the data is truncated
#: and the truncation is stated in the prompt itself.
PROMPT_DATA_BUDGET = 4000

#: Routing vocabulary. Order is canonical execution order, not priority.
TOOL_DEFS: dict[str, dict[str, Any]] = {
    "research": {
        "description": "Descriptive research report for one symbol from stored bars",
        "needs_symbol": True,
        "private": False,
        "keywords": (
            "research",
            "analy",
            "report",
            "trend",
            "momentum",
            "support",
            "resistance",
            "level",
            "sma",
            "rsi",
            "volume",
        ),
    },
    "scanner": {
        "description": "Multi-factor ranking of the stored universe",
        "needs_symbol": False,
        "private": False,
        "keywords": (
            "scan",
            "rank",
            "ranking",
            "top ",
            "best ",
            "factor",
            "screen",
            "universe",
            "compare ",
        ),
    },
    "portfolio_risk": {
        "description": "Risk metrics and limit breaches for the local portfolio",
        "needs_symbol": False,
        "private": True,
        "keywords": (
            "portfolio",
            "position",
            "exposure",
            "drawdown",
            "concentration",
            "holdings",
            "my risk",
            "var",
        ),
    },
    "regime": {
        "description": "Market trend/volatility/momentum regime labels",
        "needs_symbol": False,
        "private": False,
        "keywords": ("regime", "market state", "bull", "bear", "market mood"),
    },
    "fundamentals": {
        "description": "Derived P/E, P/B and dividend yield from stored fundamentals",
        "needs_symbol": True,
        "private": False,
        "keywords": (
            "fundamental",
            "p/e",
            "p/b",
            "eps",
            "yield",
            "book value",
            "dividend",
            "ratio",
        ),
    },
    "floorsheet": {
        "description": "Floor-sheet aggregation for imported sessions",
        "needs_symbol": False,
        "private": False,
        "keywords": (
            "floor",
            "broker",
            "counterparty",
            "accumulation",
            "distribution",
            "transaction",
        ),
    },
    "news": {
        "description": "Imported news items and recency (no live source yet)",
        "needs_symbol": False,
        "private": False,
        "keywords": ("news", "headline", "announcement", "event"),
    },
    "journal": {
        "description": "Deterministic trade statistics from the local journal",
        "needs_symbol": False,
        "private": True,
        "keywords": ("journal", "my trades", "my record", "written", "pdf"),
    },
    "backtest": {
        "description": "Backtesting (requires explicit parameters from the caller)",
        "needs_symbol": False,
        "private": False,
        "keywords": ("backtest", "walk-forward", "strategy test"),
    },
}


@dataclass(slots=True)
class ToolResult:
    """One tool's deterministic output, its provenance, and its limits."""

    tool: str
    status: str  # "ok" | "empty" | "blocked" | "error"
    private: bool
    summary: str
    provenance: str = ""
    reason: str | None = None
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "status": self.status,
            "private": self.private,
            "summary": self.summary,
            "provenance": self.provenance,
            "reason": self.reason,
            "data": self.data,
        }


@dataclass(slots=True)
class AgentRun:
    question: str
    plan: list[str]
    results: list[ToolResult] = field(default_factory=list)
    ai: dict[str, Any] | None = None

    @property
    def unresolved(self) -> list[str]:
        return [
            f"{r.tool}: {r.reason}"
            for r in self.results
            if r.status in ("empty", "blocked", "error") and r.reason
        ]

    @property
    def private_results(self) -> list[ToolResult]:
        return [r for r in self.results if r.private]

    def to_dict(self) -> dict[str, Any]:
        excluded = (
            [r.tool for r in self.private_results]
            if self.ai and self.ai.get("private_excluded")
            else []
        )
        return {
            "question": self.question,
            "plan": self.plan,
            "tool_results": [r.to_dict() for r in self.results],
            "unresolved": self.unresolved,
            "ai_interpretation": self.ai,
            "privacy": {
                "private_tools": sorted({r.tool for r in self.private_results}),
                "excluded_from_ai": excluded,
            },
            "disclaimer": DISCLAIMER,
        }


# -------------------------------------------------------------------- routing
def find_symbol(question: str, symbols: set[str]) -> str | None:
    """First stored-symbol token in the question, else None.

    A token that *looks* like a symbol but is not stored is not returned: the
    agent never invents a symbol the data does not contain.
    """
    for raw in question.replace(",", " ").replace("?", " ").split():
        token = raw.strip(".!:/").upper()
        if token in symbols:
            return token
    return None


def route(question: str, symbols: set[str] = frozenset()) -> list[str]:
    """Deterministic keyword routing. No match → empty plan (never a guess)."""
    q = (question or "").lower()
    hits = [key for key, spec in TOOL_DEFS.items() if any(word in q for word in spec["keywords"])]
    sym = find_symbol(question or "", set(symbols))
    # Symbol-scoped tools run whenever a symbol is present and the research
    # intent is there; a bare symbol question still gets a research report.
    if sym:
        if "research" not in hits and any(w in q for w in ("how", "what", "?", "why", "look")):
            hits.insert(0, "research")
        if "research" not in hits and not hits:
            hits.append("research")
    return hits  # canonical order = TOOL_DEFS insertion order


# ------------------------------------------------------------------ the tools
def _run_tool(key: str, store: Any, conn: Any, symbol: str | None, question: str) -> ToolResult:
    spec = TOOL_DEFS[key]
    private = bool(spec["private"])
    if spec["needs_symbol"] and not symbol:
        return ToolResult(
            tool=key,
            status="blocked",
            private=private,
            summary="",
            reason=f"'{key}' needs a symbol; the question named none of the stored symbols",
        )
    try:
        return _DISPATCH[key](store, conn, symbol, question)
    except Exception as exc:  # a failing tool must not sink the whole run
        return ToolResult(
            tool=key,
            status="error",
            private=private,
            summary="",
            reason=f"{type(exc).__name__}: {exc}",
        )


def _tool_research(store, conn, symbol, question) -> ToolResult:
    from megatool.research import build_report

    df = store.get_bars(symbol)
    if df.empty:
        return ToolResult(
            tool="research",
            status="empty",
            private=False,
            summary="",
            reason=f"no stored history for {symbol}",
        )
    universe = store.all_closes() if len(store.symbols()) > 1 else None
    report = build_report(df, symbol, universe)
    d = report.to_dict()
    return ToolResult(
        tool="research",
        status="ok",
        private=False,
        summary=f"{symbol}: {len(d.get('findings', []))} findings as of {d['as_of']} "
        f"over {d['bars']} stored bars",
        provenance=f"stored price_bars for {symbol}, {d['first_date']} → {d['as_of']}",
        data=d,
    )


def _tool_scanner(store, conn, symbol, question) -> ToolResult:
    from megatool.ranking import DEFAULT_WEIGHTS, RankConfig, rank_universe

    wanted = store.symbols(min_bars=1)
    frames: dict[str, Any] = {}
    for s in wanted:
        df = store.get_bars(s)
        if not df.empty:
            frames[s] = df
    if not frames:
        return ToolResult(
            tool="scanner",
            status="empty",
            private=False,
            summary="",
            reason="no stored history to rank",
        )
    meta = store.securities_meta(list(frames))
    sectors = {s: m.get("sector") for s, m in meta.items()}
    result = rank_universe(frames, RankConfig(weights=dict(DEFAULT_WEIGHTS)), sectors=sectors)
    d = result.to_dict()
    return ToolResult(
        tool="scanner",
        status="ok",
        private=False,
        summary=f"ranked {d.get('ranked_count', len(d.get('ranked', [])))} symbols; "
        f"top: " + ", ".join(r["symbol"] for r in d.get("ranked", [])[:5]),
        provenance=f"stored price_bars across {len(frames)} symbols; default weights",
        data={"top": d.get("ranked", [])[:10], "unavailable": d.get("unavailable", [])},
    )


def _tool_portfolio_risk(store, conn, symbol, question) -> ToolResult:
    from megatool.risk import portfolio_risk

    report = portfolio_risk(store)
    breaches = len(report.get("breaches", []))
    return ToolResult(
        tool="portfolio_risk",
        status="ok",
        private=True,
        summary=(
            f"status={report['status']}; {breaches} limit breach(es)"
            if report["status"] == "ok"
            else f"status=insufficient_data: {report.get('reason', '')}"
        ),
        provenance="local transaction ledger + stored price_bars",
        data=report,
    )


def _tool_regime(store, conn, symbol, question) -> ToolResult:
    from megatool.regime import detect_regimes

    result = detect_regimes(store.all_closes())
    d = result.to_dict()
    if result.status != "ok":
        return ToolResult(
            tool="regime",
            status="empty",
            private=False,
            summary="",
            reason=result.reason,
            data=d,
        )
    c = result.current
    return ToolResult(
        tool="regime",
        status="ok",
        private=False,
        summary=f"{c['date']}: trend={c['trend']}, volatility={c['volatility']}, "
        f"momentum={c['momentum']} (equal-weighted proxy, not the NEPSE index)",
        provenance="equal-weighted proxy over stored closes (blocker B-10: no official index)",
        data=d,
    )


def _tool_fundamentals(store, conn, symbol, question) -> ToolResult:
    from megatool.fundamentals import compute_symbol_ratios

    report = compute_symbol_ratios(conn, store, symbol)
    available = [
        f"{k}={v['value']}" for k, v in report["ratios"].items() if v.get("value") is not None
    ]
    return ToolResult(
        tool="fundamentals",
        status="ok" if available else "empty",
        private=False,
        summary=(f"{symbol}: " + (", ".join(available) if available else "no computable ratio")),
        provenance="stored fundamentals records + last stored close",
        reason=None if available else "every ratio refused; see data.ratios.*.unavailable_reason",
        data=report,
    )


def _tool_floorsheet(store, conn, symbol, question) -> ToolResult:
    from megatool.floorsheet import summary as floorsheet_summary

    data = floorsheet_summary(symbol=symbol)
    trades = int((data.get("totals") or {}).get("trades", 0) or 0)
    if trades == 0:
        return ToolResult(
            tool="floorsheet",
            status="blocked",
            private=False,
            summary="",
            reason="no floor sheets imported; candidate source awaits the data-rights "
            "ruling (blockers B-1/T-13)",
            data=data,
        )
    return ToolResult(
        tool="floorsheet",
        status="ok",
        private=False,
        summary=f"{trades} imported trade(s), {data['totals'].get('sessions', 0)} session(s)",
        provenance="imported floorsheet_trades (app DB)",
        data=data,
    )


def _tool_news(store, conn, symbol, question) -> ToolResult:
    from megatool.news import news_summary

    data = news_summary(symbol=symbol)
    items = int((data.get("totals") or {}).get("items", 0) or 0)
    if items == 0:
        return ToolResult(
            tool="news",
            status="blocked",
            private=False,
            summary="",
            reason="no authorized live-news source (blocker L4) and no imported "
            "records for this scope",
            data=data,
        )
    return ToolResult(
        tool="news",
        status="ok",
        private=False,
        summary=f"{items} imported item(s); latest {data['totals'].get('last_published')}",
        provenance="imported news records only (never fabricated)",
        data=data,
    )


def _tool_journal(store, conn, symbol, question) -> ToolResult:
    from megatool.journal import journal_stats

    data = journal_stats()
    closed = int(data.get("closed", 0) or 0)
    return ToolResult(
        tool="journal",
        status="ok" if closed else "empty",
        private=True,
        summary=f"{closed} closed journal entr{'y' if closed == 1 else 'ies'}"
        if closed
        else "no closed journal entries yet",
        provenance="local journal (SQLite app DB); private",
        reason=None if closed else "no closed entries to compute statistics from",
        data=data,
    )


def _tool_backtest(store, conn, symbol, question) -> ToolResult:
    return ToolResult(
        tool="backtest",
        status="blocked",
        private=False,
        summary="",
        reason="a backtest needs explicit parameters (symbol, window, costs); "
        "call /api/backtest with stated parameters — the agent never "
        "invents a strategy configuration",
    )


_DISPATCH = {
    "research": _tool_research,
    "scanner": _tool_scanner,
    "portfolio_risk": _tool_portfolio_risk,
    "regime": _tool_regime,
    "fundamentals": _tool_fundamentals,
    "floorsheet": _tool_floorsheet,
    "news": _tool_news,
    "journal": _tool_journal,
    "backtest": _tool_backtest,
}


# ----------------------------------------------------------- AI interpretation
def build_interpretation_prompt(
    question: str, results: list[ToolResult], include_private: bool = False
) -> tuple[str, list[str]]:
    """Prompt from non-private tool results. Returns (prompt, excluded_tools).

    Private results are dropped from the prompt unless ``include_private`` —
    that flag is the caller's explicit authorization to include personal data.
    """
    excluded: list[str] = []
    blocks: list[str] = []
    for r in results:
        if r.private and not include_private:
            excluded.append(r.tool)
            continue
        payload = r.summary or r.reason or "(no output)"
        if r.provenance:
            payload += f"\nprovenance: {r.provenance}"
        if r.data is not None:
            blob = json.dumps(r.data, default=str, ensure_ascii=False)
            if len(blob) > PROMPT_DATA_BUDGET:
                blob = blob[:PROMPT_DATA_BUDGET] + "… [truncated]"
            payload += f"\ndata: {blob}"
        if r.reason:
            payload += f"\nlimitation: {r.reason}"
        blocks.append(f"## {r.tool} (deterministic tool output, status={r.status})\n{payload}")

    excluded_note = ""
    if excluded:
        excluded_note = (
            "\n[Private tool results excluded from your context: "
            + ", ".join(excluded)
            + ". Do not speculate about them.]"
        )
    prompt = (
        "You are the explanation layer of a personal research tool. Below are "
        "DETERMINISTIC tool outputs with provenance and limitations.\n\n"
        + ("\n\n".join(blocks) if blocks else "(no tool produced output)")
        + excluded_note
        + f"\n\nQuestion: {question}\n\n"
        "Explain the tool outputs in plain language. Rules: (1) every number "
        "you state must appear in the tool outputs; (2) if the outputs lack "
        "something the question asks, say it is missing; (3) this is an "
        "explanation of past data, not advice and not a prediction; (4) end "
        "with a one-line reminder that deterministic figures and your "
        "explanation are different things."
    )
    return prompt, excluded


def interpret(
    question: str,
    results: list[ToolResult],
    *,
    provider: str | None = None,
    include_private: bool = False,
    provider_instance: Any = None,
) -> dict[str, Any]:
    """Run the AI explanation step. Never raises; failures are statuses.

    ``provider_instance`` exists for tests (inject a stub); production passes
    the provider *name* and the real provider is built server-side, so no
    credential ever reaches the caller.
    """
    from megatool.llm import (
        DisabledProvider,
        LLMError,
        LLMNotConfigured,
        get_provider,
    )

    prompt, excluded = build_interpretation_prompt(question, results, include_private)
    base = {"private_excluded": bool(excluded), "excluded_tools": excluded}
    try:
        prov = provider_instance if provider_instance is not None else get_provider(provider)
        if isinstance(prov, DisabledProvider) and provider_instance is None:
            return {
                **base,
                "status": "disabled",
                "text": None,
                "reason": "no AI provider configured (set MEGATOOL_AI_PROVIDER)",
            }
        out = prov.complete(
            prompt,
            system=(
                "You explain deterministic analysis outputs. Never invent "
                "numbers. Never give buy/sell instructions."
            ),
            temperature=0.0,
        )
        return {
            **base,
            "status": "ok",
            "text": out.text,
            "provider": out.provider,
            "model": out.model,
            "note": "AI-generated explanation of the deterministic tool "
            "results above; it is not itself a calculation.",
        }
    except LLMNotConfigured as exc:
        return {**base, "status": "disabled", "text": None, "reason": str(exc)}
    except LLMError as exc:
        return {**base, "status": "unavailable", "text": None, "reason": str(exc)}
    except Exception as exc:  # provider stubs/network: never 500 the run
        return {
            **base,
            "status": "error",
            "text": None,
            "reason": f"{type(exc).__name__}: {exc}",
        }


# ---------------------------------------------------------------------- entry
def run(
    question: str,
    store: Any,
    conn: Any = None,
    *,
    provider: str | None = None,
    interpret_ai: bool = False,
    include_private: bool = False,
    tools: list[str] | None = None,
) -> dict[str, Any]:
    """Route a question to tools, run them, optionally explain — deterministically."""
    symbols = set(store.symbols(min_bars=1)) if hasattr(store, "symbols") else set()
    plan = list(tools) if tools else route(question, symbols)
    unknown = [t for t in plan if t not in TOOL_DEFS]
    if unknown:
        raise ValueError(f"unknown tool(s): {', '.join(unknown)}; known: {', '.join(TOOL_DEFS)}")
    sym = find_symbol(question, symbols)
    run_obj = AgentRun(question=question, plan=plan)
    for key in plan:
        run_obj.results.append(_run_tool(key, store, conn, sym, question))
    if interpret_ai:
        run_obj.ai = interpret(
            question, run_obj.results, provider=provider, include_private=include_private
        )
    else:
        run_obj.ai = None
    return run_obj.to_dict()


def tool_registry() -> list[dict[str, Any]]:
    """What the agent can do, including which tools are private."""
    return [
        {"tool": key, **{k: v for k, v in spec.items() if k != "keywords"}}
        for key, spec in TOOL_DEFS.items()
    ]


__all__ = [
    "AgentRun",
    "TOOL_DEFS",
    "ToolResult",
    "build_interpretation_prompt",
    "find_symbol",
    "interpret",
    "route",
    "run",
    "tool_registry",
    "DISCLAIMER",
]
