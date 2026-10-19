"""Fixture tests for the market-hours benchmark harness.

No network is used anywhere in this file. The gate tests prove the harness
makes **zero** NEPSE requests when unauthorised by replacing the client class
with one that raises if it is ever constructed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from megatool import benchmark as bench
from megatool.datasources import nepse_official_live as ol

ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "benchmark_market_hours", ROOT / "scripts" / "benchmark_market_hours.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


SCRIPT = _load_script()


# ------------------------------------------------------------------ timezone
def test_npt_offset_is_five_forty_five_utc():
    npt = bench.to_npt(datetime(2026, 10, 18, 5, 15, tzinfo=bench.UTC))
    assert npt.utcoffset() == timedelta(hours=5, minutes=45)
    assert (npt.hour, npt.minute) == (11, 0)


def test_iso_npt_renders_nepal_offset():
    s = bench.iso_npt(datetime(2026, 10, 18, 5, 15, tzinfo=bench.UTC))
    assert s.startswith("2026-10-18T11:00:00")
    assert s.endswith("+05:45")


def test_to_utc_assumes_naive_is_nepal_time():
    utc = bench.to_utc(datetime(2026, 10, 18, 11, 0))  # naive → NPT
    assert utc == datetime(2026, 10, 18, 5, 15, tzinfo=bench.UTC)


@pytest.mark.parametrize(
    "dt,expected",
    [
        (datetime(2026, 10, 18, 5, 15, tzinfo=bench.UTC), True),  # Sun 11:00 NPT open
        (datetime(2026, 10, 18, 5, 14, 59, tzinfo=bench.UTC), False),  # 10:59:59 NPT
        (datetime(2026, 10, 18, 9, 15, tzinfo=bench.UTC), False),  # Sun 15:00 NPT close
        (datetime(2026, 10, 18, 8, 59, tzinfo=bench.UTC), True),  # Sun 14:59 NPT
        (datetime(2026, 10, 16, 6, 0, tzinfo=bench.UTC), False),  # Friday → closed
        (datetime(2026, 10, 17, 6, 0, tzinfo=bench.UTC), False),  # Saturday → closed
        (datetime(2026, 10, 15, 6, 0, tzinfo=bench.UTC), True),  # Thursday → open
    ],
)
def test_in_market_hours_boundaries(dt, expected):
    assert bench.in_market_hours(dt) is expected


def test_next_session_open_skips_the_weekend():
    # Thursday 2026-10-15 20:00 NPT → next open is Sunday 2026-10-18 11:00 NPT.
    after = datetime(2026, 10, 15, 20, 0, tzinfo=bench.NPT)
    nxt = bench.next_session_open(after)
    assert nxt == datetime(2026, 10, 18, 11, 0, tzinfo=bench.NPT)


def test_next_session_open_uses_today_when_before_open():
    before = datetime(2026, 10, 18, 10, 0, tzinfo=bench.NPT)
    assert bench.next_session_open(before) == datetime(2026, 10, 18, 11, 0, tzinfo=bench.NPT)


# ------------------------------------------------------------- snapshot model
def test_snapshot_hash_is_order_independent_but_content_sensitive():
    a = {"x": 1, "y": [1, 2, 3]}
    b = {"y": [1, 2, 3], "x": 1}
    c = {"x": 1, "y": [1, 2, 4]}
    assert bench.snapshot_hash(a) == bench.snapshot_hash(b)
    assert bench.snapshot_hash(a) != bench.snapshot_hash(c)


def test_record_count_handles_lists_dicts_and_empty():
    assert bench.record_count([{}, {}]) == 2
    assert bench.record_count([]) == 0
    assert bench.record_count({"a": 1, "rows": [1, 2, 3]}) == 3
    assert bench.record_count({"a": 1, "b": 2}) == 2


# ----------------------------------------------------------- source timestamps
def test_extract_market_open_uses_asof():
    field, ts = bench.extract_source_ts(
        "market-open", {"asOf": "2026-10-18T15:00:00", "isOpen": "CLOSE"}
    )
    assert field == "asOf"
    assert ts == datetime(2026, 10, 18, 9, 15, tzinfo=bench.UTC)  # 15:00 NPT → 09:15 UTC


def test_extract_nepse_index_takes_newest_generated_time():
    _, ts = bench.extract_source_ts(
        "nepse-index",
        [
            {"id": 58, "generatedTime": "2026-10-18T11:00:01.0"},
            {"id": 57, "generatedTime": "2026-10-18T15:28:11.8"},
            {"id": 62, "generatedTime": "2026-10-18T12:00:00"},
        ],
    )
    assert ts == datetime(2026, 10, 18, 9, 43, 11, 800000, tzinfo=bench.UTC)


def test_extract_lives_market_uses_newest_last_updated():
    _, ts = bench.extract_source_ts(
        "lives-market",
        [
            {"symbol": "A", "lastUpdatedDateTime": "2026-10-18T11:05:00"},
            {"symbol": "B", "lastUpdatedDateTime": "2026-10-18T11:07:30"},
        ],
    )
    assert ts == datetime(2026, 10, 18, 5, 22, 30, tzinfo=bench.UTC)


def test_extract_returns_none_when_absent_or_empty():
    assert bench.extract_source_ts("market-summary", {"a": 1}) == (None, None)
    assert bench.extract_source_ts("lives-market", []) == (None, None)
    assert bench.extract_source_ts("market-open", {"isOpen": "CLOSE"}) == (None, None)


def test_extract_yonepse_timestamps():
    _, ts = bench.extract_source_ts(
        "yonepse-live", [{"last_updated": "2026-10-12T14:59:52.670172"}]
    )
    assert ts == datetime(2026, 10, 12, 9, 14, 52, 670172, tzinfo=bench.UTC)
    field, ts2 = bench.extract_source_ts("yonepse-status", {"last_checked": "2026-10-12T10:17:11"})
    assert field == "last_checked" and ts2 is not None


# -------------------------------------------------------------------- cadence
def _rec(endpoint, start, h, status=200, records=1, ts=None):
    return {
        "endpoint": endpoint,
        "request_start_utc": start,
        "status": status,
        "duration_ms": 10.0,
        "records": records,
        "snapshot_hash": h,
        "source_ts_utc": ts,
        "source_ts_field": "asOf" if ts else None,
    }


def test_cadence_none_when_snapshot_never_changes():
    out = bench.estimate_cadence(
        [
            _rec("lives-market", "2026-10-18T05:15:00+00:00", "sha256:same"),
            _rec("lives-market", "2026-10-18T05:16:00+00:00", "sha256:same"),
            _rec("lives-market", "2026-10-18T05:17:00+00:00", "sha256:same"),
        ]
    )
    assert out["distinct_snapshots"] == 1
    assert out["changes_observed"] == 0
    assert out["cadence_seconds"] is None


def test_cadence_measures_interval_between_changes():
    out = bench.estimate_cadence(
        [
            _rec("lives-market", "2026-10-18T05:15:00+00:00", "a"),
            _rec("lives-market", "2026-10-18T05:16:00+00:00", "b"),  # +60s
            _rec("lives-market", "2026-10-18T05:17:00+00:00", "c"),  # +60s
        ]
    )
    assert out["distinct_snapshots"] == 3
    assert out["changes_observed"] == 2
    assert out["cadence_seconds"] == 60.0


def test_cadence_handles_a_single_change_and_ignores_repeats():
    out = bench.estimate_cadence(
        [
            _rec("lives-market", "2026-10-18T05:15:00+00:00", "a"),
            _rec("lives-market", "2026-10-18T05:15:30+00:00", "a"),  # repeat
            _rec("lives-market", "2026-10-18T05:16:00+00:00", "b"),  # change @60s
        ]
    )
    assert out["changes_observed"] == 1
    assert out["cadence_seconds"] == 60.0


# ------------------------------------------------------------------ summarize
def test_summarize_separates_latency_freshness_and_cadence():
    records = [
        _rec("market-open", "2026-10-18T05:15:00+00:00", "a", ts="2026-10-18T05:15:00+00:00"),
        _rec("market-open", "2026-10-18T05:16:00+00:00", "b", ts="2026-10-18T05:15:30+00:00"),
        _rec("lives-market", "2026-10-18T05:15:00+00:00", "e", records=0),  # empty board
    ]
    s = bench.summarize(records)
    assert s["true_event_latency"] == "UNMEASURABLE"
    assert s["samples"] == 3 and s["successes"] == 3
    mo = s["endpoints"]["market-open"]
    assert mo["request_duration_ms"]["median"] == 10.0
    assert mo["freshness"]["samples_with_source_ts"] == 2
    assert mo["freshness"]["pct_le_5s"] == 50.0  # ages 0s and 30s
    lm = s["endpoints"]["lives-market"]
    assert lm["freshness"]["pct_le_5s"] is None  # no source timestamp
    assert lm["cadence"]["cadence_seconds"] is None


# ----------------------------------------------------------------- gate tests
def test_schedule_only_makes_zero_nepse_requests(monkeypatch, capsys):
    monkeypatch.delenv(ol.AUTH_ENV, raising=False)

    class _Explode:
        def __init__(self, *a, **k):
            raise AssertionError("NEPSE client must NOT be constructed when unauthorised")

    monkeypatch.setattr(SCRIPT.ol, "NepseOfficialLiveClient", _Explode)
    rc = SCRIPT.main(["--source", "nepse"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SCHEDULE-ONLY" in out
    assert "MEGATOOL_NEPSE_API_AUTHORIZED=1" in out
    assert "crontab" in out


def test_off_hours_authorized_run_does_not_probe(monkeypatch, capsys):
    # Authorised, but the clock is outside the session → schedule-only, no probe.
    monkeypatch.setenv(ol.AUTH_ENV, "1")
    monkeypatch.setattr(SCRIPT, "_utcnow", lambda: datetime(2026, 10, 15, 20, 0, tzinfo=bench.NPT))

    class _Explode:
        def __init__(self, *a, **k):
            raise AssertionError("must not probe outside market hours")

    monkeypatch.setattr(SCRIPT.ol, "NepseOfficialLiveClient", _Explode)
    rc = SCRIPT.main(["--source", "nepse"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SCHEDULE-ONLY" in out and "outside the Sun–Thu" in out


def test_interval_floor_is_enforced(capsys):
    rc = SCRIPT.main(["--source", "nepse", "--interval", "1"])
    assert rc == 2
    assert "floor" in capsys.readouterr().err


# --------------------------------------------------------------------- replay
def test_replay_reads_jsonl_without_network(tmp_path, capsys):
    p = tmp_path / "s.jsonl"
    lines = [
        {
            "endpoint": "market-open",
            "request_start_utc": "2026-10-18T05:15:00+00:00",
            "status": 200,
            "duration_ms": 12.0,
            "records": 3,
            "snapshot_hash": "a",
            "source_ts_utc": "2026-10-18T05:15:00+00:00",
            "source_ts_field": "asOf",
        },
        {
            "endpoint": "market-open",
            "request_start_utc": "2026-10-18T05:16:00+00:00",
            "status": 200,
            "duration_ms": 8.0,
            "records": 3,
            "snapshot_hash": "b",
            "source_ts_utc": "2026-10-18T05:15:00+00:00",
            "source_ts_field": "asOf",
        },
        "not-json-garbage",
        {"no_endpoint": True},
    ]
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    out_path = tmp_path / "summary.json"
    rc = SCRIPT.main(["--replay", str(p), "--json-out", str(out_path)])
    assert rc == 0
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["records_read"] == 2  # garbage and non-record lines skipped
    assert summary["true_event_latency"] == "UNMEASURABLE"
    assert summary["endpoints"]["market-open"]["cadence"]["cadence_seconds"] == 60.0


def test_replay_missing_file_returns_2(tmp_path, capsys):
    rc = SCRIPT.main(["--replay", str(tmp_path / "nope.jsonl")])
    assert rc == 2


# ------------------------------------------------------------------ scheduling
def test_cron_entry_has_five_fields_and_points_at_a_trading_day():
    nxt = bench.next_session_open(datetime(2026, 10, 15, 20, 0, tzinfo=bench.NPT))
    line = SCRIPT._cron_entry(nxt, "echo hi")
    fields = line.split()
    assert len(fields) >= 6
    assert 0 <= int(fields[4]) <= 6  # cron day-of-week


def test_launchd_plist_contains_the_command():
    nxt = bench.next_session_open(datetime(2026, 10, 15, 20, 0, tzinfo=bench.NPT))
    xml = SCRIPT._launchd_plist("com.megatool.benchmark", nxt, "echo hi")
    assert "com.megatool.benchmark" in xml and "StartCalendarInterval" in xml and "echo hi" in xml
