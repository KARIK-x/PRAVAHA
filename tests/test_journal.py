"""Journal CRUD and statistics (throwaway SQLite database)."""

from __future__ import annotations

import pytest

from megatool.db import init_app_db
from megatool.journal import (
    JournalError,
    create_entry,
    delete_entry,
    get_entry,
    grade_entry,
    journal_stats,
    list_entries,
    update_entry,
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "state.sqlite"
    init_app_db(path)
    return path


BASE = {
    "symbol": "NABIL",
    "strategy": "breakout",
    "thesis": "Base broken on volume",
    "entry_price": 500.0,
    "planned_target": 550.0,
    "planned_invalidation": 480.0,
    "confidence": "medium",
    "opened_at": "2026-01-05T10:00:00",
}


# ------------------------------------------------------------------ validation
def test_create_and_read_back(db):
    eid = create_entry(BASE, db)
    e = get_entry(eid, db)
    assert e["symbol"] == "NABIL"
    assert e["entry_price"] == 500.0
    assert e["confidence"] == "medium"
    assert e["created_at"]


def test_symbol_is_upper_cased(db):
    eid = create_entry({**BASE, "symbol": "  nabil "}, db)
    assert get_entry(eid, db)["symbol"] == "NABIL"


def test_entry_needs_a_thesis_or_a_price(db):
    with pytest.raises(JournalError, match="at least a thesis or an entry price"):
        create_entry({"symbol": "NABIL"}, db)


def test_closed_entry_needs_exit_price(db):
    with pytest.raises(JournalError, match="needs an exit_price"):
        create_entry({**BASE, "closed_at": "2026-01-10T10:00:00"}, db)


def test_closed_cannot_precede_opened(db):
    with pytest.raises(JournalError, match="cannot be before"):
        create_entry({**BASE, "exit_price": 540.0, "closed_at": "2026-01-01T10:00:00"}, db)


def test_bad_confidence_rejected(db):
    with pytest.raises(JournalError, match="confidence must be one of"):
        create_entry({**BASE, "confidence": "yolo"}, db)


@pytest.mark.parametrize("value", [2, -1, "maybe"])
def test_bad_followed_plan_rejected(db, value):
    with pytest.raises(JournalError, match="followed_plan"):
        create_entry({**BASE, "followed_plan": value}, db)


def test_bad_timestamp_rejected(db):
    with pytest.raises(JournalError, match="not an ISO timestamp"):
        create_entry({**BASE, "opened_at": "sometime in January"}, db)


def test_negative_price_rejected(db):
    with pytest.raises(JournalError, match="must be > 0"):
        create_entry({**BASE, "entry_price": -1}, db)


def test_non_integer_quantity_rejected(db):
    with pytest.raises(JournalError, match="whole number"):
        create_entry({**BASE, "quantity": 2.5}, db)


# ----------------------------------------------------------------------- CRUD
def test_update_entry(db):
    eid = create_entry(BASE, db)
    assert update_entry(eid, {"exit_price": 540.0, "followed_plan": 1}, db) is True
    e = get_entry(eid, db)
    assert e["exit_price"] == 540.0
    assert e["followed_plan"] == 1
    assert update_entry(99999, {"thesis": "x"}, db) is False


def test_delete_entry(db):
    eid = create_entry(BASE, db)
    assert delete_entry(eid, db) is True
    assert delete_entry(eid, db) is False


def test_get_missing_entry_raises(db):
    with pytest.raises(JournalError, match="no journal entry"):
        get_entry(4242, db)


def test_list_filters(db):
    create_entry(BASE, db)
    create_entry({**BASE, "symbol": "NICA", "strategy": "meanrev"}, db)
    assert len(list_entries(db_path=db)) == 2
    assert len(list_entries(symbol="nabil", db_path=db)) == 1
    assert len(list_entries(strategy="meanrev", db_path=db)) == 1
    with pytest.raises(JournalError, match="status"):
        list_entries(status="maybe", db_path=db)


def test_open_and_closed_status_filters(db):
    create_entry(BASE, db)
    create_entry(
        {**BASE, "symbol": "NICA", "exit_price": 560.0, "closed_at": "2026-01-20T10:00:00"},
        db,
    )
    assert len(list_entries(status="open", db_path=db)) == 1
    assert len(list_entries(status="closed", db_path=db)) == 1


# ---------------------------------------------------------------------- stats
def _closed(db, symbol, entry, target, stop, exit_price, strategy="breakout", followed=None):
    # ``db`` is a required first argument on purpose: an earlier version of
    # this helper omitted it, so these rows went into the owner's REAL app
    # database instead of the throwaway one.
    return create_entry(
        {
            **BASE,
            "symbol": symbol,
            "strategy": strategy,
            "entry_price": entry,
            "planned_target": target,
            "planned_invalidation": stop,
            "exit_price": exit_price,
            "followed_plan": followed,
            "opened_at": "2026-01-05T10:00:00",
            "closed_at": "2026-01-20T10:00:00",
        },
        db,
    )


def test_empty_journal_reports_no_statistics(db):
    s = journal_stats(db)
    assert s["entries"] == 0
    assert s["win_rate_pct"] is None
    assert s["avg_r"] is None
    assert s["plan_adherence_pct"] is None
    assert any("No closed trades" in w for w in s["warnings"])


def test_win_rate_and_r_multiples(db):
    _closed(db, "A", 100, 120, 90, 120, followed=1)  # +2R win
    _closed(db, "B", 100, 120, 90, 90, followed=1)  # -1R loss
    _closed(db, "C", 100, 120, 90, 110, followed=0)  # +1R win, plan ignored
    s = journal_stats(db)
    assert s["closed"] == 3
    assert s["wins"] == 2
    assert s["losses"] == 1
    assert s["win_rate_pct"] == pytest.approx(66.67)
    assert s["avg_r"] == pytest.approx((2 - 1 + 1) / 3, abs=1e-4)
    assert s["plan_adherence_pct"] == pytest.approx(66.67)
    assert s["adherence_sample"] == 3


def test_breakeven_trades_are_counted_separately(db):
    _closed(db, "A", 100, 120, 90, 100)
    _closed(db, "B", 100, 120, 90, 120)
    s = journal_stats(db)
    assert s["closed"] == 2
    assert s["wins"] == 1
    assert s["breakeven"] == 1


def test_incomplete_plan_is_excluded_from_r_but_counted_in_win_rate(db):
    create_entry(
        {
            **BASE,
            "symbol": "X",
            "exit_price": 540.0,
            "planned_target": None,
            "closed_at": "2026-01-20T10:00:00",
        },
        db,
    )
    _closed(db, "Y", 100, 120, 90, 130)
    s = journal_stats(db)
    assert s["closed"] == 2
    assert s["graded_r"] == 1
    assert s["avg_r"] == pytest.approx(3.0)
    assert any("no complete plan" in w for w in s["warnings"])


def test_small_sample_is_flagged(db):
    _closed(db, "A", 100, 120, 90, 130)
    s = journal_stats(db)
    assert any("not statistically meaningful" in w for w in s["warnings"])


def test_by_strategy_breakdown(db):
    _closed(db, "A", 100, 120, 90, 130, strategy="breakout")
    _closed(db, "B", 100, 120, 90, 85, strategy="breakout")
    _closed(db, "C", 100, 110, 95, 105, strategy="meanrev")
    s = journal_stats(db)
    by = {b["strategy"]: b for b in s["by_strategy"]}
    assert by["breakout"]["closed"] == 2
    assert by["breakout"]["wins"] == 1
    assert by["breakout"]["win_rate_pct"] == pytest.approx(50.0)
    assert by["meanrev"]["avg_r"] == pytest.approx((105 - 100) / 5)


def test_stats_disclaim_prediction(db):
    s = journal_stats(db)
    assert "nothing here predicts future results" in s["note"]
    assert "measurements of recorded trades only" in s["note"]


def test_grade_entry(db):
    # Exit exactly at the planned target: +2R.
    eid = _closed(db, "A", 100, 120, 90, 120)
    g = grade_entry(eid, db)
    assert g["result"] == "target"
    assert g["r_multiple"] == pytest.approx(2.0)
    assert g["planned_r"] == pytest.approx(2.0)


def test_grade_entry_returns_none_without_a_plan(db):
    eid = create_entry(
        {
            **BASE,
            "symbol": "X",
            "exit_price": 540.0,
            "planned_target": None,
            "planned_invalidation": None,
            "closed_at": "2026-01-20T10:00:00",
        },
        db,
    )
    assert grade_entry(eid, db) is None


def test_grade_entry_returns_none_while_open(db):
    eid = create_entry(BASE, db)
    assert grade_entry(eid, db) is None


# ------------------------------------------------------- remembered thinking
def test_notes_is_accepted_as_an_alias_for_outcome_notes(db):
    """A field that is accepted and then discarded is worse than a 400."""
    eid = create_entry({**BASE, "notes": "waited for the base to break"}, db)
    assert get_entry(eid, db)["outcome_notes"] == "waited for the base to break"


def test_outcome_notes_still_wins_over_the_alias(db):
    eid = create_entry({**BASE, "notes": "short form", "outcome_notes": "the long form"}, db)
    assert get_entry(eid, db)["outcome_notes"] == "the long form"


def test_notes_survives_an_update(db):
    eid = create_entry(BASE, db)
    assert update_entry(eid, {"notes": "added later"}, db) is True
    assert get_entry(eid, db)["outcome_notes"] == "added later"
