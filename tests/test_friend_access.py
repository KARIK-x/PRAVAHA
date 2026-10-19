"""Tests for the deny-by-default friend-facing access boundary.

These exercise the real middleware through a small FastAPI app so the ordering
with CORS and the 401/403 behaviour are tested end-to-end. No network is used.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from megatool import friend_access as fa

TOKEN = "friend-test-token-123"

SAFE_GET = "/api/quotes"  # on the allowlist
SAFE_POST = "/api/screen"  # on the allowlist
PERSONAL = "/api/journal/entries"  # personal → must be denied
ADMIN = "/api/fundamentals/import"  # write/admin → must be denied


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()

    @a.get(SAFE_GET)
    def _q():
        return {"ok": True}

    @a.post(SAFE_POST)
    def _s():
        return {"ok": True}

    @a.get(PERSONAL)
    def _j():
        return {"ok": True}

    @a.post(ADMIN)
    def _i():
        return {"ok": True}

    # The static frontend (non-/api/ paths) must be reachable without a token.
    @a.get("/")
    def _root():
        return "<!doctype html><title>PRAVAHA</title>"

    @a.get("/app.js")
    def _js():
        return "// pravaha app bundle"

    a.add_middleware(fa.FriendAccessMiddleware)
    return a


def _client(app, host):
    return TestClient(app, client=(host, 12345))


# ------------------------------------------------------------- pure predicates
def test_allowlist_permits_only_listed_routes():
    assert fa.friend_allowed("GET", SAFE_GET) is True
    assert fa.friend_allowed("POST", SAFE_POST) is True
    assert fa.friend_allowed("GET", "/api/bars/NABIL") is True
    assert fa.friend_allowed("GET", "/api/bars/NABIL/structure") is True
    # Published index series are public market data (read-only).
    assert fa.friend_allowed("GET", "/api/indices") is True
    assert fa.friend_allowed("GET", "/api/indices/NEPSE") is True
    assert fa.friend_allowed("GET", "/api/indices/Commercial Banks") is True
    # A multi-segment path under the index prefix is not the index route.
    assert fa.friend_allowed("GET", "/api/indices/NEPSE/../../portfolio") is False
    assert fa.friend_allowed("POST", "/api/indices") is False


def test_allowlist_denies_personal_write_and_admin_by_default():
    assert fa.friend_allowed("GET", PERSONAL) is False
    assert fa.friend_allowed("POST", ADMIN) is False
    assert fa.friend_allowed("GET", "/api/portfolio/holdings") is False
    assert fa.friend_allowed("GET", "/api/research/NABIL") is False
    assert fa.friend_allowed("GET", "/api/written-pdf/review") is False
    assert fa.friend_allowed("POST", "/api/agent/run") is False
    # Unknown routes are denied too.
    assert fa.friend_allowed("GET", "/api/anything-else") is False


def test_allowlist_is_method_sensitive():
    assert fa.friend_allowed("POST", "/api/quotes") is False  # not a POST route
    assert fa.friend_allowed("DELETE", "/api/screen") is False


def test_loopback_detection():
    assert fa.client_is_loopback("127.0.0.1") is True
    assert fa.client_is_loopback("::1") is True
    assert fa.client_is_loopback("localhost") is True
    assert fa.client_is_loopback("10.0.0.5") is False
    assert fa.client_is_loopback("testclient") is False
    assert fa.client_is_loopback(None) is False


def test_token_compare_is_constant_time_and_rejects_missing(monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    assert fa.token_matches(TOKEN) is True
    assert fa.token_matches("wrong") is False
    assert fa.token_matches("") is False
    assert fa.token_matches(None) is False


def test_extract_token_supports_both_header_forms():
    from starlette.datastructures import Headers

    assert fa.extract_token(Headers({"X-Friend-Token": TOKEN})) == TOKEN
    assert fa.extract_token(Headers({"Authorization": f"Bearer {TOKEN}"})) == TOKEN
    assert fa.extract_token(Headers({})) is None


# ------------------------------------------------------------- middleware e2e
def test_remote_client_without_token_is_401(app, monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    r = _client(app, "10.0.0.5").get(SAFE_GET)
    assert r.status_code == 401


def test_remote_client_with_valid_token_can_read_allowlisted_route(app, monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    r = _client(app, "10.0.0.5").get(SAFE_GET, headers={"X-Friend-Token": TOKEN})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_remote_client_with_valid_token_can_post_allowlisted_route(app, monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    r = _client(app, "10.0.0.5").post(SAFE_POST, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200


def test_remote_client_with_valid_token_is_403_on_personal_route(app, monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    r = _client(app, "10.0.0.5").get(PERSONAL, headers={"X-Friend-Token": TOKEN})
    assert r.status_code == 403


def test_remote_client_with_valid_token_is_403_on_admin_route(app, monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    r = _client(app, "10.0.0.5").post(ADMIN, headers={"X-Friend-Token": TOKEN})
    assert r.status_code == 403


def test_remote_client_with_wrong_token_is_401(app, monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    r = _client(app, "10.0.0.5").get(SAFE_GET, headers={"X-Friend-Token": "nope"})
    assert r.status_code == 401


def test_loopback_owner_is_never_challenged(app, monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    c = _client(app, "127.0.0.1")
    assert c.get(SAFE_GET).status_code == 200
    assert c.get(PERSONAL).status_code == 200  # the owner sees everything


def test_loopback_trust_can_be_disabled(app, monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    monkeypatch.setenv(fa.TRUST_LOOPBACK_ENV, "0")
    assert _client(app, "127.0.0.1").get(SAFE_GET).status_code == 401


def test_boundary_inactive_without_token(app, monkeypatch):
    monkeypatch.delenv(fa.FRIEND_TOKEN_ENV, raising=False)
    # Owner-only mode: deployment binds to loopback; nothing is exposed.
    assert _client(app, "10.0.0.5").get(SAFE_GET).status_code == 200


def test_denied_response_never_echoes_the_token(app, monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    r = _client(app, "10.0.0.5").get(PERSONAL, headers={"X-Friend-Token": TOKEN})
    assert TOKEN not in r.text


def test_route_table_is_serialisable_for_docs():
    table = fa.route_table()
    assert table and all({"method", "path"} <= set(row) for row in table)


# ------------------------------------------------ startup access-boundary notice
# The boundary is OFF until a friend token is set, so an owner-only process must
# be bound to loopback. The CLI warns on a non-loopback bind; the ASGI entrypoint
# (`uvicorn megatool.api:app`) bypasses the CLI, so the state is logged on every
# entrypoint. These tests pin that behaviour and, critically, that no secret is
# ever printed.


def _capture_boundary(monkeypatch, **env):
    import io
    from contextlib import redirect_stderr

    import megatool.api as api

    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    buf = io.StringIO()
    with redirect_stderr(buf):
        api._log_access_boundary()
    return buf.getvalue()


def test_startup_notice_flags_a_non_loopback_bind_without_a_token(monkeypatch):
    out = _capture_boundary(
        monkeypatch,
        MEGATOOL_HOST="0.0.0.0",
    )
    assert "WARNING" in out
    assert "NO authentication" in out
    # The notice must name the concrete remedy.
    assert "MEGATOOL_FRIEND_TOKEN" in out


def test_startup_notice_is_calm_on_loopback_without_a_token(monkeypatch):
    out = _capture_boundary(monkeypatch, MEGATOOL_HOST="127.0.0.1")
    assert "WARNING" not in out
    assert "owner-only" in out


def test_startup_notice_reports_the_boundary_once_a_token_exists(monkeypatch):
    out = _capture_boundary(monkeypatch, MEGATOOL_HOST="0.0.0.0", MEGATOOL_FRIEND_TOKEN=TOKEN)
    assert "ACTIVE" in out
    assert "WARNING" not in out
    # A secret must never be echoed into logs.
    assert TOKEN not in out


# ------------------------------------------- session-20 read/write boundaries
def test_relative_strength_is_friend_readable_like_its_siblings():
    """Read-only per-symbol analytics share one rule; RS must not be an outlier."""
    for name in (
        "structure",
        "fibonacci",
        "levels",
        "elliott",
        "harmonic",
        "patterns",
        "candles",
        "statistics",
        "relative-strength",
    ):
        assert fa.friend_allowed("GET", f"/api/bars/NABIL/{name}") is True, name


def test_template_catalogue_and_alert_writes_stay_owner_only():
    """New routes default to denied; nothing widened the boundary by accident."""
    assert fa.friend_allowed("GET", "/api/templates") is False
    assert fa.friend_allowed("GET", "/api/alerts/history") is False
    assert fa.friend_allowed("POST", "/api/alerts/acknowledge") is False
    assert fa.friend_allowed("POST", "/api/screens/propose") is False
    assert fa.friend_allowed("POST", "/api/screens") is False


# --------------------------------------------- fail-closed private records (2026-10-19)
def test_private_record_route_predicate():
    assert fa.private_record_route("/api/journal") is True
    assert fa.private_record_route("/api/journal/123") is True
    assert fa.private_record_route("/api/portfolio") is True
    assert fa.private_record_route("/api/portfolio/risk") is True
    assert fa.private_record_route("/api/written-pdf/review") is True
    assert fa.private_record_route("/api/planning") is True
    # A sibling path that merely shares a prefix is NOT private.
    assert fa.private_record_route("/api/journalism") is False
    assert fa.private_record_route("/api/quotes") is False
    assert fa.private_record_route("/api/health") is False


def test_remote_client_without_token_cannot_reach_private_records(app, monkeypatch):
    """In production mode a non-loopback client is refused on private records."""
    monkeypatch.delenv(fa.FRIEND_TOKEN_ENV, raising=False)
    monkeypatch.setenv(fa.REQUIRE_AUTH_ENV, "1")
    assert _client(app, "10.0.0.5").get(PERSONAL).status_code == 401
    assert _client(app, "10.0.0.5").post(ADMIN).status_code == 401


def test_private_records_are_owner_only_with_a_valid_token(app, monkeypatch):
    """A valid friend token still cannot read personal/admin routes."""
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    c = _client(app, "10.0.0.5")
    assert c.get(PERSONAL, headers={"X-Friend-Token": TOKEN}).status_code == 403
    assert c.post(ADMIN, headers={"X-Friend-Token": TOKEN}).status_code == 403


def test_owner_only_mode_preserves_local_development(app, monkeypatch):
    """With no token and no require-auth the boundary is skipped entirely.

    This is the documented owner-only mode (must bind loopback) and is what keeps
    local development and the test client working. Production sets
    MEGATOOL_REQUIRE_AUTH=1 to fail closed instead.
    """
    monkeypatch.delenv(fa.FRIEND_TOKEN_ENV, raising=False)
    monkeypatch.delenv(fa.REQUIRE_AUTH_ENV, raising=False)
    c = _client(app, "10.0.0.5")
    assert c.get(PERSONAL).status_code == 200
    # Not denied by the middleware (the app answers 404 — the route is undefined).
    assert c.get("/api/not-allowlisted").status_code not in (401, 403)


def test_loopback_owner_still_sees_private_records_without_a_token(app, monkeypatch):
    monkeypatch.delenv(fa.FRIEND_TOKEN_ENV, raising=False)
    monkeypatch.delenv(fa.REQUIRE_AUTH_ENV, raising=False)
    assert _client(app, "127.0.0.1").get(PERSONAL).status_code == 200


def test_require_auth_fails_closed_without_a_token(app, monkeypatch):
    """MEGATOOL_REQUIRE_AUTH=1 with no token denies every non-loopback request."""
    monkeypatch.delenv(fa.FRIEND_TOKEN_ENV, raising=False)
    monkeypatch.setenv(fa.REQUIRE_AUTH_ENV, "1")
    # A public, allowlisted route is still refused: fail closed, not open.
    assert _client(app, "10.0.0.5").get(SAFE_GET).status_code == 401
    assert _client(app, "10.0.0.5").get(PERSONAL).status_code == 401


def test_require_auth_keeps_loopback_owner_working(app, monkeypatch):
    monkeypatch.delenv(fa.FRIEND_TOKEN_ENV, raising=False)
    monkeypatch.setenv(fa.REQUIRE_AUTH_ENV, "1")
    assert _client(app, "127.0.0.1").get(SAFE_GET).status_code == 200
    assert _client(app, "127.0.0.1").get(PERSONAL).status_code == 200


def test_require_auth_with_token_serves_allowlisted_only(app, monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    monkeypatch.setenv(fa.REQUIRE_AUTH_ENV, "1")
    c = _client(app, "10.0.0.5")
    assert c.get(SAFE_GET, headers={"X-Friend-Token": TOKEN}).status_code == 200
    assert c.get(PERSONAL, headers={"X-Friend-Token": TOKEN}).status_code == 403


def test_require_auth_denies_a_non_allowlisted_route(app, monkeypatch):
    """A route that is not on the allowlist is refused once auth is required."""
    monkeypatch.setenv(fa.REQUIRE_AUTH_ENV, "1")
    monkeypatch.delenv(fa.FRIEND_TOKEN_ENV, raising=False)
    r = _client(app, "10.0.0.5").get("/api/not-allowlisted")
    assert r.status_code == 401  # no token → 401 before the allowlist is reached


def test_health_probe_is_public_even_when_auth_is_required(app, monkeypatch):
    """A hosting provider's health check must not 401 (it would roll back)."""
    monkeypatch.setenv(fa.REQUIRE_AUTH_ENV, "1")
    monkeypatch.delenv(fa.FRIEND_TOKEN_ENV, raising=False)
    r = _client(app, "10.0.0.5").get("/api/health")
    # The tiny fixture app defines no /api/health route, so 404 means the
    # middleware let it through (rather than refusing it with 401).
    assert r.status_code != 401


def test_require_auth_is_off_by_default(monkeypatch):
    monkeypatch.delenv(fa.REQUIRE_AUTH_ENV, raising=False)
    assert fa.require_auth() is False
    monkeypatch.setenv(fa.REQUIRE_AUTH_ENV, "1")
    assert fa.require_auth() is True
    monkeypatch.setenv(fa.REQUIRE_AUTH_ENV, "0")
    assert fa.require_auth() is False


# ------------------------------- static frontend + public market surface (2026-10-19)
def test_static_frontend_is_public_even_when_auth_is_required(app, monkeypatch):
    """The deployed site must load without a token; only the API is gated.

    Regression for the production defect where GET / returned
    {"error":"authentication required for friend access"} and the whole site
    failed to render.
    """
    monkeypatch.setenv(fa.REQUIRE_AUTH_ENV, "1")
    monkeypatch.delenv(fa.FRIEND_TOKEN_ENV, raising=False)
    c = _client(app, "10.0.0.5")
    assert c.get("/").status_code == 200
    assert c.get("/app.js").status_code == 200
    # The API is still gated: no token → 401.
    assert c.get(SAFE_GET).status_code == 401


def test_static_frontend_is_public_with_a_token_too(app, monkeypatch):
    monkeypatch.setenv(fa.FRIEND_TOKEN_ENV, TOKEN)
    c = _client(app, "10.0.0.5")
    assert c.get("/").status_code == 200
    assert c.get("/app.js").status_code == 200


def test_non_api_path_is_never_gated_even_without_a_boundary(app, monkeypatch):
    monkeypatch.delenv(fa.FRIEND_TOKEN_ENV, raising=False)
    monkeypatch.delenv(fa.REQUIRE_AUTH_ENV, raising=False)
    assert _client(app, "10.0.0.5").get("/").status_code == 200


def test_public_market_surface_is_readable_with_a_token():
    """Every public dashboard/chart route the frontend calls must be allowed."""
    for path in (
        "/api/market/dashboard",
        "/api/market/ribbon",
        "/api/breadth/history",
        "/api/seasonality/NABIL",
        "/api/indices/NEPSE/ohlc",
        "/api/indices/NEPSE/structure",
        "/api/bars/NABIL/swing-workbench",
        "/api/bars/NABIL/volume-profile",
        "/api/bars/NABIL/gaps",
        "/api/bars/NABIL/breakouts",
        "/api/bars/NABIL/trailing-stop",
        "/api/sectors",
        "/api/sastoshare/pulse",
        "/api/sastoshare/valuation/NABIL",
        "/api/fundamentals/NABIL/ttm-eps",
        "/api/fundamentals/eps-rankings",
        "/api/catalog/summary",
        "/api/catalog/scanner",
        "/api/catalog/tool/scanner/foo",
        "/api/ideas",
        "/api/corporate-events",
        "/api/market-intelligence/sources",
        "/api/kronos/status",
        "/api/screen/export.xlsx",
    ):
        assert fa.friend_allowed("GET", path) is True, path
    # Bounded compute stays available.
    assert fa.friend_allowed("POST", "/api/analysis/run") is True
    assert fa.friend_allowed("POST", "/api/forecast") is True


def test_expanded_allowlist_did_not_open_personal_data():
    """The wider public surface must not include any personal record route."""
    for path in (
        "/api/portfolio",
        "/api/journal",
        "/api/watchlists",
        "/api/screens",
        "/api/experiments",
        "/api/written-pdf/records",
        "/api/research/workspace/NABIL",
        "/api/agent/tools",
        "/api/snapshots",
        "/api/query/history",
        "/api/templates",
        "/api/kronos/experiments",
        "/api/reconciliation/datasets",
        "/api/research-desk/evidence",
    ):
        assert fa.private_record_route(path) is True, path
        assert fa.friend_allowed("GET", path) is False, path
        assert fa.friend_allowed("POST", path) is False, path


def test_startup_notice_fails_closed_when_require_auth_has_no_token(monkeypatch):
    out = _capture_boundary(
        monkeypatch,
        MEGATOOL_HOST="0.0.0.0",
        MEGATOOL_REQUIRE_AUTH="1",
        MEGATOOL_FRIEND_TOKEN=None,
    )
    assert "REQUIRE_AUTH" in out
    assert "CLOSED" in out.upper()
    assert "MEGATOOL_FRIEND_TOKEN" in out
