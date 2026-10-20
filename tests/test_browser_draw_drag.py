"""Browser regression tests for the chart drawing interaction state machine.

The defect these cover: with a drawing tool active the chart CANNOT pan
(``setDrawTool`` disables ``pressedMouseMove``), yet ``onChartClick`` still
dropped any click whose pointer travelled >12 px. Click-drag placement —
including dragging to the LEFT — therefore silently did nothing, and a pan
gesture could not be distinguished from drawing.

Opt-in: needs a live dev server and playwright-cli (same harness as
``test_browser_chart_drawing.py``).

    MEGATOOL_BROWSER_TESTS=1 MEGATOOL_BROWSER_BASE=http://127.0.0.1:10000/ \
        .venv/bin/python -m pytest tests/test_browser_draw_drag.py -q
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
SESSION = "mtdragtest"
SYM = "NABIL"

pytestmark = pytest.mark.skipif(
    os.environ.get("MEGATOOL_BROWSER_TESTS") != "1",
    reason="browser tests are opt-in; set MEGATOOL_BROWSER_TESTS=1 with a live dev server",
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
        with contextlib.suppress(Exception):
            val = json.loads(val)
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
    "state.drawings=[];state.drawPending=null;state.drawDrag=null;"
    "localStorage.removeItem('mt-drawings-" + SYM + "');"
)


def test_drag_while_a_tool_is_active_still_places_the_anchor():
    """Panning is disabled with a tool active, so pointer travel is drawing intent."""
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const sel=document.querySelector('#draw-tool');sel.value='trendline';"
        "sel.dispatchEvent(new Event('change',{bubbles:true}));"
        "const ts=state.charts.price.timeScale();"
        "const i=Math.floor(state.chartDates.length*0.75);"
        "const x=ts.timeToCoordinate(state.chartDates[i]);"
        "const y=state.candleSeries.priceToCoordinate(state.chartBars[i].close);"
        "const rect=document.querySelector('#chart').getBoundingClientRect();"
        # simulate: the pointer went down 60px to the right, then travelled left
        "state.chartDrag={mouseDown:{x:rect.left+x+60,y:rect.top+y}};"
        "onChartClick({time:state.chartDates[i], point:{x:x, y:y}, seriesData:{}});"
        "return JSON.stringify({panEnabled: state.panEnabled, pending: !!state.drawPending,"
        "  pendingTime: state.drawPending && state.drawPending.t, expected: state.chartDates[i]});"
        "})()"
    )
    assert res["panEnabled"] is False, "a placement tool must disable chart panning"
    assert res["pending"] is True, "a click that travelled while a tool was active must still anchor"
    assert res["pendingTime"] == res["expected"]


def test_drag_with_no_tool_is_still_treated_as_navigation():
    """The guard must keep working when panning IS possible (no tool active)."""
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const sel=document.querySelector('#draw-tool');sel.value='trendline';"
        "sel.dispatchEvent(new Event('change',{bubbles:true}));"
        "const ts=state.charts.price.timeScale();"
        "const i=Math.floor(state.chartDates.length*0.6);"
        "const x=ts.timeToCoordinate(state.chartDates[i]);"
        "const y=state.candleSeries.priceToCoordinate(state.chartBars[i].close);"
        "const rect=document.querySelector('#chart').getBoundingClientRect();"
        # force the pan-possible state the guard is meant for
        "state.panEnabled=true;"
        "state.chartDrag={mouseDown:{x:rect.left+x+60,y:rect.top+y}};"
        "onChartClick({time:state.chartDates[i], point:{x:x, y:y}, seriesData:{}});"
        "return JSON.stringify({pending: !!state.drawPending});"
        "})()"
    )
    assert res["pending"] is False, "a pan gesture must not plant an anchor"


def test_drawing_right_to_left_creates_the_drawing_and_leaves_ohlc_untouched():
    """The exact reported case: click a candle, drag LEFT."""
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const sel=document.querySelector('#draw-tool');sel.value='trendline';"
        "sel.dispatchEvent(new Event('change',{bubbles:true}));"
        "const ts=state.charts.price.timeScale();"
        "const hi=Math.floor(state.chartDates.length*0.8), lo=Math.floor(state.chartDates.length*0.3);"
        "const barsBefore=JSON.stringify(state.chartBars.slice(lo,hi+1));"
        "const datesBefore=JSON.stringify(state.chartDates.slice(lo,hi+1));"
        # anchor 1 on the RIGHT, then drag LEFT to anchor 2
        "onChartClick({time:state.chartDates[hi], point:{x:ts.timeToCoordinate(state.chartDates[hi]), y:state.candleSeries.priceToCoordinate(state.chartBars[hi].close)}, seriesData:{}});"
        "onChartClick({time:state.chartDates[lo], point:{x:ts.timeToCoordinate(state.chartDates[lo]), y:state.candleSeries.priceToCoordinate(state.chartBars[lo].close)}, seriesData:{}});"
        "const d=state.drawings[0];"
        "const barsAfter=JSON.stringify(state.chartBars.slice(lo,hi+1));"
        "const datesAfter=JSON.stringify(state.chartDates.slice(lo,hi+1));"
        "return JSON.stringify({created: !!d, t1:d&&d.t1, t2:d&&d.t2,"
        "  expectedT1:state.chartDates[hi], expectedT2:state.chartDates[lo],"
        "  barsUnchanged: barsBefore===barsAfter, datesUnchanged: datesBefore===datesAfter,"
        "  candleSeriesAlive: !!state.candleSeries && !!state.charts.price});"
        "})()"
    )
    assert res["created"] is True, "dragging left must still create the drawing"
    assert res["t1"] == res["expectedT1"] and res["t2"] == res["expectedT2"]
    assert res["barsUnchanged"] is True, "drawing must never mutate OHLC values"
    assert res["datesUnchanged"] is True
    assert res["candleSeriesAlive"] is True, "the candle series must survive drawing"


def test_escape_cancels_a_pending_anchor():
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const sel=document.querySelector('#draw-tool');sel.value='trendline';"
        "sel.dispatchEvent(new Event('change',{bubbles:true}));"
        "const ts=state.charts.price.timeScale();"
        "const i=Math.floor(state.chartDates.length*0.5);"
        "onChartClick({time:state.chartDates[i], point:{x:ts.timeToCoordinate(state.chartDates[i]), y:state.candleSeries.priceToCoordinate(state.chartBars[i].close)}, seriesData:{}});"
        "const anchored=!!state.drawPending;"
        "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));"
        "await sleep(120);"
        "return JSON.stringify({anchored, pendingAfter: !!state.drawPending, drawings: (state.drawings||[]).length});"
        "})()"
    )
    assert res["anchored"] is True
    assert res["pendingAfter"] is False, "Escape must cancel the pending anchor"
    assert res["drawings"] == 0


def test_panning_still_works_with_no_tool_active():
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const sel=document.querySelector('#draw-tool');sel.value='';"
        "sel.dispatchEvent(new Event('change',{bubbles:true}));"
        "const ts=state.charts.price.timeScale();"
        "const before=ts.getVisibleLogicalRange();"
        "ts.setVisibleLogicalRange({from:before.from+20,to:before.to+20});"
        "await sleep(120);"
        "const after=ts.getVisibleLogicalRange();"
        "return JSON.stringify({panEnabled: state.panEnabled, moved: Math.abs(after.from-before.from)>5});"
        "})()"
    )
    assert res["panEnabled"] is True, "no tool must leave panning enabled"
    assert res["moved"] is True, "the viewport must still be pannable"
