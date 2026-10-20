"""Browser tests: universal search must open the REAL destination and initialise it.

Registry lookup alone is not proof (see tests/test_features_registry.mjs). These
drive the actual palette in a live browser and assert the view that becomes
active, plus the tool state that destination initialises.

Opt-in: needs a live dev server and playwright-cli.

    MEGATOOL_BROWSER_TESTS=1 MEGATOOL_BROWSER_BASE=http://127.0.0.1:10000/ \
        .venv/bin/python -m pytest tests/test_browser_search_destinations.py -q
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
SESSION = "mtsearchtest"

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


def _pw(*args: str, timeout: int = 180) -> str:
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
    time.sleep(6)
    yield
    _pw("close")


#: (query, expected active view id, expected extra state)
CASES = [
    ("trade planner", "journal", None),
    ("trade journal", "journal", None),
    ("top buyers", "floorsheet", None),
    ("top sellers", "floorsheet", None),
    ("buyer-seller pairs", "floorsheet", None),
    ("money-flow oversold", "screener", {"preset": "mfi_oversold"}),
    ("low volatility", "screener", {"preset": "low_volatility"}),
    ("liquid by turnover", "screener", {"preset": "liquid_turnover"}),
    ("oversold RSI", "screener", {"preset": "oversold_rsi"}),
    ("eps history", "new", None),
    ("eps growth", "new", None),
    ("dividends", "sastoshare", None),
    ("seasonality", "sea", None),
    ("holiday effect", "sea", None),
    ("sector rotation", "sastoshare", None),
    ("graham", "ideas", None),
    ("piotroski", "ideas", None),
    ("altman", "ideas", None),
    ("market breadth", "breadth", None),
    ("relative strength", "screener", None),
]


def test_every_command_opens_its_real_destination():
    _pw("goto", BASE)
    time.sleep(6)
    script = (
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        "const cases=" + json.dumps([[q, v] for q, v, _ in CASES]) + ";"
        "const out={};"
        "for (const [q,expect] of cases){"
        "  document.querySelector('#chart-search').click(); await sleep(2600);"
        "  const inp=document.querySelector('#cmdk-input');"
        "  inp.value=q; inp.dispatchEvent(new Event('input',{bubbles:true})); await sleep(300);"
        "  const first=document.querySelector('#cmdk-list .cmdk-item');"
        "  const label=first?first.querySelector('.ci-label').textContent:null;"
        "  const disabled=first?first.classList.contains('disabled'):null;"
        "  if(first) first.click(); await sleep(1100);"
        "  const active=document.querySelector('.view.active');"
        "  const activeId=active?active.id.replace('view-',''):null;"
        "  out[q]={label, disabled, activeId, ok: activeId===expect, preset:(document.querySelector('#preset')||{}).value||null};"
        "  const cm=document.querySelector('#cmdk');"
        "  if(cm && !cm.hidden){ const c=document.querySelector('#cmdk-close'); if(c) c.click(); }"
        "  await sleep(200);"
        "} return JSON.stringify(out);})()"
    )
    res = _eval(script)
    bad = {q: r for q, r in res.items() if not r["ok"]}
    assert not bad, f"commands that did not open their destination: {json.dumps(bad, indent=2)}"
    for q, r in res.items():
        assert r["disabled"] is False, f"{q} resolved to a DISABLED entry"


def test_scanner_commands_initialise_the_saved_preset():
    _pw("goto", BASE)
    time.sleep(6)
    wanted = {q: extra["preset"] for q, _v, extra in CASES if extra and "preset" in extra}
    script = (
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        "const qs=" + json.dumps(list(wanted)) + ";"
        "const out={};"
        "for (const q of qs){"
        "  document.querySelector('#chart-search').click(); await sleep(2400);"
        "  const inp=document.querySelector('#cmdk-input');"
        "  inp.value=q; inp.dispatchEvent(new Event('input',{bubbles:true})); await sleep(300);"
        "  const first=document.querySelector('#cmdk-list .cmdk-item'); if(first) first.click();"
        "  await sleep(1400);"
        "  out[q]=(document.querySelector('#preset')||{}).value||null;"
        "  const cm=document.querySelector('#cmdk'); if(cm && !cm.hidden){ const c=document.querySelector('#cmdk-close'); if(c) c.click(); }"
        "  await sleep(200);"
        "} return JSON.stringify(out);})()"
    )
    res = _eval(script)
    for q, expect in wanted.items():
        assert res.get(q) == expect, f"{q} should initialise preset {expect}, got {res.get(q)}"


def test_unavailable_features_are_never_presented_as_working():
    _pw("goto", BASE)
    time.sleep(6)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        "document.querySelector('#chart-search').click(); await sleep(2600);"
        "const inp=document.querySelector('#cmdk-input');"
        "inp.value='multi timeframe'; inp.dispatchEvent(new Event('input',{bubbles:true})); await sleep(300);"
        "const items=[...document.querySelectorAll('#cmdk-list .cmdk-item')];"
        "const first=items[0];"
        "return JSON.stringify({label:first?first.querySelector('.ci-label').textContent:null,"
        "  disabled:first?first.classList.contains('disabled'):null,"
        "  hint:first?(first.querySelector('.ci-hint')||{}).textContent:null});})()"
    )
    assert res["disabled"] is True, "an unimplemented feature must be listed disabled"
    assert res["hint"], "a disabled entry must explain why"


def test_search_does_not_break_the_chart_toolbar_after_navigation():
    _pw("goto", BASE)
    time.sleep(6)
    res = _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        "showView('charts'); document.querySelector('#symbol-input').value='NABIL';"
        "await loadChart(); await sleep(1500);"
        "document.querySelector('#chart-search').click(); await sleep(2400);"
        "const inp=document.querySelector('#cmdk-input');"
        "inp.value='seasonality'; inp.dispatchEvent(new Event('input',{bubbles:true})); await sleep(300);"
        "const first=document.querySelector('#cmdk-list .cmdk-item'); if(first) first.click();"
        "await sleep(1500);"
        "showView('charts'); viewShown('charts'); await sleep(800);"
        "return JSON.stringify({active: (document.querySelector('.view.active')||{}).id,"
        "  candleAlive: !!window.mtState.candleSeries, bars: (window.mtState.chartBars||[]).length,"
        "  toolbar: !!document.getElementById('chart-toolbar')});})()"
    )
    assert res["active"] == "view-charts"
    assert res["candleAlive"] is True, "the candle series must survive a search round-trip"
    assert res["bars"] > 0
    assert res["toolbar"] is True
