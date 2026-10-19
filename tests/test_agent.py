"""Focused tests for the research agent (feature 12) and AI interpretation (feature 1).

Synthetic fixtures only. The suite pins: deterministic routing, per-tool
statuses with honest reasons (blocked/empty never masquerade as ok), the
privacy contract (private results excluded from the AI prompt unless
explicitly authorized), the separation of tool results from AI interpretation,
and the API routes. No network is ever used; the AI step is tested with an
injected stub provider.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.agent import (
    TOOL_DEFS,
    ToolResult,
    build_interpretation_prompt,
    find_symbol,
    interpret,
    route,
    run,
    tool_registry,
)
from megatool.api import create_app
from megatool.db import init_app_db
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")
N_BARS = 60


def _bars(symbol: str, closes: np.ndarray) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": pd.bdate_range("2024-01-01", periods=n),
            "open": closes,
            "high": closes * 1.02,
            "low": closes * 0.98,
            "close": closes,
            "volume": np.full(n, 10_000, dtype=np.int64),
            "turnover": closes * 10_000,
            "source": "SYNTHETIC-TEST-FIXTURE",
            "retrieved_at": RETRIEVED,
            "validation_status": "valid",
        }
    )


@pytest.fixture
def env(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(_bars("ALPHA", 100.0 + np.arange(N_BARS, dtype=float)))
    store.upsert_bars(_bars("BETA", 200.0 - np.arange(N_BARS, dtype=float) * 0.5))
    app_db = tmp_path / "state.sqlite"
    init_app_db(app_db)
    yield store, app_db
    store.close()


class _StubProvider:
    """Captures the prompt; returns canned text. No network."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt, *, system=None, max_tokens=None, temperature=0.0):
        self.prompts.append(prompt)

        class _Out:
            text = "stub explanation of the deterministic results"
            provider = "stub"
            model = "stub-1"

        return _Out()


# -------------------------------------------------------------------- routing
def test_route_maps_keywords_to_tools():
    plan = route("analyze the trend and momentum of ALPHA")
    assert "research" in plan
    assert "scanner" not in plan
    assert "portfolio_risk" in route("what is my portfolio exposure and drawdown")
    assert "regime" in route("what regime is the market in")
    assert "news" in route("any news on ALPHA")
    assert route("") == [] and route("zzz unrelated") == []


def test_find_symbol_only_returns_stored_symbols():
    assert find_symbol("look at ALPHA and BETA", {"ALPHA", "BETA"}) == "ALPHA"
    # A symbol-shaped token that is not stored is never invented.
    assert find_symbol("look at GHOST", {"ALPHA"}) is None


def test_bare_symbol_question_still_routes_to_research():
    assert route("ALPHA", {"ALPHA"}) == ["research"]


# ------------------------------------------------------------------ tool runs
def test_run_research_result_has_provenance_and_as_of(env):
    store, app_db = env
    payload = run("analyze ALPHA trend", store, app_db)
    assert payload["plan"] == ["research"]
    res = payload["tool_results"][0]
    assert res["status"] == "ok" and res["private"] is False
    assert "stored price_bars for ALPHA" in res["provenance"]
    assert res["data"]["as_of"] is not None
    assert payload["ai_interpretation"] is None  # interpret off by default
    assert "disclaimer" in payload


def test_run_reports_blocked_tools_with_honest_reasons(env):
    store, app_db = env
    payload = run("news and floor sheet and backtest for ALPHA", store, app_db)
    by_tool = {r["tool"]: r for r in payload["tool_results"]}
    assert by_tool["news"]["status"] == "blocked"
    assert "no authorized live-news source" in by_tool["news"]["reason"]
    assert by_tool["floorsheet"]["status"] == "blocked"
    assert "data-rights" in by_tool["floorsheet"]["reason"]
    assert by_tool["backtest"]["status"] == "blocked"
    assert "explicit parameters" in by_tool["backtest"]["reason"]
    # Blocked reasons surface in unresolved so nothing is silently missing.
    assert any("news:" in u for u in payload["unresolved"])


def test_private_tools_are_flagged_and_returned_locally(env):
    store, app_db = env
    payload = run("my portfolio risk and journal stats", store, app_db)
    private = [r for r in payload["tool_results"] if r["private"]]
    assert {r["tool"] for r in private} == {"portfolio_risk", "journal"}
    # Privacy section names them even though the results are returned locally.
    assert set(payload["privacy"]["private_tools"]) == {"portfolio_risk", "journal"}
    assert payload["ai_interpretation"] is None


def test_unknown_tool_is_rejected_not_guessed(env):
    store, app_db = env
    with pytest.raises(ValueError, match="unknown tool"):
        run("anything", store, app_db, tools=["telepathy"])


def test_symbol_scoped_tool_without_symbol_is_blocked(env):
    store, app_db = env
    payload = run("fundamentals please", store, app_db)  # no stored symbol named
    by_tool = {r["tool"]: r for r in payload["tool_results"]}
    assert by_tool["fundamentals"]["status"] == "blocked"
    assert "needs a symbol" in by_tool["fundamentals"]["reason"]


# ---------------------------------------------------------- AI interpretation
def test_prompt_excludes_private_results_by_default():
    results = [
        ToolResult(
            tool="research",
            status="ok",
            private=False,
            summary="trend up",
            provenance="stored bars",
            data={"sma": 100},
        ),
        ToolResult(
            tool="journal", status="ok", private=True, summary="SECRET-THESIS", data={"closed": 3}
        ),
    ]
    prompt, excluded = build_interpretation_prompt("q", results, include_private=False)
    assert "SECRET-THESIS" not in prompt
    assert "journal" in prompt  # the EXCLUSION note names it
    assert excluded == ["journal"]
    assert "stored bars" in prompt


def test_prompt_includes_private_results_when_authorized():
    results = [
        ToolResult(
            tool="journal", status="ok", private=True, summary="SECRET-THESIS", data={"closed": 3}
        ),
    ]
    prompt, excluded = build_interpretation_prompt("q", results, include_private=True)
    assert "SECRET-THESIS" in prompt
    assert excluded == []


def test_interpret_separates_ai_from_tool_output_and_never_raises():
    results = [
        ToolResult(
            tool="regime",
            status="ok",
            private=False,
            summary="trend=bull",
            provenance="proxy",
            data={"current": {"trend": "bull"}},
        ),
        ToolResult(tool="portfolio_risk", status="ok", private=True, summary="PRIVATE-HOLDINGS"),
    ]
    stub = _StubProvider()
    ai = interpret("what regime", results, provider_instance=stub)
    assert ai["status"] == "ok" and ai["provider"] == "stub"
    assert "not itself a calculation" in ai["note"]
    assert ai["excluded_tools"] == ["portfolio_risk"]
    # The stub never saw the private summary.
    assert all("PRIVATE-HOLDINGS" not in p for p in stub.prompts)
    # The prompt did see the deterministic regime summary with provenance.
    assert "trend=bull" in stub.prompts[0] and "proxy" in stub.prompts[0]


def test_interpret_without_provider_is_disabled_not_an_error(env):
    store, app_db = env
    payload = run("analyze ALPHA trend", store, app_db, interpret_ai=True)
    ai = payload["ai_interpretation"]
    assert ai is not None
    assert ai["status"] == "disabled" and ai["text"] is None
    assert "MEGATOOL_AI_PROVIDER" in ai["reason"]
    # tool results are untouched by the failed AI step
    assert payload["tool_results"][0]["status"] == "ok"


def test_interpret_with_unknown_provider_name_is_an_error_status():
    ai = interpret("q", [], provider="no-such-provider")
    assert ai["status"] in ("disabled", "error", "unavailable")
    assert ai["text"] is None


# ------------------------------------------------------------------ API routes
def test_agent_tools_route_lists_private_flags(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    app = create_app(store=store)
    with TestClient(app) as client:
        d = client.get("/api/agent/tools").json()
        tools = {t["tool"]: t for t in d["tools"]}
        assert set(tools) == set(TOOL_DEFS)
        assert tools["portfolio_risk"]["private"] is True
        assert tools["research"]["private"] is False
    store.close()


def test_agent_run_route_end_to_end(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(_bars("ALPHA", 100.0 + np.arange(N_BARS, dtype=float)))
    init_app_db()  # isolated app DB (conftest points PATHS at tmp)
    app = create_app(store=store)
    with TestClient(app) as client:
        d = client.post("/api/agent/run", json={"question": "analyze ALPHA trend"}).json()
        assert d["plan"] == ["research"]
        assert d["tool_results"][0]["status"] == "ok"
        assert d["ai_interpretation"] is None
        # interpret=true with no provider configured → status, not a 500
        d2 = client.post(
            "/api/agent/run", json={"question": "analyze ALPHA trend", "interpret": True}
        )
        assert d2.status_code == 200
        assert d2.json()["ai_interpretation"]["status"] == "disabled"
        # validation: empty question and unknown tools are 400s
        assert client.post("/api/agent/run", json={"question": " "}).status_code == 400
        bad = client.post(
            "/api/agent/run",
            json={"question": "x", "tools": ["nope"]},
        )
        assert bad.status_code == 400
        assert "unknown tool" in bad.json()["detail"]
    store.close()


def test_research_ask_interpret_appends_without_replacing(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(_bars("ALPHA", 100.0 + np.arange(N_BARS, dtype=float)))
    init_app_db()
    app = create_app(store=store)
    with TestClient(app) as client:
        base = client.post(
            "/api/research/ask", json={"symbol": "ALPHA", "question": "trend"}
        ).json()
        with_ai = client.post(
            "/api/research/ask",
            json={"symbol": "ALPHA", "question": "trend", "interpret": True},
        ).json()
        # Deterministic payload identical; only the AI field is added.
        for key in ("findings", "symbol", "warnings"):
            assert with_ai.get(key) == base.get(key)
        assert "ai_interpretation" not in base
        assert with_ai["ai_interpretation"]["status"] == "disabled"
    store.close()


def test_tool_registry_contract():
    reg = tool_registry()
    assert len(reg) == len(TOOL_DEFS)
    for entry in reg:
        assert {"tool", "description", "needs_symbol", "private"} <= set(entry)
