"""Compose one symbol's research workspace from the real modules.

Why this exists
---------------
The Master Specification asks for two things that turn out to be the same
thing from two sides:

* §1/§16 — a **unified stock research page**, where a researcher selects a
  symbol and sees its overview, chart access, indicators, trend/momentum,
  volatility, Fibonacci, candlesticks, support/resistance, provenance and the
  existing report in one place.
* §17/Target 6 — an **honest analysis status**, where the user can tell which
  analyses genuinely ran, which failed, and which cannot run.

A page that renders module results *and* the state those results came from is
both. This module produces that payload.

The state model (§Target 6.A)
-----------------------------
Every module reports exactly one of::

    NOT_STARTED  RUNNING  COMPLETED  COMPLETED_WITH_WARNINGS
    FAILED       BLOCKED_BY_MISSING_DATA  CACHED_RESULT_AVAILABLE

States are derived from **actual execution**: each module is called inside a
timer and a ``try``. A state is never looked up from a hardcoded list of
"successful" modules, a percentage is never invented, and one module failing
never lets the page pretend it succeeded — the failure is recorded with its
error text and the remaining modules still run (§Target 6.E).

Result contract (§5)
--------------------
Every module payload carries the same envelope: ``symbol``, ``method``,
``method_version``, ``params``, ``input`` (start/end/latest observation),
``calculated_at``, ``classification``, ``result``, ``warnings`` and
``error``. Extending this beats inventing a second architecture (§5).

Boundaries (§8)
---------------
The workspace is bounded to ``limit`` bars (default 500) so opening a page on
an 8 GB machine does not load 514,018 bars. Nothing here is cached across
requests yet — ``cached`` is reported as ``False`` rather than claimed.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

__all__ = ["ModuleResult", "build_workspace"]

#: Bars fetched when the caller does not bound the window. Chosen so a page
#: open stays responsive on the target machine (§8).
DEFAULT_LIMIT = 500

METHOD = "research-workspace"
VERSION = "1.0"


def _valid_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Maximal ``[start, stop)`` runs of ``True`` in a boolean mask.

    Contiguity is the point: candlestick rules are defined over *consecutive*
    bars, so a run must never be stitched across an excluded bar.
    """
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, ok in enumerate(mask.tolist()):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class ModuleResult:
    """One module's execution state and (when it ran) its payload."""

    name: str
    label: str
    state: str = "NOT_STARTED"
    started_at: str | None = None
    completed_at: str | None = None
    elapsed_ms: float | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    cached: bool = False
    retryable: bool = False
    classification: str | None = None
    method: str | None = None
    method_version: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(
    name: str,
    label: str,
    fn: Callable[[], tuple[dict[str, Any] | None, list[str], str, str]],
) -> ModuleResult:
    """Execute one module, timing it and isolating its failures.

    ``fn`` returns ``(payload, warnings, classification, method,
    method_version, params)``. Any exception becomes a FAILED (or
    BLOCKED_BY_MISSING_DATA) state carrying the message — never a silent
    omission, and never a reason to abort the modules after it.
    """
    mod = ModuleResult(name=name, label=label, started_at=_now())
    t0 = time.perf_counter()
    try:
        result, warnings, classification, method, method_version, params = fn()
    except KeyError as exc:
        # A missing key is almost always absent input data, not a code fault.
        mod.state = "BLOCKED_BY_MISSING_DATA"
        mod.error = f"required input missing: {exc}"
        mod.retryable = True
    except ImportError as exc:
        mod.state = "BLOCKED_BY_MISSING_DATA"
        mod.error = f"module unavailable: {exc}"
        mod.retryable = True
    except NotImplementedError as exc:
        mod.state = "BLOCKED_BY_MISSING_DATA"
        mod.error = str(exc)
        mod.retryable = False
    except Exception as exc:  # noqa: BLE001 - one module must not kill the page
        mod.state = "FAILED"
        mod.error = f"{type(exc).__name__}: {exc}"
        mod.retryable = True
    else:
        mod.result = result
        mod.warnings = list(warnings)
        mod.classification = classification
        mod.method = method
        mod.method_version = method_version
        mod.params = params
        mod.state = "COMPLETED_WITH_WARNINGS" if warnings else "COMPLETED"
    finally:
        mod.completed_at = _now()
        mod.elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)

    return mod


def _overview(df: Any, dates: list[str], provenance: dict[str, Any]) -> dict[str, Any]:
    """Latest observation, change, coverage and volume — all dated.

    Nothing here is called a live price. Change is computed only from the last
    two stored closes, and is reported as historical.
    """
    close = df["close"].to_numpy(float)
    volume = df["volume"].to_numpy(float) if "volume" in df.columns else None

    last = float(close[-1])
    prev = float(close[-2]) if close.size > 1 else None
    change = last - prev if prev is not None else None
    change_pct = (change / prev * 100.0) if change is not None and prev else None

    warnings: list[str] = []
    if close.size < 2:
        warnings.append("Fewer than two observations, so change cannot be computed.")
    if volume is None or not np.isfinite(volume).any():
        warnings.append("No usable volume column in the stored bars.")

    return {
        "symbol": str(df["symbol"].iloc[0]) if "symbol" in df.columns else None,
        "last_close": round(last, 4),
        "previous_close": round(prev, 4) if prev is not None else None,
        "change": round(change, 4) if change is not None else None,
        "change_percent": round(change_pct, 4) if change_pct is not None else None,
        # Explicitly historical: these are stored observations, not a live quote.
        "price_kind": "historical close (stored bars, not a live price)",
        "observation_date": dates[-1],
        "first_date": dates[0],
        "last_date": dates[-1],
        "observations": int(close.size),
        "latest_volume": int(volume[-1]) if volume is not None else None,
        "provenance": provenance,
        "warnings": warnings,
    }


def build_workspace(
    df: Any,
    symbol: str,
    limit: int = DEFAULT_LIMIT,
    run: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Build the unified research payload for one symbol.

    Parameters
    ----------
    df
        Bounded OHLCV frame, oldest to newest.
    symbol
        The requested symbol (already upper-cased by the caller).
    limit
        The bar bound actually applied, reported back so the UI can show it.
    run
        Optional per-module enable flags, e.g. ``{"candlesticks": False}``.
        A module set to ``False`` reports ``NOT_STARTED`` — honest, because
        it was not skipped for a data reason, it was simply not asked for.

    Returns
    -------
    dict
        Overview, module states with timings and errors, and the contract
        envelope. Structure mirrors §5 so consumers never need to special-case
        a module.
    """
    from megatool.ta.fibonacci import levels_for
    from megatool.ta.levels import build_zones
    from megatool.ta.swings import DEFAULT_LEFT, DEFAULT_RIGHT, classify_structure, find_swings

    run = run or {}
    dates = [str(d.date()) for d in df["trading_date"]]
    n = len(df)

    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    volume = df["volume"].to_numpy(float) if "volume" in df.columns else None

    # OHLC self-consistency. The stored dataset contains bars whose close (or
    # open) sits outside [low, high], and a handful where high < low. Those
    # records are NEVER modified here — but a consumer must not be handed a
    # "candle" that cannot exist, so the mask below excludes them from pattern
    # detection and the count is reported as a data-quality warning.
    ohlc_valid = (
        np.isfinite(open_)
        & np.isfinite(high)
        & np.isfinite(low)
        & np.isfinite(close)
        & (high >= np.maximum(open_, close))
        & (low <= np.minimum(open_, close))
        & (high >= low)
    )
    ohlc_invalid = int((~ohlc_valid).sum())

    provenance = {
        "source": str(df["source"].iloc[0]) if "source" in df.columns else "unknown",
        "validation_status": (
            str(df["validation_status"].iloc[0]) if "validation_status" in df.columns else "unknown"
        ),
        "first_date": dates[0],
        "last_date": dates[-1],
        "observations": n,
        "price_adjustment": "unadjusted for bonus/split issues",
    }
    input_block = {"start": dates[0], "end": dates[-1], "latest": dates[-1], "bars": n}

    def envelope(
        result: dict[str, Any],
        warnings: list[str],
        classification: str,
        method: str,
        method_version: str = "1.0",
        params: dict[str, Any] | None = None,
    ) -> tuple[
        dict[str, Any],
        list[str],
        str,
        str,
        str,
        dict[str, Any],
    ]:
        # Returns the raw payload plus its contract metadata. `ModuleResult`
        # carries the metadata and the payload separately so a consumer never
        # has to unwrap `result["result"]`.
        return (
            result,
            warnings,
            classification,
            method,
            method_version,
            params or {},
        )

    modules: list[ModuleResult] = []

    # ---------------------------------------------------------- overview
    def do_overview():
        ov = _overview(df, dates, provenance)
        warns = ov.pop("warnings")
        return envelope(ov, warns, "CALCULATED", "latest stored bar summary")

    modules.append(_run("overview", "Stock overview", do_overview))

    # -------------------------------------------------------- structure
    def do_structure():
        if n < 2 * 3 + 1:
            raise NotImplementedError(f"needs at least 7 bars for swing detection, got {n}")
        swings = find_swings(high, low, left=DEFAULT_LEFT, right=DEFAULT_RIGHT)
        info = classify_structure(swings)
        result = {
            "swings": [
                {
                    **s.to_dict(),
                    "date": dates[s.index],
                    "confirmed_date": dates[s.confirmed_index],
                }
                for s in swings
            ],
            "labels": [{**row, "date": dates[row["index"]]} for row in info["labels"]],
            "trend": info["trend"],
            "swing_highs": info["swing_highs"],
            "swing_lows": info["swing_lows"],
        }
        warns = []
        if not swings:
            warns.append("No swing points met the detection rules on this window.")
        return envelope(
            result,
            warns,
            "DETECTED",
            "fractal pivot (unique extreme over left/right window)",
            params={"left": DEFAULT_LEFT, "right": DEFAULT_RIGHT},
        )

    modules.append(_run("structure", "Swing structure", do_structure))

    # ------------------------------------------------------- fibonacci
    def do_fibonacci():
        swings = find_swings(high, low, left=DEFAULT_LEFT, right=DEFAULT_RIGHT)
        usable = [s for s in swings if s.confirmed]
        highs_only = [s for s in usable if s.kind == "high"]
        lows_only = [s for s in usable if s.kind == "low"]
        if not highs_only or not lows_only:
            raise NotImplementedError(
                "needs at least one confirmed swing high and one confirmed swing "
                f"low; found {len(highs_only)} high / {len(lows_only)} low"
            )
        hi = max(highs_only, key=lambda s: (s.index, s.price))
        lo = max(lows_only, key=lambda s: (s.index, -s.price))
        s0, s1 = (lo, hi) if lo.index <= hi.index else (hi, lo)
        table = levels_for(s0.price, s1.price, start_index=s0.index, end_index=s1.index)
        payload = table.to_dict()
        payload["anchors"]["start_date"] = dates[s0.index]
        payload["anchors"]["end_date"] = dates[s1.index]
        payload["anchors"]["start_kind"] = s0.kind
        payload["anchors"]["end_kind"] = s1.kind
        return envelope(
            payload,
            [
                "CALCULATED from two chosen swing anchors — arithmetic, not a "
                "prediction and not evidence any level will hold.",
                "The 50% retracement is a market convention, not a Fibonacci ratio.",
            ],
            "CALCULATED",
            "fibonacci from swing anchors",
        )

    modules.append(_run("fibonacci", "Fibonacci analysis", do_fibonacci))

    # ------------------------------------------- support / resistance
    def do_levels():
        swings = find_swings(high, low, left=DEFAULT_LEFT, right=DEFAULT_RIGHT)
        # `min_touches=2` matches the API route's default: a lone pivot is a
        # point, not a tested level. Excluded zones are still returned, so
        # nothing is hidden by the filter.
        zones = build_zones(swings, close=close, min_touches=2)
        if zones["counts"]["total"] == 0:
            raise NotImplementedError("no swing points met the detection rules")
        result = {
            **{k: v for k, v in zones.items() if k not in {"zones", "excluded"}},
            "zones": [
                {
                    **z,
                    "first_date": dates[min(z["swing_indices"])],
                    "last_date": dates[max(z["swing_indices"])],
                }
                for z in zones["zones"]
            ],
            "excluded": zones["excluded"],
        }
        return envelope(
            result,
            list(zones["warnings"]),
            "DETECTED",
            "swing-cluster",
            method_version=zones["method_version"],
            params=zones["params"],
        )

    modules.append(_run("levels", "Support and resistance", do_levels))

    # ------------------------------ trend / momentum / volatility (shared)
    def do_summary():
        from megatool.ta.summary import SummaryError, build_summary  # local

        # This module validates OHLC strictly, which is correct. How a corrupt
        # bar is handled here is deliberately *different* from candlesticks,
        # and the difference matters:
        #
        #   * Candlestick rules need 2-3 bars to be genuinely adjacent, so
        #     there detection runs on contiguous runs only (see below) —
        #     compacting would invent adjacency that never traded.
        #   * Trend/momentum/volatility are *aggregate* statistics (means,
        #     ratios, ranges) where skipping one bad observation does not
        #     create a false pattern. Splitting at the first bad bar instead
        #     would have been the worse error: on real ADBL data a single
        #     corrupt bar at 2026-04-29 would have cut the summary off five
        #     months early and reported a "current" trend as of 2026-04-28.
        #
        # So the bad bars are dropped, the rest are used, and the omission is
        # stated with counts and dates rather than absorbed silently.
        base: list[str] = ["CALCULATED from stored OHLC — descriptive, not predictive."]
        if bool(np.all(ohlc_valid)):
            r = build_summary(open_, high, low, close, volume=volume, dates=dates)
        else:
            keep = ohlc_valid
            kept_dates = [d for d, k in zip(dates, keep, strict=True) if k]
            if len(kept_dates) < 2:
                raise SummaryError(
                    f"only {len(kept_dates)} self-consistent bar(s) in this "
                    f"window; {ohlc_invalid} of {n} have inconsistent OHLC"
                )
            r = build_summary(
                open_[keep],
                high[keep],
                low[keep],
                close[keep],
                volume=None if volume is None else volume[keep],
                dates=kept_dates,
            )
            base.append(
                f"{ohlc_invalid} of {n} bar(s) in this window have "
                "inconsistent OHLC (open or close outside [low, high], or "
                "high < low) and were excluded from these statistics. Used "
                f"the remaining {len(kept_dates)} bars, {kept_dates[0]} → "
                f"{kept_dates[-1]}. The stored records were not modified."
            )

        d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        warns = list(d.pop("warnings", []))
        return envelope(d, warns + base, "DETECTED", "trend/momentum/volatility summary")

    modules.append(_run("trend_momentum_volatility", "Trend, momentum & volatility", do_summary))

    # ---------------------------------------------------- candlesticks
    def do_candles():
        from megatool.ta.candles import CandleError, detect_patterns

        base = [
            "DETECTED by explicit geometric rules — a match is not a "
            "confirmed reversal and not a forecast."
        ]
        if ohlc_invalid:
            base.append(
                f"{ohlc_invalid} of {n} bar(s) in this window have internally "
                "inconsistent OHLC (open or close outside [low, high], or "
                "high < low). They were excluded from pattern detection; the "
                "stored records were not modified."
            )

        rows: list[dict[str, Any]] = []
        skipped_segments = 0

        # Detection runs on each maximal run of self-consistent bars rather
        # than on a compacted array: dropping a bar and letting a three-candle
        # pattern "span" the gap would invent adjacency that never traded.
        for start, stop in _valid_runs(ohlc_valid):
            if stop - start < 3:
                continue
            try:
                found = detect_patterns(
                    open_[start:stop],
                    high[start:stop],
                    low[start:stop],
                    close[start:stop],
                    dates=dates[start:stop],
                )
            except CandleError:
                # A segment the rule library refuses is reported, not hidden.
                skipped_segments += 1
                continue
            for p in found:
                row = p.to_dict() if hasattr(p, "to_dict") else dict(p)
                local = int(row.get("index", -1))
                original = start + local
                row["index"] = original
                row["date"] = dates[original] if 0 <= original < n else None
                rows.append(row)

        rows.sort(key=lambda r: (int(r["index"]), str(r["name"])))

        if skipped_segments:
            base.append(
                f"{skipped_segments} valid segment(s) were rejected by the "
                "rule library and produced no patterns."
            )
        if not rows and not ohlc_invalid and not skipped_segments:
            base.append("No pattern rules matched this window.")

        return envelope(
            {"patterns": rows, "count": len(rows), "bars_excluded": ohlc_invalid},
            base,
            "DETECTED",
            "candlestick rule library",
        )

    modules.append(_run("candlesticks", "Candlestick patterns", do_candles))

    # ------------------------------------------------- research report
    def do_report():
        from megatool.research import build_report

        # `universe` is deliberately omitted: a cross-sectional comparison is a
        # different, more expensive analysis and is not what this panel shows.
        rep = build_report(df, symbol)
        d = rep.to_dict()
        return envelope(
            d,
            list(d.get("warnings", [])),
            "CALCULATED",
            "deterministic research report",
        )

    modules.append(_run("research_report", "Research report", do_report))

    # --------------------------------------------------- data quality
    # Data-quality propagation includes B-21 (non_positive_price) flags
    def do_quality():
        flagged = 0
        if "validation_status" in df.columns:
            flagged = int((df["validation_status"] != "valid").sum())
        gaps = int(np.sum(~np.isfinite(close)))
        warns: list[str] = []
        if flagged:
            warns.append(f"{flagged} bar(s) are not marked valid.")
        if gaps:
            warns.append(f"{gaps} close value(s) are non-finite.")
        if ohlc_invalid:
            warns.append(
                f"{ohlc_invalid} bar(s) have internally inconsistent OHLC "
                "(open or close outside [low, high], or high < low). Stored "
                "records were left unmodified; pattern detection skips them."
            )
        if not flagged and not gaps and not ohlc_invalid:
            warns.append(
                "No flagged bars, no non-finite closes and no OHLC violations in this window."
            )
        result = {
            "flagged_bars": flagged,
            "non_finite_closes": gaps,
            "ohlc_violations": ohlc_invalid,
            "ohlc_violation_share_percent": (round(ohlc_invalid / n * 100, 4) if n else None),
            "provenance": provenance,
            "sector_available": None,
        }
        return envelope(result, warns, "CALCULATED", "window data-quality check")

    modules.append(_run("data_quality", "Data quality & provenance", do_quality))

    # ------------------------------------------------ apply enable flags
    for mod in modules:
        if run.get(mod.name) is False and mod.state != "NOT_STARTED":
            mod.state = "NOT_STARTED"
            mod.result = None
            mod.warnings = []
            mod.error = None
            mod.method = None

    counts: dict[str, int] = {}
    for mod in modules:
        counts[mod.state] = counts.get(mod.state, 0) + 1

    failed = [m for m in modules if m.state in {"FAILED", "BLOCKED_BY_MISSING_DATA"}]
    warned = [m for m in modules if m.state == "COMPLETED_WITH_WARNINGS"]

    if failed and any(m.state == "COMPLETED" for m in modules):
        overall = "COMPLETED_WITH_WARNINGS"
    elif failed:
        overall = "FAILED"
    elif warned:
        overall = "COMPLETED_WITH_WARNINGS"
    else:
        overall = "COMPLETED"

    # §5 contract: every module carries the same envelope fields, so a consumer
    # never has to special-case one.
    calculated_at = _now()
    module_rows = []
    for m in modules:
        row = m.to_dict()
        row["symbol"] = symbol
        row["input"] = input_block
        row["calculated_at"] = calculated_at
        module_rows.append(row)

    return {
        "symbol": symbol,
        "method": METHOD,
        "method_version": VERSION,
        "calculated_at": calculated_at,
        "input": input_block,
        "limit_applied": int(limit),
        "overall_state": overall,
        "state_counts": counts,
        "overview": next((m.result for m in modules if m.name == "overview" and m.result), None),
        "modules": module_rows,
        "warnings": [w for m in modules for w in m.warnings],
        "failed": [{"name": m.name, "state": m.state, "error": m.error} for m in failed],
        "classification_note": (
            "CALCULATED = arithmetic on stated inputs; DETECTED = candidate "
            "found by explicit rules. Neither is a recommendation."
        ),
        "caveats": [
            "Stored historical bars, not live quotes. Every price here is dated.",
            "Prices are unadjusted for bonus/split issues.",
            "No module output here is investment advice or a trading signal.",
        ],
    }
