"""Disaggregated coverage model for the security universe.

Why this module exists
----------------------
The Phase-1 brief asked to "investigate the reported 78.3% symbol coverage".
That number is **not a coverage figure at all**: it is the cross-source
*unanimity* rate in ``NEPSE_DATA_SOURCE_ASSESSMENT.md`` — 401 of 512 symbols
that two or more sources both list agree across every source (``401/512 =
0.7832``).  It says nothing about how much of the universe is identified,
classified or rankable.

A single blended percentage invites exactly that misreading.  Coverage must be
reported as a set of separate, well-defined fractions, each with its own
numerator, denominator, eligibility rule and unresolved set.  This module
computes them from a live :class:`~megatool.market_store.MarketStore` (or any
market DuckDB) so the number in a report is always reproducible.

The seven metrics
-----------------
1. ``security_identity``        — every master row carrying an attested name.
2. ``active_ordinary_identity`` — active ordinary shares carrying a name.
3. ``inactive_identity``        — retired (merged/delisted/suspended) rows
                                  carrying a name.
4. ``sector_classification``    — ordinary shares carrying a business sector.
5. ``historical_symbol_mapping``— retired tickers with a documented successor.
6. ``corporate_action_reconciliation`` — registry entries verified on **both**
                                  signals (notice/name evidence *and* a store
                                  handoff), not merely source-attested.
7. ``sector_rank_eligibility``  — ordinary shares with sector data that clear
                                  the ranking bar floor.

A record that is *unknown* is different from one that is *unresolved-on-
purpose*: metric 5 reports the 8 retired tickers whose successor is genuinely
unknown separately rather than dropping them from the denominator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Statuses that mean "this security no longer trades under this ticker".
RETIRED_STATUSES: frozenset[str] = frozenset({"MERGED", "DELISTED", "SUSPENDED"})

#: Default minimum bars before a symbol is considered rankable (mirrors the
#: ranking engine's own floor).
DEFAULT_MIN_BARS = 60


@dataclass(frozen=True)
class Metric:
    """One coverage fraction with a fully explained definition."""

    key: str
    label: str
    numerator: int
    denominator: int
    definition: str
    eligibility: str
    unresolved: tuple[str, ...] = ()

    @property
    def pct(self) -> float:
        return 100.0 * self.numerator / self.denominator if self.denominator else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "pct": round(self.pct, 4),
            "definition": self.definition,
            "eligibility": self.eligibility,
            "unresolved": list(self.unresolved),
        }


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _master_columns(store: Any) -> set[str]:
    try:
        rows = store.query_rows("DESCRIBE security_master")
    except Exception:  # pragma: no cover - defensive
        return set()
    return {str(r[0]) for r in rows}


def _load_master(store: Any) -> list[dict[str, Any]]:
    """Read security_master tolerating columns a pre-migration DB lacks."""
    cols = _master_columns(store)
    wanted = [
        c
        for c in ("symbol", "name", "sector", "instrument_type", "status", "successor_symbol")
        if c in cols
    ]
    if "symbol" not in wanted:
        return []
    select = ", ".join(wanted)
    rows = store.query_rows(f"SELECT {select} FROM security_master")
    out = []
    for r in rows:
        rec = dict(zip(wanted, r, strict=False))
        rec.setdefault("status", "UNKNOWN")
        rec.setdefault("successor_symbol", None)
        rec.setdefault("sector", None)
        rec.setdefault("instrument_type", None)
        rec.setdefault("name", None)
        out.append(rec)
    return out


def _bar_counts(store: Any) -> dict[str, int]:
    try:
        rows = store.query_rows("SELECT symbol, COUNT(*) FROM price_bars GROUP BY symbol")
    except Exception:  # pragma: no cover - defensive
        return {}
    return {str(s).upper(): int(n) for s, n in rows}


def _is_retired(status: Any) -> bool:
    return str(status or "").strip().upper() in RETIRED_STATUSES


def _registry_counts() -> tuple[int, int, list[str]]:
    """Return (verified_both_signals, total, unresolved_symbols)."""
    try:
        from megatool.corporate_actions import EVIDENCE_VERIFIED, VERIFIED_CORPORATE_ACTIONS
    except Exception:  # pragma: no cover - defensive
        return 0, 0, []
    verified = sum(1 for a in VERIFIED_CORPORATE_ACTIONS if a.grade == EVIDENCE_VERIFIED)
    unresolved = sorted(a.symbol for a in VERIFIED_CORPORATE_ACTIONS if not a.successor)
    return verified, len(VERIFIED_CORPORATE_ACTIONS), unresolved


def coverage_report(store: Any, *, min_bars: int = DEFAULT_MIN_BARS) -> dict[str, Any]:
    """Compute the seven disaggregated coverage metrics for ``store``.

    ``store`` is a :class:`MarketStore` (or anything exposing ``query_rows``).
    The function is read-only and safe against a production database that has
    not yet received the R5/B-4 schema migration.
    """
    master = _load_master(store)
    bars = _bar_counts(store)

    total_rows = len(master)
    named = [r for r in master if _has_text(r.get("name"))]

    active_ordinary = [
        r
        for r in master
        if str(r.get("instrument_type") or "").lower() == "ordinary"
        and not _is_retired(r.get("status"))
    ]
    inactive = [r for r in master if _is_retired(r.get("status"))]

    ordinary_sectored = [r for r in active_ordinary if _has_text(r.get("sector"))]
    inactive_named = [r for r in inactive if _has_text(r.get("name"))]
    inactive_mapped = [r for r in inactive if _has_text(r.get("successor_symbol"))]
    inactive_unresolved = sorted(
        str(r["symbol"]).upper() for r in inactive if not _has_text(r.get("successor_symbol"))
    )

    rankable_ordinary = [
        r for r in active_ordinary if bars.get(str(r["symbol"]).upper(), 0) >= min_bars
    ]
    rankable_sectored = [r for r in rankable_ordinary if _has_text(r.get("sector"))]

    verified, registry_total, registry_unresolved = _registry_counts()

    metrics = [
        Metric(
            key="security_identity",
            label="Security-master identity coverage",
            numerator=len(named),
            denominator=total_rows,
            definition="Rows in security_master that carry an attested name.",
            eligibility="Every row in security_master.",
        ),
        Metric(
            key="active_ordinary_identity",
            label="Active ordinary-security identity coverage",
            numerator=sum(1 for r in active_ordinary if _has_text(r.get("name"))),
            denominator=len(active_ordinary),
            definition="Active ordinary shares (not merged/delisted/suspended) carrying a name.",
            eligibility="instrument_type = 'ordinary' and status not in "
            "{MERGED, DELISTED, SUSPENDED}.",
        ),
        Metric(
            key="inactive_identity",
            label="Historical / inactive security identity coverage",
            numerator=len(inactive_named),
            denominator=len(inactive),
            definition="Retired tickers carrying a name (from the corporate-action registry).",
            eligibility="status in {MERGED, DELISTED, SUSPENDED}.",
        ),
        Metric(
            key="sector_classification",
            label="Verified sector-classification coverage",
            numerator=len(ordinary_sectored),
            denominator=len(active_ordinary),
            definition="Ordinary shares carrying an issuer business sector.",
            eligibility="instrument_type = 'ordinary' (non-ordinary instruments are "
            "classified by instrument, not business sector).",
        ),
        Metric(
            key="historical_symbol_mapping",
            label="Historical symbol-mapping coverage",
            numerator=len(inactive_mapped),
            denominator=len(inactive),
            definition="Retired tickers resolved to a documented successor.",
            eligibility="status in {MERGED, DELISTED, SUSPENDED}.",
            unresolved=tuple(inactive_unresolved),
        ),
        Metric(
            key="corporate_action_reconciliation",
            label="Corporate-action reconciliation coverage",
            numerator=verified,
            denominator=registry_total,
            definition="Registry entries verified on both signals (notice/name evidence "
            "AND a store handoff) rather than source-attested only.",
            eligibility="Every entry in the corporate-action registry.",
            unresolved=tuple(registry_unresolved),
        ),
        Metric(
            key="sector_rank_eligibility",
            label="Coverage of securities eligible for sector ranking",
            numerator=len(rankable_sectored),
            denominator=len(rankable_ordinary),
            definition=f"Rankable ordinary shares (>= {min_bars} bars) that carry a sector.",
            eligibility=f"instrument_type = 'ordinary' and bar count >= {min_bars}.",
        ),
    ]

    return {
        "min_bars": min_bars,
        "origin_of_783": (
            "The reported 78.3% is the cross-source unanimity rate (401/512) among "
            "symbols covered by >= 2 sources in NEPSE_DATA_SOURCE_ASSESSMENT.md; it is "
            "not a coverage metric and must not be quoted as one."
        ),
        "metrics": {m.key: m.as_dict() for m in metrics},
        "totals": {
            "master_rows": total_rows,
            "active_ordinary": len(active_ordinary),
            "retired": len(inactive),
        },
    }
