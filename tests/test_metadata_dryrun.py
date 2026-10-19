"""Focused tests for the T-M2 dry-run security-metadata harness.

Each test covers one requirement of the dry run: schema validation, duplicate
handling, vocabulary rejection, unknown/conflicting metadata, manual-review
flags, the merged-is-not-delisted rule, successor-symbol handling,
determinism, and — most importantly — that running the harness leaves the
store byte-identical.

Nothing here touches a real database: ``conftest`` redirects both database
paths to ``tmp_path`` for every test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from megatool.cli import main
from megatool.market_store import STATUS_ACTIVE, STATUS_MERGED, MarketStore
from megatool.metadata_dryrun import (
    MetadataDryRunError,
    build_dry_run,
    metadata_gaps,
    read_metadata_csv,
    render_markdown,
    result_json,
    write_outputs,
)

HEADER = "symbol,name,instrument_type,sector,status,delisted,successor_symbol,source,requires_manual_review\n"


def _csv(path: Path, body: str) -> Path:
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def _store(path: Path) -> MarketStore:
    s = MarketStore(path)
    s.upsert_securities(
        [
            {
                "symbol": "ABC",
                "name": "Alpha Ltd",
                "sector": "Bank",
                "instrument_type": "ordinary",
                "delisted": False,
                "source": "fixture",
            },
            {"symbol": "XYZ", "name": "Xyz Ltd", "source": "fixture"},
            {
                "symbol": "GONE",
                "name": "Gone Ltd",
                "sector": "Hydropower",
                "delisted": True,
                "source": "fixture",
            },
        ]
    )
    return s


def _record(result: dict, symbol: str) -> dict:
    matches = [r for r in result["records"] if r["symbol"] == symbol]
    assert len(matches) == 1, f"expected exactly one record for {symbol}"
    return matches[0]


# --------------------------------------------------------------- valid input


def test_valid_input_reconciles_cleanly(tmp_path: Path) -> None:
    csv = _csv(
        tmp_path / "reviewed.csv",
        "ABC,,,Hydro Power,listed,,,owner-note,\nNEW1,,ordinary,Life Insurance,listed,,,,,\n",
    )
    store = _store(tmp_path / "db.duckdb")
    before = store.securities_meta()
    result = build_dry_run(csv, store)
    after = store.securities_meta()
    store.close()

    assert result["summary"]["records_examined"] == 2
    assert result["summary"]["rows_rejected"] == 0
    # ABC has a stored sector/status that disagrees with the file -> conflict.
    assert _record(result, "ABC")["action"] == "conflict"
    assert _record(result, "NEW1")["action"] == "addition"
    assert result["summary"]["additions"] == 1
    assert result["summary"]["conflicting"] == 1
    # every proposed value is labelled unverified (source supplied or not)
    assert _record(result, "ABC")["confidence"] == "source-provided-unverified"
    assert _record(result, "NEW1")["confidence"] == "unverified-no-provenance"
    assert before == after  # reading through the harness changes nothing


def test_cli_writes_both_outputs_and_matches_library(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    csv = _csv(tmp_path / "reviewed.csv", "NEW1,,ordinary,Life Insurance,listed,,,,,\n")
    store = _store(tmp_path / "db.duckdb")
    store.close()
    out_dir = tmp_path / "out"

    rc = main(
        [
            "metadata",
            "dry-run",
            "--input",
            str(csv),
            "--db",
            str(tmp_path / "db.duckdb"),
            "--out-dir",
            str(out_dir),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    json_path = out_dir / "reviewed_dryrun.json"
    md_path = out_dir / "reviewed_dryrun.md"
    assert json_path.exists() and md_path.exists()
    assert "Nothing was imported" in captured.out

    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    store = MarketStore(tmp_path / "db.duckdb", read_only=True)
    fresh = build_dry_run(csv, store)
    store.close()
    assert on_disk == fresh  # deterministic across independent runs
    assert "# Security-metadata dry run (no import performed)" in md_path.read_text(
        encoding="utf-8"
    )


# --------------------------------------------------------- schema validation


def test_missing_symbol_column_rejected(tmp_path: Path) -> None:
    p = tmp_path / "bad.csv"
    p.write_text("name,sector\nAlpha,Bank\n", encoding="utf-8")
    with pytest.raises(MetadataDryRunError, match="symbol"):
        read_metadata_csv(p)


def test_no_metadata_columns_rejected(tmp_path: Path) -> None:
    p = tmp_path / "bad.csv"
    p.write_text("symbol,foo\nABC,1\n", encoding="utf-8")
    with pytest.raises(MetadataDryRunError, match="no metadata"):
        read_metadata_csv(p)


def test_empty_and_rowless_files_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(MetadataDryRunError, match="empty"):
        read_metadata_csv(empty)

    header_only = tmp_path / "header.csv"
    header_only.write_text("symbol,sector\n", encoding="utf-8")
    with pytest.raises(MetadataDryRunError, match="no data rows"):
        read_metadata_csv(header_only)

    with pytest.raises(MetadataDryRunError, match="no such file"):
        read_metadata_csv(tmp_path / "missing.csv")


def test_ignored_columns_reported(tmp_path: Path) -> None:
    p = tmp_path / "review.csv"
    p.write_text(
        "symbol,name,source_category,sector\nABC,Alpha,share_sansar,Bank\n", encoding="utf-8"
    )
    rows, ignored = read_metadata_csv(p)
    assert ignored == ["source_category"]
    assert len(rows) == 1


# ---------------------------------------------------------- duplicate symbols


def test_identical_duplicates_collapse_and_conflicting_duplicates_are_ambiguous(
    tmp_path: Path,
) -> None:
    csv = _csv(
        tmp_path / "reviewed.csv",
        "DUP1,,ordinary,Bank,listed,,,,\n"
        "DUP1,,ordinary,Bank,listed,,,,\n"
        "DUP2,,ordinary,Bank,listed,,,,\n"
        "DUP2,,ordinary,Hydro,listed,,,,\n",
    )
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()

    s = result["summary"]
    assert s["records_examined"] == 4
    assert s["rows_collapsed_duplicates"] == 1
    assert s["symbols_ambiguous"] == 1
    assert s["conflicting"] == 1
    dup1 = _record(result, "DUP1")
    assert dup1["action"] == "addition"  # collapsed to a single record
    dup2 = _record(result, "DUP2")
    assert dup2["action"] == "conflict"
    assert dup2["requires_manual_review"] is True
    assert "duplicate symbol rows disagree" in dup2["conflicts"][0]
    # both raw row values are preserved for the reviewer
    assert "Bank" in dup2["review_reasons"][0] and "Hydro" in dup2["review_reasons"][0]


def test_blank_symbol_rows_rejected(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "reviewed.csv", ",,,,,,,,\nABC,,ordinary,Bank,listed,,,,\n")
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    assert result["summary"]["records_examined"] == 2
    assert result["summary"]["rows_rejected"] == 1
    rejected = result["rejected_records"]
    assert rejected[0]["reasons"] == ["symbol is empty"]
    assert isinstance(rejected[0]["line"], int)  # line numbers survive for the report


# --------------------------------------------------- invalid vocab / formats


def test_invalid_instrument_type_status_and_delisted_rejected(tmp_path: Path) -> None:
    csv = _csv(
        tmp_path / "reviewed.csv",
        "BADTYPE,,etf,,listed,,,,\nBADSTAT,,,Bank,mergedish,,,,\nBADDEL,,,Bank,listed,maybe,,\n",
    )
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()

    assert result["summary"]["rows_rejected"] == 3
    by_symbol = {r["symbol"]: r["reasons"] for r in result["rejected_records"]}
    assert "instrument_type" in by_symbol["BADTYPE"][0]
    assert "status" in by_symbol["BADSTAT"][0]
    assert "TRUE/FALSE" in by_symbol["BADDEL"][0]
    # rejected symbols produce no record and nothing is coerced
    assert result["records"] == []


def test_invalid_symbol_format_rejected(tmp_path: Path) -> None:
    csv = _csv(
        tmp_path / "reviewed.csv",
        "lower,,,,listed,,,,\nHAS SPACE,,,,listed,,,,\nPUNC!,,,,listed,,,,\n",
    )
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    assert result["summary"]["rows_rejected"] == 3
    reasons = " ".join(" ".join(r["reasons"]) for r in result["rejected_records"])
    assert "uppercase" in reasons


def test_invalid_symbol_format_accepts_bond_symbols(tmp_path: Path) -> None:
    csv = _csv(
        tmp_path / "reviewed.csv",
        "NMBD87-88,,,,listed,,,,\nGBD80/81,,,,listed,,,,\n",
    )
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    assert result["summary"]["rows_rejected"] == 0
    assert result["summary"]["symbols_validated"] == 2


# -------------------------------------------------- sector provenance preview


def test_sector_provenance_columns_are_reconciled(tmp_path: Path) -> None:
    csv = Path(tmp_path / "reviewed.csv")
    csv.write_text(
        "symbol,name,instrument_type,sector,status,delisted,successor_symbol,source,"
        "requires_manual_review,sector_source,sector_retrieved_at,sector_observed_date\n"
        "ABC,,,Hydro Power,,,,owner-note,,owner-note,2026-10-15T09:30:00Z,2026-10-15\n",
        encoding="utf-8",
    )
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    rec = _record(result, "ABC")
    assert rec["proposed"]["sector_source"] == "owner-note"
    assert rec["proposed"]["sector_retrieved_at"] == "2026-10-15T09:30:00"
    assert rec["proposed"]["sector_observed_date"] == "2026-10-15"
    # Sector and provenance both disagree with the stored row -> conflict.
    assert rec["action"] == "conflict"
    assert any("sector_source" in c for c in rec["conflicts"])


def test_missing_sector_source_is_flagged_for_review(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "reviewed.csv", "ABC,,,Hydro Power,,,,,\n")
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    rec = _record(result, "ABC")
    assert rec["requires_manual_review"] is True
    assert any("sector_source" in r for r in rec["review_reasons"])


def test_malformed_sector_timestamp_or_date_rejected(tmp_path: Path) -> None:
    csv = Path(tmp_path / "bad.csv")
    csv.write_text(
        "symbol,sector,sector_retrieved_at,sector_observed_date\n"
        "ABC,Bank,not-a-date,\n"
        "XYZ,Bank,,2026-99-01\n",
        encoding="utf-8",
    )
    store = _store(tmp_path / "db.duckdb")
    with pytest.raises(MetadataDryRunError, match="sector_retrieved_at"):
        build_dry_run(csv, store)
    store.close()


# ------------------------------------------------------ metadata gaps report


def test_metadata_gaps_reports_missing_fields(tmp_path: Path) -> None:
    store = _store(tmp_path / "db.duckdb")
    result = metadata_gaps(store)
    store.close()

    assert result["store_symbols"] == 3
    assert result["gaps"]["sector"]["count"] == 1
    assert "XYZ" in result["gaps"]["sector"]["symbols"]
    assert result["gaps"]["instrument_type"]["count"] == 2
    assert "XYZ" in result["gaps"]["instrument_type"]["symbols"]
    # ABC and XYZ keep the default UNKNOWN status; GONE derives DELISTED.
    assert result["gaps"]["status_unknown"]["count"] == 2
    assert "XYZ" in result["gaps"]["status_unknown"]["symbols"]
    assert result["gaps"]["name"]["count"] == 0
    assert result["complete_records"] == 0  # no symbol has all four fields populated


def test_metadata_gaps_cli_writes_outputs_and_matches_library(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    store = _store(tmp_path / "db.duckdb")
    store.close()
    out_dir = tmp_path / "out"

    rc = main(
        [
            "metadata",
            "gaps",
            "--db",
            str(tmp_path / "db.duckdb"),
            "--out-dir",
            str(out_dir),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    json_path = out_dir / "db_gaps.json"
    md_path = out_dir / "db_gaps.md"
    assert json_path.exists() and md_path.exists()

    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    store = MarketStore(tmp_path / "db.duckdb", read_only=True)
    fresh = metadata_gaps(store)
    store.close()
    assert on_disk == fresh
    assert "Security-metadata gap report" in md_path.read_text(encoding="utf-8")


# -------------------------------------------- unknown vs conflicting metadata


def test_blank_metadata_never_filled(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "reviewed.csv", "NEW1,,ordinary,,listed,,,,\n")
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    rec = _record(result, "NEW1")
    assert "sector" not in rec["proposed"]  # blank stays blank — no invented sector
    assert "name" not in rec["proposed"]  # and no invented name either
    assert rec["current"] is None
    # blank fields are counted as unknown, never guessed
    assert result["summary"]["unknown_values_left_blank"] >= 1


def test_conflict_preserves_and_reports_stored_value(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "reviewed.csv", "ABC,,,Hydro Power,listed,,,owner-note,\n")
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    rec = _record(result, "ABC")
    assert rec["action"] == "conflict"
    assert any("sector" in c for c in rec["conflicts"])
    assert rec["current"]["sector"] == "Bank"  # stored side is preserved and shown
    assert rec["requires_manual_review"] is True


def test_delisted_reactivation_is_a_conflict(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "reviewed.csv", "GONE,,,,listed,FALSE,,,owner-note,\n")
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    rec = _record(result, "GONE")
    assert rec["action"] == "conflict"
    assert any("reactivation risk" in c for c in rec["conflicts"])
    assert rec["current"]["delisted"] is True  # stored True wins; nothing overwritten


def test_clean_update_and_no_proposal(tmp_path: Path) -> None:
    csv = _csv(
        tmp_path / "reviewed.csv",
        "XYZ,,,Microfinance,,,,,\n"  # fills a stored NULL: update
        "ABC,,,,,,,,\n",  # all metadata blank: proposes nothing
    )
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    xyz = _record(result, "XYZ")
    assert xyz["action"] == "update"
    assert xyz["proposed"]["sector"] == "Microfinance"
    assert xyz["current"]["sector"] is None  # unknown stayed unknown until proposed
    abc = _record(result, "ABC")
    assert abc["action"] == "no-proposal"
    assert abc["requires_manual_review"] is True  # a row proposing nothing is surfaced
    assert result["summary"]["updates"] == 1
    assert result["summary"]["no_proposal"] == 1


def test_status_change_on_existing_row_is_a_conflict(tmp_path: Path) -> None:
    # The store now has a status column (default UNKNOWN), so a status proposal
    # that disagrees with the stored value is a conflict, not a silent update.
    csv = _csv(tmp_path / "reviewed.csv", "ABC,,,,listed,,,note,\n")
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    rec = _record(result, "ABC")
    assert rec["action"] == "conflict"
    assert rec["requires_manual_review"] is True
    assert rec["proposed"]["status"] == STATUS_ACTIVE


# --------------------------------------------------------- merged vs delisted


def test_merged_status_never_becomes_delisted(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "reviewed.csv", "XYZ,,,,merged,,,share-sansar-note,\n")
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    rec = _record(result, "XYZ")
    assert "delisted" not in rec["proposed"]  # merged is never converted
    assert rec["requires_manual_review"] is True
    assert any("MERGED" in r for r in rec["review_reasons"])
    assert result["policy"]["merged_status"] == "stored as-is (MERGED); never converted to DELISTED"
    # nowhere in the whole result is a merged row turned into delisted=True
    for r in result["records"]:
        if r["proposed"].get("status") == STATUS_MERGED:
            assert r["proposed"].get("delisted") is not True


def test_status_and_delisted_tension_flagged(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "reviewed.csv", "NEW1,,ordinary,Life Insurance,listed,TRUE,,,\n")
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    rec = _record(result, "NEW1")
    assert rec["requires_manual_review"] is True
    assert any("internal tension" in r for r in rec["review_reasons"])


# -------------------------------------------------------- successor symbols


def test_successor_symbol_proposal_reconciled(tmp_path: Path) -> None:
    csv = _csv(
        tmp_path / "reviewed.csv", "XYZ,,,,merged,,ACTIVE,note,\nNEW2,,ordinary,Bank,listed,,,,\n"
    )
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    xyz = _record(result, "XYZ")
    assert xyz["proposed"].get("successor_symbol") == "ACTIVE"
    assert xyz["requires_manual_review"] is True
    new2 = _record(result, "NEW2")
    assert new2["proposed"].get("successor_symbol") is None


# ---------------------------------------------------------- manual-review flag


def test_explicit_manual_review_flag_honoured(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "reviewed.csv", "XYZ,,,Microfinance,,,,,TRUE\n")
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    rec = _record(result, "XYZ")
    assert rec["action"] == "update"
    assert rec["requires_manual_review"] is True
    assert any("requires_manual_review=TRUE" in r for r in rec["review_reasons"])
    assert result["summary"]["requires_manual_review"] == 1


# ---------------------------------------------------------------- determinism


def test_dry_run_output_is_deterministic(tmp_path: Path) -> None:
    csv = _csv(
        tmp_path / "reviewed.csv",
        "ABC,,,Hydro Power,listed,,,note,\n"
        "NEW1,,ordinary,Life Insurance,listed,,,,\n"
        "DUP2,,ordinary,Bank,listed,,,,\n"
        "DUP2,,ordinary,Hydro,listed,,,,\n"
        "BADTYPE,,etf,,listed,,,,\n",
    )
    store = _store(tmp_path / "db.duckdb")
    first = build_dry_run(csv, store)
    second = build_dry_run(csv, store)
    store.close()

    assert result_json(first) == result_json(second)
    assert render_markdown(first) == render_markdown(second)
    assert first["input"]["sha256"] == hashlib.sha256(csv.read_bytes()).hexdigest()
    assert "timestamp" not in result_json(first).lower()


def test_write_outputs_refuses_to_overwrite(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "reviewed.csv", "NEW1,,ordinary,Life Insurance,listed,,,,\n")
    store = _store(tmp_path / "db.duckdb")
    result = build_dry_run(csv, store)
    store.close()
    out_dir = tmp_path / "out"
    written = write_outputs(result, out_dir)
    original = written["json"].read_bytes()
    with pytest.raises(MetadataDryRunError, match="refusing to overwrite"):
        write_outputs(result, out_dir)
    assert written["json"].read_bytes() == original  # prior artifact untouched


# ------------------------------------------------- store safety (the hard one)


def test_cli_run_leaves_database_byte_identical(tmp_path: Path) -> None:
    csv = _csv(
        tmp_path / "reviewed.csv",
        "ABC,,,Hydro Power,listed,,,note,\nNEW1,,ordinary,X,listed,,,,\n",
    )
    store = _store(tmp_path / "db.duckdb")
    snapshot = store.securities_meta()
    store.close()
    db = tmp_path / "db.duckdb"
    digest_before = hashlib.sha256(db.read_bytes()).hexdigest()
    mtime_before = db.stat().st_mtime_ns

    rc = main(
        [
            "metadata",
            "dry-run",
            "--input",
            str(csv),
            "--db",
            str(db),
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 0
    assert hashlib.sha256(db.read_bytes()).hexdigest() == digest_before
    assert db.stat().st_mtime_ns == mtime_before

    reopened = MarketStore(db, read_only=True)
    assert reopened.securities_meta() == snapshot
    reopened.close()


def test_cli_reports_missing_input_and_missing_database(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    rc = main(
        [
            "metadata",
            "dry-run",
            "--input",
            str(tmp_path / "nope.csv"),
            "--db",
            str(tmp_path / "nope.duckdb"),
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 1
    assert "no such file" in capsys.readouterr().err


def test_cli_reports_locked_or_missing_database_honestly(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    csv = _csv(tmp_path / "reviewed.csv", "NEW1,,ordinary,X,listed,,,,\n")
    rc = main(
        [
            "metadata",
            "dry-run",
            "--input",
            str(csv),
            "--db",
            str(tmp_path / "missing.duckdb"),
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "cannot open the database read-only" in err
    assert "never writes to the database" in err  # the hint stays honest
    assert not (tmp_path / "out").exists()  # nothing written on failure
