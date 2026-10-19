"""Corporate-event calendar tests (NF-004 / NF-020 — the feasible part).

Synthetic notices only. The point of the suite is the refusal contract: a notice
with no date is refused rather than guessed, an unknown event type is refused, a
source is mandatory, and the registry projection carries real attested dates.
"""

from __future__ import annotations

import pytest

from megatool.corporate_events import (
    EVENT_TYPES,
    CorporateEvent,
    CorporateEventError,
    calendar,
    coverage,
    import_events,
    list_events,
    parse_events_csv,
    registry_events,
    summary,
)
from megatool.db import get_conn, init_app_db


@pytest.fixture(autouse=True)
def _schema():
    init_app_db()


def _row(**kw):
    base = {"symbol": "SYN1", "event_type": "dividend", "effective_date": "2026-05-01",
            "value": 12.0, "unit": "NPR", "source": "supplied-doc", "grade": "reported"}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def test_a_notice_without_a_date_is_refused_not_guessed():
    with pytest.raises(CorporateEventError) as exc:
        CorporateEvent(symbol="SYN1", event_type="dividend", source="doc").validate()
    assert "effective_date" in str(exc.value)


def test_unknown_event_type_is_refused():
    with pytest.raises(CorporateEventError):
        CorporateEvent(symbol="SYN1", event_type="rumour", effective_date="2026-01-01",
                       source="doc").validate()


def test_a_source_is_mandatory():
    with pytest.raises(CorporateEventError):
        CorporateEvent(symbol="SYN1", event_type="dividend", effective_date="2026-01-01").validate()


def test_bad_ratio_and_bad_date_are_refused():
    with pytest.raises(CorporateEventError):
        CorporateEvent(symbol="SYN1", event_type="bonus", effective_date="2026-01-01",
                       source="doc", ratio="one to two").validate()
    with pytest.raises(CorporateEventError):
        CorporateEvent(symbol="SYN1", event_type="bonus", effective_date="01/01/2026",
                       source="doc").validate()


def test_a_merger_needs_no_effective_date_because_registry_entries_may_lack_one():
    ev = CorporateEvent(symbol="SYN1", event_type="merger", source="registry", successor="SYN2")
    ev.validate()  # does not raise
    assert ev.effective_date == ""


def test_event_vocabulary_covers_the_notice_types():
    assert {"dividend", "bonus", "rights", "ipo", "allotment", "agm"} <= set(EVENT_TYPES)


# --------------------------------------------------------------------------- #
# Import and query
# --------------------------------------------------------------------------- #

def test_import_then_list_and_reimport_is_idempotent():
    with get_conn() as conn:
        first = import_events([_row()], conn)
        assert first == {"inserted": 1, "updated": 0, "rejected": 0, "total": 1}
        second = import_events([_row(value=15.0)], conn)
        assert second["updated"] == 1
        rows = list_events(conn, include_registry=False)
    assert len(rows) == 1
    assert rows[0]["value"] == 15.0


def test_rejected_rows_are_counted_not_silently_dropped():
    with get_conn() as conn:
        out = import_events([_row(), {"symbol": "SYN1", "event_type": "dividend"}], conn)
        assert out["inserted"] == 1 and out["rejected"] == 1
        assert len(list_events(conn, include_registry=False)) == 1


def test_filters_by_symbol_type_and_window():
    with get_conn() as conn:
        import_events([
            _row(effective_date="2026-05-01"),
            _row(event_type="bonus", effective_date="2026-06-01", ratio="1:2"),
            _row(symbol="SYN2", effective_date="2027-01-01"),
        ], conn)
        assert len(list_events(conn, symbol="SYN1", include_registry=False)) == 2
        assert len(list_events(conn, event_type="bonus", include_registry=False)) == 1
        assert len(list_events(conn, since="2027-01-01", include_registry=False)) == 1
        assert len(list_events(conn, until="2026-05-31", include_registry=False)) == 1


def test_the_registry_is_projected_with_real_dates_and_attested_grade():
    events = registry_events()
    assert events, "the attested registry must not be empty"
    for ev in events:
        assert ev["grade"] == "attested"
        assert ev["source"] == "corporate_actions:registry"
        assert ev["event_type"] in ("merger", "retirement")
    dated = [e for e in events if e["effective_date"]]
    assert dated, "at least some registry actions carry an observed date"


def test_list_includes_registry_by_default():
    with get_conn() as conn:
        rows = list_events(conn)
    assert any(r["source"] == "corporate_actions:registry" for r in rows)


def test_calendar_explains_that_empty_means_not_imported():
    with get_conn() as conn:
        cal = calendar(conn)
    assert "not that no such event occurred" in cal["note"]


# --------------------------------------------------------------------------- #
# Coverage honesty
# --------------------------------------------------------------------------- #

def test_coverage_names_the_missing_notice_types():
    with get_conn() as conn:
        cov = coverage(conn)
    assert cov["status"] == "no_imported_notices"
    assert {"dividend", "bonus", "rights", "ipo", "allotment", "agm"} <= set(cov["missing_notice_types"])
    assert "NOT derivable from" in cov["limitation"]
    assert cov["registry_total"] > 0


def test_summary_separates_stored_from_projected():
    with get_conn() as conn:
        import_events([_row()], conn)
        s = summary(conn)
    assert s["stored"].get("dividend") == 1
    assert s["stored_total"] == 1
    assert s["registry_total"] >= 1
    assert s["registry_projected"]


# --------------------------------------------------------------------------- #
# CSV parsing
# --------------------------------------------------------------------------- #

def test_csv_parse_maps_headers_and_applies_default_source():
    text = ("symbol,event_type,effective_date,value,unit\n"
            "NABIL,dividend,2026-05-01,12.5,NPR\n")
    rows = parse_events_csv(text, source="my-doc.csv")
    assert rows[0]["symbol"] == "NABIL"
    assert rows[0]["source"] == "my-doc.csv"


def test_csv_parse_accepts_type_and_date_aliases():
    rows = parse_events_csv("symbol,type,date\nNABIL,bonus,2026-05-01\n")
    with get_conn() as conn:
        out = import_events(rows, conn)
    assert out["inserted"] == 1


def test_empty_document_is_refused():
    with pytest.raises(CorporateEventError):
        parse_events_csv("   ")
