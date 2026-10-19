"""Browser-driven regression test for the chart-drawing placement fix (Phase 14).

The defect: ``onChartClick`` trusted ``param.time`` directly, so clicks in the
empty space to the right of the last bar were rejected ("Click inside the
plotted bars.") and, in builds where ``param.time`` resolved to an unexpected
value, the anchor landed on an unrelated (often the first) bar.

The fix resolves the timestamp with ``barIndexAtX()`` (the same logical-coordinate
helper the drag path uses) when ``param.time`` is missing, clamping to the data
range instead of jumping.

These tests are OPT-IN (need a live dev server + playwright-cli). They use the
same harness as ``test_browser_objects_manager.py``.
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
SESSION = "mtdrawtest"
SYM = "NABIL"

pytestmark = pytest.mark.skipif(
    os.environ.get("MEGATOOL_BROWSER_TESTS") != "1",
    reason="browser tests are opt-in; set MEGATOOL_BROWSER_TESTS=1 with a live dev server on :10000",
)


def _server_up() -> bool:
    try:
        with urllib.request.urlopen(BASE, timeout=2) as r:  # noqa: S310
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


_SETUP = (
    "showView('charts');"
    "document.querySelector('#symbol-input').value='" + SYM + "';"
    "document.querySelector('#range').value='250';"
    "await loadChart();await sleep(2000);"
    "const sel=document.querySelector('#draw-tool');sel.value='trendline';sel.dispatchEvent(new Event('change',{bubbles:true}));"
    "state.drawings=[];state.drawPending=null;localStorage.removeItem('mt-drawings-" + SYM + "');"
)


def test_drawing_near_last_bar_does_not_jump_to_beginning():
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const ts=state.charts.price.timeScale();"
        "const lastDate=state.chartDates[state.chartDates.length-1];"
        "const lastY=state.candleSeries.priceToCoordinate(state.chartBars[state.chartBars.length-1].close);"
        "onChartClick({time:null, point:{x:ts.timeToCoordinate(lastDate)+40, y:lastY}, seriesData:{}});"
        "const a1=state.drawPending?{...state.drawPending}:null;"
        "const midIdx=Math.floor(state.chartDates.length/2);"
        "const midX=ts.timeToCoordinate(state.chartDates[midIdx]);"
        "const midY=state.candleSeries.priceToCoordinate(state.chartBars[midIdx].close);"
        "onChartClick({time:state.chartDates[midIdx], point:{x:midX, y:midY}, seriesData:{}});"
        "const d=state.drawings[0];"
        "const firstDate=state.chartDates[0];"
        "return JSON.stringify({anchor1:a1, t1:d&&d.t1, t2:d&&d.t2, firstDate, lastDate,"
        "  renders: d && ts.timeToCoordinate(d.t1)!=null && ts.timeToCoordinate(d.t2)!=null,"
        "  noJumpToBeginning: d && d.t1===lastDate});"
        "})()"
    )
    assert res["noJumpToBeginning"] is True, f"anchor 1 should land on the last bar, got {res}"
    assert res["t1"] == res["lastDate"]
    assert res["renders"] is True
    assert res["t1"] != res["firstDate"]


def test_drawing_near_first_bar():
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const ts=state.charts.price.timeScale();"
        "const firstDate=state.chartDates[0];"
        "const firstY=state.candleSeries.priceToCoordinate(state.chartBars[0].close);"
        "const firstX=ts.timeToCoordinate(firstDate);"
        "onChartClick({time:firstDate, point:{x:firstX, y:firstY}, seriesData:{}});"
        "const a1=state.drawPending?{...state.drawPending}:null;"
        "const midIdx=Math.floor(state.chartDates.length/2);"
        "const midX=ts.timeToCoordinate(state.chartDates[midIdx]);"
        "const midY=state.candleSeries.priceToCoordinate(state.chartBars[midIdx].close);"
        "onChartClick({time:state.chartDates[midIdx], point:{x:midX, y:midY}, seriesData:{}});"
        "const d=state.drawings[0];"
        "return JSON.stringify({t1:d&&d.t1, firstDate, renders: d && ts.timeToCoordinate(d.t1)!=null});"
        "})()"
    )
    assert res["t1"] == res["firstDate"]
    assert res["renders"] is True


def test_drawing_save_restore_preserves_coordinates():
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const ts=state.charts.price.timeScale();"
        "const lastDate=state.chartDates[state.chartDates.length-1];"
        "const lastY=state.candleSeries.priceToCoordinate(state.chartBars[state.chartBars.length-1].close);"
        "onChartClick({time:null, point:{x:ts.timeToCoordinate(lastDate)+40, y:lastY}, seriesData:{}});"
        "const midIdx=Math.floor(state.chartDates.length/2);"
        "const midX=ts.timeToCoordinate(state.chartDates[midIdx]);"
        "const midY=state.candleSeries.priceToCoordinate(state.chartBars[midIdx].close);"
        "onChartClick({time:state.chartDates[midIdx], point:{x:midX, y:midY}, seriesData:{}});"
        "const before=JSON.stringify(state.drawings);"
        "persistDrawings('" + SYM + "', state.drawings);"
        "state.drawings=[];"
        "state.drawings=loadDrawings('" + SYM + "');"
        "const after=JSON.stringify(state.drawings);"
        "localStorage.removeItem('mt-drawings-" + SYM + "');"
        "return JSON.stringify({saved:true, preserved: before===after, n: state.drawings.length});"
        "})()"
    )
    assert res["preserved"] is True
    assert res["n"] == 1
