"""Browser regression tests for the BABA screens and the shared symbol picker.

The defects these cover are user-facing, so they are checked through the real
page and the real dev API rather than by calling the report hooks directly:

* GVL is a valid catalogue symbol and has stored quarterly records.
* The same autocomplete is used on Scanner and Quarterly Analysis, matches a
  company name case-insensitively, closes after selection, and never submits a
  partial query as a symbol.
* A sector report has the structured hierarchy and a scoped export.
* A missing quarterly record is an empty state, not an invalid symbol.

Opt-in, same harness as ``test_browser_draw_drag.py``:

    MEGATOOL_BROWSER_TESTS=1 MEGATOOL_BROWSER_BASE=http://127.0.0.1:10000/ \
        .venv/bin/python -m pytest tests/test_browser_baba_screens.py -q
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
SESSION = "mtbabatest"

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


def _show(view: str) -> None:
    _pw("goto", _fresh_url())
    time.sleep(4)
    _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        f"showView({view!r});viewShown({view!r});await sleep(1200);return true;}})()"
    )


def _pick_symbol(selector: str, query: str) -> dict:
    _pw("fill", selector, query)
    time.sleep(0.5)
    listed = _eval(
        "(()=>{const el=document.querySelector('#baba-sym-ac');"
        "return JSON.stringify({hidden: el && el.hidden,"
        " items: [...document.querySelectorAll('#baba-sym-ac .sym-ac-item')].map(n=>n.innerText),"
        " expanded: document.querySelector(%r).getAttribute('aria-expanded')});})()" % selector
    )
    assert listed["items"], f"no autocomplete matches for {query!r}: {listed}"
    assert any("GVL" in item for item in listed["items"]), listed
    _pw("press", "ArrowDown")
    _pw("press", "Enter")
    time.sleep(0.4)
    return _eval(
        "(()=>{const el=document.querySelector(%r);const ac=document.querySelector('#baba-sym-ac');"
        "return JSON.stringify({value: el.value, hidden: ac && ac.hidden,"
        " expanded: el.getAttribute('aria-expanded'),"
        " badge: el.closest('label') && el.closest('label').querySelector('.sym-picked')"
        "   ? el.closest('label').querySelector('.sym-picked').textContent : ''});})()" % selector
    )


def test_scanner_uses_the_shared_catalogue_and_finds_gvl_by_name():
    _show("baba/scanner")
    picked = _pick_symbol("#baba-scan-syms", "green ven")
    assert picked["value"] == "GVL"
    assert picked["hidden"] is True, "the list must close after a selection"
    assert picked["expanded"] == "false"
    assert "Green Ventures" in picked["badge"]

    _pw("click", "#baba-scan-go")
    time.sleep(5)
    res = _eval(
        "(()=>{const out=document.querySelector('#baba-scan-out');"
        "return JSON.stringify({text: out.innerText, err: document.querySelector('#baba-scan-error').textContent,"
        " scroll: out.scrollWidth, client: out.clientWidth});})()"
    )
    text = res["text"]
    assert "FUNDAMENTAL SCANNER" in text
    assert "GVL" in text and "Green Ventures" in text
    assert "Fourth Quarter 2025-2026" in text
    assert "13.02" in text
    assert "Not stored" in text, "missing metrics must be shown explicitly"
    assert "not live" in text.lower()
    assert "failed" not in res["err"].lower()
    assert "[object Object]" not in text and "undefined" not in text


def test_quarterly_analysis_shows_real_gvl_quarters_and_growth():
    _show("baba/quarterly")
    picked = _pick_symbol("#baba-q-sym", "gvl")
    assert picked["value"] == "GVL"
    assert picked["hidden"] is True
    time.sleep(5)
    res = _eval(
        "(()=>{const out=document.querySelector('#baba-q-out');"
        "return JSON.stringify({text: out.innerText, err: document.querySelector('#baba-q-error').textContent});})()"
    )
    text = res["text"]
    assert "QUARTERLY ANALYSIS" in text.upper()
    assert "GVL" in text
    assert "Fourth Quarter 2025-2026" in text
    assert "13.02" in text
    assert "Q4" in text and "present" in text
    assert "no stored quarterly filing" not in text.lower()
    assert "Stored-value check" in text, "an implausible stored per-share value must be disclosed"
    assert "[object Object]" not in text
    assert "error" not in res["err"].lower()


def test_sector_report_has_hierarchy_and_a_scoped_export():
    _pw("goto", _fresh_url())
    time.sleep(4)
    _eval(
        "(async()=>{const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));"
        "BABA.sector='Finance Companies';showView('baba/sector');viewShown('baba/sector');"
        "await sleep(4500);return true;})()"
    )
    res = _eval(
        "(()=>{const out=document.querySelector('#baba-sector-report');"
        "return JSON.stringify({text: out.innerText, scroll: out.scrollWidth, client: out.clientWidth,"
        " tables: out.querySelectorAll('table').length,"
        " sections: [...out.querySelectorAll('h2,h3')].length,"
        " bodyMax: getComputedStyle(document.querySelector('#baba-body')).maxHeight,"
        " exportButton: !!document.querySelector('#baba-sector-export')});})()"
    )
    text = res["text"]
    assert "SECTOR REPORT" in text.upper()
    assert "Finance Companies" in text
    assert "COMPANIES" in text.upper()
    assert "Best Finance Company" in text, "company names should be readable"
    assert "Coverage and data quality" in text
    assert "Company-by-company comparison" in text
    assert "Data-quality notes" in text
    assert "Report generated" in text
    assert res["tables"] >= 2
    assert res["sections"] >= 5, "the report should expose its full hierarchy, not a clipped top slice"
    assert res["bodyMax"] == "none", "the BABA page must scroll normally; tables scroll inside their own wrappers"
    assert res["exportButton"] is True
    assert res["scroll"] <= res["client"] + 2, "the page itself must not overflow; tables scroll inside their wrapper"
    assert "[object Object]" not in text and "raw" not in text.lower()

    exported = _eval(
        "(async()=>{const syms=(BABA_SECTORS.by['Finance Companies']||[]);"
        "const q=new URLSearchParams({components:'sector_overview,sector_comparison',"
        " symbols:syms.join(','),sector:'Finance Companies',format:'json'});"
        "const r=await fetch(API_BASE+'/api/baba/report/export?'+q.toString(),_withFriendToken({}));"
        "const text=await r.text();let data=null;try{data=JSON.parse(text)}catch(e){}"
        "return JSON.stringify({status:r.status,type:r.headers.get('content-type'),data});})()"
    )
    assert exported["status"] == 200, exported
    data = exported["data"]
    assert data["sector"] == "Finance Companies"
    overview = data["sections"]["sector_overview"]
    assert [r[0] for r in overview["rows"]] == ["Finance Companies"]
    assert set(data["sections"]) <= {"sector_overview", "sector_comparison"}


def test_partial_symbol_is_not_submitted_as_a_valid_symbol():
    _show("baba/scanner")
    _pw("fill", "#baba-scan-syms", "ZZZZ")
    time.sleep(0.4)
    _pw("click", "#baba-scan-go")
    time.sleep(0.6)
    res = _eval(
        "(()=>JSON.stringify({err: document.querySelector('#baba-scan-error').textContent,"
        " out: document.querySelector('#baba-scan-out').innerText}))()"
    )
    assert "not in the stored symbol catalogue" in res["err"].lower()
    assert "ZZZZ" in res["err"]
    assert "FUNDAMENTAL SCANNER" not in res["out"].upper()


def test_autocomplete_is_accessible_and_closes_on_outside_click():
    _show("baba/scanner")
    _pw("fill", "#baba-scan-syms", "zzzz")
    time.sleep(0.4)
    open_state = _eval(
        "(()=>{const el=document.querySelector('#baba-scan-syms');const ac=document.querySelector('#baba-sym-ac');"
        "return JSON.stringify({expanded:el.getAttribute('aria-expanded'),"
        " controls:el.getAttribute('aria-controls'), hidden:ac.hidden,"
        " text:ac.innerText, role:el.getAttribute('role')});})()"
    )
    assert open_state["role"] == "combobox"
    assert open_state["expanded"] == "true"
    assert open_state["controls"] == "baba-sym-ac"
    assert open_state["hidden"] is False
    assert "No stored symbol matches" in open_state["text"]

    _pw("click", "#baba-scan-sector")
    time.sleep(0.2)
    closed = _eval(
        "(()=>{const el=document.querySelector('#baba-scan-syms');const ac=document.querySelector('#baba-sym-ac');"
        "return JSON.stringify({expanded:el.getAttribute('aria-expanded'),hidden:ac.hidden});})()"
    )
    assert closed["expanded"] == "false"
    assert closed["hidden"] is True
