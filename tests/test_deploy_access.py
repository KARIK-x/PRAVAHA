"""Deployment access regression tests (2026-10-19).

Reproduce the production defect on https://pravaha-hkwt.onrender.com:

* ``GET /`` returned ``{"error":"authentication required for friend access"}``
  (HTTP 401) because the friend-access middleware gated the *static frontend*,
  so the whole site failed to render.
* Once authenticated, the public dashboard/chart routes the frontend calls were
  not on the allowlist and answered 403.

These tests exercise the REAL application (``create_app``) through the friend
middleware with a production-like configuration, from a non-loopback client.
Nothing here touches real data: the shared conftest isolates both databases.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore

TOKEN = "deploy-regression-token"
REMOTE = ("203.0.113.7", 40000)  # TEST-NET-3: never loopback


@pytest.fixture
def prod_client(tmp_path, monkeypatch):
    """The real app, access-controlled exactly as the Render Blueprint sets it."""
    monkeypatch.setenv("MEGATOOL_REQUIRE_AUTH", "1")
    monkeypatch.setenv("MEGATOOL_FRIEND_TOKEN", TOKEN)
    monkeypatch.setenv("MEGATOOL_FRIEND_TRUST_LOOPBACK", "0")
    store = MarketStore(tmp_path / "market.duckdb")
    app = create_app(store=store)
    with TestClient(app, client=REMOTE) as c:
        yield c
    store.close()


def _auth():
    return {"X-Friend-Token": TOKEN}


# --------------------------------------------------------------- static frontend
def test_root_serves_the_dashboard_html(prod_client):
    r = prod_client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "PRAVAHA" in r.text


def test_static_assets_are_public(prod_client):
    for path in ("/app.js", "/styles.css", "/viz.js", "/vendor/lightweight-charts.standalone.js"):
        r = prod_client.get(path)
        assert r.status_code == 200, path


def test_root_is_public_without_any_token(prod_client):
    # No X-Friend-Token at all: the shell must still be served.
    assert prod_client.get("/").status_code == 200


# ------------------------------------------------------------------ health probe
def test_health_is_public(prod_client):
    r = prod_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] in ("ok", "degraded")


# ------------------------------------------------------------------ API gating
def test_api_requires_a_token(prod_client):
    assert prod_client.get("/api/status").status_code == 401
    assert prod_client.get("/api/market/dashboard").status_code == 401


def test_public_market_routes_work_with_a_token(prod_client):
    for path in (
        "/api/status",
        "/api/market/dashboard",
        "/api/market/ribbon",
        "/api/breadth/history",
        "/api/sectors",
        "/api/sastoshare/pulse",
        "/api/catalog/summary",
        "/api/indices",
    ):
        r = prod_client.get(path, headers=_auth())
        assert r.status_code == 200, f"{path} -> {r.status_code}"


def test_missing_market_data_is_an_honest_404_not_a_block(prod_client):
    """An empty store yields 404 'no stored history' — data, not auth, not route."""
    r = prod_client.get("/api/bars/NABIL", headers=_auth())
    assert r.status_code == 404
    assert "no stored history" in r.json()["detail"].lower()


# ------------------------------------------------------- private records guarded
@pytest.mark.parametrize(
    "path",
    [
        "/api/portfolio",
        "/api/journal",
        "/api/watchlists",
        "/api/screens",
        "/api/written-pdf/records",
        "/api/research/workspace/NABIL",
        "/api/snapshots",
        "/api/query/history",
        "/api/templates",
    ],
)
def test_private_records_stay_owner_only(prod_client, path):
    # A valid friend token must NOT unlock personal data.
    assert prod_client.get(path, headers=_auth()).status_code == 403, path
    # Without a token it is a plain 401.
    assert prod_client.get(path).status_code == 401, path


def test_unknown_api_route_is_denied_by_default(prod_client):
    # Deny-by-default is preserved: an unlisted route is refused, not served.
    assert prod_client.get("/api/not-a-real-route", headers=_auth()).status_code == 403


def test_private_write_is_not_reachable_with_a_token(prod_client):
    assert prod_client.post("/api/fundamentals/import", headers=_auth(), json={"text": "x"}).status_code == 403


# ----------------------------------------------------- split-deployment config
def test_netlify_proxies_api_and_never_rewrites_it_to_index_html():
    """The Netlify frontend must reach the Render API, and an API 404 must stay a
    JSON 404 — a `/* -> index.html` SPA rewrite would turn it into the HTML shell.
    """
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    cfg = tomllib.loads((root / "netlify.toml").read_text(encoding="utf-8"))
    redirects = cfg.get("redirects", [])

    api = [r for r in redirects if r.get("from") == "/api/*"]
    assert api, "the /api/* proxy is missing; the Netlify frontend would 404 every API call"
    assert api[0]["to"].endswith("/api/:splat")
    assert api[0]["status"] == 200

    for r in redirects:
        assert not (
            r.get("from") == "/*" and "index.html" in str(r.get("to", ""))
        ), "a /* -> index.html rewrite would swallow API responses as HTML"

    # The frontend keeps the API base empty (same-origin) and relies on the proxy.
    html = (root / "web/static/index.html").read_text(encoding="utf-8")
    assert 'name="megatool-api-base" content=""' in html


def test_static_tree_has_no_api_path_that_would_shadow_the_proxy():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    assert not (root / "web/static/api").exists()
    assert not (root / "web/static/_redirects").exists()
