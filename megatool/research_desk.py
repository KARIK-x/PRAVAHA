"""Evidence-bound AI research desk (mission Phase D / NF-015).

The desk assembles a bundle of *real* observations and calculations from the
project's own stores, then (only if the owner has configured a provider) asks a
model to reason over that bundle. The model is instructed to cite an evidence id
for every factual or numerical claim and to classify each conclusion.

Two rules are structural, not prompt-level:

* the bundle is built **before** the model is called, and the review step checks
  every number in the answer against the bundle; unmatched numbers are flagged,
  never silently accepted;
* the desk has no path to the portfolio ledger or the order path -- it cannot
  place a trade or mutate a position.

When no provider is configured the desk still returns the evidence bundle plus an
explicit "AI unavailable" error, so the research tools remain usable offline.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from megatool import llm

#: Phrases that indicate a stronger conclusion than observational data supports.
_OVERCLAIM = re.compile(
    r"\b(guaranteed|guarantee|certain(?:ly)?|risk[- ]free|will definitely|"
    r"always (?:rise|fall|increase|decrease)|never (?:fall|rise)|promise[sd]?)\b",
    re.IGNORECASE,
)
_CAUSAL = re.compile(
    r"\b(because of|due to|caused by|will lead to|therefore .{0,40} will|"
    r"proves? that|as a result, .{0,30} will)\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_CLAIM_TAGS = (
    "verified fact", "direct calculation", "estimate", "hypothesis",
    "interpretation", "unknown", "unsupported",
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@contextmanager
def _using_store(store: Any):
    """Temporarily point the catalogue at the supplied store (API reuse)."""
    if store is None:
        yield
        return
    from megatool import catalog

    prev = catalog.store_provider()
    catalog.set_store_provider(lambda: store)
    try:
        yield
    finally:
        catalog.set_store_provider(prev)


def _item(kind: str, label: str, value: Any, *, unit: str = "", as_of: str | None = None,
          source: str = "", calculation: str = "", dataset: str = "",
          quality: str = "ok", limitations: str = "") -> dict[str, Any]:
    return {
        "kind": kind,          # fact | calculation
        "label": label,
        "value": value,
        "unit": unit,
        "as_of": as_of,
        "source": source,
        "calculation": calculation,
        "dataset": dataset,
        "quality": quality,
        "limitations": limitations,
    }


def build_evidence(symbol: str, *, store: Any = None) -> dict[str, Any]:
    """Collect the real evidence bundle for a symbol. Never invents a value."""
    from megatool import catalog
    from megatool.fundamentals import query_symbol
    from megatool.db import get_conn

    sym = (symbol or "").strip().upper()
    items: list[dict[str, Any]] = []
    missing: list[str] = []
    limitations: list[str] = []

    if store is None:
        from megatool.market_store import MarketStore

        store = MarketStore(read_only=True)

    df = None
    try:
        df = store.get_bars(sym)
    except Exception as exc:  # pragma: no cover
        missing.append(f"price_bars ({exc})")
    if df is None or df.empty:
        missing.append("price_bars")
    else:
        close = df["close"].astype(float)
        items.append(_item(
            "fact", "Latest stored close", float(close.iloc[-1]), unit="NPR",
            as_of=str(df["trading_date"].iloc[-1]), source="price_bars",
            calculation="last stored close", dataset="price_bars",
        ))
        items.append(_item(
            "fact", "Stored bars", int(len(df)), unit="bars",
            as_of=str(df["trading_date"].iloc[-1]), source="price_bars",
            calculation="count", dataset="price_bars",
        ))
        items.append(_item(
            "fact", "History range", f"{df['trading_date'].iloc[0]}..{df['trading_date'].iloc[-1]}",
            source="price_bars", calculation="min/max trading_date", dataset="price_bars",
        ))
        if "source" in df:
            srcs = sorted({str(x) for x in df["source"].dropna().unique()})
            items.append(_item("fact", "Price source", ", ".join(srcs), source="price_bars",
                               dataset="price_bars"))
        if "adjustment_status" in df:
            adj = sorted({str(x) for x in df["adjustment_status"].dropna().unique()})
            items.append(_item("fact", "Adjustment status", ", ".join(adj),
                               source="price_bars", dataset="price_bars",
                               quality="ok" if adj == ["adjusted"] else "limitation",
                               limitations="" if adj == ["adjusted"] else
                               "Prices are not corporate-action adjusted."))
            if adj != ["adjusted"]:
                limitations.append("Prices are unadjusted; total-return and dividend claims are unsupported.")

    # --- data quality on the price series
    if df is not None and not df.empty:
        try:
            from megatool.quality import validate_series

            _, rep = validate_series(df)
            d = rep.as_dict()
            items.append(_item(
                "calculation", "Price-row validation", f"{d.get('suspect', 0)} suspect / {d.get('rows_checked', 0)} rows",
                source="megatool.quality", calculation="validate_series", dataset="price_bars",
                quality="ok" if not d.get("suspect") else "warning",
            ))
        except Exception:
            pass

    # --- technical rating + volatility percentile (real engines)
    # Each engine names its headline value differently. The map is explicit so a
    # renamed or absent key produces a stated "missing" entry rather than a
    # silent ``None`` that reads like a genuine measurement of nothing.
    _HEADLINE = {
        "technical_rating": ("score", "rating"),
        "volatility_percentile": ("percentile", "value"),
    }
    with _using_store(store):
        for fn, label in (("technical_rating", "Technical rating"),
                          ("volatility_percentile", "Volatility percentile")):
            try:
                out = catalog.run_analysis(fn, symbol=sym)
                if not (isinstance(out, dict) and out.get("available", True)):
                    missing.append(f"{fn}: {out.get('reason', 'unavailable')}")
                    continue
                val = None
                for key in _HEADLINE.get(fn, ("value",)):
                    if out.get(key) is not None:
                        val = out[key]
                        break
                if val is None:
                    missing.append(f"{fn}: the engine returned no headline value")
                    continue
                detail = out.get("verdict") if fn == "technical_rating" else None
                items.append(_item(
                    "calculation", f"{label} ({detail})" if detail else label, val,
                    unit=("0-100" if fn == "technical_rating" else "%"),
                    source="megatool.catalog", calculation=fn, dataset="price_bars",
                    as_of=str(out.get("as_of", "")) or None,
                ))
            except Exception as exc:
                missing.append(f"{fn}: {exc}")

    # --- fundamentals
    try:
        with get_conn() as conn:
            rows = query_symbol(conn, sym)
    except Exception:
        rows = []
    if not rows:
        missing.append("fundamentals")
    else:
        latest: dict[str, Any] = {}
        for r in rows:  # newest first
            if r.get("field") and r["field"] not in latest and r.get("value") is not None:
                latest[r["field"]] = r
        for field in ("eps", "pe", "paid_up_capital", "profit", "net_worth_per_share"):
            r = latest.get(field)
            if r is None:
                missing.append(f"fundamentals.{field}")
                continue
            items.append(_item(
                "fact", f"Fundamental: {field}", float(r["value"]), unit=r.get("unit", ""),
                as_of=r.get("period_end"), source=r.get("source", "fundamentals"),
                calculation="latest stored value", dataset="fundamentals",
            ))
        items.append(_item(
            "fact", "Fundamental records", int(len(rows)), unit="records",
            source="fundamentals", calculation="count", dataset="fundamentals",
        ))

    # --- universe context
    try:
        n = store.query_one("SELECT COUNT(DISTINCT symbol) FROM price_bars")
        if n:
            items.append(_item("fact", "Universe size", int(n[0]), unit="securities",
                               source="price_bars", calculation="count distinct symbol",
                               dataset="price_bars"))
    except Exception:
        pass

    limitations.extend([
        "Daily data only; no intraday, order-book or trade-level detail.",
        "No historical index membership, so survivorship bias cannot be excluded.",
        "The stored universe is not a point-in-time universe.",
    ])
    return {
        "symbol": sym,
        "generated_at": _now(),
        "items": items,
        "missing": sorted(set(missing)),
        "limitations": limitations,
    }


def _evidence_numbers(evidence: dict[str, Any]) -> list[float]:
    nums: list[float] = []
    for it in evidence.get("items", []):
        v = it.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            nums.append(float(v))
    return nums


def skeptical_review(text: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Rule-based sceptical review of an answer against the evidence bundle.

    This does not understand the prose; it checks structural risks and compares
    every number it can find to the bundle. Unmatched numbers are flagged for a
    human to verify -- they are not called wrong.
    """
    checks: list[dict[str, str]] = []
    answer_nums = [float(x) for x in _NUMBER.findall(text or "")]
    ev_nums = _evidence_numbers(evidence)
    unmatched: list[float] = []
    for n in answer_nums:
        if not ev_nums:
            unmatched.append(n)
            continue
        ok = False
        for e in ev_nums:
            for cand in (abs(e), abs(e) * 100.0, abs(e) / 100.0):
                if cand == 0:
                    if n == 0:
                        ok = True
                elif abs(n - cand) <= max(abs(cand) * 0.02, 1e-9):
                    ok = True
            if ok:
                break
        if not ok:
            unmatched.append(n)
    if unmatched:
        checks.append({"check": "unsupported_numeric_claims", "status": "flag",
                       "detail": f"{len(unmatched)} number(s) in the answer did not match any evidence value: "
                                 f"{sorted(set(unmatched))[:12]}"})
    else:
        checks.append({"check": "unsupported_numeric_claims", "status": "pass",
                       "detail": "every number found in the answer matched an evidence value"})

    missing = evidence.get("missing", [])
    checks.append({"check": "missing_inputs", "status": "flag" if missing else "pass",
                   "detail": ", ".join(missing) if missing else "no required input was missing"})

    stale = [it["label"] for it in evidence.get("items", []) if it.get("quality") == "stale"]
    checks.append({"check": "stale_data", "status": "flag" if stale else "pass",
                   "detail": ", ".join(stale) if stale else "no evidence item was flagged stale"})

    over = _OVERCLAIM.findall(text or "")
    checks.append({"check": "conclusion_strength", "status": "flag" if over else "pass",
                   "detail": f"over-strong wording: {over}" if over else "no guarantees or absolute wording found"})

    causal = _CAUSAL.findall(text or "")
    checks.append({"check": "causal_language", "status": "flag" if causal else "pass",
                   "detail": f"causal wording: {causal[:5]}" if causal else "no unsupported causal wording found"})

    checks.append({"check": "lookahead_bias", "status": "info",
                   "detail": "signal studies use next-session entry; forward-looking statements are not evidence."})
    checks.append({"check": "overfitting", "status": "info",
                   "detail": "any backtest figure must state the number of trials and any out-of-sample window."})
    checks.append({"check": "survivorship_bias", "status": "info",
                   "detail": "no historical index membership is stored, so survivorship bias cannot be excluded."})
    checks.append({"check": "corporate_action_treatment", "status": "info",
                   "detail": "prices are stored unadjusted; total-return claims are unsupported."})

    tags = {t: len(re.findall(re.escape(t), (text or "").lower())) for t in _CLAIM_TAGS}
    flags = sum(1 for c in checks if c["status"] == "flag")
    verdict = "unsupported" if flags >= 3 else ("needs_review" if flags else "supported_by_evidence")
    return {"checks": checks, "claim_tag_counts": tags, "flags": flags, "verdict": verdict}


_SYSTEM = (
    "You are a sceptical equity-research assistant. Use ONLY the evidence bundle "
    "provided. For every factual or numerical claim, cite the evidence item in square "
    "brackets using its label, and classify each conclusion as one of: verified fact, "
    "direct calculation, estimate, hypothesis, interpretation, unknown. If the evidence "
    "does not support a claim, say so explicitly. Never invent a value. Never recommend "
    "a trade."
)


def _prompt(question: str, evidence: dict[str, Any]) -> str:
    lines = [f"Question: {question}", f"Symbol: {evidence.get('symbol', '')}", "", "Evidence:"]
    for it in evidence.get("items", []):
        lines.append(
            f"- [{it['label']}] value={it['value']!r} unit={it.get('unit','')} "
            f"as_of={it.get('as_of') or 'unknown'} source={it.get('source')} "
            f"calculation={it.get('calculation')}"
        )
    if evidence.get("missing"):
        lines.append("Missing inputs: " + ", ".join(evidence["missing"]))
    if evidence.get("limitations"):
        lines.append("Limitations: " + " ".join(evidence["limitations"]))
    lines.append("")
    lines.append("Answer in this structure: Evidence used; Analysis; Conflicting evidence; "
                 "Missing inputs; Assumptions; Uncertainty; Conclusion; Invalidation conditions.")
    return "\n".join(lines)


def run_research(question: str, symbol: str, *, provider: str | None = None,
                 store: Any = None, max_tokens: int | None = None) -> dict[str, Any]:
    """Build evidence, ask the configured provider, review, and persist."""
    from megatool.db import get_conn

    evidence = build_evidence(symbol, store=store)
    status = llm.provider_status(provider)
    base = {
        "question": question,
        "symbol": evidence["symbol"],
        "evidence": evidence,
        "provider": status.get("provider"),
        "model": status.get("model"),
        "available": False,
        "answer": "",
        "review": {},
        "error": "",
        "created_at": _now(),
    }
    if not status.get("configured"):
        base["error"] = (
            "No AI provider is configured. The evidence bundle and research tools remain "
            "available; set MEGATOOL_AI_PROVIDER (and a model) to enable model reasoning."
        )
        base["review"] = skeptical_review("", evidence)
        _persist(base)
        return base

    try:
        prov = llm.get_provider(provider)
        result = prov.complete(
            _prompt(question, evidence), system=_SYSTEM, max_tokens=max_tokens, temperature=0.0
        )
    except llm.LLMError as exc:
        base["error"] = f"AI provider unavailable: {exc}"
        base["review"] = skeptical_review("", evidence)
        _persist(base)
        return base
    except Exception as exc:  # pragma: no cover - defensive
        base["error"] = f"AI request failed: {exc}"
        base["review"] = skeptical_review("", evidence)
        _persist(base)
        return base

    text = getattr(result, "text", "") or ""
    base.update({
        "available": True,
        "answer": text,
        "provider": getattr(result, "provider", status.get("provider")),
        "model": getattr(result, "model", status.get("model")),
        "usage": getattr(result, "usage", None),
        "review": skeptical_review(text, evidence),
    })
    _persist(base)
    return base


def _persist(base: dict[str, Any]) -> None:
    """Store the run. A persistence failure is surfaced, never hidden.

    Research must still return its answer, but silently losing the audit record
    would be worse than reporting that it could not be written, so the failure is
    attached to the result as ``persist_error``.
    """
    import json

    from megatool.db import get_conn

    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO research_runs (created_at, symbol, question, provider, model, "
                "available, evidence_json, review_json, answer, error, snapshot_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    base["created_at"], base["symbol"], base["question"],
                    str(base.get("provider") or ""), str(base.get("model") or ""),
                    1 if base.get("available") else 0,
                    json.dumps(base.get("evidence", {}), default=str),
                    json.dumps(base.get("review", {}), default=str),
                    str(base.get("answer") or ""), str(base.get("error") or ""), "",
                ),
            )
    except Exception as exc:  # pragma: no cover - defensive
        base["persist_error"] = f"{type(exc).__name__}: {exc}"


def history(limit: int = 50) -> list[dict[str, Any]]:
    from megatool.db import get_conn

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, created_at, symbol, question, provider, model, available, error "
            "FROM research_runs ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
    return [dict(r) for r in rows]
