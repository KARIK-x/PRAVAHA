"""Opt-in browser regression tests for the reference-driven visualisation pass,
the shared scanner/algorithm tool-information panel and the compact indicator
selector row.

Everything under test is DOM/SVG state produced by ``web/static/viz.js`` and
``web/static/app.js`` — it is not reachable from the Python API — so the
assertions run against a real browser through ``playwright-cli``.

They are OPT-IN (like ``tests/test_browser_objects_manager.py``): the module is
skipped unless ``MEGATOOL_BROWSER_TESTS=1`` and a dev server is answering on
:10000. Run with::

    MEGATOOL_BROWSER_TESTS=1 .venv/bin/python -m pytest -q tests/test_browser_viz_toolinfo.py

The one mutating case (adding an indicator to a chart) snapshots and restores
the persisted per-symbol config so a run never clobbers a user's setup.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request

import pytest

BASE = os.environ.get("MEGATOOL_BROWSER_BASE", "http://127.0.0.1:10000/")
SESSION = "mtviztest"
SYM = "NABIL"

pytestmark = pytest.mark.skipif(
    os.environ.get("MEGATOOL_BROWSER_TESTS") != "1",
    reason="browser tests are opt-in; set MEGATOOL_BROWSER_TESTS=1 with a live dev server on :10000",
)


def _server_up() -> bool:
    try:
        with urllib.request.urlopen(BASE, timeout=2) as r:  # noqa: S310 (local dev URL)
            return r.status == 200
    except Exception:
        return False


def _pw(*args: str, timeout: int = 180) -> str:
    p = subprocess.run(
        ["playwright-cli", f"-s={SESSION}", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return (p.stdout or "") + (p.stderr or "")


def _eval(js: str):
    out = _pw("eval", js)
    m = re.search(r"^### Result\s*\n(.+)$", out, re.M)
    if not m:
        raise AssertionError(f"playwright-cli eval produced no result:\n{out}")
    raw = m.group(1).strip()
    try:
        val = json.loads(raw)
    except Exception:
        val = raw
    if isinstance(val, str):
        with contextlib.suppress(Exception):
            val = json.loads(val)
    return val


def _goto() -> None:
    _pw("goto", BASE)
    time.sleep(5)


@pytest.fixture(scope="module", autouse=True)
def _browser():
    if shutil.which("playwright-cli") is None:
        pytest.skip("playwright-cli is not on PATH")
    if not _server_up():
        pytest.skip(f"no dev server at {BASE}")
    _pw("close")
    _pw("open", BASE)
    time.sleep(5)
    yield
    _pw("close")


def test_overview_visualisations_render():
    _goto()
    res = _eval(
        "(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));"
        "showView('overview');if(typeof viewShown==='function')viewShown('overview');"
        "await sleep(7000);"
        "const g=document.querySelector('#ov-gauge svg');"
        "return JSON.stringify({"
        "gauge:!!g,gaugeAria:g?g.getAttribute('aria-label'):null,"
        "sector:!!document.querySelector('#ov-sector-chart svg'),"
        "sectorBars:document.querySelectorAll('#ov-sector-chart rect').length,"
        "donut:!!document.querySelector('#ov-sector-donut svg'),"
        "donutSlices:document.querySelectorAll('#ov-sector-donut path').length,"
        "fundmap:!!document.querySelector('#ov-fundmap svg'),"
        "fundmapDots:document.querySelectorAll('#ov-fundmap circle').length"
        "});})()"
    )
    assert res["gauge"], f"market barometer gauge did not render: {res}"
    assert res["gaugeAria"] and "barometer" in res["gaugeAria"].lower(), (
        f"gauge needs an accessible label: {res}"
    )
    assert res["sector"] and res["sectorBars"] > 0, f"sector performance bars missing: {res}"
    assert res["donut"] and res["donutSlices"] > 0, f"turnover donut missing: {res}"
    assert res["fundmap"] and res["fundmapDots"] > 0, f"fundamental map scatter missing: {res}"


def test_breadth_chart_renders_for_every_metric():
    _goto()
    res = _eval(
        "(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));"
        "showView('breadth');if(typeof viewShown==='function')viewShown('breadth');"
        "document.querySelector('#bh-start').value='2022-01-01';"
        "document.querySelector('#bh-load').click();await sleep(6000);"
        "const out={};const sel=document.querySelector('#bh-chart-metric');"
        "for(const m of ['net_new_highs','ad_ratio','ad_line','ad_volume_line','arms_index','pct_above_sma_50','pct_above_sma_200']){"
        "sel.value=m;sel.dispatchEvent(new Event('change'));await sleep(400);"
        "const svg=document.querySelector('#bh-chart svg');"
        "out[m]=!!svg?{paths:svg.querySelectorAll('path').length,aria:svg.getAttribute('aria-label')}:null;}"
        "return JSON.stringify(out);})()"
    )
    for metric in (
        "net_new_highs",
        "ad_ratio",
        "ad_line",
        "ad_volume_line",
        "arms_index",
        "pct_above_sma_50",
        "pct_above_sma_200",
    ):
        assert res.get(metric), f"breadth chart did not render for {metric}: {res}"
        assert res[metric]["paths"] >= 1, f"breadth chart for {metric} has no drawn path: {res}"


def test_seasonality_charts_render():
    _goto()
    res = _eval(
        "(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));"
        "showView('sea');if(typeof viewShown==='function')viewShown('sea');"
        "document.querySelector('#sea-symbol').value='" + SYM + "';"
        "document.querySelector('#sea-load').click();await sleep(6000);"
        "return JSON.stringify({"
        "months:!!document.querySelector('#sea-chart-months svg'),"
        "monthBars:document.querySelectorAll('#sea-chart-months rect').length,"
        "weekdays:!!document.querySelector('#sea-chart-weekdays svg'),"
        "quarters:!!document.querySelector('#sea-chart-quarters svg')"
        "});})()"
    )
    assert res["months"] and res["monthBars"] >= 12, f"month-of-year bars missing: {res}"
    assert res["weekdays"], f"weekday bars missing: {res}"
    assert res["quarters"], f"quarter bars missing: {res}"


def test_tool_info_panel_opens_with_per_entry_content():
    _goto()
    res = _eval(
        "(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));"
        "const out={};"
        "await window.__mtToolInfo.openToolInfo('scan.oversold_rsi');"
        "const b=document.querySelector('#tool-info-body');"
        "out.scanner={hidden:document.querySelector('#tool-info').hidden,"
        "sections:b.querySelectorAll('.ti-section').length,"
        "purpose:(b.querySelector('.ti-section p')||{}).textContent,"
        "formula:(b.querySelector('.ti-formula')||{}).textContent};"
        "await window.__mtToolInfo.openToolInfo('algo.sma_cross');"
        "const b2=document.querySelector('#tool-info-body');"
        "out.algo={sections:b2.querySelectorAll('.ti-section').length,"
        "purpose:(b2.querySelector('.ti-section p')||{}).textContent,"
        "formula:(b2.querySelector('.ti-formula')||{}).textContent};"
        "return JSON.stringify(out);})()"
    )
    assert res["scanner"]["hidden"] is False, "tool-info modal should be visible"
    assert res["scanner"]["sections"] >= 8, f"scanner panel missing sections: {res}"
    assert "RSI below 30" in (res["scanner"]["purpose"] or ""), (
        f"scanner purpose must be the entry's own description: {res}"
    )
    assert "rsi < 30" in (res["scanner"]["formula"] or ""), (
        f"scanner formula must be the implemented rule: {res}"
    )
    assert res["algo"]["sections"] >= 8, f"algorithm panel missing sections: {res}"
    assert "SMA(fast)" in (res["algo"]["formula"] or ""), (
        f"algorithm formula must be the implemented rule: {res}"
    )
    assert res["scanner"]["purpose"] != res["algo"]["purpose"], (
        "panels must not share one generic description"
    )


def test_tool_info_handles_missing_and_long_metadata():
    _goto()
    res = _eval(
        "(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));"
        "const out={};"
        "await window.__mtToolInfo.openToolInfo('scan.this_does_not_exist');"
        "out.missing=(document.querySelector('#tool-info-body').textContent||'');"
        "let threw=false;let html='';"
        "try{html=window.__mtToolInfo.toolInfoHtml({id:'x',kind:'scanner',category:'c',"
        "name:'N',description:Array(400).fill('longword').join(' '),formula:'a',params:{},tags:[],"
        "limitations:[],data_requirements:[]});}catch(e){threw=true;}"
        "out.emptyThrew=threw;out.emptyLong=html.length>2000;"
        "let t=false;try{window.__mtToolInfo.toolInfoHtml({});}catch(e){t=true;}"
        "out.bareThrew=t;"
        "return JSON.stringify(out);})()"
    )
    assert "could not load" in (res["missing"] or "").lower(), (
        f"missing tool must degrade gracefully: {res}"
    )
    assert res["emptyThrew"] is False, "toolInfoHtml must not throw on a sparse tool"
    assert res["bareThrew"] is False, "toolInfoHtml must not throw on an empty tool"
    assert res["emptyLong"], "toolInfoHtml must render a long description"


def test_indicator_selector_is_compact_and_informative():
    _goto()
    res = _eval(
        "(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));"
        "const K={L:'mt-chart-layers-',I:'mt-custom-inds-',D:'mt-drawings-'};"
        "const SNAP={};Object.keys(K).forEach(k=>{SNAP[k]=localStorage.getItem(K[k]+'"
        + SYM
        + "');});"
        "const restore=()=>{Object.keys(K).forEach(k=>{const v=SNAP[k];"
        "if(v===null)localStorage.removeItem(K[k]+'"
        + SYM
        + "');else localStorage.setItem(K[k]+'"
        + SYM
        + "',v);});};"
        "const out={};"
        "try{"
        "showView('charts');if(typeof viewShown==='function')viewShown('charts');"
        "document.querySelector('#symbol-input').value='"
        + SYM
        + "';await loadChart();await sleep(2500);"
        "await addToChartFromCatalog('sma',null);await sleep(500);"
        "const drawer=document.querySelector('#ind-drawer');if(drawer)drawer.hidden=false;"
        "await renderIndDrawer();await sleep(300);"
        "const row=document.querySelector('#ind-instances .ind-inst');"
        "out.hasInfo=!!row.querySelector('.ii-info');"
        "out.extraHiddenByDefault=row.querySelector('.ii-extra').hidden;"
        "out.name=row.querySelector('.ii-name').textContent.trim();"
        "row.querySelector('.ii-toggle').click();await sleep(300);"
        "out.extraShownAfterToggle=!document.querySelector('#ind-instances .ind-inst').querySelector('.ii-extra').hidden;"
        "document.querySelector('#ind-instances .ind-inst .ii-info').click();await sleep(1200);"
        "const pane=document.querySelector('#ind-info');"
        "out.infoOpen=pane?!pane.hidden:false;"
        "out.infoTitle=(document.querySelector('#ind-info-title')||{}).textContent||'';"
        "}finally{restore();}"
        "return JSON.stringify(out);})()"
    )
    assert res["hasInfo"], f"compact row must keep an ⓘ control: {res}"
    assert res["extraHiddenByDefault"], f"parameters must be hidden until expanded: {res}"
    assert res["extraShownAfterToggle"], f"⚙ must reveal parameters/actions: {res}"
    assert res["infoOpen"], f"ⓘ must open the indicator information pane: {res}"
    assert res["infoTitle"].strip(), f"indicator info pane needs a title: {res}"
