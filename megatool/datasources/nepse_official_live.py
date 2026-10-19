"""NEPSE official market-data client (live intraday) — AUTHORIZATION-PENDING.

WHAT THIS IS
------------
A read-only Python client for the official Nepal Stock Exchange web API rooted
at ``https://nepalstock.com.np/api/nots`` — the same interface the public
``VoidArchive/go-nepse`` Go library wraps and the one YONEPSE republishes.

HOW THE EXCHANGE'S TOKEN WORKS (verified live 2026-10-15)
---------------------------------------------------------
The site is an Angular SPA that hands *every anonymous visitor* a bootstrap
token:

1. ``GET /api/authenticate/prove`` returns ``salt1..salt5`` and an
   ``accessToken`` with junk characters inserted at positions that are computed
   client-side by an obfuscation routine the site ships as a tiny WASM module.
2. The junk positions are derived from **only ``salt2``**: take its last three
   decimal digits ``d1,d2,d3``, look up ``TABLE[d1+d2+d3]`` (``T``), and the
   five positions to strip are ``T+22``, ``d2+d3+T+32``, ``d2+d3+T+60``,
   ``d2+T+88``, ``d3+T+110``.
3. The stripped token is sent as ``Authorization: Salter <token>``.

This table/formula is a *bit-for-bit* reimplementation of the ``css.wasm``
module embedded in go-nepse (validated against the real WASM via ``pywasm``
during development; see ``tests/test_datasources_nepse_official_live.py``).

No user credentials are involved and nothing is forged or stolen: the token is
the one the exchange gives an anonymous browser. TLS certificate verification
is **always on** (``verify=True``); the exchange's certificate is currently
valid (``CN=www.nepalstock.com.np``, expires 2026-12-10), so go-nepse's
documented ``TLSVerification = false`` workaround is NOT needed and NOT used.

AUTHORIZATION — READ BEFORE ENABLING
------------------------------------
The API is *undocumented* and the token generator is *obfuscated anti-automation
code*. Public reachability is not permission. The project therefore treats
automated use as an **owner authorization decision**, exactly as
``nepalstock_official.py`` documents (Rule 9). Every network method here
refuses to run unless ``MEGATOOL_NEPSE_API_AUTHORIZED=1`` is set, and the
project deliberately wires this client to **no** scheduled or automatic path.

Enable it only after you have made that call yourself.
"""

from __future__ import annotations

import os
import random
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx

#: Provenance string recorded on every stored quote.
SOURCE_LIVE_MARKET = "nepalstock.com.np/api/nots/lives-market"
SOURCE_INDICES = "nepalstock.com.np/api/nots/nepse-index"

BASE_URL = "https://nepalstock.com.np"
PROVE_PATH = "/api/authenticate/prove"
AUTH_ENV = "MEGATOOL_NEPSE_API_AUTHORIZED"

#: The exchange rejects tokens older than ~60s; refresh at 45s (same as go-nepse).
TOKEN_TTL_SECONDS = 45.0

#: Upper bound on a server-supplied ``Retry-After`` (never sleep for minutes).
MAX_RETRY_AFTER_SECONDS = 60.0

#: Browser-like headers. The exchange returns 401 to some non-browser agents.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": BASE_URL + "/",
}

#: Lookup table lifted from go-nepse ``internal/auth/css.wasm`` (39 int32 values).
_TOKEN_INDEX_TABLE = (
    5,
    8,
    4,
    7,
    9,
    4,
    6,
    9,
    5,
    5,
    6,
    5,
    3,
    5,
    4,
    4,
    9,
    6,
    6,
    8,
    8,
    6,
    8,
    6,
    5,
    8,
    4,
    9,
    5,
    9,
    8,
    5,
    3,
    4,
    7,
    7,
    4,
    7,
    3,
)


class NepseOfficialError(RuntimeError):
    """Something went wrong talking to the NEPSE official API."""


class NepseOfficialNotAuthorized(NepseOfficialError):
    """Raised when a network call is attempted without owner authorization."""


class NepseOfficialAuthError(NepseOfficialError):
    """A genuine authorization failure (401/403) that must not be retried."""


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Stop hammering a failing source, then probe once before resuming.

    ``closed`` → normal; after ``failure_threshold`` consecutive failures it
    trips to ``open`` and refuses calls; after ``recovery_timeout`` seconds it
    becomes ``half_open`` and permits ``half_open_max_calls`` probe(s); a probe
    success closes it, a probe failure re-opens it. The clock is injectable so
    tests need no sleeping.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        clock: Any = time.monotonic,
    ):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_calls = 0
        self._last_error: str | None = None

    @property
    def state(self) -> CircuitState:
        if self._state is CircuitState.OPEN and self._elapsed() >= self.recovery_timeout:
            # Time to try one probe.
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 0
        return self._state

    def _elapsed(self) -> float:
        return 0.0 if self._opened_at is None else self._clock() - self._opened_at

    def allow(self) -> bool:
        """True if a call may proceed now (consuming a half-open probe slot)."""
        state = self.state
        if state is CircuitState.CLOSED:
            return True
        if state is CircuitState.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        return False

    def record_success(self) -> None:
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = None
        self._half_open_calls = 0
        self._last_error = None

    def record_failure(self, error: Any = None) -> None:
        self._failures += 1
        if error is not None:
            self._last_error = str(error)[:200]
        if self._state is CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
            self._half_open_calls = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": str(self.state),
            "failures": self._failures,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout,
            "last_error": self._last_error,
        }


# ------------------------------------------------------------------ token math
def strip_positions(salt2: int) -> list[int]:
    """Return the five character positions to strip from ``accessToken``.

    Derivation validated bit-for-bit against go-nepse's embedded ``css.wasm``.
    Only ``salt2`` participates.
    """
    d1 = salt2 % 10
    d2 = (salt2 // 10) % 10
    d3 = (salt2 // 100) % 10
    t = _TOKEN_INDEX_TABLE[d1 + d2 + d3]
    return [t + 22, d2 + d3 + t + 32, d2 + d3 + t + 60, d2 + t + 88, d3 + t + 110]


def _strip(token: str, positions: list[int]) -> str:
    drop = {p for p in positions if 0 <= p < len(token)}
    return "".join(c for i, c in enumerate(token) if i not in drop)


def decode_access_token(prove: dict[str, Any]) -> str:
    """Decode the stripped bearer token from a ``/api/authenticate/prove`` body."""
    try:
        token = str(prove["accessToken"])
        salt2 = int(prove["salt2"])
    except (KeyError, TypeError, ValueError) as exc:
        raise NepseOfficialError(f"malformed prove response: {exc}") from exc
    return _strip(token, strip_positions(salt2))


# ------------------------------------------------------------------- helpers
def _finite(value: Any) -> float | None:
    """Coerce to a finite float, or ``None`` for missing/non-finite input."""
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / ±inf
        return None
    return f


def _finite_int(value: Any) -> int | None:
    f = _finite(value)
    if f is None or f < 0:
        return None
    return int(f)


def _parse_npt_timestamp(value: Any) -> datetime | None:
    """Parse a naive Nepal-local (UTC+05:45) timestamp like ``2026-10-15T15:00:00``."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt


# -------------------------------------------------------------------- client
class NepseOfficialLiveClient:
    """Read-only client for the NEPSE official API. Authorization-gated.

    Construction performs no network I/O. Every method that touches the network
    first calls :meth:`_require_authorized`, which raises unless
    ``MEGATOOL_NEPSE_API_AUTHORIZED=1`` (or ``authorized=True`` was passed).
    """

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        timeout: float = 20.0,
        authorized: bool | None = None,
        http: httpx.Client | None = None,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        jitter: bool = True,
        breaker: CircuitBreaker | None = None,
        sleep: Any = time.sleep,
        check_certificate: bool | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        if authorized is None:
            authorized = os.environ.get(AUTH_ENV) == "1"
        self._authorized = bool(authorized)
        self._max_retries = max_retries
        self._backoff = backoff_seconds
        self._jitter = jitter
        self._breaker = breaker if breaker is not None else CircuitBreaker()
        self._sleep = sleep
        if http is not None:
            self._http = http
            self._owns_http = False
        else:
            # verify=True is explicit and non-negotiable: it is never disabled.
            self._http = httpx.Client(
                timeout=timeout, follow_redirects=True, verify=True, headers=_HEADERS
            )
            self._owns_http = True
        # Certificate checks do their own verified handshake, so only the real,
        # self-owned client does them (an injected client — tests/mocks — never).
        self._check_cert = self._owns_http if check_certificate is None else check_certificate
        self._cert: dict[str, Any] | None = None
        self._cert_attempted = False
        self._token: str | None = None
        self._token_at: float = 0.0

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> NepseOfficialLiveClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- gate --------------------------------------------------------------
    def _require_authorized(self) -> None:
        if not self._authorized:
            raise NepseOfficialNotAuthorized(
                "NEPSE official API access is not authorized in this environment. "
                f"Set {AUTH_ENV}=1 only after making an explicit owner decision "
                "(undocumented API + obfuscated token generator; public reachability "
                "is not permission)."
            )

    # -- token -------------------------------------------------------------
    def _access_token(self, *, force: bool = False) -> str:
        self._require_authorized()
        now = time.monotonic()
        if not force and self._token and (now - self._token_at) < TOKEN_TTL_SECONDS:
            return self._token
        resp = self._http.get(self.base_url + PROVE_PATH)
        if resp.status_code != 200:
            raise NepseOfficialError(f"prove failed: HTTP {resp.status_code}")
        token = decode_access_token(resp.json())
        self._token = token
        self._token_at = now
        return token

    # -- certificate -------------------------------------------------------
    @property
    def certificate(self) -> dict[str, Any] | None:
        """Peer-certificate info captured on the first authorized fetch."""
        return self._cert

    def _maybe_check_certificate(self) -> None:
        """Read the peer certificate once per client run (never breaks a fetch)."""
        if self._cert_attempted or not self._check_cert:
            return
        self._cert_attempted = True
        try:
            from urllib.parse import urlparse

            from megatool.source_health import certificate_info

            host = urlparse(self.base_url).hostname or ""
            if host:
                self._cert = certificate_info(host, timeout=self.timeout)
        except Exception:  # noqa: BLE001 - a cert probe must never fail a fetch
            self._cert = None

    # -- retry helpers -----------------------------------------------------
    def _sleep_backoff(self, attempt: int) -> None:
        delay = self._backoff * (2**attempt)
        if self._jitter:
            delay *= random.uniform(0.5, 1.5)
        self._sleep(delay)

    def _retry_after(self, resp: httpx.Response, attempt: int) -> float:
        raw = resp.headers.get("Retry-After")
        if raw:
            try:
                return max(0.0, min(float(raw), MAX_RETRY_AFTER_SECONDS))
            except ValueError:
                pass  # HTTP-date form is not parsed; fall back to backoff
        return self._backoff * (2**attempt)

    # -- request core ------------------------------------------------------
    def _get_json(self, path: str) -> Any:
        """Authenticated GET: circuit-broken, bounded retry, distinct error classes.

        * TLS/network failures, 5xx and timeouts → backoff+jitter and retry;
        * 429 → honour ``Retry-After`` (capped) then retry;
        * 401 → one token refresh; a second 401, or any 403, is an authorization
          failure and is **not** retried;
        * non-JSON body → fail without retrying (malformed, not transient);
        * refusal to call at all while the breaker is open.
        """
        self._require_authorized()
        if not self._breaker.allow():
            raise NepseOfficialError(
                f"circuit breaker is {self._breaker.state} — refusing to call {path}"
            )
        url = self.base_url + path
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                token = self._access_token(force=attempt > 0)
            except NepseOfficialError as exc:
                self._breaker.record_failure(exc)
                raise
            try:
                resp = self._http.get(url, headers={"Authorization": "Salter " + token})
            except httpx.HTTPError as exc:  # network or TLS failure → retry
                self._breaker.record_failure(exc)
                last_exc = exc
                self._sleep_backoff(attempt)
                continue

            code = resp.status_code
            if code in (401, 403):
                if code == 401 and attempt == 0:
                    # Token expired between prove and use — refresh, do not retry
                    # an authorization failure.
                    self._token = None
                    continue
                self._breaker.record_failure(f"HTTP {code}")
                raise NepseOfficialAuthError(f"HTTP {code} for {path} (not retried)")
            if code == 429:
                self._breaker.record_failure("HTTP 429")
                last_exc = NepseOfficialError("HTTP 429")
                self._sleep(self._retry_after(resp, attempt))
                continue
            if code >= 500:
                self._breaker.record_failure(f"HTTP {code}")
                last_exc = NepseOfficialError(f"HTTP {code}")
                self._sleep_backoff(attempt)
                continue
            if code != 200:
                self._breaker.record_failure(f"HTTP {code}")
                raise NepseOfficialError(f"HTTP {code} for {path}")
            try:
                data = resp.json()
            except ValueError as exc:
                self._breaker.record_failure("non-JSON")
                raise NepseOfficialError(f"non-JSON response for {path}") from exc

            self._breaker.record_success()
            self._maybe_check_certificate()
            return data
        raise NepseOfficialError(f"request to {path} failed: {last_exc}")

    def breaker_snapshot(self) -> dict[str, Any]:
        return self._breaker.snapshot()

    # -- endpoints (paths from go-nepse DefaultEndpoints) ------------------
    def market_status(self) -> dict[str, Any]:
        """``isOpen`` / ``asOf`` / ``id`` — the exchange's own open/close flag."""
        return self._get_json("/api/nots/nepse-data/market-open")

    def market_summary(self) -> dict[str, float | None]:
        """Aggregate turnover/shares/transactions/capitalisation for the day."""
        items = self._get_json("/api/nots/market-summary")
        out: dict[str, float | None] = {}
        for item in items or []:
            out[str(item.get("detail", "")).strip()] = _finite(item.get("value"))
        return out

    def indices(self) -> list[dict[str, Any]]:
        """Raw index board (NEPSE composite + Sensitive/Float, id 57/58/62/63)."""
        rows = self._get_json("/api/nots/nepse-index")
        return list(rows or [])

    def live_market(self) -> list[dict[str, Any]]:
        """Intraday quote board for all actively traded securities.

        Returns ``[]`` outside market hours — that is the exchange's own answer,
        not an error, and callers must not present it as a live board.
        """
        rows = self._get_json("/api/nots/lives-market")
        return list(rows or [])

    def securities(self) -> list[dict[str, Any]]:
        rows = self._get_json("/api/nots/security?nonDelisted=true")
        return list(rows or [])

    def companies(self) -> list[dict[str, Any]]:
        rows = self._get_json("/api/nots/company/list")
        return list(rows or [])


# ------------------------------------------------------------------ converters
def live_market_to_quote_rows(
    records: list[dict[str, Any]],
    *,
    retrieved_at: datetime | None = None,
    source: str = SOURCE_LIVE_MARKET,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Convert NEPSE ``lives-market`` records into ``market_quotes`` rows.

    Same contract as the YONEPSE converter: never invent a value.

    * no symbol → rejected (``no_symbol``);
    * no parseable ``lastUpdatedDateTime`` → rejected (``missing_timestamp``)
      because freshness cannot be asserted without the source's own clock;
    * missing ``lastTradedPrice`` → ``NULL`` + ``validation_status='missing'``
      (unavailable ≠ valid 0);
    * non-positive / non-finite ``lastTradedPrice`` → ``NULL`` + ``'invalid'``;
    * ``high < low`` → ``'suspect'``.

    ``change`` is derived only when both LTP and previous close are present
    (arithmetic on source fields, never an invented price); otherwise ``NULL``.
    """
    stamp = (retrieved_at or datetime.now(UTC)).replace(tzinfo=None)
    stats = {
        "records_in": 0,
        "rows_out": 0,
        "no_symbol": 0,
        "missing_timestamp": 0,
        "missing_ltp": 0,
        "invalid_ltp": 0,
        "suspect": 0,
    }
    rows: list[dict[str, Any]] = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        stats["records_in"] += 1
        symbol = str(rec.get("symbol") or "").strip().upper()
        if not symbol:
            stats["no_symbol"] += 1
            continue
        ts = _parse_npt_timestamp(rec.get("lastUpdatedDateTime"))
        if ts is None:
            stats["missing_timestamp"] += 1
            continue

        ltp = _finite(rec.get("lastTradedPrice"))
        prev = _finite(rec.get("previousClose"))
        status = "valid"
        if ltp is None:
            status = "missing"
            stats["missing_ltp"] += 1
        elif ltp <= 0:
            status = "invalid"
            ltp = None
            stats["invalid_ltp"] += 1

        low = _finite(rec.get("lowPrice"))
        high = _finite(rec.get("highPrice"))
        if high is not None and low is not None and high < low:
            if status == "valid":
                status = "suspect"
            stats["suspect"] += 1

        change = None
        if ltp is not None and prev is not None:
            change = round(ltp - prev, 4)

        rows.append(
            {
                "symbol": symbol,
                "quote_date": ts.date().isoformat(),
                "ltp": ltp,
                "previous_close": prev,
                "high": high,
                "low": low,
                "change": change,
                "percent_change": _finite(rec.get("percentageChange")),
                "volume": _finite_int(rec.get("totalTradeQuantity")),
                "turnover": _finite(rec.get("totalTradeValue")),
                "trades": None,
                "market_cap": None,
                "name": (rec.get("securityName") or "").strip() or None,
                "source": source,
                "source_updated_at": ts.isoformat(timespec="seconds"),
                "retrieved_at": stamp.isoformat(timespec="seconds"),
                "validation_status": status,
            }
        )
    stats["rows_out"] = len(rows)
    return rows, stats


#: Exchange index ids → the names used elsewhere in Mega Tool.
_INDEX_ID_NAMES = {
    58: "NEPSE",
    57: "Sensitive Index",
    62: "Float Index",
    63: "Sensitive Float Index",
}


def indices_to_index_rows(
    records: list[dict[str, Any]],
    *,
    retrieved_at: datetime | None = None,
    source: str = SOURCE_INDICES,
) -> list[dict[str, Any]]:
    """Convert the official index board into ``index_series`` rows.

    NOTE ON PROVENANCE: rows are keyed ``(index_name, trading_date)`` by the
    store, so importing official ``NEPSE`` values will overwrite a same-day
    value imported from another source. This converter is provided for explicit,
    auditable use and is deliberately **not** wired into any ingest script.
    """
    stamp = (retrieved_at or datetime.now(UTC)).replace(tzinfo=None)
    out: list[dict[str, Any]] = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        ts = _parse_npt_timestamp(rec.get("generatedTime"))
        close = _finite(rec.get("close"))
        if ts is None or close is None or close <= 0:
            continue
        idx_id = rec.get("id")
        name = _INDEX_ID_NAMES.get(idx_id) if isinstance(idx_id, int) else None
        if name is None:
            name = str(rec.get("index") or "").strip() or None
        if name is None:
            continue
        out.append(
            {
                "index_name": name,
                "trading_date": ts.date().isoformat(),
                "close": close,
                "source": source,
                "retrieved_at": stamp.isoformat(timespec="seconds"),
            }
        )
    return out


def market_status_summary(status: dict[str, Any] | None) -> dict[str, Any]:
    """Describe a market status payload without over-claiming liveness."""
    status = status or {}
    is_open = status.get("isOpen")
    return {
        "is_open": is_open,
        "as_of": status.get("asOf"),
        "source": "nepalstock.com.np/api/nots/nepse-data/market-open",
        "note": (
            "is_open/as_of are the exchange's own published values; as_of is the "
            "exchange's observation time, not the time of this request."
        ),
    }
