"""Tests for certificate-expiry inspection and the source-health cache.

No network is used: the certificate *parsing* and *warning threshold* logic is
tested directly, while the live TLS handshake is exercised only by the gated
health-check script, never by the test suite.
"""

from __future__ import annotations

from megatool import source_health as sh


# ------------------------------------------------------------------- warnings
def test_warning_none_when_comfortably_valid():
    assert sh.certificate_warning({"days_remaining": 90, "not_after": "2027-01-01"}) is None
    assert sh.certificate_warning({"days_remaining": 30.1, "not_after": "x"}) is None


def test_warning_at_the_30_day_threshold():
    msg = sh.certificate_warning({"days_remaining": 30, "not_after": "2026-12-10T00:00:00+00:00"})
    assert msg is not None and "expires in" in msg and "2026-12-10" in msg


def test_warning_for_the_known_nepse_certificate_window():
    # The exchange certificate expires 2026-12-10; at 8 weeks out this must warn.
    msg = sh.certificate_warning(
        {"days_remaining": 56, "not_after": "2026-12-10T00:00:00+00:00"}, warn_days=60
    )
    assert msg is not None and "expires in" in msg


def test_warning_expired_and_unknown():
    assert sh.certificate_warning({"days_remaining": 0}).startswith("certificate EXPIRED")
    assert sh.certificate_warning({"days_remaining": -5}).startswith("certificate EXPIRED")
    assert sh.certificate_warning({"days_remaining": None}).startswith("certificate expiry unknown")
    assert sh.certificate_warning(None).startswith("certificate expiry unknown")


# ------------------------------------------------------------------- parsing
def test_parse_cert_time_reads_openssl_format():
    dt = sh._parse_cert_time("Dec 10 23:59:59 2026 GMT")
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == (2026, 12, 10)
    assert dt.tzinfo is not None


def test_parse_cert_time_rejects_garbage():
    assert sh._parse_cert_time("not a date") is None
    assert sh._parse_cert_time(None) is None
    assert sh._parse_cert_time("") is None


def test_flat_name_flattens_rdns():
    entries = ((("commonName", "www.nepalstock.com.np"),), (("organizationName", "NEPSE"),))
    assert sh._flat_name(entries) == "commonName=www.nepalstock.com.np, organizationName=NEPSE"
    assert sh._flat_name(None) is None


# ---------------------------------------------------------------- health cache
def test_read_health_missing_and_garbage(tmp_path):
    p = tmp_path / "h.json"
    assert sh.read_health(p) == {}
    p.write_text("{not json", encoding="utf-8")
    assert sh.read_health(p) == {}
    p.write_text("[1,2,3]", encoding="utf-8")
    assert sh.read_health(p) == {}


def test_update_and_view_roundtrip(tmp_path):
    p = tmp_path / "h.json"
    sh.update_source_health(
        "nepse",
        {
            "last_checked_at_utc": "2026-10-18T06:00:00+00:00",
            "certificate": {"days_remaining": 20, "not_after": "2026-12-10T00:00:00+00:00"},
            "circuit": {"state": "closed", "failures": 0},
        },
        p,
    )
    view = sh.source_health_view("nepse", p)
    assert view["checked"] is True
    assert view["certificate_warning"] is not None
    assert view["circuit"]["state"] == "closed"
    assert "not a continuous monitor" in view["note"]


def test_update_merges_without_dropping_fields(tmp_path):
    p = tmp_path / "h.json"
    sh.update_source_health("nepse", {"a": 1, "b": 2}, p)
    sh.update_source_health("nepse", {"b": 3}, p)
    rec = sh.read_health(p)["nepse"]
    assert rec == {"a": 1, "b": 3}


def test_view_of_unknown_source_is_unchecked(tmp_path):
    view = sh.source_health_view("nope", tmp_path / "h.json")
    assert view["checked"] is False
    assert "no health check recorded" in view["reason"]


def test_health_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom.json"
    monkeypatch.setenv("MEGATOOL_HEALTH_PATH", str(target))
    assert sh.health_path() == target


def test_health_view_never_exposes_sensitive_material(tmp_path):
    """The safe view must expose only the certificate's public metadata."""
    p = tmp_path / "h.json"
    sh.update_source_health(
        "nepse",
        {
            "last_checked_at_utc": "T",
            "certificate": {"subject": "CN=x", "days_remaining": 20, "not_after": "y"},
            "access_token": "SHOULD-NOT-PROPAGATE",
            "cookie": "SHOULD-NOT-PROPAGATE",
        },
        p,
    )
    view = sh.source_health_view("nepse", p)
    flat = str(view)
    assert "SHOULD-NOT-PROPAGATE" not in flat
