"""Deterministic natural-language → scanner-rule translation.

The chat assistant offers a "propose a rule" action. That proposal is produced
here by a **deterministic grammar**, not by a language model and not by
generated code:

* the input is a plain question string;
* each clause is matched against a small table of documented phrasings;
* every produced condition names a metric that exists in the live catalogue
  (:data:`megatool.scanner.METRIC_HELP`) and an operator in
  :data:`megatool.scanner.OPERATORS`;
* the assembled tree is parsed back through ``ScreenNode.from_dict`` and
  ``validate_tree`` before it is returned.

A clause that cannot be mapped is returned in ``unmatched`` **with a reason**
(usually "no such metric") instead of being silently dropped or approximated,
so the user sees exactly what the assistant could and could not understand.

Nothing here is executed. The caller (API route) only ever returns the tree for
the user to review; execution happens later through the existing, validated
``POST /api/screen`` path.
"""

from __future__ import annotations

import re
from typing import Any

from megatool.scanner import METRIC_HELP, ScreenNode, validate_tree

#: Phrases that separate independent conditions.
_AND = re.compile(r"\s*(?:,|;|\band\b|\bplus\b|\bwith\b)\s*")
_ANY = re.compile(r"\s*\bor\b\s*")

_NUM = r"(-?\d+(?:\.\d+)?)"
_ABOVE = r"(?:above|over|greater than|higher than|>|>=|at least|exceeds?)"
_BELOW = r"(?:below|under|less than|lower than|<|<=|at most|beneath)"


def _cond(metric: str, operator: str, value: float, lookback: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"metric": metric, "operator": operator, "value": float(value)}
    if lookback is not None:
        d["lookback"] = int(lookback)
    return d


#: (regex, metric, operator, value_source, lookback_group) in match order.
#: Each entry is deliberately narrow: a phrasing that is not recognised is
#: reported as unmatched rather than guessed.
_RULES: list[tuple[re.Pattern[str], str, str, Any, int | None]] = [
    # --- moving averages (close relative to its own SMA) -------------------
    (
        re.compile(
            rf"(?:price|close|it)\s+{_ABOVE}\s+(?:its\s+)?(?:sma|simple moving average)\s*{_NUM}\b"
        ),
        "close_vs_sma",
        "gt",
        0.0,
        1,
    ),
    (
        re.compile(
            rf"(?:price|close|it)\s+{_BELOW}\s+(?:its\s+)?(?:sma|simple moving average)\s*{_NUM}\b"
        ),
        "close_vs_sma",
        "lt",
        0.0,
        1,
    ),
    (
        re.compile(
            rf"(?:sma|simple moving average)\s*{_NUM}\s+(?:is\s+)?{_ABOVE}\s*(?:the\s+)?(?:price|close)"
        ),
        "close_vs_sma",
        "lt",
        0.0,
        1,
    ),
    # --- raw price --------------------------------------------------------
    (
        re.compile(rf"(?:price|close|share price)\s+{_ABOVE}\s+(?:rs\.?|npr|₨)?\s*{_NUM}\b"),
        "close",
        "gt",
        1,
        None,
    ),
    (
        re.compile(rf"(?:price|close|share price)\s+{_BELOW}\s+(?:rs\.?|npr|₨)?\s*{_NUM}\b"),
        "close",
        "lt",
        1,
        None,
    ),
    # --- oscillators ------------------------------------------------------
    (re.compile(rf"\brsi\s*(?:\(14\))?\s*{_ABOVE}\s*{_NUM}"), "rsi", "gt", 1, None),
    (re.compile(rf"\brsi\s*(?:\(14\))?\s*{_BELOW}\s*{_NUM}"), "rsi", "lt", 1, None),
    (re.compile(rf"\bmfi\s*{_ABOVE}\s*{_NUM}"), "mfi", "gt", 1, None),
    (re.compile(rf"\bmfi\s*{_BELOW}\s*{_NUM}"), "mfi", "lt", 1, None),
    (re.compile(rf"stochastic\s*%?d?\s*{_ABOVE}\s*{_NUM}"), "stochastic_k", "gt", 1, None),
    (re.compile(rf"stochastic\s*%?d?\s*{_BELOW}\s*{_NUM}"), "stochastic_k", "lt", 1, None),
    (re.compile(rf"\badx\s*{_ABOVE}\s*{_NUM}"), "adx", "gt", 1, None),
    (re.compile(rf"\badx\s*{_BELOW}\s*{_NUM}"), "adx", "lt", 1, None),
    # --- MACD -------------------------------------------------------------
    (re.compile(r"(?:macd\s*)?(?:bullish|golden)[^,;]{0,16}cross"), "macd_cross", "gt", 0.0, None),
    (
        re.compile(r"(?:macd\s*)?(?:bearish|death|dead)[^,;]{0,16}cross"),
        "macd_cross",
        "lt",
        0.0,
        None,
    ),
    (re.compile(rf"macd histogram\s*{_ABOVE}\s*{_NUM}"), "macd_histogram", "gt", 1, None),
    (re.compile(rf"macd histogram\s*{_BELOW}\s*{_NUM}"), "macd_histogram", "lt", 1, None),
    # --- volume -----------------------------------------------------------
    (
        re.compile(rf"(?:relative |unusual |high )volume\s*{_ABOVE}\s*{_NUM}"),
        "relative_volume",
        "gt",
        1,
        None,
    ),
    (
        re.compile(rf"volume\s*{_ABOVE}\s*(?:its\s+)?(?:average|mean|sma|20[- ]day average)"),
        "volume_sma_ratio",
        "gt",
        1.0,
        None,
    ),
    (
        re.compile(rf"volume\s*{_BELOW}\s*(?:its\s+)?(?:average|mean|sma)"),
        "volume_sma_ratio",
        "lt",
        1.0,
        None,
    ),
    (
        re.compile(rf"turnover\s*{_ABOVE}\s*(?:its\s+)?(?:average|mean|sma)"),
        "turnover_sma_ratio",
        "gt",
        1.0,
        None,
    ),
    # --- returns / distance ----------------------------------------------
    (re.compile(rf"{_NUM}\s*[- ]?day\s+return\s*{_ABOVE}\s*{_NUM}"), "return_20d", "gt", 1, None),
    (
        re.compile(rf"return\s+over\s+the\s+last\s+{_NUM}\s+days\s*{_ABOVE}\s*{_NUM}"),
        "return_20d",
        "gt",
        2,
        None,
    ),
    (
        re.compile(
            rf"(?:within|near)\s*{_NUM}\s*%\s*of\s+(?:the\s+)?(?:52[- ]week|trailing)\s+high"
        ),
        "distance_from_high_52w",
        "lt",
        1,
        None,
    ),
    # --- trend strength ---------------------------------------------------
    (re.compile(rf"atr\s*(?:%|percent)?\s*{_ABOVE}\s*{_NUM}"), "atr_percent", "gt", 1, None),
    (re.compile(rf"atr\s*(?:%|percent)?\s*{_BELOW}\s*{_NUM}"), "atr_percent", "lt", 1, None),
]

#: Phrasings we deliberately do NOT map, with the honest reason.
_UNSUPPORTED: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\b(?:p\s*/\s*e|pe|price\s+to\s+earnings)\b"),
        "P/E is not a scanner metric — fundamentals are not wired into the scanner yet",
    ),
    (
        re.compile(r"\b(?:p\s*/\s*b|pb|price\s+to\s+book|book\s+value)\b"),
        "P/B is not a scanner metric — fundamentals are not wired into the scanner yet",
    ),
    (
        re.compile(r"\b(?:dividend\s*yield|dividend|dps)\b"),
        "dividend yield is not a scanner metric — fundamentals are not wired into the scanner yet",
    ),
    (
        re.compile(r"\b(?:eps|earnings\s+per\s+share|earnings|profit|revenue|net\s+worth)\b"),
        "EPS/revenue are not scanner metrics — fundamentals are not wired into the scanner yet",
    ),
    (
        re.compile(r"\b(?:relative strength|rs rating|outperform(?:ing)? the (?:index|market))\b"),
        "relative strength is not exposed as a scanner metric — no benchmark consumer is wired to the scanner",
    ),
    (
        re.compile(r"\b(?:golden cross of sma|death cross of sma|sma\s*\d+\s+cross)\b"),
        "SMA crossovers are available as the `sma_cross` metric, but the phrasing "
        "was not specific enough to choose a period",
    ),
]


_PREAMBLE = re.compile(
    r"^\s*(?:please\s+)?(?:find|scan|screen|show|list|give|get|which|what)\b"
    r"[^,;]{0,40}?\b(?:stocks?|symbols?|shares?|securities?|companies|that|where|with)\b\s*"
)


def _clauses(question: str) -> tuple[str, list[str]]:
    """Split into clauses and choose the top-level operator."""
    q = " " + question.strip().lower() + " "
    # "find stocks with rsi < 30" → the request preamble is not a condition.
    stripped = _PREAMBLE.sub("", q).strip() or q
    q = " " + stripped + " "
    if _ANY.search(q):
        parts = [p for p in _ANY.split(q) if p.strip()]
        return "OR", parts
    parts = [p for p in _AND.split(q) if p.strip()]
    return "AND", parts


def parse_question(question: str) -> dict[str, Any]:
    """Translate *question* into a validated screen tree, or explain why not.

    Raises :class:`ValueError` when nothing at all could be understood, so the
    caller returns a 400 rather than an empty rule that would match nothing.
    """
    if not question or not question.strip():
        raise ValueError("question must not be empty")

    op, clauses = _clauses(question)
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in clauses:
        clause = raw.strip()
        if not clause:
            continue
        hit = None
        for rx, metric, operator, value_src, lookback_group in _RULES:
            m = rx.search(clause)
            if not m:
                continue
            if metric not in METRIC_HELP:
                continue
            if isinstance(value_src, int):
                g = value_src
                value = float(m.group(g)) if g <= (m.re.groups) else 0.0
            else:
                value = float(value_src)
            lookback = None
            if lookback_group is not None and lookback_group <= m.re.groups:
                try:
                    lookback = int(float(m.group(lookback_group)))
                except (TypeError, ValueError):
                    lookback = None
            hit = _cond(metric, operator, value, lookback)
            break
        if hit is not None:
            key = f"{hit['metric']}|{hit['operator']}|{hit['value']}|{hit.get('lookback')}"
            if key in seen:
                continue
            seen.add(key)
            matched.append({"clause": clause, "condition": hit})
            continue

        reason = "no supported metric phrasing matched this clause"
        for rx, why in _UNSUPPORTED:
            if rx.search(clause):
                reason = why
                break
        unmatched.append({"clause": clause, "reason": reason})

    if not matched:
        detail = "; ".join(f"{u['clause']}: {u['reason']}" for u in unmatched[:3])
        raise ValueError(
            "no supported condition could be understood" + (f" ({detail})" if detail else "")
        )

    tree: dict[str, Any] = {"op": op, "conditions": [m["condition"] for m in matched]}
    node = ScreenNode.from_dict(tree)
    problems = validate_tree(node)
    if problems:
        raise ValueError("internal error: parsed rule failed validation: " + "; ".join(problems))

    return {
        "tree": tree,
        "rendered": node.render(),
        "operator": op,
        "matched": matched,
        "unmatched": unmatched,
        "basis": "deterministic grammar over the live metric catalogue (no model, no code execution)",
        "metrics_available": len(METRIC_HELP),
        "notes": [
            "Review and edit the conditions before running; nothing has been executed.",
            "A metric with no backing data makes a security ineligible with a reason, "
            "not a silent pass.",
        ],
    }
