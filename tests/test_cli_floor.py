"""CLI floor-sheet commands.

The autouse fixture in conftest.py points both databases at a throwaway
directory, so these run against an isolated store rather than the owner's.
"""

from __future__ import annotations

import pytest

from megatool.cli import main

SHEET = """Symbol,Buyer,Seller,Quantity,Rate,Amount
NABIL,B1,B2,100,500,50000
NICA,B2,B3,300,250,75000
"""


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_summary_before_any_import_tells_you_what_to_do(tmp_path, capsys):
    assert main(["floor", "summary", "--sessions"]) == 0
    out = capsys.readouterr().out
    assert "No floor sheet has been imported" in out
    assert "megatool floor import FILE --date" in out


def test_import_then_list_sessions(tmp_path, capsys):
    path = _write(tmp_path, "sheet.csv", SHEET)
    assert main(["floor", "import", str(path), "--date", "2026-10-09"]) == 0
    out = capsys.readouterr().out
    assert "trades stored:         2" in out

    assert main(["floor", "summary", "--sessions"]) == 0
    listing = capsys.readouterr().out
    assert "2026-10-09" in listing
    assert "NABIL" not in listing.splitlines()[1]  # the session line shows counts


def test_reimporting_the_same_file_reports_nothing_added(tmp_path, capsys):
    path = _write(tmp_path, "sheet.csv", SHEET)
    main(["floor", "import", str(path), "--date", "2026-10-09"])
    capsys.readouterr()
    assert main(["floor", "import", str(path), "--date", "2026-10-09"]) == 0
    out = capsys.readouterr().out
    assert "trades stored:         0" in out
    assert "already imported" in out


def test_summary_prints_totals_tables_and_the_honesty_limits(tmp_path, capsys):
    path = _write(tmp_path, "sheet.csv", SHEET)
    main(["floor", "import", str(path), "--date", "2026-10-09"])
    capsys.readouterr()

    assert main(["floor", "summary"]) == 0
    out = capsys.readouterr().out
    assert "trades:                2" in out
    assert "NPR 125,000.00" in out  # 50,000 + 75,000
    assert "Top buyers" in out and "Top sellers" in out
    # The framing must survive the trip through the terminal.
    assert "broker CODES, not beneficial owners" in out
    assert "not why" in out
    assert "investment advice" in out


def test_summary_can_be_filtered_by_symbol(tmp_path, capsys):
    path = _write(tmp_path, "sheet.csv", SHEET)
    main(["floor", "import", str(path), "--date", "2026-10-09"])
    capsys.readouterr()

    assert main(["floor", "summary", "--symbol", "NICA"]) == 0
    out = capsys.readouterr().out
    assert "NABIL" not in out
    assert "NICA" in out


def test_a_file_that_is_not_a_floor_sheet_is_an_error_not_a_traceback(tmp_path, capsys):
    path = _write(tmp_path, "bad.csv", "Symbol,Quantity\nNABIL,100\n")
    assert main(["floor", "import", str(path), "--date", "2026-10-09"]) == 1
    err = capsys.readouterr().err
    assert "missing required column(s): buyer, seller, rate" in err
    assert "Traceback" not in err


def test_a_missing_file_is_an_error_not_a_traceback(tmp_path, capsys):
    assert main(["floor", "import", str(tmp_path / "nope.csv"), "--date", "2026-10-09"]) == 1
    assert "no such file" in capsys.readouterr().err


def test_skipped_rows_are_reported_with_their_line_number(tmp_path, capsys):
    path = _write(
        tmp_path,
        "messy.csv",
        "Symbol,Buyer,Seller,Quantity,Rate,Amount\nNABIL,B1,B2,oops,500,0\nNABIL,B1,B2,100,500,99999\n",
    )
    assert main(["floor", "import", str(path), "--date", "2026-10-10"]) == 0
    out = capsys.readouterr().out
    assert "rows skipped:          1" in out
    assert "skipped line 2: not a number" in out
    assert "disagrees with quantity x rate" in out


def test_date_is_required_for_an_import(tmp_path, capsys):
    path = _write(tmp_path, "sheet.csv", SHEET)
    with pytest.raises(SystemExit):
        main(["floor", "import", str(path)])
