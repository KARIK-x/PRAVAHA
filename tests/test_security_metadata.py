"""Security-metadata tests: upsert preservation, the reader, eligibility filters (T-M1).

Every fixture here is synthetic and deterministic, built into a throwaway
DuckDB file; nothing asserts anything about real NEPSE symbols, sectors or
listing statuses. What is pinned is contract-level:

* an omitted (or NULL) field must never erase stored metadata — in particular
  a partial refresh must never flip a delisted/merged/suspended security back
  to active and must never erase a recorded successor symbol;
* ``securities_meta()`` returns exactly what is stored, with unknown staying
  explicitly unknown;
* the scanner/rank default excludes verified non-tradable securities
  (``DELISTED``, ``SUSPENDED``, ``MERGED``) while keeping ``ACTIVE`` and
  ``UNKNOWN`` visible; ``UNKNOWN`` is allowed so missing metadata does not
  silently erase valid securities, but the uncertainty is observable;
* ``MERGED`` is never silently converted to ``DELISTED``;
* delisted/inactive securities keep their price history and stay analysable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool.market_store import (
    STATUS_ACTIVE,
    STATUS_DELISTED,
    STATUS_MERGED,
    STATUS_SUSPENDED,
    STATUS_UNKNOWN,
    MarketStore,
    eligibility_from_meta,
)
from megatool.scanner import ScreenNode, run_screen

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _bars(symbol: str, closes: np.ndarray, start: str = "2026-01-01") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    vol = np.full(len(closes), 10_000.0)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": dates,
            "open": closes,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": vol.astype(np.int64),
            "turnover": closes * vol,
            "percent_change": np.nan,
            "source": "test",
            "retrieved_at": RETRIEVED,
        }
    )


@pytest.fixture
def store(tmp_path) -> MarketStore:
    s = MarketStore(tmp_path / "meta.duckdb")
    yield s
    s.close()


def _row(store: MarketStore, symbol: str):
    return store.execute(
        "SELECT name, sector, instrument_type, status, delisted, successor_symbol "
        "FROM security_master WHERE symbol = ?",
        (symbol,),
    ).fetchone()


_ALWAYS_TRUE = ScreenNode.from_dict(
    {"op": "AND", "conditions": [{"metric": "close", "operator": "gt", "value": 0}]}
)


# ------------------------------------------- upsert: omitted must not erase


def test_omitted_delisted_preserves_existing_true(store):
    store.upsert_securities(
        [{"symbol": "ABC", "name": "Alpha", "source": "test", "delisted": True}]
    )
    # A partial refresh that says nothing about delisted must not reactivate it.
    store.upsert_securities([{"symbol": "ABC", "name": "Alpha Ltd", "source": "test"}])
    name, sector, itype, status, delisted, successor = _row(store, "ABC")
    assert delisted is True
    assert status == STATUS_DELISTED


def test_explicit_false_overwrites_true(store):
    store.upsert_securities(
        [{"symbol": "ABC", "name": "Alpha", "source": "test", "delisted": True}]
    )
    store.upsert_securities([{"symbol": "ABC", "source": "test", "delisted": False}])
    assert _row(store, "ABC")[4] is False
    assert _row(store, "ABC")[3] == STATUS_UNKNOWN


def test_explicit_true_overwrites_false(store):
    store.upsert_securities([{"symbol": "ABC", "name": "A", "source": "test"}])
    store.upsert_securities([{"symbol": "ABC", "source": "test", "delisted": True}])
    assert _row(store, "ABC")[4] is True
    assert _row(store, "ABC")[3] == STATUS_DELISTED


def test_explicit_none_preserves_like_omission(store):
    # None and "key absent" are the same contract: preserve. Never reactivate.
    store.upsert_securities([{"symbol": "ABC", "name": "A", "source": "test", "delisted": True}])
    store.upsert_securities([{"symbol": "ABC", "source": "test", "delisted": None}])
    assert _row(store, "ABC")[4] is True


def test_new_security_without_key_gets_schema_default(store):
    store.upsert_securities([{"symbol": "NEW", "source": "test"}])
    name, sector, itype, status, delisted, successor = _row(store, "NEW")
    assert delisted is False
    assert status == STATUS_UNKNOWN


def test_new_security_with_explicit_value_stores_it(store):
    store.upsert_securities([{"symbol": "NEW", "source": "test", "delisted": True}])
    assert _row(store, "NEW")[4] is True


def test_supplied_values_coerced_like_before(store):
    # Established contract: bool() coercion, NULL is never stored.
    store.upsert_securities([{"symbol": "ABC", "source": "test"}])
    store.upsert_securities([{"symbol": "ABC", "source": "test", "delisted": 1}])
    assert _row(store, "ABC")[4] is True


def test_sibling_fields_keep_calesce_semantics(store):
    store.upsert_securities(
        [{"symbol": "ABC", "name": "Alpha", "sector": "Bank", "source": "test"}]
    )
    # None preserves; a real value replaces.
    store.upsert_securities(
        [{"symbol": "ABC", "name": None, "sector": "Hydropower", "source": "test"}]
    )
    assert _row(store, "ABC")[:2] == ("Alpha", "Hydropower")


def test_set_sectors_still_never_touches_delisted(store):
    # The pre-existing guarantee must survive the upsert change.
    store.upsert_securities(
        [{"symbol": "ABC", "name": "Alpha", "source": "test", "delisted": True}]
    )
    store.set_sectors({"ABC": "Bank"})
    name, sector, itype, status, delisted, successor = _row(store, "ABC")
    assert sector == "Bank"
    assert delisted is True


# ----------------------------------------------- status / successor handling


def test_status_is_normalised_to_canonical_values(store):
    store.upsert_securities(
        [
            {"symbol": "A1", "source": "test", "status": "listed"},
            {"symbol": "A2", "source": "test", "status": "active"},
            {"symbol": "A3", "source": "test", "status": "MERGED"},
        ]
    )
    assert _row(store, "A1")[3] == STATUS_ACTIVE
    assert _row(store, "A2")[3] == STATUS_ACTIVE
    assert _row(store, "A3")[3] == STATUS_MERGED
    # status ACTIVE implies delisted=False.
    assert _row(store, "A1")[4] is False
    # status MERGED implies delisted=False (merged != delisted).
    assert _row(store, "A3")[4] is False


def test_invalid_status_rejects_row(store):
    with pytest.raises(ValueError, match="invalid status"):
        store.upsert_securities([{"symbol": "BAD", "source": "test", "status": "banana"}])


def test_status_takes_precedence_over_delisted(store):
    # If only status is supplied, delisted is derived from it.
    store.upsert_securities([{"symbol": "ABC", "source": "test", "status": "DELISTED"}])
    assert _row(store, "ABC")[3] == STATUS_DELISTED
    assert _row(store, "ABC")[4] is True


def test_delisted_without_status_derives_status(store):
    store.upsert_securities([{"symbol": "ABC", "source": "test", "delisted": True}])
    assert _row(store, "ABC")[3] == STATUS_DELISTED


def test_contradictory_status_and_delisted_rejected(store):
    with pytest.raises(ValueError, match="contradictory"):
        store.upsert_securities(
            [{"symbol": "ABC", "source": "test", "status": "ACTIVE", "delisted": True}]
        )


def test_omitted_status_preserves_existing_non_default(store):
    store.upsert_securities([{"symbol": "ABC", "source": "test", "status": "SUSPENDED"}])
    store.upsert_securities([{"symbol": "ABC", "source": "test", "name": "New Name"}])
    assert _row(store, "ABC")[3] == STATUS_SUSPENDED


def test_successor_symbol_stored_and_preserved(store):
    store.upsert_securities(
        [{"symbol": "ABC", "source": "test", "status": "MERGED", "successor_symbol": "XYZ"}]
    )
    assert _row(store, "ABC")[5] == "XYZ"
    # Partial refresh must not erase the successor.
    store.upsert_securities([{"symbol": "ABC", "source": "test", "name": "Merged Co"}])
    assert _row(store, "ABC")[5] == "XYZ"


def test_explicit_empty_successor_symbol_clears_value(store):
    store.upsert_securities([{"symbol": "ABC", "source": "test", "successor_symbol": "XYZ"}])
    store.upsert_securities([{"symbol": "ABC", "source": "test", "successor_symbol": ""}])
    assert _row(store, "ABC")[5] is None


# ------------------------------------------------- securities_meta() reader


def test_securities_meta_structure(store):
    store.upsert_securities(
        [
            {
                "symbol": "ABC",
                "name": "Alpha",
                "sector": "Bank",
                "instrument_type": "ordinary",
                "source": "test",
            },
            {"symbol": "XYZ", "name": "Xeno", "source": "test"},
        ]
    )
    meta = store.securities_meta()
    assert set(meta) == {"ABC", "XYZ"}
    assert meta["ABC"] == {
        "name": "Alpha",
        "sector": "Bank",
        "sector_source": None,
        "sector_retrieved_at": None,
        "sector_observed_date": None,
        "instrument_type": "ordinary",
        "status": STATUS_UNKNOWN,
        "delisted": False,
        "successor_symbol": None,
    }
    # Incomplete metadata stays incomplete, not filled in.
    assert meta["XYZ"] == {
        "name": "Xeno",
        "sector": None,
        "sector_source": None,
        "sector_retrieved_at": None,
        "sector_observed_date": None,
        "instrument_type": None,
        "status": STATUS_UNKNOWN,
        "delisted": False,
        "successor_symbol": None,
    }


def test_securities_meta_subset_and_case_normalisation(store):
    store.upsert_securities(
        [{"symbol": "ABC", "source": "test"}, {"symbol": "XYZ", "source": "test"}]
    )
    meta = store.securities_meta(["abc", "NOSUCH"])
    assert set(meta) == {"ABC"}  # unknown symbol simply absent, not invented


def test_securities_meta_empty_iterable_short_circuits(store):
    store.upsert_securities([{"symbol": "ABC", "source": "test"}])
    assert store.securities_meta([]) == {}


def test_securities_meta_missing_row_is_absent_not_guessed(store):
    # A symbol with bars but no security_master row must read as "no metadata".
    assert store.securities_meta(["GHOST"]) == {}


def test_securities_meta_reports_legacy_null_delisted_as_none(store):
    store.upsert_securities([{"symbol": "ABC", "source": "test"}])
    store.execute("UPDATE security_master SET delisted = NULL WHERE symbol = 'ABC'")
    meta = store.securities_meta()["ABC"]
    assert meta["delisted"] is None
    assert meta["status"] == STATUS_UNKNOWN


def test_securities_meta_derives_delisted_status_from_legacy_flag(store):
    store.upsert_securities([{"symbol": "ABC", "source": "test", "delisted": True}])
    store.execute("UPDATE security_master SET status = NULL WHERE symbol = 'ABC'")
    assert store.securities_meta()["ABC"]["status"] == STATUS_DELISTED


# --------------------------------------------- eligibility_from_meta (pure)


def test_no_filters_allows_everything_including_no_metadata():
    assert eligibility_from_meta(None) == (True, "")
    assert eligibility_from_meta({"delisted": True}) == (True, "")
    assert eligibility_from_meta({}, exclude_delisted=False, instrument_types=None) == (True, "")


def test_exclude_delisted_excludes_verified_non_tradable_statuses():
    for status in (STATUS_DELISTED, STATUS_SUSPENDED, STATUS_MERGED):
        allowed, reason = eligibility_from_meta({"status": status}, exclude_delisted=True)
        assert allowed is False
        assert status in reason
        assert "not currently tradable" in reason


def test_exclude_delisted_allows_active():
    assert eligibility_from_meta({"status": STATUS_ACTIVE}, exclude_delisted=True) == (True, "")


def test_unknown_status_is_allowed_but_observable():
    allowed, reason = eligibility_from_meta(None, exclude_delisted=True)
    assert allowed is True
    assert "unknown" in reason
    assert "uncertain" in reason

    allowed2, reason2 = eligibility_from_meta({"status": STATUS_UNKNOWN}, exclude_delisted=True)
    assert allowed2 is True
    assert "uncertain" in reason2


def test_legacy_delisted_true_maps_to_excluded_status():
    allowed, reason = eligibility_from_meta({"delisted": True}, exclude_delisted=True)
    assert allowed is False
    assert STATUS_DELISTED in reason


def test_instrument_type_filter_is_case_insensitive_and_explicit():
    meta = {"status": STATUS_ACTIVE, "instrument_type": "Ordinary"}
    assert eligibility_from_meta(meta, instrument_types=["ORDINARY"])[0] is True
    allowed, reason = eligibility_from_meta(meta, instrument_types=["debenture"])
    assert allowed is False
    # The reason names the STORED value verbatim, never the requested one.
    assert "Ordinary" in reason and "not in the requested" in reason


def test_unknown_instrument_type_is_excluded_not_guessed():
    allowed, reason = eligibility_from_meta(
        {"status": STATUS_ACTIVE, "instrument_type": None}, instrument_types=["ordinary"]
    )
    assert allowed is False
    assert "unknown" in reason


def test_empty_instrument_list_is_an_active_filter_matching_nothing():
    assert (
        eligibility_from_meta(
            {"status": STATUS_ACTIVE, "instrument_type": "ordinary"}, instrument_types=[]
        )[0]
        is False
    )


def test_merged_is_never_treated_as_delisted_in_eligibility():
    # The reason must name MERGED, not silently use a delisted path.
    allowed, reason = eligibility_from_meta({"status": STATUS_MERGED}, exclude_delisted=True)
    assert allowed is False
    assert STATUS_MERGED in reason
    assert STATUS_DELISTED not in reason


# -------------------------------------------------- run_screen: default filter


@pytest.fixture
def screened_store(tmp_path) -> MarketStore:
    """ACTIVE, SUSPENDED, MERGED, DELISTED and GHOST (bars, no row)."""
    s = MarketStore(tmp_path / "screen.duckdb")
    n = 60
    x = np.arange(n, dtype=float)
    for sym in ("ACTIVE", "SUSPENDED", "MERGED", "DELISTED", "GHOST"):
        s.upsert_bars(_bars(sym, 100.0 + x))
    s.upsert_securities(
        [
            {
                "symbol": "ACTIVE",
                "name": "Active Co",
                "instrument_type": "ordinary",
                "source": "test",
                "status": STATUS_ACTIVE,
            },
            {
                "symbol": "SUSPENDED",
                "name": "Suspended Co",
                "instrument_type": "ordinary",
                "source": "test",
                "status": STATUS_SUSPENDED,
            },
            {
                "symbol": "MERGED",
                "name": "Merged Co",
                "instrument_type": "ordinary",
                "source": "test",
                "status": STATUS_MERGED,
                "successor_symbol": "ACTIVE",
            },
            {
                "symbol": "DELISTED",
                "name": "Delisted Co",
                "instrument_type": "ordinary",
                "source": "test",
                "status": STATUS_DELISTED,
            },
            # GHOST deliberately gets no security_master row.
        ]
    )
    yield s
    s.close()


def test_default_screen_excludes_verified_non_tradable_and_includes_unknown(
    screened_store,
):
    res = {r.symbol: r for r in run_screen(screened_store, _ALWAYS_TRUE)}
    assert set(res) == {"ACTIVE", "SUSPENDED", "MERGED", "DELISTED", "GHOST"}
    assert res["ACTIVE"].eligible is True
    assert res["SUSPENDED"].eligible is False
    assert res["MERGED"].eligible is False
    assert res["DELISTED"].eligible is False
    # Unknown metadata is allowed so valid securities are not erased, but the
    # uncertainty is observable in the note.
    assert res["GHOST"].eligible is True
    assert "uncertain" in res["GHOST"].note


def test_screen_with_filters_disabled_includes_everything(screened_store):
    res = {r.symbol: r for r in run_screen(screened_store, _ALWAYS_TRUE, exclude_delisted=False)}
    assert all(r.eligible for r in res.values())


def test_instrument_types_filter_uses_stored_metadata(screened_store):
    res = {
        r.symbol: r for r in run_screen(screened_store, _ALWAYS_TRUE, instrument_types=["ordinary"])
    }
    # Default inactive exclusion still applies; only ACTIVE survives.
    assert res["ACTIVE"].eligible is True
    assert res["SUSPENDED"].eligible is False
    assert res["MERGED"].eligible is False
    assert res["DELISTED"].eligible is False
    # GHOST's type is unknown -> not proof of eligibility.
    assert res["GHOST"].eligible is False
    assert "unknown" in res["GHOST"].note


def test_combined_filters_and_inactive_security_stays_analysable(screened_store):
    res = {
        r.symbol: r
        for r in run_screen(
            screened_store, _ALWAYS_TRUE, exclude_delisted=True, instrument_types=["ordinary"]
        )
    }
    assert res["DELISTED"].eligible is False
    # The bars were never deleted or hidden: history reads still work.
    df = screened_store.get_bars("DELISTED")
    assert len(df) == 60
    # And with the filters off the same symbol screens normally.
    earlier = {
        r.symbol: r
        for r in run_screen(
            screened_store,
            _ALWAYS_TRUE,
            symbols=["DELISTED"],
            exclude_delisted=False,
        )
    }
    assert earlier["DELISTED"].eligible is True


def test_filter_decision_is_the_shared_pure_function(screened_store):
    # Scanner consistency guarantee: same inputs, same answer as eligibility_from_meta.
    meta = screened_store.securities_meta(["MERGED"])["MERGED"]
    assert eligibility_from_meta(meta, exclude_delisted=True) == (
        False,
        "status=MERGED; not currently tradable",
    )


def test_successor_symbol_is_returned_not_invented(screened_store):
    meta = screened_store.securities_meta(["MERGED"])["MERGED"]
    assert meta["successor_symbol"] == "ACTIVE"
    # A symbol with no successor evidence returns None, not a guessed mapping.
    assert screened_store.securities_meta(["ACTIVE"])["ACTIVE"]["successor_symbol"] is None
