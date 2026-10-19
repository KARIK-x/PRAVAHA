"""Friend-facing access boundary — explicit, deny-by-default.

The owner runs Mega Tool locally on loopback. Sharing read-only market views
with a friend means exposing a *small, named* slice of the API to a different
origin. This module defines that slice and enforces it.

MODEL
-----
* **Loopback (127.0.0.1/::1/localhost)** → the owner. Full access, unchanged.
* **Any other client** → a friend. Must present a valid shared read-only token
  (``X-Friend-Token`` or ``Authorization: Bearer``); the request must also match
  the explicit allowlist below. Unlisted routes are **denied by default**.

The boundary is only *enforced* once ``MEGATOOL_FRIEND_TOKEN`` is set. With no
token configured the process is owner-only and must bind to loopback (the app's
default host); the deployment doc states this explicitly. Nothing here turns the
boundary off — an unset token simply means "not exposed yet".

FAIL-CLOSED RULES (added 2026-10-19)
------------------------------------
The boundary is *active* when a token is configured **or** the deployment sets
``MEGATOOL_REQUIRE_AUTH=1`` (:func:`boundary_active`). When it is active, two
rules protect private data:

1. **Private records are owner-only.** Routes under :data:`FRIEND_DENIED_PREFIXES`
   (portfolio, journal, planning, alerts, watchlists, experiments, screens,
   written-pdf, research, agent, imports) are served to a **loopback** client
   only. A non-loopback client is refused with 401 (no token) or 403 (token
   present) — never served. The check is independent of the allowlist.
2. **Production fails closed.** ``MEGATOOL_REQUIRE_AUTH=1`` activates the
   boundary even with no token configured; :func:`token_matches` then rejects
   every request, so all non-loopback traffic is refused (401) rather than
   silently served. This is the switch a hosted deployment (e.g. Render) sets.

When the boundary is **inactive** (no token and no require-auth) the process is
owner-only and must bind loopback; enforcement is skipped so local development
and the test client keep full access. `/api/health` is always public so a
hosting provider's health check cannot be mistaken for an intruder.

CORS is NOT authentication. The allowlist and the token are.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import re

#: Shared read-only token. When set, the friend boundary is enforced.
FRIEND_TOKEN_ENV = "MEGATOOL_FRIEND_TOKEN"

#: The deployed frontend origin (e.g. https://<site>.netlify.app). Config placeholder.
FRIEND_ORIGIN_ENV = "MEGATOOL_FRIEND_ORIGIN"

#: Treat loopback as the owner even when a token is configured.
TRUST_LOOPBACK_ENV = "MEGATOOL_FRIEND_TRUST_LOOPBACK"

#: Production hardening switch. When set to "1" the friend boundary is enforced
#: even if no token is configured, so a hosted deployment fails closed instead
#: of silently serving every route to non-loopback clients.
REQUIRE_AUTH_ENV = "MEGATOOL_REQUIRE_AUTH"

#: EXPLICIT allowlist of (METHOD, path-regex) exposed to friend tokens.
#: Everything not listed here is denied for non-loopback clients.
FRIEND_ROUTES: tuple[tuple[str, str], ...] = (
    # meta / source health
    ("GET", r"^/api/health$"),
    ("GET", r"^/api/status$"),
    ("GET", r"^/api/sources$"),
    # quotes + reference data
    ("GET", r"^/api/quotes$"),
    ("GET", r"^/api/securities$"),
    # market snapshot / quality / regime
    ("GET", r"^/api/dashboard$"),
    ("GET", r"^/api/quality$"),
    ("GET", r"^/api/regime$"),
    ("GET", r"^/api/regime/history$"),
    # published index series (read-only market data)
    ("GET", r"^/api/indices$"),
    ("GET", r"^/api/indices/[A-Za-z0-9 ._&()+-]+$"),
    # per-symbol bars + analytics (read-only)
    ("GET", r"^/api/bars/[A-Za-z0-9._-]+$"),
    ("GET", r"^/api/bars/[A-Za-z0-9._-]+/(weekly|monthly)$"),
    (
        "GET",
        r"^/api/bars/[A-Za-z0-9._-]+/"
        r"(indicator|structure|fibonacci|levels|elliott|harmonic|patterns|candles|statistics"
        r"|relative-strength)$",
    ),
    ("GET", r"^/api/indicators$"),
    # descriptive statistics over public market data
    ("GET", r"^/api/stats/correlation$"),
    # screening / ranking / strategies / bounded compute
    ("GET", r"^/api/screen/presets$"),
    ("GET", r"^/api/screen/export\.csv$"),
    ("POST", r"^/api/screen$"),
    ("POST", r"^/api/rank$"),
    ("GET", r"^/api/strategies$"),
    ("POST", r"^/api/backtest$"),
    ("POST", r"^/api/walk-forward$"),
    # public fundamentals + floorsheet summaries
    ("GET", r"^/api/fundamentals/summary$"),
    ("GET", r"^/api/fundamentals/compare$"),
    ("GET", r"^/api/fundamentals/[A-Za-z0-9._-]+$"),
    ("GET", r"^/api/fundamentals/[A-Za-z0-9._-]+/ratios$"),
    ("GET", r"^/api/floorsheet/sessions$"),
    ("GET", r"^/api/floorsheet/summary$"),
    ("GET", r"^/api/floorsheet/trend$"),
    ("GET", r"^/api/forecast/models$"),
)

#: Always-public liveness probes. These disclose no private data and must answer
#: a hosting provider's HTTP health check even when the friend boundary is
#: active (a 401 would mark the deployment unhealthy and trigger a rollback).
PUBLIC_PROBES: tuple[str, ...] = ("/api/health",)

#: Documented as NEVER friend-facing (personal data / write / admin).
FRIEND_DENIED_PREFIXES: tuple[str, ...] = (
    "/api/portfolio",
    "/api/journal",
    "/api/planning",
    "/api/alerts",
    "/api/watchlists",
    "/api/experiments",
    "/api/screens",
    "/api/written-pdf",
    "/api/research",
    "/api/agent",
    "/api/news/import",
    "/api/fundamentals/import",
    "/api/floorsheet/import",
)

_COMPILED = tuple((method, re.compile(pattern)) for method, pattern in FRIEND_ROUTES)


def friend_allowed(method: str, path: str) -> bool:
    """True only when ``(method, path)`` is on the explicit allowlist."""
    return any(m == method.upper() and rx.match(path) for m, rx in _COMPILED)


def client_is_loopback(host: str | None) -> bool:
    """True for an actual loopback IP or ``localhost`` (never the test sentinel)."""
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def friend_token() -> str | None:
    token = os.environ.get(FRIEND_TOKEN_ENV)
    return token or None


def require_auth() -> bool:
    """True when the deployment demands authentication (production hardening).

    Set ``MEGATOOL_REQUIRE_AUTH=1`` on a hosted deployment. The boundary is then
    enforced even with no token configured, and a missing token means *deny*,
    not *allow* — the process fails closed rather than open.
    """
    return os.environ.get(REQUIRE_AUTH_ENV, "0").strip() == "1"


def boundary_active() -> bool:
    """The friend boundary is enforced once a token is configured **or** the
    deployment requires authentication (``MEGATOOL_REQUIRE_AUTH=1``)."""
    return friend_token() is not None or require_auth()


def private_record_route(path: str) -> bool:
    """True when ``path`` is a personal / write / admin route.

    These routes must never be served to a non-loopback client without a valid
    token, and are never served *with* one either — they are owner-only. The
    check matches the exact prefix or a child path, so ``/api/journal`` and
    ``/api/journal/123`` both match while ``/api/journalism`` does not.
    """
    for prefix in FRIEND_DENIED_PREFIXES:
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?"):
            return True
    return False


def trust_loopback() -> bool:
    return os.environ.get(TRUST_LOOPBACK_ENV, "1") != "0"


def token_matches(supplied: str | None) -> bool:
    """Constant-time compare; never logs the value."""
    expected = friend_token()
    if not expected or not supplied:
        return False
    return hmac.compare_digest(str(supplied), expected)


def extract_token(headers: object) -> str | None:
    """Pull the friend token from ``X-Friend-Token`` or ``Authorization: Bearer``."""
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    direct = getter("x-friend-token")
    if direct:
        return str(direct)
    auth = getter("authorization")
    if auth and str(auth).lower().startswith("bearer "):
        return str(auth)[7:].strip()
    return None


def friend_origin() -> str | None:
    origin = os.environ.get(FRIEND_ORIGIN_ENV)
    return origin.rstrip("/") if origin else None


def route_table() -> list[dict[str, str]]:
    """The allowlist as data, for docs/tests."""
    return [{"method": m, "path": p} for m, p in FRIEND_ROUTES]


def _deny(status_code: int, detail: str, extra: dict[str, str] | None = None):
    from starlette.responses import JSONResponse

    body: dict[str, object] = {"error": detail}
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status_code)


class FriendAccessMiddleware:
    """ASGI middleware enforcing the friend boundary (see module docstring).

    Written as a pure-ASGI middleware so it never buffers file/stream responses
    and needs no third-party base class.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Owner-only mode (no token, no require-auth): nothing is enforced, so a
        # local developer and the test client keep full access. Production must
        # set MEGATOOL_REQUIRE_AUTH=1 (see boundary_active) to fail closed.
        if scope["type"] != "http" or not boundary_active():
            return await self.app(scope, receive, send)

        # CORS preflight carries no credentials by design; let CORSMiddleware
        # answer it. OPTIONS never discloses data.
        if scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)

        path = scope.get("path", "/")

        # Liveness probes are always public (see PUBLIC_PROBES), so a hosting
        # provider's health check never 401s and triggers a rollback.
        if path in PUBLIC_PROBES:
            return await self.app(scope, receive, send)

        client = scope.get("client")
        host = client[0] if client else None
        if trust_loopback() and client_is_loopback(host):
            return await self.app(scope, receive, send)

        headers = _Headers(scope.get("headers") or [])
        authed = token_matches(extract_token(headers))

        # Private records are owner-only: never served to a non-loopback client,
        # with or without a valid token. This is independent of the allowlist, so
        # a route cannot be published by accident.
        if private_record_route(path):
            if authed:
                return await _deny(403, "route not exposed for friend access")(scope, receive, send)
            return await _deny(401, "authentication required for private records")(
                scope, receive, send
            )

        # Non-loopback: a valid token is required, then the explicit allowlist.
        # With require-auth on but no token configured, token_matches rejects
        # everything and the deployment fails closed.
        if not authed:
            return await _deny(401, "authentication required for friend access")(
                scope, receive, send
            )
        if not friend_allowed(scope.get("method", "GET"), path):
            return await _deny(403, "route not exposed for friend access")(scope, receive, send)

        return await self.app(scope, receive, send)


class _Headers:
    """Minimal case-insensitive header view over an ASGI header list."""

    def __init__(self, raw: list[tuple[bytes, bytes]]):
        self._map: dict[str, str] = {}
        for name, value in raw:
            self._map.setdefault(
                bytes(name).decode("latin-1").lower(), bytes(value).decode("latin-1")
            )

    def get(self, key: str, default=None):
        return self._map.get(key.lower(), default)
