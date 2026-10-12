"""Tests for the secondary-digitization reference parser.

Two things are being pinned here.

First, **provenance**: every record this module emits is another machine's
reading of the same handwritten notebook, so it must never be able to present
itself as a visual reading or as current market data.

Second, **the cross-check is honest about what it found**. Every arithmetic
expectation below is worked out in the comment above it independently of the
code under test, so a parser change cannot quietly redefine what "agrees" means.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from megatool import written_reference as wr
from megatool.written_reference import (
    DATA_VINTAGE,
    MD_FILENAME,
    PROVENANCE,
    load_reference,
    parse_markdown,
    reference_summary,
    write_reference_csvs,
)

SOURCE = Path(wr.__file__).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ref() -> dict:
    """Parsed once: the reference files are read-only inputs to every test."""
    return load_reference()


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------
def test_every_reference_record_carries_the_three_labels(ref: dict) -> None:
    families = (
        "transactions",
        "fundamentals",
        "scoreboards",
        "strategies",
        "watchlists",
        "settlements",
        "workbook_rows",
    )
    total = 0
    for name in families:
        rows = ref[name]
        total += len(rows)
        for row in rows:
            assert row["provenance"] == PROVENANCE == "secondary_digitization"
            assert row["verification"] == "unverified"
            assert row["data_vintage"] == DATA_VINTAGE
            assert row["source_file"] in wr.REFERENCE_FILES
    assert total > 100, "the reference files are real; an empty parse would hide a regression"


def test_reference_figures_are_declared_historical_never_live_market_data(ref: dict) -> None:
    """A notebook 'Market Price' is a handwriting artifact, not a NEPSE quote.

    Anything downstream that reads ``data_vintage`` must be able to refuse to
    treat these as tradable current prices.
    """
    seen = set()
    for name in ("fundamentals", "transactions", "scoreboards", "workbook_rows"):
        for row in ref[name]:
            seen.add(row["data_vintage"])
    assert seen == {"historical_handwritten"}


def test_the_reference_module_never_touches_the_database() -> None:
    """Records are delivered as files, not imported, so nothing duplicates.

    Page attribution is required for every ``pdf_records`` row and the
    reference files do not say which page a figure came from — inventing one
    would break the rule ``written_pdf`` depends on. Guarding the source keeps
    that decision from being quietly reversed later.
    """
    assert "get_conn" not in SOURCE
    assert "import_records" not in SOURCE
    assert not re.search(r"\bINSERT\s+INTO\b", SOURCE, re.IGNORECASE)


def test_a_missing_reference_file_is_reported_not_raised(tmp_path: Path) -> None:
    ref = load_reference(root=tmp_path)
    assert ref["files_missing"] == [MD_FILENAME]
    assert ref["files_found"] == []
    assert ref["transactions"] == ref["settlements"] == ref["cross_check"] == []
    assert ref["component_cross_check"] == []


# --------------------------------------------------------------------------
# settlement parsing — three regressions that each produced wrong output
# --------------------------------------------------------------------------
def test_the_last_august_settlement_is_not_polluted_by_september_rows(ref: dict) -> None:
    """8E is the last multi-line block, so nothing reset ``current`` after it.

    Before this was fixed, September's trade-register rows were scanned while
    8E was still open and overwrote its totals with September figures.
    """
    blocks = {b["label"]: b for b in ref["settlements"]}

    # read by eye on page 19 and confirmed by the totals cross-check below.
    assert blocks["8E"]["buy_total"] == 217_495.28
    assert blocks["8E"]["sell_total"] == 148_478.38
    assert blocks["8E"]["net"] == 69_016.90
    # September's own numbers would have appeared here before the fix.
    assert blocks["8E"]["buy_total"] != 146_549.32


def test_an_inline_settlement_closes_its_block_before_the_next_section() -> None:
    """11A must not absorb the January day-line's net.

    ``- **15 Jan:** … → **Net Payable:** NPR 21,091.29`` follows 11A in the
    document and matches the same net pattern, so an inline settlement that
    left its block open would silently have 11A reporting January's figure.
    """
    md = (wr._PROJECT_ROOT / MD_FILENAME).read_text(encoding="utf-8")
    blocks = wr._settlement_blocks(md)

    assert blocks["11A"]["buy_total"] == 301_275.69
    assert blocks["11A"]["sell_total"] == 247_751.61
    # 301275.69 - 247751.61 = 53524.08
    assert blocks["11A"]["net"] == 53_524.08
    # The January day-line's net, which used to overwrite the line above.
    assert blocks["11A"]["net"] != 21_091.29


def test_a_settlement_whose_label_carries_a_date_range_still_parses() -> None:
    """9E and 9F are written ``Buy (29 Sep): NPR …``, not ``Buy NPR …``."""
    md = (wr._PROJECT_ROOT / MD_FILENAME).read_text(encoding="utf-8")
    blocks = wr._settlement_blocks(md)

    # read by eye on page 23.
    assert blocks["9E"]["buy_total"] == 121_894.12
    assert blocks["9E"]["sell_total"] == 81_793.82
    assert blocks["9E"]["net"] == 40_100.30
    assert blocks["9F"]["buy_total"] == 146_549.32
    assert blocks["9F"]["sell_total"] == 55_642.28
    # 146549.32 - 55642.28 = 90907.04
    assert blocks["9F"]["net"] == 90_907.04


def test_a_markdown_table_and_a_bullet_are_not_confused() -> None:
    parsed = parse_markdown("# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- bullet\n")
    body = parsed["sections"]["T"]
    assert body["tables"][0]["header"] == ["a", "b"]
    assert body["tables"][0]["rows"] == [["1", "2"]]
    assert body["bullets"] == ["bullet"]


def test_a_torn_table_row_is_kept_as_read_rather_than_padded() -> None:
    """A missing cell is an absence. Padding would invent a value."""
    parsed = parse_markdown("# T\n\n| a | b | c |\n|---|---|---|\n| 1 | 2 |\n")
    assert parsed["sections"]["T"]["tables"][0]["rows"] == [["1", "2"]]


# --------------------------------------------------------------------------
# cross-checks
# --------------------------------------------------------------------------
def test_the_totals_cross_check_agrees_on_every_compared_field(ref: dict) -> None:
    """August and September expose settlement totals; every one must agree."""
    cross = ref["cross_check"]
    compared = [c for c in cross if c["fields_compared"]]

    assert len(compared) == 9
    assert sum(c["fields_compared"] for c in compared) == 27
    assert sum(c["fields_agree"] for c in compared) == 27
    assert all(not c["disagreements"] for c in compared)

    by_label = {c["label"]: c for c in cross}
    # buy, sell and net — three fields each.
    for label in ("8C", "8D", "8E", "9A", "9B", "9C", "9D", "9E", "9F"):
        assert by_label[label]["fields_compared"] == 3
        assert by_label[label]["verification"] == "cross_checked"


def test_december_exposes_no_totals_so_it_reports_zero_comparisons(ref: dict) -> None:
    """12A-12F are written as day lines, not settlements — cmp=0, not a pass.

    Reporting these as agreeing would be claiming evidence that does not exist.
    The component check below is where December is actually covered.
    """
    by_label = {c["label"]: c for c in ref["cross_check"]}
    for label in ("12A", "12B", "12C", "12D", "12E", "12F"):
        assert by_label[label]["fields_compared"] == 0
        assert by_label[label]["verification"] == "unverified"


def test_the_component_cross_check_has_no_disagreements(ref: dict) -> None:
    """Every component read by eye that the reference also has must match."""
    comps = ref["component_cross_check"]
    readable = [c for c in comps if c["components_match"] is not None]

    assert len(comps) == 22
    assert len(readable) == 11
    assert sum(1 for c in readable if c["components_match"]) == 11
    assert sum(1 for c in readable if not c["components_match"]) == 0
    assert all(c["verification"] == "cross_checked" for c in readable)


def test_12c_buy_components_match_at_the_corrected_value(ref: dict) -> None:
    """The correction applied to page 28 is independently confirmed here.

    The by-eye read was 77793.55 and left the block 2.00 short of its net.
    8963.09 + 68832.46 = 77795.55, which is what the reference states for
    12 Dec — and what the corrected record now holds.
    """
    from megatool.written_transcribe import VISUALLY_READ_PAGE_28

    rec = {d["label"]: d for d in VISUALLY_READ_PAGE_28}["12C"]
    assert rec["buy_total"] == 77_795.55
    assert rec["superseded_readings"][0]["original_reading"] == 77_793.55

    row = next(
        c for c in ref["component_cross_check"] if c["label"] == "12C" and c["side"] == "buy"
    )
    assert row["reference_components"] == [77_795.55]
    assert row["my_components"] == [77_795.55]
    assert row["components_match"] is True
    assert row["total_matches_reference_sum"] is True


def test_12d_components_match_but_the_written_total_still_differs_by_a_cent(
    ref: dict,
) -> None:
    """The 0.01 is in the written total, not in any component — and stays.

    98889.26 + 95841.88 + 75943.63 + 12782.66 = 283457.43
    The page writes 283457.42. Both are reported; neither is edited.
    """
    from megatool.written_transcribe import VISUALLY_READ_PAGE_30

    rec = {d["label"]: d for d in VISUALLY_READ_PAGE_30}["12D"]
    assert rec["buy_total"] == 283_457.42  # as written, unchanged
    assert sum(rec["buy_components"]) == pytest.approx(283_457.43)
    assert len(rec["source_discrepancies"]) == 1

    row = next(
        c for c in ref["component_cross_check"] if c["label"] == "12D" and c["side"] == "buy"
    )
    assert row["components_match"] is True  # every component agrees
    assert row["total_matches_reference_sum"] is False  # the total does not


def test_12f_sell_components_stay_empty_even_though_the_reference_supplies_them(
    ref: dict,
) -> None:
    """An unread list is an absence of reading, not a disagreement.

    12497.86 + 130228.05 = 142725.91, exactly the sell total read by eye. The
    sum is reported as agreeing; the component list on the *record* is not
    filled, because a machine reading is not a visual reading.
    """
    from megatool.written_transcribe import VISUALLY_READ_PAGE_30

    rec = {d["label"]: d for d in VISUALLY_READ_PAGE_30}["12F"]
    assert rec["sell_components"] == []
    assert rec["sell_total"] == 142_725.91
    assert 12_497.86 + 130_228.05 == 142_725.91

    row = next(
        c for c in ref["component_cross_check"] if c["label"] == "12F" and c["side"] == "sell"
    )
    assert row["my_components"] == []
    assert row["reference_components"] == [12_497.86, 130_228.05]
    assert row["components_match"] is None  # neither agreement nor disagreement
    assert row["total_matches_reference_sum"] is True
    assert "not read by eye" in row["note"]


def test_no_figure_was_moved_to_make_a_cross_check_pass() -> None:
    """The disagreements that still exist must still exist."""
    from megatool.written_transcribe import ALL_VISUALLY_READ

    rec = {d["label"]: d for d in ALL_VISUALLY_READ}
    # Page 19's 8C does not close, and no second reading repaired it.
    assert rec["8C"]["source_discrepancies"]  # the 1.00 and 8.03 are still there
    # Page 30's 12D 0.01 is still reported, not edited away.
    assert rec["12D"]["source_discrepancies"]
    # The withdrawn figure must never reappear anywhere in the verified set.
    assert "186129.76" not in json.dumps(list(ALL_VISUALLY_READ))
    assert "186,129.76" not in json.dumps(list(ALL_VISUALLY_READ))


def test_the_cross_check_never_claims_more_than_cross_checked(ref: dict) -> None:
    """``cross_checked`` is a second reading agreeing — never ``verified``."""
    allowed = {"unverified", "cross_checked"}
    for row in ref["cross_check"]:
        assert row["verification"] in allowed
    for row in ref["component_cross_check"]:
        assert row["verification"] in allowed


def test_summary_counts_match_the_data_they_count(ref: dict) -> None:
    s = reference_summary(ref)
    assert s["transactions"] == len(ref["transactions"])
    assert s["component_sides_compared"] == len(ref["component_cross_check"])
    readable = [c for c in ref["component_cross_check"] if c["components_match"] is not None]
    assert s["component_sides_readable"] == len(readable)
    assert s["component_sides_agreeing"] + s["component_sides_disagreeing"] == len(readable)
    assert s["fields_compared"] >= s["fields_agree"]
    assert set(s["files_found"]) == {MD_FILENAME, wr.XLSX_FILENAME}
    assert ref["workbook_rows"], "the workbook is present and must be reported as parsed"


# --------------------------------------------------------------------------
# CSV delivery
# --------------------------------------------------------------------------
def test_csv_output_is_machine_readable_and_never_writes_none_as_zero(
    ref: dict, tmp_path: Path
) -> None:
    """Structured cells become JSON; an unread value becomes empty, not 0.

    Writing ``None`` as ``0`` would turn "we could not read it" into "the
    value is zero" — the same failure mode that produced the withdrawn
    186,129.76.
    """
    counts = write_reference_csvs(tmp_path, ref)
    assert counts["reference_component_cross_check.csv"] == 22
    assert counts["reference_cross_check.csv"] == 16

    for name in counts:
        path = tmp_path / name
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            for cell in row.values():
                if cell is None or cell == "":
                    continue
                assert "None" not in cell, f"{name}: Python repr leaked into CSV"
                if cell[0] in "[{":
                    assert _is_json(cell), f"{name}: structured cell is not JSON: {cell!r}"

    # 12F's unread components must be [] (JSON), never 0 or empty-meaning-zero.
    with (tmp_path / "reference_component_cross_check.csv").open(
        newline="", encoding="utf-8"
    ) as fh:
        rows = list(csv.DictReader(fh))
    sell_12f = next(r for r in rows if r["label"] == "12F" and r["side"] == "sell")
    assert json.loads(sell_12f["my_components"]) == []
    assert sell_12f["components_match"] == ""  # None -> blank, not "False"
    assert json.loads(sell_12f["reference_components"]) == [12_497.86, 130_228.05]
    assert json.loads(sell_12f["total_matches_reference_sum"]) is True


def _is_json(cell: str) -> bool:
    try:
        json.loads(cell)
    except (ValueError, TypeError):
        return False
    return True


def test_writing_is_reproducible(ref: dict, tmp_path: Path) -> None:
    """Re-running the build must not accumulate rows (idempotent output)."""
    first = write_reference_csvs(tmp_path, ref)
    second = write_reference_csvs(tmp_path, load_reference())
    assert first == second
