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


def boundary_active() -> bool:
    """The friend boundary is enforced only once a token is configured."""
    return friend_token() is not None


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
        if scope["type"] != "http" or not boundary_active():
            return await self.app(scope, receive, send)

        # CORS preflight carries no credentials by design; let CORSMiddleware
        # answer it. OPTIONS never discloses data.
        if scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)

        client = scope.get("client")
        host = client[0] if client else None
        if trust_loopback() and client_is_loopback(host):
            return await self.app(scope, receive, send)

        # Non-loopback: require a valid token, then the allowlist.
        headers = _Headers(scope.get("headers") or [])
        if not token_matches(extract_token(headers)):
            response = _deny(401, "authentication required for friend access")
        elif not friend_allowed(scope.get("method", "GET"), scope.get("path", "/")):
            response = _deny(403, "route not exposed for friend access")
        else:
            return await self.app(scope, receive, send)
        return await response(scope, receive, send)


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
