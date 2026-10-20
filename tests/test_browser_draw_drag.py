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


def _fresh_url() -> str:
    """Cache-bust the HTML for local runs.

    Static assets carry their own version query; the page itself does not, so a
    long-lived Playwright profile could otherwise keep testing yesterday's HTML.
    """
    sep = "&" if "?" in BASE else "?"
    return f"{BASE}{sep}v={int(time.time() * 1000)}"


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
    _pw("open", _fresh_url())
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
    _pw("goto", _fresh_url())
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
    _pw("goto", _fresh_url())
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
    _pw("goto", _fresh_url())
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
    _pw("goto", _fresh_url())
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
    _pw("goto", _fresh_url())
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


def test_real_pointer_leftward_drawing_keeps_both_anchors_under_the_cursor():
    """The exact coordinate failure, exercised with real mouse events.

    Two anchors placed at local chart y=100 and y=300 must map back to the same
    pixels after the drawing overlay is rendered. A preview drawn right-to-left
    must also be sorted, because Lightweight Charts rejects descending time.
    """
    _pw("goto", _fresh_url())
    time.sleep(5)
    _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const sel=document.querySelector('#draw-tool');sel.value='trendline';"
        "sel.dispatchEvent(new Event('change',{bubbles:true}));"
        "await sleep(500);"  # let any tool-activation layout settle first
        "return true;})()"
    )
    geom = _eval(
        "(()=>{const ts=state.charts.price.timeScale();"
        "const n=state.chartDates.length;"
        "const i1=Math.floor(n*0.8), i2=Math.floor(n*0.3);"
        "const el=document.querySelector('#chart');const r=el.getBoundingClientRect();"
        "const x1=ts.timeToCoordinate(state.chartDates[i1]);"
        "const x2=ts.timeToCoordinate(state.chartDates[i2]);"
        "return JSON.stringify({sx1:Math.round(r.left+el.clientLeft+x1), sy1:Math.round(r.top+el.clientTop+100),"
        " sx2:Math.round(r.left+el.clientLeft+x2), sy2:Math.round(r.top+el.clientTop+300),"
        " i1:state.chartDates[i1], i2:state.chartDates[i2]});})()"
    )
    out = ""
    out += _pw("mousemove", str(geom["sx1"]), str(geom["sy1"]))
    out += _pw("mousedown")
    out += _pw("mouseup")
    time.sleep(0.25)
    out += _pw("mousemove", str((geom["sx1"] + geom["sx2"]) // 2), "520")
    out += _pw("mousemove", str(geom["sx2"]), str(geom["sy2"]))
    time.sleep(0.35)
    preview = _eval(
        "(()=>{const pv=state.drawPreviewSeries&&state.drawPreviewSeries[0];"
        "return JSON.stringify({n:state.drawPreviewSeries.length, data:pv&&pv.data?pv.data():[],"
        " pending: !!state.drawPending});})()"
    )
    assert preview["n"] == 1 and preview["data"], preview
    times = [p["time"] for p in preview["data"]]
    assert times == sorted(times), f"preview time must be ascending for a leftward drag: {times}"
    assert "Value is null" not in out

    out += _pw("mousedown")
    out += _pw("mouseup")
    time.sleep(0.6)
    res = _eval(
        "(()=>{const d=state.drawings[0];const cs=state.candleSeries;"
        "const ts=state.charts.price.timeScale();"
        "const pt=(t,p)=>({x:ts.timeToCoordinate(t),y:cs.priceToCoordinate(p)});"
        "return JSON.stringify({n:state.drawings.length,"
        " d:d&&{t1:d.t1,t2:d.t2,p1:d.p1,p2:d.p2},"
        " back1:d&&pt(d.t1,d.p1), back2:d&&pt(d.t2,d.p2),"
        " series:state.drawSeries.length, preview:state.drawPreviewSeries.length});})()"
    )
    assert res["n"] == 1, res
    assert res["series"] == 1, "the committed drawing must be rendered"
    assert res["preview"] == 0, "the transient preview must be removed after commit"
    assert abs(res["back1"]["y"] - 100.5) <= 1.5, res
    assert abs(res["back2"]["y"] - 300.5) <= 1.5, res
    assert res["back1"]["x"] is not None and res["back2"]["x"] is not None
    assert "Value is null" not in out


def test_anchor_markers_never_change_the_price_scale():
    """Markers belong on a non-autoscaling host, not on the candlestick series.

    Lightweight Charts reserves vertical room for markers. When the anchor
    markers were set on the candles, a click at one pixel stored a price that
    mapped 5–10 px lower after the drawing committed. The dedicated host is
    excluded from autoscale, so the price at a fixed pixel is unchanged.
    """
    _pw("goto", _fresh_url())
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const cs=state.candleSeries;"
        "const t=state.chartDates[Math.floor(state.chartDates.length*0.7)];"
        "const before=cs.priceToCoordinate(cs.coordinateToPrice(150));"
        "state.pendingMarker=[{time:t,position:'inBar',color:'#fff',shape:'circle',text:'A'}];"
        "flushMarkers();"
        "await sleep(250);"
        "const after=cs.priceToCoordinate(cs.coordinateToPrice(150));"
        "const host=state.markerSeries;"
        "const opts=host&&host.options();"
        "return JSON.stringify({before,after,host:!!host,"
        "range:opts&&opts.autoscaleInfoProvider?opts.autoscaleInfoProvider():'missing',"
        "points:host?host.data().length:0,dates:state.chartDates.length});})()"
    )
    assert res["host"] is True, res
    assert res["points"] == res["dates"], res
    assert res["range"] is None, res
    assert abs(res["before"] - res["after"]) < 0.01, res


def test_drawing_survives_zoom_scroll_and_keeps_chart_local_coordinates():
    """Coordinate conversion must use the chart's own APIs, not page offsets."""
    _pw("goto", _fresh_url())
    time.sleep(5)
    _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const sel=document.querySelector('#draw-tool');sel.value='trendline';"
        "sel.dispatchEvent(new Event('change',{bubbles:true}));"
        "const ts=state.charts.price.timeScale();"
        "const n=state.chartDates.length;"
        "const hi=Math.floor(n*0.75),lo=Math.floor(n*0.35);"
        "onChartClick({time:state.chartDates[hi], point:{x:ts.timeToCoordinate(state.chartDates[hi]),"
        " y:state.candleSeries.priceToCoordinate(state.chartBars[hi].close)}, seriesData:{}});"
        "onChartClick({time:state.chartDates[lo], point:{x:ts.timeToCoordinate(state.chartDates[lo]),"
        " y:state.candleSeries.priceToCoordinate(state.chartBars[lo].close)}, seriesData:{}});"
        "return true;})()"
    )
    time.sleep(0.3)
    zoom = _eval(
        "(async()=>{const ts=state.charts.price.timeScale();const d=state.drawings[0];"
        "const before=ts.getVisibleLogicalRange();"
        "ts.setVisibleLogicalRange({from:before.from+8,to:before.to-8});"
        "await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));"
        "const cs=state.candleSeries;"
        "const out={x1:ts.timeToCoordinate(d.t1),x2:ts.timeToCoordinate(d.t2),"
        " y1:cs.priceToCoordinate(d.p1),y2:cs.priceToCoordinate(d.p2)};"
        "ts.setVisibleLogicalRange(before);"
        "return JSON.stringify(out);})()"
    )
    assert all(isinstance(zoom[k], (int, float)) for k in ("x1", "x2", "y1", "y2")), zoom

    _pw("resize", "1200", "800")
    time.sleep(0.6)
    resized = _eval(
        "(()=>{const ts=state.charts.price.timeScale(),cs=state.candleSeries,d=state.drawings[0];"
        "const el=document.querySelector('#chart');"
        "return JSON.stringify({w:el.clientWidth,h:el.clientHeight,n:state.drawings.length,"
        "t1:d.t1,p1:d.p1,x1:ts.timeToCoordinate(d.t1),x2:ts.timeToCoordinate(d.t2),"
        "y1:cs.priceToCoordinate(d.p1),y2:cs.priceToCoordinate(d.p2)});})()"
    )
    assert resized["n"] == 1 and resized["t1"] == "2026-07-13", resized
    assert all(isinstance(resized[k], (int, float)) for k in ("x1", "x2", "y1", "y2")), resized
    _pw("resize", "1280", "720")
    time.sleep(0.4)

    scrolled = _eval(
        "(async()=>{window.scrollBy(0,80);"
        "await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));"
        "const el=document.querySelector('#chart'),r=el.getBoundingClientRect();"
        "const ts=state.charts.price.timeScale();const i=Math.floor(state.chartDates.length*0.6);"
        "return JSON.stringify({x:Math.round(r.left+el.clientLeft+ts.timeToCoordinate(state.chartDates[i])),"
        " y:Math.round(r.top+el.clientTop+250), expected:state.chartDates[i]});})()"
    )
    _pw("mousemove", str(scrolled["x"]), str(scrolled["y"]))
    _pw("mousedown")
    _pw("mouseup")
    time.sleep(0.3)
    pending = _eval(
        "(()=>JSON.stringify({t:state.drawPending&&state.drawPending.t,"
        "y:state.drawPending&&state.candleSeries.priceToCoordinate(state.drawPending.p)}))()"
    )
    assert pending["t"] == scrolled["expected"], (pending, scrolled)
    assert abs(pending["y"] - 250.5) <= 1.5, pending
    _eval("(()=>{document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));return true;})()")
    time.sleep(0.15)
    assert _eval("(()=>JSON.stringify({pending:!!state.drawPending}))()")["pending"] is False


def test_coincident_anchors_create_a_valid_single_point_drawing():
    """Two clicks on the same bar/price must not feed descending or empty data."""
    _pw("goto", _fresh_url())
    time.sleep(5)
    geom = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "const sel=document.querySelector('#draw-tool');sel.value='trendline';"
        "sel.dispatchEvent(new Event('change',{bubbles:true}));await sleep(400);"
        "const ts=state.charts.price.timeScale();"
        "const i=Math.floor(state.chartDates.length*0.55);"
        "const el=document.querySelector('#chart'),r=el.getBoundingClientRect();"
        "return JSON.stringify({x:Math.round(r.left+el.clientLeft+ts.timeToCoordinate(state.chartDates[i])),"
        " y:Math.round(r.top+el.clientTop+200),time:state.chartDates[i]});})()"
    )
    for _ in range(2):
        _pw("mousemove", str(geom["x"]), str(geom["y"]))
        _pw("mousedown")
        _pw("mouseup")
        time.sleep(0.25)
    res = _eval(
        "(()=>{const d=state.drawings[0];const s=state.drawSeries[0];"
        "return JSON.stringify({n:state.drawings.length,t1:d&&d.t1,t2:d&&d.t2,"
        "p1:d&&d.p1,p2:d&&d.p2,series:state.drawSeries.length,"
        "points:s?s.data().length:null,preview:state.drawPreviewSeries.length});})()"
    )
    assert res["n"] == 1 and res["t1"] == geom["time"] and res["t2"] == geom["time"], res
    assert res["p1"] == res["p2"], res
    assert res["series"] == 1 and res["points"] == 1, res
    assert res["preview"] == 0, res
