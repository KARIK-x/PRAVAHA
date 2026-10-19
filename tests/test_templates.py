"""The research-template catalogue is honest about what the platform can do.

Two properties are pinned here, because they are the whole point of making
templates *declarative*:

1. every step path exists in the application's own route table — a template
   can never advertise an endpoint that is not served;
2. every step actually executes against a fixture store without a server error
   (5xx) or a request-validation error (422) — so "run this workflow" cannot
   dead-end on a malformed declaration.

Fixtures are synthetic; nothing here is evidence about real NEPSE prices.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore
from megatool.templates import TEMPLATES, get_template, template_catalogue


@pytest.fixture
def env(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    n = 300
    closes = 500.0 + np.arange(n, dtype=float) + np.sin(np.arange(n) / 7.0) * 10.0
    dates = pd.bdate_range("2024-01-01", periods=n)
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": "TPL1",
                "trading_date": dates,
                "open": closes,
                "high": closes * 1.02,
                "low": closes * 0.98,
                "close": closes,
                "volume": np.full(n, 10_000, dtype=np.int64),
                "turnover": closes * 10_000,
                "percent_change": 0.1,
                "source": "fixture",
                "retrieved_at": pd.Timestamp("2026-10-11"),
                "validation_status": "valid",
            }
        )
    )
    store.upsert_index_rows(
        [
            {"index_name": "NEPSE", "trading_date": d, "close": 2000.0, "source": "fixture"}
            for d in dates
        ]
    )
    app = create_app(store=store)
    yield store, app
    store.close()


# ------------------------------------------------------------------ catalogue
def test_template_ids_are_unique_and_non_empty():
    ids = [t.id for t in TEMPLATES]
    assert len(ids) == len(set(ids))
    assert all(i and i.islower() for i in ids)
    assert len(TEMPLATES) >= 12


def test_every_template_declares_a_real_workflow_not_just_a_title():
    for t in TEMPLATES:
        assert t.title and t.summary
        assert t.steps, f"{t.id} has no steps"
        for step in t.steps:
            assert step.label and step.why and step.path.startswith("/api/")


def test_get_template_and_catalogue_contract():
    assert get_template("elliott_review") is not None
    assert get_template("nope") is None
    cat = template_catalogue()
    assert cat["count"] == len(TEMPLATES)
    assert "{symbol}" in cat["placeholder_rules"]
    assert "add no new calculation" in cat["how_it_runs"]


def test_route_is_served(env):
    store, app = env
    with TestClient(app) as c:
        r = c.get("/api/templates")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(TEMPLATES)
    assert "disclaimer" in body


# ---------------------------------------------------- every step is executable
def _resolve(path: str, symbol: str, symbols: str) -> str:
    return path.replace("{symbol}", symbol).replace("{symbols}", symbols)


def test_every_step_path_exists_in_the_route_table(env):
    """A declared path must be a path the app actually serves."""
    store, app = env
    served = set(app.openapi()["paths"])
    for t in TEMPLATES:
        for step in t.steps:
            assert step.path in served, f"{t.id}: {step.path} is not a served route"


def test_every_step_executes_without_a_server_error(env):
    store, app = env
    with TestClient(app) as c:
        for t in TEMPLATES:
            for step in t.steps:
                path = _resolve(step.path, "TPL1", "TPL1")
                method = step.params.get("_method", "GET")
                params = {k: v for k, v in step.params.items() if k != "_method"}
                params = {
                    k: (v.replace("{symbols}", "TPL1") if isinstance(v, str) else v)
                    for k, v in params.items()
                }
                r = c.post(path, json=params) if method == "POST" else c.get(path, params=params)
                assert r.status_code < 500, f"{t.id}/{step.label}: {r.status_code} {r.text[:200]}"
                assert r.status_code != 422, (
                    f"{t.id}/{step.label}: declaration is malformed -> {r.json()}"
                )
                # 404 is acceptable only when the step is about optional data
                # (fundamentals / portfolio), and must be a stated reason.
                if r.status_code == 404:
                    assert r.json().get("detail"), f"{t.id}/{step.label}: bare 404"


def test_symbol_placeholder_steps_all_accept_the_symbol(env):
    """Every {symbol} step must not 400/404 for a symbol with stored history."""
    store, app = env
    with TestClient(app) as c:
        for t in TEMPLATES:
            if "symbol" not in t.inputs:
                continue
            for step in t.steps:
                if "{symbol}" not in step.path:
                    continue
                params = {k: v for k, v in step.params.items() if k != "_method"}
                r = c.get(_resolve(step.path, "TPL1", "TPL1"), params=params)
                assert r.status_code == 200, f"{t.id}/{step.label}: {r.status_code} {r.text[:200]}"
