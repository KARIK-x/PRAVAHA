"""Index-series loader tests: strict validation, no partial writes, no synthesis.

Fixtures are SYNTHETIC. Nothing here asserts a real NEPSE index value; the
loader's job is to refuse anything that would corrupt a genuine series the
owner later supplies (bad dates, non-finite/non-positive closes, duplicates).
"""

from __future__ import annotations

import pytest

from megatool.index_series import (
    REQUIRED_COLUMNS,
    IndexSeriesError,
    import_index_series,
    read_index_csv,
)
from megatool.market_store import MarketStore

GOOD = """date,close
2026-01-05,2100.5
2026-01-06,2110.25
2026-01-07,2099.0
"""


def _store(tmp_path) -> MarketStore:
    return MarketStore(tmp_path / "index.duckdb")


# ------------------------------------------------------------------ parsing


def test_required_columns_are_declared():
    assert REQUIRED_COLUMNS == ("date", "close")


def test_read_parses_valid_points():
    points, errors = read_index_csv(GOOD)
    assert errors == []
    assert len(points) == 3
    assert points[0]["close"] == 2100.5
    assert points[0]["date"].isoformat() == "2026-01-05"


def test_read_refuses_missing_close_column():
    with pytest.raises(IndexSeriesError) as exc:
        read_index_csv("date\n2026-01-05\n")
    assert "close" in str(exc.value)


def test_read_refuses_empty_file():
    with pytest.raises(IndexSeriesError):
        read_index_csv("")


def test_unparseable_date_is_an_error_not_coerced():
    points, errors = read_index_csv("date,close\nnot-a-date,2100\n")
    assert points == []
    assert errors and "unparseable date" in errors[0]["reason"]


def test_non_numeric_close_is_an_error():
    _, errors = read_index_csv("date,close\n2026-01-05,2100 USD\n")
    assert errors and "non-numeric close" in errors[0]["reason"]


def test_non_finite_close_is_an_error():
    for bad in ("nan", "inf", "-inf"):
        _, errors = read_index_csv(f"date,close\n2026-01-05,{bad}\n")
        assert errors and "non-finite close" in errors[0]["reason"], bad


@pytest.mark.parametrize("bad", ["0", "-5", "-0.1"])
def test_non_positive_close_is_an_error(bad):
    _, errors = read_index_csv(f"date,close\n2026-01-05,{bad}\n")
    assert errors and "must be > 0" in errors[0]["reason"]


def test_duplicate_date_is_rejected_not_deduped():
    text = "date,close\n2026-01-05,2100\n2026-01-05,2101\n"
    points, errors = read_index_csv(text)
    assert len(points) == 1
    assert errors and "duplicate date" in errors[0]["reason"]


# ------------------------------------------------------------------ import


def test_import_writes_points_readable_in_date_order(tmp_path):
    store = _store(tmp_path)
    report = import_index_series(GOOD, index_name="NEPSE", source="owner file", store=store)
    assert report["points_written"] == 3
    assert report["first_date"] == "2026-01-05"
    assert report["last_date"] == "2026-01-07"
    df = store.index_closes("NEPSE")
    assert list(df["close"]) == [2100.5, 2110.25, 2099.0]
    assert store.index_names() == ["NEPSE"]


def test_import_orders_points_chronologically_regardless_of_file_order(tmp_path):
    store = _store(tmp_path)
    shuffled = "date,close\n2026-01-07,2099\n2026-01-05,2100.5\n2026-01-06,2110.25\n"
    report = import_index_series(shuffled, index_name="NEPSE", source="s", store=store)
    assert report["first_date"] == "2026-01-05"
    assert report["last_date"] == "2026-01-07"
    df = store.index_closes("NEPSE")
    assert list(df["close"]) == [2100.5, 2110.25, 2099.0]


def test_import_with_any_bad_point_writes_nothing(tmp_path):
    store = _store(tmp_path)
    bad = "date,close\n2026-01-05,2100\nnot-a-date,2101\n"
    with pytest.raises(IndexSeriesError) as exc:
        import_index_series(bad, index_name="NEPSE", source="s", store=store)
    assert "nothing was written" in str(exc.value)
    assert store.index_closes("NEPSE").empty


def test_import_requires_index_name_and_source(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(IndexSeriesError):
        import_index_series(GOOD, index_name="  ", source="s", store=store)
    with pytest.raises(IndexSeriesError):
        import_index_series(GOOD, index_name="NEPSE", source="  ", store=store)


def test_import_is_idempotent_for_same_dates(tmp_path):
    store = _store(tmp_path)
    import_index_series(GOOD, index_name="NEPSE", source="s", store=store)
    second = import_index_series(GOOD, index_name="NEPSE", source="s2", store=store)
    assert second["points_written"] == 3
    df = store.index_closes("NEPSE")
    assert len(df) == 3  # overwritten, not duplicated
    assert (
        store.execute(
            "SELECT source FROM index_series WHERE index_name='NEPSE' LIMIT 1"
        ).fetchone()[0]
        == "s2"
    )
