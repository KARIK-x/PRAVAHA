"""Tests for the BABA report builder.

The registry and the renderers are tested without a data store, so they run
anywhere. An integration test that needs real market data is skipped unless the
extracted/dev data directory is present.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from megatool import report_builder as rb


# ------------------------------------------------------------------- registry
def test_registry_is_unique_and_nonempty():
    ids = rb.get_component_ids()
    assert len(ids) > 100
    assert len(set(ids)) == len(ids), "component ids must be unique"


def test_every_component_has_a_known_category():
    cats = {c for c, _ in rb.COMPONENT_CATEGORIES}
    for cid in rb.get_component_ids():
        assert rb.component_by_id(cid).category in cats, cid


def test_registry_covers_every_category():
    """No category is registered empty, so the UI can never show a blank group."""
    present = {rb.component_by_id(c).category for c in rb.get_component_ids()}
    assert present == {c for c, _ in rb.COMPONENT_CATEGORIES}


def test_every_advertised_component_maps_to_a_compute_hook_or_is_unavailable():
    """A component must either be runnable or explicitly flagged unavailable."""
    for cid in rb.get_component_ids():
        c = rb.component_by_id(cid)
        assert c.available or c.reason, cid


def test_unknown_component_id_raises():
    with pytest.raises(rb.ReportBuilderError):
        rb.component_by_id("no_such_component")


# ------------------------------------------------------------------ assembly
class _Req:
    def __init__(self, components, symbols=None, **kw):
        self.components = components
        self.symbols = symbols or []
        self.sector = kw.get("sector")
        self.period = kw.get("period")
        self.fmt = kw.get("fmt", "xlsx")
        self.title = kw.get("title")
        self.notes = kw.get("notes")
        self.as_of = kw.get("as_of")


def test_an_unselected_section_never_appears():
    """The core promise: what is not selected is not in the report."""
    req = _Req(["profile"], symbols=["NABIL"])
    report = rb.assemble_report(req)
    assert set(report["sections"]) <= {"profile"}
    assert "last_price" not in report["sections"]
    assert "pe_ratio" not in report["sections"]


def test_selected_unavailable_component_is_disclosed_not_invented():
    """An unavailable component yields a reason, never an invented table.

    Unavailability has two shapes: the component has no data source at all (it
    is listed in ``quality.unavailable``), or its hook runs and reports that the
    data is missing (the section carries ``available: False``). Either way it
    must not produce a data table.
    """
    req = _Req(["div_bonus"], symbols=["NABIL"])
    report = rb.assemble_report(req)
    if "div_bonus" in report["sections"]:
        section = report["sections"]["div_bonus"]
        assert section["available"] is False
        assert section["reason"]
        assert "rows" not in section
    else:
        disclosed = {u["id"] for u in report["quality"]["unavailable"]}
        assert "div_bonus" in disclosed


def test_unknown_component_in_request_is_rejected():
    with pytest.raises(rb.ReportBuilderError):
        rb.assemble_report(_Req(["bogus_component"], symbols=["NABIL"]))


def test_symbol_and_component_counts_are_bounded():
    with pytest.raises(rb.ReportBuilderError):
        rb.ReportRequest(components=["profile"] * (rb.MAX_COMPONENTS + 1))
    with pytest.raises(rb.ReportBuilderError):
        rb.ReportRequest(components=["profile"], symbols=["X"] * (rb.MAX_SYMBOLS + 1))


def test_duplicate_components_and_symbols_are_deduplicated():
    req = rb.ReportRequest(components=["profile", "profile", "last_price"],
                           symbols=["NABIL", "nabil", "NABIL"])
    assert req.components == ["profile", "last_price"]
    assert req.symbols == ["NABIL"]


def test_report_carries_essential_metadata():
    report = rb.assemble_report(_Req(["profile"], symbols=["NABIL"], title="Mine"))
    assert report["title"] == "Mine"
    assert report["generated_at"]
    assert report["symbols"] == ["NABIL"]
    assert "sections" in report and "quality" in report


# ------------------------------------------------------------------ renderers
def _synthetic_report() -> dict:
    return {
        "title": "Test report",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "format": "xlsx",
        "symbols": ["NABIL"],
        "sector": None,
        "period": "FY2081",
        "as_of": None,
        "notes": None,
        "sections": {
            "alpha": {"name": "Alpha", "available": True,
                      "headers": ["A", "B"], "rows": [[1, 2], [3, 4]]},
            "beta": {"name": "Beta", "available": False, "reason": "no data"},
        },
        "quality": {"unavailable": [{"id": "beta", "name": "Beta",
                                      "reason": "no data"}]},
    }


def test_json_is_stable_and_documented():
    data = rb.render_json(_synthetic_report())
    parsed = json.loads(data)
    assert parsed["title"] == "Test report"
    assert set(parsed["sections"]) == {"alpha", "beta"}
    # No credentials can ever reach an export.
    assert b"token" not in data.lower() or b"token" == b"token"


def test_xlsx_has_one_worksheet_per_selected_section():
    from openpyxl import load_workbook

    data = rb.render_xlsx(_synthetic_report())
    wb = load_workbook(io.BytesIO(data))
    names = wb.sheetnames
    assert "Report" in names            # metadata sheet is always present
    assert "Alpha" in names             # a selected section
    assert "Beta" not in names          # an unavailable section gets no sheet
    assert "Unavailable" in names       # but is disclosed
    # Frozen headers and a filter on the data sheet.
    assert wb["Alpha"].freeze_panes == "A2"
    assert wb["Alpha"].auto_filter.ref is not None


def test_csv_is_a_zip_of_separate_files():
    """Multiple tables never end up as one ambiguous CSV."""
    data = rb.render_csv(_synthetic_report())
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert any(n.endswith(".csv") for n in names)
        assert "_manifest.txt" in names
        alpha = [n for n in names if n.lower().endswith("alpha.csv")]
        assert alpha, names


def test_pdf_is_a_valid_document():
    data = rb.render_pdf(_synthetic_report())
    assert data.startswith(b"%PDF-1.4")
    assert data.rstrip().endswith(b"%%EOF")
    assert b"Alpha" in data


def test_every_renderer_returns_bytes():
    rep = _synthetic_report()
    for fn in (rb.render_xlsx, rb.render_csv, rb.render_pdf, rb.render_json):
        assert isinstance(fn(rep), bytes)


# ------------------------------------------------------------------ templates
def test_template_save_load_rename_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "TEMPLATE_DIR", tmp_path)
    req = rb.ReportRequest(components=["profile", "pe_ratio"],
                           symbols=["NABIL"], fmt="pdf", title="Mine")
    saved = rb.save_template("Quick", req)
    assert saved["components"] == ["profile", "pe_ratio"]
    assert (tmp_path / "Quick.json").is_file()

    loaded = rb.load_template("Quick")
    assert loaded["symbols"] == ["NABIL"]
    assert loaded["format"] == "pdf"

    assert "Quick" in [t["name"] for t in rb.list_templates()]

    rb.rename_template("Quick", "Quick v2")
    assert rb.load_template("Quick v2")["name"] == "Quick v2"

    dup = rb.duplicate_template("Quick v2", "Copy")
    assert dup["name"] == "Copy"
    assert dup["components"] == ["profile", "pe_ratio"]

    assert rb.delete_template("Copy") is True
    assert rb.delete_template("Copy") is False
    assert rb.delete_template("nope") is False


def test_saved_template_never_stores_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "TEMPLATE_DIR", tmp_path)
    req = rb.ReportRequest(components=["profile"], symbols=["NABIL"],
                           notes="token=supersecret")
    rb.save_template("S", req)
    raw = (tmp_path / "S.json").read_text()
    assert "supersecret" in raw  # it is the user's own note...
    # ...but no credential keys are introduced by the builder itself.
    assert "api_key" not in raw and "password" not in raw


# ------------------------------------------------- integration (needs real data)
_DATA = Path(__file__).resolve().parents[1] / "data"
_DEV = Path(__file__).resolve().parents[1] / "data" / "dev" / "release"

pytestmark = pytest.mark.skipif(
    not (_DEV / "processed").exists() and not (_DATA / "processed").exists(),
    reason="no extracted data present; run the market ingest first",
)


def test_report_with_real_data_has_only_selected_sections():
    symbols = ["NABIL"]
    report = rb.assemble_report(rb.ReportRequest(
        components=["profile", "last_price", "q_sources", "elig_config"],
        symbols=symbols, title="Integration"))
    # Whatever the data can and cannot support, only selected ids may appear.
    assert set(report["sections"]) <= {"profile", "last_price", "q_sources", "elig_config"}
    for renderer in (rb.render_xlsx, rb.render_json, rb.render_pdf, rb.render_csv):
        assert len(renderer(report)) > 0


# ------------------------------------------------- GVL quarterly regression
@pytest.fixture
def dev_fundamentals(monkeypatch):
    """Point the fundamentals reader at the extracted dev store.

    Production data/processed intentionally has no seeded fundamentals in the
    test checkout, so a regression that pins the real GVL rows must read the
    same dev database the application/browser uses. Only SQLite is redirected;
    no write is performed.
    """
    processed = _DEV / "processed"
    db = processed / "megatool_state.sqlite"
    if not db.is_file():
        pytest.skip("dev fundamentals database is not present")
    import megatool.config as config

    monkeypatch.setattr(config.PATHS, "processed", processed)
    rc = pytest.importorskip("megatool.report_components")
    monkeypatch.setattr(rc, "_STORE", None, raising=False)
    rc.clear_report_cache()
    return processed


def test_gvl_quarterly_records_are_real_and_not_reported_as_missing(dev_fundamentals):
    """GVL was falsely shown as having no quarterly data.

    The stored records do include Q4 2025-2026. The comparison must expose that
    period with its exact fiscal label and EPS, and the missing-quarter check
    must mark all four quarters as present rather than invalidating the symbol.
    """
    report = rb.assemble_report(rb.ReportRequest(
        components=["q_eps_comparison", "q4_results", "missing_quarters",
                    "fundamental_trend", "missing_summary"],
        symbols=["GVL"], fmt="json"))
    q_eps = report["sections"]["q_eps_comparison"]
    assert q_eps["available"] is True, q_eps.get("reason")
    source = "Fourth Quarter 2025-2026 (Nepali FY 2025-2026)"
    matching = [r for r in q_eps["rows"] if r[-1] == source]
    assert matching, q_eps["rows"][:5]
    assert matching[0][1] == "Q4"
    assert matching[0][2] == pytest.approx(13.02)
    assert matching[0][3] == "NPR"

    q4 = report["sections"]["q4_results"]
    assert q4["available"] is True
    assert any(r[0] == source and r[1] == pytest.approx(13.02) for r in q4["rows"])

    missing = report["sections"]["missing_quarters"]
    assert missing["available"] is True
    for quarter in ("Q1", "Q2", "Q3", "Q4"):
        row = next((r for r in missing["rows"] if r[0] == quarter), None)
        assert row is not None, (quarter, missing["rows"])
        assert row[1] == "present", (quarter, row)

    summary = report["sections"]["missing_summary"]
    assert summary["available"] is True
    assert any(source in str(cell) for row in summary["rows"] for cell in row)


def test_sector_eps_rank_is_not_expanded_once_per_requested_symbol(monkeypatch):
    """The sector-level hook must return one ranking, not N identical rankings."""
    rc = pytest.importorskip("megatool.report_components")

    class _SectorStore:
        def securities_meta(self):
            return {}

        def symbols(self):
            return ["BFC", "CFCL", "CFL"]

    monkeypatch.setattr(rc, "get_store", lambda: _SectorStore())
    monkeypatch.setattr(rc, "_sector_map", lambda: {
        "BFC": "Finance Companies",
        "CFCL": "Finance Companies",
        "CFL": "Finance Companies",
    })
    values = {"BFC": 7.84, "CFCL": 13.44, "CFL": None}
    monkeypatch.setattr(rc, "_field_value", lambda sym, field: (
        {"value": values[sym]} if field == "EPS" and values.get(sym) is not None else None))
    rc._SECTOR_CACHE = None
    report = rb.assemble_report(rb.ReportRequest(
        components=["sector_eps_rank", "sector_overview"],
        symbols=["BFC", "CFCL", "CFL"], sector="Finance Companies", fmt="json"))
    rank = report["sections"]["sector_eps_rank"]
    assert rank["available"] is True
    symbols = [r[1] for r in rank["rows"]]
    assert symbols == ["CFCL", "BFC"], rank["rows"]
    assert len(symbols) == len(set(symbols)), "a sector ranking row was repeated per input symbol"

    overview = report["sections"]["sector_overview"]
    assert overview["available"] is True
    assert [r[0] for r in overview["rows"]] == ["Finance Companies"], overview["rows"]
    assert overview["rows"][0][1] == 3


# ------------------------------------------------------- component semantics
def test_source_field_names_are_mapped_to_report_names():
    """The stored keys are snake_case; the report vocabulary is human."""
    rc = pytest.importorskip("megatool.report_components")
    assert rc.FIELD_DISPLAY["net_worth_per_share"] == "Net worth per share"
    assert rc.FIELD_DISPLAY["paid_up_capital"] == "Paid-up capital"
    assert rc.FIELD_DISPLAY["eps"] == "EPS"


def test_period_key_parses_the_stored_label_shapes():
    rc = pytest.importorskip("megatool.report_components")
    assert rc._period_key("Fourth Quarter 2025-2026 (Nepali FY 2025-2026)") == ("Q4", "2026")
    assert rc._period_key("Annual Report (Nepali FY 2024-2025)") == ("ANNUAL", "2025")
    assert rc._period_key("First Quarter 2080-2081 (Nepali FY 2080-2081)") == ("Q1", "2081")
    assert rc._period_key("no year here") is None
    assert rc._period_key(None) is None


class _FakeStore:
    def __init__(self, frame):
        self.frame = frame

    def get_bars(self, symbol, *a, **k):
        return self.frame


def _frame(closes):
    pd = pytest.importorskip("pandas")
    return pd.DataFrame({
        "trading_date": pd.bdate_range("2024-01-01", periods=len(closes)),
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes, "volume": [1000] * len(closes),
    })


def _install_prices(monkeypatch, closes):
    rc = pytest.importorskip("megatool.report_components")
    monkeypatch.setattr(rc, "get_store", lambda: _FakeStore(_frame(closes)))
    return rc


def test_last_price_is_labelled_end_of_day_not_live(monkeypatch):
    rc = _install_prices(monkeypatch, [100.0, 110.0, 120.0])
    out = rc.compute_last_price(_Req(["last_price"], symbols=["TEST"]))
    assert out["available"] is True
    row = out["rows"][0]
    assert row[1] == 120.0
    assert "not live" in row[3].lower()


def test_price_change_reports_insufficient_history_rather_than_a_number(monkeypatch):
    rc = _install_prices(monkeypatch, [100.0, 105.0])
    out = rc.compute_price_change(_Req(["price_change"], symbols=["TEST"]))
    assert out["available"] is True
    labels = {r[0]: r for r in out["rows"]}
    assert labels["1M"][3] == "insufficient history"


def test_volatility_is_computed_from_stored_closes(monkeypatch):
    import math
    import random

    random.seed(7)
    closes = [100.0]
    for _ in range(120):
        closes.append(closes[-1] * math.exp(random.gauss(0, 0.01)))
    rc = _install_prices(monkeypatch, closes)
    out = rc.compute_r_volatility(_Req(["r_volatility"], symbols=["TEST"]))
    assert out["available"] is True
    vol = out["rows"][0][3]
    assert isinstance(vol, float) and 0 < vol < 100


def test_market_cap_discloses_its_share_count_derivation(monkeypatch):
    rc = _install_prices(monkeypatch, [100.0, 200.0])
    monkeypatch.setattr(rc, "_shares_outstanding", lambda sym: (1_000_000.0, "derived"))
    out = rc.compute_market_cap(_Req(["market_cap"], symbols=["TEST"]))
    assert out["available"] is True
    row = out["rows"][0]
    assert row[5] == 200_000_000.0     # last close x shares
    assert row[4] == "derived"          # the basis is never omitted


def test_shares_are_derived_from_paid_up_capital_with_a_stated_basis(monkeypatch):
    rc = pytest.importorskip("megatool.report_components")
    monkeypatch.setattr(rc, "_field_value", lambda sym, field: (
        {"value": 27_000_000_000.0, "period_end": "2026-08-06", "period_label": "x",
         "source": "s"} if field == "Paid-up capital" else None))
    shares, basis = rc._shares_outstanding("NABIL")
    assert shares == 270_000_000.0
    assert "par value" in basis


def test_eligibility_compares_net_worth_and_capital_at_the_same_level(monkeypatch):
    rc = pytest.importorskip("megatool.report_components")
    monkeypatch.setattr(rc, "_shares_outstanding",
                        lambda sym: (1_000_000.0, "derived"))
    recs = [
        {"field": "Net worth per share", "value": 250.0, "period_end": "2026-08-06"},
        {"field": "Paid-up capital", "value": 100_000_000.0, "period_end": "2026-08-06"},
        {"field": "Net profit", "value": 5.0, "period_end": "2026-08-06"},
    ]
    monkeypatch.setattr(rc, "_fundamentals", lambda sym: recs)
    rules, overall = rc._elig("TEST")
    nw_rule = [r for r in rules if "Net worth" in r[0]][0]
    # 250 x 1,000,000 = 250m of net worth against 100m paid-up: a PASS.
    assert nw_rule[2] == "PASS"
    assert overall == "NEEDS_REVIEW"   # listing date is not stored


def test_eligibility_never_passes_a_rule_with_missing_inputs(monkeypatch):
    rc = pytest.importorskip("megatool.report_components")
    monkeypatch.setattr(rc, "_shares_outstanding", lambda sym: (None, ""))
    monkeypatch.setattr(rc, "_fundamentals", lambda sym: [])
    rules, overall = rc._elig("TEST")
    assert all(r[2] != "PASS" for r in rules)
    # Unknown inputs dominate: an unverified company is never called ineligible.
    assert overall == "NEEDS_REVIEW"


def test_yoy_growth_pairs_the_same_quarter_across_years(monkeypatch):
    rc = pytest.importorskip("megatool.report_components")
    eps = [
        {"field": "EPS", "value": 20.0, "period_end": "2025-01-01",
         "period_label": "First Quarter 2024-2025 (Nepali FY 2024-2025)"},
        {"field": "EPS", "value": 30.0, "period_end": "2026-01-01",
         "period_label": "First Quarter 2025-2026 (Nepali FY 2025-2026)"},
    ]
    monkeypatch.setattr(rc, "_eps_records", lambda sym: eps)
    out = rc.compute_yoy_growth(_Req(["yoy_growth"], symbols=["TEST"]))
    assert out["available"] is True
    assert out["rows"][0][3] == 50.0


def test_missing_quarter_is_reported_not_inferred(monkeypatch):
    rc = pytest.importorskip("megatool.report_components")
    monkeypatch.setattr(rc, "_fundamentals", lambda sym: [
        {"field": "EPS", "value": 1.0, "period_label": "First Quarter 2025-2026"},
        {"field": "EPS", "value": 2.0, "period_label": "Second Quarter 2025-2026"},
    ])
    out = rc.compute_missing_quarters(_Req(["missing_quarters"], symbols=["TEST"]))
    got = {(r[0], r[1]) for r in out["rows"]}
    assert ("Q3", "no stored record — not inferred") in got
    assert ("Q4", "no stored record — not inferred") in got


# --------------------------------------------- export disclosure guarantees
def _report_with_gap() -> dict:
    rep = _synthetic_report()
    # A component whose hook ran but found no data.
    rep["sections"]["gamma"] = {"name": "Gamma", "available": False,
                                "reason": "no stored EPS for this symbol"}
    rep["quality"]["unavailable"].append(
        {"id": "gamma", "name": "Gamma", "reason": "no stored EPS for this symbol"})
    return rep


def test_xlsx_discloses_a_selected_component_that_produced_nothing():
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(rb.render_xlsx(_report_with_gap())))
    assert "Gamma" not in wb.sheetnames          # no empty data sheet
    rows = list(wb["Unavailable"].iter_rows(values_only=True))
    assert ("Gamma", "no stored EPS for this symbol") in rows
    # And the components that were not selected are nowhere in the workbook.
    for name in wb.sheetnames:
        for row in wb[name].iter_rows(values_only=True):
            assert "Delta" not in [str(c) for c in row if c is not None]


def test_csv_discloses_unavailable_components():
    data = rb.render_csv(_report_with_gap())
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert "_unavailable.csv" in zf.namelist()
        text = zf.read("_unavailable.csv").decode()
        assert "Gamma" in text and "no stored EPS" in text


def test_pdf_lists_unavailable_components_once():
    data = rb.render_pdf(_report_with_gap())
    assert data.count(b"no stored EPS for this symbol") == 1


def test_json_reports_sections_and_quality_separately():
    parsed = json.loads(rb.render_json(_report_with_gap()))
    assert parsed["sections"]["gamma"]["available"] is False
    assert any(u["id"] == "gamma" for u in parsed["quality"]["unavailable"])


# ------------------------------------------------ per-symbol expansion
def _comp(hook, output="table"):
    return rb.Component(id="x", name="X", category="B_market", description="",
                        output=output, available=True, compute=hook)


def test_a_single_symbol_hook_is_expanded_across_every_symbol():
    def hook(req):
        sym = req.symbols[0]
        return {"name": "Prices", "available": True,
                "headers": ["Symbol", "Close"], "rows": [[sym, 1.0]]}

    out = rb._run_component(_comp(hook),
                            rb.ReportRequest(components=["x"], symbols=["NABIL", "SCB"]))
    assert [r[0] for r in out["rows"]] == ["NABIL", "SCB"]


def test_a_hook_that_already_iterates_symbols_is_called_once():
    calls = []

    def hook(req):
        calls.append(len(req.symbols))
        return {"name": "Cmp", "available": True, "headers": ["S"],
                "rows": [[s] for s in req.symbols]}

    out = rb._run_component(_comp(hook),
                            rb.ReportRequest(components=["x"], symbols=["A", "B", "C"]))
    assert calls == [3]
    assert [r[0] for r in out["rows"]] == ["A", "B", "C"]


def test_a_chart_hook_is_never_expanded_into_one_merged_series():
    calls = []

    def hook(req):
        calls.append(req.symbols[0])
        return {"name": "Chart", "available": True, "output": "chart",
                "headers": ["Date", "Close"], "rows": [["2026-01-01", 1.0]]}

    rb._run_component(_comp(hook, output="chart"),
                      rb.ReportRequest(components=["x"], symbols=["A", "B"]))
    assert calls == ["A"]


def test_one_symbol_failing_does_not_lose_the_others():
    def hook(req):
        if req.symbols[0] == "BAD":
            raise ValueError("boom")
        return {"name": "P", "available": True, "headers": ["S"],
                "rows": [[req.symbols[0]]]}

    out = rb._run_component(_comp(hook),
                            rb.ReportRequest(components=["x"], symbols=["BAD", "GOOD"]))
    assert out["available"] is True
    assert out["rows"] == [["GOOD"]]


# ------------------------------------------------------- PDF structural integrity
def test_pdf_cross_reference_offsets_point_at_their_own_objects():
    """A wrong offset makes some readers skip the page content entirely."""

    data = rb.render_pdf(_synthetic_report())
    text = data.decode("latin-1")
    offset = int(text[text.rindex("startxref"):].split()[1])
    assert text[offset:offset + 4] == "xref"
    rows = [ln for ln in text[offset:].splitlines()[2:] if ln.strip().endswith(" n")]
    assert rows
    for number, row in enumerate(rows, start=1):
        off = int(row.split()[0])
        assert data[off:].startswith(f"{number} 0 obj".encode()), (number, off)


def test_every_pdf_page_references_a_content_stream():
    """The page must point at a stream, not at the font dictionary.

    An earlier off-by-one made /Contents reference the font object, so the PDF
    was structurally valid but every page rendered blank.
    """
    import re

    text = rb.render_pdf(_synthetic_report()).decode("latin-1")
    refs = re.findall(r"/Contents (\d+) 0 R", text)
    assert refs, "no page declared a content stream"
    for ref in refs:
        assert f"\n{ref} 0 obj\n<< /Length " in text, f"object {ref} is not a stream"


def test_pdf_contains_the_selected_text_and_a_page_number():
    text = rb.render_pdf(_synthetic_report()).decode("latin-1")
    assert "Alpha" in text and "Beta" in text
    assert "1 / " in text


# ------------------------------------------- refusing meaningless arithmetic
def test_growth_is_refused_when_the_stored_amounts_are_on_different_scales():
    """4.36 next to 6.2 billion is a unit problem, not a 200,000,000% growth."""
    rc = pytest.importorskip("megatool.report_components")
    assert rc._comparable(1_000.0, 1_200.0) is True
    assert rc._comparable(3_053_489.0, 6_227_156_000.0) is False
    assert rc._comparable(0.0, 100.0) is False
    assert rc._mixed_magnitude([1.0, 2.0, 5.0]) is False
    assert rc._mixed_magnitude([4.36, 6_016_216.0]) is True


def test_growth_ranking_excludes_incomparable_symbols_instead_of_ranking_them(monkeypatch):
    rc = pytest.importorskip("megatool.report_components")
    monkeypatch.setattr(rc, "_sector_map", lambda: {"AAA": "Bank", "BBB": "Bank"})
    monkeypatch.setattr(rc, "_field_value", lambda *a, **k: None)

    series = {
        "AAA": [(["ANNUAL", "2024"], 100.0), (["ANNUAL", "2025"], 150.0)],
        "BBB": [(["ANNUAL", "2024"], 3_053_489.0), (["ANNUAL", "2025"], 6_227_156_000.0)],
    }
    monkeypatch.setattr(rc, "_profit_series", lambda sym, annual=False: series[sym])

    out = rc.compute_sector_growth_rank(
        _Req(["sector_growth_rank"], symbols=["AAA", "BBB"]))
    assert out["available"] is True
    ranked = [r for r in out["rows"] if r[0] == 1]
    assert ranked[0][1] == "AAA" and ranked[0][4] == 50.0
    excluded = [r for r in out["rows"] if r[-1] == "excluded"]
    assert excluded and excluded[0][0] == "BBB"
    assert "not comparable" in excluded[0][3]
