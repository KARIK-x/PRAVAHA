"""FastAPI application: the local research terminal's backend.

Bound to 127.0.0.1 by default. It is a personal tool, so it deliberately does
not bind a public interface, and it never accepts credentials.

Every response that shows market data also shows its provenance and timestamp,
so the front end can never display a number without its source.
"""

from __future__ import annotations

import json
import re
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
from megatool.floorsheet import (
    FloorSheetError,
)
from megatool.floorsheet import (
    import_floorsheet as floorsheet_import,
)
from megatool.floorsheet import (
    list_sessions as floorsheet_sessions,
)
from megatool.floorsheet import (
    summary as floorsheet_summary,
)
from megatool.forecast import (
    MODELS as FORECAST_MODELS,
)
from megatool.forecast import (
    ForecastError,
    compare_models,
    naive_drift_check,
    run_forecast,
)
from megatool.fundamentals import (
    FundamentalError,
    records_from_rows,
)
from megatool.fundamentals import (
    fundamentals_summary as fundamentals_counts,
)
from megatool.fundamentals import (
    import_records as fundamentals_import,
)
from megatool.fundamentals import (
    query_symbol as fundamentals_query,
)
from megatool.fundamentals import (
    read_csv as fundamentals_read_csv,
)
from megatool.journal import (
    JournalError,
    journal_stats,
)
from megatool.journal import (
    create_entry as journal_create,
)
from megatool.journal import (
    delete_entry as journal_delete,
)
from megatool.journal import (
    get_entry as journal_get,
)
from megatool.journal import (
    grade_entry as journal_grade,
)
from megatool.journal import (
    list_entries as journal_list,
)
from megatool.journal import (
    update_entry as journal_update,
)
from megatool.market_store import MarketStore
from megatool.planning import PlanError, make_plan, plan_outcome, position_size
from megatool.portfolio import (
    PortfolioError,
    add_manual_position,
    add_transaction,
    delete_transaction,
    list_transactions,
    remove_manual_position,
    value_portfolio,
)
from megatool.ranking import (
    DEFAULT_WEIGHTS,
    PRICE_FACTORS,
    UNAVAILABLE_FACTORS,
    RankConfig,
    rank_universe,
)
from megatool.research import (
    TOPIC_HELP,
    TOPICS,
    journal_only_answer,
)
from megatool.research import (
    answer as research_answer,
)
from megatool.research import (
    build_report as research_report,
)
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
from megatool.walkforward import WalkForwardConfig, walk_forward


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


class PydanticRankRequest(BaseModel):
    """Ranking request body. Declared at module scope for the same reason as
    :class:`PydanticScreenRequest`.

    ``weights`` only overrides the factors it names; omitted factors keep their
    defaults. Only factors with real backing data can receive a positive weight.
    """

    symbols: list[str] | None = None
    as_of: date | None = None
    min_bars: int = Field(60, ge=1, le=10_000)
    max_missing_fraction: float = Field(0.5, ge=0.0, le=1.0)
    weights: dict[str, float] | None = None
    top: int = Field(50, ge=1, le=1000)


class PydanticWalkForwardRequest(BaseModel):
    """Walk-forward validation request.

    Bounded by default: a monthly walk-forward over the full history takes
    minutes, so the defaults keep a single request inside a reasonable time.
    """

    frequency: str = Field("Q", description="M (monthly) or Q (quarterly)")
    start: date | None = None
    end: date | None = None
    top_quantile: float = Field(0.25, ge=0.01, le=0.5)
    min_bars: int = Field(60, ge=1, le=10_000)
    max_missing_fraction: float = Field(0.5, ge=0.0, le=1.0)
    weights: dict[str, float] | None = None
    permutations: int = Field(100, ge=0, le=2000)
    random_seed: int = 20261012


class PydanticFundamentalsImport(BaseModel):
    """CSV payload for the Fundamentals Lab.

    ``format='csv'`` means ``content`` is a full CSV document with a header
    row. Nothing here reaches the network: the caller supplies the file.
    """

    content: str = Field(..., description="CSV text with a header row")
    dry_run: bool = Field(False, description="Validate and report counts without writing anything")


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


class PydanticTransactionRequest(BaseModel):
    """One portfolio transaction."""

    symbol: str
    side: str
    quantity: Any
    price: Any
    fees: Any = 0.0
    traded_at: str | None = None
    notes: str | None = None


class PydanticManualPositionRequest(BaseModel):
    symbol: str
    quantity: int
    avg_cost: float
    notes: str | None = None


class PydanticJournalRequest(BaseModel):
    """Free-form journal payload: every field is optional and validated in
    ``journal._clean``, so the model just needs to accept the keys."""

    model_config = {"extra": "allow"}


class PydanticPlanRequest(BaseModel):
    entry: float
    stop: float
    target: float
    exit_price: float | None = None
    capital: float | None = None
    risk_pct: float | None = None


class PydanticForecastRequest(BaseModel):
    """Forecast one symbol's stored closes."""

    symbol: str
    model: str = "naive"
    horizon: int = Field(5, ge=1, le=120)
    holdout: int | None = Field(None, ge=1, le=1000)
    params: dict[str, Any] = Field(default_factory=dict)
    start: date | None = None
    end: date | None = None


class PydanticForecastCompareRequest(BaseModel):
    """Score every registered model on the identical split."""

    symbol: str
    horizon: int = Field(5, ge=1, le=120)
    holdout: int | None = Field(None, ge=1, le=1000)
    start: date | None = None
    end: date | None = None


class PydanticAskRequest(BaseModel):
    """A plain-language question for the research assistant."""

    symbol: str
    question: str = Field("", max_length=500)


class PydanticFloorSheetRequest(BaseModel):
    """One session's floor sheet, pasted as CSV text."""

    text: str = Field(min_length=1, max_length=20_000_000)
    traded_at: str
    source: str = "manual import"


class PydanticReviewRequest(BaseModel):
    """Set the review status of specific extracted PDF records."""

    ids: list[int] = Field(min_length=1, max_length=5000)
    status: str


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
    def securities(q: str | None = None, limit: int = Query(200, ge=1, le=2000)) -> dict[str, Any]:
        store = get_store()
        df = store.coverage()
        if q:
            # ``q`` is user input reaching a regular expression. Unescaped, a
            # stray "(" raises (a 500), and a "." silently matches more than
            # the trader typed ("A.C" matching "ABC").
            mask = df["symbol"].str.contains(re.escape(q.upper().strip()), case=False, na=False)
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
        limit: int | None = Query(None, ge=1, le=5000),
        include_flagged: bool = Query(
            False,
            description=(
                "include rows marked validation_status=invalid (physically "
                "impossible: high<low, negative/zero price, missing OHLC). "
                "Off by default so charting and indicators never see them; "
                "on for diagnosing what the quality report found."
            ),
        ),
    ) -> dict[str, Any]:
        store = get_store()
        df = store.get_bars(
            symbol.upper(), start=start, end=end, limit=limit, include_invalid=include_flagged
        )
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

    @app.post("/api/rank")
    def rank(req: PydanticRankRequest) -> dict[str, Any]:
        """Rank the stored universe by transparent, weighted factors.

        Every factor's percentile and its weighted contribution are returned,
        so a score can be reconstructed by hand. Factors without backing data
        are listed under ``unavailable`` and score nothing.
        """
        weights = dict(DEFAULT_WEIGHTS)
        if req.weights:
            for key, value in req.weights.items():
                if key not in PRICE_FACTORS:
                    raise HTTPException(
                        400,
                        f"unknown factor {key!r}; known factors: "
                        + ", ".join(sorted(PRICE_FACTORS)),
                    )
                if value < 0:
                    raise HTTPException(400, f"weight for {key!r} must be >= 0")
                weights[key] = float(value)

        config = RankConfig(
            weights=weights,
            min_bars=req.min_bars,
            max_missing_fraction=req.max_missing_fraction,
            as_of=req.as_of.isoformat() if req.as_of else None,
        )

        store = get_store()
        wanted = list(req.symbols) if req.symbols else store.symbols(min_bars=1)
        frames: dict[str, pd.DataFrame] = {}
        for symbol in wanted:
            df = store.get_bars(symbol.upper(), end=req.as_of)
            if not df.empty:
                frames[symbol.upper()] = df

        if not frames:
            raise HTTPException(404, "no stored history for the requested symbols")

        try:
            result = rank_universe(frames, config)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        payload = result.to_dict()
        payload["requested"] = len(wanted)
        payload["truncated_to"] = req.as_of.isoformat() if req.as_of else None
        payload["unavailable"] = UNAVAILABLE_FACTORS
        payload["top"] = payload["ranked"][: req.top]
        payload["disclaimer"] = (
            "A ranking is a research view over past data. It is not a "
            "prediction, a recommendation, or a trading signal, and it does "
            "not indicate expected profit."
        )
        return payload

    # ------------------------------------------------------- walk-forward
    @app.post("/api/walk-forward")
    def walk_forward_endpoint(req: PydanticWalkForwardRequest) -> dict[str, Any]:
        """Validate the ranking historically: rank at each period end, hold the
        tails, measure what happened next.

        This is the honest test of whether the ranking has ever worked. It
        ranks using only data available at each rebalance date, so there is no
        look-ahead, and it reports the result against both the whole-universe
        benchmark and a random-selection baseline.

        The response always carries the caveats. Read them before reading the
        numbers.
        """
        weights = dict(DEFAULT_WEIGHTS)
        if req.weights:
            for key, value in req.weights.items():
                if key not in PRICE_FACTORS:
                    raise HTTPException(
                        400,
                        f"unknown factor {key!r}; known factors: "
                        + ", ".join(sorted(PRICE_FACTORS)),
                    )
                if value < 0:
                    raise HTTPException(400, f"weight for {key!r} must be >= 0")
                weights[key] = float(value)

        config = WalkForwardConfig(
            frequency=req.frequency,
            start=req.start.isoformat() if req.start else None,
            end=req.end.isoformat() if req.end else None,
            top_quantile=req.top_quantile,
            min_bars=req.min_bars,
            max_missing_fraction=req.max_missing_fraction,
            weights=weights,
            permutations=req.permutations,
            random_seed=req.random_seed,
        )
        problems = config.validate()
        if problems:
            raise HTTPException(400, "; ".join(problems))

        store = get_store()
        frames: dict[str, pd.DataFrame] = {}
        for symbol in store.symbols(min_bars=1):
            df = store.get_bars(symbol)
            if not df.empty:
                frames[symbol] = df
        if not frames:
            raise HTTPException(404, "no stored history to validate")

        result = walk_forward(frames, config)
        payload = result.to_dict()
        payload["disclaimer"] = (
            "A walk-forward spread is a research measurement over past data. It "
            "is not a prediction, a recommendation, or a trading signal, and it "
            "does not indicate expected profit. The caveats in this response "
            "apply to every number in it."
        )
        return payload

    # ----------------------------------------------------------- fundamentals
    @app.get("/api/fundamentals/summary")
    def fundamentals_summary_endpoint() -> dict[str, Any]:
        with get_conn() as conn:
            return fundamentals_counts(conn)

    @app.get("/api/fundamentals/{symbol}")
    def fundamentals_for_symbol(symbol: str) -> dict[str, Any]:
        with get_conn() as conn:
            rows = fundamentals_query(conn, symbol)
        return {
            "symbol": symbol.upper(),
            "count": len(rows),
            "records": rows,
            "note": (
                "Each row carries its reporting period, unit, source and "
                "verification level. A value marked 'extracted' has not been "
                "checked and must not be treated as a current figure."
            ),
        }

    @app.post("/api/fundamentals/import")
    def fundamentals_import_endpoint(req: PydanticFundamentalsImport) -> dict[str, Any]:
        """Validate and store a CSV of fundamentals supplied by the caller."""
        try:
            rows = fundamentals_read_csv(req.content)
            records = records_from_rows(rows)
        except FundamentalError as exc:
            raise HTTPException(400, f"rejected: {exc}") from exc

        summary = {
            "accepted": len(records),
            "symbols": len({r.symbol for r in records}),
            "fields": sorted({r.field for r in records}),
            "without_period": sum(1 for r in records if r.period_end is None),
            "by_verification": {
                level: sum(1 for r in records if r.verification == level)
                for level in ("extracted", "reviewed", "verified")
            },
            "dry_run": req.dry_run,
        }
        if req.dry_run:
            summary["written"] = 0
            return summary

        with get_conn() as conn:
            result = fundamentals_import(records, conn)
        summary["written"] = result["total"]
        summary["inserted"] = result["inserted"]
        summary["updated"] = result["updated"]
        return summary

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

    # ------------------------------------------------------------ floor sheet
    @app.post("/api/floorsheet/import")
    def floorsheet_import_route(req: PydanticFloorSheetRequest) -> dict[str, Any]:
        """Import one session's floor sheet (CSV text).

        There is no floor-sheet API to call, so this is import-based by design.
        Re-importing the same file for the same session adds nothing.
        """
        try:
            return floorsheet_import(req.text, req.traded_at, source=req.source)
        except FloorSheetError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/floorsheet/sessions")
    def floorsheet_session_list() -> dict[str, Any]:
        sessions = floorsheet_sessions()
        return {
            "sessions": sessions,
            "note": "Sessions with an imported floor sheet. An empty list means "
            "nothing has been imported, not that nothing traded.",
        }

    @app.get("/api/floorsheet/summary")
    def floorsheet_summary_route(
        traded_at: str | None = None,
        symbol: str | None = None,
        top: int = Query(10, ge=1, le=100),
    ) -> dict[str, Any]:
        """Concentration and counterparty analysis. Descriptive, never a signal."""
        return floorsheet_summary(traded_at=traded_at, symbol=symbol, top=top)

    # ------------------------------------------------------------ written pdf
    @app.get("/api/written-pdf/records")
    def written_pdf_records(
        symbol: str | None = None,
        record_type: str | None = None,
        page: int | None = None,
        reviewed_only: bool = False,
    ) -> dict[str, Any]:
        """Records extracted from Written Data.pdf.

        Every record carries its source page, extraction confidence, and review
        status. Unreviewed records are included but flagged: they are a personal
        journal, not independently verified market data.
        """
        from megatool.written_pdf import RecordType, ReviewStatus, query_records

        # Validate the record type. An unknown value is a client error
        # (400), not a server error (500).
        record_type_enum: RecordType | None = None
        if record_type:
            try:
                record_type_enum = RecordType(record_type)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"unknown record_type: {record_type!r}. "
                    f"Valid types: {', '.join(t.value for t in RecordType)}",
                ) from exc

        rows = query_records(
            symbol=symbol,
            record_type=record_type_enum,
            page=page,
            review_status=ReviewStatus.REVIEWED if reviewed_only else None,
        )
        return {
            "count": len(rows),
            "records": rows,
            "note": (
                "Records from a handwritten personal journal. They are descriptive "
                "historical observations, not verified market data. Review status "
                "is shown per record."
            ),
        }

    @app.get("/api/written-pdf/summary")
    def written_pdf_summary() -> dict[str, Any]:
        """Coverage of the PDF extraction: how many records, by type and review status."""
        from megatool.written_pdf import query_records

        rows = query_records()
        by_type: dict[str, int] = {}
        by_review: dict[str, int] = {}
        by_page: dict[int, int] = {}
        for r in rows:
            by_type[r["record_type"]] = by_type.get(r["record_type"], 0) + 1
            by_review[r["review_status"]] = by_review.get(r["review_status"], 0) + 1
            by_page[r["page"]] = by_page.get(r["page"], 0) + 1
        return {
            "total": len(rows),
            "by_type": by_type,
            "by_review_status": by_review,
            "pages_covered": len(by_page),
            "note": (
                "Extraction from a 52-page handwritten journal. Automated OCR failed "
                "on 42 of 52 pages; records were transcribed by visual inspection. "
                "All values require human review before financial use."
            ),
        }

    @app.post("/api/written-pdf/review")
    def written_pdf_review(req: PydanticReviewRequest) -> dict[str, Any]:
        """Mark extracted records as reviewed, corrected, or rejected.

        This is the human-verification step. Records start `unreviewed` and
        are never surfaced as findings until a human flips them here.
        """
        from megatool.written_pdf import PdfValidationError, ReviewStatus, set_review_status

        try:
            status = ReviewStatus(req.status)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"unknown status: {req.status!r}. "
                f"Valid: {', '.join(s.value for s in ReviewStatus)}",
            ) from exc
        try:
            return set_review_status(req.ids, status)
        except PdfValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ----------------------------------------------------------- forecasting
    @app.get("/api/forecast/models")
    def forecast_models() -> dict[str, Any]:
        """The models on offer, with their default parameters."""
        return {
            "models": [{"key": key, **spec} for key, spec in FORECAST_MODELS.items()],
            "note": (
                "Every model is scored against the naive 'last value' forecast on "
                "a hold-out window it never saw. Beating that baseline once is "
                "not evidence of a tradeable edge."
            ),
        }

    @app.post("/api/forecast")
    def forecast(req: PydanticForecastRequest) -> dict[str, Any]:
        """Fit on the past, score on an unseen window, then project forward."""
        store = get_store()
        symbol = req.symbol.upper()
        df = store.get_bars(symbol, start=req.start, end=req.end)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol}")
        try:
            result = run_forecast(
                df["close"].to_numpy(),
                model=req.model,
                horizon=req.horizon,
                holdout=req.holdout,
                params=req.params,
                dates=[str(d.date()) for d in df["trading_date"]],
            )
        except ForecastError as exc:
            raise HTTPException(400, str(exc)) from exc
        payload = result.to_dict()
        payload["symbol"] = symbol
        payload["data_as_of"] = str(df["trading_date"].max().date())
        payload["live"] = False
        payload["random_walk"] = naive_drift_check(df["close"].to_numpy())
        payload["note"] = (
            "Statistical projection of stored, UNADJUSTED closes. This is not a "
            "prediction of what the market will do and not investment advice."
        )
        return payload

    @app.post("/api/forecast/compare")
    def forecast_compare(req: PydanticForecastCompareRequest) -> dict[str, Any]:
        """Rank every model on one identical, honest split."""
        store = get_store()
        symbol = req.symbol.upper()
        df = store.get_bars(symbol, start=req.start, end=req.end)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol}")
        out = compare_models(
            df["close"].to_numpy(),
            horizon=req.horizon,
            holdout=req.holdout,
            dates=[str(d.date()) for d in df["trading_date"]],
        )
        out["symbol"] = symbol
        out["data_as_of"] = str(df["trading_date"].max().date())
        out["live"] = False
        return out

    # -------------------------------------------------- research assistant
    @app.get("/api/research/topics")
    def research_topics() -> dict[str, Any]:
        """What the assistant can answer - and what it refuses to."""
        return {
            "topics": [{"key": k, "help": TOPIC_HELP[k]} for k in TOPICS],
            "what_this_is": (
                "A deterministic rules engine over stored bars. It returns a "
                "number, the window it came from, and the definition used, so "
                "every claim can be checked. There is no language model behind "
                "it: no LLM key exists in this project and no local model fits "
                "this machine."
            ),
            "what_this_is_not": (
                "Not an opinion, not a recommendation, not a prediction. It "
                "cannot read news or filings, and it will not tell you to buy "
                "or sell anything."
            ),
        }

    @app.get("/api/research/{symbol}")
    def research_symbol(symbol: str) -> dict[str, Any]:
        """Full descriptive report for one symbol, every figure cited."""
        store = get_store()
        sym = symbol.upper()
        df = store.get_bars(sym)
        if df.empty:
            # Fall back to journal-only so symbols present in the handwritten
            # records but absent from the stored dataset remain reachable.
            payload = journal_only_answer(sym)
            if payload["pdf_findings"]:
                payload["live"] = False
                return payload
            raise HTTPException(404, f"no stored history for {sym}")
        universe = store.all_closes() if len(store.symbols()) > 1 else None
        payload = research_report(df, sym, universe=universe).to_dict()
        payload["live"] = False
        return payload

    @app.post("/api/research/ask")
    def research_ask(req: PydanticAskRequest) -> dict[str, Any]:
        """Ask a plain question. Predictive questions are refused on purpose."""
        store = get_store()
        sym = req.symbol.upper()
        df = store.get_bars(sym)
        if df.empty:
            # No price history, but the handwritten journal may still cover
            # this symbol. Return the journal answer instead of a bare 404.
            payload = journal_only_answer(sym, req.question)
            if payload["pdf_findings"] or any("not reviewed" in w for w in payload["warnings"]):
                payload["live"] = False
                return payload
            raise HTTPException(404, f"no stored history for {sym}")
        universe = store.all_closes() if len(store.symbols()) > 1 else None
        payload = research_answer(df, sym, req.question, universe=universe)
        payload["live"] = False
        return payload

    # ------------------------------------------------------------- portfolio
    @app.get("/api/portfolio")
    def portfolio() -> dict[str, Any]:
        """Positions derived from your ledger, marked to the latest stored close."""
        return value_portfolio(get_store())

    @app.get("/api/portfolio/transactions")
    def portfolio_transactions(
        symbol: str | None = None, limit: int = Query(500, ge=1, le=5000)
    ) -> dict[str, Any]:
        return {"transactions": [t.to_dict() for t in list_transactions(symbol, limit)]}

    @app.post("/api/portfolio/transactions")
    def portfolio_add_transaction(req: PydanticTransactionRequest) -> dict[str, Any]:
        try:
            tx = add_transaction(req.model_dump())
        except PortfolioError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"transaction": tx.to_dict()}

    @app.delete("/api/portfolio/transactions/{tx_id}")
    def portfolio_delete_transaction(tx_id: int) -> dict[str, Any]:
        if not delete_transaction(tx_id):
            raise HTTPException(404, f"no transaction with id {tx_id}")
        return {"deleted": tx_id}

    @app.post("/api/portfolio/manual")
    def portfolio_manual(req: PydanticManualPositionRequest) -> dict[str, Any]:
        try:
            add_manual_position(req.symbol, req.quantity, req.avg_cost, req.notes)
        except PortfolioError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True, "symbol": req.symbol.upper()}

    @app.delete("/api/portfolio/manual/{symbol}")
    def portfolio_delete_manual(symbol: str) -> dict[str, Any]:
        if not remove_manual_position(symbol):
            raise HTTPException(404, f"no manual position for {symbol.upper()}")
        return {"deleted": symbol.upper()}

    # ---------------------------------------------------------------- journal
    @app.get("/api/journal/stats")
    def journal_statistics() -> dict[str, Any]:
        """Win rate, R multiples and plan adherence over recorded trades."""
        return journal_stats()

    @app.get("/api/journal")
    def journal_entries(
        symbol: str | None = None,
        strategy: str | None = None,
        status: str | None = None,
        limit: int = Query(500, ge=1, le=5000),
    ) -> dict[str, Any]:
        try:
            return {"entries": journal_list(symbol, strategy, status, limit)}
        except JournalError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/journal")
    def journal_new(req: PydanticJournalRequest) -> dict[str, Any]:
        try:
            entry_id = journal_create(req.model_dump(exclude_unset=True))
        except JournalError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"id": entry_id, "entry": journal_get(entry_id)}

    @app.get("/api/journal/{entry_id}")
    def journal_one(entry_id: int) -> dict[str, Any]:
        try:
            return journal_get(entry_id)
        except JournalError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.patch("/api/journal/{entry_id}")
    def journal_patch(entry_id: int, req: PydanticJournalRequest) -> dict[str, Any]:
        # A bad edit (a negative price, a close with no exit) is the owner's
        # input, not a server fault: it must arrive as a 400 with the reason,
        # never as a bare 500.
        try:
            updated = journal_update(entry_id, req.model_dump(exclude_unset=True))
        except JournalError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not updated:
            raise HTTPException(404, f"no journal entry with id {entry_id}")
        return journal_get(entry_id)

    @app.delete("/api/journal/{entry_id}")
    def journal_delete_entry(entry_id: int) -> dict[str, Any]:
        # Named ``journal_delete_entry`` on purpose: a route function called
        # ``journal_delete`` would shadow the imported helper in this scope and
        # recurse forever.
        if not journal_delete(entry_id):
            raise HTTPException(404, f"no journal entry with id {entry_id}")
        return {"deleted": entry_id}

    @app.get("/api/journal/{entry_id}/grade")
    def journal_grade_entry(entry_id: int) -> dict[str, Any]:
        """Grade one closed entry against the plan it was supposed to follow."""
        try:
            graded = journal_grade(entry_id)
        except JournalError as exc:
            raise HTTPException(404, str(exc)) from exc
        if graded is None:
            raise HTTPException(
                400,
                "this entry cannot be graded: it needs an exit price and a plan "
                "(entry, target and invalidation)",
            )
        return graded

    # -------------------------------------------------------------- planning
    @app.post("/api/planning")
    def planning(req: PydanticPlanRequest) -> dict[str, Any]:
        """Turn an entry/stop/target into R multiples and a position size.

        Sizing is computed only when capital and risk_pct are supplied.
        """
        try:
            plan = make_plan(req.entry, req.stop, req.target)
            payload: dict[str, Any] = {"plan": plan.to_dict()}
            if req.capital is not None and req.risk_pct is not None:
                payload["sizing"] = position_size(
                    req.capital, req.risk_pct, plan.risk_per_share, req.entry
                ).to_dict()
            elif req.capital is not None or req.risk_pct is not None:
                raise HTTPException(400, "capital and risk_pct must be supplied together")
        except PlanError as exc:
            raise HTTPException(400, str(exc)) from exc
        payload["note"] = (
            "A plan is arithmetic, not a prediction: it converts your own entry, "
            "stop and target into position size and R multiples. Whether price "
            "reaches either level is unknown."
        )
        return payload

    @app.post("/api/planning/grade")
    def planning_grade(req: PydanticPlanRequest) -> dict[str, Any]:
        """Grade a finished trade against the plan made at entry."""
        if req.exit_price is None:
            raise HTTPException(400, "exit_price is required to grade a trade")
        try:
            return plan_outcome(req.entry, req.stop, req.target, req.exit_price)
        except PlanError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/dashboard")
    def dashboard(top: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
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
