"""Static wiring checks for the reference-driven visualisation pass.

These are cheap, deterministic guards that run in the normal suite. They do NOT
prove the charts render — that is the job of ``tests/test_browser_viz_toolinfo.py``
(opt-in, real browser). They only pin the *wiring* so a later edit cannot quietly
unlink the visualisation module, drop a chart host from the markup, or stop
calling the shared tool-information renderer.

Everything asserted here is a structural fact about files in ``web/static``.
"""

from __future__ import annotations

import re

from megatool.config import WEB_DIR

INDEX = (WEB_DIR / "index.html").read_text(encoding="utf-8")
APP = (WEB_DIR / "app.js").read_text(encoding="utf-8")
VIZ = (WEB_DIR / "viz.js").read_text(encoding="utf-8")
CSS = (WEB_DIR / "styles.css").read_text(encoding="utf-8")


def test_viz_module_present_and_loaded():
    assert (WEB_DIR / "viz.js").exists(), "web/static/viz.js is the SVG visualisation module"
    assert re.search(r'<script src="/viz\.js\?v=[^"]+"></script>', INDEX), (
        "viz.js must be loaded by index.html"
    )
    assert "window.VIZ" in VIZ, "viz.js must expose window.VIZ"
    for fn in ("line", "bars", "donut", "gauge", "sparkline", "scatter", "empty"):
        assert re.search(rf"\b{fn}\b", VIZ), f"viz.js must define {fn}()"


def test_stylesheet_and_app_are_linked_with_cache_busters():
    assert re.search(r'<link rel="stylesheet" href="/styles\.css\?v=[^"]+"', INDEX)
    assert re.search(r'<script src="/app\.js\?v=[^"]+"></script>', INDEX)


def test_new_chart_hosts_exist_in_markup():
    for host_id in (
        "ov-gauge",  # market barometer gauge (overview)
        "ov-sector-chart",  # sector performance bars
        "ov-sector-donut",  # turnover-share donut
        "ov-fundmap",  # fundamental map scatter (P/E vs P/B)
        "bh-chart",  # breadth indicator chart
        "bh-chart-metric",  # breadth metric selector
        "sea-chart-months",  # seasonality month bars
        "sea-chart-weekdays",  # seasonality weekday bars
        "sea-chart-quarters",  # seasonality quarter bars
    ):
        assert f'id="{host_id}"' in INDEX, f"missing chart host #{host_id}"


def test_app_wires_viz_primitives_and_charts():
    for call in ("VIZ.line(", "VIZ.bars(", "VIZ.donut(", "VIZ.gauge(", "VIZ.scatter("):
        assert call in APP, f"app.js must call {call}"
    assert "renderBreadthChart" in APP
    assert "renderSeasonalityCharts" in APP
    assert "renderOverviewVisuals" in APP


def test_tool_information_panel_is_shared_and_wired():
    assert 'id="tool-info"' in INDEX, "the shared tool-information modal must exist"
    assert 'id="tool-info-body"' in INDEX
    assert 'id="preset-info-btn"' in INDEX, "screener preset needs an ⓘ control"
    assert 'id="bt-strategy-info-btn"' in INDEX, "backtest strategy needs an ⓘ control"
    assert "function toolInfoHtml" in APP
    assert "async function openToolInfo" in APP
    assert "function bindToolInfoModal" in APP
    assert "bindToolInfoModal()" in APP, "the modal must be bound at startup"


def test_indicator_compact_row_moves_params_behind_a_toggle():
    # The compact selector row keeps icon + name + ⓘ + essential actions and
    # hides parameters/apply/reset behind an expandable panel.
    row = APP.split("function indInstanceRowHtml", 1)[1].split("\n}", 1)[0]
    assert 'class="ii-extra"' in row
    assert 'data-ind-act="expand"' in row
    assert 'data-ind-act="info"' in row
    assert "indExpandedIds" in APP
    assert ".ind-inst .ii-extra" in CSS
