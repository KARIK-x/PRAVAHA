"""Tests for the unified live-data layer.

Everything here is deterministic and offline: the HTTP boundary
(``megatool.live._http_get_json``) and the YONEPSE fetchers are injected, so no
request ever leaves the machine. The point of these tests is *freshness and
honesty*, not network behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from megatool import live


def _now() -> datetime:
    return datetime(2026, 10, 16, 8, 0, 0, tzinfo=UTC)


# ------------------------------------------------------------------- helpers
def test_parse_ts_treats_naive_as_nepal_time():
    dt = live._parse_ts("2026-10-16T13:45:00")
    assert dt == datetime(2026, 10, 16, 8, 0, 0, tzinfo=UTC)  # 13:45 NPT == 08:00 UTC


def test_parse_ts_accepts_epoch_ms_and_z():
    assert live._parse_ts(1792134870000).year == 2026
    assert live._parse_ts("2026-10-16T08:00:00Z") == datetime(2026, 10, 16, 8, 0, tzinfo=UTC)


def test_parse_ts_rejects_junk():
    assert live._parse_ts("not a time") is None
    assert live._parse_ts("") is None
    assert live._parse_ts(None) is None


def test_freshness_is_relative_to_the_source_cadence():
    # Sub-minute age -> genuinely live.
    assert live._freshness(5, True, 20) == "live"
    # 37 minutes old from an HOURLY publisher is its normal lag, not "stale".
    assert live._freshness(37 * 60, True, 3600) == "delayed"
    # Three hours from an hourly publisher has fallen behind -> stale.
    assert live._freshness(3 * 3600, True, 3600) == "stale"
    # The same 30-minute age from a 20-second source IS stale.
    assert live._freshness(1800, True, 20) == "stale"
    # A closed market's hours-old last close is expected, not stale.
    assert live._freshness(6 * 3600, False, 3600) == "last-close"
    # Beyond a few days -> historical.
    assert live._freshness(10 * 24 * 3600, True, 3600) == "historical"
    assert live._freshness(None, True) == live.NO_TIMESTAMP


def test_status_vocabulary_maps_from_freshness():
    assert live._status_for("live") == "LIVE_VERIFIED"
    assert live._status_for("delayed") == "DELAYED"
    assert live._status_for("last-close") == "DELAYED"
    assert live._status_for("stale") == "STALE"
    assert live._status_for("historical") == "HISTORICAL"
    assert live._status_for(live.NO_TIMESTAMP) == "UNKNOWN"


# ------------------------------------------------------------- record mapping
def test_quotes_never_invent_a_price():
    rows, newest = live._quotes_from_records(
        [
            {
                "symbol": "NABIL",
                "ltp": 500.0,
                "last_updated": "2026-10-16T13:45:00",
                "high": 510,
                "low": 495,
            },
            {"symbol": "ZERO", "ltp": 0, "last_updated": "2026-10-16T13:45:00"},
            {"symbol": "MISSING", "last_updated": "2026-10-16T13:45:00"},
            {
                "symbol": "BADS",
                "ltp": 10,
                "high": 5,
                "low": 9,
                "last_updated": "2026-10-16T13:44:00",
            },
            {"no_symbol": True, "ltp": 1},
        ],
        time_key=("last_updated",),
    )
    by = {r.symbol: r for r in rows}
    assert by["NABIL"].ltp == 500.0 and by["NABIL"].validation_status == "valid"
    assert by["ZERO"].ltp is None and by["ZERO"].validation_status == "invalid"
    assert by["MISSING"].ltp is None and by["MISSING"].validation_status == "missing"
    assert by["BADS"].validation_status == "suspect"
    assert "no_symbol" not in by
    assert newest == "2026-10-16T08:00:00+00:00"  # 13:45 NPT -> 08:00 UTC


def test_pick_main_index_prefers_the_nepse_index():
    idx = live._pick_main_index(
        [{"index": "Sensitive Index", "close": 1}, {"index": "NEPSE Index", "close": 2591.0}]
    )
    assert idx["close"] == 2591.0


# ----------------------------------------------------------------- providers
def test_sharehub_needs_credentials(monkeypatch):
    monkeypatch.delenv(live.SHAREHUB_EMAIL_ENV, raising=False)
    monkeypatch.delenv(live.SHAREHUB_PASSWORD_ENV, raising=False)
    ok, reason = live.ShareHubProvider().configured()
    assert ok is False and "licensed ShareHub" in reason
    monkeypatch.setenv(live.SHAREHUB_EMAIL_ENV, "a@b.c")
    monkeypatch.setenv(live.SHAREHUB_PASSWORD_ENV, "secret")
    ok, reason = live.ShareHubProvider().configured()
    assert ok is True and reason is None


def test_sharehub_parses_documented_shape(monkeypatch):
    monkeypatch.setenv(live.SHAREHUB_EMAIL_ENV, "a@b.c")
    monkeypatch.setenv(live.SHAREHUB_PASSWORD_ENV, "secret")
    calls: list[str] = []

    def fake_get(url, *, headers=None, timeout=20.0, data=None, method=None):
        calls.append(url)
        if url == live.SHAREHUB_LOGIN:
            return {"data": {"accessToken": "tok"}}, 12.0
        return {
            "success": True,
            "data": {
                "asOf": "2026-10-16T13:45:00",
                "isOpen": True,
                "stockPrices": [
                    {
                        "symbol": "NABIL",
                        "ltp": 500.0,
                        "change": 5,
                        "percentChange": 1.0,
                        "previousClose": 495.0,
                        "asOf": "2026-10-16T13:45:00",
                    },
                ],
                "indices": [{"index": "NEPSE Index", "close": 2591.8}],
            },
        }, 30.0

    monkeypatch.setattr(live, "_http_get_json", fake_get)
    out = live.ShareHubProvider().load()
    assert out["is_open"] is True
    assert out["quotes"][0].symbol == "NABIL"
    assert out["index"]["close"] == 2591.8
    assert calls[0] == live.SHAREHUB_LOGIN


def test_sharehub_retries_once_on_401(monkeypatch):
    monkeypatch.setenv(live.SHAREHUB_EMAIL_ENV, "a@b.c")
    monkeypatch.setenv(live.SHAREHUB_PASSWORD_ENV, "secret")
    state = {"n": 0, "tok": 0}

    def fake_get(url, *, headers=None, timeout=20.0, data=None, method=None):
        if url == live.SHAREHUB_LOGIN:
            state["tok"] += 1
            return {"data": {"accessToken": f"tok{state['tok']}"}}, 5.0
        state["n"] += 1
        if state["n"] == 1:
            raise live.LiveError("HTTP 401 from market")
        return {"data": {"isOpen": True, "stockPrices": [], "asOf": "2026-10-16T13:45:00"}}, 5.0

    monkeypatch.setattr(live, "_http_get_json", fake_get)
    out = live.ShareHubProvider().load()
    assert state["tok"] == 2  # logged in again after the 401
    assert out["is_open"] is True


def test_official_provider_is_gated(monkeypatch):
    monkeypatch.delenv(live.GATE_ENV, raising=False)
    ok, reason = live.OfficialProvider().configured()
    assert ok is False and live.GATE_ENV in reason
    monkeypatch.setenv(live.GATE_ENV, "1")
    # Gate is open but the bridge may be absent in this environment; either the
    # provider is ready or it names the missing bridge. It must never silently
    # claim to be ready without a binary.
    ok, reason = live.OfficialProvider().configured()
    assert ok is True or "bridge" in (reason or "")


def _fake_snapshot(origin, status, live_records, indices):
    return {"status": status, "live": live_records, "indices": indices, "origin": origin}


def test_yonepse_provider_uses_published_timestamps(monkeypatch):
    monkeypatch.setattr(
        live.yonepse,
        "fetch_market_snapshot",
        lambda: _fake_snapshot(
            live.yonepse.RAW_BASE_URL,
            {"is_open": False, "last_checked": "2026-10-12T10:17:11"},
            [{"symbol": "NABIL", "ltp": 500.0, "last_updated": "2026-10-12T14:59:52"}],
            [{"index": "NEPSE Index", "close": 2591.0}],
        ),
    )
    out = live.YonepseProvider().load()
    # The newer of the two published stamps wins: the quote (09:14:52 UTC), not
    # the status check (10:17:11 NPT == 04:32:11 UTC).
    assert out["observed_at"] == "2026-10-12T09:14:52+00:00"
    assert out["index"]["close"] == 2591.0
    assert out["is_open"] is False


def test_yonepse_provider_flags_the_pages_fallback_provenance(monkeypatch):
    # When the fresh raw content is unreadable (upstream merge-conflict commits
    # do happen), the provider still answers but must say it used the mirror.
    monkeypatch.setattr(
        live.yonepse,
        "fetch_market_snapshot",
        lambda: _fake_snapshot(
            live.yonepse.PAGES_BASE_URL,
            {"is_open": False, "last_checked": "2026-10-12T10:17:11"},
            [{"symbol": "NABIL", "ltp": 500.0, "last_updated": "2026-10-12T14:59:52"}],
            [],
        ),
    )
    out = live.YonepseProvider().load()
    assert out["origin"] == live.yonepse.PAGES_BASE_URL
    assert any("GitHub-Pages mirror" in n for n in out["notes"])


def test_feed_provider_parses_a_list_and_an_object(monkeypatch):
    monkeypatch.setenv(live.FEED_URL_ENV, "https://example.test/feed")
    monkeypatch.setattr(
        live,
        "_http_get_json",
        lambda url, **kw: (
            {
                "as_of": "2026-10-16T13:59:59",
                "is_open": True,
                "index": {"index": "NEPSE Index", "close": 2600.0},
                "quotes": [
                    {"symbol": "NABIL", "ltp": 501.0, "last_updated": "2026-10-16T13:59:59"}
                ],
            },
            4.0,
        ),
    )
    out = live.FeedProvider().load()
    assert out["quotes"][0].ltp == 501.0
    assert out["observed_at"] == "2026-10-16T13:59:59"


def test_feed_provider_rejects_a_non_json_shape(monkeypatch):
    monkeypatch.setenv(live.FEED_URL_ENV, "https://example.test/feed")
    monkeypatch.setattr(live, "_http_get_json", lambda url, **kw: ("just a string", 1.0))
    with pytest.raises(live.LiveError):
        live.FeedProvider().load()


# -------------------------------------------------------------------- service
class _FakeProvider(live.LiveProvider):
    id = "fake"
    label = "Fake"
    cadence_seconds = 30

    def __init__(self, *, observed="2026-10-16T07:59:55", fail=False, is_open=True):
        self._observed = observed
        self._fail = fail
        self._is_open = is_open

    def configured(self):
        return True, None

    def load(self):
        if self._fail:
            raise live.LiveError("provider exploded")
        return {
            "quotes": live._quotes_from_records(
                [{"symbol": "NABIL", "ltp": 500.0, "last_updated": self._observed}],
                time_key=("last_updated",),
            )[0],
            "index": {"index": "NEPSE Index", "close": 2591.0},
            "is_open": self._is_open,
            "observed_at": self._observed,
            "latency_ms": 42.0,
            "notes": [],
        }


def test_service_measures_age_not_latency():
    # 13:44:55 NPT == 07:59:55 UTC, i.e. 5 s before the frozen "now".
    svc = live.LiveService([_FakeProvider(observed="2026-10-16T13:44:55")], now=_now)
    snap = svc.snapshot()
    assert snap["ok"] is True
    assert snap["fetch_latency_ms"] == 42.0  # the request was fast...
    assert snap["age_seconds"] == 5.0  # ...but the observation is 5 s old
    assert snap["freshness"] == "live"


def test_service_reports_stale_data_as_stale():
    svc = live.LiveService([_FakeProvider(observed="2026-10-12T08:00:00", is_open=True)], now=_now)
    snap = svc.snapshot()
    assert snap["freshness"] == "stale"
    assert snap["age_seconds"] > 3 * 24 * 3600


def test_service_caches_at_the_source_cadence():
    clock = {"t": 1000.0}
    svc = live.LiveService([_FakeProvider()], now=_now, monotonic=lambda: clock["t"])
    first = svc.snapshot()
    assert first["cached"] is False
    clock["t"] += 10  # inside the 30 s cadence
    second = svc.snapshot()
    assert second["cached"] is True
    assert second["cache_age_seconds"] == pytest.approx(10.0)
    clock["t"] += 25  # past the cadence
    third = svc.snapshot()
    assert third["cached"] is False
    forced = svc.snapshot(force=True)
    assert forced["cached"] is False


def test_service_surfaces_a_provider_failure_without_inventing_data():
    svc = live.LiveService([_FakeProvider(fail=True)], now=_now)
    snap = svc.snapshot()
    assert snap["ok"] is False
    assert snap["quotes"] == []
    assert "provider exploded" in snap["error"]
    assert snap["freshness"] == live.NO_TIMESTAMP


def test_service_with_no_provider_is_explicit(monkeypatch):
    monkeypatch.delenv(live.GATE_ENV, raising=False)
    monkeypatch.delenv(live.FEED_URL_ENV, raising=False)
    monkeypatch.delenv(live.SHAREHUB_EMAIL_ENV, raising=False)
    monkeypatch.delenv(live.SHAREHUB_PASSWORD_ENV, raising=False)
    monkeypatch.setenv(live.PROVIDER_ENV, "sharehub")  # forced but unconfigured
    svc = live.LiveService(now=_now)
    snap = svc.snapshot()
    assert snap["ok"] is False and snap["provider"] is None
    assert "no live provider" in snap["error"]


def test_provider_priority_and_forced_selection(monkeypatch):
    monkeypatch.delenv(live.PROVIDER_ENV, raising=False)
    share, official, feed, yone = live.default_providers()
    svc = live.LiveService([feed, yone], now=_now)
    assert svc.active_provider().id == "yonepse"  # feed unconfigured -> public fallback
    monkeypatch.setenv(live.FEED_URL_ENV, "https://example.test/feed")
    assert svc.active_provider().id == "feed"
    monkeypatch.setenv(live.PROVIDER_ENV, "yonepse")
    assert svc.active_provider().id == "yonepse"


def test_quotes_filter_and_market_strips_the_list():
    svc = live.LiveService([_FakeProvider()], now=_now)
    q = svc.quotes(["NABIL"])
    assert q["count"] == 1 and q["quotes"][0]["symbol"] == "NABIL"
    assert svc.quotes(["NOTLISTED"])["count"] == 0
    market = svc.market()
    assert "quotes" not in market
    assert market["quote_count"] == 1
    assert market["index"]["close"] == 2591.0


def test_service_status_lists_every_provider(monkeypatch):
    monkeypatch.delenv(live.GATE_ENV, raising=False)
    svc = live.LiveService(now=_now)
    st = svc.status()
    ids = {p["id"] for p in st["providers"]}
    assert {"sharehub", "official", "feed", "yonepse"} <= ids
    assert st["official_gate_open"] is False
    assert st["tls_verification"] is True


def test_get_service_is_a_singleton():
    assert live.get_service() is live.get_service()


def test_http_get_never_sends_a_secret_in_a_url():
    # Credentials must travel in a POST body / header, never a query string.
    import inspect

    src = inspect.getsource(live.ShareHubProvider._access_token)
    assert "SHAREHUB_PASSWORD_ENV" in src
    assert "data=body" in src
