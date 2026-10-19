"""Tests for the gated NEPSE official live client.

The strip-position vectors below were produced by running go-nepse's embedded
``css.wasm`` through the ``pywasm`` interpreter and are asserted here as a
regression guard: if NEPSE's obfuscation routine changes, these fail loudly
rather than silently sending a malformed token.
"""

from __future__ import annotations

import httpx
import pytest

from megatool.datasources import nepse_official_live as ol

# (salt2, positions) — captured from the real css.wasm via pywasm.
WASM_VECTORS = [
    (66868, [30, 54, 82, 102, 126]),
    (99999, [31, 59, 87, 106, 128]),
    (12345, [25, 42, 70, 95, 116]),
    (10000, [27, 37, 65, 93, 115]),
    (99, [28, 47, 75, 103, 116]),
]


@pytest.mark.parametrize("salt2,expected", WASM_VECTORS)
def test_strip_positions_match_the_embedded_wasm(salt2, expected):
    assert ol.strip_positions(salt2) == expected


def test_only_salt2_participates_in_position_math():
    # The WASM functions read only the 2nd parameter; strip_positions takes only salt2.
    assert ol.strip_positions(66868) == ol.strip_positions(66868)


def test_decode_access_token_strips_five_characters():
    token = "".join(chr(65 + (i % 26)) for i in range(250))
    prove = {"salt2": 66868, "accessToken": token}
    out = ol.decode_access_token(prove)
    assert len(out) == 245
    dropped = sorted(ol.strip_positions(66868))
    expected = "".join(c for i, c in enumerate(token) if i not in set(dropped))
    assert out == expected


def test_decode_access_token_rejects_malformed_payload():
    with pytest.raises(ol.NepseOfficialError):
        ol.decode_access_token({"accessToken": "abc"})  # no salt2
    with pytest.raises(ol.NepseOfficialError):
        ol.decode_access_token({"salt2": "not-an-int", "accessToken": "abc"})


# --------------------------------------------------------------------- gating
def test_construction_is_offline_and_unauthorized_by_default(monkeypatch):
    monkeypatch.delenv(ol.AUTH_ENV, raising=False)
    client = ol.NepseOfficialLiveClient()
    assert client._authorized is False
    for call in (
        client.market_status,
        client.market_summary,
        client.indices,
        client.live_market,
        client.securities,
        client.companies,
    ):
        with pytest.raises(ol.NepseOfficialNotAuthorized):
            call()
    client.close()


def test_authorized_via_env_flag(monkeypatch):
    monkeypatch.setenv(ol.AUTH_ENV, "1")
    assert ol.NepseOfficialLiveClient()._authorized is True


# ------------------------------------------------------- request flow (mocked)
def _mock_client(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return ol.NepseOfficialLiveClient(authorized=True, http=http, backoff_seconds=0.0)


def test_token_is_cached_across_requests():
    calls = {"prove": 0, "data": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/authenticate/prove"):
            calls["prove"] += 1
            return httpx.Response(200, json={"salt2": 66868, "accessToken": "x" * 250})
        calls["data"] += 1
        assert request.headers["Authorization"] == "Salter " + "x" * 245
        return httpx.Response(200, json=[{"detail": "Total Turnover Rs:", "value": 5.0}])

    client = _mock_client(handler)
    client.market_summary()
    client.market_summary()
    assert calls["prove"] == 1  # cached within the TTL
    assert calls["data"] == 2
    client.close()


def test_401_triggers_a_single_token_refresh():
    seen = {"prove": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/authenticate/prove"):
            seen["prove"] += 1
            return httpx.Response(200, json={"salt2": 12345, "accessToken": "y" * 250})
        # First data request after the initial token is rejected as expired.
        if seen["prove"] == 1:
            return httpx.Response(401, text="WARNING: UNAUTHORIZED ACCESS")
        return httpx.Response(200, json=[{"symbol": "NABIL"}])

    client = _mock_client(handler)
    out = client.live_market()
    assert out == [{"symbol": "NABIL"}]
    assert seen["prove"] == 2  # original + refresh
    client.close()


def test_server_error_is_retried_then_raises():
    calls = {"data": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/authenticate/prove"):
            return httpx.Response(200, json={"salt2": 12345, "accessToken": "z" * 250})
        calls["data"] += 1
        return httpx.Response(503, text="boom")

    client = _mock_client(handler)
    with pytest.raises(ol.NepseOfficialError):
        client.market_status()
    assert calls["data"] == 3  # 1 + max_retries(2)
    client.close()


def test_non_json_body_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/authenticate/prove"):
            return httpx.Response(200, json={"salt2": 12345, "accessToken": "z" * 250})
        return httpx.Response(200, text="<html>not json</html>")

    client = _mock_client(handler)
    with pytest.raises(ol.NepseOfficialError):
        client.indices()
    client.close()


# ------------------------------------------------------------ quote conversion
def test_live_market_to_quote_rows_happy_path():
    records = [
        {
            "symbol": "nabil",
            "securityName": "Nabil Bank Limited",
            "lastTradedPrice": 537.1,
            "previousClose": 530.0,
            "highPrice": 540.0,
            "lowPrice": 528.0,
            "percentageChange": 1.34,
            "totalTradeQuantity": 12345,
            "totalTradeValue": 6_600_000.0,
            "lastUpdatedDateTime": "2026-10-15T15:00:00",
        }
    ]
    rows, stats = ol.live_market_to_quote_rows(records)
    assert stats["rows_out"] == 1 and stats["records_in"] == 1
    r = rows[0]
    assert r["symbol"] == "NABIL"
    assert r["quote_date"] == "2026-10-15"
    assert r["ltp"] == 537.1
    assert r["change"] == pytest.approx(7.1)
    assert r["volume"] == 12345
    assert r["source"] == ol.SOURCE_LIVE_MARKET
    assert r["validation_status"] == "valid"


def test_live_market_to_quote_rows_never_invents_values():
    records = [
        {"symbol": "", "lastUpdatedDateTime": "2026-10-15T15:00:00"},  # no_symbol
        {"symbol": "X", "lastTradedPrice": 1.0},  # missing_timestamp
        {"symbol": "Y", "lastTradedPrice": None, "lastUpdatedDateTime": "2026-10-15T15:00:00"},
        {"symbol": "Z", "lastTradedPrice": 0, "lastUpdatedDateTime": "2026-10-15T15:00:00"},
        {
            "symbol": "W",
            "lastTradedPrice": 10.0,
            "highPrice": 5.0,
            "lowPrice": 9.0,
            "lastUpdatedDateTime": "2026-10-15T15:00:00",
        },
    ]
    rows, stats = ol.live_market_to_quote_rows(records)
    assert stats["no_symbol"] == 1
    assert stats["missing_timestamp"] == 1
    assert stats["missing_ltp"] == 1
    assert stats["invalid_ltp"] == 1
    assert stats["suspect"] == 1
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["Y"]["ltp"] is None and by_symbol["Y"]["validation_status"] == "missing"
    assert by_symbol["Z"]["ltp"] is None and by_symbol["Z"]["validation_status"] == "invalid"
    assert by_symbol["W"]["validation_status"] == "suspect"
    # Unavailable must never be coerced to a fabricated 0.
    assert by_symbol["Z"]["ltp"] != 0.0


def test_live_market_to_quote_rows_empty_is_not_fabricated():
    rows, stats = ol.live_market_to_quote_rows([])
    assert rows == [] and stats["rows_out"] == 0


def test_quote_ts_is_treated_as_nepal_local_time():
    # 2026-10-15T15:00:00 NPT is the same calendar date in UTC+05:45.
    rows, _ = ol.live_market_to_quote_rows(
        [{"symbol": "NABIL", "lastTradedPrice": 1.0, "lastUpdatedDateTime": "2026-10-15T00:15:00"}]
    )
    assert rows[0]["quote_date"] == "2026-10-15"
    assert rows[0]["source_updated_at"] == "2026-10-15T00:15:00"


# ---------------------------------------------------------------- index rows
def test_indices_to_index_rows_maps_known_ids_and_skips_bad_values():
    records = [
        {
            "id": 58,
            "index": "Nepse Index",
            "close": 2500.5,
            "generatedTime": "2026-10-15T15:28:11.8",
        },
        {
            "id": 57,
            "index": "Sensitive Index",
            "close": 474.9,
            "generatedTime": "2026-10-15T15:28:11.8",
        },
        {
            "id": 99,
            "index": "Custom",
            "close": 0,
            "generatedTime": "2026-10-15T15:28:11.8",
        },  # close<=0 skipped
        {"id": 60, "index": "Finance", "close": 1.0},  # no generatedTime skipped
    ]
    rows = ol.indices_to_index_rows(records)
    names = {r["index_name"] for r in rows}
    assert names == {"NEPSE", "Sensitive Index"}
    assert all(r["trading_date"] == "2026-10-15" for r in rows)
    assert all(r["source"] == ol.SOURCE_INDICES for r in rows)


def test_market_status_summary_does_not_overclaim():
    out = ol.market_status_summary({"isOpen": "CLOSE", "asOf": "2026-10-15T15:00:00", "id": 80})
    assert out["is_open"] == "CLOSE"
    assert out["as_of"] == "2026-10-15T15:00:00"
    assert "not the time of this request" in out["note"]


# --------------------------------------------------------------- circuit breaker
class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_breaker_opens_after_threshold_and_refuses():
    clk = _Clock()
    b = ol.CircuitBreaker(failure_threshold=3, recovery_timeout=10.0, clock=clk)
    assert b.allow() is True and b.state is ol.CircuitState.CLOSED
    for _ in range(3):
        b.record_failure("boom")
    assert b.state is ol.CircuitState.OPEN
    assert b.allow() is False
    assert b.snapshot()["failures"] == 3


def test_breaker_half_opens_then_closes_on_success():
    clk = _Clock()
    b = ol.CircuitBreaker(failure_threshold=1, recovery_timeout=10.0, clock=clk)
    b.record_failure()
    assert b.state is ol.CircuitState.OPEN
    clk.t = 10.0
    assert b.state is ol.CircuitState.HALF_OPEN
    assert b.allow() is True
    assert b.allow() is False  # only one probe is permitted
    b.record_success()
    assert b.state is ol.CircuitState.CLOSED
    assert b.snapshot()["failures"] == 0


def test_breaker_reopens_when_the_probe_fails():
    clk = _Clock()
    b = ol.CircuitBreaker(failure_threshold=1, recovery_timeout=10.0, clock=clk)
    b.record_failure()
    clk.t = 10.0
    assert b.allow() is True  # half-open probe
    b.record_failure()
    assert b.state is ol.CircuitState.OPEN
    assert b.allow() is False


def test_breaker_rejects_bad_config():
    with pytest.raises(ValueError):
        ol.CircuitBreaker(failure_threshold=0)
    with pytest.raises(ValueError):
        ol.CircuitBreaker(half_open_max_calls=0)


def test_open_breaker_refuses_without_any_network():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls["n"] += 1
        return httpx.Response(500)

    upstream = httpx.Client(transport=httpx.MockTransport(handler))
    tripped = ol.CircuitBreaker(failure_threshold=1, recovery_timeout=9999.0)
    tripped.record_failure("already down")
    client = ol.NepseOfficialLiveClient(
        authorized=True, http=upstream, breaker=tripped, jitter=False
    )
    with pytest.raises(ol.NepseOfficialError, match="circuit breaker"):
        client.market_status()
    assert calls["n"] == 0  # the breaker refused before any request
    client.close()


def test_unauthorized_client_stays_closed_to_collection():
    """Even with a healthy breaker, an ungated client makes no calls."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls["n"] += 1
        return httpx.Response(200, json=[])

    client = ol.NepseOfficialLiveClient(
        authorized=False, http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(ol.NepseOfficialNotAuthorized):
        client.market_status()
    assert calls["n"] == 0
    client.close()


# ---------------------------------------------------------------- retry policy
def _client(handler, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    kw.setdefault("authorized", True)
    kw.setdefault("jitter", False)
    kw.setdefault("backoff_seconds", 0.0)
    return ol.NepseOfficialLiveClient(http=http, **kw)


def _prove_ok(handler):
    def wrapped(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/authenticate/prove"):
            return httpx.Response(200, json={"salt2": 12345, "accessToken": "z" * 250})
        return handler(request)

    return wrapped


def test_403_is_an_authorization_failure_and_is_not_retried():
    calls = {"data": 0}

    def data(request):
        calls["data"] += 1
        return httpx.Response(403, text="forbidden")

    client = _client(_prove_ok(data))
    with pytest.raises(ol.NepseOfficialAuthError):
        client.market_status()
    assert calls["data"] == 1  # never hammered
    client.close()


def test_429_honours_retry_after():
    seq = {"n": 0}
    slept: list[float] = []

    def data(request):
        seq["n"] += 1
        if seq["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, text="slow down")
        return httpx.Response(200, json={"ok": True})

    client = _client(_prove_ok(data), backoff_seconds=5.0, sleep=slept.append)
    assert client.market_status() == {"ok": True}
    assert slept == [0.0]  # Retry-After: 0 was honoured, not the 5s backoff
    client.close()


def test_retry_after_is_capped():
    seq = {"n": 0}
    slept: list[float] = []

    def data(request):
        seq["n"] += 1
        if seq["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "9999"}, text="slow down")
        return httpx.Response(200, json=[])

    client = _client(_prove_ok(data), backoff_seconds=1.0, sleep=slept.append)
    client.market_status()
    assert slept == [60.0]  # capped at MAX_RETRY_AFTER_SECONDS
    client.close()


def test_backoff_jitter_stays_within_range():
    slept: list[float] = []

    def data(request):
        return httpx.Response(503, text="down")

    client = _client(
        _prove_ok(data), jitter=True, backoff_seconds=1.0, max_retries=1, sleep=slept.append
    )
    with pytest.raises(ol.NepseOfficialError):
        client.market_status()
    assert len(slept) == 2
    assert 0.5 <= slept[0] <= 1.5  # 1s ± 50%
    assert 1.0 <= slept[1] <= 3.0  # 2s ± 50%
    client.close()


def test_breaker_state_is_reported_after_failures():
    def data(request):
        return httpx.Response(503, text="down")

    client = _client(_prove_ok(data), max_retries=0)
    with pytest.raises(ol.NepseOfficialError):
        client.market_status()
    snap = client.breaker_snapshot()
    assert snap["failures"] == 1
    assert snap["state"] in {"closed", "open"}
    client.close()
