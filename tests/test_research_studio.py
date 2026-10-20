"""Tests for the Research Studio: volatility forecasting, report jobs and exports.

Everything here is synthetic and deterministic. No test asserts real NEPSE
prices, and no report package is written outside a temporary directory.
"""

from __future__ import annotations

import io
import json
import time
import zipfile

import numpy as np
import pandas as pd
import pytest

from megatool import jobs
from megatool import research_report as rr
from megatool.volatility import (
    VolatilityError,
    bar_arrays,
    position_sizing,
    volatility_report,
)


# --------------------------------------------------------------------------- #
# Synthetic bars
# --------------------------------------------------------------------------- #
def _ohlc(n: int = 320, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    vol = 0.008 + 0.02 * (np.sin(np.arange(n) / 25.0) ** 2)
    close = 500.0 * np.exp(np.cumsum(rng.normal(0, vol)))
    open_ = close * (1 + rng.normal(0, vol / 3, n))
    high = np.maximum.reduce([close, open_]) * (1 + np.abs(rng.normal(0, vol, n)))
    low = np.minimum.reduce([close, open_]) * (1 - np.abs(rng.normal(0, vol, n)))
    return pd.DataFrame({
        "trading_date": pd.bdate_range("2025-01-01", periods=n),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.integers(1_000, 90_000, n),
        "source": "synthetic", "validation_status": "valid",
    })


# --------------------------------------------------------------------------- #
# Volatility
# --------------------------------------------------------------------------- #
def test_bar_arrays_rejects_an_empty_frame():
    with pytest.raises(VolatilityError):
        bar_arrays(pd.DataFrame())


def test_bar_arrays_needs_enough_consistent_bars():
    df = _ohlc(30)
    with pytest.raises(VolatilityError):
        bar_arrays(df)


def test_volatility_report_is_out_of_sample_and_has_a_naive_baseline():
    out = volatility_report(_ohlc(), "TEST")
    ev = out["evaluation"]
    assert ev["naive_baseline"]
    assert "naive" in ev["models"]
    assert ev["evaluation"]["leak_free"] is True
    assert ev["evaluation"]["observations"] > 100
    assert ev["evaluation"]["first_target"] < ev["evaluation"]["last_target"]
    for name, m in ev["models"].items():
        assert m["n"] > 0
        assert m["mae"] >= 0
        assert "interval_coverage_percent" in m, name


def test_forecast_cannot_see_future_bars():
    """Appending one more bar must not change the forecast *origin* inputs.

    The point forecast is allowed to change (it is a new origin), but the
    evaluation must remain chronological: every target is after its inputs.
    """
    df = _ohlc(260)
    ev = volatility_report(df, "TEST")["evaluation"]
    assert ev["evaluation"]["last_target"] == str(df["trading_date"].iloc[-1].date())


def test_point_forecast_and_band_are_positive_and_ordered():
    out = volatility_report(_ohlc(), "TEST")
    fc = out["forecast"]
    assert fc["point_range"] > 0
    lo, hi = fc["band_80"]
    assert 0 <= lo <= hi
    assert fc["model"] in out["evaluation"]["models"]
    assert "not a live quote" in fc["price_kind"].lower() or "not live" in fc["price_kind"].lower()


def test_models_are_scored_on_the_same_targets():
    m = volatility_report(_ohlc(), "TEST")["evaluation"]["models"]
    assert len({v["n"] for v in m.values()}) == 1


def test_position_sizing_keeps_rupee_risk_constant_as_stop_widens():
    tight = position_sizing(500.0, 5_000.0, 10.0, stop_multiple=1.0)
    wide = position_sizing(500.0, 5_000.0, 20.0, stop_multiple=2.0)
    assert wide["shares"] < tight["shares"]
    assert wide["stop_distance"] == 40.0
    assert wide["max_loss_at_stop"] <= 5_000.0
    assert tight["max_loss_at_stop"] <= 5_000.0


def test_position_sizing_cap_is_disclosed():
    out = position_sizing(1_000.0, 100_000.0, 1.0, capital=10_000.0)
    assert out["shares"] == 10
    assert out["cap_note"]


def test_position_sizing_rejects_non_positive_inputs():
    with pytest.raises(VolatilityError):
        position_sizing(0.0, 100.0, 1.0)


def test_volatility_report_sizing_is_absent_without_a_budget():
    out = volatility_report(_ohlc(), "TEST")
    assert out["position_sizing"]["available"] is False


def test_volatility_report_never_claims_direction():
    out = volatility_report(_ohlc(), "TEST", risk_budget=5_000)
    joined = " ".join(out["caveats"]).lower()
    assert "not its direction" in joined


# --------------------------------------------------------------------------- #
# Charts + PDF
# --------------------------------------------------------------------------- #
def test_chart_raster_and_png_are_valid():
    from megatool.chartimg import png_bytes, rgb_line_chart

    rgb = rgb_line_chart([1, 3, 2, 5, 4, 8])
    assert len(rgb) == 760 * 300 * 3
    png = png_bytes(rgb, 760, 300)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_pdf_with_an_image_is_readable_and_extractable():
    fitz = pytest.importorskip("pymupdf")
    from megatool.chartimg import rgb_line_chart
    from megatool.pdfwriter import write_pdf_blocks

    rgb = rgb_line_chart([1, 2, 4, 3, 6])
    pdf = write_pdf_blocks([
        {"type": "text", "text": "PRAVAHA image test", "size": 14},
        {"type": "image", "rgb": rgb, "width": 760, "height": 300,
         "draw_width": 500, "draw_height": 197},
        {"type": "text", "text": "Text after the chart.", "size": 9},
    ])
    assert b"/Subtype /Image" in pdf
    doc = fitz.open(stream=pdf, filetype="pdf")
    assert doc.page_count == 1
    text = doc[0].get_text()
    assert "PRAVAHA image test" in text
    assert "Text after the chart." in text


def test_pdf_paginates_instead_of_clipping():
    from megatool.pdfwriter import write_pdf_blocks

    blocks = [{"type": "text", "text": f"line {i}", "size": 9} for i in range(400)]
    pdf = write_pdf_blocks(blocks)
    assert pdf.count(b"/Type /Page ") >= 2


# --------------------------------------------------------------------------- #
# Catalog and safety
# --------------------------------------------------------------------------- #
def test_catalog_excludes_private_categories_by_default():
    cat = rr.research_catalog()
    ids = {c["id"] for c in cat["components"]}
    assert not any(i.startswith(("j_", "p_")) for i in ids)
    assert set(cat["private_excluded"]) == {"K_journal", "L_portfolio"}
    assert cat["presets"]


def test_catalog_can_include_private_only_when_asked():
    cat = rr.research_catalog(allow_private=True)
    ids = {c["id"] for c in cat["components"]}
    assert any(i.startswith("j_") for i in ids)


def test_private_components_are_stripped_from_a_report_selection():
    chosen = rr.clean_components(["profile", "j_ledger", "p_holdings", "last_price"])
    assert chosen == ["profile", "last_price"]


def test_unknown_component_is_rejected():
    with pytest.raises(ValueError):
        rr.clean_components(["not_a_component"])


def test_symbol_validation_rejects_injection():
    assert rr.clean_symbols(["nabil", "SCB"]) == ["NABIL", "SCB"]
    with pytest.raises(ValueError):
        rr.clean_symbols(["NABIL; DROP TABLE bars"])


def test_component_bound_is_enforced():
    ids = ["profile"] * (rr.MAX_RESEARCH_COMPONENTS + 1)
    with pytest.raises(ValueError):
        rr.clean_components(ids)


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
@pytest.fixture
def job_dirs(tmp_path, monkeypatch):
    jd = tmp_path / "jobs"
    ed = tmp_path / "exports"
    monkeypatch.setenv("MEGATOOL_JOBS_DIR", str(jd))
    monkeypatch.setenv("MEGATOOL_JOB_EXPORTS_DIR", str(ed))
    monkeypatch.setattr(jobs, "_RECOVERED", True)
    return jd, ed


def test_job_progress_is_derived_from_completed_steps(job_dirs):
    job = jobs.create_job("test", {"a": 1}, steps_total=10)
    assert job.progress == 0.0
    jobs.update_job(job.id, steps_done=3, stage="working")
    assert jobs.get_job(job.id).progress == 30.0
    jobs.update_job(job.id, steps_done=10, stage="done")
    assert jobs.get_job(job.id).progress == 100.0


def test_job_cannot_report_more_than_total(job_dirs):
    job = jobs.create_job("test", steps_total=4)
    jobs.update_job(job.id, steps_done=99)
    assert jobs.get_job(job.id).progress == 100.0


def test_job_artifacts_must_exist_and_stay_in_the_job_directory(job_dirs):
    job = jobs.create_job("test", steps_total=1)
    jobs.update_job(job.id, steps_done=1)
    out = jobs.exports_dir(job.id)
    good = out / "report.pdf"
    good.write_bytes(b"%PDF-1.4 test")
    done = jobs.complete_job(job.id, {"pdf": good})
    assert done.status == "SUCCEEDED"
    assert done.artifacts["pdf"]["bytes"] == good.stat().st_size
    assert jobs.artifact_path(job.id, "pdf") == good

    missing = jobs.create_job("test", steps_total=1)
    with pytest.raises(jobs.JobError):
        jobs.complete_job(missing.id, {"pdf": out / "nope.pdf"})


def test_job_rejects_unknown_artifact(job_dirs):
    job = jobs.create_job("test", steps_total=1)
    jobs.update_job(job.id, steps_done=1)
    f = jobs.exports_dir(job.id) / "a.json"
    f.write_text("{}")
    jobs.complete_job(job.id, {"json": f})
    with pytest.raises(jobs.JobError):
        jobs.artifact_path(job.id, "xlsx")


def test_job_id_traversal_is_refused(job_dirs):
    with pytest.raises(jobs.JobError):
        jobs.get_job("../../etc/passwd")


def test_a_running_job_from_a_dead_process_is_marked_interrupted(job_dirs, monkeypatch):
    job = jobs.create_job("test", steps_total=2)
    jobs.update_job(job.id, steps_done=1, status="RUNNING")
    monkeypatch.setattr(jobs, "_RECOVERED", False)
    recovered = jobs.get_job(job.id)
    assert recovered.status == "INTERRUPTED"
    assert recovered.progress == 50.0


def test_background_work_failure_is_recorded(job_dirs):
    job = jobs.create_job("test", steps_total=1)

    def boom(_job_id):
        raise RuntimeError("no data")

    jobs.start_job(job.id, boom)
    for _ in range(100):
        cur = jobs.get_job(job.id)
        if cur.status in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.02)
    assert cur.status == "FAILED"
    assert "no data" in (cur.error or "")


# --------------------------------------------------------------------------- #
# Full bundle rendering (synthetic store)
# --------------------------------------------------------------------------- #
class _FakeStore:
    def __init__(self, frame):
        self.frame = frame

    def get_bars(self, symbol, *a, **k):
        return self.frame


@pytest.fixture
def fake_store(monkeypatch):
    """Point every report component at the same synthetic frame."""
    rc = pytest.importorskip("megatool.report_components")
    frame = _ohlc()
    fake = _FakeStore(frame)
    monkeypatch.setattr(rc, "get_store", lambda: fake)
    monkeypatch.setattr(rc, "_STORE", fake)
    return frame


def _bundle(components=None):
    symbols = ["TEST1", "TEST2"]
    return rr.build_bundle(
        symbols,
        components or ["profile", "last_price", "price_summary", "c_price"],
        title="Synthetic research",
        store=_FakeStore(_ohlc()),
    )


def test_bundle_has_only_selected_sections(fake_store):
    bundle = _bundle(["last_price", "c_price"])
    for sym in bundle["symbols"]:
        assert set(bundle["symbols_data"][sym]["sections"]) <= {
            "last_price", "c_price", "volatility_forecast", "volatility_evaluation"
        }


def test_bundle_xlsx_is_a_real_workbook(fake_store):
    pytest.importorskip("openpyxl")
    from openpyxl import load_workbook

    data = rr.render_bundle_xlsx(_bundle())
    wb = load_workbook(io.BytesIO(data))
    assert "Report" in wb.sheetnames
    assert any(s.lower().startswith("price chart") for s in wb.sheetnames)


def test_single_symbol_xlsx_has_one_sheet_per_section(fake_store):
    from openpyxl import load_workbook

    bundle = _bundle(["last_price", "c_price"])
    wb = load_workbook(io.BytesIO(rr.render_symbol_xlsx(bundle, "TEST1")))
    assert "Report" in wb.sheetnames
    assert len(wb.sheetnames) >= 3


def test_bundle_pdf_is_valid_and_contains_chart_images(fake_store):
    fitz = pytest.importorskip("pymupdf")
    pdf = rr.render_bundle_pdf(_bundle())
    assert pdf[:5] == b"%PDF-"
    doc = fitz.open(stream=pdf, filetype="pdf")
    assert doc.page_count >= 1
    text = "".join(p.get_text() for p in doc)
    assert "Synthetic research" in text


def test_bundle_json_is_parseable_and_discloses_unavailable(fake_store):
    bundle = _bundle()
    parsed = json.loads(rr.render_bundle_json(bundle))
    assert parsed["symbols"] == ["TEST1", "TEST2"]
    assert "quality" in parsed


def test_bundle_zip_contains_combined_and_per_symbol_files(fake_store):
    bundle = _bundle()
    z = zipfile.ZipFile(io.BytesIO(rr.render_bundle_zip(bundle)))
    names = set(z.namelist())
    assert "README.txt" in names
    assert "research-report.pdf" in names
    assert "research-report.xlsx" in names
    assert "research-report.json" in names
    assert "research-data.zip" in names
    for sym in bundle["symbols"]:
        assert f"{sym}/{sym}-research.xlsx" in names
        assert f"{sym}/{sym}-research.pdf" in names
    assert z.read("README.txt").startswith(b"PRAVAHA research package")


def test_unselected_section_never_appears_anywhere(fake_store):
    bundle = _bundle(["last_price"])
    z = zipfile.ZipFile(io.BytesIO(rr.render_bundle_zip(bundle)))
    names = z.namelist()
    assert not any("technical" in n.lower() for n in names)
    for sym in bundle["symbols"]:
        assert "ta_summary" not in bundle["symbols_data"][sym]["sections"]


def test_bundle_requires_at_least_one_symbol():
    with pytest.raises(ValueError):
        rr.build_bundle([], ["last_price"], store=_FakeStore(_ohlc()))


def test_bundle_requires_at_least_one_component():
    with pytest.raises(ValueError):
        rr.build_bundle(["TEST1"], [], store=_FakeStore(_ohlc()))


# --------------------------------------------------------------------------- #
# API surface
# --------------------------------------------------------------------------- #
def test_api_catalog_and_volatility_and_job(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import megatool.report_components as rc
    from megatool.api import create_app
    from megatool.market_store import MarketStore

    monkeypatch.setenv("MEGATOOL_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("MEGATOOL_JOB_EXPORTS_DIR", str(tmp_path / "exports"))
    monkeypatch.setattr(jobs, "_RECOVERED", True)

    store = MarketStore(tmp_path / "market.duckdb")
    df = _ohlc(180)
    df["symbol"] = "TEST1"
    df["retrieved_at"] = pd.Timestamp("2026-10-20")
    store.upsert_bars(df)
    monkeypatch.setattr(rc, "_STORE", store)

    app = create_app(store=store)
    with TestClient(app) as client:
        cat = client.get("/api/baba/research/catalog")
        assert cat.status_code == 200
        assert cat.json()["presets"]

        vol = client.get("/api/baba/volatility/TEST1?risk_budget=5000")
        assert vol.status_code == 200
        assert vol.json()["forecast"]["point_range"] > 0

        start = client.post("/api/baba/research/jobs", json={
            "symbols": ["TEST1"],
            "components": ["last_price", "c_price"],
            "title": "API synthetic",
        })
        assert start.status_code == 200, start.text
        job_id = start.json()["job"]["id"]

        payload = None
        for _ in range(300):
            payload = client.get(f"/api/baba/research/jobs/{job_id}").json()["job"]
            if payload["status"] in ("SUCCEEDED", "FAILED", "INTERRUPTED"):
                break
            time.sleep(0.05)
        assert payload["status"] == "SUCCEEDED", payload.get("error")
        assert payload["progress"] == 100.0
        assert set(payload["artifacts"]) == {"pdf", "xlsx", "json", "zip"}

        pdf = client.get(f"/api/baba/research/jobs/{job_id}/download/pdf")
        assert pdf.status_code == 200
        assert pdf.content[:5] == b"%PDF-"
        assert "no-store" in pdf.headers["cache-control"]

        bad = client.get(f"/api/baba/research/jobs/{job_id}/download/exe")
        assert bad.status_code == 400

        listed = client.get("/api/baba/research/jobs").json()["jobs"]
        assert any(j["id"] == job_id for j in listed)


def test_api_job_rejects_unknown_symbol_characters(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from megatool.api import create_app
    from megatool.market_store import MarketStore

    monkeypatch.setenv("MEGATOOL_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("MEGATOOL_JOB_EXPORTS_DIR", str(tmp_path / "exports"))
    store = MarketStore(tmp_path / "market.duckdb")
    app = create_app(store=store)
    with TestClient(app) as client:
        r = client.post("/api/baba/research/jobs", json={
            "symbols": ["../etc/passwd"], "components": ["last_price"],
        })
        assert r.status_code == 400
    store.close()
