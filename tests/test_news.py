"""News / Events local-processing tests (throwaway SQLite, fixture files).

These verify the processing layer the spec's Section 22 requires once a
source exists: validation, timestamp normalisation, dedup, symbol
association, safe failure, and summaries that never overstate what they are.

ALL RECORDS HERE ARE SYNTHETIC-TEST-FIXTURES. No headline in this file was
ever published anywhere, and nothing here asserts anything about real
companies, real events or real markets.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from megatool.db import SCHEMA_VERSION, get_conn, init_app_db
from megatool.news import (
    NewsError,
    import_news,
    news_summary,
    parse_news,
)

NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)

CSV_OK = """title,published_at,summary,url,source,symbols
Alpha AGM concluded,2026-01-05,Board approved dividend proposal,https://ex.test/a1,ShareSansar,NABIL
Beta gets bank licence,2026-01-07T09:30:00,Nepal Rastra Bank grants licence,https://ex.test/b1,Manager note,"NICA, NABIL"
"""


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "state.sqlite"
    init_app_db(path)
    return path


# ------------------------------------------------------------------ parsing
def test_valid_csv_parses_with_normalised_timestamps_and_symbols():
    p = parse_news(CSV_OK, now=NOW)
    assert p.total_rows == 2 and len(p.rows) == 2
    assert p.skipped == []
    first, second = p.rows
    # date-only stays a date; a datetime keeps its time
    assert first.published_at == "2026-01-05"
    assert second.published_at == "2026-01-07T09:30:00"
    assert first.publisher == "ShareSansar"
    assert second.symbols == ["NICA", "NABIL"]
    assert first.uid and first.uid == parse_news(CSV_OK, now=NOW).rows[0].uid


def test_published_column_aliases_are_recognised():
    csv_text = """Headline,Published,Link,Scrip
Some result,2026-01-04,https://ex.test/x,upper
"""
    p = parse_news(csv_text, now=NOW)
    assert p.rows[0].title == "Some result"
    assert p.rows[0].published_at == "2026-01-04"
    assert p.rows[0].url == "https://ex.test/x"
    assert p.rows[0].symbols == ["UPPER"]


def test_missing_required_columns_are_reported_with_the_header_seen():
    with pytest.raises(NewsError) as exc:
        parse_news("foo\nbar\n", now=NOW)
    message = str(exc.value)
    assert "missing required column(s): title, published_at" in message
    assert "Columns found: foo" in message


def test_empty_file_and_bad_format_are_rejected():
    with pytest.raises(NewsError, match="empty"):
        parse_news("   ", now=NOW)
    with pytest.raises(NewsError, match="unknown format"):
        parse_news(CSV_OK, fmt="xml", now=NOW)


def test_bad_or_empty_timestamps_are_skipped_with_reasons():
    csv_text = """title,published_at
No date here,
Wrong shape,2026/01/05
Fine,2026-01-05
"""
    p = parse_news(csv_text, now=NOW)
    assert [r.title for r in p.rows] == ["Fine"]
    reasons = " ".join(s["reason"] for s in p.skipped)
    assert "empty timestamp" in reasons
    assert "not an ISO date/datetime" in reasons


def test_future_and_prehistory_timestamps_are_rejected():
    csv_text = """title,published_at
From the future,2027-03-01
Yesterday,2026-01-09
Medieval,1899-12-31
"""
    p = parse_news(csv_text, now=NOW)
    assert [r.title for r in p.rows] == ["Yesterday"]
    reasons = " ".join(s["reason"] for s in p.skipped)
    assert "in the future" in reasons
    assert "before 1900-01-01" in reasons


def test_missing_title_is_skipped_not_stored_blank():
    csv_text = """title,published_at
,2026-01-05
"""
    p = parse_news(csv_text, now=NOW)
    assert p.rows == []
    assert p.skipped[0]["reason"] == "missing title"


def test_duplicate_items_in_one_file_are_counted_once():
    p = parse_news(CSV_OK + CSV_OK.splitlines()[1] + "\n", now=NOW)
    assert len(p.rows) == 2
    assert p.duplicates == 1
    assert any("duplicate item" in s["reason"] for s in p.skipped)


def test_overlong_titles_are_truncated_with_a_warning():
    csv_text = f"title,published_at\n{'x' * 1500},2026-01-05\n"
    p = parse_news(csv_text, now=NOW)
    assert len(p.rows[0].title) == 1000
    assert any("truncated" in w for w in p.warnings)


def test_unrecognised_columns_are_reported_not_silently_kept():
    csv_text = "title,published_at,mood\nHello,2026-01-05,joyful\n"
    p = parse_news(csv_text, now=NOW)
    assert any("mood" in w and "not recognised" in w for w in p.warnings)


def test_nonsense_symbols_are_ignored_with_a_warning():
    csv_text = 'title,published_at,symbols\nHello,2026-01-05,"NABIL, ###, NICA"\n'
    p = parse_news(csv_text, now=NOW)
    assert p.rows[0].symbols == ["NABIL", "NICA"]
    assert any("'###' is not a scrip code" in w for w in p.warnings)


# ------------------------------------------------------------------- JSON
def test_json_list_and_items_wrapper_both_work():
    one = parse_news(
        '[{"title": "T1", "published_at": "2026-01-05", "symbols": "NABIL"}]', fmt="json", now=NOW
    )
    two = parse_news(
        '{"items": [{"title": "T1", "published_at": "2026-01-05", "symbols": "NABIL"}]}',
        fmt="json",
        now=NOW,
    )
    assert one.rows == two.rows
    assert one.rows[0].symbols == ["NABIL"]


def test_malformed_json_and_wrong_shapes_are_rejected():
    with pytest.raises(NewsError, match="not valid JSON"):
        parse_news("{nope", fmt="json", now=NOW)
    with pytest.raises(NewsError, match="items"):
        parse_news('{"other": []}', fmt="json", now=NOW)
    p = parse_news('[{"title": "ok", "published_at": "2026-01-05"}, 42]', fmt="json", now=NOW)
    assert len(p.rows) == 1
    assert p.skipped[0]["reason"] == "not an object"


# ------------------------------------------------------------- import + store
def test_import_is_idempotent_by_item_identity(db):
    first = import_news(CSV_OK, source_file="week.csv", now=NOW, db_path=db)
    assert first["added"] == 2 and first["duplicates"] == 0
    second = import_news(CSV_OK, source_file="week.csv", now=NOW, db_path=db)
    assert second["added"] == 0 and second["duplicates"] == 2

    s = news_summary(now=NOW, db_path=db)
    assert s["totals"]["items"] == 2  # re-importing never doubles the archive


def test_import_rejects_an_empty_file_before_touching_the_database(db):
    with pytest.raises(NewsError):
        import_news("", db_path=db)
    assert news_summary(now=NOW, db_path=db)["totals"]["items"] == 0


# ----------------------------------------------------------------- summaries
def test_summary_counts_filters_and_orders_imported_records(db):
    import_news(CSV_OK, now=NOW, db_path=db)
    s = news_summary(now=NOW, db_path=db)
    assert s["totals"] == {
        "items": 2,
        "first_published": "2026-01-05",
        "last_published": "2026-01-07T09:30:00",
    }
    assert [r["title"] for r in s["recent"]] == [
        "Beta gets bank licence",
        "Alpha AGM concluded",
    ]
    by_symbol = {r["symbol"]: r["items"] for r in s["by_symbol"]}
    assert by_symbol == {"NABIL": 2, "NICA": 1}
    assert s["by_date"][0]["day"] == "2026-01-07"

    only_nica = news_summary(symbol="nica", now=NOW, db_path=db)
    assert only_nica["totals"]["items"] == 1
    assert only_nica["filter"]["symbol"] == "NICA"

    since = news_summary(since="2026-01-07", now=NOW, db_path=db)
    assert since["totals"]["items"] == 1


def test_summary_of_an_empty_archive_says_so_and_never_invents_headlines(db):
    s = news_summary(now=NOW, db_path=db)
    assert s["totals"]["items"] == 0
    assert s["recent"] == [] and s["by_symbol"] == []
    assert "no live source is connected" in s["note"]
    assert "nothing is fetched" in s["note"]


def test_stale_archive_is_flagged_as_an_archive_not_a_feed(db):
    import_news(CSV_OK, now=NOW, db_path=db)
    later = datetime(2026, 3, 1, tzinfo=UTC)  # ~7 weeks after the newest item
    s = news_summary(now=later, db_path=db)
    assert any("import archive, not a live feed" in w for w in s["warnings"])


def test_provenance_is_recorded_per_item(db):
    import_news(CSV_OK, source_file="owner-export.csv", now=NOW, db_path=db)
    from megatool.db import get_conn

    with get_conn(db) as conn:
        rows = conn.execute("SELECT source_file FROM news_items").fetchall()
    assert {r["source_file"] for r in rows} == {"owner-export.csv"}


def test_an_existing_v5_database_gains_the_news_tables_on_upgrade(tmp_path):
    """A database created before schema v6 must gain the news tables.

    The v6 news tables are brand new (no ALTER columns needed), so the
    migration is the ``CREATE TABLE IF NOT EXISTS`` in the schema script.
    Simulate a pre-news database by dropping them and stamping version 5,
    then re-init: the tables must come back and the version must reach 6.
    """
    path = tmp_path / "state.sqlite"
    init_app_db(path)  # v6 baseline
    with get_conn(path) as conn:  # roll it back to a v5-era shape
        conn.execute("DROP TABLE IF EXISTS news_item_symbols")
        conn.execute("DROP TABLE IF EXISTS news_items")
        conn.execute("UPDATE schema_meta SET value='5' WHERE key='schema_version'")
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "news_items" not in tables  # genuinely pre-news now

    assert init_app_db(path) == SCHEMA_VERSION  # upgraded in place
    with get_conn(path) as conn:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()["value"]
    assert "news_items" in tables and "news_item_symbols" in tables
    assert int(version) == SCHEMA_VERSION
    # and the upgraded archive is usable, not an empty shell
    assert news_summary(now=NOW, db_path=path)["totals"]["items"] == 0


# ------------------------------------------- deterministic classification (F4)
from megatool.news import (  # noqa: E402  (grouped with the F4 section it tests)
    NEWS_CATEGORIES,
    categorize_headline,
    relevance_for,
    story_key,
)


def test_categorize_uses_a_closed_vocabulary_with_keyword_evidence():
    cases = {
        "NABIL declares dividend for the year": "corporate_action",
        "Quarterly profit jumps on higher revenue": "financial_result",
        "SEBON issues circular on margin trading": "regulatory",
        "Alpha AGM concluded": "meeting",
        "IPO allotment completed": "listing",
        "Nepse index closes higher, turnover rises": "market_general",
        "Something entirely unrelated happened": "other",
    }
    for title, expected in cases.items():
        out = categorize_headline(title)
        assert out["category"] == expected, title
        assert out["kind"] == "deterministic_classification"
        assert out["basis"]  # evidence is always stated
    assert categorize_headline("anything")["category"] in NEWS_CATEGORIES


def test_relevance_tells_named_apart_from_merely_mapped():
    named = relevance_for("NABIL declares dividend", "NABIL")
    assert named["direct_mention"] is True and "word in the headline" in named["basis"]
    mapped = relevance_for("Beta gets bank licence", "NABIL")
    assert mapped["direct_mention"] is False and "import mapping" in mapped["basis"]
    # Word boundary: NABIL must not match inside RENABIL.
    inside = relevance_for("RENABIL moves", "NABIL")
    assert inside["direct_mention"] is False
    assert relevance_for("any title", None)["basis"] == "no symbol in scope"


def test_story_key_groups_punctuation_and_case_rewrites_only():
    a = story_key("NABIL declares dividend for the fiscal year!")
    b = story_key("nabil declares dividend for the fiscal year")
    c = story_key("NABIL board approves expansion plan")
    assert a == b, "case/punct rewrites of one headline must group"
    assert a != c, "different stories must not merge"


def test_summary_carries_classification_and_repeated_coverage(db):
    same_story = CSV_OK + (
        "NABIL declares dividend for the fiscal year,2026-01-08,"
        "first pass,https://ex.test/n1,Publisher A,NABIL\n"
        "NABIL declares dividend for the fiscal year!,2026-01-09,"
        "rewrite,https://ex.test/n2,Publisher B,NABIL"
    )
    import_news(same_story, now=NOW, db_path=db)
    s = news_summary(now=NOW, db_path=db)
    assert s["totals"]["items"] == 4
    # Every recent item carries classification with fact/derived separation.
    for item in s["recent"]:
        assert item["event"]["category"] in NEWS_CATEGORIES
        assert item["relevance"]["kind"] == "deterministic_match"
        assert "not sentiment" in item["fact_vs_derived"]
        assert "sentiment" not in item and "impact" not in item
    # The two rewrites group as repeated coverage, reported not merged.
    groups = s["repeated_coverage"]["groups"]
    assert any(g["items"] == 2 for g in groups)
    assert s["totals"]["items"] == 4, "grouping never deletes records"
    assert "heuristic" in s["repeated_coverage"]["method"]


def test_summary_states_no_sentiment_or_impact_estimates(db):
    import_news(CSV_OK, now=NOW, db_path=db)
    s = news_summary(now=NOW, db_path=db)
    assert "no sentiment score" in s["note"]
    assert "no price-impact" in s["note"]
    assert "deterministic keyword classifications" in s["note"]
