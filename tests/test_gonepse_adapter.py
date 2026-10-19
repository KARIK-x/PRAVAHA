"""Tests for the go-nepse adapter (actual Go library, via the bridge).

Nothing here touches the network. The adapter's subprocess boundary is injected,
so every failure mode (missing binary, missing gate, malformed output, timeout,
provider error) is deterministic.
"""

from __future__ import annotations

import json
import stat
import subprocess

import pytest

from megatool.datasources.base import SourceError, SourceUnavailable
from megatool.datasources.gonepse import (
    BRIDGE_ENV,
    GATE_ENV,
    GoNepseAdapter,
    find_bridge,
    gate_open,
)


def _envelope(*, data=None, error=None, ok=None):
    env = {"ok": (error is None) if ok is None else ok, "schemaVersion": "1", "data": data}
    if error is not None:
        env["error"] = error
    return env


def _proc(*, data=None, error=None, ok=None, returncode=0, stdout=None, stderr=b""):
    if stdout is None:
        stdout = json.dumps(_envelope(data=data, error=error, ok=ok)).encode()
    return subprocess.CompletedProcess(
        args=["gonepse-bridge"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _Recorder:
    """A fake bridge runner that records requests and returns a canned result."""

    def __init__(self, result=None, exc=None):
        self.requests: list[dict] = []
        self.result = result
        self.exc = exc

    def __call__(self, request):
        self.requests.append(request)
        if self.exc is not None:
            raise self.exc
        return self.result


def _adapter(monkeypatch, *, result=None, exc=None, bridge="/bin/true", **kw):
    """An adapter whose bridge is faked, with the gate open."""
    monkeypatch.setenv(GATE_ENV, "1")
    rec = _Recorder(result=result, exc=exc)
    return GoNepseAdapter(bridge=bridge, runner=rec, **kw), rec


# ---------------------------------------------------------------------- gating


def test_gate_is_closed_by_default(monkeypatch):
    monkeypatch.delenv(GATE_ENV, raising=False)
    assert gate_open() is False


def test_gate_opens_only_on_exactly_one(monkeypatch):
    monkeypatch.setenv(GATE_ENV, "true")  # not "1"
    assert gate_open() is False
    monkeypatch.setenv(GATE_ENV, "1")
    assert gate_open() is True


def test_call_without_gate_raises_and_never_spawns(monkeypatch):
    monkeypatch.delenv(GATE_ENV, raising=False)
    adapter, rec = _adapter(monkeypatch, result=_proc(data={"TotalTurnover": 1}))
    monkeypatch.delenv(GATE_ENV, raising=False)  # _adapter set it; undo
    with pytest.raises(SourceUnavailable) as exc:
        adapter.market_summary()
    assert "authorization" in str(exc.value).lower()
    assert rec.requests == []  # the gate is enforced before the subprocess


def test_missing_bridge_is_unavailable_even_with_gate(monkeypatch):
    monkeypatch.setenv(GATE_ENV, "1")
    adapter = GoNepseAdapter(bridge="", runner=_Recorder(result=_proc(data={})))
    with pytest.raises(SourceUnavailable) as exc:
        adapter.securities()
    assert "bridge binary not found" in str(exc.value)


# ---------------------------------------------------------------------- parsing


def test_valid_envelope_returns_data(monkeypatch):
    adapter, rec = _adapter(
        monkeypatch, result=_proc(data={"TotalTurnover": 123456.5, "TotalTransactions": 42})
    )
    assert adapter.market_summary() == {"TotalTurnover": 123456.5, "TotalTransactions": 42}
    assert rec.requests == [{"op": "market-summary"}]


def test_request_carries_symbol_and_dates(monkeypatch):
    adapter, rec = _adapter(monkeypatch, result=_proc(data=[]))
    adapter.price_history("nabil", start="2026-01-01", end="2026-06-30")
    assert rec.requests == [
        {"op": "price-history", "symbol": "nabil", "start": "2026-01-01", "end": "2026-06-30"}
    ]


def test_unknown_op_is_rejected_before_spawn(monkeypatch):
    adapter, rec = _adapter(monkeypatch, result=_proc(data={}))
    with pytest.raises(SourceError):
        adapter.call("definitely-not-an-op")
    assert rec.requests == []


def test_symbol_operation_without_symbol_is_rejected(monkeypatch):
    adapter, rec = _adapter(monkeypatch, result=_proc(data={}))
    with pytest.raises(SourceError):
        adapter.call("find-security")
    assert rec.requests == []


def test_malformed_json_is_a_source_error(monkeypatch):
    adapter, _ = _adapter(monkeypatch, result=_proc(stdout=b"{not json"))
    with pytest.raises(SourceError) as exc:
        adapter.market_summary()
    assert "not JSON" in str(exc.value)


def test_empty_output_is_a_source_error(monkeypatch):
    adapter, _ = _adapter(monkeypatch, result=_proc(stdout=b"", stderr=b"boom", returncode=2))
    with pytest.raises(SourceError) as exc:
        adapter.market_summary()
    assert "no output" in str(exc.value)
    assert "boom" in str(exc.value)


def test_non_envelope_json_is_a_source_error(monkeypatch):
    adapter, _ = _adapter(monkeypatch, result=_proc(stdout=json.dumps([1, 2, 3]).encode()))
    with pytest.raises(SourceError):
        adapter.market_summary()


def test_provider_error_envelope_is_a_source_error(monkeypatch):
    adapter, _ = _adapter(
        monkeypatch, result=_proc(error={"kind": "not_found", "message": "NEPSE Index"})
    )
    with pytest.raises(SourceError) as exc:
        adapter.nepse_index()
    assert "not_found" in str(exc.value)


def test_unauthorized_envelope_is_unavailable(monkeypatch):
    adapter, _ = _adapter(
        monkeypatch, result=_proc(error={"kind": "unauthorized", "message": "gate closed"})
    )
    with pytest.raises(SourceUnavailable):
        adapter.market_summary()


def test_timeout_is_a_source_error(monkeypatch):
    adapter, _ = _adapter(
        monkeypatch, exc=subprocess.TimeoutExpired(cmd="gonepse-bridge", timeout=30)
    )
    with pytest.raises(SourceError) as exc:
        adapter.live_market()
    assert "timed out" in str(exc.value)


def test_oserror_is_unavailable(monkeypatch):
    adapter, _ = _adapter(monkeypatch, exc=OSError("exec format error"))
    with pytest.raises(SourceUnavailable):
        adapter.securities()


# ---------------------------------------------------------------------- helpers


def test_list_symbols_dedupes_and_sorts(monkeypatch):
    adapter, _ = _adapter(
        monkeypatch,
        result=_proc(
            data=[
                {"symbol": "NABIL"},
                {"symbol": "ADBL"},
                {"symbol": "NABIL"},
                {"securityName": "no symbol here"},
            ]
        ),
    )
    assert adapter.list_symbols() == ["ADBL", "NABIL"]


def test_fetch_history_builds_canonical_frame_without_inventing_open(monkeypatch):
    adapter, _ = _adapter(
        monkeypatch,
        result=_proc(
            data=[
                {
                    "businessDate": "2026-01-02",
                    "highPrice": 11.0,
                    "lowPrice": 9.5,
                    "closePrice": 10.0,
                    "totalTradedQuantity": 100,
                    "totalTradedValue": 1000.0,
                    "totalTrades": 7,
                },
                {
                    "businessDate": "2026-01-01",
                    "highPrice": 10.5,
                    "lowPrice": 9.0,
                    "closePrice": 9.8,
                    "totalTradedQuantity": 50,
                    "totalTradedValue": 490.0,
                    "totalTrades": 3,
                },
            ]
        ),
    )
    df = adapter.fetch_history("nabil")
    assert list(df.columns) == [
        "symbol",
        "trading_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
        "transactions",
    ]
    assert df["trading_date"].is_monotonic_increasing  # sorted
    assert df["symbol"].tolist() == ["NABIL", "NABIL"]
    assert df["open"].isna().all()  # the source has no open price; never invented
    assert df["close"].tolist() == [9.8, 10.0]


def test_find_bridge_honours_env_only_for_real_executables(monkeypatch, tmp_path):
    monkeypatch.setenv(BRIDGE_ENV, str(tmp_path / "nope"))
    assert find_bridge() is None

    real = tmp_path / "bridge"
    real.write_text("#!/bin/sh\nexit 0\n")
    real.chmod(real.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv(BRIDGE_ENV, str(real))
    assert find_bridge() == str(real)


# ---------------------------------------------------------------------- diagnostics


def test_status_reports_tls_on_and_blocked_without_gate(monkeypatch):
    monkeypatch.delenv(GATE_ENV, raising=False)
    adapter = GoNepseAdapter(bridge="/bin/true")
    st = adapter.status()
    assert st["tls_verification"] is True
    assert st["authorized"] is False
    assert st["live"] == "blocked"
    assert GATE_ENV in st["blocked_reason"]
    assert "market-summary" in st["operations"]
    assert adapter.health()["available"] is False


def test_status_reports_ready_when_gate_and_bridge_present(monkeypatch):
    monkeypatch.setenv(GATE_ENV, "1")
    adapter = GoNepseAdapter(bridge="/bin/true")
    st = adapter.status()
    assert st["live"] == "ready"
    assert st["blocked_reason"] is None
    assert adapter.health()["available"] is True


def test_live_roundtrip_through_the_real_bridge_when_built(monkeypatch):
    """Exercise the Python -> Go -> real-library path end to end.

    When the bridge binary is present we run it (with the gate set) against an
    unreachable host and require an honest, parsed provider error — proving the
    subprocess, the stdin/stdout protocol and the error mapping really work.
    When the binary is absent, the adapter must refuse with a clear reason.
    Neither branch contacts NEPSE.
    """
    monkeypatch.setenv(GATE_ENV, "1")
    bridge = find_bridge()
    adapter = GoNepseAdapter(bridge=bridge, base_url="https://127.0.0.1:1", timeout=5.0)
    if bridge is None:
        with pytest.raises(SourceUnavailable) as exc:
            adapter.market_summary()
        assert "bridge binary not found" in str(exc.value)
        return
    with pytest.raises(SourceError) as exc:
        adapter.market_summary()
    # A reachable-but-refusing host yields a network-level provider error,
    # never a fabricated value.
    assert "go-nepse:" in str(exc.value)
