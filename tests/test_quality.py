"""Unit tests for ``megatool.quality`` — the per-bar validation sweep.

These pin the B-21 / T-31 fix: a zero in ``open``/``low``/``close``
was previously invisible (only ``high == 0`` was checked), so it
reached every calculation and could drag an all-time low, ATR, %B or
a support level to zero. The row is now flagged ``non_positive_price``
and classified ``suspect`` — surfaced for a human look, but *retained*
in every calculation. Whether zero prices should be excluded entirely
is the owner's data-policy decision (register R1, same as B-20) and is
deliberately **not** made here.
"""

from __future__ import annotations

import pandas as pd
import pytest

from megatool.market_store import MarketStore
from megatool.models import ValidationStatus
from megatool.quality import (
    F_NON_POSITIVE,
    FLAG_HELP,
    FLAG_SEVERITY,
    validate_bar,
    validate_series,
)

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


# ------------------------------------------------------------- the fix itself
@pytest.mark.parametrize(
    ("field", "values"),
    [
        # The fields that were previously invisible: only ``high == 0``
        # was checked before B-21, so a zero open/low/close slipped
        # through. (A zero ``high`` with a positive ``low`` would be an
        # *inverted* bar, which hard-fails earlier — covered separately.)
        ("open", (0.0, 846.6, 800.0, 814.0)),
        ("low", (772.3, 846.6, 0.0, 814.0)),
        ("close", (772.3, 846.6, 800.0, 0.0)),
    ],
)
def test_any_zero_price_field_is_flagged(field, values):
    """A zero in any OHLC field is impossible for a traded price."""
    open_, high, low, close = values
    flags, status = validate_bar(open_, high, low, close, volume=1000)
    assert F_NON_POSITIVE in flags
    assert status is ValidationStatus.SUSPECT


@pytest.mark.parametrize(
    ("open", "high", "low", "close"),
    [
        (772.3, 846.6, 0.0, 814.0),  # KRBL 2024-12-01, verbatim
        (277.9, 290.5, 0.0, 287.0),  # GRDBL 2023-06-25, verbatim
        (0.0, 506.0, 506.0, 506.0),  # NMFBS 2017-02-08, verbatim
        (0.0, 141.0, 136.0, 141.0),  # FMDBL 2012-06-10, verbatim
    ],
)
def test_the_ten_real_b21_rows_are_now_visible(open, high, low, close):
    """The exact rows B-21 found readable-but-unflagged are now flagged."""
    flags, status = validate_bar(open, high, low, close, volume=1000)
    assert F_NON_POSITIVE in flags
    assert status is ValidationStatus.SUSPECT  # flagged, not excluded


def test_zero_high_is_still_hard_invalid_and_also_flagged():
    """``high == 0`` was already ``zero_price``/hard; it keeps that
    severity (the hard flag wins) and now also carries the general flag."""
    flags, status = validate_bar(100.0, 0.0, 0.0, 100.0, volume=1000)
    assert status is ValidationStatus.INVALID
    assert "zero_price" in flags
    assert F_NON_POSITIVE in flags


def test_negative_price_still_hard_fails_before_the_zero_check():
    """A negative is physically impossible and must remain ``invalid``."""
    flags, status = validate_bar(-1.0, 5.0, 1.0, 2.0, volume=1000)
    assert status is ValidationStatus.INVALID
    assert "negative_value" in flags
    assert F_NON_POSITIVE not in flags  # the earlier return owns it


# --------------------------------------------------- guards against overreach
def test_normal_bar_is_valid_and_unflagged():
    flags, status = validate_bar(100.0, 105.0, 95.0, 100.0, volume=1000)
    assert status is ValidationStatus.VALID
    assert F_NON_POSITIVE not in flags


def test_zero_volume_is_legal_and_not_flagged():
    """A suspended/no-trade day has zero volume; that is not a price defect."""
    flags, status = validate_bar(100.0, 105.0, 95.0, 100.0, volume=0)
    assert status is ValidationStatus.VALID
    assert F_NON_POSITIVE not in flags


@pytest.mark.parametrize("price", [0.01, 1.0, 0.5])
def test_tiny_positive_prices_are_not_flagged(price):
    """A small-but-positive price is a real price (e.g. a post-split scrip)."""
    flags, status = validate_bar(price, price * 1.05, price * 0.95, price, 1000)
    assert status is ValidationStatus.VALID
    assert F_NON_POSITIVE not in flags


def test_non_positive_flag_is_review_not_hard():
    """The severity is what keeps the row in every calculation.

    ``hard`` would exclude the row via the read path's ``_NOT_INVALID``
    filter — that is the owner's R1 decision, not this fix's.
    """
    assert FLAG_SEVERITY[F_NON_POSITIVE] == "review"


def test_non_positive_flag_has_help_text():
    assert FLAG_HELP[F_NON_POSITIVE]


# ------------------------------------------------------- end-to-end retention
def test_validate_series_flags_and_retains_a_zero_low_row():
    """The sweep labels the row ``suspect`` and never drops it."""
    df = pd.DataFrame(
        {
            "symbol": ["ZP"] * 3,
            "trading_date": pd.bdate_range("2026-01-01", periods=3),
            "open": [100.0, 100.0, 100.0],
            "high": [105.0, 105.0, 105.0],
            "low": [95.0, 0.0, 95.0],  # bar 2 is the B-21 corruption
            "close": [100.0, 100.0, 100.0],
            "volume": [1000, 1000, 1000],
        }
    )
    annotated, report = validate_series(df)
    assert len(annotated) == 3, "validate_series must never drop a row"
    row = annotated.iloc[1]
    assert row["validation_status"] == "suspect"
    assert F_NON_POSITIVE in row["flags"]
    assert report.suspect == 1
    assert report.invalid == 0
    assert report.flag_counts[F_NON_POSITIVE] == 1


def test_a_suspect_zero_price_row_is_retained_by_the_read_path(tmp_path):
    """``suspect`` rows are not filtered — so this fix changes no
    calculation, only the label. (Only ``invalid`` is excluded.)"""
    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": ["ZP"] * 3,
                "trading_date": list(pd.bdate_range("2026-01-01", periods=3)),
                "open": [100.0, 100.0, 100.0],
                "high": [105.0, 105.0, 105.0],
                "low": [95.0, 0.0, 95.0],
                "close": [100.0, 100.0, 100.0],
                "volume": [1000, 1000, 1000],
                "source": ["TEST"] * 3,
                "retrieved_at": [RETRIEVED] * 3,
                "validation_status": ["valid", "suspect", "valid"],
                "flags": [None, F_NON_POSITIVE, None],
            }
        )
    )
    bars = store.get_bars("ZP")
    assert len(bars) == 3, "a suspect row must stay readable"
    assert float(bars["low"].min()) == 0.0  # retained, and visible as suspect
    store.close()
