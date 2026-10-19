"""Live market data - one honest read of the freshest permitted source.

Why this module exists
----------------------
NEPSE has no single obvious "live" API for a personal tool:

* **NEPSE official API** (``nepalstock.com.np/api/nots``) returns
  ``401 WARNING: UNAUTHORIZED ACCESS`` to any request without its ``Salter``
  token, and producing that token means defeating the exchange's client-side
  anti-bot obfuscation. This project will not do that, so the official surface
  stays behind ``MEGATOOL_NEPSE_API_AUTHORIZED`` and is never enabled by this
  module.
* **ShareHub** publishes a documented NEPSE Data API whose live board refreshes
  roughly every 20 seconds. It needs a licensed account, a Bearer token and an
  IP allow-list - i.e. owner credentials this code does not invent but will use
  the moment they are provided.
* **YONEPSE** is a public, no-auth JSON mirror. It is honest but *slow and
  occasionally stallable*: its market snapshot is published on an hourly
  cadence and has, at times, gone days without a market-file update.

This module turns those into one interface and, crucially, **measures freshness
instead of asserting it**. It reports the source's *own* newest observation
time, the time we fetched, the fetch latency, and the resulting observation
age - so a 90 ms request that returns a 4-day-old snapshot is reported as a
4-day-old snapshot, never as "live".

Nothing here invents a price. A provider that is unconfigured, unreachable or
malformed yields an explicit reason, and the caller keeps showing stored data.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from megatool.datasources import yonepse

#: Environment configuration. Nothing here is ever set by this module.
FEED_URL_ENV = "MEGATOOL_LIVE_FEED_URL"
SHAREHUB_EMAIL_ENV = "MEGATOOL_SHAREHUB_EMAIL"
SHAREHUB_PASSWORD_ENV = "MEGATOOL_SHAREHUB_PASSWORD"
PROVIDER_ENV = "MEGATOOL_LIVE_PROVIDER"
GATE_ENV = "MEGATOOL_NEPSE_API_AUTHORIZED"

SHAREHUB_BASE = "https://sharehubnepal.com/data/api/v1/nepse-data"
SHAREHUB_LOGIN = "https://sharehubnepal.com/account/api/v1/auth/login/email"

NPT = timezone(timedelta(hours=5, minutes=45))

#: Freshness bands, in observation age (end-to-end), not request latency.
#:
#: ``live`` requires ~sub-minute age; ``delayed`` means the observation is
#: within the source's own normal publication lag (so an hourly publisher is
#: not mislabelled "stale"); ``stale`` means it is older than that while the
#: market is open; ``last-close`` is the expected hours-old last trade once the
#: market closes; ``historical`` is older than a few days.
LIVE_MAX_SECONDS = 30.0
CLOSED_LAST_CLOSE_SECONDS = 3 * 24 * 3600
HISTORICAL_SECONDS = 5 * 24 * 3600
STALE = "stale"
HISTORICAL = "historical"
NO_TIMESTAMP = "unknown"


class LiveError(Exception):
    """A provider could not supply a usable snapshot (never a fabricated one)."""


# --------------------------------------------------------------------- helpers
def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_ts(value: Any) -> datetime | None:
    """Parse a source timestamp into an aware UTC datetime.

    Accepts ISO-8601 with or without an offset, or a bare epoch-milliseconds
    integer. Naive timestamps are treated as Nepal local time (UTC+05:45),
    because that is how every NEPSE-facing publisher writes them.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit() and len(text) >= 12:  # epoch ms as a string
        return _parse_ts(int(text))
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=NPT)
    return dt.astimezone(UTC)


def _finite(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _finite_pos(value: Any) -> float | None:
    f = _finite(value)
    return None if f is None or f <= 0 else f


def _finite_int(value: Any) -> int | None:
    f = _finite(value)
    return None if f is None else int(f)


def _freshness(
    age_seconds: float | None,
    is_open: bool | None,
    publish_cadence_seconds: float = 60.0,
) -> str:
    """Label an observation by age *relative to the source's own cadence*.

    A source that publishes hourly will normally be up to an hour old; calling
    that "stale" would misdescribe a healthy source just as surely as calling it
    "live" would overstate freshness. ``delayed`` therefore covers the source's
    normal publication window, and ``stale`` means it has fallen behind that.
    """
    if age_seconds is None:
        return NO_TIMESTAMP
    if age_seconds > HISTORICAL_SECONDS:
        return HISTORICAL
    if is_open is False and age_seconds <= CLOSED_LAST_CLOSE_SECONDS:
        # Outside trading hours the newest observation is the last close, which
        # is expected to be hours old and must not read as "stale".
        return "last-close"
    if age_seconds <= LIVE_MAX_SECONDS:
        return "live"
    window = max(publish_cadence_seconds * 1.5, 90.0)
    if age_seconds <= window:
        return "delayed"
    return STALE


#: The diagnostics status vocabulary (Phase 5), keyed by the fine-grained
#: freshness label. ``LIVE_VERIFIED`` requires a sub-minute observation age, so
#: it can never be shown merely because a request returned HTTP 200.
_STATUS_BY_FRESHNESS: dict[str, str] = {
    "live": "LIVE_VERIFIED",
    "delayed": "DELAYED",
    "last-close": "DELAYED",
    "stale": "STALE",
    "historical": "HISTORICAL",
    NO_TIMESTAMP: "UNKNOWN",
}


def _status_for(freshness: str) -> str:
    return _STATUS_BY_FRESHNESS.get(freshness, "UNKNOWN")


def _http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
    data: bytes | None = None,
    method: str | None = None,
) -> tuple[Any, float]:
    """GET/POST JSON and return ``(payload, latency_ms)``. TLS stays verified."""
    req = Request(url, data=data, method=method or ("POST" if data else "GET"))
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for key, val in (headers or {}).items():
        req.add_header(key, val)
    started = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https hosts
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:  # surface the status, do not mask it
        body = ""
        with contextlib.suppress(Exception):
            body = exc.read().decode("utf-8", "replace")[:200]
        raise LiveError(f"HTTP {exc.code} from {url}: {body}") from exc
    except URLError as exc:
        raise LiveError(f"cannot reach {url}: {exc.reason}") from exc
    latency_ms = (time.perf_counter() - started) * 1000.0
    try:
        return json.loads(raw), latency_ms
    except json.JSONDecodeError as exc:
        raise LiveError(f"non-JSON response from {url}") from exc


@dataclass(slots=True)
class LiveQuote:
    """One security's most recent published price observation."""

    symbol: str
    ltp: float | None
    previous_close: float | None = None
    change: float | None = None
    percent_change: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None
    turnover: float | None = None
    trades: int | None = None
    name: str | None = None
    observed_at: str | None = None  # the source's own timestamp for this row
    validation_status: str = "valid"


# ------------------------------------------------------------------- providers
class LiveProvider:
    """A source of near-live NEPSE quotes.

    Subclasses only implement :meth:`load`, returning a *partial* dict; the
    service fills in provenance and freshness so no provider can claim to be
    fresher than its own timestamps allow.
    """

    id = "base"
    label = "base"
    #: How often we may re-poll the source (the cache TTL).
    cadence_seconds = 60
    #: How often the source itself publishes new observations. Drives the
    #: freshness bands, so an hourly publisher is not called "stale" merely for
    #: being an hour old.
    publish_cadence_seconds = 60.0

    def configured(self) -> tuple[bool, str | None]:
        return True, None

    def load(self) -> dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError


class FeedProvider(LiveProvider):
    """An owner-supplied JSON feed URL (any permitted source).

    This is the escape hatch: point ``MEGATOOL_LIVE_FEED_URL`` at a feed the
    owner is authorized to use - their broker's read-only endpoint, a licensed
    vendor, or their own collector - and the app treats it exactly like the
    built-in providers.
    """

    id = "feed"
    label = "Owner-configured JSON feed"
    cadence_seconds = int(os.getenv("MEGATOOL_LIVE_FEED_CADENCE", "15") or 15)
    publish_cadence_seconds = float(os.getenv("MEGATOOL_LIVE_FEED_CADENCE", "15") or 15)

    def configured(self) -> tuple[bool, str | None]:
        if os.getenv(FEED_URL_ENV, "").strip():
            return True, None
        return False, f"{FEED_URL_ENV} is not set"

    def load(self) -> dict[str, Any]:
        url = os.environ[FEED_URL_ENV].strip()
        payload, latency = _http_get_json(url)
        if isinstance(payload, dict):
            records = payload.get("quotes") or payload.get("data") or []
            index = payload.get("index")
            is_open = payload.get("is_open", payload.get("isOpen"))
            summary = payload.get("summary") or []
            observed = payload.get("as_of") or payload.get("asOf")
        elif isinstance(payload, list):
            records, index, is_open, summary, observed = payload, None, None, [], None
        else:
            raise LiveError("feed JSON was neither an object nor an array")
        quotes, newest = _quotes_from_records(
            records, time_key=("last_updated", "timestamp", "as_of")
        )
        return {
            "quotes": quotes,
            "index": index,
            "is_open": is_open,
            "summary": summary,
            "observed_at": observed or newest,
            "latency_ms": latency,
            "notes": ["parsed from the owner-configured feed URL"],
        }


class YonepseProvider(LiveProvider):
    """YONEPSE's public raw JSON. No auth; upstream scrapes ~hourly in-session."""

    id = "yonepse"
    label = "YONEPSE public JSON (raw content)"
    cadence_seconds = 300
    # The upstream scraper runs about hourly during trading hours.
    publish_cadence_seconds = 3600.0

    def configured(self) -> tuple[bool, str | None]:
        return True, None

    def load(self) -> dict[str, Any]:
        started = time.perf_counter()
        snap = yonepse.fetch_market_snapshot()
        latency = (time.perf_counter() - started) * 1000.0
        status = snap["status"]
        records = snap["live"]
        indices = snap["indices"]
        origin = snap["origin"]
        quotes, newest = _quotes_from_records(records, time_key=("last_updated",))
        index = _pick_main_index(indices) if isinstance(indices, list) else None
        checked = yonepse.market_status_summary(status)
        # Report the newest of the two published stamps, compared as instants
        # (never as strings) so a naive NPT stamp and an aware UTC stamp cannot
        # be ordered wrongly.
        observed = _max_iso(checked.get("last_checked"), newest)
        notes = [
            "YONEPSE's upstream scraper runs on a roughly hourly cadence during "
            "trading hours, so this is current-day data, not tick-by-tick; the "
            "age below is the newest observation in the payload, and each row "
            "keeps its own last-trade time.",
        ]
        if origin == yonepse.PAGES_BASE_URL:
            notes.append(
                "served from the GitHub-Pages mirror because the fresh raw "
                "content was unreadable; that mirror is CDN-cached and can be "
                "days behind, which the age below will show",
            )
        elif origin and origin != yonepse.RAW_BASE_URL:
            notes.append(
                "read from a recent commit because the branch tip was "
                "unreadable (the upstream repo occasionally lands a broken "
                "merge commit); the age below is the real observation age",
            )
        return {
            "quotes": quotes,
            "index": index,
            "is_open": checked.get("is_open"),
            "is_open_source": checked.get("is_open_source"),
            "observed_at": observed,
            "latency_ms": latency,
            "origin": origin,
            "notes": notes,
        }


class ShareHubProvider(LiveProvider):
    """ShareHub's documented NEPSE Data API (licensed; ~20 s live cadence)."""

    id = "sharehub"
    label = "ShareHub NEPSE Data API (licensed)"
    cadence_seconds = 20
    publish_cadence_seconds = 20.0

    def __init__(self) -> None:
        self._token: str | None = None

    def configured(self) -> tuple[bool, str | None]:
        email = os.getenv(SHAREHUB_EMAIL_ENV, "").strip()
        password = os.getenv(SHAREHUB_PASSWORD_ENV, "").strip()
        if email and password:
            return True, None
        return False, (
            f"needs a licensed ShareHub Data API account: set "
            f"{SHAREHUB_EMAIL_ENV} and {SHAREHUB_PASSWORD_ENV} (server-side only), "
            f"and register this server's IP with ShareHub"
        )

    def _access_token(self) -> str:
        if self._token:
            return self._token
        body = json.dumps(
            {
                "email": os.environ[SHAREHUB_EMAIL_ENV].strip(),
                "password": os.environ[SHAREHUB_PASSWORD_ENV].strip(),
                "useOnCookies": False,
            }
        ).encode()
        payload, _ = _http_get_json(SHAREHUB_LOGIN, data=body)
        token = ((payload or {}).get("data") or {}).get("accessToken")
        if not token:
            raise LiveError("ShareHub login succeeded but returned no accessToken")
        self._token = str(token)
        return self._token

    def load(self) -> dict[str, Any]:
        token = self._access_token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            payload, latency = _http_get_json(f"{SHAREHUB_BASE}/market", headers=headers)
        except LiveError as exc:
            if "401" in str(exc):
                self._token = None  # refresh once on expiry
                headers["Authorization"] = f"Bearer {self._access_token()}"
                payload, latency = _http_get_json(f"{SHAREHUB_BASE}/market", headers=headers)
            else:
                raise
        data = (payload or {}).get("data") or payload or {}
        if not isinstance(data, dict):
            raise LiveError("unexpected ShareHub market payload")
        quotes, newest = _quotes_from_records(
            data.get("stockPrices") or data.get("stocks") or data.get("quotes") or [],
            time_key=("asOf", "lastUpdated", "last_updated", "timestamp"),
        )
        index = data.get("index") or _pick_main_index(data.get("indices") or [])
        is_open = data.get("isOpen", data.get("marketOpen"))
        observed = data.get("asOf") or data.get("lastUpdated") or newest
        return {
            "quotes": quotes,
            "index": index,
            "is_open": is_open,
            "summary": data.get("summary") or [],
            "observed_at": observed,
            "latency_ms": latency,
            "notes": ["ShareHub live board refreshes ~every 20 s during trading hours"],
        }


class OfficialProvider(LiveProvider):
    """The gated official surface, via the actual go-nepse go library bridge.

    This is the only near-real-time source, and it is deliberately inert until
    the owner opens ``MEGATOOL_NEPSE_API_AUTHORIZED``. It never sets that flag
    and never disables TLS verification.
    """

    id = "official"
    label = "NEPSE official API via go-nepse (gated)"
    cadence_seconds = 5
    publish_cadence_seconds = 5.0

    def configured(self) -> tuple[bool, str | None]:
        if os.getenv(GATE_ENV) != "1":
            return False, (
                f"owner authorization gate is closed (set {GATE_ENV}=1 to allow "
                f"the official API; not set by this application)"
            )
        from megatool.datasources.gonepse import find_bridge

        if not find_bridge():
            return False, "go-nepse bridge binary not found (build tools/gonepse-bridge)"
        return True, None

    def load(self) -> dict[str, Any]:
        from megatool.datasources.gonepse import GoNepseAdapter

        adapter = GoNepseAdapter()
        started = time.perf_counter()
        live = adapter.live_market() or []
        status = adapter.market_status() or {}
        index = adapter.nepse_index() or {}
        latency = (time.perf_counter() - started) * 1000.0
        quotes, newest = _quotes_from_records(
            live,
            time_key=("lastUpdated", "lastTradedTime", "asOf"),
            symbol_key=("symbol", "stockSymbol"),
            mapping={
                "ltp": ("lastTradedPrice", "ltp", "closePrice"),
                "previous_close": ("previousClose",),
                "change": ("pointChange",),
                "percent_change": ("percentageChange",),
                "high": ("highPrice",),
                "low": ("lowPrice",),
                "volume": ("totalTradedQuantity", "volume"),
                "turnover": ("totalTradedValue",),
                "trades": ("totalTrades",),
            },
        )
        index_norm = None
        if index:
            index_norm = {
                "name": "NEPSE Index",
                "close": _finite(index.get("IndexValue", index.get("indexValue"))),
                "change": _finite(index.get("PointChange", index.get("pointChange"))),
                "perChange": _finite(index.get("PercentChange", index.get("percentChange"))),
                "as_of": index.get("GeneratedTime") or index.get("generatedTime"),
            }
            newest = _max_iso(newest, index_norm.get("as_of"))
        return {
            "quotes": quotes,
            "index": index_norm,
            "is_open": (status.get("IsOpen") == "OPEN") if status else None,
            "summary": [],
            "observed_at": newest,
            "latency_ms": latency,
            "notes": [
                "official API via the go-nepse Go library; TLS verification stays on",
            ],
        }


# --------------------------------------------------------------- record mapping
def _quotes_from_records(
    records: Any,
    *,
    time_key: tuple[str, ...],
    symbol_key: tuple[str, ...] = ("symbol",),
    mapping: dict[str, tuple[str, ...]] | None = None,
) -> tuple[list[LiveQuote], str | None]:
    """Normalise heterogeneous quote records; never fabricate a missing field."""
    mapping = mapping or {
        "ltp": ("ltp", "lastTradedPrice", "close"),
        "previous_close": ("previous_close", "previousClose", "prevClose"),
        "change": ("change", "pointChange"),
        "percent_change": ("percent_change", "percentChange", "perChange"),
        "high": ("high", "highPrice"),
        "low": ("low", "lowPrice"),
        "volume": ("volume", "totalTradedQuantity"),
        "turnover": ("turnover", "totalTradedValue"),
        "trades": ("trades", "totalTrades"),
        "name": ("name", "securityName", "companyName"),
    }
    quotes: list[LiveQuote] = []
    newest: datetime | None = None
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        symbol = next((str(rec[k]).strip().upper() for k in symbol_key if rec.get(k)), "")
        if not symbol:
            continue

        ltp = _finite_pos(_pick(rec, "ltp", mapping))
        status = (
            "valid"
            if ltp is not None
            else ("missing" if _pick(rec, "ltp", mapping) is None else "invalid")
        )
        ts = None
        for key in time_key:
            ts = _parse_ts(rec.get(key))
            if ts is not None:
                break
        if ts is not None and (newest is None or ts > newest):
            newest = ts
        high, low = _finite(_pick(rec, "high", mapping)), _finite(_pick(rec, "low", mapping))
        if high is not None and low is not None and high < low and status == "valid":
            status = "suspect"
        name = _pick(rec, "name", mapping)
        quotes.append(
            LiveQuote(
                symbol=symbol,
                ltp=ltp,
                previous_close=_finite(_pick(rec, "previous_close", mapping)),
                change=_finite(_pick(rec, "change", mapping)),
                percent_change=_finite(_pick(rec, "percent_change", mapping)),
                high=high,
                low=low,
                volume=_finite_int(_pick(rec, "volume", mapping)),
                turnover=_finite(_pick(rec, "turnover", mapping)),
                trades=_finite_int(_pick(rec, "trades", mapping)),
                name=(str(name).strip() or None) if name else None,
                observed_at=ts.isoformat(timespec="seconds") if ts else None,
                validation_status=status,
            )
        )
    return quotes, (newest.isoformat(timespec="seconds") if newest else None)


def _pick(rec: dict[str, Any], field_name: str, mapping: dict[str, tuple[str, ...]]) -> Any:
    """First present value for ``field_name`` among its candidate keys."""
    for key in mapping[field_name]:
        if rec.get(key) not in (None, ""):
            return rec[key]
    return None


def _pick_main_index(indices: Any) -> dict[str, Any] | None:
    if not isinstance(indices, list) or not indices:
        return None
    for item in indices:
        if isinstance(item, dict) and str(item.get("index", "")).strip().lower() in (
            "nepse index",
            "nepse",
        ):
            return item
    return indices[0] if isinstance(indices[0], dict) else None


def _max_iso(*values: Any) -> str | None:
    parsed = [_parse_ts(v) for v in values if v]
    parsed = [p for p in parsed if p is not None]
    if not parsed:
        return None
    return max(parsed).isoformat(timespec="seconds")


# --------------------------------------------------------------------- service
def default_providers() -> list[LiveProvider]:
    """Priority order: best documented live source first, public mirror last."""
    return [ShareHubProvider(), OfficialProvider(), FeedProvider(), YonepseProvider()]


@dataclass
class _Cached:
    expires_at: float
    bundle: dict[str, Any]


class LiveService:
    """Selects a provider, caches at the source's cadence, reports freshness."""

    def __init__(
        self,
        providers: list[LiveProvider] | None = None,
        *,
        now: Callable[[], datetime] = _utcnow,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._providers = providers if providers is not None else default_providers()
        self._now = now
        self._monotonic = monotonic
        self._cache: dict[str, _Cached] = {}
        self._lock = threading.Lock()

    # -- provider selection --------------------------------------------------
    def provider_status(self) -> list[dict[str, Any]]:
        out = []
        for p in self._providers:
            ok, reason = p.configured()
            out.append(
                {
                    "id": p.id,
                    "label": p.label,
                    "configured": ok,
                    "reason": reason,
                    "cadence_seconds": p.cadence_seconds,
                    "publish_cadence_seconds": p.publish_cadence_seconds,
                    "requires_gate": p.id == "official",
                }
            )
        return out

    def active_provider(self) -> LiveProvider | None:
        forced = os.getenv(PROVIDER_ENV, "").strip()
        if forced:
            for p in self._providers:
                if p.id == forced:
                    ok, _ = p.configured()
                    return p if ok else None
            return None
        for p in self._providers:
            ok, _ = p.configured()
            if ok:
                return p
        return None

    # -- snapshot ------------------------------------------------------------
    def _error_bundle(self, provider: LiveProvider, exc: Exception) -> dict[str, Any]:
        now = self._now()
        return {
            "provider": provider.id,
            "label": provider.label,
            "ok": False,
            "error": str(exc),
            "is_open": None,
            "index": None,
            "summary": [],
            "sectors": [],
            "quotes": [],
            "observed_at": None,
            "fetched_at": now.isoformat(timespec="seconds"),
            "fetch_latency_ms": None,
            "age_seconds": None,
            "freshness": NO_TIMESTAMP,
            "status": "UNAVAILABLE",
            "quote_count": 0,
            "missing_price": 0,
            "notes": [f"{provider.label} could not be read: {exc}"],
        }

    def _build(self, provider: LiveProvider) -> dict[str, Any]:
        now = self._now()
        try:
            raw = provider.load()
        except Exception as exc:  # noqa: BLE001 - any failure is reported, not hidden
            return self._error_bundle(provider, exc)
        quotes: list[LiveQuote] = raw.get("quotes") or []
        observed = _parse_ts(raw.get("observed_at"))
        age = (now - observed).total_seconds() if observed else None
        missing = sum(1 for q in quotes if q.ltp is None)
        freshness = _freshness(age, raw.get("is_open"), provider.publish_cadence_seconds)
        return {
            "provider": provider.id,
            "label": provider.label,
            "ok": True,
            "error": None,
            "is_open": raw.get("is_open"),
            "is_open_source": raw.get("is_open_source"),
            "index": raw.get("index"),
            "summary": raw.get("summary") or [],
            "sectors": raw.get("sectors") or [],
            "quotes": [asdict(q) for q in quotes],
            "observed_at": observed.isoformat(timespec="seconds") if observed else None,
            "origin": raw.get("origin"),
            "fetched_at": now.isoformat(timespec="seconds"),
            "fetch_latency_ms": round(float(raw.get("latency_ms") or 0.0), 1),
            "age_seconds": None if age is None else round(age, 1),
            "freshness": freshness,
            "status": _status_for(freshness),
            "publish_cadence_seconds": provider.publish_cadence_seconds,
            "quote_count": len(quotes),
            "missing_price": missing,
            "notes": list(raw.get("notes") or []),
        }

    def snapshot(self, *, force: bool = False) -> dict[str, Any]:
        provider = self.active_provider()
        if provider is None:
            return {
                "provider": None,
                "label": "no live provider configured",
                "ok": False,
                "error": "no live provider is configured or available",
                "is_open": None,
                "index": None,
                "summary": [],
                "sectors": [],
                "quotes": [],
                "observed_at": None,
                "fetched_at": self._now().isoformat(timespec="seconds"),
                "fetch_latency_ms": None,
                "age_seconds": None,
                "freshness": NO_TIMESTAMP,
                "status": "UNAVAILABLE",
                "quote_count": 0,
                "missing_price": 0,
                "notes": [
                    "Configure a provider: ShareHub credentials, the official gate, "
                    "or MEGATOOL_LIVE_FEED_URL. YONEPSE is a public fallback.",
                ],
            }
        ttl = max(provider.cadence_seconds, 5)
        with self._lock:
            cached = self._cache.get(provider.id)
            if not force and cached and cached.expires_at > self._monotonic():
                bundle = dict(cached.bundle)
                bundle["cache_age_seconds"] = round(
                    max(0.0, ttl - (cached.expires_at - self._monotonic())), 1
                )
                bundle["cached"] = True
                return bundle
            bundle = self._build(provider)
            self._cache[provider.id] = _Cached(expires_at=self._monotonic() + ttl, bundle=bundle)
        bundle = dict(bundle)
        bundle["cache_age_seconds"] = 0.0
        bundle["cached"] = False
        return bundle

    def status(self) -> dict[str, Any]:
        active = self.active_provider()
        return {
            "active_provider": active.id if active else None,
            "providers": self.provider_status(),
            "official_gate_open": os.getenv(GATE_ENV) == "1",
            "tls_verification": True,
            "note": (
                "Freshness is measured from the source's own newest timestamp "
                "(age_seconds), not from how fast the request returned. The "
                "official NEPSE API requires the owner gate and an anti-bot token "
                "this project does not defeat."
            ),
        }

    def market(self, *, force: bool = False) -> dict[str, Any]:
        snap = self.snapshot(force=force)
        # Strip the (potentially large) quote list from the market summary.
        market = {k: v for k, v in snap.items() if k != "quotes"}
        market["quote_count"] = snap.get("quote_count", 0)
        return market

    def quotes(self, symbols: list[str] | None = None, *, force: bool = False) -> dict[str, Any]:
        snap = self.snapshot(force=force)
        wanted = {s.strip().upper() for s in (symbols or []) if s and s.strip()}
        rows = snap.get("quotes", [])
        if wanted:
            rows = [q for q in rows if q["symbol"] in wanted]
        return {
            "provider": snap.get("provider"),
            "label": snap.get("label"),
            "ok": snap.get("ok"),
            "error": snap.get("error"),
            "observed_at": snap.get("observed_at"),
            "fetched_at": snap.get("fetched_at"),
            "age_seconds": snap.get("age_seconds"),
            "freshness": snap.get("freshness"),
            "status": snap.get("status"),
            "fetch_latency_ms": snap.get("fetch_latency_ms"),
            "cache_age_seconds": snap.get("cache_age_seconds"),
            "cached": snap.get("cached", False),
            "count": len(rows),
            "quotes": rows,
            "notes": snap.get("notes", []),
        }


_SERVICE: LiveService | None = None
_SERVICE_LOCK = threading.Lock()


def get_service() -> LiveService:
    """Process-wide live service (single cache, single set of connections)."""
    global _SERVICE
    if _SERVICE is None:
        with _SERVICE_LOCK:
            if _SERVICE is None:
                _SERVICE = LiveService()
    return _SERVICE
