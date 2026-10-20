"""Full research reports for one or many NEPSE symbols.

This module is the "Research Studio" behind the existing Research view. It does
not invent a second analytics stack: every figure comes from the same
:mod:`megatool.report_builder` components and the same market store that the
rest of the application uses, plus :mod:`megatool.volatility` for the
next-session range forecast.

Outputs
-------
* **XLSX** — one worksheet per selected component (single symbol) or one sheet
  per component with a ``Symbol`` column (many symbols). Chart components become
  native, editable Excel charts. A ``Report`` sheet states provenance and a
  ``Unavailable`` sheet names every selected component that had no data.
* **PDF** — a printable document with a cover, every selected section, real
  chart images and the unavailable-analysis disclosure.
* **ZIP** — the combined PDF + combined XLSX + combined JSON, one XLSX and one
  PDF per symbol, and a README describing exactly what is inside.
* **JSON** — the assembled data, for programmatic use.

No journal or portfolio component is ever included by a job: a research report
is public-market analysis. The API additionally strips those categories from
requests made by a non-loopback client.

Progress is reported by the caller's callback after each unit of work that
actually completed (one symbol assembled, one workbook written, ...). Nothing
here sleeps or estimates a percentage from elapsed time.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from megatool import report_builder as rb
from megatool.volatility import VolatilityError, volatility_report

__all__ = [
    "RESEARCH_PRESETS",
    "PUBLIC_CATEGORIES",
    "PRIVATE_CATEGORIES",
    "MAX_RESEARCH_SYMBOLS",
    "MAX_RESEARCH_COMPONENTS",
    "research_catalog",
    "clean_components",
    "clean_symbols",
    "build_bundle",
    "render_bundle_xlsx",
    "render_bundle_pdf",
    "render_bundle_json",
    "render_bundle_zip",
    "render_symbol_xlsx",
    "render_symbol_pdf",
]

MAX_RESEARCH_SYMBOLS = 25
MAX_RESEARCH_COMPONENTS = 80

#: Categories that contain personal records and are never part of a research
#: report job (and are stripped from non-loopback API requests).
PRIVATE_CATEGORIES = ("K_journal", "L_portfolio")
PUBLIC_CATEGORIES = tuple(
    cid for cid, _name in rb.COMPONENT_CATEGORIES if cid not in PRIVATE_CATEGORIES
)

_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,19}$")

RESEARCH_PRESETS: dict[str, dict[str, Any]] = {
    "snapshot": {
        "label": "Company snapshot",
        "description": "Identity, price, valuation and the key fundamental ratios.",
        "components": [
            "profile", "data_coverage", "last_price", "price_summary", "market_cap",
            "range_52w", "price_change", "eps_ttm", "net_worth_ps", "pe_ratio",
            "pb_ratio", "dividend_yield", "fundamental_summary", "r_volatility",
            "q_sources", "q_missing", "c_price",
        ],
    },
    "fundamental": {
        "label": "Fundamental deep dive",
        "description": "Quarterly and annual statements, ratios, growth, valuation and dividends.",
        "components": [
            "profile", "market_cap", "shares_outstanding", "paid_up_capital",
            "eps_quarterly", "eps_annual", "eps_ttm", "net_worth_ps", "revenue",
            "net_profit", "profit_margin", "earnings_growth", "revenue_growth",
            "roe", "roa", "pe_ratio", "pb_ratio", "dps", "dividend_yield",
            "fundamental_trend", "fundamental_summary", "fundamental_quality",
            "q1_results", "q2_results", "q3_results", "q4_results",
            "q_eps_comparison", "q_profit_comparison", "yoy_growth", "seq_growth",
            "annual_summary", "comparability", "pe_analysis", "pb_analysis",
            "divyield_analysis", "valuation_limits", "div_history", "div_cash",
            "div_bonus", "div_consistency", "c_eps_trend", "c_profit_trend",
            "c_revenue_trend", "c_dividend", "q_period_coverage", "q_missing",
        ],
    },
    "technical": {
        "label": "Technical and risk",
        "description": "Trend, momentum, levels, patterns, multi-timeframe, risk and charts.",
        "components": [
            "profile", "data_coverage", "last_price", "price_summary", "range_52w",
            "price_change", "volume_turnover", "liquidity", "trend", "perf_multi",
            "ma", "rsi", "macd", "volatility", "volume_analysis", "support_resistance",
            "fibonacci", "candlestick", "patterns", "mtf_trend", "ta_summary",
            "technical_warnings", "r_volatility", "r_drawdown", "r_distribution",
            "r_downside", "r_gaps", "r_liquidity_risk", "r_coverage", "c_price",
            "c_volume", "c_technical", "c_risk", "q_sources", "q_missing",
        ],
    },
    "risk": {
        "label": "Risk pack",
        "description": "Volatility, drawdown, tails, gaps and next-session range forecast.",
        "components": [
            "profile", "data_coverage", "last_price", "price_summary", "volatility",
            "r_volatility", "r_drawdown", "r_distribution", "r_downside", "r_gaps",
            "r_liquidity_risk", "r_coverage", "r_correlation", "c_price", "c_risk",
            "technical_warnings", "q_sources", "q_freshness", "q_missing",
        ],
    },
    "full": {
        "label": "Full research report",
        "description": (
            "Every public analysis category: identity, market, fundamentals, "
            "quarterly, valuation, eligibility, sector, technical, dividend, risk, "
            "charts and data quality."
        ),
        "components": [
            # identity + market
            "profile", "data_coverage", "last_price", "price_summary", "market_cap",
            "range_52w", "price_change",
            # fundamentals
            "eps_quarterly", "eps_annual", "eps_ttm", "net_worth_ps", "revenue",
            "net_profit", "profit_margin", "earnings_growth", "revenue_growth",
            "roe", "roa", "pe_ratio", "pb_ratio", "dps", "dividend_yield",
            "fundamental_trend", "fundamental_summary", "fundamental_quality",
            # quarterly
            "q1_results", "q2_results", "q3_results", "q4_results",
            "q_eps_comparison", "q_profit_comparison", "yoy_growth", "seq_growth",
            "annual_summary", "comparability",
            # valuation + eligibility
            "pe_analysis", "pb_analysis", "divyield_analysis", "valuation_limits",
            "elig_result", "elig_failed",
            # sector
            "sector_overview", "sector_outliers",
            # technical
            "trend", "perf_multi", "ma", "rsi", "macd", "volatility",
            "volume_analysis", "support_resistance", "fibonacci", "candlestick",
            "patterns", "mtf_trend", "ta_summary", "technical_warnings",
            # dividend
            "div_history", "div_cash", "div_bonus", "div_consistency",
            # risk
            "r_volatility", "r_drawdown", "r_distribution", "r_downside", "r_gaps",
            "r_liquidity_risk", "r_coverage",
            # charts
            "c_price", "c_volume", "c_eps_trend", "c_profit_trend",
            "c_revenue_trend", "c_dividend", "c_risk", "c_technical",
            # quality
            "q_sources", "q_missing", "q_formulas", "q_unavailable",
        ],
    },
}


def _normalise(symbols: list[str]) -> list[str]:
    out: list[str] = []
    bad: list[str] = []
    for raw in symbols or []:
        s = str(raw).strip().upper()
        if not s:
            continue
        if not _SYMBOL_RE.match(s):
            bad.append(s)
            continue
        if s not in out:
            out.append(s)
    if bad:
        raise ValueError("invalid symbol(s): " + ", ".join(bad[:5]))
    return out


def clean_symbols(symbols: list[str]) -> list[str]:
    """Validate and de-duplicate symbols; raises ValueError on an invalid one."""
    return _normalise(symbols)


def clean_components(components: list[str] | None, *, allow_private: bool = False) -> list[str]:
    """Validate ids, drop private categories unless explicitly allowed, dedupe."""
    raw = list(components or [])
    if len(raw) > MAX_RESEARCH_COMPONENTS:
        raise ValueError(f"too many components (max {MAX_RESEARCH_COMPONENTS})")
    reg = rb._registry()  # noqa: SLF001 - the public accessor is heavier
    chosen: list[str] = []
    for cid in raw:
        c = reg.get(str(cid))
        if c is None:
            raise ValueError(f"unknown component {cid!r}")
        if not allow_private and c.category in PRIVATE_CATEGORIES:
            continue
        if cid not in chosen:
            chosen.append(cid)
    if len(chosen) > MAX_RESEARCH_COMPONENTS:
        raise ValueError(f"too many components (max {MAX_RESEARCH_COMPONENTS})")
    return chosen


def research_catalog(*, allow_private: bool = False) -> dict[str, Any]:
    """Everything the selection UI needs: components, categories and presets."""
    reg = rb._registry()  # noqa: SLF001
    categories = [
        {"id": cid, "name": name}
        for cid, name in rb.COMPONENT_CATEGORIES
        if allow_private or cid not in PRIVATE_CATEGORIES
    ]
    components = [
        {
            "id": c.id,
            "name": c.name,
            "category": c.category,
            "description": c.description,
            "output": c.output,
            "available": c.available,
            "reason": c.reason,
        }
        for c in reg.values()
        if allow_private or c.category not in PRIVATE_CATEGORIES
    ]
    presets = []
    for key, p in RESEARCH_PRESETS.items():
        comps = clean_components(p["components"], allow_private=allow_private)
        presets.append({
            "id": key, "label": p["label"], "description": p["description"],
            "components": comps,
            "count": len(comps),
        })
    return {
        "categories": categories,
        "components": components,
        "presets": presets,
        "default_preset": "full",
        "max_symbols": MAX_RESEARCH_SYMBOLS,
        "max_components": MAX_RESEARCH_COMPONENTS,
        "private_excluded": [] if allow_private else list(PRIVATE_CATEGORIES),
        "note": (
            "Every selected component is computed independently and appears in "
            "every output. A component whose data is absent is listed as "
            "unavailable with its reason; it is never replaced with an invented value."
        ),
    }


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def _volatility_sections(symbol: str, store: Any, *,
                         risk_budget: float | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Two real report sections built from :mod:`megatool.volatility`."""
    try:
        df = store.get_bars(symbol)
        vol = volatility_report(df, symbol, risk_budget=risk_budget)
    except (VolatilityError, KeyError, ValueError) as exc:
        reason = f"next-session range forecast unavailable: {exc}"
        return (
            {"name": "Next-session range forecast", "available": False, "reason": reason},
            {"name": "Range-forecast evaluation", "available": False, "reason": reason},
        )
    fc = vol["forecast"]
    ev = vol["evaluation"]
    rows = [
        ["As-of session", fc["as_of_session"]],
        ["Price basis", fc["price_kind"]],
        ["Point range forecast (next session)", fc["point_range"]],
        ["Point as % of last close", fc["point_range_percent_of_price"]],
        ["80% band (points)", f'{fc["band_80"][0]} - {fc["band_80"][1]}'],
        ["80% band (% of close)", f'{fc["band_80_percent_of_price"][0]} - '
                                 f'{fc["band_80_percent_of_price"][1]}'],
        ["Band method", fc.get("band_80_method", "")],
        ["60-session median range", fc["normal_range_60_session_median"]],
        ["Forecast / normal", fc["ratio_to_normal"]],
        ["Selected model", fc["model"]],
        ["Measured interval coverage (%)", fc["measured_interval_coverage_percent"]],
        ["History", f'{fc["history_first"]} to {fc["as_of_session"]} ({fc["history_bars"]} bars)'],
    ]
    if risk_budget:
        for row in vol.get("position_sizing", {}).get("table", []):
            rows.append([f"Sizing at {row['label']}",
                         f'{row["shares"]} shares, stop {row["stop_distance"]}, '
                         f'notional {row["notional"]}, max loss {row["max_loss_at_stop"]}'])
    fc_section = {
        "name": "Next-session range forecast",
        "available": True,
        "output": "table",
        "headers": ["Item", "Value"],
        "rows": rows,
        "methodology": "Walk-forward volatility models on stored OHLC bars; see the evaluation table.",
    }
    eval_rows = []
    for name, m in ev["models"].items():
        eval_rows.append([
            name, m["n"], m["mae"], m["rmse"], m["median_ape_percent"],
            m["improvement_vs_naive_percent"], m["interval_coverage_percent"],
        ])
    ev_section = {
        "name": "Range-forecast evaluation",
        "available": True,
        "output": "table",
        "headers": ["Model", "Observations", "MAE (points)", "RMSE", "Median APE (%)",
                    "Improvement vs naive (%)", "80% coverage (%)"],
        "rows": eval_rows,
        "methodology": (
            f'{ev["evaluation"]["method"]}; targets {ev["evaluation"]["first_target"]} '
            f'to {ev["evaluation"]["last_target"]}. No figure is borrowed from another market.'
        ),
        "note": ev["note"],
    }
    return fc_section, ev_section


def build_bundle(
    symbols: list[str],
    components: list[str] | None = None,
    *,
    title: str | None = None,
    notes: str | None = None,
    risk_budget: float | None = None,
    progress: Callable[[int, str, str], None] | None = None,
    allow_private: bool = False,
    store: Any = None,
) -> dict[str, Any]:
    """Assemble one research bundle. Raises ValueError on invalid input.

    ``progress(done_steps, stage, message)`` is called after each symbol has
    been fully assembled. The caller decides the total step count.
    """
    syms = _normalise(symbols)
    if not syms:
        raise ValueError("select at least one symbol")
    if len(syms) > MAX_RESEARCH_SYMBOLS:
        raise ValueError(f"too many symbols (max {MAX_RESEARCH_SYMBOLS})")
    chosen = clean_components(components, allow_private=allow_private)
    if not chosen:
        raise ValueError("select at least one analysis component")

    from megatool.market_store import MarketStore

    store = store or MarketStore()
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    data: dict[str, Any] = {}
    all_unavailable: dict[str, dict[str, Any]] = {}
    missing_symbols: list[dict[str, str]] = []

    for idx, sym in enumerate(syms, start=1):
        req = rb.ReportRequest(
            components=chosen,
            symbols=[sym],
            fmt="json",
            title=title or f"Research report: {sym}",
            notes=notes,
        )
        try:
            report = rb.assemble_report(req)
        except Exception as exc:  # noqa: BLE001 - one symbol must not kill the job
            missing_symbols.append({"symbol": sym, "reason": f"{type(exc).__name__}: {exc}"})
            if progress:
                progress(idx, "assembling", f"{sym}: failed ({exc})")
            continue
        fc, ev = _volatility_sections(sym, store, risk_budget=risk_budget)
        report["sections"]["volatility_forecast"] = fc
        report["sections"]["volatility_evaluation"] = ev
        # Surface the volatility sections' own unavailability in the disclosure.
        for key, sec in (("volatility_forecast", fc), ("volatility_evaluation", ev)):
            if not sec.get("available", True):
                report["quality"]["unavailable"].append(
                    {"id": key, "name": sec["name"], "reason": sec.get("reason", "")}
                )
        data[sym] = report
        for item in report["quality"]["unavailable"]:
            all_unavailable[item["id"]] = item
        if progress:
            progress(idx, "assembling", f"{sym}: {len(report['sections'])} sections assembled")

    if not data:
        reasons = "; ".join(f"{m['symbol']}: {m['reason']}" for m in missing_symbols)
        raise ValueError(f"no symbol could be assembled ({reasons})")

    return {
        "title": title or "PRAVAHA research report",
        "generated_at": generated,
        "symbols": [s for s in syms if s in data],
        "requested_symbols": syms,
        "components": chosen,
        "notes": notes,
        "as_of": generated[:10],
        "risk_budget": risk_budget,
        "symbols_data": data,
        "quality": {
            "unavailable": list(all_unavailable.values()),
            "missing_symbols": missing_symbols,
            "price_kind": "stored end-of-day bars, not live quotes",
        },
        "methodology": (
            "Sections are the same registry components used by the BABA report "
            "builder. Fundamentals, sectors, technicals and risk call the same "
            "modules as the rest of the app. The range forecast is evaluated "
            "walk-forward on stored NEPSE bars only."
        ),
        "caveats": [
            "Stored historical data, not live quotes.",
            "Prices are unadjusted for bonus/split issues unless a section says otherwise.",
            "No section is investment advice or a trading signal.",
            "Unavailable analyses are named with a reason and never filled with estimates.",
        ],
    }


# --------------------------------------------------------------------------- #
# Helpers shared by renderers
# --------------------------------------------------------------------------- #
def _rows(section: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    if not section.get("available", True):
        return ["Status"], [[section.get("reason", "unavailable")]]
    if "headers" in section and "rows" in section:
        return [str(h) for h in section["headers"]], [list(r) for r in section["rows"]]
    if isinstance(section.get("table"), dict):
        t = section["table"]
        return [str(h) for h in t.get("headers", [])], [list(r) for r in t.get("rows", [])]
    return ["Value"], [[json.dumps(section, default=str)[:500]]]


def _safe_sheet(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", str(name)).strip() or "Sheet"
    base = base[:31]
    out = base
    n = 2
    while out.lower() in used:
        suffix = f" {n}"
        out = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(out.lower())
    return out


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if value != value:
            return "-"
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (list, tuple)):
        return ", ".join(_fmt(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, default=str)
    return str(value)


def _chart(section: dict[str, Any]) -> tuple[bytes, int, int] | None:
    from megatool.chartimg import chart_from_section

    return chart_from_section(section, width=760, height=300)


def _unavailable(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return list(bundle.get("quality", {}).get("unavailable", []))


def _symbol_report(bundle: dict[str, Any], symbol: str) -> dict[str, Any]:
    return bundle["symbols_data"][symbol]


# --------------------------------------------------------------------------- #
# XLSX
# --------------------------------------------------------------------------- #
def render_symbol_xlsx(bundle: dict[str, Any], symbol: str) -> bytes:
    """One workbook for one symbol: a sheet per selected component."""
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    report = _symbol_report(bundle, symbol)
    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    head_fill = PatternFill("solid", fgColor="071C18")
    head_font = Font(bold=True, color="F5F8F7")

    meta = wb.create_sheet(_safe_sheet("Report", used))
    for row in [
        ("Title", bundle.get("title", "")),
        ("Symbol", symbol),
        ("Generated", bundle.get("generated_at", "")),
        ("Sections", len(report["sections"])),
        ("Price basis", bundle["quality"].get("price_kind", "")),
        ("Source note", "Computed from the application's stored market and fundamental records."),
        ("Caveat", "Not live quotes. Not investment advice."),
    ]:
        meta.append(list(row))
    for cell in meta[1]:
        cell.fill = head_fill
        cell.font = head_font
    meta.column_dimensions["A"].width = 22
    meta.column_dimensions["B"].width = 90
    meta.freeze_panes = "A2"

    for cid, section in report["sections"].items():
        if not section.get("available", True):
            continue
        ws = wb.create_sheet(_safe_sheet(str(section.get("name") or cid), used))
        headers, rows = _rows(section)
        headers = headers or ["Value"]
        ws.append(headers)
        for row in rows:
            ws.append([(_fmt(v) if not isinstance(v, (int, float)) else v) for v in row])
        for cell in ws[1]:
            cell.fill = head_fill
            cell.font = head_font
        ws.freeze_panes = "A2"
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
        for idx, h in enumerate(headers, start=1):
            width = max([len(str(h))] + [len(_fmt(r[idx - 1])) for r in rows[:300] if len(r) >= idx])
            ws.column_dimensions[get_column_letter(idx)].width = min(max(width + 2, 10), 70)
        if section.get("output") == "chart" and len(headers) >= 2 and len(rows) >= 2:
            chart = BarChart() if (section.get("chart") or {}).get("kind") == "bar" else LineChart()
            chart.title = str(section.get("name") or cid)
            chart.height, chart.width = 8, 18
            data_ref = Reference(ws, min_col=2, min_row=1, max_row=len(rows) + 1)
            chart.add_data(data_ref, titles_from_data=True)
            ws.add_chart(chart, f"{get_column_letter(len(headers) + 2)}2")
        if section.get("methodology"):
            ws.cell(row=len(rows) + 3, column=1, value="Method").font = Font(bold=True)
            ws.cell(row=len(rows) + 3, column=2, value=str(section["methodology"]))

    un = [u for u in _unavailable(bundle) if u.get("id") in report["sections"]
          or u.get("id", "").startswith("volatility_")]
    if un:
        ws = wb.create_sheet(_safe_sheet("Unavailable", used))
        ws.append(["Component", "Reason"])
        for item in un:
            ws.append([item.get("name", item.get("id")), item.get("reason", "")])
        for cell in ws[1]:
            cell.fill = head_fill
            cell.font = head_font
        ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render_bundle_xlsx(bundle: dict[str, Any]) -> bytes:
    """A workbook for the whole bundle.

    One symbol keeps the per-component sheet layout. Many symbols use one sheet
    per component with a leading ``Symbol`` column, so a 25-symbol report stays
    a normal-sized workbook instead of 1,500 sheets.
    """
    if len(bundle["symbols"]) == 1:
        return render_symbol_xlsx(bundle, bundle["symbols"][0])

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    head_fill = PatternFill("solid", fgColor="071C18")
    head_font = Font(bold=True, color="F5F8F7")

    meta = wb.create_sheet(_safe_sheet("Report", used))
    for row in [
        ("Title", bundle.get("title", "")),
        ("Symbols", ", ".join(bundle["symbols"])),
        ("Generated", bundle.get("generated_at", "")),
        ("Components", len(bundle.get("components", []))),
        ("Price basis", bundle["quality"].get("price_kind", "")),
        ("Caveat", "Not live quotes. Not investment advice."),
    ]:
        meta.append(list(row))
    for cell in meta[1]:
        cell.fill = head_fill
        cell.font = head_font
    meta.column_dimensions["A"].width = 22
    meta.column_dimensions["B"].width = 90

    # Gather each component across symbols.
    by_component: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for sym in bundle["symbols"]:
        for cid, section in _symbol_report(bundle, sym)["sections"].items():
            by_component.setdefault(cid, []).append((sym, section))

    for cid, entries in by_component.items():
        available = [(s, sec) for s, sec in entries if sec.get("available", True)]
        if not available:
            continue
        name = available[0][1].get("name") or cid
        ws = wb.create_sheet(_safe_sheet(str(name), used))
        headers, _first_rows = _rows(available[0][1])
        ws.append(["Symbol", *headers])
        for sym, section in available:
            _h, rows = _rows(section)
            for row in rows:
                ws.append([sym, *[(_fmt(v) if not isinstance(v, (int, float)) else v) for v in row]])
        for cell in ws[1]:
            cell.fill = head_fill
            cell.font = head_font
        ws.freeze_panes = "B2"
        if ws.max_row > 1:
            ws.auto_filter.ref = f"A1:{get_column_letter(max(2, len(headers) + 1))}{ws.max_row}"
        for idx in range(1, len(headers) + 2):
            ws.column_dimensions[get_column_letter(idx)].width = 18 if idx == 1 else 28

    un = _unavailable(bundle)
    if un:
        ws = wb.create_sheet(_safe_sheet("Unavailable", used))
        ws.append(["Component", "Reason"])
        for item in un:
            ws.append([item.get("name", item.get("id")), item.get("reason", "")])
        for cell in ws[1]:
            cell.fill = head_fill
            cell.font = head_font

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def _pdf_blocks_for_symbol(bundle: dict[str, Any], symbol: str, *,
                           cover: bool = True, max_rows: int = 400) -> list[dict[str, Any]]:
    from megatool.pdfwriter import wrap

    report = _symbol_report(bundle, symbol)
    blocks: list[dict[str, Any]] = []

    def text(s: str, size: int = 9, gap: float = 3) -> None:
        blocks.append({"type": "text", "text": str(s), "size": int(size), "gap": gap})

    if cover:
        text(bundle.get("title", "PRAVAHA research report"), 20, 8)
        text(f"Symbol: {symbol}", 14, 6)
        text(f"Generated: {bundle.get('generated_at', '')}", 9)
        text("Data: stored end-of-day records. Not live quotes. Not investment advice.", 9)
        text(f"Sections: {len(report['sections'])}  |  "
             f"Unavailable: {len(report['quality'].get('unavailable', []))}", 9)
        if bundle.get("notes"):
            for ln in wrap(str(bundle["notes"]), width=105):
                text(ln, 9)
        blocks.append({"type": "pagebreak"})

    for cid, section in report["sections"].items():
        if not section.get("available", True):
            continue
        text(str(section.get("name") or cid), 13, 6)
        if section.get("methodology"):
            for ln in wrap(f"Method: {section['methodology']}", width=118):
                text(ln, 7, 2)
        headers, rows = _rows(section)
        text(" | ".join(str(h) for h in headers), 8, 3)
        shown = rows[:max_rows]
        for row in shown:
            for ln in wrap(" | ".join(_fmt(v) for v in row), width=118):
                text(ln, 8, 2)
        if len(rows) > max_rows:
            text(f"... {len(rows) - max_rows} more row(s) are in the XLSX export.", 8, 3)
        if section.get("output") == "chart":
            img = _chart(section)
            if img:
                rgb, w, h = img
                blocks.append({"type": "image", "rgb": rgb, "width": w, "height": h,
                               "draw_width": 500, "draw_height": 197})
        blocks.append({"type": "spacer", "height": 10})

    un = [u for u in _unavailable(bundle) if u.get("id") in report["sections"]
          or u.get("id", "").startswith("volatility_")]
    if un:
        text("Unavailable analyses", 13, 6)
        text("These were selected but could not be computed. No substitute value was invented.", 8)
        for item in un:
            for ln in wrap(f"{item.get('name', item.get('id'))}: {item.get('reason', '')}", width=118):
                text(ln, 8, 2)
    return blocks


def render_bundle_pdf(bundle: dict[str, Any], *, max_rows: int = 400) -> bytes:
    """One printable PDF containing every selected symbol and section."""
    from megatool.pdfwriter import write_pdf_blocks

    blocks: list[dict[str, Any]] = []
    first = True
    for sym in bundle["symbols"]:
        if not first:
            blocks.append({"type": "pagebreak"})
        blocks.extend(_pdf_blocks_for_symbol(bundle, sym, cover=first, max_rows=max_rows))
        first = False
    if not blocks:
        blocks = [{"type": "text", "text": "PRAVAHA research report", "size": 12}]
    return write_pdf_blocks(blocks)


def render_symbol_pdf(bundle: dict[str, Any], symbol: str) -> bytes:
    from megatool.pdfwriter import write_pdf_blocks

    return write_pdf_blocks(_pdf_blocks_for_symbol(bundle, symbol, cover=True))


# --------------------------------------------------------------------------- #
# JSON / ZIP
# --------------------------------------------------------------------------- #
def render_bundle_json(bundle: dict[str, Any]) -> bytes:
    return json.dumps(bundle, indent=2, default=str, ensure_ascii=False).encode("utf-8")


def render_bundle_csv(bundle: dict[str, Any]) -> bytes:
    """A ZIP of one CSV per component for each symbol (plus a manifest)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = ["PRAVAHA research export",
                    f"Generated: {bundle.get('generated_at', '')}",
                    f"Symbols: {', '.join(bundle['symbols'])}",
                    f"Price basis: {bundle['quality'].get('price_kind', '')}", ""]
        for sym in bundle["symbols"]:
            for cid, section in _symbol_report(bundle, sym)["sections"].items():
                if not section.get("available", True):
                    continue
                headers, rows = _rows(section)
                text = io.StringIO()
                writer = csv.writer(text)
                writer.writerow(headers)
                for row in rows:
                    writer.writerow([_fmt(v) for v in row])
                name = f"{sym}/{re.sub(r'[^A-Za-z0-9._-]+', '_', cid)}.csv"
                zf.writestr(name, text.getvalue())
                manifest.append(f"{name}  ({len(rows)} rows)")
        un = _unavailable(bundle)
        if un:
            text = io.StringIO()
            writer = csv.writer(text)
            writer.writerow(["Component", "Reason"])
            for item in un:
                writer.writerow([item.get("name", item.get("id")), item.get("reason", "")])
            zf.writestr("_unavailable.csv", text.getvalue())
        zf.writestr("_manifest.txt", "\n".join(manifest) + "\n")
    return buf.getvalue()


def _readme(bundle: dict[str, Any]) -> str:
    return "\n".join([
        "PRAVAHA research package",
        "========================",
        f"Generated: {bundle.get('generated_at', '')}",
        f"Symbols: {', '.join(bundle['symbols'])}",
        f"Components: {len(bundle.get('components', []))}",
        "",
        "Contents",
        "--------",
        "  research-report.pdf          combined PDF, every selected symbol",
        "  research-report.xlsx         combined workbook, one sheet per component",
        "  research-report.json         the assembled data",
        "  research-data.zip            one CSV per component, per symbol",
        "  <SYMBOL>/<SYMBOL>-research.xlsx",
        "  <SYMBOL>/<SYMBOL>-research.pdf",
        "",
        "Data policy",
        "-----------",
        "  Every figure is computed from the application's stored records.",
        "  Prices are end-of-day, not live quotes. Not investment advice.",
        "  A selected analysis with no data is listed as unavailable with a reason.",
        "",
        "Caveats",
        "-------",
        *[f"  - {c}" for c in bundle.get("caveats", [])],
        "",
    ])


def render_bundle_zip(bundle: dict[str, Any],
                      parts: dict[str, dict[str, bytes]] | None = None) -> bytes:
    """The complete package: combined files + one report per symbol.

    ``parts`` may supply already-rendered ``{"xlsx": bytes, "pdf": bytes}`` for
    a symbol, so a job that rendered them for progress reporting does not pay
    for the same work twice.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", _readme(bundle))
        zf.writestr("research-report.pdf", render_bundle_pdf(bundle))
        zf.writestr("research-report.xlsx", render_bundle_xlsx(bundle))
        zf.writestr("research-report.json", render_bundle_json(bundle))
        zf.writestr("research-data.zip", render_bundle_csv(bundle))
        for sym in bundle["symbols"]:
            ready = (parts or {}).get(sym, {})
            xlsx = ready.get("xlsx") or render_symbol_xlsx(bundle, sym)
            pdf = ready.get("pdf") or render_symbol_pdf(bundle, sym)
            zf.writestr(f"{sym}/{sym}-research.xlsx", xlsx)
            zf.writestr(f"{sym}/{sym}-research.pdf", pdf)
    return buf.getvalue()
