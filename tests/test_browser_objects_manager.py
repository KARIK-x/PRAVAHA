"""Browser-driven regression tests for the Chart Objects manager, detector-marker
persistence and Fibonacci viewport preservation.

Why these live in the pytest suite
----------------------------------
The behaviour under test is DOM/Lightweight-Charts state (which rows the manager
reports, what Hide/Remove actually do to the canvas, whether the visible time
window moves when a Fibonacci tool or layer activates). None of that is reachable
from the Python API, so the assertions are made against a real browser through
``playwright-cli``.

They are OPT-IN because they need a live dev server and a browser: the module is
skipped unless ``MEGATOOL_BROWSER_TESTS=1``, and it also skips itself if the
server or ``playwright-cli`` is unavailable. Run it with::

    MEGATOOL_BROWSER_TESTS=1 .venv/bin/python -m pytest -q tests/test_browser_objects_manager.py

Every mutating test snapshots and restores the persisted per-symbol config
(layers, catalog indicators, drawings) so a run never clobbers a user's setup.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.request

import pytest

BASE = os.environ.get("MEGATOOL_BROWSER_BASE", "http://127.0.0.1:10000/")
SESSION = "mtobjtest"
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


def _pw(*args: str, timeout: int = 120) -> str:
    p = subprocess.run(
        ["playwright-cli", f"-s={SESSION}", *args],
        capture_output=True, text=True, timeout=timeout,
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
        try:
            val = json.loads(val)
        except Exception:
            pass
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


# JavaScript shared by every case: load the chart then hand back control.
_SETUP = (
    "showView('charts');"
    "document.querySelector('#symbol-input').value='" + SYM + "';"
    "document.querySelector('#range').value='250';"
    "await loadChart();await sleep(2000);"
)

# Snapshot the per-symbol persisted config, expose restore(), so a mutating test
# leaves the profile exactly as it found it.
_SNAP = (
    "const K={L:'mt-chart-layers-',I:'mt-custom-inds-',D:'mt-drawings-'};"
    "const SNAP={};Object.keys(K).forEach(k=>{SNAP[k]=localStorage.getItem(K[k]+'" + SYM + "');});"
    "const restore=()=>{Object.keys(K).forEach(k=>{const v=SNAP[k];"
    "if(v===null)localStorage.removeItem(K[k]+'" + SYM + "');else localStorage.setItem(K[k]+'" + SYM + "',v);});};"
)


def test_quick_layer_overlays_in_object_manager():
    _goto()
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "['#ind-sma','#ind-ema','#ind-bb','#ind-vol'].forEach(s=>{const e=document.querySelector(s);if(e)e.checked=true;});"
        "await loadChart();await sleep(2500);"
        "const g=(collectChartObjects()||[]).find(x=>x.title==='Quick layers');"
        "const items=g?g.items:[];const byId={};items.forEach(i=>byId[i.id]=i);"
        "return JSON.stringify({sma:!!byId['quick-sma'],ema:!!byId['quick-ema'],bb:!!byId['quick-bb'],vol:!!byId['quick-vol'],"
        "ownersOk:items.length>0&&items.every(i=>!!i.owner&&!!i.label&&!!i.when)});})()"
    )
    assert res["sma"], f"SMA quick overlay missing from manager: {res}"
    assert res["ema"], f"EMA quick overlay missing: {res}"
    assert res["bb"], f"Bollinger quick overlay missing: {res}"
    assert res["vol"], f"Volume quick overlay missing: {res}"
    assert res["ownersOk"], f"quick-layer rows must show label/type/owner: {res}"


def test_oscillator_panes_in_object_manager():
    _goto()
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "['#ind-rsi','#ind-macd'].forEach(s=>{const e=document.querySelector(s);if(e)e.checked=true;});"
        "await loadChart();await sleep(3000);"
        "const g=(collectChartObjects()||[]).find(x=>x.title==='Quick layers');"
        "const ids=(g?g.items:[]).map(i=>i.id);"
        "return JSON.stringify({rsiRow:ids.indexOf('quick-rsi')>=0,macdRow:ids.indexOf('quick-macd')>=0,"
        "rsiPane:!!state.charts['rsi-pane'],macdPane:!!state.charts['macd-pane'],"
        "rsiVisible:!!(document.querySelector('#rsi-pane')&&!document.querySelector('#rsi-pane').hidden)});})()"
    )
    assert res["rsiRow"] and res["rsiPane"], f"RSI pane not in manager/chart: {res}"
    assert res["macdRow"] and res["macdPane"], f"MACD pane not in manager/chart: {res}"
    assert res["rsiVisible"], f"RSI pane should be visible after enabling: {res}"


def test_hide_and_remove_act_on_real_objects_and_annotations():
    _goto()
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SNAP + _SETUP +
        "try{"
        "['#ind-rsi','#ind-swings'].forEach(s=>{const e=document.querySelector(s);if(e)e.checked=true;});"
        "await loadChart();await sleep(3000);"
        "const qr=state.quickObjects.find(q=>q.id==='quick-rsi');toggleQuickObject(qr);"
        "const rsiHidden=document.querySelector('#rsi-pane').hidden;toggleQuickObject(qr);"
        "const rsiShown=!document.querySelector('#rsi-pane').hidden;"
        "const qs=state.quickObjects.find(q=>q.id==='quick-swings');"
        "const owned=quickOwnedMarkers(qs).length;toggleQuickObject(qs);"
        "const markersHidden=owned>0&&quickOwnedMarkers(qs).every(m=>m.hidden);toggleQuickObject(qs);"
        "removeQuickObject(qs);"
        "const swingsCleared=quickOwnedMarkers(qs).length===0&&!state.quickObjects.some(q=>q.id==='quick-swings')"
        "&&!document.querySelector('#ind-swings').checked;"
        "removeQuickObject(qr);"
        "const paneGone=!state.charts['rsi-pane']&&!state.quickObjects.some(q=>q.id==='quick-rsi')"
        "&&document.querySelector('#rsi-pane').hidden&&!document.querySelector('#ind-rsi').checked;"
        "return JSON.stringify({rsiHidden,rsiShown,owned,markersHidden,swingsCleared,paneGone});"
        "}finally{restore();}})()"
    )
    assert res["rsiHidden"] and res["rsiShown"], f"Hide/Show must affect the pane: {res}"
    assert res["owned"] > 0, f"swings quick layer should own markers: {res}"
    assert res["markersHidden"], f"hiding the swings layer must hide its markers: {res}"
    assert res["swingsCleared"], f"removing swings must drop owned markers + toggle: {res}"
    assert res["paneGone"], f"removing RSI must remove the pane and its row: {res}"


def test_detector_markers_restore_after_reload():
    _goto()
    # First pass: enable the patterns layer (persisted), let the detector run.
    first = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "if(!state.layers.patterns)toggleLayer('patterns');await sleep(6500);"
        "return JSON.stringify({n:(state.patternMarkers||[]).length,series:(state.patternSeries||[]).length});})()"
    )
    assert first["n"] > 0, f"patterns layer produced no markers to restore: {first}"
    # Full page reload: markers must be reconstructed from the persisted layer flag.
    _goto()
    second = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP + "await sleep(4000);"
        "return JSON.stringify({n:(state.patternMarkers||[]).length,layers:Object.keys(state.layers||{})});})()"
    )
    assert "patterns" in second["layers"], f"persisted layer flag lost: {second}"
    assert second["n"] == first["n"], f"marker count changed across reload ({first['n']} -> {second['n']})"
    # Clean up: leave the profile as found.
    _eval("(async()=>{""if(state.layers.patterns)toggleLayer('patterns');"
          "return JSON.stringify({ok:true});})()")


def test_no_duplicate_objects_across_repeated_reloads():
    counts = []
    for _ in range(3):
        _goto()
        r = _eval(
            "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
            + _SETUP + "await sleep(2500);"
            "return JSON.stringify({quick:(state.quickObjects||[]).length,"
            "markers:(state.markers||[]).length,candle:(state.candleMarkers||[]).length,"
            "pat:(state.patternMarkers||[]).length,groups:(collectChartObjects()||[]).length});})()"
        )
        counts.append(r)
    assert counts[0] == counts[1] == counts[2], f"object counts drifted across reloads: {counts}"


def test_manual_fibonacci_preserves_viewport():
    _goto()
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SNAP + _SETUP +
        "try{"
        "const ts=state.charts.price.timeScale();const n=state.chartBars.length;"
        "ts.setVisibleLogicalRange({from:Math.floor(n*0.30),to:Math.floor(n*0.70)});await sleep(300);"
        "const snap=()=>{const r=ts.getVisibleLogicalRange();return r?{from:+r.from.toFixed(3),to:+r.to.toFixed(3)}:null;};"
        "const before=snap();const dBefore=(state.drawings||[]).length;"
        "setDrawTool('fib_retracement');const dates=state.chartBars.map(b=>b.time);"
        "const i1=Math.floor(n*0.40),i2=Math.floor(n*0.58);"
        "onChartClick({time:dates[i1],point:{x:ts.timeToCoordinate(dates[i1]),y:state.candleSeries.priceToCoordinate(state.chartBars[i1].high)}});"
        "onChartClick({time:dates[i2],point:{x:ts.timeToCoordinate(dates[i2]),y:state.candleSeries.priceToCoordinate(state.chartBars[i2].low)}});"
        "await sleep(400);setDrawTool(null);"
        "const added=(state.drawings||[]).slice(-1)[0];"
        "return JSON.stringify({before,after:snap(),addedType:added&&added.type,dBefore,dAfter:(state.drawings||[]).length});"
        "}finally{restore();}})()"
    )
    assert res["addedType"] == "fib_retracement", f"manual fib not committed: {res}"
    assert res["dAfter"] == res["dBefore"] + 1, f"drawing not added: {res}"
    assert res["before"] == res["after"], f"manual fib moved the viewport: {res['before']} -> {res['after']}"


def test_automatic_fibonacci_preserves_viewport_and_objects():
    _goto()
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SNAP + _SETUP +
        "try{"
        "const ts=state.charts.price.timeScale();const n=state.chartBars.length;"
        "ts.setVisibleLogicalRange({from:Math.floor(n*0.30),to:Math.floor(n*0.70)});await sleep(300);"
        "const snap=()=>{const r=ts.getVisibleLogicalRange();return r?{from:+r.from.toFixed(3),to:+r.to.toFixed(3)}:null;};"
        "const before=snap();"
        "const dBefore=(state.drawings||[]).length;const iBefore=(state.customInds||[]).length;"
        "const extra=await addToChartFromCatalog('sma',{period:9});await sleep(1500);"
        "const afterAdd=snap();"
        "toggleLayer('fib');await sleep(5000);const ts2=state.charts.price.timeScale();"
        "const r2=ts2.getVisibleLogicalRange();const after={from:+r2.from.toFixed(3),to:+r2.to.toFixed(3)};"
        "const res={before,afterAdd,after,fibSeries:(state.layerSeries.fib||[]).length,"
        "drawingsOk:(state.drawings||[]).length===dBefore,"
        "indsOk:(state.customInds||[]).length===iBefore+1,"
        "extraAlive:(state.customInds||[]).some(x=>x.id===extra.id)};"
        "return JSON.stringify(res);"
        "}finally{restore();}})()"
    )
    assert res["before"] == res["afterAdd"], f"adding an indicator moved the viewport: {res}"
    assert res["before"] == res["after"], f"auto fib moved the viewport: {res['before']} -> {res['after']}"
    assert res["fibSeries"] > 0, f"auto fib drew nothing to preserve around: {res}"
    assert res["drawingsOk"], f"existing drawings not preserved through auto fib: {res}"
    assert res["indsOk"] and res["extraAlive"], f"existing indicators not preserved: {res}"


def test_no_browser_console_errors():
    _goto()
    _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "['#ind-sma','#ind-rsi'].forEach(s=>{const e=document.querySelector(s);if(e)e.checked=true;});"
        "await loadChart();await sleep(2500);return JSON.stringify({ok:true});})()"
    )
    out = _pw("console", "error")
    m = re.search(r"Errors:\s*(\d+)", out)
    assert m, f"could not read console summary:\n{out}"
    assert int(m.group(1)) == 0, f"browser console reported errors:\n{out}"
