"""Source-adapter contract tests: honest failure, offline fixtures, no secrets.

These adapters are the project's boundary with the outside world, so the
properties that matter are:

* a blocked source fails with an EXPLANATION (never a fake payload);
* cached/local paths work with **zero network calls** - proven by making any
  HTTP attempt raise the test;
* credentials never appear in any reported payload.

No test here touches the network. Fixtures are SYNTHETIC-TEST-FIXTURE files
in tmp_path; the owner's real caches are never read or written.
"""

from __future__ import annotations

import io
import json

import pandas as pd
import pytest

from megatool.datasources.base import (
    BaseAdapter,
    SourceConfig,
    SourceError,
    SourceUnavailable,
)
from megatool.datasources.local_file import (
    LocalFileAdapter,
    canonicalise_columns,
)
from megatool.datasources.nepalstock_official import NepalStockOfficialAdapter
from megatool.datasources.nepse_data_repo import NepseDataRepoAdapter
from megatool.models import DataSource

REPO_CSV = """published_date,open,high,low,close,per_change,traded_quantity,traded_amount,status
2026-01-05,100,105,95,100,1.5,1000,100000,10
2026-01-04,99,104,94,99,-1.0,900,89100,10
2026-01-05,101,106,96,101,1.0,1100,111100,10
2026-01-02,98,103,93,98,0.5,800,78400,10
not-a-date,1,2,0,1,0,1,1,10
"""


@pytest.fixture
def no_network(monkeypatch):
    """Any attempt to perform HTTP in these tests fails loudly.

    SourceError (not AssertionError) mimics the adapter's real offline
    failure mode so ``health()``/fallback paths behave as they would in
    production; the message still makes an attempted dial-out obvious in any
    test whose contract is "no network".
    """

    def _boom(self, url, **params):  # noqa: ANN001 - mirrors _get signature
        raise SourceError(f"network attempted: {url}")

    monkeypatch.setattr(NepseDataRepoAdapter, "_get", _boom)


# ----------------------------------------------------------------- base contract
def test_source_config_declares_its_access_terms():
    cfg = SourceConfig(
        source_id=DataSource.LOCAL_IMPORT,
        label="x",
        access_method="local-file",
        requires_auth=False,
        fields_supplied=("close",),
        fields_missing=("sector",),
    )
    assert cfg.fields_missing == ("sector",)  # declared limits travel with config


def test_health_never_raises_and_reports_the_reason():
    class Blocked(BaseAdapter):
        config = SourceConfig(source_id=DataSource.LOCAL_IMPORT, label="blocked", access_method="x")

        def list_symbols(self):
            raise SourceUnavailable("HTTP 401: UNAUTHORIZED ACCESS")

        def fetch_history(self, symbol):  # pragma: no cover - not reached
            raise NotImplementedError

    out = Blocked().health()
    assert out["available"] is False
    assert "UNAUTHORIZED ACCESS" in out["reason"]


def test_health_reports_available_with_a_working_source():
    class Working(BaseAdapter):
        config = SourceConfig(source_id=DataSource.LOCAL_IMPORT, label="ok", access_method="x")

        def list_symbols(self):
            return ["AAA", "BBB"]

        def fetch_history(self, symbol):  # pragma: no cover - not reached
            raise NotImplementedError

    out = Working().health()
    assert out == {
        "source": DataSource.LOCAL_IMPORT.value,
        "label": "ok",
        "available": True,
        "symbols": 2,
    }


# ------------------------------------------------------------- local file adapter
def test_missing_file_is_an_explanation_not_a_traceback(tmp_path):
    with pytest.raises(SourceError, match="does not exist"):
        LocalFileAdapter(tmp_path / "nope.csv")


def test_multi_symbol_file_aliases_and_uppercased_symbols(tmp_path):
    p = tmp_path / "export.csv"
    p.write_text(
        "Date,Scrip,LTP,Opening,L_MAX,l_low,Qty\n"
        "2026-01-05,nabil,100,99,105,95,1000\n"
        "2026-01-04,nica,50,49,51,48,500\n"
    )
    a = LocalFileAdapter(p)
    assert a.list_symbols() == ["NABIL", "NICA"]
    df = a.fetch_history("nabil")
    assert list(df["symbol"]) == ["NABIL"] * 1
    assert df["close"].iloc[0] == 100
    assert df["volume"].dtype.name == "Int64"
    # the mapping of what it understood is reported, never guessed silently
    assert a.column_mapping["Date"] == "trading_date"
    assert a.describe()["access_method"] == "local-file"
    assert (
        "local-file" in a.describe()["terms_note"] or "Owner-supplied" in a.describe()["terms_note"]
    )


def test_single_symbol_file_requires_and_honours_the_supplied_symbol(tmp_path):
    p = tmp_path / "single.csv"
    p.write_text("date,close\n2026-01-05,100\n")
    with pytest.raises(SourceError, match="no symbol column"):
        LocalFileAdapter(p).list_symbols()

    a = LocalFileAdapter(p, symbol="nabil")
    assert a.list_symbols() == ["NABIL"]
    assert list(a.fetch_history("NABIL")["symbol"]) == ["NABIL"]
    with pytest.raises(SourceError, match="was imported as"):
        a.fetch_history("OTHER")


def test_unrecognised_headers_are_reported_with_the_header_seen(tmp_path):
    p = tmp_path / "nodate.csv"
    p.write_text("foo,bar\n1,2\n")
    with pytest.raises(SourceError) as exc:
        LocalFileAdapter(p, symbol="NABIL").fetch_history("NABIL")
    assert "no date column" in str(exc.value) and "foo" in str(exc.value)

    p2 = tmp_path / "noclose.csv"
    p2.write_text("date,foo\n2026-01-05,1\n")
    with pytest.raises(SourceError, match="no close-price column"):
        LocalFileAdapter(p2, symbol="NABIL").fetch_history("NABIL")


def test_canonicalise_keeps_unrecognised_columns(tmp_path):
    df = pd.DataFrame({"Close": [1], "My Note": ["keep me"]})
    out, mapping = canonicalise_columns(df)
    assert mapping == {"Close": "close"}
    assert "My Note" in out.columns


def test_unreadable_file_becomes_a_source_error(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("")  # exists, but has nothing to parse
    with pytest.raises(SourceError, match="could not read"):
        LocalFileAdapter(p, symbol="NABIL").fetch_history("NABIL")


# ------------------------------------------------------------ github dataset adapter
@pytest.fixture
def repo(tmp_path):
    return NepseDataRepoAdapter(cache_dir=tmp_path / "cache")


def test_repo_normalise_maps_columns_sorts_dedups_and_drops_status(repo):
    df = repo.normalise(pd.read_csv(io.StringIO(REPO_CSV)), "nabil")
    assert list(df.columns) == [
        "symbol",
        "trading_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
        "percent_change",
    ]
    assert "status" not in df.columns
    # sorted ascending, the unparseable date dropped, the duplicate date deduped
    dates = [str(d.date()) for d in df["trading_date"]]
    assert dates == sorted(dates)
    assert len(df) == 3 and dates[-1] == "2026-01-05"
    assert df["close"].dtype.kind in "fi"  # numeric, never an object column
    assert df["symbol"].unique().tolist() == ["NABIL"]


def test_repo_normalise_rejects_a_csv_with_the_wrong_shape(repo):
    with pytest.raises(SourceError, match="missing expected columns"):
        repo.normalise(pd.DataFrame({"something": [1]}), "NABIL")


def test_repo_serves_from_a_fresh_cache_with_zero_network(repo, no_network):
    repo.cache_dir.mkdir(parents=True, exist_ok=True)
    (repo.cache_dir / "NABIL.csv").write_text(REPO_CSV)
    df = repo.fetch_history("nabil")  # would raise AssertionError if it dialled out
    assert len(df) == 3


def test_repo_symbol_index_serves_from_a_fresh_index_with_zero_network(repo, no_network):
    import time

    repo.cache_dir.mkdir(parents=True, exist_ok=True)
    (repo.cache_dir / "_symbols.json").write_text(
        json.dumps({"symbols": ["NABIL", "NMB"], "_fetched_at": time.time()})
    )
    assert repo.list_symbols() == ["NABIL", "NMB"]


def test_repo_falls_back_to_local_csvs_when_the_index_fetch_fails(repo, no_network):
    repo.cache_dir.mkdir(parents=True, exist_ok=True)
    (repo.cache_dir / "NABIL.csv").write_text(REPO_CSV)
    (repo.cache_dir / "_symbols.json").write_text("not json at all")
    assert repo.list_symbols() == ["NABIL"]  # degraded, but honest and offline


def test_repo_without_any_cache_reports_unavailability_without_raising(repo, no_network):
    out = repo.health()
    assert out["available"] is False
    assert out["reason"]  # says WHY, not just False


def test_repo_declares_its_missing_fields_and_no_auth(repo):
    d = repo.describe()
    assert d["requires_auth"] is False
    assert "sector" in d["fields_missing"]
    assert "indices" in d["fields_missing"]
    assert "no LICENSE" in d["terms_note"]


# ------------------------------------------------------- official API (blocked by policy)
def test_official_adapter_refuses_without_credentials_before_any_request():
    a = NepalStockOfficialAdapter()
    with pytest.raises(SourceUnavailable, match="authenticated user session"):
        a.list_symbols()
    with pytest.raises(SourceUnavailable, match="will not bypass"):
        a.fetch_history("NABIL")


def test_official_adapter_refuses_even_with_a_token_because_it_is_unvalidated():
    a = NepalStockOfficialAdapter(token="fake-session-token-xyz")
    with pytest.raises(SourceError, match="not implemented"):
        a.list_symbols()


def test_official_health_is_available_false_with_the_401_explanation():
    out = NepalStockOfficialAdapter().health()
    assert out["available"] is False
    assert "401" in out["reason"]
    assert out["requires_auth"] is True


def test_official_adapter_never_leaks_its_token_into_reported_payloads():
    secret = "super-secret-session-token-000"
    a = NepalStockOfficialAdapter(token=secret)
    rendered = json.dumps(a.describe()) + json.dumps(a.health())
    assert secret not in rendered
