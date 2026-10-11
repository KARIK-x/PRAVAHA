"""FastAPI application: the local research terminal's backend.

Bound to 127.0.0.1 by default. It is a personal tool, so it deliberately does
not bind a public interface, and it never accepts credentials.

Every response that shows market data also shows its provenance and timestamp,
so the front end can never display a number without its source.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from megatool import DISCLAIMER, __version__
from megatool.backtest import (
    STRATEGIES,
    BacktestConfig,
    build_strategy,
    run_backtest,
)
from megatool.config import HOST, PATHS, PORT, ensure_dirs
from megatool.db import get_conn, init_app_db
from megatool.market_store import MarketStore
from megatool.scanner import (
    METRIC_HELP,
    PRESET_SCREENS,
    ScreenNode,
    run_screen,
    to_dataframe,
    validate_tree,
)
from megatool.ta import available as ta_available
from megatool.ta import compute as ta_compute


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class PydanticScreenRequest(BaseModel):
    """Screen request body.

    Declared at module scope on purpose: with postponed (string) annotations
    FastAPI resolves hints against module globals, so a class defined inside
    ``create_app`` would not be recognised as a body model.
    """

    tree: dict[str, Any] = Field(..., description="ScreenNode filter tree")
    symbols: list[str] | None = None
    as_of: date | None = None
    min_bars: int = 30


class PydanticBacktestRequest(BaseModel):
    """Backtest request body (module scope for the same reason as above)."""

    symbol: str
    strategy: str = "sma_cross"
    params: dict[str, Any] = Field(default_factory=dict)
    start: date | None = None
    end: date | None = None
    initial_cash: float = Field(100_000.0, gt=0)
    fee_rate: float = Field(0.004, ge=0)
    slippage: float = Field(0.0, ge=0)
    execution: str = "next_open"
    whole_units: bool = True


def create_app(store: MarketStore | None = None) -> FastAPI:
    ensure_dirs()
    init_app_db()

    shared_store = store

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_app_db()
        yield
        if shared_store is not None:
            shared_store.close()

    app = FastAPI(
        title="Mega Tool",
        version=__version__,
        description="Local NEPSE research and trading-analysis terminal. " + DISCLAIMER,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    def get_store() -> MarketStore:
        nonlocal shared_store
        if shared_store is None:
            shared_store = MarketStore()
        return shared_store

    # ------------------------------------------------------------------ meta
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        try:
            store = get_store()
            bars = store.bar_count()
            symbols = len(store.symbols())
            db_ok = True
        except Exception:
            bars, symbols, db_ok = 0, 0, False
            store = None  # type: ignore[assignment]
        return {
            "status": "ok" if db_ok else "degraded",
            "version": __version__,
            "time": _now(),
            "market_db_open": db_ok,
            "bars_stored": bars,
            "symbols_stored": symbols,
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        """Data freshness + provenance. Never claims live data."""
        store = get_store()
        cov = store.global_coverage()
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT source, status, finished_at, symbols_succeeded, rows_inserted "
                    "FROM ingestion_log ORDER BY id DESC LIMIT 10"
                ).fetchall()
                history = [dict(r) for r in rows]
        except Exception:
            history = []

        last_date = cov.get("last_date")
        is_live = False  # No official live feed is connected; say so plainly.
        return {
            "coverage": cov,
            "recent_ingestions": history,
            "live_feed_connected": is_live,
            "data_as_of": last_date,
            "note": (
                "Mega Tool has no live NEPSE feed. The official API requires an "
                "authenticated session and is not used. All figures are from the "
                "stored historical dataset and are dated by `data_as_of`."
            ),
        }

    @app.get("/api/sources")
    def sources() -> dict[str, Any]:
        from megatool.datasources.nepalstock_official import NepalStockOfficialAdapter
        from megatool.datasources.nepse_data_repo import NepseDataRepoAdapter

        out = []
        for adapter in (NepseDataRepoAdapter(), NepalStockOfficialAdapter()):
            try:
                out.append(
                    adapter.describe() | {"available": adapter.health().get("available", False)}
                )
            except Exception as exc:  # pragma: no cover - defensive
                out.append({"label": "unknown", "error": str(exc)})
        return {"sources": out}

    # ------------------------------------------------------------- securities
    @app.get("/api/securities")
    def securities(q: str | None = None, limit: int = Query(200, le=2000)) -> dict[str, Any]:
        store = get_store()
        df = store.coverage()
        if q:
            mask = df["symbol"].str.contains(q.upper().strip(), case=False, na=False)
            df = df[mask]
        df = df.head(limit)
        return {
            "count": len(df),
            "securities": [
                {
                    "symbol": r["symbol"],
                    "bars": int(r["bars"]),
                    "first_date": str(r["first_date"]),
                    "last_date": str(r["last_date"]),
                    "suspect_rows": int(r["suspect_rows"] or 0),
                    "invalid_rows": int(r["invalid_rows"] or 0),
                }
                for _, r in df.iterrows()
            ],
        }

    # ------------------------------------------------------------------ bars
    @app.get("/api/bars/{symbol}")
    def bars(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = Query(None, le=5000),
    ) -> dict[str, Any]:
        store = get_store()
        df = store.get_bars(symbol.upper(), start=start, end=end, limit=limit)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol.upper()}")
        src = sorted(set(df["source"].dropna()))
        return {
            "symbol": symbol.upper(),
            "count": len(df),
            "sources": src,
            "first_date": str(df["trading_date"].min().date()),
            "last_date": str(df["trading_date"].max().date()),
            "adjustment_status": sorted(set(df["adjustment_status"].dropna())),
            "bars": _bars_payload(df),
        }

    def _bars_payload(df: pd.DataFrame) -> list[dict[str, Any]]:
        out = []
        for _, r in df.iterrows():
            out.append(
                {
                    "time": str(r["trading_date"].date()),
                    "open": _f(r.get("open")),
                    "high": _f(r.get("high")),
                    "low": _f(r.get("low")),
                    "close": _f(r.get("close")),
                    "volume": _i(r.get("volume")),
                    "turnover": _f(r.get("turnover")),
                    "percent_change": _f(r.get("percent_change")),
                    "validation_status": r.get("validation_status"),
                    "flags": [x for x in str(r.get("flags") or "").split(",") if x],
                }
            )
        return out

    # ----------------------------------------------------------- indicators
    @app.get("/api/indicators")
    def indicators(category: str | None = None) -> dict[str, Any]:
        return {"indicators": ta_available(category), "metrics": METRIC_HELP}

    @app.get("/api/bars/{symbol}/indicator")
    def indicator(
        symbol: str,
        name: str,
        start: date | None = None,
        end: date | None = None,
        params: str | None = Query(
            None, description="JSON object overriding the indicator's default parameters"
        ),
    ) -> dict[str, Any]:
        store = get_store()
        df = store.get_bars(symbol.upper(), start=start, end=end)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol.upper()}")

        overrides: dict[str, Any] = {}
        if params:
            try:
                parsed = json.loads(params)
            except json.JSONDecodeError as exc:
                raise HTTPException(400, f"`params` is not valid JSON: {exc}") from exc
            if not isinstance(parsed, dict):
                raise HTTPException(400, "`params` must be a JSON object")
            overrides = parsed

        data = {
            "open": df["open"].to_numpy(float),
            "high": df["high"].to_numpy(float),
            "low": df["low"].to_numpy(float),
            "close": df["close"].to_numpy(float),
            "volume": df["volume"].to_numpy(float),
        }
        try:
            r = ta_compute(name, data, **overrides)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        series: dict[str, list[float | None]] = {}
        for col, vals in r.values.items():
            series[col] = [None if (v is None or np.isnan(v)) else float(v) for v in vals]
        return {
            "symbol": symbol.upper(),
            "indicator": name,
            "params": r.params,
            "warmup": r.warmup,
            "output_warmup": r.output_warmup,
            "insufficient_data": r.insufficient_data,
            "message": r.message,
            "dates": [str(d.date()) for d in df["trading_date"]],
            "series": series,
        }

    # ---------------------------------------------------------------- screen
    @app.get("/api/screen/presets")
    def screen_presets() -> dict[str, Any]:
        return {
            "presets": [{"key": k, **v} for k, v in PRESET_SCREENS.items()],
            "metrics": METRIC_HELP,
        }

    @app.post("/api/screen")
    def screen(req: PydanticScreenRequest) -> dict[str, Any]:
        try:
            node = ScreenNode.from_dict(req.tree)
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, f"invalid screen definition: {exc}") from exc
        problems = validate_tree(node)
        if problems:
            raise HTTPException(400, "invalid screen definition: " + "; ".join(problems))
        store = get_store()
        results = run_screen(
            store, node, symbols=req.symbols, as_of=req.as_of, min_bars=req.min_bars
        )
        passed = [r for r in results if r.passed]
        ineligible = [r for r in results if not r.eligible]
        return {
            "rendered": node.render(),
            "evaluated": len(results),
            "eligible": sum(1 for r in results if r.eligible),
            "passed": len(passed),
            "ineligible": len(ineligible),
            "results": [
                {
                    "symbol": r.symbol,
                    "eligible": r.eligible,
                    "passed": r.passed,
                    "last_date": r.last_date,
                    "note": r.note,
                    "reasons": r.reasons,
                    "failures": r.failures,
                }
                for r in results
                if r.passed or not r.eligible
            ],
        }

    @app.get("/api/screen/export.csv")
    def screen_export(tree: str) -> str:
        """Export a screen as CSV. `tree` is a JSON filter tree."""
        import json

        try:
            node = ScreenNode.from_dict(json.loads(tree))
        except Exception as exc:
            raise HTTPException(400, f"invalid screen definition: {exc}") from exc
        problems = validate_tree(node)
        if problems:
            raise HTTPException(400, "invalid screen definition: " + "; ".join(problems))
        df = to_dataframe(run_screen(get_store(), node))
        return Response(
            content=df.to_csv(index=False),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=screen.csv"},
        )

    # ------------------------------------------------------------- dashboard
    # ------------------------------------------------------------- backtest
    @app.get("/api/strategies")
    def strategies() -> dict[str, Any]:
        """The strategies the engine can run, with their default parameters."""
        return {
            "strategies": [
                {
                    "key": key,
                    "label": spec["label"],
                    "description": spec["description"],
                    "params": spec["params"],
                }
                for key, spec in STRATEGIES.items()
            ],
            "config_defaults": {
                "initial_cash": 100_000.0,
                "fee_rate": 0.004,
                "slippage": 0.0,
                "execution": "next_open",
                "whole_units": True,
            },
            "note": "Backtests are historical calculations with the assumptions "
            "listed in the response. They are not predictions or advice.",
        }

    @app.post("/api/backtest")
    def backtest(req: PydanticBacktestRequest) -> dict[str, Any]:
        store = get_store()
        df = store.get_bars(req.symbol.upper(), start=req.start, end=req.end)
        if df.empty:
            raise HTTPException(404, f"no stored history for {req.symbol.upper()}")
        if len(df) < 2:
            raise HTTPException(
                400, f"only {len(df)} bar(s) stored for {req.symbol.upper()}; need at least 2"
            )
        try:
            signal_fn, label, params = build_strategy(req.strategy, **req.params)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            cfg = BacktestConfig(
                initial_cash=req.initial_cash,
                fee_rate=req.fee_rate,
                slippage=req.slippage,
                execution=req.execution,  # type: ignore[arg-type]
                whole_units=req.whole_units,
            )
            result = run_backtest(
                df,
                signal_fn,
                cfg,
                symbol=req.symbol.upper(),
                strategy=label,
                params=params,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        payload = result.to_dict()
        payload["data_as_of"] = str(df["trading_date"].max().date())
        payload["live"] = False
        payload["note"] = (
            "Historical calculation only. The assumptions are listed in "
            "`assumptions`; past performance does not indicate future results."
        )
        return payload

    @app.get("/api/dashboard")
    def dashboard(top: int = Query(10, le=50)) -> dict[str, Any]:
        """Market snapshot from the most recent stored bar per symbol.

        This is NOT a live market summary. Breadth and movers are computed from
        the latest stored trading day, which is dated explicitly.
        """
        store = get_store()
        latest = store.latest_bars()
        if latest.empty:
            return {"empty": True, "note": "No market data stored yet. Run `megatool fetch`."}

        as_of = str(pd.to_datetime(latest["trading_date"]).max().date())
        df = latest.copy()
        df["change_pct"] = pd.to_numeric(df["percent_change"], errors="coerce")

        advancers = int((df["change_pct"] > 0).sum())
        decliners = int((df["change_pct"] < 0).sum())
        unchanged = int((df["change_pct"] == 0).sum())
        unknown = int(df["change_pct"].isna().sum())

        movers = df.dropna(subset=["change_pct"]).sort_values("change_pct")
        gainers = movers.tail(top)[::-1]
        losers = movers.head(top)
        active = df.dropna(subset=["turnover"]).sort_values("turnover", ascending=False).head(top)

        total_turnover = float(pd.to_numeric(df["turnover"], errors="coerce").fillna(0).sum())
        total_volume = float(pd.to_numeric(df["volume"], errors="coerce").fillna(0).sum())

        return {
            "data_as_of": as_of,
            "is_live": False,
            "symbols": len(df),
            "breadth": {
                "advancers": advancers,
                "decliners": decliners,
                "unchanged": unchanged,
                "unknown": unknown,
            },
            "total_turnover": total_turnover,
            "total_volume": total_volume,
            "gainers": _mover_rows(gainers),
            "losers": _mover_rows(losers),
            "most_active": [
                {
                    "symbol": r["symbol"],
                    "close": _f(r["close"]),
                    "volume": _i(r["volume"]),
                    "turnover": _f(r["turnover"]),
                }
                for _, r in active.iterrows()
            ],
            "note": (
                "Computed from the most recent stored trading day, not a live feed. "
                "NEPSE index and sector indices are not available without the "
                "official authenticated API, so no index value is shown."
            ),
        }

    def _mover_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
        return [
            {
                "symbol": r["symbol"],
                "close": _f(r["close"]),
                "change_pct": _f(r["change_pct"]),
                "volume": _i(r["volume"]),
                "turnover": _f(r["turnover"]),
            }
            for _, r in frame.iterrows()
        ]

    # --------------------------------------------------------------- quality
    @app.get("/api/quality")
    def quality(symbol: str | None = None) -> dict[str, Any]:
        from megatool.quality import validate_series

        store = get_store()
        symbols = [symbol.upper()] if symbol else store.symbols(min_bars=1)[:50]
        reports = []
        for s in symbols:
            df = store.get_bars(s)
            if df.empty:
                continue
            _, rep = validate_series(df)
            reports.append(rep.as_dict())
        return {
            "symbols_checked": len(reports),
            "reports": reports,
            "total_rows": sum(r["rows_checked"] for r in reports),
            "total_suspect": sum(r["suspect"] for r in reports),
            "total_invalid": sum(r["invalid"] for r in reports),
        }

    # ------------------------------------------------------------- portfolio
    @app.get("/api/portfolio")
    def portfolio() -> dict[str, Any]:
        """Holdings valued at the latest stored close.

        This is an analytical estimate, NOT a broker settlement statement.
        """
        store = get_store()
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT symbol, quantity, avg_cost, opened_at, notes FROM portfolio_positions "
                "ORDER BY symbol"
            ).fetchall()
            txns = conn.execute(
                "SELECT symbol, side, quantity, price, fees, traded_at FROM "
                "portfolio_transactions ORDER BY traded_at"
            ).fetchall()

        positions = [dict(r) for r in rows]
        if not positions:
            return {
                "positions": [],
                "transactions": [dict(t) for t in txns],
                "note": "No positions recorded. Add them via the Portfolio page.",
            }

        latest = {r["symbol"]: r for _, r in store.latest_bars().iterrows()}
        out = []
        total_value = 0.0
        total_cost = 0.0
        missing_price = []
        for p in positions:
            sym = p["symbol"]
            row = latest.get(sym)
            value = cost = pnl = None
            if row is not None and row["close"] is not None and not pd.isna(row["close"]):
                value = float(row["close"]) * p["quantity"]
                cost = p["avg_cost"] * p["quantity"]
                pnl = value - cost
                total_value += value
                total_cost += cost
            else:
                missing_price.append(sym)
            out.append(
                {
                    **p,
                    "last_close": _f(row["close"]) if row is not None else None,
                    "last_date": str(row["trading_date"].date()) if row is not None else None,
                    "market_value": value,
                    "cost_basis": cost,
                    "unrealised_pnl": pnl,
                    "unrealised_pnl_pct": (pnl / cost * 100.0)
                    if (pnl is not None and cost)
                    else None,
                    "priced": row is not None,
                }
            )
        for p in out:
            p["weight_pct"] = (
                (p["market_value"] / total_value * 100.0)
                if (p["market_value"] and total_value)
                else None
            )

        return {
            "positions": out,
            "transactions": [dict(t) for t in txns],
            "total_market_value": total_value or None,
            "total_cost_basis": total_cost or None,
            "total_unrealised_pnl": (total_value - total_cost) if total_value else None,
            "unpriced_symbols": missing_price,
            "note": (
                "Valued at the latest stored close (see each row's `last_date`). "
                "This is an analytical estimate, not a broker settlement record."
            ),
        }

    # Serve the terminal UI (same origin, no CORS involved).
    if PATHS.web.exists():
        app.mount("/", StaticFiles(directory=str(PATHS.web), html=True), name="web")

    return app


def _f(v: object) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _i(v: object) -> int | None:
    x = _f(v)
    return None if x is None else int(round(x))


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":  # pragma: no cover
    run()
