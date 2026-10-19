"""Browser-driven regression test for the Trend Strength & Regime analysis layer.

Category 2 of the five approved Part B analysis categories. Reuses the existing
adx, supertrend and parabolic_sar indicators via /api/bars/{symbol}/indicator.

OPT-IN (needs a live dev server + playwright-cli).
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
SESSION = "mttrendtest"
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
    "localStorage.removeItem('mt-chart-layers-" + SYM + "');"
    "showView('charts');"
    "document.querySelector('#symbol-input').value='" + SYM + "';"
    "document.querySelector('#range').value='120';"
    "await loadChart();await sleep(2000);"
)


def test_trend_layer_toggles_and_renders():
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "toggleLayer('trend');await sleep(5000);"
        "return JSON.stringify({on:!!state.layers.trend,"
        "drawn:(state.layerDrawn.trend||{}).drawn,"
        "nMarkers:state.trendMarkers.length,"
        "errs:window.__errs||[]});"
        "})()"
    )
    assert res["on"] is True
    assert res["errs"] == []


def test_trend_layer_toggle_off_clears():
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "toggleLayer('trend');await sleep(5000);"
        "toggleLayer('trend');await sleep(4000);"
        "return JSON.stringify({on:!!state.layers.trend,"
        "nMarkers:state.trendMarkers.length,"
        "errs:window.__errs||[]});"
        "})()"
    )
    assert res["on"] is False
    assert res["nMarkers"] == 0
    assert res["errs"] == []


def test_classify_trend_regime_logic():
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "JSON.stringify({"
        "trending: classifyTrendRegime(30, 25, 15),"
        "ranging: classifyTrendRegime(15, 20, 22),"
        "transition: classifyTrendRegime(22, 18, 20),"
        "bullish: classifyTrendRegime(25, 30, 10).direction,"
        "bearish: classifyTrendRegime(25, 10, 30).direction,"
        "unknown: classifyTrendRegime(NaN, 10, 20).regime"
        "})"
    )
    assert res["trending"]["regime"] == "trending"
    assert res["ranging"]["regime"] == "ranging"
    assert res["transition"]["regime"] == "transition"
    assert res["bullish"] == "bullish"
    assert res["bearish"] == "bearish"
    assert res["unknown"] == "unknown"


def test_structure_layer_still_works_after_trend():
    _pw("goto", BASE)
    time.sleep(5)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        + _SETUP +
        "toggleLayer('structure');await sleep(4000);"
        "toggleLayer('trend');await sleep(5000);"
        "return JSON.stringify({structure:!!state.layers.structure,"
        "trend:!!state.layers.trend,"
        "errs:window.__errs||[]});"
        "})()"
    )
    assert res["structure"] is True
    assert res["trend"] is True
    assert res["errs"] == []
