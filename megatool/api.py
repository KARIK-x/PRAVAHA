"""FastAPI application: the local research terminal's backend.

Bound to 127.0.0.1 by default. It is a personal tool, so it deliberately does
not bind a public interface, and it never accepts credentials.

Every response that shows market data also shows its provenance and timestamp,
so the front end can never display a number without its source.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from megatool import DISCLAIMER, __version__, corporate_actions
from megatool import stats as _stats_mod
from megatool.backtest import (
    FEE_SCHEDULES,
    PLACEHOLDER_FEE_RATE,
    STRATEGIES,
    BacktestConfig,
    build_strategy,
    run_backtest,
)
from megatool.config import HOST, PATHS, PORT, ensure_dirs
from megatool.datasources import sector_consensus
from megatool.db import get_conn, init_app_db
from megatool.experiments import (
    ExperimentError,
    compare_experiments,
    delete_experiment,
    get_experiment,
    list_experiments,
    save_experiment,
)
from megatool.experiments import (
    to_markdown as experiment_markdown,
)
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
from megatool.floorsheet import (
    trend as floorsheet_trend,
)
from megatool.forecast import (
    MODELS as FORECAST_MODELS,
)
from megatool.forecast import (
    ForecastError,
    compare_models,
    naive_drift_check,
    rolling_origin,
    run_forecast,
)
from megatool.fundamentals import (
    FundamentalError,
    records_from_rows,
)
from megatool.fundamentals import (
    compute_symbol_ratios as fundamentals_ratios,
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
from megatool.fundamentals import (
    compute_eps_growth,
    compute_ttm_eps,
    historical_pe,
)
from megatool.sectors import canonical_sector
from megatool.journal import (
    JournalError,
    journal_stats,
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
from megatool.market_store import MarketStore, eligibility_from_meta
from megatool.news import (
    NewsError,
    news_summary,
)
from megatool.news import (
    import_news as news_import,
)
from megatool.planning import (
    PlanError,
    constraint_check,
    entry_cost_estimate,
    make_plan,
    plan_outcome,
    position_size,
)
from megatool.portfolio import (
    PortfolioError,
    add_manual_position,
    add_transaction,
    cash_flows,
    delete_transaction,
    derive_positions,
    list_transactions,
    remove_manual_position,
    value_portfolio,
)
from megatool.ranking import (
    DEFAULT_WEIGHTS,
    NEPSE_COMPOSITE_INDEX,
    PRICE_FACTORS,
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
from megatool.rs_timeframes import MAX_LOOKBACKS, parse_lookbacks, timeframe_rows
from megatool.scanner import (
    METRIC_HELP,
    PRESET_SCREENS,
    ScreenNode,
    run_screen,
    to_dataframe,
    validate_tree,
)
from megatool.screens import (
    ScreenError as SavedScreenError,
)
from megatool.screens import (
    delete_screen,
    duplicate_screen,
    get_screen,
    list_screens,
    metric_catalogue,
    save_screen,
    update_screen,
)
from megatool.ta import available as ta_available
from megatool.ta import compute as ta_compute
from megatool.ta.candles import (
    PATTERN_NAMES as CANDLE_PATTERN_TYPES,
)
from megatool.ta.candles import (
    CandleError,
)
from megatool.ta.candles import (
    PatternParams as CandleParams,
)
from megatool.ta.candles import (
    detect_patterns as detect_candle_patterns,
)
from megatool.ta.elliott import analyze_elliott_extended
from megatool.ta.fibonacci import (
    DEFAULT_EXTENSIONS,
    DEFAULT_RETRACEMENTS,
    FibonacciError,
    levels_for,
)
from megatool.ta.harmonic import DEFAULT_SPECS as HARMONIC_SPECS
from megatool.ta.harmonic import analyze_harmonic
from megatool.ta.levels import ZonesError, build_zones
from megatool.ta.multitimeframe import aggregate_daily_to_monthly, aggregate_daily_to_weekly
from megatool.ta.patterns import PATTERN_TYPES, PatternConfig
from megatool.ta.patterns import detect_patterns as detect_chart_patterns
from megatool.ta.swings import (
    DEFAULT_LEFT,
    DEFAULT_RIGHT,
    SwingError,
    classify_structure,
    detect_equal_highs_lows,
    detect_fvgs,
    find_breaks,
    find_swings,
)
from megatool.walkforward import WalkForwardConfig, walk_forward
from megatool.watchlists import (
    WatchlistError,
    create_watchlist,
    delete_watchlist,
    get_watchlist,
    list_watchlists,
    update_watchlist,
)
from megatool.workspace import DEFAULT_LIMIT as DEFAULT_WORKSPACE_LIMIT
from megatool.workspace import build_workspace

#: Modules the workspace can run, used to validate the `modules` filter.
WORKSPACE_MODULES = (
    "overview",
    "structure",
    "fibonacci",
    "levels",
    "trend_momentum_volatility",
    "candlesticks",
    "research_report",
    "data_quality",
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


#: Symbol sanity rule shared by every per-symbol route.
#:
#: Previously six endpoints hard-capped the symbol at 10 characters while four
#: others did not, so a stored symbol longer than 10 chars was analysable on
#: ``/api/bars/{symbol}`` but returned 400 on ``/api/bars/{symbol}/weekly``.
#: Real NEPSE tickers are short, but a *stored* symbol must behave the same on
#: every route. The rule is deliberately about safety (no path separators, no
#: empty/oversized input), not about guessing a ticker's length: an unknown but
#: well-formed symbol still falls through to the normal 404.
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._&-]{0,23}$")
SYMBOL_MAX_LENGTH = 24


def _log_access_boundary() -> None:
    """Print the access-boundary state once at startup.

    The friend boundary is **off** until ``MEGATOOL_FRIEND_TOKEN`` is set, so an
    owner-only process serves private routes (journal, portfolio, transcribed
    records) to any client that can reach the socket. The CLI warns when it is
    asked to bind non-loopback, but ``uvicorn megatool.api:app`` bypasses the CLI
    entirely, so the state is also logged here — on every entrypoint — to make
    the assumption visible instead of implicit.
    """
    import sys

    from megatool.friend_access import boundary_active, friend_origin, friend_token

    if boundary_active():
        if friend_token() is None:
            # require-auth is on but no token is configured: fail closed.
            print(
                "  \u26a0 access boundary: MEGATOOL_REQUIRE_AUTH=1 but NO friend token "
                "is set.\n  Failing CLOSED: every non-loopback request is refused "
                "(401).\n  Set MEGATOOL_FRIEND_TOKEN to serve allowlisted read-only "
                "routes to friends.",
                file=sys.stderr,
            )
            return
        origin = friend_origin() or "(any origin permitted by CORS config)"
        print(
            f"  access boundary: friend token ACTIVE - non-loopback clients must "
            f"authenticate; allowlisted read-only routes only; private records "
            f"stay owner-only; origin {origin}",
            file=sys.stderr,
        )
        return
    host = os.environ.get("MEGATOOL_HOST", HOST)
    port = os.environ.get("MEGATOOL_PORT", str(PORT))
    if host in ("127.0.0.1", "localhost", "::1"):
        print(
            "  access boundary: owner-only (no friend token). Binding "
            f"{host}:{port}; private routes require loopback and are unreachable "
            "off-host.",
            file=sys.stderr,
        )
    else:
        print(
            f"  \u26a0 WARNING: bound to {host} with NO authentication and NO friend\n"
            "  boundary active. Anyone who can reach this address can read and edit\n"
            "  your journal, portfolio and transcribed records. Set\n"
            "  MEGATOOL_FRIEND_TOKEN, or bind 127.0.0.1.",
            file=sys.stderr,
        )


def valid_symbol(symbol: str | None) -> bool:
    """True when ``symbol`` is a safe, well-formed ticker.

    Rejects empty, whitespace, path-traversal-ish or oversized input. It does
    **not** assert the symbol exists — callers report 404 when the store has no
    such series, so a malformed value is a 400 and a missing one a 404.
    """
    if not symbol:
        return False
    s = symbol.strip()
    return bool(_SYMBOL_RE.match(s))


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
    exclude_delisted: bool = Field(
        True,
        description="Exclude verified non-tradable securities (DELISTED, "
        "SUSPENDED, MERGED) from the screen. UNKNOWN symbols are still screened "
        "so missing metadata does not silently erase valid securities, but the "
        "uncertainty is reported in the result note. Pass False to include every "
        "symbol with stored history.",
    )
    instrument_types: list[str] | None = Field(
        None,
        description="Opt-in: keep only securities whose stored instrument_type "
        "is in this list (e.g. ['ordinary']); unknown types are ineligible",
    )


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
    exclude_delisted: bool = Field(
        True,
        description="Exclude verified non-tradable securities (DELISTED, "
        "SUSPENDED, MERGED) from the ranked universe. UNKNOWN symbols are still "
        "ranked so missing metadata does not silently erase valid securities. "
        "Pass False to rank every symbol with stored history.",
    )
    instrument_types: list[str] | None = Field(
        None,
        description="Opt-in: rank only securities whose stored instrument_type "
        "is in this list (e.g. ['ordinary']); unknown types are excluded",
    )


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
    #: OPT-IN verified component schedule (C3/D-y). ``None`` = the legacy
    #: flat fee_rate. When set, fee_rate must be left at its default.
    fee_schedule: str | None = None
    #: OPT-IN CGT declaration; only "natural_person" is accepted (the engine
    #: will not classify an investor entity). Requires fee_schedule.
    cgt: str | None = None


class PydanticWatchlistRequest(BaseModel):
    """Create a watchlist."""

    name: str
    symbols: list[str] | None = None


class PydanticWatchlistPatch(BaseModel):
    """Edit a watchlist: rename, replace, add, or remove."""

    new_name: str | None = None
    symbols: list[str] | None = None
    add: list[str] | None = None
    remove: list[str] | None = None


class PydanticExperimentSave(BaseModel):
    """Persist a backtest run as a reproducible experiment."""

    label: str
    config: dict[str, Any]
    result: dict[str, Any]


class PydanticSavedScreenSave(BaseModel):
    """Persist a custom analytical rule (an AND/OR condition tree)."""

    name: str
    definition: dict[str, Any]
    overwrite: bool = False


class PydanticSavedScreenPatch(BaseModel):
    """Rename a saved screen and/or replace its definition."""

    new_name: str | None = None
    definition: dict[str, Any] | None = None


class PydanticAnalysisRun(BaseModel):
    """Run one quantitative analysis algorithm from the unified catalogue."""

    fn: str
    symbol: str | None = None
    symbols: list[str] | None = None
    params: dict[str, Any] | None = None


class PydanticFundamentalRun(BaseModel):
    """Run one fundamental tool from the unified catalogue."""

    fn: str
    symbol: str


class PydanticReconcileRun(BaseModel):
    """Run one data-source reconciliation comparison."""

    dataset: str
    tolerance: float | None = None


class PydanticReconcileResolve(BaseModel):
    """Record a human decision about one reconciliation finding."""

    dataset: str
    finding_key: str
    resolution: str
    classification: str = ""
    chosen_source: str = ""
    note: str = ""
    actor: str = "local"


class PydanticSnapshotCapture(BaseModel):
    """Capture a reproducible snapshot by running a catalogue feature."""

    feature: str
    params: dict[str, Any] | None = None


class PydanticSnapshotCreate(BaseModel):
    """Persist a snapshot from already-computed results (e.g. a backtest)."""

    feature: str
    params: dict[str, Any] | None = None
    results: dict[str, Any]
    universe: str = ""
    date_range: str = ""
    source_ids: list[str] | None = None
    data_cutoff: str | None = None
    benchmark: str = ""
    costs: str = ""
    seed: str = ""
    warnings: list[str] | None = None
    data_quality: str = "unknown"
    limitations: str = ""
    required: list[str] | None = None
    missing: list[str] | None = None


class PydanticSnapshotCompare(BaseModel):
    """Compare two stored snapshots."""

    a: str
    b: str


class PydanticResearchRun(BaseModel):
    """Ask the evidence-bound research desk a question about one symbol."""

    question: str
    symbol: str
    provider: str | None = None
    max_tokens: int | None = None


class PydanticResearchReview(BaseModel):
    """Run the sceptical review over a piece of text and a symbol's evidence."""

    text: str
    symbol: str


class PydanticNlQuery(BaseModel):
    """A natural-language question over the project's own stored data."""

    question: str


class PydanticCorporateEventsImport(BaseModel):
    """A corporate-event document, pasted as CSV text."""

    text: str = Field(min_length=1, max_length=20_000_000)
    source: str = "manual import"


class PydanticSavedScreenDuplicate(BaseModel):
    """Duplicate a saved screen under a new name."""

    new_name: str


class PydanticRuleProposal(BaseModel):
    """Ask the assistant to propose a screen rule from a plain-language question."""

    question: str = Field(..., min_length=1, max_length=500)


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


class PydanticJournalReflect(BaseModel):
    """Optional AI reflection over one journal entry (feature 5).

    ``authorize_private=false`` (default) means NO model call happens — the
    journal stays local. The flag is the owner's explicit, per-request
    authorization for their private journal content to reach a model.
    """

    provider: str = ""
    authorize_private: bool = False


class PydanticPlanRequest(BaseModel):
    entry: float
    stop: float
    target: float
    exit_price: float | None = None
    capital: float | None = None
    risk_pct: float | None = None
    symbol: str | None = Field(
        None,
        max_length=12,
        description=(
            "with a symbol, the plan is checked against the local portfolio "
            "(current weight, post-trade weight, concentration limit); omit "
            "for pure plan arithmetic"
        ),
    )
    max_weight_pct: float = Field(
        40.0,
        gt=0,
        le=100,
        description="concentration limit for the post-trade weight check",
    )


class PydanticForecastRequest(BaseModel):
    """Forecast one symbol's stored closes."""

    symbol: str
    model: str = "naive"
    horizon: int = Field(5, ge=1, le=120)
    holdout: int | None = Field(None, ge=1, le=1000)
    params: dict[str, Any] = Field(default_factory=dict)
    start: date | None = None
    end: date | None = None


class PydanticKronosForecast(BaseModel):
    """Kronos forecast run: official model on stored daily bars."""

    symbol: str
    pred_len: int = Field(10, ge=1, le=64)
    # hard cap here is mini's official 2048; variant-specific limits are
    # enforced again inside the service (base/small reject > 512)
    context_len: int = Field(256, ge=12, le=2048)
    variant: str = "base"
    temperature: float = Field(1.0, gt=0.0, le=2.0)
    sample_count: int = Field(1, ge=1, le=16)
    device: str | None = None  # "cpu" | "mps" | None (auto)


class PydanticKronosEvaluate(BaseModel):
    """Kronos walk-forward evaluation against honest baselines."""

    symbol: str
    pred_len: int = Field(5, ge=1, le=64)
    variant: str = "base"
    windows: int = Field(6, ge=1, le=24)
    device: str | None = None
    # mini's official 2048 is the schema cap; per-variant limits are enforced
    # in the service (base/small reject > 512)
    context_len: int = Field(256, ge=12, le=2048)


class PydanticForecastCompareRequest(BaseModel):
    """Score every registered model on the identical split."""

    symbol: str
    horizon: int = Field(5, ge=1, le=120)
    holdout: int | None = Field(None, ge=1, le=1000)
    start: date | None = None
    end: date | None = None


class PydanticForecastRollingRequest(BaseModel):
    """Rolling-origin (walk-forward) evaluation across many chronological cuts."""

    symbol: str
    model: str = "naive"
    train_min: int = Field(20, ge=3, le=100_000)
    holdout: int = Field(5, ge=1, le=1000)
    step: int = Field(5, ge=1, le=1000)
    params: dict[str, Any] = Field(default_factory=dict)
    start: date | None = None
    end: date | None = None


class PydanticNewsImportRequest(BaseModel):
    """One owner-supplied file of news records (CSV text or JSON text)."""

    content: str = Field(..., min_length=1)
    format: str = Field("csv", pattern="^(?i)(csv|json)$")
    source: str = Field("", max_length=200)


class PydanticAskRequest(BaseModel):
    """A plain-language question for the research assistant."""

    symbol: str
    question: str = Field("", max_length=500)
    interpret: bool = Field(
        False,
        description=(
            "also request an AI explanation of the deterministic answer; the "
            "deterministic payload is never replaced"
        ),
    )
    include_private: bool = Field(
        False,
        description=(
            "authorization to include personal journal findings in the AI "
            "prompt; default False strips them from any hosted-model context"
        ),
    )
    provider: str = Field("", description="AI provider name; '' (default) uses the configured one")


class PydanticAgentRequest(BaseModel):
    """A research question for the orchestration agent (feature 12)."""

    question: str = Field("", max_length=1000)
    interpret: bool = False
    include_private: bool = False
    provider: str = ""
    tools: list[str] | None = Field(
        None, description="optional explicit tool list; overrides keyword routing"
    )


class PydanticFloorSheetRequest(BaseModel):
    """One session's floor sheet, pasted as CSV text."""

    text: str = Field(min_length=1, max_length=20_000_000)
    traded_at: str
    source: str = "manual import"


class PydanticReviewRequest(BaseModel):
    """Set the review status of specific extracted PDF records."""

    ids: list[int] = Field(min_length=1, max_length=5000)
    status: str


def _save_kronos_experiment(kind: str, req: Any, result: dict[str, Any], device: str) -> int:
    """Persist one Kronos run into ``kronos_experiments`` (schema v8).

    The honest result payload is stored verbatim; little is derived here so
    what a later reader sees is exactly what the server measured. Failures to
    save never fail the forecast itself - a lost log is not a lost forecast.
    """
    from megatool.db import get_conn
    from megatool.db import now_iso as _db_now

    params = {
        "pred_len": req.pred_len,
        "context_len": req.context_len,
        "variant": req.variant,
        "temperature": getattr(req, "temperature", 1.0),
        "sample_count": getattr(req, "sample_count", 1),
        "windows": getattr(req, "windows", None),
    }
    inference = result.get("inference_seconds")
    if inference is None and "avg" in result:
        inference = result["avg"].get("total_seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO kronos_experiments (
                created_at, kind, symbol, variant, device, context_len,
                pred_len, temperature, sample_count, params_json,
                result_json, inference_seconds, note
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                _db_now(),
                kind,
                req.symbol,
                req.variant,
                device or str(result.get("device", "")),
                req.context_len,
                req.pred_len,
                float(getattr(req, "temperature", 1.0)),
                int(getattr(req, "sample_count", 1)),
                json.dumps(params),
                json.dumps(result, default=str),
                inference,
                str(result.get("note", "")),
            ),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        return int(row["id"])


def list_kronos_experiments(
    kind: str | None = None, symbol: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Recent Kronos runs, newest first (payloads included)."""
    from megatool.db import get_conn

    sql = "SELECT * FROM kronos_experiments WHERE 1=1"
    params: list[Any] = []
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol.upper())
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        for col in ("params_json", "result_json"):
            try:
                item[col[:-5]] = json.loads(item[col])
            except (TypeError, ValueError):
                item[col[:-5]] = {}
            del item[col]
        out.append(item)
    return out


def create_app(store: MarketStore | None = None) -> FastAPI:
    ensure_dirs()
    init_app_db()

    shared_store = store

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        import sys as _sys

        init_app_db()
        _log_access_boundary()
        # On a hosted host with an ephemeral disk the market database starts
        # empty. Seed it from the public sources in a BACKGROUND thread so the
        # app serves immediately (the health check never waits on a download)
        # and charts populate as the data lands. Disabled for loopback binds, so
        # local development and the test client never start a download. A failed
        # seed is reported and never kills the app.
        try:
            from megatool.deploy_seed import start_background_seed

            start_background_seed(
                get_store(), log=lambda m: print(m, file=_sys.stderr)
            )
        except Exception as exc:  # noqa: BLE001 - startup must not fail here
            print(f"[seed] startup hook skipped: {type(exc).__name__}: {exc}", file=_sys.stderr)
        yield
        if shared_store is not None:
            shared_store.close()

    app = FastAPI(
        title="PRAVAHA — NEPSE Analytics Platform",
        version=__version__,
        description=(
            "PRAVAHA — NEPSE Analytics Platform. Insights today. A brighter "
            "tomorrow. Local NEPSE research and trading-analysis workspace. "
        ) + DISCLAIMER,
        lifespan=lifespan,
    )
    # Friend boundary FIRST, then CORS, so CORS is the outermost middleware and
    # can answer preflight (OPTIONS) before authentication is considered.
    from megatool.friend_access import FriendAccessMiddleware, friend_origin

    app.add_middleware(FriendAccessMiddleware)

    # Optional, conservative rate limiter for expensive endpoints. Disabled by
    # default (limit 0) so local research and the test suite are unaffected;
    # enable with MEGATOOL_RATE_LIMIT=<requests per minute>.
    _rl = int(os.getenv("MEGATOOL_RATE_LIMIT", "0"))
    if _rl > 0:
        from collections import defaultdict, deque
        import time as _time

        class _RateLimitMiddleware:
            def __init__(self, app):
                self.app = app
                self.buckets: dict[str, deque] = defaultdict(deque)
                self.limit = _rl
                self.window = 60.0

            async def __call__(self, scope, receive, send):
                if scope["type"] != "http":
                    await self.app(scope, receive, send)
                    return
                client = scope.get("client")
                key = client[0] if client else "unknown"
                path = scope.get("path", "")
                # Only throttle expensive endpoints, not health/static.
                if path.startswith("/api/kronos") or path.startswith("/api/market-intelligence/collect"):
                    now = _time.monotonic()
                    bucket = self.buckets[key]
                    while bucket and now - bucket[0] > self.window:
                        bucket.popleft()
                    if len(bucket) >= self.limit:
                        from starlette.responses import JSONResponse
                        resp = JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
                        await resp(scope, receive, send)
                        return
                    bucket.append(now)
                await self.app(scope, receive, send)

        app.add_middleware(_RateLimitMiddleware)

    _origins = ["http://127.0.0.1", "http://localhost"]
    _friend_origin = friend_origin()
    if _friend_origin:
        _origins.append(_friend_origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Friend-Token", "Authorization"],
    )

    def get_store() -> MarketStore:
        nonlocal shared_store
        if shared_store is None:
            shared_store = MarketStore()
        return shared_store

    # Store-backed analysis reuses this connection. DuckDB permits only one
    # read-write handle per file, so a second open (even read-only) from this
    # process would fail; the catalogue therefore borrows the server's store.
    try:
        from megatool import catalog as _cat

        _cat.set_store_provider(get_store)
    except Exception:  # pragma: no cover - catalogue is optional
        pass

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

        from megatool.live import get_service

        live_status = get_service().status()
        active = live_status.get("active_provider")
        # "Connected" means an owner-configured source is active, not merely that
        # the always-available public fallback exists. The YONEPSE mirror is a
        # fallback and is never counted as a live feed.
        live_connected = active is not None and active != "yonepse"

        last_date = cov.get("last_date")
        return {
            "coverage": cov,
            "recent_ingestions": history,
            "live_feed_connected": live_connected,
            "live": live_status,
            "data_as_of": last_date,
            "note": (
                "no live NEPSE feed is connected for owner-configured providers, so "
                "all figures here come from the stored historical dataset, dated by "
                "`data_as_of`. A public YONEPSE mirror is an hourly fallback, is "
                "labelled with its own observation age at /api/live/market, and is "
                "never presented as live."
            )
            if not live_connected
            else (
                f"live market data is served by the '{active}' provider; freshness "
                "is measured from the source's own timestamps (see /api/live/status). "
                "Historical analysis still reads the stored dataset."
            ),
        }

    @app.get("/api/live/status")
    def live_status() -> dict[str, Any]:
        """Which live providers exist, and why each is available or not.

        Network-free: it reports configuration and the owner gate, never a
        liveness probe. Data freshness is a per-snapshot fact, not a status claim.
        """
        from megatool.live import get_service

        return get_service().status()

    @app.get("/api/live/market")
    def live_market(refresh: bool = False) -> dict[str, Any]:
        """Freshest available market snapshot, with freshness measured.

        ``age_seconds`` is the observation age end-to-end (how old the source's
        own newest timestamp is), not how long the request took. Read-only; the
        snapshot is cached at the provider's publication cadence.
        """
        from megatool.live import get_service

        return get_service().market(force=refresh)

    @app.get("/api/market/dashboard")
    def market_dashboard(
        index_limit: int = Query(300, ge=30, le=6720),
        top: int = Query(8, ge=1, le=30),
    ) -> dict[str, Any]:
        """One call for the redesigned Overview dashboard.

        Assembles the live market snapshot (with measured freshness), real NEPSE
        index history, market breadth and moving-average participation, sector
        performance from the free quote board, gainers/losers/most active, and the
        valuation picture from stored fundamentals. Read-only; cached at each
        provider's publication cadence.
        """
        from megatool.market_dashboard import build_dashboard

        with get_conn() as conn:
            return build_dashboard(
                get_store(), conn, _live_service(), index_limit=index_limit, top=top
            )

    def _live_service() -> Any:
        from megatool.live import get_service

        return get_service()

    @app.get("/api/breadth/history")
    def breadth_history_route(
        start: date | None = None,
        end: date | None = None,
        windows: str = Query(
            "20,50,200",
            description="comma-separated SMA windows, e.g. 20,50,200",
        ),
        high_low_window: int = Query(250, ge=2, le=1000),
    ) -> dict[str, Any]:
        """Market-breadth history from stored daily closes.

        Definitions (universe, advances, %-above-SMA, A/D lines, new
        highs/lows) are echoed in the payload's ``definitions`` so a series
        can never be read with the wrong meaning.
        """
        from megatool.breadth import breadth_history as _breadth_history

        try:
            parsed = tuple(int(w) for w in str(windows).split(",") if str(w).strip())
        except ValueError as exc:
            raise HTTPException(400, f"invalid windows parameter: {exc}") from exc
        if not parsed or any(w < 2 or w > 1000 for w in parsed):
            raise HTTPException(400, "each window must be an integer in [2, 1000]")
        return _breadth_history(
            get_store(),
            start=start,
            end=end,
            sma_windows=parsed,
            high_low_window=high_low_window,
        )

    @app.get("/api/seasonality/{symbol}")
    def seasonality_route(
        symbol: str,
        min_month_bars: int = Query(10, ge=1, le=25),
    ) -> dict[str, Any]:
        """Monthly / weekday / holiday seasonality for one symbol or index.

        Descriptive statistics over the stored range; sample sizes are quoted
        in the payload. The holiday section reports 'unavailable' whenever the
        bundled calendar has no holiday entries — it is never approximated.
        """
        from megatool.seasonality import seasonality_report

        sym = symbol.strip().upper()
        if not valid_symbol(sym) and sym not in {str(n).upper() for n in get_store().index_names()}:
            raise HTTPException(400, "invalid symbol")
        try:
            return seasonality_report(get_store(), sym, min_month_bars=min_month_bars)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/live/quotes")
    def live_quotes(symbols: str | None = None, refresh: bool = False) -> dict[str, Any]:
        """Freshest available per-symbol quotes; freshness is measured, not assumed."""
        from megatool.live import get_service

        wanted = [s for s in (symbols or "").split(",") if s.strip()]
        return get_service().quotes(wanted, force=refresh)

    @app.get("/api/collector/status")
    def collector_status() -> dict[str, Any]:
        """Provenance of the latest ``megatool collector`` run, or not-run yet.

        Read-only: it never triggers a fetch. Every dataset row carries its
        own freshness label and the run-level observation age, so what this
        reports matches what ``megatool collector status`` prints.
        """
        from megatool.collector import latest_report

        report = latest_report()
        if report is None:
            return {
                "run": None,
                "note": "no collector run yet; run `megatool collector snapshot`",
            }
        run = {k: report[k] for k in report if k not in ("detail", "history")}
        return {
            "run": run,
            "datasets": report["datasets"],
            "history": report["history"],
        }

    @app.get("/api/kronos/status")
    def kronos_status() -> dict[str, Any]:
        """Model/tokenizer availability, versions, load state, official ids.

        Diagnostics only - it loads no weights. Forecasts are never sampled if
        the official files are missing; the reply states what is absent.
        """
        from megatool.kronos_service import get_manager

        return {
            "devices": {"mps_hint": "Apple-silicon MPS is selected automatically when present"},
            **get_manager().availability(),
        }

    @app.post("/api/kronos/forecast")
    def kronos_forecast(req: PydanticKronosForecast) -> dict[str, Any]:
        """Run REAL Kronos inference on the stored bars of one symbol.

        Every returned candle is labelled ``is_predicted``: it is a model
        sample, not an observed NEPSE trade, and is stored only in
        ``kronos_experiments`` (never in the candle tables).
        """
        from megatool.kronos_service import (
            DataQualityError,
            ForecastRequest,
            KronosUnavailable,
            get_manager,
        )

        req_obj = ForecastRequest(
            symbol=req.symbol,
            pred_len=req.pred_len,
            context_len=req.context_len,
            variant=req.variant,
            temperature=req.temperature,
            sample_count=req.sample_count,
        )
        manager = get_manager()
        with get_store() as store:
            bars = store.get_bars(req_obj.symbol, limit=req_obj.context_len + 1)
        if bars.empty:
            raise HTTPException(404, f"no stored bars for {req_obj.symbol} in the market history")
        try:
            result = manager.forecast(bars, req_obj, device=req.device)
        except KronosUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except DataQualityError as exc:
            raise HTTPException(422, str(exc)) from exc
        _save_kronos_experiment(
            kind="forecast", req=req_obj, result=result, device=req.device or ""
        )
        return result

    @app.post("/api/kronos/evaluate")
    def kronos_evaluate(req: PydanticKronosEvaluate) -> dict[str, Any]:
        """Chronological walk-forward of Kronos vs naive/drift baselines.

        Windows move strictly forward in time; no window's context reaches
        into its own realized range. Results are research measurements, never
        claims of profitability.
        """
        from megatool.kronos_service import (
            DataQualityError,
            ForecastRequest,
            KronosUnavailable,
            get_manager,
        )

        req_obj = ForecastRequest(
            symbol=req.symbol,
            pred_len=req.pred_len,
            context_len=req.context_len,
            variant=req.variant,
        )
        manager = get_manager()
        with get_store() as store:
            bars = store.get_bars(
                req_obj.symbol, limit=req_obj.context_len + req_obj.pred_len * int(req.windows) + 2
            )
        if bars.empty:
            raise HTTPException(404, f"no stored bars for {req_obj.symbol} in the market history")
        try:
            result = manager.evaluate(bars, req_obj, windows=int(req.windows), device=req.device)
        except KronosUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except DataQualityError as exc:
            raise HTTPException(422, str(exc)) from exc
        _save_kronos_experiment(
            kind="evaluate", req=req_obj, result=result, device=req.device or ""
        )
        return result

    @app.get("/api/kronos/experiments")
    def kronos_experiments(symbol: str | None = None, kind: str | None = None) -> dict[str, Any]:
        items = list_kronos_experiments(kind=kind, symbol=symbol)
        return {"experiments": items, "count": len(items)}

    @app.delete("/api/kronos/experiments/{exp_id}")
    def kronos_experiment_delete(exp_id: int) -> dict[str, Any]:
        from megatool.db import get_conn

        with get_conn() as conn:
            deleted = conn.execute(
                "DELETE FROM kronos_experiments WHERE id = ?", (exp_id,)
            ).rowcount
        if not deleted:
            raise HTTPException(404, f"no kronos experiment with id {exp_id}")
        return {"deleted": exp_id}

    @app.post("/api/kronos/unload")
    def kronos_unload() -> dict[str, Any]:
        """Release the resident model from memory (weights stay on disk)."""
        from megatool.kronos_service import get_manager

        return get_manager().unload()

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
        # YONEPSE is a snapshot source reached on demand (CLI/ingest), not a
        # library adapter, so it is described statically here without a network
        # probe. ``available`` is left null on purpose: asserting liveness from
        # an API call would be a claim the endpoint cannot actually make.
        out.append(
            {
                "label": "YONEPSE (snapshot JSON)",
                "kind": "snapshot",
                "access_method": "https-get (snapshot files)",
                "requires_auth": False,
                "available": None,
                "note": "read-only GitHub Pages snapshots; reference data, "
                "financials, notices and a near-live quote board (market/live.json)",
            }
        )
        # NEPSE official live API: reached only through the gated client in
        # ``nepse_official_live``. Described statically (no probe): the flag
        # reflects the owner authorization gate, not a measured liveness. The
        # ``health`` block is the *last recorded* certificate/circuit check —
        # it is read from a cache file and is never a continuous monitor.
        from megatool import source_health

        out.append(
            {
                "label": "NEPSE official API (live, gated)",
                "kind": "live",
                "access_method": "https-get (authorization-gated)",
                # Authorization is required but is not a credential: no token is
                # stored or sent from this process unless the owner enables it.
                "requires_auth": True,
                # `available: None` means "not probed" — the gated client is
                # never called just to measure liveness. This is not "down".
                "available": None,
                "authorized": os.environ.get("MEGATOOL_NEPSE_API_AUTHORIZED") == "1",
                "health": source_health.source_health_view("nepse-official"),
                "note": "undocumented exchange API; automated access is an owner "
                "authorization decision (set MEGATOOL_NEPSE_API_AUTHORIZED=1). "
                "go-nepse speaks this same surface and is integrated through the "
                "Go bridge (see the go-nepse entry below and "
                "docs/GO_NEPSE_INVESTIGATION.md).",
            }
        )
        # go-nepse: the *actual* Go library, reached through the JSON bridge in
        # tools/gonepse-bridge (megatool/datasources/gonepse.py). Described from
        # its own network-free diagnostics. ``available`` is whether a live call
        # is currently possible, which requires both a built bridge and the open
        # owner gate — never a claim that NEPSE answered.
        from megatool.datasources.gonepse import GoNepseAdapter

        gonepse = GoNepseAdapter()
        gst = gonepse.status()
        out.append(
            {
                "label": gonepse.config.label,
                "kind": "live (go library)",
                "access_method": gonepse.config.access_method,
                "requires_auth": True,
                "available": gst["live"] == "ready",
                "authorized": gst["authorized"],
                "bridge_present": gst["bridge_present"],
                "tls_verification": gst["tls_verification"],
                "live_connection_tested": gst["live_connection_tested"],
                "blocker": gst["static_blocker"],
                "note": "wraps github.com/voidarchive/go-nepse via "
                "tools/gonepse-bridge; TLS verification stays on and live calls "
                "stay behind the owner gate; blocked by NEPSE anti-bot token "
                "obfuscation and the closed owner gate (not tested live).",
            }
        )
        return {"sources": out}

    @app.get("/api/gonepse/status")
    def gonepse_status() -> dict[str, Any]:
        """Diagnostics for the go-nepse (actual Go library) provider."""
        from megatool.datasources.gonepse import GoNepseAdapter
        return GoNepseAdapter().status()

    @app.get("/api/market-intelligence/health")
    def market_intelligence_health() -> dict[str, Any]:
        """Health of the integrated market-intelligence source registry."""
        from megatool.market_intelligence.database.db import connect, run_migrations
        from pathlib import Path
        db_path = _mi_db_path()
        try:
            conn = connect(db_path, shared_thread=True)
            migrations_dir = Path(__file__).resolve().parent / "market_intelligence" / "data" / "migrations"
            # fall back to the copied migrations dir
            if not migrations_dir.exists():
                migrations_dir = Path(__file__).resolve().parents[1] / "Kimi_Agent_Shared attachments k3" / "nepse-market-intelligence" / "migrations"
            run_migrations(conn, migrations_dir)
            counts = {}
            for t in ("sources", "articles", "events", "social_accounts"):
                try:
                    counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except Exception:
                    counts[t] = 0
            conn.close()
            return {"status": "ok", "db": str(db_path), "counts": counts}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @app.get("/api/market-intelligence/sources")
    def market_intelligence_sources(status: str | None = None, group: str | None = None,
                                   limit: int = 50, offset: int = 0) -> dict[str, Any]:
        from megatool.market_intelligence.database.db import connect
        from megatool.market_intelligence.database.db import run_migrations
        from pathlib import Path
        db_path = _mi_db_path()
        conn = connect(db_path, shared_thread=True)
        migrations_dir = Path(__file__).resolve().parent / "market_intelligence" / "data" / "migrations"
        if not migrations_dir.exists():
            migrations_dir = Path(__file__).resolve().parents[1] / "Kimi_Agent_Shared attachments k3" / "nepse-market-intelligence" / "migrations"
        run_migrations(conn, migrations_dir)
        sql = "SELECT source_id, source_name, primary_domain, source_group, automated_access_status, rss_url, last_successful_fetch_at FROM sources WHERE 1=1"
        params: list = []
        if status:
            sql += " AND automated_access_status = ?"; params.append(status)
        if group:
            sql += " AND source_group = ?"; params.append(group)
        sql += " ORDER BY source_group, source_name"
        limit = min(max(1, limit), 200)
        offset = max(0, offset)
        cur = conn.execute(f"{sql} LIMIT ? OFFSET ?", (*params, limit, offset))
        items = [dict(r) for r in cur.fetchall()]
        total = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        conn.close()
        return {"items": items, "total": total}

    @app.get("/api/market-intelligence/source-health")
    def market_intelligence_source_health() -> dict[str, Any]:
        from megatool.market_intelligence.database.db import connect, run_migrations
        from pathlib import Path
        db_path = _mi_db_path()
        conn = connect(db_path, shared_thread=True)
        migrations_dir = Path(__file__).resolve().parent / "market_intelligence" / "data" / "migrations"
        if not migrations_dir.exists():
            migrations_dir = Path(__file__).resolve().parents[1] / "Kimi_Agent_Shared attachments k3" / "nepse-market-intelligence" / "migrations"
        run_migrations(conn, migrations_dir)
        try:
            rows = [dict(r) for r in conn.execute("SELECT * FROM source_health ORDER BY checked_at DESC LIMIT 50").fetchall()]
        except Exception:
            rows = []
        conn.close()
        return {"items": rows}

    @app.post("/api/market-intelligence/collect")
    def market_intelligence_collect(limit_sources: int = 5) -> dict[str, Any]:
        """Run RSS collection on up to limit_sources verified sources (bounded)."""
        from megatool.market_intelligence.database.db import connect, run_migrations
        from megatool.market_intelligence.ingestion.rss.collector import RSSAdapter
        from megatool.market_intelligence.ingestion.common.http import HttpFetcher
        from megatool.market_intelligence.ingestion.pipeline import Pipeline
        from megatool.market_intelligence.event_detection.classifier import EventClassifier
        from megatool.market_intelligence.sentiment.lexicon import LexiconSentimentModel
        from pathlib import Path
        import json as _json
        db_path = _mi_db_path()
        conn = connect(db_path, shared_thread=True)
        migrations_dir = Path(__file__).resolve().parent / "market_intelligence" / "data" / "migrations"
        if not migrations_dir.exists():
            migrations_dir = Path(__file__).resolve().parents[1] / "Kimi_Agent_Shared attachments k3" / "nepse-market-intelligence" / "migrations"
        run_migrations(conn, migrations_dir)
        sources = [dict(r) for r in conn.execute(
            "SELECT * FROM sources WHERE automated_access_status='VERIFIED' AND rss_url IS NOT NULL LIMIT ?",
            (max(1, min(limit_sources, 20)),)).fetchall()]
        fetcher = HttpFetcher(timeout_s=15, max_bytes=2000000, max_retries=1,
                             collection_enabled=True, dry_run=False)
        pipe = Pipeline(conn, entity_registry=None, sentiment_model=LexiconSentimentModel(),
                        event_classifier=EventClassifier(), near_threshold=0.8)
        total_stored = 0
        results = []
        for src in sources:
            adapter = RSSAdapter(source=src, fetcher=fetcher)
            report = adapter.collect(max_items=10)
            stored = 0
            if report.ok and report.items:
                for item in report.items:
                    outcome = pipe.process(src["source_id"], item, "rss")
                    if outcome.get("status") == "stored":
                        stored += 1
                conn.commit()
            total_stored += stored
            results.append({"source": src["source_name"], "ok": report.ok,
                            "fetched": len(report.items), "stored": stored,
                            "error": report.error})
        conn.close()
        return {"status": "ok", "sources_attempted": len(sources),
                "total_stored": total_stored, "results": results}

    @app.post("/api/market-intelligence/import-csv")
    def market_intelligence_import_csv(body: dict[str, Any]) -> dict[str, Any]:
        """Import sources from a CSV/JSON list provided by the user.
        Body: {"sources": [ {source_id, source_name, primary_domain, ...}, ... ]}
        Validates, deduplicates, and imports. Returns counts."""
        from megatool.market_intelligence.database.db import connect, run_migrations, upsert_source
        from pathlib import Path
        db_path = _mi_db_path()
        conn = connect(db_path, shared_thread=True)
        migrations_dir = Path(__file__).resolve().parent / "market_intelligence" / "data" / "migrations"
        if not migrations_dir.exists():
            migrations_dir = Path(__file__).resolve().parents[1] / "Kimi_Agent_Shared attachments k3" / "nepse-market-intelligence" / "migrations"
        run_migrations(conn, migrations_dir)
        sources = body.get("sources", [])
        if not isinstance(sources, list):
            conn.close()
            return {"status": "error", "error": "sources must be a list"}
        imported = 0
        skipped = 0
        errors = []
        for src in sources:
            if not isinstance(src, dict):
                skipped += 1
                continue
            if not src.get("source_id") or not src.get("source_name") or not src.get("primary_domain"):
                skipped += 1
                errors.append(f"missing required fields: {src.get('source_name', '?')}")
                continue
            # check duplicate
            exists = conn.execute("SELECT 1 FROM sources WHERE source_id=?", (src["source_id"],)).fetchone()
            if exists:
                skipped += 1
                continue
            try:
                # set defaults for missing fields
                rec = {
                    "source_id": src["source_id"],
                    "source_name": src["source_name"],
                    "primary_domain": src["primary_domain"],
                    "canonical_homepage": src.get("canonical_homepage"),
                    "source_group": src.get("source_group", "C"),
                    "source_type": src.get("source_type", "news_portal"),
                    "country_or_region": src.get("country_or_region", "Nepal"),
                    "primary_language": src.get("primary_language", "ne"),
                    "automated_access_status": src.get("automated_access_status", "REVIEW_REQUIRED"),
                    "rss_url": src.get("rss_url"),
                    "rss_available": src.get("rss_available"),
                }
                upsert_source(conn, rec)
                imported += 1
            except Exception as e:
                skipped += 1
                errors.append(str(e))
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        conn.close()
        return {"status": "ok", "imported": imported, "skipped": skipped, "total": total, "errors": errors[:10]}

    @app.post("/api/market-intelligence/import-sources")
    def market_intelligence_import_sources() -> dict[str, Any]:
        """Import the bundled K3 source registry (100 sources) into the MI DB."""
        from megatool.market_intelligence.database.db import connect, run_migrations, upsert_source
        from pathlib import Path
        import json as _json
        db_path = _mi_db_path()
        conn = connect(db_path, shared_thread=True)
        migrations_dir = Path(__file__).resolve().parent / "market_intelligence" / "data" / "migrations"
        if not migrations_dir.exists():
            migrations_dir = Path(__file__).resolve().parents[1] / "Kimi_Agent_Shared attachments k3" / "nepse-market-intelligence" / "migrations"
        run_migrations(conn, migrations_dir)
        reg_path = Path(__file__).resolve().parents[1] / "Kimi_Agent_Shared attachments k3" / "nepse-market-intelligence" / "data" / "registry" / "source_registry.json"
        if not reg_path.exists():
            conn.close()
            return {"status": "error", "error": "source registry file not found"}
        reg = _json.loads(reg_path.read_text(encoding="utf-8"))
        n = 0
        for s in reg.get("sources", []):
            try:
                upsert_source(conn, s)
                n += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        return {"status": "ok", "imported": n, "total_in_registry": len(reg.get("sources", []))}

    @app.get("/api/quotes")
    def quotes(max_age_minutes: int | None = Query(None, ge=0)) -> dict[str, Any]:
        """Latest stored quotes with honest freshness.

        Freshness is measured from each quote's own source timestamp (Nepal
        time, UTC+05:45) — never from the request clock — so a source that has
        stopped updating shows up as stale instead of looking current.
        """
        store = get_store()
        freshness = store.quote_freshness()
        rows = store.latest_quotes()
        if max_age_minutes is not None:
            rows = [
                r
                for r in rows
                if r["age_minutes"] is not None and r["age_minutes"] <= max_age_minutes
            ]
        return {
            "count": len(rows),
            "freshness": freshness,
            "quotes": rows,
        }

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
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
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
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
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

    @app.get("/api/bars/{symbol}/structure")
    def structure(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        left: int = Query(DEFAULT_LEFT, ge=1, le=200),
        right: int = Query(DEFAULT_RIGHT, ge=1, le=200),
        min_prominence: float = Query(0.0, ge=0.0, le=1.0),
    ) -> dict[str, Any]:
        """Swing points and market structure for one symbol.

        This is a *detection* endpoint, not a signal: it reports candidate
        turning points under the documented rules in ``megatool.ta.swings``.
        Every swing carries ``confirmed_index`` — the first bar at which the
        swing was knowable — because a pivot is only a pivot once ``right``
        further bars have failed to exceed it. Anything earlier would be
        look-ahead.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        store = get_store()
        df = store.get_bars(symbol.upper(), start=start, end=end, limit=limit)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol.upper()}")

        highs = df["high"].to_numpy(float)
        lows = df["low"].to_numpy(float)
        closes = df["close"].to_numpy(float)

        try:
            swings = find_swings(highs, lows, left=left, right=right, min_prominence=min_prominence)
        except SwingError as exc:
            raise HTTPException(400, str(exc)) from exc

        dates = [str(d.date()) for d in df["trading_date"]]
        structure_info = classify_structure(swings)
        breaks = find_breaks(swings, closes)
        equal_hl = detect_equal_highs_lows(swings)
        fvgs = detect_fvgs(highs.tolist(), lows.tolist())

        def stamp(row: dict[str, Any], idx_key: str = "index") -> dict[str, Any]:
            i = row[idx_key]
            return {**row, "date": dates[i] if 0 <= i < len(dates) else None}

        return {
            "symbol": symbol.upper(),
            "method": "fractal pivot (unique extreme over left/right window)",
            "params": {"left": left, "right": right, "min_prominence": min_prominence},
            "counts": {
                "bars": int(len(df)),
                "swings": len(swings),
                "swing_highs": structure_info["swing_highs"],
                "swing_lows": structure_info["swing_lows"],
            },
            "first_date": dates[0],
            "last_date": dates[-1],
            "swings": [
                {
                    **stamp(s.to_dict()),
                    "confirmed_date": (
                        dates[s.confirmed_index] if 0 <= s.confirmed_index < len(dates) else None
                    ),
                }
                for s in swings
            ],
            "labels": [stamp(row) for row in structure_info["labels"]],
            "trend": structure_info["trend"],
            "breaks": [stamp(row) for row in breaks],
            "equal_highs_lows": equal_hl,
            "fvgs": fvgs,
            "interpretation": "detected",
            "caveats": [
                "Detected turning points under fixed geometric rules, not validated "
                "patterns and not a prediction.",
                "A swing is knowable only at `confirmed_index`, `right` bars after the "
                "pivot bar; do not act on it before then.",
                "Swing classification depends on `left`, `right` and `min_prominence`; "
                "different settings give different, defensible structures.",
                "Prices are unadjusted for bonus/split issues, so a structural break "
                "may reflect a corporate action rather than trading behaviour.",
            ],
        }

    @app.get("/api/bars/{symbol}/swing-workbench")
    def swing_workbench_route(
        symbol: str,
        limit: int = Query(400, ge=60, le=2000),
        as_of: date | None = Query(  # noqa: B008 - FastAPI injection marker; never a shared runtime default.
            None, description="analyse the series only up to this date (inclusive)"
        ),
        left: int = Query(DEFAULT_LEFT, ge=1, le=200),
        right: int = Query(DEFAULT_RIGHT, ge=1, le=200),
        min_prominence: float = Query(0.0, ge=0.0, le=1.0),
        account_size: float = Query(100_000.0, gt=0),
        risk_fraction: float = Query(0.01, gt=0, le=1),
    ) -> dict[str, Any]:
        """Mechanical swing-workbench context for one symbol (Part 17).

        Composes the same swing primitives as ``/structure`` and the indicator
        engine into one payload: nearest confirmed levels, measured-move
        arithmetic, a mechanical checklist, and position-size arithmetic for
        the supplied account. Nothing here is advice; every block records its
        definitions, and missing evidence stays ``None`` with a reason.
        """
        from megatool.swing_workbench import swing_workbench as _workbench

        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        store = get_store()
        df = store.get_bars(symbol.upper(), end=as_of, limit=limit)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol.upper()}")
        try:
            out = _workbench(
                df,
                left=left,
                right=right,
                min_prominence=min_prominence,
                account_size=account_size,
                risk_fraction=risk_fraction,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        out["symbol"] = symbol.upper()
        out["as_of"] = str(df["trading_date"].max().date())
        return out

    @app.get("/api/bars/{symbol}/fibonacci")
    def fibonacci(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        left: int = Query(DEFAULT_LEFT, ge=1, le=200),
        right: int = Query(DEFAULT_RIGHT, ge=1, le=200),
        min_prominence: float = Query(0.0, ge=0.0, le=1.0),
        anchor: str = Query(
            "auto",
            pattern="^(auto|last_leg)$",
            help="auto = most recent confirmed swing high/low pair; "
            "last_leg = the same pair (explicit alias).",
        ),
        retracements: str | None = Query(
            None, help="Optional JSON array of ratios, e.g. [0.382,0.618]."
        ),
        extensions: str | None = Query(None, help="Optional JSON array of ratios."),
        include_unconfirmed: bool = Query(
            False,
            help="Allow anchors from a swing not yet confirmed. Off by default "
            "because an unconfirmed pivot is not knowable history.",
        ),
    ) -> dict[str, Any]:
        """Fibonacci retracement and extension levels for one symbol.

        Anchors are swing points from ``megatool.ta.swings``, so this endpoint
        and the structure endpoint always agree on what a turning point is.

        The output is **CALCULATED** — arithmetic on two chosen anchors. It is
        not a prediction and carries no claim that price will respect a level.
        The 50% row is reported as ``family: "convention"`` because it is not
        a Fibonacci ratio.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        store = get_store()
        df = store.get_bars(symbol.upper(), start=start, end=end, limit=limit)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol.upper()}")
        dates = [str(d.date()) for d in df["trading_date"]]

        def parse_ratios(raw: str | None, name: str) -> list[float] | None:
            if raw is None:
                return None
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise HTTPException(400, f"`{name}` is not valid JSON: {exc}") from exc
            if not isinstance(parsed, list):
                raise HTTPException(400, f"`{name}` must be a JSON array of ratios")
            # Reject bad ratios here (client error → 400) so a malformed level
            # set never reaches the calculation and is never mistaken for a
            # data-availability problem (which is a 200 `available:false`).
            ratios: list[float] = []
            for item in parsed:
                if isinstance(item, bool) or not isinstance(item, (int, float)):
                    raise HTTPException(400, f"`{name}` must contain only numbers, got {item!r}")
                value = float(item)
                if value != value or value in (float("inf"), float("-inf")) or value < 0:
                    raise HTTPException(
                        400, f"`{name}` ratios must be finite and non-negative, got {item!r}"
                    )
                ratios.append(value)
            return ratios

        def unavailable(reason: str) -> dict[str, Any]:
            """200 contract: anchors were not resolvable, so nothing is fabricated.

            Mirrors ``relative-strength``/``patterns`` — a genuine data condition
            (too few swings, or an anchor pair that cannot form a study) is an
            answer with a reason, not an HTTP error.
            """
            return {
                "symbol": symbol.upper(),
                "classification": "calculated",
                "method": "fibonacci from swing anchors",
                "method_version": "1.0",
                "available": False,
                "unavailable_reason": reason,
                "anchor_policy": (
                    "most recent confirmed swing high and low (last completed leg)"
                    if not include_unconfirmed
                    else "most recent swing high and low, allowing unconfirmed anchors"
                ),
                "anchor_mode": anchor,
                "params": {
                    "left": left,
                    "right": right,
                    "min_prominence": min_prominence,
                    "include_unconfirmed": include_unconfirmed,
                    "retracements": list(ret_ratios)
                    if ret_ratios is not None
                    else list(DEFAULT_RETRACEMENTS),
                    "extensions": list(ext_ratios)
                    if ext_ratios is not None
                    else list(DEFAULT_EXTENSIONS),
                },
                "first_date": dates[0],
                "last_date": dates[-1],
                "bars": int(len(df)),
                "anchors": None,
                "direction": None,
                "formula": {
                    "retracement": "end - range * r",
                    "extension": "end + range * r",
                    "range": "end - start (signed)",
                },
                "retracements": [],
                "extensions": [],
                "caveats": [
                    "CALCULATED: arithmetic on two chosen swing anchors, not a "
                    "prediction and not evidence that any level will hold.",
                    "No levels are shown because the requested window did not "
                    "produce a usable anchor pair.",
                ],
            }

        ret_ratios = parse_ratios(retracements, "retracements")
        ext_ratios = parse_ratios(extensions, "extensions")

        highs = df["high"].to_numpy(float)
        lows = df["low"].to_numpy(float)

        try:
            swings = find_swings(highs, lows, left=left, right=right, min_prominence=min_prominence)
        except SwingError as exc:
            raise HTTPException(400, str(exc)) from exc

        usable = [s for s in swings if include_unconfirmed or s.confirmed]
        highs_only = [s for s in usable if s.kind == "high"]
        lows_only = [s for s in usable if s.kind == "low"]
        if not highs_only or not lows_only:
            return unavailable(
                "not enough confirmed swings of both kinds to anchor a Fibonacci "
                "study; widen the window, loosen `left`/`right`, or set "
                "`include_unconfirmed=true` (which uses not-yet-confirmed anchors)"
            )

        # Anchor on the most recent confirmed high and low: the last completed
        # leg. Ties break to the later bar so the anchors stay chronological.
        hi = max(highs_only, key=lambda s: (s.index, s.price))
        lo = max(lows_only, key=lambda s: (s.index, -s.price))
        start_sw, end_sw = (lo, hi) if lo.index <= hi.index else (hi, lo)

        try:
            table = levels_for(
                start_sw.price,
                end_sw.price,
                retracements=ret_ratios,
                extensions=ext_ratios,
                start_index=start_sw.index,
                end_index=end_sw.index,
            )
        except FibonacciError as exc:
            # A bad *ratio* is already rejected as a 400 above; reaching here
            # means the two selected swings cannot form a study (equal prices,
            # or a non-positive anchor) — a data condition, reported honestly.
            return unavailable(str(exc))

        payload = table.to_dict()
        payload["anchors"]["start_date"] = dates[start_sw.index]
        payload["anchors"]["end_date"] = dates[end_sw.index]
        payload["anchors"]["start_kind"] = start_sw.kind
        payload["anchors"]["end_kind"] = end_sw.kind
        payload["anchors"].pop("start_index", None)
        payload["anchors"].pop("end_index", None)
        payload["anchors"]["start_index"] = start_sw.index
        payload["anchors"]["end_index"] = end_sw.index

        return {
            "symbol": symbol.upper(),
            "classification": "calculated",
            "method": "fibonacci from swing anchors",
            "method_version": "1.0",
            "available": True,
            "anchor_policy": (
                "most recent confirmed swing high and low (last completed leg)"
                if not include_unconfirmed
                else "most recent swing high and low, allowing unconfirmed anchors"
            ),
            "anchor_mode": anchor,
            "params": {
                "left": left,
                "right": right,
                "min_prominence": min_prominence,
                "include_unconfirmed": include_unconfirmed,
                "retracements": list(ret_ratios)
                if ret_ratios is not None
                else list(DEFAULT_RETRACEMENTS),
                "extensions": list(ext_ratios)
                if ext_ratios is not None
                else list(DEFAULT_EXTENSIONS),
            },
            "first_date": dates[0],
            "last_date": dates[-1],
            "bars": int(len(df)),
            **payload,
            "caveats": [
                "CALCULATED: arithmetic on two chosen swing anchors, not a "
                "prediction and not evidence that any level will hold.",
                "Anchors are chosen by the stated policy; a different pair of "
                "swings gives different, equally defensible levels.",
                "The 50% retracement is a market convention, not a Fibonacci ratio.",
                "Prices are unadjusted for bonus/split issues, so levels may "
                "reflect a corporate action rather than trading behaviour.",
            ],
        }

    @app.get("/api/bars/{symbol}/levels")
    def levels(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        left: int = Query(DEFAULT_LEFT, ge=1, le=200),
        right: int = Query(DEFAULT_RIGHT, ge=1, le=200),
        min_prominence: float = Query(0.0, ge=0.0, le=1.0),
        tolerance_frac: float = Query(0.01, gt=0.0, le=0.5),
        tolerance_mode: str = Query("price", pattern="^(price|atr)$"),
        atr_multiple: float = Query(1.0, gt=0.0, le=10.0),
        min_touches: int = Query(
            2,
            ge=1,
            le=50,
            help="Distinct swings a zone needs to appear in the primary list. "
            "Defaults to 2 so a lone pivot cannot masquerade as a tested "
            "level; excluded zones are still returned.",
        ),
        use_atr: bool = Query(False, help="Compute ATR(14) to scale the tolerance."),
    ) -> dict[str, Any]:
        """Support and resistance zones clustered from swing points.

        Zones are **DETECTED** candidate price bands under the stated
        tolerance — not order-book liquidity, and not a guarantee any band
        holds. Output is sorted by centre price so the chart can place it
        deterministically.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        store = get_store()
        df = store.get_bars(symbol.upper(), start=start, end=end, limit=limit)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol.upper()}")

        highs = df["high"].to_numpy(float)
        lows = df["low"].to_numpy(float)
        closes = df["close"].to_numpy(float)

        try:
            swings = find_swings(highs, lows, left=left, right=right, min_prominence=min_prominence)
        except SwingError as exc:
            raise HTTPException(400, str(exc)) from exc

        atr_series: list[float] = []
        if use_atr and tolerance_mode == "atr":
            atr_series = [
                None if (v is None or np.isnan(v)) else float(v)
                for v in ta_compute("atr", {"high": highs, "low": lows, "close": closes}).values[
                    "atr"
                ]
            ]

        try:
            zones = build_zones(
                swings,
                close=closes,
                tolerance_frac=tolerance_frac,
                tolerance_mode=tolerance_mode,
                atr_multiple=atr_multiple,
                atr=atr_series,
                min_touches=min_touches,
            )
        except ZonesError as exc:
            raise HTTPException(400, str(exc)) from exc

        dates = [str(d.date()) for d in df["trading_date"]]

        def stamp(row: dict[str, Any]) -> dict[str, Any]:
            # Zones span a band, so they carry the first and last swing date
            # rather than a single index.
            idxs = row.get("swing_indices", [])
            return {
                **row,
                "first_date": dates[min(idxs)] if idxs else None,
                "last_date": dates[max(idxs)] if idxs else None,
            }

        return {
            "symbol": symbol.upper(),
            "classification": "detected",
            "first_date": dates[0],
            "last_date": dates[-1],
            "bars": int(len(df)),
            **{k: v for k, v in zones.items() if k != "zones"},
            "zones": [stamp(row) for row in zones["zones"]],
            "excluded": [stamp(row) for row in zones["excluded"]],
            "swing_counts": {"total": len(swings)},
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
            store,
            node,
            symbols=req.symbols,
            as_of=req.as_of,
            min_bars=req.min_bars,
            exclude_delisted=req.exclude_delisted,
            instrument_types=req.instrument_types,
        )
        passed = [r for r in results if r.passed]
        ineligible = [r for r in results if not r.eligible]
        body: dict[str, Any] = {
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
        if req.exclude_delisted or req.instrument_types is not None:
            body["eligibility_filter"] = {
                "exclude_delisted": req.exclude_delisted,
                "instrument_types": req.instrument_types,
                "policy": "unknown metadata is ineligible with an explicit note; never guessed",
            }
        return body

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
        requested = len(wanted)
        filters_active = req.exclude_delisted or req.instrument_types is not None
        excluded_meta: list[dict[str, str]] = []
        if filters_active:
            # One metadata query for the whole request; the same pure
            # decision function the scanner uses, so both stay consistent.
            # The verified corporate-action registry fills the gap left by an
            # empty security_master, so a merged symbol with no stored row is
            # still excluded from the active universe. Stored metadata wins.
            meta = corporate_actions.merge_into_meta(store.securities_meta(wanted), wanted)
            kept: list[str] = []
            for s in wanted:
                allowed, reason = eligibility_from_meta(
                    meta.get(str(s).upper()),
                    exclude_delisted=req.exclude_delisted,
                    instrument_types=req.instrument_types,
                )
                if allowed:
                    kept.append(s)
                else:
                    excluded_meta.append({"symbol": str(s).upper(), "reason": reason})
            wanted = kept
            if not wanted:
                raise HTTPException(
                    400,
                    "every requested symbol was excluded by the eligibility "
                    "filter; rerun without exclude_delisted/instrument_types "
                    "to rank the full universe",
                )
        frames: dict[str, pd.DataFrame] = {}
        for symbol in wanted:
            df = store.get_bars(symbol.upper(), end=req.as_of)
            if not df.empty:
                frames[symbol.upper()] = df

        if not frames:
            raise HTTPException(404, "no stored history for the requested symbols")

        # Sector classifications feed the ranking's data-driven sector factor
        # (availability is computed from live coverage, never assumed).
        meta = store.securities_meta(list(frames))
        # Only ORDINARY shares participate. Verified against the real
        # compilations: every mutual fund (63 of them) and every debenture
        # (89 of them) carries its issuer's business sector, so an unfiltered
        # map ranks a bank's bond and a bank's mutual fund *against* that
        # bank's ordinary shares. A sector percentile describes a peer group,
        # not an instrument list, so non-ordinary instruments are excluded here.
        sectors = sector_consensus.ordinary_only_sector_map(meta)
        excluded_instrument_sectored = sector_consensus.non_ordinary_with_sector(meta)

        # The official NEPSE composite index feeds the data-driven
        # relative_strength factor. Only that exact series is used; when it is
        # absent the factor is declared unavailable rather than substituted.
        benchmark = store.index_closes(NEPSE_COMPOSITE_INDEX)
        if benchmark is None or benchmark.empty:
            benchmark = None

        try:
            result = rank_universe(frames, config, sectors=sectors, benchmark=benchmark)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        payload = result.to_dict()
        payload["requested"] = requested
        payload["truncated_to"] = req.as_of.isoformat() if req.as_of else None
        if filters_active:
            payload["eligibility_filter"] = {
                "exclude_delisted": req.exclude_delisted,
                "instrument_types": req.instrument_types,
                "excluded": excluded_meta,
                "policy": "unknown metadata is excluded with an explicit reason; never guessed",
            }
        payload["unavailable"] = result.unavailable
        payload["sector_factor_scope"] = {
            "symbols_with_sector": sum(1 for m in meta.values() if m.get("sector")),
            "symbols_used_for_sector_percentile": len(sectors),
            "non_ordinary_excluded": excluded_instrument_sectored,
            "policy": (
                "only ordinary shares are ranked within a sector; mutual funds, "
                "debentures, bonds, promoter and preference shares are classified "
                "by instrument and never given an ordinary company sector"
            ),
        }
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

    # Registered before /{symbol}: a single segment would otherwise be
    # captured as a symbol by the parameterised route below.
    @app.get("/api/fundamentals/compare")
    def fundamentals_compare(
        symbols: str = Query(..., min_length=1, description="comma-separated symbols, max 10"),
    ) -> dict[str, Any]:
        """Side-by-side derived ratios for several symbols (deterministic)."""
        requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if not requested:
            raise HTTPException(400, "no symbols given")
        if len(requested) > 10:
            raise HTTPException(400, "at most 10 symbols per comparison")
        store = get_store()
        with get_conn() as conn:
            reports = [fundamentals_ratios(conn, store, s) for s in requested]
        return {
            "symbols": reports,
            "note": (
                "Each entry is the same deterministic ratio report as "
                "/api/fundamentals/{symbol}/ratios; value=null always carries "
                "its reason."
            ),
        }

    @app.get("/api/fundamentals/eps-rankings")
    def fundamentals_eps_rankings(
        period: str = Query("latest", description="Period label filter (e.g. 'Third Quarter 2025-2026') or 'latest' for most recent per symbol"),
        sector: str | None = Query(None, description="Filter by sector (requires sector data)"),
        sort: str = Query("desc", description="asc or desc"),
        limit: int = Query(50, ge=1, le=500),
    ) -> dict[str, Any]:
        """EPS rankings across symbols for a given reporting period.

        Uses stored fundamentals only. Period-aware: 'latest' picks the most
        recent EPS record per symbol. Does not fabricate missing values.
        """
        from megatool.fundamentals import query_symbol
        store = get_store()
        with get_conn() as conn:
            if period == "latest":
                # most recent EPS per symbol
                rows = conn.execute(
                    """
                    SELECT f.symbol, f.value AS eps, f.period_end, f.period_label,
                           f.verification, f.source, f.retrieved_at
                    FROM fundamentals f
                    WHERE f.field = 'eps'
                      AND f.period_end = (
                        SELECT MAX(f2.period_end) FROM fundamentals f2
                        WHERE f2.symbol = f.symbol AND f2.field = 'eps'
                      )
                    ORDER BY f.value DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT symbol, value AS eps, period_end, period_label,
                           verification, source, retrieved_at
                    FROM fundamentals
                    WHERE field = 'eps' AND period_label = ?
                    ORDER BY value DESC
                    """,
                    (period,),
                ).fetchall()
            items = []
            for r in rows:
                items.append({
                    "symbol": r["symbol"],
                    "eps": r["eps"],
                    "period_end": r["period_end"],
                    "period_label": r["period_label"],
                    "verification": r["verification"],
                    "source": r["source"],
                    "retrieved_at": r["retrieved_at"],
                })
            if sort == "asc":
                items.sort(key=lambda x: (x["eps"] is None, x["eps"] if x["eps"] is not None else 0))
            else:
                items.sort(key=lambda x: (x["eps"] is None, -(x["eps"] if x["eps"] is not None else 0)))
            # distinct period labels for the selector
            periods = [r[0] for r in conn.execute(
                "SELECT DISTINCT period_label FROM fundamentals WHERE field='eps' ORDER BY period_end DESC LIMIT 20"
            ).fetchall()]
            return {
                "items": items[:limit],
                "total": len(items),
                "periods": periods,
                "note": "EPS values from stored fundamentals. Missing/invalid values are excluded, not zero-filled. Period and source shown per row.",
            }
    def fundamentals_compare(
        symbols: str = Query(..., min_length=1, description="comma-separated symbols, max 10"),
    ) -> dict[str, Any]:
        """Side-by-side derived ratios for several symbols (deterministic)."""
        requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if not requested:
            raise HTTPException(400, "no symbols given")
        if len(requested) > 10:
            raise HTTPException(400, "at most 10 symbols per comparison")
        store = get_store()
        with get_conn() as conn:
            reports = [fundamentals_ratios(conn, store, s) for s in requested]
        return {
            "symbols": reports,
            "note": (
                "Each entry is the same deterministic ratio report as "
                "/api/fundamentals/{symbol}/ratios; value=null always carries "
                "its reason."
            ),
        }

    @app.get("/api/fundamentals/{symbol}/ttm-eps")
    def fundamentals_ttm_eps(symbol: str) -> dict[str, Any]:
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        with get_conn() as conn:
            return compute_ttm_eps(conn, symbol)

    @app.get("/api/fundamentals/{symbol}/eps-growth")
    def fundamentals_eps_growth(symbol: str) -> dict[str, Any]:
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        with get_conn() as conn:
            return compute_eps_growth(conn, symbol)

    @app.get("/api/fundamentals/{symbol}/historical-pe")
    def fundamentals_historical_pe(
        symbol: str,
        price: float = Query(..., description="Historical price"),
        price_date: str = Query(..., description="Price date (YYYY-MM-DD)"),
    ) -> dict[str, Any]:
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        try:
            pd = date.fromisoformat(price_date)
        except ValueError:
            raise HTTPException(400, "invalid price_date format (expected YYYY-MM-DD)")
        with get_conn() as conn:
            return historical_pe(conn, symbol, price, pd)

    @app.get("/api/fundamentals/{symbol}/ratios")
    def fundamentals_ratios_endpoint(symbol: str) -> dict[str, Any]:
        """Derived P/E, P/B and dividend yield from stored inputs only.

        Inputs are reported figures with period/source/verification; the price
        is the last stored close with its date. Missing inputs yield
        value=null plus the exact reason - never an estimate.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        store = get_store()
        with get_conn() as conn:
            return fundamentals_ratios(conn, store, symbol)

    # ------------------------------------ fundamental revisions & point-in-time
    # NOTE: registered before /api/fundamentals/{symbol}; that catch-all would
    # otherwise swallow these static paths and treat them as a symbol name.
    @app.get("/api/fundamentals/revisions")
    def fundamentals_revisions(symbol: str | None = None, limit: int = 200) -> dict[str, Any]:
        from megatool.db import get_conn
        from megatool.fundamentals import revision_monitor

        with get_conn() as conn:
            return revision_monitor(conn, symbol=symbol, limit=limit)

    @app.get("/api/fundamentals/as-of")
    def fundamentals_as_of(symbol: str, as_of: str) -> dict[str, Any]:
        from megatool.db import get_conn
        from megatool.fundamentals import point_in_time_coverage, query_symbol_as_of

        with get_conn() as conn:
            rows = query_symbol_as_of(conn, symbol, as_of)
            coverage = point_in_time_coverage(conn, symbol)
        return {"symbol": symbol.upper(), "as_of": as_of, "rows": rows,
                "row_count": len(rows), "coverage": coverage}

    @app.get("/api/fundamentals/{symbol}")
    def fundamentals_for_symbol(symbol: str) -> dict[str, Any]:
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
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

    @app.get("/api/screen/export.xlsx")
    def screen_export_xlsx(tree: str) -> Response:
        """Export a screen as Excel (.xlsx) using openpyxl."""
        import json
        import io

        try:
            node = ScreenNode.from_dict(json.loads(tree))
        except Exception as exc:
            raise HTTPException(400, f"invalid screen definition: {exc}") from exc
        problems = validate_tree(node)
        if problems:
            raise HTTPException(400, "invalid screen definition: " + "; ".join(problems))
        df = to_dataframe(run_screen(get_store(), node))
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Screen results"
        ws.append(list(df.columns))
        for row in df.itertuples(index=False):
            ws.append([("" if v is None else v) for v in row])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=screen.xlsx"},
        )

    @app.get("/api/screen/export.pdf")
    def screen_export_pdf(tree: str) -> Response:
        """Export a screen as a minimal, valid PDF (no external dependency)."""
        import json

        try:
            node = ScreenNode.from_dict(json.loads(tree))
        except Exception as exc:
            raise HTTPException(400, f"invalid screen definition: {exc}") from exc
        problems = validate_tree(node)
        if problems:
            raise HTTPException(400, "invalid screen definition: " + "; ".join(problems))
        df = to_dataframe(run_screen(get_store(), node))
        # Build a minimal valid PDF with text content.
        lines = ["Mega Tool - Screen Export", "", "Columns: " + ", ".join(str(c) for c in df.columns), ""]
        for row in df.head(40).itertuples(index=False):
            lines.append(" | ".join(str(v) if v is not None else "" for v in row))
        # Escape parentheses for PDF text.
        def esc_pdf(s):
            return str(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content = "BT /F1 9 Tf 40 780 Td 12 TL " + " ".join(f"({esc_pdf(l)}) Tj T*" for l in lines) + " ET"
        # Minimal PDF structure.
        objects = []
        objects.append("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
        objects.append("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
        objects.append("3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n")
        objects.append("4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
        stream = content.encode("latin-1", errors="replace")
        objects.append(f"5 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream\nendobj\n")
        # Assemble with xref.
        body = b""
        offsets = []
        for o in objects:
            offsets.append(len(body))
            body += o.encode("latin-1") if isinstance(o, str) else o
        xref_pos = len(body)
        xref = f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n"
        for off in offsets:
            xref += f"{off:010d} 00000 n \n"
        trailer = f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
        pdf = b"%PDF-1.4\n" + body + xref.encode("latin-1") + trailer.encode("latin-1")
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=screen.pdf"},
        )

    # ==================================================================== BABA
    # The BABA report builder. Everything runs in-process so it shares the
    # already-open market store (DuckDB allows only one process to hold the
    # file lock).
    from megatool import report_builder as rb

    #: Journal and portfolio components contain private records. They are only
    #: ever included when the caller is the owner (loopback + trusted) AND asks
    #: for them explicitly. A shared deployment can therefore never export them
    #: by guessing a component id.
    _PRIVATE_CATEGORIES = ("K_journal", "L_portfolio")

    def _baba_owner(request: Request) -> bool:
        from megatool.friend_access import client_is_loopback, trust_loopback

        host = request.client.host if request.client else None
        return bool(trust_loopback() and client_is_loopback(host))

    def _baba_components(body: dict[str, Any], *, allow_private: bool) -> list[str]:
        reg = rb._registry()
        out = []
        for cid in body.get("components") or []:
            comp = reg.get(cid)
            if comp is None:
                raise HTTPException(400, f"unknown component {cid!r}")
            if not allow_private and comp.category in _PRIVATE_CATEGORIES:
                continue
            out.append(cid)
        return out

    @app.get("/api/baba/components")
    def baba_components(request: Request) -> dict[str, Any]:
        """The report component registry: what exists, and what can run today.

        Availability is computed per component from whether a data source
        currently backs it, so a checkbox is never offered for a section that
        would have to be invented. Private categories are omitted for a
        non-owner client.
        """
        reg = rb._registry()
        owner = _baba_owner(request)
        out = []
        for cid in rb.get_component_ids():
            c = reg[cid]
            if not owner and c.category in _PRIVATE_CATEGORIES:
                continue
            out.append({
                "id": c.id,
                "name": c.name,
                "category": c.category,
                "category_name": dict(rb.COMPONENT_CATEGORIES).get(c.category, c.category),
                "description": c.description,
                "output": c.output,
                "requires": list(c.requires),
                "scope": list(c.scope),
                "available": c.available,
                "reason": c.reason,
                "methodology": c.methodology,
                "private": c.category in _PRIVATE_CATEGORIES,
            })
        categories = [
            {"id": cid, "name": name}
            for cid, name in rb.COMPONENT_CATEGORIES
            if owner or cid not in _PRIVATE_CATEGORIES
        ]
        return {
            "categories": categories,
            "components": out,
            "count": len(out),
            "available": sum(1 for c in reg.values() if c.available),
            "private_included": owner,
            "sector_targets": {
                "note": ("Provisional user-supplied reference counts. These are NOT "
                         "verified current NEPSE listing counts and are never presented "
                         "as fact. Actual counts are computed from stored data."),
                "Commercial Banks": 19, "Development Banks": 11, "Hydropower": 28,
                "Microfinance": 17, "Life Insurance": 12, "Non-Life Insurance": 11,
                "Finance Companies": 11, "Investment Companies": 6, "Hotels": 3,
                "Manufacturing and Processing": 2, "Others": 3,
            },
        }

    @app.get("/api/baba/symbols")
    def baba_symbols() -> dict[str, Any]:
        """The authoritative symbol catalogue used by BABA autocomplete.

        A symbol is present when it has stored bars, security-master metadata,
        or a fundamental record. Presence is deliberately independent of one
        dataset: a valid company with no quarterly filing must remain
        selectable, while each dataset flag tells the UI what it can load.
        """
        from megatool.report_components import review_company_names

        store = get_store()
        fallback_names = review_company_names()
        fundamentals: dict[str, dict[str, Any]] = {}
        fundamental_error = None
        try:
            db = PATHS.processed / "megatool_state.sqlite"
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
                rows = conn.execute(
                    """SELECT symbol, COUNT(*), MAX(period_end),
                              MAX(CASE WHEN LOWER(COALESCE(period_label, ''))
                                        LIKE '%quarter%' THEN 1 ELSE 0 END)
                       FROM fundamentals GROUP BY symbol"""
                ).fetchall()
                for symbol, count, latest, has_q in rows:
                    fundamentals[str(symbol).upper()] = {
                        "count": int(count or 0),
                        "latest": str(latest)[:10] if latest else None,
                        "quarterly": bool(has_q),
                    }
        except Exception as exc:  # noqa: BLE001 - the catalogue still works without it
            fundamental_error = str(exc)

        bar_counts: dict[str, tuple[int, str | None]] = {}
        try:
            for symbol, count, _first_date, last_date in store.query_rows(
                """SELECT symbol, COUNT(*), MIN(trading_date), MAX(trading_date)
                   FROM price_bars GROUP BY symbol"""
            ):
                bar_counts[str(symbol).upper()] = (
                    int(count or 0),
                    str(last_date)[:10] if last_date else None,
                )
        except Exception:  # noqa: BLE001 - metadata-only catalogue is still useful
            pass

        try:
            meta = store.securities_meta()
        except Exception:  # noqa: BLE001
            meta = {}

        names = set(bar_counts) | set(fundamentals) | set(meta)
        out = []
        for symbol in sorted(names):
            info = meta.get(symbol, {})
            f = fundamentals.get(symbol, {})
            bars, last_date = bar_counts.get(symbol, (0, None))
            out.append({
                "symbol": symbol,
                "name": info.get("name") or fallback_names.get(symbol) or "",
                "sector": canonical_sector(info.get("sector")) or "",
                "instrument_type": info.get("instrument_type") or "",
                "status": info.get("status") or "UNKNOWN",
                "has_prices": bars > 0,
                "bars": bars,
                "last_price_date": last_date,
                "has_fundamentals": bool(f),
                "fundamental_count": int(f.get("count") or 0),
                "latest_period": f.get("latest"),
                "has_quarterly": bool(f.get("quarterly")),
            })
        return {
            "count": len(out),
            "symbols": out,
            "source": "price bars + security master + stored fundamentals; "
                      "company names fall back to the labelled review sources when the master has none",
            "fundamental_error": fundamental_error,
        }

    def _baba_request(body: dict[str, Any], *, allow_private: bool = True) -> rb.ReportRequest:
        """Validate an incoming report request.

        Symbol and component counts are bounded so a request cannot make the
        generator scan the whole universe or build an unbounded document.
        """
        symbols = body.get("symbols") or []
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.replace("\n", ",").split(",") if s.strip()]
        if not isinstance(symbols, list) or len(symbols) > rb.MAX_SYMBOLS:
            raise HTTPException(400, f"too many symbols (max {rb.MAX_SYMBOLS})")
        components = body.get("components") or []
        if not isinstance(components, list) or len(components) > rb.MAX_COMPONENTS:
            raise HTTPException(400, f"too many components (max {rb.MAX_COMPONENTS})")
        ids = _baba_components(body, allow_private=allow_private)
        return rb.ReportRequest(
            components=ids,
            symbols=[str(s).strip().upper() for s in symbols if str(s).strip()],
            sector=body.get("sector"),
            period=body.get("period"),
            fmt=str(body.get("format") or "xlsx").lower(),
            title=body.get("title"),
            notes=body.get("notes"),
        )

    @app.post("/api/baba/report/preview")
    def baba_report_preview(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Assemble the selected sections and return them for on-screen preview.

        The preview is exactly what will be exported: the same sections, the
        same values, the same unavailable list.
        """
        req = _baba_request(body, allow_private=_baba_owner(request))
        report = rb.assemble_report(req)
        report["quality"]["private_components_included"] = any(
            c.startswith(("j_", "p_")) for c in req.components
        )
        return report

    @app.get("/api/baba/report/export")
    def baba_report_export(request: Request, components: str, format: str = "xlsx",
                           symbols: str = "", sector: str | None = None,
                           period: str | None = None, title: str | None = None,
                           notes: str | None = None) -> Response:
        """Render the selected sections to a file and download it.

        ``components`` is a comma-separated id list. Journal and portfolio
        components are private: they are included only for the owner, and only
        with an explicit ``include_private=true`` flag. A shared request can
        never silently attach personal transactions.
        """
        fmt = (format or "xlsx").lower()
        if fmt not in ("xlsx", "csv", "pdf", "json"):
            raise HTTPException(400, f"unsupported format {fmt!r}")
        ids = [c.strip() for c in components.split(",") if c.strip()]
        owner = _baba_owner(request)
        include_private = (
            owner and str(request.query_params.get("include_private", "")).lower()
            in ("1", "true", "yes")
        )
        body = {
            "components": ids,
            "symbols": [s.strip().upper() for s in symbols.split(",") if s.strip()],
            "sector": sector, "period": period, "format": fmt,
            "title": title, "notes": notes,
        }
        req = _baba_request(body, allow_private=include_private)
        report = rb.assemble_report(req)
        renderer = {
            "xlsx": (rb.render_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     "report.xlsx"),
            "csv": (rb.render_csv, "application/zip", "report_csv.zip"),
            "pdf": (rb.render_pdf, "application/pdf", "report.pdf"),
            "json": (rb.render_json, "application/json", "report.json"),
        }[fmt]
        data, media, filename = renderer[0](report), renderer[1], renderer[2]
        # Private data must never be cacheable.
        private = any(c.startswith(("j_", "p_")) for c in req.components)
        headers = {"Content-Disposition": f"attachment; filename={filename}"}
        if private:
            headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            headers["Pragma"] = "no-cache"
        return Response(content=data, media_type=media, headers=headers)

    # ------------------------------------------------------- research studio
    @app.get("/api/baba/research/catalog")
    def baba_research_catalog() -> dict[str, Any]:
        """Components, categories and presets for the multi-symbol report UI.

        Journal and portfolio components are deliberately absent: a research
        report is public-market analysis, and a job never assembles private
        records. (The BABA component catalog keeps them for the owner's
        on-screen report builder.)
        """
        from megatool.research_report import research_catalog

        return research_catalog(allow_private=False)

    @app.post("/api/baba/research/jobs")
    def baba_research_job_start(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Start a real background build. Returns the job id immediately."""
        from megatool import jobs
        from megatool import research_report as rr

        owner = _baba_owner(request)
        raw_components = body.get("components")
        if raw_components is not None and not isinstance(raw_components, list):
            raise HTTPException(400, "components must be a list of component ids")
        components = rr.clean_components(raw_components or [], allow_private=False)
        if not components:
            preset = rr.RESEARCH_PRESETS.get(str(body.get("preset") or "full"))
            if preset is None:
                raise HTTPException(400, f"unknown preset {body.get('preset')!r}")
            components = rr.clean_components(preset["components"], allow_private=False)
        raw_symbols = body.get("symbols") or []
        if isinstance(raw_symbols, str):
            raw_symbols = [s.strip() for s in raw_symbols.replace("\n", ",").split(",") if s.strip()]
        if not isinstance(raw_symbols, list):
            raise HTTPException(400, "symbols must be a list")
        if len(raw_symbols) > rr.MAX_RESEARCH_SYMBOLS:
            raise HTTPException(400, f"too many symbols (max {rr.MAX_RESEARCH_SYMBOLS})")
        try:
            symbols = rr.clean_symbols([str(s) for s in raw_symbols])
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not symbols:
            raise HTTPException(400, "select at least one symbol")
        risk_budget = body.get("risk_budget")
        capital = body.get("capital")
        if risk_budget is not None:
            try:
                risk_budget = float(risk_budget)
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "risk_budget must be a number") from exc
            if risk_budget < 0:
                raise HTTPException(400, "risk_budget must be >= 0")
        if capital is not None:
            try:
                capital = float(capital)
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "capital must be a number") from exc
            if capital < 0:
                raise HTTPException(400, "capital must be >= 0")
        title = body.get("title")
        notes = body.get("notes")

        steps = len(symbols) * 3 + 4
        job = jobs.create_job(
            "research_report",
            params={
                "symbols": symbols,
                "components": components,
                "title": title,
                "risk_budget": risk_budget,
                "capital": capital,
                "owner": owner,
            },
            steps_total=steps,
            stage="queued",
        )

        def _work(job_id: str) -> dict[str, Any]:
            from pathlib import Path

            def progress(done: int, stage: str, message: str) -> None:
                jobs.update_job(job_id, steps_done=done, stage=stage, message=message)

            bundle = rr.build_bundle(
                symbols, components,
                title=title, notes=notes,
                risk_budget=risk_budget,
                progress=progress,
                allow_private=False,
                store=get_store(),
            )
            out = jobs.exports_dir(job_id)
            artifacts: dict[str, Path] = {}
            # One XLSX and one PDF per symbol: real, separately reported steps.
            parts: dict[str, dict[str, bytes]] = {}
            done = len(symbols)
            for idx, sym in enumerate(bundle["symbols"], start=1):
                xlsx_bytes = rr.render_symbol_xlsx(bundle, sym)
                parts[sym] = {"xlsx": xlsx_bytes}
                progress(done + (idx - 1) * 2 + 1, "rendering_symbol",
                         f"{sym}: workbook written")
                pdf_bytes = rr.render_symbol_pdf(bundle, sym)
                parts[sym]["pdf"] = pdf_bytes
                progress(done + (idx - 1) * 2 + 2, "rendering_symbol",
                         f"{sym}: PDF written")
                (out / f"{sym}-research.xlsx").write_bytes(xlsx_bytes)
                (out / f"{sym}-research.pdf").write_bytes(pdf_bytes)

            base = len(symbols) * 3
            progress(base + 1, "rendering_pdf", "Writing the combined PDF")
            pdf = out / "research-report.pdf"
            pdf.write_bytes(rr.render_bundle_pdf(bundle))
            artifacts["pdf"] = pdf
            progress(base + 2, "rendering_xlsx", "Writing the combined workbook")
            xlsx = out / "research-report.xlsx"
            xlsx.write_bytes(rr.render_bundle_xlsx(bundle))
            artifacts["xlsx"] = xlsx
            progress(base + 3, "rendering_json", "Writing the assembled JSON")
            js = out / "research-report.json"
            js.write_bytes(rr.render_bundle_json(bundle))
            artifacts["json"] = js
            progress(base + 4, "packaging", "Packaging per-symbol reports and CSVs")
            zpath = out / "research-package.zip"
            zpath.write_bytes(rr.render_bundle_zip(bundle, parts=parts))
            artifacts["zip"] = zpath
            return artifacts

        jobs.start_job(job.id, _work)
        return {"job": job.to_dict(), "steps_total": steps}

    @app.get("/api/baba/research/jobs")
    def baba_research_jobs(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
        from megatool import jobs

        return {"jobs": [j.to_dict() for j in jobs.list_jobs(kind="research_report", limit=limit)]}

    @app.get("/api/baba/research/jobs/{job_id}")
    def baba_research_job(job_id: str) -> dict[str, Any]:
        from megatool import jobs

        try:
            return {"job": jobs.get_job(job_id).to_dict()}
        except jobs.JobError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/baba/research/jobs/{job_id}/download/{fmt}")
    def baba_research_download(job_id: str, fmt: str) -> Response:
        from megatool import jobs

        media = {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "json": "application/json",
            "zip": "application/zip",
        }
        if fmt not in media:
            raise HTTPException(400, f"unsupported format {fmt!r}")
        try:
            path = jobs.artifact_path(job_id, fmt)
        except jobs.JobError as exc:
            raise HTTPException(404, str(exc)) from exc
        headers = {
            "Content-Disposition": f'attachment; filename="{path.name}"',
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        }
        return Response(content=path.read_bytes(), media_type=media[fmt], headers=headers)

    @app.get("/api/baba/volatility/{symbol}")
    def baba_volatility(symbol: str, risk_budget: float | None = Query(None, ge=0),
                        capital: float | None = Query(None, ge=0)) -> dict[str, Any]:
        """Next-session range forecast from stored bars, with out-of-sample scoring."""
        from megatool.volatility import VolatilityError, volatility_report

        sym = symbol.upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,19}", sym):
            raise HTTPException(400, "invalid symbol")
        store = get_store()
        df = store.get_bars(sym)
        if df is None or df.empty:
            raise HTTPException(404, f"no stored history for {sym}")
        try:
            return volatility_report(df, sym, risk_budget=risk_budget, capital=capital)
        except VolatilityError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/baba/templates")
    def baba_templates_list() -> dict[str, Any]:
        return {"templates": rb.list_templates()}

    @app.post("/api/baba/templates")
    def baba_templates_save(body: dict[str, Any]) -> dict[str, Any]:
        name = str(body.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "a template name is required")
        req = _baba_request(body)
        return rb.save_template(name, req)

    @app.put("/api/baba/templates/{name}")
    def baba_templates_rename(name: str, body: dict[str, Any]) -> dict[str, Any]:
        return rb.rename_template(name, str(body.get("name") or "").strip())

    @app.delete("/api/baba/templates/{name}")
    def baba_templates_delete(name: str) -> dict[str, Any]:
        if not rb.delete_template(name):
            raise HTTPException(404, f"no template named {name!r}")
        return {"deleted": name}

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
                    "category": spec.get("category", "undefined"),
                }
                for key, spec in STRATEGIES.items()
            ],
            "config_defaults": {
                "initial_cash": 100_000.0,
                "fee_rate": PLACEHOLDER_FEE_RATE,
                # The default fee is NOT a verified NEPSE rate; every /api/backtest
                # result repeats this in its `cost_model` block (B-31 / R3 / T-12).
                "fee_rate_status": "placeholder",
                "slippage": 0.0,
                "execution": "next_open",
                "whole_units": True,
                # OPT-IN verified component schedule (C3/D-y): pass
                # fee_schedule="official-2083-84" (and optionally
                # cgt="natural_person") to price each side with the official
                # tiered commission + SEBON + sell-side DP charge, and — only
                # when the category is declared — holding-period capital gains
                # tax. The flat fee_rate stays the default, unchanged.
                "fee_schedule": None,
                "cgt": None,
                "available_fee_schedules": sorted(FEE_SCHEDULES),
            },
            "note": "Backtests are historical calculations with the assumptions "
            "listed in the response. They are not predictions or advice. The "
            "default fee_rate is a PLACEHOLDER - see `cost_model.status` in every "
            "/api/backtest result.",
        }

    @app.post("/api/backtest")
    def backtest(req: PydanticBacktestRequest) -> dict[str, Any]:
        return _run_backtest_request(req)

    def _run_backtest_request(req: PydanticBacktestRequest) -> dict[str, Any]:
        """Run one backtest from a validated request.

        Shared by ``POST /api/backtest`` and the experiment workbench so a
        saved run reproduces through the *identical* calculation path — there
        is no second, drifting implementation to disagree with the first.
        """
        if not valid_symbol(req.symbol):
            raise HTTPException(400, "invalid symbol")
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
                fee_schedule=req.fee_schedule,
                cgt=req.cgt,
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

    # --------------------------------------------------------- experiments
    @app.get("/api/experiments/compare")
    def experiments_compare(a: int, b: int) -> dict[str, Any]:
        """Metric-by-metric comparison of two saved experiments."""
        try:
            ea = get_experiment(a)
            eb = get_experiment(b)
        except ExperimentError as exc:
            raise HTTPException(404, str(exc)) from exc
        return compare_experiments(ea, eb)

    @app.get("/api/experiments")
    def experiments_list() -> dict[str, Any]:
        items = list_experiments()
        return {"experiments": items, "count": len(items)}

    @app.post("/api/experiments")
    def experiments_save(req: PydanticExperimentSave) -> dict[str, Any]:
        try:
            return save_experiment(req.label, req.config, req.result)
        except ExperimentError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/experiments/{exp_id}")
    def experiments_get(exp_id: int) -> dict[str, Any]:
        try:
            return get_experiment(exp_id)
        except ExperimentError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.delete("/api/experiments/{exp_id}")
    def experiments_delete(exp_id: int) -> dict[str, Any]:
        if not delete_experiment(exp_id):
            raise HTTPException(404, f"no experiment with id {exp_id}")
        return {"deleted": exp_id}

    @app.post("/api/experiments/{exp_id}/reproduce")
    def experiments_reproduce(exp_id: int) -> dict[str, Any]:
        """Re-run a saved experiment and compare the fresh metrics to the snapshot.

        The stored configuration is rebuilt into a request and run through the
        same ``_run_backtest_request`` path. Divergences are reported with
        their delta — never hidden by an "identical"/"reproduced" claim.
        """
        try:
            saved = get_experiment(exp_id)
        except ExperimentError as exc:
            raise HTTPException(404, str(exc)) from exc
        try:
            req = PydanticBacktestRequest(**saved["config"])
        except Exception as exc:  # noqa: BLE001 - surfaced as a 400 to the caller
            raise HTTPException(400, f"stored configuration is not usable: {exc}") from exc
        fresh = _run_backtest_request(req)
        comparison = compare_experiments(
            {
                "id": saved["id"],
                "label": saved["label"],
                "config_hash": saved["config_hash"],
                "metrics": saved["result"].get("metrics", {}),
                "config": saved["config"],
            },
            {
                "id": None,
                "label": "fresh run",
                "config_hash": saved["config_hash"],
                "metrics": fresh.get("metrics", {}),
                "config": saved["config"],
            },
        )
        return {"experiment": exp_id, "reproduced": fresh, "comparison": comparison}

    @app.get("/api/experiments/{exp_id}/export")
    def experiments_export(
        exp_id: int, format: str = Query("markdown", pattern="^(markdown|json)$")
    ) -> Any:
        """Export a saved experiment as Markdown (default) or JSON."""
        try:
            exp = get_experiment(exp_id)
        except ExperimentError as exc:
            raise HTTPException(404, str(exc)) from exc
        if format == "json":
            return exp
        return PlainTextResponse(experiment_markdown(exp), media_type="text/markdown")

    # ----------------------------------------------------------- watchlists
    def _watchlist_rows(symbols: list[str]) -> list[dict[str, Any]]:
        """Enrich watchlist symbols with the latest stored close/change.

        A symbol with no stored bar is returned with ``close: null`` and a
        reason — a missing quote is never rendered as a zero.
        """
        if not symbols:
            return []
        latest = get_store().latest_bars()
        by: dict[str, Any] = {}
        if latest is not None and not latest.empty:
            for _, r in latest.iterrows():
                by[str(r["symbol"])] = r
        rows: list[dict[str, Any]] = []
        for s in symbols:
            r = by.get(s)
            if r is None:
                rows.append(
                    {
                        "symbol": s,
                        "close": None,
                        "change_pct": None,
                        "turnover": None,
                        "volume": None,
                        "data_as_of": None,
                        "note": "no stored bar for this symbol",
                    }
                )
            else:
                chg = pd.to_numeric(pd.Series([r.get("percent_change")]), errors="coerce").iloc[0]
                rows.append(
                    {
                        "symbol": s,
                        "close": _f(r["close"]),
                        "change_pct": _f(chg),
                        "turnover": _f(r.get("turnover")),
                        "volume": _i(r.get("volume")),
                        "data_as_of": str(pd.to_datetime(r["trading_date"]).date()),
                        "note": "latest stored bar (not a live feed)",
                    }
                )
        return rows

    @app.get("/api/watchlists")
    def watchlists_list() -> dict[str, Any]:
        items = list_watchlists()
        return {"watchlists": items, "count": len(items)}

    @app.post("/api/watchlists")
    def watchlists_create(req: PydanticWatchlistRequest) -> dict[str, Any]:
        try:
            return create_watchlist(req.name, req.symbols)
        except WatchlistError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/watchlists/{name}")
    def watchlists_get(name: str) -> dict[str, Any]:
        try:
            wl = get_watchlist(name)
        except WatchlistError as exc:
            raise HTTPException(404, str(exc)) from exc
        wl["rows"] = _watchlist_rows(wl["symbols"])
        return wl

    @app.patch("/api/watchlists/{name}")
    def watchlists_patch(name: str, req: PydanticWatchlistPatch) -> dict[str, Any]:
        try:
            return update_watchlist(
                name,
                new_name=req.new_name,
                symbols=req.symbols if req.symbols is not None else "__unset__",
                add=req.add,
                remove=req.remove,
            )
        except WatchlistError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete("/api/watchlists/{name}")
    def watchlists_delete(name: str) -> dict[str, Any]:
        if not delete_watchlist(name):
            raise HTTPException(404, f"no watchlist named {name!r}")
        return {"deleted": name}

    # -------------------------------------------------- saved screens / rules
    @app.get("/api/templates")
    def templates() -> dict[str, Any]:
        """Reusable research **workflow** templates (declarative, read-only).

        Each template names existing endpoints and the parameters to use, so the
        frontend can run a workflow without any new calculation engine. A
        template configures tools; it does not add analysis of its own.
        """
        from megatool.templates import template_catalogue

        payload = template_catalogue()
        payload["disclaimer"] = DISCLAIMER
        return payload

    @app.get("/api/screens")
    def screens_list() -> dict[str, Any]:
        """List saved custom rules, plus the live metric catalogue for the UI.

        The catalogue is embedded here (rather than a sibling route) so the
        integer-typed ``{screen_id}`` path can never shadow it.
        """
        items = list_screens()
        return {"screens": items, "count": len(items), "metrics": metric_catalogue()}

    @app.post("/api/screens/propose")
    def screens_propose(req: PydanticRuleProposal) -> dict[str, Any]:
        """Translate a plain-language question into a screen rule **proposal**.

        The translation is deterministic (:mod:`megatool.rule_parse`): a
        documented grammar over the live metric catalogue. No model is called,
        no code is generated or executed, and nothing is screened here — the
        response is a validated data tree for the user to review, edit and then
        run through the existing ``POST /api/screen`` path. Clauses that cannot
        be mapped are returned with a reason rather than dropped.
        """
        from megatool.rule_parse import parse_question

        try:
            return parse_question(req.question)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/screens")
    def screens_save(req: PydanticSavedScreenSave) -> dict[str, Any]:
        try:
            return save_screen(req.name, req.definition, overwrite=req.overwrite)
        except SavedScreenError as exc:
            raise HTTPException(400, str(exc)) from exc
        except sqlite3.IntegrityError as exc:  # name raced in as a duplicate
            raise HTTPException(400, f"a screen named {req.name!r} already exists") from exc

    @app.get("/api/screens/{screen_id}")
    def screens_get(screen_id: int) -> dict[str, Any]:
        try:
            return get_screen(screen_id)
        except SavedScreenError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.patch("/api/screens/{screen_id}")
    def screens_patch(screen_id: int, req: PydanticSavedScreenPatch) -> dict[str, Any]:
        try:
            return update_screen(screen_id, new_name=req.new_name, definition=req.definition)
        except SavedScreenError as exc:
            message = str(exc)
            code = 404 if message.startswith("no saved screen") else 400
            raise HTTPException(code, message) from exc

    @app.post("/api/screens/{screen_id}/duplicate")
    def screens_duplicate(screen_id: int, req: PydanticSavedScreenDuplicate) -> dict[str, Any]:
        try:
            return duplicate_screen(screen_id, req.new_name)
        except SavedScreenError as exc:
            message = str(exc)
            code = 404 if message.startswith("no saved screen") else 400
            raise HTTPException(code, message) from exc

    @app.delete("/api/screens/{screen_id}")
    def screens_delete(screen_id: int) -> dict[str, Any]:
        if not delete_screen(screen_id):
            raise HTTPException(404, f"no saved screen with id {screen_id}")
        return {"deleted": screen_id}

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

    @app.get("/api/floorsheet/trend")
    def floorsheet_trend_route(
        symbol: str | None = None,
        sessions: int = Query(10, ge=2, le=60),
        top: int = Query(5, ge=1, le=50),
    ) -> dict[str, Any]:
        """Multi-session activity trend and per-broker net flow (feature 3).

        Activity figures are observed prints; flow labels are inferences with
        their basis stated. Fewer than two imported sessions yields an explicit
        insufficient_sessions status instead of a trend from one point.
        """
        return floorsheet_trend(symbol=symbol, sessions=sessions, top=top)

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

    @app.post("/api/forecast/rolling")
    def forecast_rolling(req: PydanticForecastRollingRequest) -> dict[str, Any]:
        """Walk-forward evaluation: many chronological origins, one honest verdict.

        Each origin fits on the points strictly before its own hold-out window
        and is scored against the naive last-value forecast there. The summary
        says how often the model beat that baseline - if it rarely does, the
        answer is that the model has shown no skill, and the payload says so
        in words rather than hiding it behind a smooth curve.
        """
        store = get_store()
        symbol = req.symbol.upper()
        df = store.get_bars(symbol, start=req.start, end=req.end)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol}")
        try:
            out = rolling_origin(
                df["close"].to_numpy(),
                model=req.model,
                train_min=req.train_min,
                holdout=req.holdout,
                step=req.step,
                params=req.params,
                dates=[str(d.date()) for d in df["trading_date"]],
            )
        except ForecastError as exc:
            raise HTTPException(400, str(exc)) from exc
        out["symbol"] = symbol
        out["data_as_of"] = str(df["trading_date"].max().date())
        out["live"] = False
        return out

    # ------------------------------------------------------------ news / events
    @app.post("/api/news/import")
    def news_import_route(req: PydanticNewsImportRequest) -> dict[str, Any]:
        """Import one owner-supplied file of news records (CSV or JSON text).

        This is the ONLY way news records enter the archive: no live source
        is connected (register item 7 / L4). Every skipped row is returned
        with its line number and reason, because a silently dropped headline
        is a wrong "latest news" date later.
        """
        try:
            return news_import(
                req.content,
                fmt=req.format.lower(),
                source_file=req.source,
            )
        except NewsError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/news/summary")
    def news_summary_route(
        symbol: str | None = None, since: str | None = None, top: int = 10
    ) -> dict[str, Any]:
        """Counts and recency over the IMPORTED archive - never more than that."""
        return news_summary(symbol=symbol or None, since=since or None, top=max(1, min(top, 50)))

    # -------------------------------------------------- research assistant
    @app.get("/api/research/topics")
    def research_topics() -> dict[str, Any]:
        """What the assistant can answer - and what it refuses to."""
        from megatool.llm import provider_status

        status = provider_status()
        return {
            "topics": [{"key": k, "help": TOPIC_HELP[k]} for k in TOPICS],
            "what_this_is": (
                "A deterministic rules engine over stored bars. It returns a "
                "number, the window it came from, and the definition used, so "
                "every claim can be checked. No language model produces these "
                "figures: the numbers come only from calculations."
            ),
            "what_this_is_not": (
                "Not an opinion, not a recommendation, not a prediction. It "
                "cannot read news or filings, and it will not tell you to buy "
                "or sell anything."
            ),
            "ai_status": status,
            "ai_note": (
                "An AI provider (local Ollama or hosted OpenRouter) may be "
                "configured for OPTIONAL explanations of the deterministic "
                "results (set interpret=true on /api/research/ask). AI text is "
                "labelled and never replaces or alters the calculations."
            ),
        }

    @app.get("/api/research/{symbol}")
    def research_symbol(symbol: str) -> dict[str, Any]:
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
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

    @app.get("/api/research/workspace/{symbol}")
    def research_workspace(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int = Query(DEFAULT_WORKSPACE_LIMIT, ge=30, le=5000),
        modules: str | None = Query(
            None,
            help="Optional comma-separated module names to run; omitted runs all.",
        ),
    ) -> dict[str, Any]:
        """Unified research workspace for one symbol (§1/§16) with honest state.

        Returns the symbol overview plus every analysis module's **actual**
        execution state — COMPLETED, COMPLETED_WITH_WARNINGS, FAILED,
        BLOCKED_BY_MISSING_DATA or NOT_STARTED — with timings and error text.

        A failing module never makes the page look successful: it is recorded
        and the remaining modules still run. No completion percentage is
        invented, because exact progress is not measurable here.
        """
        sym = symbol.upper()
        store = get_store()
        df = store.get_bars(sym, start=start, end=end, limit=limit)
        if df.empty:
            raise HTTPException(404, f"no stored history for {sym}")

        run: dict[str, bool] = {}
        if modules:
            wanted = {m.strip() for m in modules.split(",") if m.strip()}
            unknown = wanted - set(WORKSPACE_MODULES)
            if unknown:
                raise HTTPException(
                    400,
                    f"unknown module(s): {sorted(unknown)}; valid: {sorted(WORKSPACE_MODULES)}",
                )
            run = {name: name in wanted for name in WORKSPACE_MODULES}

        try:
            return build_workspace(df, sym, limit=limit, run=run)
        except Exception as exc:  # noqa: BLE001 - surface, never mask
            raise HTTPException(500, f"workspace failed: {type(exc).__name__}: {exc}") from exc

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
        if req.interpret:
            # The deterministic payload is never replaced: the AI explanation
            # is appended beside it, and personal journal findings are stripped
            # from the prompt unless the caller explicitly authorizes them.
            from megatool.agent import ToolResult
            from megatool.agent import interpret as agent_interpret

            private_keys = [
                k for k in payload if any(t in k.lower() for t in ("pdf", "journal", "written"))
            ]
            data = (
                payload
                if req.include_private
                else {k: v for k, v in payload.items() if k not in private_keys}
            )
            tr = ToolResult(
                tool="research",
                status="ok",
                private=False,
                summary=f"deterministic answer for {sym} as of {payload.get('as_of', '?')}",
                provenance="deterministic rules engine over stored price_bars",
                data=data,
            )
            ai = agent_interpret(
                req.question or "summarize these findings",
                [tr],
                provider=req.provider or None,
                include_private=req.include_private,
            )
            if private_keys and not req.include_private:
                ai["excluded_private_keys"] = private_keys
            payload["ai_interpretation"] = ai
        return payload

    # -------------------------------------------------------------- agent (F12)
    @app.get("/api/agent/tools")
    def agent_tools() -> dict[str, Any]:
        """The tool registry: what the agent routes to, and which are private."""
        from megatool.agent import tool_registry

        return {"tools": tool_registry(), "disclaimer": DISCLAIMER}

    @app.post("/api/agent/run")
    def agent_run(req: PydanticAgentRequest) -> dict[str, Any]:
        """Route a research question to existing tools; optionally explain.

        Deterministic tool results and any AI interpretation are returned in
        separate fields. Private tools (portfolio risk, journal) run locally
        but are excluded from the AI prompt unless include_private=true.
        Read-only: the agent never trades.
        """
        from megatool.agent import run as agent_execute

        if not req.question or not req.question.strip():
            raise HTTPException(400, "question must not be empty")
        store = get_store()
        with get_conn() as conn:
            try:
                return agent_execute(
                    req.question,
                    store,
                    conn,
                    provider=req.provider or None,
                    interpret_ai=req.interpret,
                    include_private=req.include_private,
                    tools=req.tools,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc

    # ------------------------------------------------------------- ideas
    @app.get("/api/ideas")
    def ideas_catalogue() -> dict[str, Any]:
        """Investment-idea models with the inputs each needs, and what is stored.

        A model is only runnable when every input it needs exists in the database;
        the catalogue states this up front so a model is never presented as
        available when it would have to invent inputs.
        """
        from megatool.ideas import model_catalogue

        return {"models": model_catalogue()}

    @app.get("/api/ideas/{model_id}")
    def ideas_run(
        model_id: str,
        limit: int = Query(40, ge=1, le=200),
    ) -> dict[str, Any]:
        """Ranked results for one model, or an explicit insufficiency.

        Returns ``status: "insufficient_data"`` with the missing fields named when
        the model cannot be computed — never a fabricated score.
        """
        from megatool.ideas import IdeasError, evaluate

        try:
            with get_conn() as conn:
                return evaluate(model_id, get_store(), conn, limit=limit)
        except IdeasError as exc:
            raise HTTPException(404, str(exc)) from exc

    # ------------------------------------------------------------- portfolio
    @app.get("/api/portfolio")
    def portfolio() -> dict[str, Any]:
        """Positions derived from your ledger, marked to the latest stored close."""
        return value_portfolio(get_store())

    @app.get("/api/portfolio/cash-flow")
    def portfolio_cash_flow() -> dict[str, Any]:
        """Cash-flow view derived from the recorded transactions.

        A buy costs `quantity x price + fees`; a sell returns
        `quantity x price - fees`. Deposits, withdrawals, dividends and interest
        are not recorded, so `net_cash_flow` is the trades' net cash effect, not
        an account cash balance.
        """
        return cash_flows()

    @app.get("/api/portfolio/risk")
    def portfolio_risk(
        max_weight_pct: float = Query(40.0, ge=1.0, le=100.0),
        max_drawdown_pct: float = Query(25.0, ge=1.0, le=100.0),
        max_vol_pct: float = Query(5.0, ge=0.1, le=100.0),
    ) -> dict[str, Any]:
        """Deterministic risk metrics from stored history + explainable limits.

        Limits are query parameters with the documented defaults; every breach
        names its measured value and threshold. No live data is used.
        """
        from megatool.risk import portfolio_risk

        return portfolio_risk(
            get_store(),
            limits={
                "max_weight_pct": max_weight_pct,
                "max_drawdown_pct": max_drawdown_pct,
                "max_vol_pct": max_vol_pct,
            },
        )

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

    @app.post("/api/journal/{entry_id}/reflect")
    def journal_reflect_entry(entry_id: int, req: PydanticJournalReflect) -> dict[str, Any]:
        """Local deterministic reflection; AI only with explicit authorization.

        With authorize_private=false (default) no provider is contacted and
        the response says so. With the flag, the AI text is appended beside
        the deterministic context — never in place of it — and the recipient
        (local Ollama vs hosted) is named.
        """
        from megatool.journal import reflect as journal_reflect

        out = journal_reflect(
            entry_id, provider=req.provider or None, authorize_private=req.authorize_private
        )
        if out is None:
            raise HTTPException(404, f"no journal entry with id {entry_id}")
        return out

    # -------------------------------------------------------------- planning
    @app.post("/api/planning")
    def planning(req: PydanticPlanRequest) -> dict[str, Any]:
        """Turn an entry/stop/target into R multiples and a position size.

        Sizing is computed only when capital and risk_pct are supplied. With
        ``symbol``, the plan is also checked against the local portfolio:
        current weight, post-trade weight under a stated funding assumption,
        and the concentration limit - each figure either computed or refused
        with its reason, never approximated.
        """
        try:
            plan = make_plan(req.entry, req.stop, req.target)
            payload: dict[str, Any] = {"plan": plan.to_dict()}
            sizing_obj = None
            if req.capital is not None and req.risk_pct is not None:
                sizing_obj = position_size(
                    req.capital, req.risk_pct, plan.risk_per_share, req.entry
                )
                payload["sizing"] = sizing_obj.to_dict()
                # C3/D-y: the same verified engine prices the planned BUY, so
                # the "costs are excluded from sizing" note above is now
                # answered with an explicit estimate instead of a caveat.
                if sizing_obj.units > 0:
                    payload["cost_estimate"] = entry_cost_estimate(sizing_obj.cash_used)
                else:
                    payload["cost_estimate"] = {
                        "schedule": None,
                        "note": "no units to price: the sizing could not buy one unit",
                    }
            elif req.capital is not None or req.risk_pct is not None:
                raise HTTPException(400, "capital and risk_pct must be supplied together")

            if req.symbol and req.symbol.strip():
                sym = req.symbol.upper().strip()
                positions = derive_positions()
                cur_units = next((p.quantity for p in positions if p.symbol == sym), 0)
                valued = value_portfolio(get_store())
                summ = valued["summary"]
                price: float | None = None
                price_date: str | None = None
                for pos in valued["positions"]:
                    if pos["symbol"] == sym:
                        price = pos.get("last_price")
                        price_date = pos.get("price_as_of")
                payload["portfolio_check"] = constraint_check(
                    symbol=sym,
                    entry=req.entry,
                    sizing=sizing_obj,
                    current_units=max(int(cur_units), 0),
                    current_price=price,
                    current_price_date=price_date,
                    valued_total=float(summ.get("valued_market_value") or 0),
                    open_positions=int(summ.get("open_positions") or 0),
                    unvalued_positions=int(summ.get("unvalued_positions") or 0),
                    max_weight_pct=req.max_weight_pct,
                )
            else:
                payload["portfolio_check"] = {
                    "symbol": None,
                    "checked": False,
                    "reason": (
                        "no symbol given: pass symbol to check this plan "
                        "against your local portfolio"
                    ),
                }
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
                + _index_note(store)
            ),
        }

    @app.get("/api/market/ribbon")
    def market_ribbon(top: int = Query(8, ge=1, le=30)) -> dict[str, Any]:
        """Categorised scrolling-market-ribbon payload.

        Computed from the **most recent stored trading day** — never a live feed.
        Every ranking rule is stated in the payload, so a "top gainer" claim can
        be checked against its own definition. Each group keeps its true ranking,
        but a symbol is *claimed* by the first group that ranks it, so the ribbon
        shows distinct names instead of the same ten stocks five times; the
        number of duplicates skipped is reported per group rather than hidden.

        Categories that the stored data cannot support honestly are returned in
        ``unavailable`` with a reason, not faked.
        """
        store = get_store()
        latest = store.latest_bars()
        if latest.empty:
            return {"empty": True, "note": "No market data stored yet. Run `megatool fetch`."}

        df = latest.copy()
        for col in ("close", "percent_change", "turnover", "volume", "high", "low"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["change_pct"] = df["percent_change"]
        as_of = str(pd.to_datetime(df["trading_date"]).max().date())

        def item(row: Any) -> dict[str, Any]:
            return {
                "symbol": row["symbol"],
                "close": _f(row["close"]),
                "change_pct": _f(row["change_pct"]),
                "volume": _i(row["volume"]),
                "turnover": _f(row["turnover"]),
            }

        specs = [
            (
                "gainers",
                "Top gainers",
                f"largest percentage change up, {as_of} close vs the previous stored close",
                df.dropna(subset=["change_pct"]).query("change_pct > 0")
                .sort_values("change_pct", ascending=False),
            ),
            (
                "losers",
                "Top losers",
                f"largest percentage change down, {as_of} close vs the previous stored close",
                df.dropna(subset=["change_pct"]).query("change_pct < 0")
                .sort_values("change_pct"),
            ),
            (
                "turnover",
                "Turnover leaders",
                "largest traded value (turnover, NPR) on the most recent stored day",
                df.dropna(subset=["turnover"]).sort_values("turnover", ascending=False),
            ),
            (
                "volume",
                "Volume leaders",
                "largest traded share volume on the most recent stored day",
                df.dropna(subset=["volume"]).sort_values("volume", ascending=False),
            ),
        ]

        claimed: set[str] = set()
        groups: list[dict[str, Any]] = []
        for key, title, rule, frame in specs:
            picked: list[dict[str, Any]] = []
            skipped = 0
            for _, row in frame.iterrows():
                sym = row["symbol"]
                if sym in claimed:
                    skipped += 1
                    continue
                if len(picked) >= top:
                    break
                claimed.add(sym)
                picked.append(item(row))
            groups.append(
                {
                    "key": key,
                    "title": title,
                    "rule": rule,
                    "items": picked,
                    "skipped_duplicates": skipped,
                }
            )

        # New 252-bar highs/lows: the latest close compared with the high/low of
        # the *prior* 252 stored bars, so the test is not tautological. Requires
        # genuine high/low (a close-only series is skipped, not approximated).
        highs: list[dict[str, Any]] = []
        lows: list[dict[str, Any]] = []
        hl_reason = ""
        try:
            hl = store.query_df(
                """
                WITH ranked AS (
                    SELECT symbol, trading_date, high, low, close,
                           ROW_NUMBER() OVER (
                               PARTITION BY symbol ORDER BY trading_date DESC) AS rn
                    FROM price_bars WHERE high IS NOT NULL AND low IS NOT NULL
                ),
                prior AS (
                    SELECT symbol, MAX(high) AS hi, MIN(low) AS lo, COUNT(*) AS n
                    FROM ranked WHERE rn > 1 AND rn <= 252 GROUP BY symbol
                )
                SELECT p.symbol, p.hi, p.lo, l.close
                FROM prior p JOIN (
                    SELECT symbol, close FROM ranked WHERE rn = 1
                ) l ON l.symbol = p.symbol
                WHERE p.n >= 120
                """
            )
            if hl is not None and not hl.empty:
                for _, r in hl.iterrows():
                    if r["symbol"] in claimed:
                        continue  # already shown under a ranking group
                    close = _f(r["close"])
                    if close is None:
                        continue
                    if _f(r["hi"]) is not None and close > float(r["hi"]):
                        highs.append({"symbol": r["symbol"], "close": close, "level": _f(r["hi"])})
                    if _f(r["lo"]) is not None and close < float(r["lo"]):
                        lows.append({"symbol": r["symbol"], "close": close, "level": _f(r["lo"])})
                highs.sort(key=lambda x: x["symbol"])
                lows.sort(key=lambda x: x["symbol"])
        except Exception as exc:  # pragma: no cover - defensive
            hl_reason = f"extreme scan unavailable: {type(exc).__name__}"

        if highs or lows:
            groups.append(
                {
                    "key": "extremes",
                    "title": "New 252-bar extremes",
                    "rule": "latest close beyond the high/low of the prior 252 stored bars (≥120 required)",
                    "items": [{"symbol": h["symbol"], "close": h["close"], "change_pct": None,
                               "volume": None, "turnover": None, "kind": "high"} for h in highs]
                    + [{"symbol": lo["symbol"], "close": lo["close"], "change_pct": None,
                        "volume": None, "turnover": None, "kind": "low"} for lo in lows],
                    "skipped_duplicates": 0,
                }
            )

        unavailable = [
            {
                "key": "relvol",
                "title": "Unusual volume (relative)",
                "reason": (
                    "needs a per-symbol average-volume baseline over a window; the "
                    "bundle's Volume Scan screener computes it (metric "
                    "`volume_ratio_50`) but the ribbon does not duplicate that query"
                ),
            }
        ]
        if hl_reason:
            unavailable.append({"key": "extremes", "title": "New 252-bar extremes", "reason": hl_reason})

        # Headline index (from the stored index series, if one was supplied). The
        # change is computed from the last two stored closes — index_series does
        # not carry a percent_change column.
        index_info = None
        try:
            names = store.index_names()
            if names:
                idx = store.index_closes(names[0])
                if idx is not None and len(idx):
                    last = idx.iloc[-1]
                    prev = idx.iloc[-2] if len(idx) > 1 else None
                    change = (
                        round(float(last["close"]) - float(prev["close"]), 2)
                        if prev is not None
                        else None
                    )
                    pct = (
                        round(change / float(prev["close"]) * 100.0, 2)
                        if prev is not None and float(prev["close"])
                        else None
                    )
                    index_info = {
                        "name": names[0],
                        "date": str(pd.to_datetime(last["trading_date"]).date()),
                        "close": _f(last["close"]),
                        "change": change,
                        "change_pct": pct,
                    }
        except Exception:  # pragma: no cover - defensive
            index_info = None

        advancers = int((df["change_pct"] > 0).sum())
        decliners = int((df["change_pct"] < 0).sum())
        unchanged = int((df["change_pct"] == 0).sum())

        return {
            "as_of": as_of,
            "is_live": False,
            "freshness": (
                "delayed — computed from the most recent stored trading day, not a live feed"
            ),
            "index": index_info,
            "symbols": len(df),
            "names_available": False,
            "names_note": "security_master is empty in this build, so no company names are shown rather than guessed",
            "breadth": {"advancers": advancers, "decliners": decliners, "unchanged": unchanged},
            "totals": {
                "turnover": float(df["turnover"].fillna(0).sum()),
                "volume": float(df["volume"].fillna(0).sum()),
            },
            "groups": groups,
            "unavailable": unavailable,
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

    def _index_note(store: Any) -> str:
        """Data-driven index note: available once index_series is populated.

        The dashboard previously asserted indices were unavailable. That is
        only true while the store holds no series; once a supplied index file
        is loaded (B-10), saying "unavailable" would itself be wrong.
        """
        try:
            names = store.index_names()
        except Exception:  # pragma: no cover - defensive
            names = []
        if not names:
            return (
                "The stored dataset carries no historical index series yet "
                "(import a supplied index file to add one), so no index value is "
                "shown here; the live strip above shows the current index when a "
                "market source is connected."
            )
        row = store.query_one("SELECT MAX(trading_date) FROM index_series")
        latest = str(row[0]) if row and row[0] else "unknown"
        return (
            f"{len(names)} published index series loaded (latest {latest}); "
            "values come from the supplied index files, not a live feed."
        )

    # --------------------------------------------------------------- indices
    @app.get("/api/indices")
    def indices() -> dict[str, Any]:
        """Which published index series are stored, with their coverage.

        This consumes the historical index data imported for B-10. It is
        read-only: the values are the supplied *published* series, not a live
        feed, and the official NEPSE composite is named explicitly so the
        relative-strength benchmark can be identified.
        """
        store = get_store()
        names = store.index_names()
        series = []
        for name in names:
            row = store.query_one(
                """
                SELECT COUNT(*), MIN(trading_date), MAX(trading_date)
                FROM index_series
                WHERE index_name = ?
                """,
                (name,),
            )
            series.append(
                {
                    "name": name,
                    "rows": int(row[0]) if row and row[0] is not None else 0,
                    "first_date": str(row[1]) if row and row[1] else None,
                    "last_date": str(row[2]) if row and row[2] else None,
                }
            )
        return {
            "series": series,
            "count": len(series),
            "benchmark": NEPSE_COMPOSITE_INDEX,
            "benchmark_available": any(s["name"] == NEPSE_COMPOSITE_INDEX for s in series),
            "source": (
                "supplied published index files (blocker B-10); not a live feed "
                "and not the authenticated official API"
            ),
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/indices/{name}")
    def index_series(
        name: str,
        limit: int = Query(2000, ge=1, le=20000),
    ) -> dict[str, Any]:
        """One stored index series, date-ordered, newest last.

        A name with no stored series is a 404 with a stated reason, never an
        empty-but-successful response that could read as a real index.
        """
        store = get_store()
        df = store.index_closes(name)
        if df is None or df.empty:
            raise HTTPException(404, f"no stored index series named {name!r}")
        total = store.query_one("SELECT COUNT(*) FROM index_series WHERE index_name = ?", (name,))
        frame = df.tail(limit)
        points = [
            {"date": str(row.trading_date), "close": float(row.close)}
            for row in frame.itertuples(index=False)
        ]
        return {
            "name": name,
            "rows_total": int(total[0]) if total and total[0] is not None else len(points),
            "rows_returned": len(points),
            "first_date": points[0]["date"] if points else None,
            "last_date": points[-1]["date"] if points else None,
            "points": points,
            "source": (
                "supplied published index files (blocker B-10); not a live feed "
                "and not the authenticated official API"
            ),
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/indices/{name}/ohlc")
    def index_ohlc(
        name: str,
        limit: int = Query(2000, ge=1, le=20000),
        genuine_only: bool = Query(False, description="Return only rows with genuine (non-placeholder) OHLC"),
    ) -> dict[str, Any]:
        """Historical OHLC for a published index series (socrateai source).

        Returns OHLC bars where available. Rows with placeholder OHLC
        (O=H=L=C) are included but flagged with ohlc_status='placeholder'.
        Volume field is market-wide turnover in NPR, not share volume.
        """
        with get_conn() as conn:
            query = (
                "SELECT trading_date, open, high, low, close, volume, volume_type, "
                "ohlc_status, source FROM index_ohlc_history WHERE index_name = ?"
            )
            params = [name]
            if genuine_only:
                query += " AND ohlc_status = 'genuine'"
            query += " ORDER BY trading_date"
            rows = conn.execute(query, params).fetchall()
        if not rows:
            raise HTTPException(404, f"no historical OHLC for index {name!r}")
        frame_rows = rows[-limit:] if limit < len(rows) else rows
        bars = []
        for r in frame_rows:
            is_placeholder = (r[7] == "placeholder")
            bar = {
                "date": str(r[0]),
                "open": None if is_placeholder else (float(r[1]) if r[1] is not None else None),
                "high": None if is_placeholder else (float(r[2]) if r[2] is not None else None),
                "low": None if is_placeholder else (float(r[3]) if r[3] is not None else None),
                "close": float(r[4]),
                "volume": float(r[5]) if r[5] is not None else None,
                "volume_type": r[6],
                "ohlc_status": r[7],
            }
            bars.append(bar)
        genuine_count = sum(1 for r in rows if r[7] == "genuine")
        placeholder_count = sum(1 for r in rows if r[7] == "placeholder")
        invalid_count = sum(1 for r in rows if r[7] == "invalid")
        vol_count = sum(1 for r in rows if r[5] is not None)
        genuine_dates = [str(r[0]) for r in rows if r[7] == "genuine"]
        return {
            "name": name,
            "rows_total": len(rows),
            "rows_returned": len(bars),
            "first_date": bars[0]["date"] if bars else None,
            "last_date": bars[-1]["date"] if bars else None,
            "bars": bars,
            "genuine_ohlc_count": genuine_count,
            "placeholder_ohlc_count": placeholder_count,
            "invalid_ohlc_count": invalid_count,
            "genuine_first_date": genuine_dates[0] if genuine_dates else None,
            "genuine_last_date": genuine_dates[-1] if genuine_dates else None,
            "volume_rows": vol_count,
            "volume_type": "market-wide turnover in NPR (not share volume)",
            "source": "socrateai-official/nepse-open-data (MIT license)",
            "disclaimer": (
                "Historical OHLC from a community dataset derived from NEPSE "
                "published data. Rows before ~2017 have placeholder OHLC "
                "(O=H=L=C=close). Volume field is market-wide turnover in NPR. "
                "Not a live feed."
            ),
        }

    @app.get("/api/indices/{name}/structure")
    def index_structure(
        name: str,
        left: int = Query(DEFAULT_LEFT, ge=1, le=200),
        right: int = Query(DEFAULT_RIGHT, ge=1, le=200),
        min_prominence: float = Query(0.0, ge=0.0, le=1.0),
    ) -> dict[str, Any]:
        """Swing points and market structure for a published index series.

        Uses ONLY genuine OHLC observations from index_ohlc_history.
        Placeholder (O=H=L=C) and invalid rows are excluded. Data gaps
        between genuine observations are NOT bridged.
        """
        import numpy as np
        from datetime import datetime

        with get_conn() as conn:
            rows = conn.execute(
                "SELECT trading_date, open, high, low, close FROM index_ohlc_history "
                "WHERE index_name = ? AND ohlc_status = 'genuine' ORDER BY trading_date",
                (name,),
            ).fetchall()

        if not rows:
            raise HTTPException(404, f"no genuine OHLC history for index {name!r}")

        dates = [str(r[0]) for r in rows]
        highs = np.array([float(r[2]) for r in rows], dtype=float)
        lows = np.array([float(r[3]) for r in rows], dtype=float)
        closes = np.array([float(r[4]) for r in rows], dtype=float)

        gap_count = 0
        for i in range(1, len(dates)):
            d1 = datetime.strptime(dates[i - 1], "%Y-%m-%d").date()
            d2 = datetime.strptime(dates[i], "%Y-%m-%d").date()
            if (d2 - d1).days > 7:
                gap_count += 1

        try:
            swings = find_swings(highs, lows, left=left, right=right, min_prominence=min_prominence)
        except SwingError as exc:
            raise HTTPException(400, str(exc)) from exc

        structure_info = classify_structure(swings)
        breaks = find_breaks(swings, closes)
        equal_hl = detect_equal_highs_lows(swings)
        fvgs = detect_fvgs(highs.tolist(), lows.tolist())

        def stamp(row, idx_key="index"):
            i = row[idx_key]
            return {**row, "date": dates[i] if 0 <= i < len(dates) else None}

        return {
            "name": name,
            "method": "fractal pivot (unique extreme over left/right window)",
            "params": {"left": left, "right": right, "min_prominence": min_prominence},
            "data_quality": {
                "genuine_rows_used": len(rows),
                "data_gaps": gap_count,
                "consecutive": gap_count == 0,
                "note": (
                    "Swings computed from genuine OHLC rows only. "
                    "Placeholder and invalid rows excluded. "
                    "Data gaps between genuine observations are NOT bridged."
                ),
            },
            "counts": {
                "bars": int(len(rows)),
                "swings": len(swings),
                "swing_highs": structure_info["swing_highs"],
                "swing_lows": structure_info["swing_lows"],
            },
            "first_date": dates[0],
            "last_date": dates[-1],
            "swings": [
                {
                    **stamp(s.to_dict()),
                    "confirmed_date": (
                        dates[s.confirmed_index] if 0 <= s.confirmed_index < len(dates) else None
                    ),
                }
                for s in swings
            ],
            "labels": [stamp(row) for row in structure_info["labels"]],
            "trend": structure_info["trend"],
            "breaks": [stamp(row) for row in breaks],
            "equal_highs_lows": equal_hl,
            "fvgs": fvgs,
            "interpretation": "detected",
            "caveats": [
                "Detected turning points under fixed geometric rules, not validated "
                "patterns and not a prediction.",
                "A swing is knowable only at confirmed_index, right bars after the "
                "pivot bar; do not act on it before then.",
                "Swings use ONLY genuine OHLC observations. Placeholder (O=H=L=C) and "
                "invalid rows are excluded. Data gaps are NOT bridged.",
                "Prices are unadjusted for bonus/split issues.",
            ],
        }

    @app.get("/api/bars/{symbol}/relative-strength")
    def relative_strength(
        symbol: str,
        benchmark: str = Query(
            NEPSE_COMPOSITE_INDEX,
            description="stored index series to compare against (default: the official NEPSE composite)",
        ),
        window: int = Query(60, ge=2, le=2000),
        min_bars: int = Query(60, ge=2, le=2000),
        start: date | None = None,
        end: date | None = None,
        limit: int | None = Query(None, ge=2, le=20000),
        lookbacks: str | None = Query(
            None,
            description=(
                "optional comma-separated lookback list (e.g. '20,60,120,250'; at most "
                f"{MAX_LOOKBACKS} values, each 2..2000) to additionally receive a per-lookback "
                "multi-timeframe table computed from the same aligned series"
            ),
        ),
    ) -> dict[str, Any]:
        """Stock-versus-index relative strength, computed from stored history.

        The calculation is defined explicitly so it can be checked:

        * both series are keyed on ``trading_date`` and joined on dates present
          in **both** (an inner join — a date missing from either side is
          reported, never forward-filled);
        * the *ratio* is ``stock_close / benchmark_close`` rebased to 100 at the
          first aligned date inside the window (`stock/benchmark`-style relative
          strength — rising means the stock is outperforming);
        * the *excess return* is the stock's ``window``-bar close-to-close
          percentage return minus the benchmark's over the same aligned window.

        The benchmark defaults to the official NEPSE composite. No substitute
        index is used: an unknown or too-short benchmark series is reported as
        unavailable with a reason.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        upper = symbol.upper()
        store = get_store()
        try:
            tf_lookbacks = parse_lookbacks(lookbacks)
        except ValueError as exc:
            raise HTTPException(
                400,
                f"invalid lookbacks list: {exc} (example: lookbacks=20,60,120,250)",
            ) from exc
        bench_df = store.index_closes(benchmark)
        if bench_df is None or bench_df.empty:
            names = store.index_names()
            raise HTTPException(
                404,
                f"no stored index series named {benchmark!r}; stored: "
                + (", ".join(names) if names else "none (no index data is loaded)"),
            )

        df = store.get_bars(upper, end=end)
        if df.empty:
            raise HTTPException(404, f"no stored history for {upper}")
        if start is not None:
            df = df[df["trading_date"] >= pd.Timestamp(start)]
        stock_bars_total = int(len(df))

        stock = df[["trading_date", "close"]].rename(columns={"close": "stock"})
        bench = bench_df.rename(columns={"close": "bench"})
        bench["trading_date"] = pd.to_datetime(bench["trading_date"])
        stock["trading_date"] = pd.to_datetime(stock["trading_date"])
        if limit:
            stock = stock.tail(limit)

        merged = stock.merge(bench, on="trading_date", how="inner").dropna()
        merged = merged.sort_values("trading_date")
        only_stock = int(len(stock) - len(merged))
        only_bench = int(
            len(bench[bench["trading_date"] <= stock["trading_date"].max()]) - len(merged)
        )

        base = {
            "symbol": upper,
            "benchmark": benchmark,
            "window": window,
            "calculation": (
                "ratio = stock_close / benchmark_close rebased to 100 at the first "
                "aligned date; excess = stock window return − benchmark window return, "
                "over dates present in both series (inner join)"
            ),
            "source": (
                "stored price bars + supplied published index files; historical, not a live feed"
            ),
            "coverage": {
                "stock_bars": stock_bars_total,
                "benchmark_bars": int(len(bench)),
                "aligned_bars": int(len(merged)),
                "stock_dates_without_benchmark": only_stock,
                "benchmark_dates_without_stock": max(0, only_bench),
            },
            "first_date": str(merged["trading_date"].iloc[0].date()) if len(merged) else None,
            "last_date": str(merged["trading_date"].iloc[-1].date()) if len(merged) else None,
            "disclaimer": DISCLAIMER,
        }
        if tf_lookbacks:
            base["timeframes"] = timeframe_rows(merged, tf_lookbacks)
            base["timeframes_calculation"] = (
                "same formulas as the single window, applied at each requested "
                "lookback over the identical aligned date set; per-lookback "
                "availability is reported rather than shortened silently"
            )

        if len(merged) < max(2, min_bars):
            base.update(
                {
                    "available": False,
                    "unavailable_reason": (
                        f"only {len(merged)} dates are present in both {upper} and "
                        f"{benchmark}; at least {max(2, min_bars)} aligned bars are required "
                        "before a relative-strength comparison is shown"
                    ),
                    "ratio_points": [],
                    "benchmark_points": [],
                    "stock_return_pct": None,
                    "benchmark_return_pct": None,
                    "excess_return_pct": None,
                }
            )
            if tf_lookbacks:
                base["timeframes"] = timeframe_rows(merged, tf_lookbacks)
            return base

        m = merged.tail(max(window + 1, 2)).reset_index(drop=True)
        base_ratio = float(m["bench"].iloc[0])
        # Rebase the ratio line to 100 at the first aligned bar of the window so
        # the line reads as "relative performance since <date>".
        raw0 = float(m["stock"].iloc[0]) / base_ratio if base_ratio else None
        ratio_points = []
        if raw0:
            for r in m.itertuples(index=False):
                b = float(r.bench)
                if b == 0:
                    continue
                ratio_points.append(
                    {
                        "date": str(r.trading_date.date()),
                        "ratio": round(float(r.stock) / b / raw0 * 100.0, 4),
                        "stock": float(r.stock),
                        "benchmark": b,
                    }
                )
        window_ok = len(m) >= window + 1
        stock_ret = (
            float(m["stock"].iloc[-1] / m["stock"].iloc[-1 - window] - 1.0) * 100.0
            if window_ok
            else None
        )
        bench_ret = (
            float(m["bench"].iloc[-1] / m["bench"].iloc[-1 - window] - 1.0) * 100.0
            if window_ok
            else None
        )
        base.update(
            {
                "available": window_ok,
                "unavailable_reason": ""
                if window_ok
                else (
                    f"{len(m)} aligned bars cover less than the {window}-bar window; "
                    "the ratio series is shown but the window return is not computed"
                ),
                "window_bars_used": len(m),
                "base_benchmark_close": base_ratio,
                "base_ratio": round(raw0, 8) if raw0 else None,
                "ratio_points": ratio_points,
                "benchmark_points": [
                    {"date": str(r.trading_date.date()), "close": float(r.bench)}
                    for r in m.itertuples(index=False)
                ],
                "stock_return_pct": None if stock_ret is None else round(stock_ret, 4),
                "benchmark_return_pct": None if bench_ret is None else round(bench_ret, 4),
                "excess_return_pct": (
                    None
                    if stock_ret is None or bench_ret is None
                    else round(stock_ret - bench_ret, 4)
                ),
            }
        )
        return base

    # ---------------------------------------------------- gaps & breakouts
    @app.get("/api/bars/{symbol}/gaps")
    def gaps_endpoint(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = Query(None, ge=2, le=5000),
        atr_period: int = Query(14, ge=2, le=500),
        common_max_atr: float = Query(0.25, ge=0.0, le=5.0),
        big_min_atr: float = Query(0.75, ge=0.0, le=5.0),
    ) -> dict[str, Any]:
        """Session-to-session gaps with a rule-based scale class.

        The gap itself is a fact of stored bars (low entirely above the prior
        high or high entirely below the prior low); the class (common /
        runaway / breakaway / exhaustion) is a stated rule over ATR scale and
        trend context — a description of the shape, never a prediction. A
        closed-within-N-bars figure is computed post hoc and flagged as such.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        from megatool.ta.gaps import GapError, detect_gaps

        store = get_store()
        df = store.get_bars(symbol.upper(), start=start, end=end, limit=limit)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol.upper()}")
        try:
            gaps = detect_gaps(
                df["high"].to_numpy(float).tolist(),
                df["low"].to_numpy(float).tolist(),
                df["close"].to_numpy(float).tolist(),
                atr_period=atr_period,
                common_max_atr=common_max_atr,
                big_min_atr=big_min_atr,
            )
        except GapError as exc:
            raise HTTPException(400, str(exc)) from exc
        notes = [g for g in gaps if "data_note" in g]
        found = [g for g in gaps if "data_note" not in g]
        for g in found:
            g["date"] = str(df["trading_date"].iloc[g["index"]].date())
        return {
            "symbol": symbol.upper(),
            "first_date": str(df["trading_date"].iloc[0].date()),
            "last_date": str(df["trading_date"].iloc[-1].date()),
            "gaps": found,
            "notes": [n["data_note"] for n in notes],
            "count": len(found),
            "source": (
                "stored daily bars; gap classes are charting-literature rules "
                "describing the shape — not predictions"
            ),
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/bars/{symbol}/breakouts")
    def breakouts_endpoint(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = Query(None, ge=25, le=5000),
        window: int = Query(20, ge=2, le=500),
        min_frac: float = Query(0.005, gt=0.0, lt=0.5),
        confirm_bars: int = Query(3, ge=1, le=50),
    ) -> dict[str, Any]:
        """Breakouts beyond a rolling extreme, tagged true/false/unconfirmed.

        Level = the prior ``window`` bars' high (upside) or low (downside);
        a breakout is *false* when a later close comes back across it within
        ``confirm_bars`` sessions; a breakout not yet confirmable at the end
        of the window is reported unconfirmed rather than counted as true.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        from megatool.ta.gaps import GapError, detect_false_breakouts

        store = get_store()
        df = store.get_bars(symbol.upper(), start=start, end=end, limit=limit)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol.upper()}")
        try:
            found = detect_false_breakouts(
                df["high"].to_numpy(float).tolist(),
                df["low"].to_numpy(float).tolist(),
                df["close"].to_numpy(float).tolist(),
                window=window,
                min_frac=min_frac,
                confirm_bars=confirm_bars,
            )
        except GapError as exc:
            raise HTTPException(400, str(exc)) from exc
        for r in found:
            r["date"] = str(df["trading_date"].iloc[r["index"]].date())
        return {
            "symbol": symbol.upper(),
            "first_date": str(df["trading_date"].iloc[0].date()),
            "last_date": str(df["trading_date"].iloc[-1].date()),
            "breakouts": found,
            "count": len(found),
            "source": (
                "stored daily bars; true/false breakouts are classified post "
                "hoc over this window and are not tradable signals"
            ),
            "disclaimer": DISCLAIMER,
        }

    # ------------------------------------------------------ trailing stops
    @app.get("/api/bars/{symbol}/trailing-stop")
    def trailing_stop_endpoint(
        symbol: str,
        method: str = Query(
            "chandelier",
            description="chandelier (HH(N) − k·ATR), swing (lowest low of M bars) or pct (peak close − pct%)",
            pattern="^(chandelier|swing|pct)$",
        ),
        atr_period: int = Query(22, ge=1, le=500),
        atr_multiple: float = Query(3.0, gt=0.0, le=20.0),
        swing_bars: int = Query(10, ge=2, le=500),
        pct: float = Query(8.0, gt=0.0, le=90.0),
        start: date | None = None,
        end: date | None = None,
        limit: int | None = Query(None, ge=2, le=5000),
    ) -> dict[str, Any]:
        """Ratcheted trailing-stop series for an open long, from stored bars.

        The stop is recomputed at every closed bar from data through that bar
        only; it moves up never down; an exit needs a later bar's low at the
        stop. No exit suggestion, no execution — a research overlay.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        from megatool.ta.trailing import TrailingError, trailing_stop

        store = get_store()
        df = store.get_bars(symbol.upper(), start=start, end=end, limit=limit)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol.upper()}")
        try:
            result = trailing_stop(
                df["high"].to_numpy(float).tolist(),
                df["low"].to_numpy(float).tolist(),
                df["close"].to_numpy(float).tolist(),
                method,
                atr_period=atr_period,
                atr_multiple=atr_multiple,
                swing_bars=swing_bars,
                pct=pct,
            )
        except TrailingError as exc:
            raise HTTPException(400, str(exc)) from exc
        dates = [str(d.date()) for d in df["trading_date"]]
        result["dates"] = dates[: result["bars_used"]]
        result["stopped"] = result["exited_index"] is not None
        return {
            "symbol": symbol.upper(),
            "first_date": str(df["trading_date"].iloc[0].date()),
            "last_date": str(df["trading_date"].iloc[-1].date()),
            "result": result,
            "source": (
                "stored daily bars; a ratcheted stop overlay computed post hoc — "
                "not a forecast and not an execution plan"
            ),
            "disclaimer": DISCLAIMER,
        }

    # ------------------------------------------------------ volume profile
    @app.get("/api/bars/{symbol}/volume-profile")
    def volume_profile_endpoint(
        symbol: str,
        bins: int = Query(48, ge=10, le=200),
        start: date | None = None,
        end: date | None = None,
        limit: int | None = Query(None, ge=2, le=5000),
    ) -> dict[str, Any]:
        """Daily-bar volume profile over the stored history (optionally limited).

        A deterministic exchange-free histogram: each session's volume is
        spread across the price bins its low→high range touches, then POC, the
        70% value area and strict HVN/LVN nodes are derived. Because only
        daily bars are stored, the split across a session's range is an
        allocation model — the response says so plainly and never presents the
        landmarks as intraday observations or predictions.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        from megatool.ta.profile import ProfileError, volume_profile

        store = get_store()
        df = store.get_bars(symbol.upper(), start=start, end=end, limit=limit)
        if df.empty:
            raise HTTPException(404, f"no stored history for {symbol.upper()}")
        highs = df["high"].to_numpy(float).tolist()
        lows = df["low"].to_numpy(float).tolist()
        volumes = df["volume"].to_numpy(float).tolist()
        try:
            result = volume_profile(highs, lows, volumes, bins=bins)
        except ProfileError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {
            "symbol": symbol.upper(),
            "sessions_used": int(len(df)),
            "first_date": str(df["trading_date"].iloc[0].date()),
            "last_date": str(df["trading_date"].iloc[-1].date()),
            "profile": result,
            "source": (
                "stored daily bars; profile over past distribution only — "
                "not a forecast and not intraday detail"
            ),
            "disclaimer": DISCLAIMER,
        }

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

    # ------------------------------------------------------ market regime
    @app.get("/api/regime")
    def regime() -> dict[str, Any]:
        """Current market regime labels computed causally from stored closes.

        The equal-weighted proxy is NOT the official NEPSE index (blocker
        B-10); it is derived from the stored universe and labelled as a proxy.
        """
        from megatool.regime import detect_regimes

        store = get_store()
        closes = store.all_closes()
        result = detect_regimes(closes)
        payload = result.to_dict()
        payload["disclaimer"] = DISCLAIMER
        return payload

    @app.get("/api/regime/history")
    def regime_history(limit: int = Query(250, ge=1, le=2000)) -> dict[str, Any]:
        """Recent per-date regime labels (same causal computation)."""
        from megatool.regime import detect_regimes

        store = get_store()
        closes = store.all_closes()
        result = detect_regimes(closes, limit=limit)
        payload = result.to_dict()
        payload["disclaimer"] = DISCLAIMER
        return payload

    # ----------------------------------------------------------------- alerts
    @app.post("/api/alerts/evaluate")
    def alerts_evaluate(body: dict[str, Any]) -> dict[str, Any]:
        """Evaluate alert conditions against stored bars; record first firings.

        Each condition fires at most once per (condition, symbol) until the
        owner clears the history — the schema's UNIQUE(alert_key, symbol)
        makes a poll cycle incapable of duplicating an alert.
        """
        from megatool.alerts import evaluate_conditions

        conditions = body.get("conditions") or []
        if not isinstance(conditions, list) or not conditions:
            raise HTTPException(400, "conditions must be a non-empty list")
        with get_conn() as conn:
            result = evaluate_conditions(get_store(), conn, conditions)
        payload = result.to_dict()
        payload["disclaimer"] = DISCLAIMER
        return payload

    @app.post("/api/alerts/acknowledge")
    def alerts_acknowledge(body: dict[str, Any]) -> dict[str, Any]:
        """Acknowledge alerts so they stop being flagged as unseen.

        Does not delete history and does not change cooldowns: acknowledging an
        alert can never cause it to re-fire. Pass ``{"alert_ids": [1, 2]}`` or
        ``{"all": true}``.
        """
        from megatool.alerts import acknowledge_alerts

        ids = body.get("alert_ids")
        ack_all = bool(body.get("all"))
        if not ack_all and not isinstance(ids, list):
            raise HTTPException(400, "pass {'alert_ids': [...]} or {'all': true}")
        if isinstance(ids, list):
            try:
                ids = [int(i) for i in ids]
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "alert_ids must be a list of integers") from exc
        with get_conn() as conn:
            changed = acknowledge_alerts(conn, alert_ids=ids, all_alerts=ack_all)
        return {"acknowledged": changed, "disclaimer": DISCLAIMER}

    @app.get("/api/alerts/history")
    def alerts_history(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
        from megatool.alerts import list_alerts

        with get_conn() as conn:
            alerts = list_alerts(conn, limit)
        return {"alerts": alerts, "disclaimer": DISCLAIMER}

    @app.delete("/api/alerts/clear")
    def alerts_clear() -> dict[str, Any]:
        """Clear alert history so conditions can re-arm (owner-invoked)."""
        from megatool.alerts import clear_alerts

        with get_conn() as conn:
            cleared = clear_alerts(conn)
        return {"cleared": cleared, "disclaimer": DISCLAIMER}

    # -------------------------------------------------- timeframe aggregates
    # Weekly and monthly bars are aggregated from the stored daily bars using
    # calendar periods (past-only, no future data). They share the daily bars
    # response envelope so one frontend loader can render any timeframe. The
    # earlier bare-list contract returned raw pandas rows keyed ``trading_date``
    # with no ``symbol``/``count``/``bars`` wrapper, which ``loadChart`` cannot
    # consume -- concrete evidence that the old contract was incorrect.
    def _timeframe_bars(symbol: str) -> tuple[pd.DataFrame, str]:
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        upper = symbol.upper()
        df = get_store().get_bars(upper)
        if df is None or df.empty:
            raise HTTPException(404, f"no stored history for {upper}")
        return df, upper

    def _timeframe_payload(
        upper: str, df: pd.DataFrame, agg: pd.DataFrame, timeframe: str
    ) -> dict[str, Any]:
        if agg.empty:
            raise HTTPException(404, f"no plottable history for {upper}")
        return {
            "symbol": upper,
            "count": len(agg),
            "timeframe": timeframe,
            "sources": sorted(set(df["source"].dropna())) if "source" in df.columns else [],
            "first_date": str(agg["trading_date"].min().date()),
            "last_date": str(agg["trading_date"].max().date()),
            "adjustment_status": sorted(set(df["adjustment_status"].dropna()))
            if "adjustment_status" in df.columns
            else [],
            "bars": _bars_payload(agg),
        }

    @app.get("/api/bars/{symbol}/weekly")
    def weekly_aggregate(
        symbol: str, limit: int | None = Query(None, ge=1, le=5000)
    ) -> dict[str, Any]:
        """Weekly OHLCV aggregated from daily bars, grouped by calendar week.

        A week is built only from sessions already stored; incomplete weeks are
        simply the most recent group, never padded or fabricated.
        """
        df, upper = _timeframe_bars(symbol)
        agg = aggregate_daily_to_weekly(df)
        if limit is not None and not agg.empty:
            agg = agg.tail(limit)
        return _timeframe_payload(upper, df, agg, "weekly")

    @app.get("/api/bars/{symbol}/monthly")
    def monthly_aggregate(
        symbol: str, limit: int | None = Query(None, ge=1, le=5000)
    ) -> dict[str, Any]:
        """Monthly OHLCV aggregated from daily bars, grouped by calendar month."""
        df, upper = _timeframe_bars(symbol)
        agg = aggregate_daily_to_monthly(df)
        if limit is not None and not agg.empty:
            agg = agg.tail(limit)
        return _timeframe_payload(upper, df, agg, "monthly")

    @app.get("/api/bars/{symbol}/elliott")
    def elliott_aggregate(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = Query(None, ge=1, le=20000),
    ) -> dict[str, Any]:
        """Bounded Elliott-wave candidates derived from confirmed swings.

        ``find_swings`` needs only the high and low arrays. Output is
        ``CANDIDATE_ONLY``: heuristic counts with an explicit uncertainty note,
        never a guaranteed forecast. A malformed symbol is a 400; missing or
        too-short history is a 404. Insufficient confirmed swings is a normal
        ``INSUFFICIENT_EVIDENCE`` result (not an error).

        ``start``/``end``/``limit`` select the historical analysis window; the
        window is applied **before** swings are found, so the count is computed
        only from bars the researcher chose. Each candidate reports
        ``swings_used`` so the client can map it back to the same confirmed
        pivots it drew from ``/structure`` over the same window.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        upper = symbol.upper()
        df = get_store().get_bars(upper, start=start, end=end, limit=limit)
        if df is None or len(df) < 3:
            raise HTTPException(404, f"no or insufficient history for {upper}")
        try:
            swings = find_swings(
                df["high"].to_numpy(float),
                df["low"].to_numpy(float),
                left=DEFAULT_LEFT,
                right=DEFAULT_RIGHT,
            )
        except SwingError as exc:
            raise HTTPException(400, str(exc)) from exc
        result = analyze_elliott_extended(swings)
        dates = [str(d.date()) for d in df["trading_date"]]
        # The engine counts only *confirmed* swings (look-ahead rule), so the
        # same filter must be applied here or the pivots would not line up.
        confirmed = [s for s in swings if getattr(s, "confirmed", True)]

        def _pivots(count: int) -> list[dict[str, Any]]:
            """The exact confirmed pivots the engine used — with their dates.

            ``analyze_elliott_extended`` builds each candidate from the earliest
            ``count`` confirmed swings, so the identical slice is returned here.
            Shipping the pivots means the chart draws the engine's real turning
            points instead of re-deriving them from a second request that could
            disagree on the window.
            """
            out: list[dict[str, Any]] = []
            for s in confirmed[:count]:
                row = s.to_dict()
                i = row.get("index")
                if isinstance(i, int) and 0 <= i < len(dates):
                    row["date"] = dates[i]
                ci = s.confirmed_index
                row["confirmed_date"] = dates[ci] if 0 <= ci < len(dates) else None
                out.append(row)
            return out

        candidates: list[dict[str, Any]] = []
        for cand in result.get("candidates", []):
            cand = dict(cand)
            cand["pivots"] = _pivots(int(cand.get("swings_used") or 0))
            candidates.append(cand)

        return {
            "symbol": upper,
            "status": result["status"],
            "method": result.get("method"),
            "uncertainty": result.get("uncertainty", ""),
            "evidence": result.get("evidence", ""),
            "swings_considered": result.get("swings_considered", len(swings)),
            "candidates": candidates,
            "invalidation_conditions": result.get("invalidation_conditions"),
            "message": result.get("message"),
            "renderable": len(candidates),
            "window": {
                "bars": int(len(df)),
                "first_date": dates[0] if dates else None,
                "last_date": dates[-1] if dates else None,
                "confirmed_swings": len(confirmed),
            },
            "minimum": {
                "confirmed_swings_for_3_wave": 3,
                "confirmed_swings_for_5_wave": 5,
                "note": (
                    "Counts are built from confirmed swing pivots, not bar count: "
                    "a short window can still qualify if it holds enough pivots, "
                    "and a long one cannot if it does not."
                ),
            },
        }

    @app.get("/api/bars/{symbol}/harmonic")
    def harmonic_candidates(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = Query(None, ge=1, le=20000),
        slack: float = Query(0.0, ge=0.0, le=0.5),
        patterns: str | None = Query(
            None, description="comma-separated harmonic names to keep (omit for all)"
        ),
    ) -> dict[str, Any]:
        """Harmonic XABCD pattern candidates from confirmed swings (§7).

        Patterns tested: Gartley, Butterfly, Bat, Crab, Cypher — published
        ratio bands defined in ``megatool.ta.harmonic``. ``status`` is
        ``CANDIDATE_ONLY`` (matched), ``NO_MATCH`` (measurable windows, no
        band set matched) or ``INSUFFICIENT_EVIDENCE`` (<5 confirmed swings
        or degenerate legs). Matches are candidates with evidence and an
        invalidation level, never asserted signals. A malformed symbol is a
        400; missing or too-short history a 404.

        ``start``/``end``/``limit`` select the window; ``slack`` widens every
        published band symmetrically (0 = the published ratios only); and
        ``patterns`` restricts detection to a subset of the catalogue, so a
        researcher can ask "Gartley and Bat only" and see exactly what that
        answered. An unknown pattern name is a 400.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        upper = symbol.upper()
        df = get_store().get_bars(upper, start=start, end=end, limit=limit)
        if df is None or len(df) < 3:
            raise HTTPException(404, f"no or insufficient history for {upper}")

        specs = HARMONIC_SPECS
        if patterns is not None:
            wanted = [p.strip().lower() for p in patterns.split(",") if p.strip()]
            by_name = {s.name.lower(): s for s in HARMONIC_SPECS}
            unknown = [p for p in wanted if p not in by_name]
            if unknown:
                raise HTTPException(
                    400, f"unknown harmonic pattern(s): {', '.join(sorted(set(unknown)))}"
                )
            specs = tuple(by_name[p] for p in wanted)

        try:
            swings = find_swings(
                df["high"].to_numpy(float),
                df["low"].to_numpy(float),
                left=DEFAULT_LEFT,
                right=DEFAULT_RIGHT,
            )
        except SwingError as exc:
            raise HTTPException(400, str(exc)) from exc
        result = analyze_harmonic(swings, slack=slack, specs=specs)
        dates = [str(d.date()) for d in df["trading_date"]]

        def _with_dates(cand: dict[str, Any]) -> dict[str, Any]:
            """Attach the bar date to every XABCD point, in the engine's own
            order. The client then draws the exact pivots the detector matched
            instead of mapping raw bar indexes through a second bars request."""
            c = dict(cand)
            pts: dict[str, Any] = {}
            for key, point in (c.get("points") or {}).items():
                p = dict(point)
                i = p.get("index")
                if isinstance(i, int) and 0 <= i < len(dates):
                    p["date"] = dates[i]
                pts[key] = p
            c["points"] = pts
            c["pivots"] = [pts[k] for k in ("X", "A", "B", "C", "D") if k in pts]
            return c

        candidates = [_with_dates(c) for c in result.get("candidates", [])]
        return {
            "symbol": upper,
            "status": result["status"],
            "method": result.get("method"),
            "uncertainty": result.get("uncertainty", ""),
            "evidence": result.get("evidence", ""),
            "swings_considered": result.get("swings_considered", len(swings)),
            "windows_tested": result.get("windows_tested", 0),
            "patterns_tested": result.get("patterns_tested", []),
            "catalogue": [s.name for s in HARMONIC_SPECS],
            "slack": float(slack),
            "candidates": candidates,
            "message": result.get("message"),
            "renderable": len(candidates),
            "window": {
                "bars": int(len(df)),
                "first_date": dates[0] if dates else None,
                "last_date": dates[-1] if dates else None,
            },
            "minimum": {
                "confirmed_swings": 5,
                "note": (
                    "Each test window needs five consecutive confirmed pivots. "
                    "A short bar range is not itself a failure — it simply "
                    "contains fewer windows, so 'no match' may mean 'not enough "
                    "structure tested yet' rather than 'no pattern exists'."
                ),
            },
        }

    @app.get("/api/bars/{symbol}/patterns")
    def chart_patterns(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        level_tol: float = Query(0.035, ge=0.0, le=0.5),
        min_bars: int = Query(60, ge=20, le=2000),
        channel_period: int = Query(20, ge=5, le=200),
        patterns: str | None = Query(
            None, description="comma-separated chart-pattern names to keep (omit for all)"
        ),
    ) -> dict[str, Any]:
        """Rule-based chart-pattern detections for one symbol (§5.3).

        Patterns are geometric matches over confirmed swing pivots
        (:mod:`megatool.ta.swings`), so this endpoint and the structure,
        Fibonacci and harmonic endpoints agree on what a turning point is.

        Every pattern is **descriptive**: it reports the pivots, a documented
        rule set, a symmetry-based quality score and a confirmation state.
        ``status`` is ``confirmed`` only when price has already closed beyond
        the pattern's trigger within the stored history. Nothing here is a
        prediction or a trade signal. Too little history returns
        ``available=false`` with a reason rather than an empty list.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        upper = symbol.upper()
        df = get_store().get_bars(upper, start=start, end=end, limit=limit)
        if df is None or df.empty:
            raise HTTPException(404, f"no stored history for {upper}")
        dates = [str(d)[:10] for d in df["trading_date"]]
        cfg = PatternConfig(level_tol=level_tol, min_bars=min_bars, channel_period=channel_period)
        try:
            result = detect_chart_patterns(
                df["high"].to_numpy(float),
                df["low"].to_numpy(float),
                df["close"].to_numpy(float),
                dates=dates,
                config=cfg,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        wanted: list[str] | None = None
        if patterns is not None:
            wanted = [p.strip() for p in patterns.split(",") if p.strip()]
            unknown = [p for p in wanted if p not in PATTERN_TYPES]
            if unknown:
                raise HTTPException(
                    400, f"unknown chart pattern(s): {', '.join(sorted(set(unknown)))}"
                )
        found = result["patterns"]
        if wanted is not None:
            found = [p for p in found if p["pattern"] in wanted]

        return {
            "symbol": upper,
            "as_of": dates[-1] if dates else None,
            "available": result["available"],
            "unavailable_reason": result["unavailable_reason"],
            "patterns": found,
            "parameters": result["parameters"],
            "catalogue": PATTERN_TYPES,
            "notes": result["notes"],
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/bars/{symbol}/candles")
    def candlestick_patterns(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        patterns: str | None = Query(
            None, description="comma-separated pattern names to keep (omit for all)"
        ),
        trend_bars: int = Query(3, ge=1, le=50),
        require_prior_trend: bool = Query(True),
    ) -> dict[str, Any]:
        """Candlestick formations for one symbol (spec §8).

        Single-, two- and three-candle shapes found under documented geometric
        rules (:mod:`megatool.ta.candles`). Each result is a **DETECTED**
        candidate — the engine implements **no** confirmation rule, so nothing
        here is a reversal signal or a forecast. A malformed symbol or an
        unknown pattern name is a 400; missing history is a 404.

        Bars whose OHLC is internally impossible (open/close outside
        ``[low, high]``, or ``high < low``) are excluded and counted, and
        detection runs only on maximal runs of self-consistent bars, so a
        three-candle pattern can never "span" a gap that never traded. The
        stored records are never modified.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        upper = symbol.upper()
        df = get_store().get_bars(upper, start=start, end=end, limit=limit)
        if df is None or df.empty:
            raise HTTPException(404, f"no stored history for {upper}")

        wanted: list[str] | None = None
        if patterns is not None:
            wanted = [p.strip() for p in patterns.split(",") if p.strip()]
            unknown = [p for p in wanted if p not in CANDLE_PATTERN_TYPES]
            if unknown:
                raise HTTPException(
                    400,
                    f"unknown candlestick pattern(s): {', '.join(sorted(set(unknown)))}",
                )

        dates = [str(d)[:10] for d in df["trading_date"]]
        op = pd.to_numeric(df["open"], errors="coerce").to_numpy(float)
        hi = df["high"].to_numpy(float)
        lo = df["low"].to_numpy(float)
        cl = df["close"].to_numpy(float)

        # A stored row that cannot be a real candle is excluded, never fixed.
        valid = (
            np.isfinite(op)
            & np.isfinite(hi)
            & np.isfinite(lo)
            & np.isfinite(cl)
            & (hi >= np.maximum(op, cl))
            & (lo <= np.minimum(op, cl))
            & (hi >= lo)
        )
        invalid = int((~valid).sum())

        params = CandleParams(trend_bars=trend_bars, require_prior_trend=require_prior_trend)
        rows: list[dict[str, Any]] = []
        skipped_segments = 0
        i = 0
        n = len(valid)
        while i < n:
            if not valid[i]:
                i += 1
                continue
            j = i
            while j < n and valid[j]:
                j += 1
            if j - i >= 3:  # the engine needs three bars
                try:
                    found = detect_candle_patterns(
                        op[i:j],
                        hi[i:j],
                        lo[i:j],
                        cl[i:j],
                        params=params,
                        dates=dates[i:j],
                    )
                except CandleError:
                    skipped_segments += 1
                else:
                    for p in found:
                        row = p.to_dict()
                        row["index"] = i + int(row["index"])
                        row["date"] = dates[row["index"]] if row["index"] < len(dates) else None
                        rows.append(row)
            i = j

        rows.sort(key=lambda r: (int(r["index"]), str(r["name"])))
        if wanted:
            keep = set(wanted)
            rows = [r for r in rows if r["name"] in keep]
        for r in rows:
            # Chart hint: a bearish shape marks above the bar, everything else
            # below. Presentation only — it is not a directional signal.
            r["marker_position"] = "aboveBar" if r["direction"] == "bearish" else "belowBar"

        return {
            "symbol": upper,
            "as_of": dates[-1] if dates else None,
            "bars": len(df),
            "bars_excluded_invalid_ohlc": invalid,
            "segments_skipped": skipped_segments,
            "count": len(rows),
            "patterns": rows,
            "catalogue": list(CANDLE_PATTERN_TYPES),
            "parameters": {"trend_bars": trend_bars, "require_prior_trend": require_prior_trend},
            "notes": [
                "DETECTED by explicit geometric rules — a match is not a confirmed "
                "reversal and not a forecast.",
                "No confirmation rule is implemented; `confirmed` is always null.",
            ],
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/bars/{symbol}/statistics")
    def bar_statistics(
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        periods_per_year: int = Query(240, ge=1, le=1000),
        risk_free_annual: float = Query(0.0, ge=-1.0, le=1.0),
    ) -> dict[str, Any]:
        """Descriptive and risk statistics for one symbol's close series (§16).

        Undefined metrics are ``null`` (never NaN, never invented). The
        annualisation convention and the risk-free rate are stated in the
        response so a reader can reproduce the numbers.
        """
        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        upper = symbol.upper()
        df = get_store().get_bars(upper, start=start, end=end, limit=limit)
        if df is None or df.empty:
            raise HTTPException(404, f"no stored history for {upper}")
        close = df["close"].to_numpy(float)
        returns = close[1:] / close[:-1] - 1.0 if close.size > 1 else np.array([])
        return {
            "symbol": upper,
            "bars": int(close.size),
            "first_date": str(df["trading_date"].iloc[0])[:10],
            "last_date": str(df["trading_date"].iloc[-1])[:10],
            "price": _stats_mod.descriptive(close),
            "returns": _stats_mod.return_statistics(
                close,
                periods_per_year=periods_per_year,
                risk_free_annual=risk_free_annual,
            ),
            "return_series": _stats_mod.descriptive(returns),
            "assumptions": {
                "periods_per_year": periods_per_year,
                "risk_free_annual": risk_free_annual,
                "note": "Annualisation is a stated convention (240 NEPSE trading days), "
                "not a measured fact.",
            },
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/stats/correlation")
    def stats_correlation(
        symbols: str = Query(..., help="Comma-separated symbols, 2-25 of them."),
        method: str = Query("pearson", pattern="^(pearson|spearman)$"),
        period: int = Query(120, ge=10, le=2000),
    ) -> dict[str, Any]:
        """Pairwise correlation matrix across stored close series (§18.1).

        Series are aligned on the shortest common length, then pairwise-complete
        (each cell uses only points finite in both symbols and reports its own
        sample size). Correlation is a descriptive statistic between two price
        paths; it is not causation and is not a trading signal.
        """
        names = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if len(names) < 2:
            raise HTTPException(400, "at least two symbols are required")
        if len(names) > 25:
            raise HTTPException(400, "at most 25 symbols are supported")
        names = list(dict.fromkeys(names))
        store = get_store()
        series: dict[str, Any] = {}
        notes: dict[str, str] = {}
        for name in names:
            df = store.get_bars(name, limit=period)
            if df is None or len(df) < 10:
                notes[name] = "insufficient stored history (<10 bars)"
                continue
            series[name] = df["close"].to_numpy(float)
        if len(series) < 2:
            raise HTTPException(404, "fewer than two symbols have usable history")
        matrix = _stats_mod.correlation_matrix(series, method=method)
        return {
            "method": method,
            "period": period,
            "included": list(series.keys()),
            "excluded": notes,
            "common_bars": matrix["n"],
            "symbols": matrix["symbols"],
            "matrix": matrix["matrix"],
            "pair_n": matrix["pair_n"],
            "disclaimer": DISCLAIMER,
        }

    # ------------------------------------------------------------------
    # Unified searchable catalogue (scanners / algorithms / fundamentals)
    # ------------------------------------------------------------------
    from megatool import catalog as _catalog

    @app.get("/api/catalog/summary")
    def catalog_summary() -> dict[str, Any]:
        return _catalog.catalog_summary()

    @app.get("/api/catalog/{kind}")
    def catalog_kind(kind: str, q: str = "", category: str = "all") -> dict[str, Any]:
        if kind not in ("scanner", "algorithm", "fundamental"):
            raise HTTPException(404, f"unknown catalogue kind {kind!r}")
        tools = _catalog.search(kind, q, category)
        return {
            "kind": kind,
            "query": q,
            "category": category,
            "categories": _catalog.categories(kind),
            "total": len(_catalog.all_tools(kind)),
            "matched": len(tools),
            "tools": tools,
        }

    @app.get("/api/catalog/tool/{tool_id:path}")
    def catalog_tool(tool_id: str) -> dict[str, Any]:
        tool = _catalog.get_tool(tool_id)
        if tool is None:
            raise HTTPException(404, f"unknown tool {tool_id!r}")
        return tool

    @app.post("/api/analysis/run")
    def analysis_run(req: PydanticAnalysisRun) -> dict[str, Any]:
        params = dict(req.params or {})
        if req.symbol is not None:
            params.setdefault("symbol", req.symbol.upper())
        if req.symbols is not None:
            params["symbols"] = [s.upper() for s in req.symbols]
        try:
            out = _catalog.run_analysis(req.fn, **params)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, f"analysis failed: {exc}") from exc
        if isinstance(out, dict):
            out.setdefault("disclaimer", DISCLAIMER)
        return {"fn": req.fn, "result": out}

    @app.post("/api/fundamental/run")
    def fundamental_run(req: PydanticFundamentalRun) -> dict[str, Any]:
        try:
            out = _catalog.run_fundamental(req.fn, req.symbol)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, f"fundamental tool failed: {exc}") from exc
        out.setdefault("disclaimer", DISCLAIMER)
        return out

    # ------------------------------------------------- data-source reconciliation
    @app.get("/api/reconciliation/datasets")
    def reconciliation_datasets() -> dict[str, Any]:
        from megatool import reconcile

        return reconcile.inventory(get_store())

    @app.get("/api/reconciliation/profile")
    def reconciliation_profile(dataset: str) -> dict[str, Any]:
        from megatool import reconcile

        try:
            return reconcile.profile(dataset, get_store())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/reconciliation/run")
    def reconciliation_run(req: PydanticReconcileRun) -> dict[str, Any]:
        from megatool import reconcile

        try:
            out = reconcile.run(req.dataset, tolerance=req.tolerance, store=get_store())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        out["disclaimer"] = DISCLAIMER
        return out

    @app.post("/api/reconciliation/resolve")
    def reconciliation_resolve(req: PydanticReconcileResolve) -> dict[str, Any]:
        from megatool import reconcile

        try:
            return reconcile.resolve(
                dataset=req.dataset, finding_key=req.finding_key,
                classification=req.classification, resolution=req.resolution,
                chosen_source=req.chosen_source, note=req.note, actor=req.actor,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/reconciliation/history")
    def reconciliation_history(dataset: str | None = None, limit: int = 100) -> dict[str, Any]:
        from megatool import reconcile

        return reconcile.history(dataset=dataset, limit=limit)

    # ------------------------------------------------------ calculation snapshots
    @app.get("/api/snapshots")
    def snapshots_list(feature: str | None = None, limit: int = 100) -> dict[str, Any]:
        from megatool import snapshots

        return {"snapshots": snapshots.list_snapshots(feature=feature, limit=limit)}

    @app.get("/api/snapshots/compare")
    def snapshots_compare(a: str, b: str) -> dict[str, Any]:
        from megatool import snapshots

        try:
            return snapshots.compare(a, b)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/snapshots/capture")
    def snapshots_capture(req: PydanticSnapshotCapture) -> dict[str, Any]:
        from megatool import snapshots

        try:
            return snapshots.capture(req.feature, req.params or {}, store=get_store())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/snapshots")
    def snapshots_create(req: PydanticSnapshotCreate) -> dict[str, Any]:
        from megatool import snapshots

        try:
            return snapshots.create(
                feature=req.feature, params=req.params or {}, results=req.results,
                universe=req.universe, date_range=req.date_range,
                source_ids=req.source_ids, data_cutoff=req.data_cutoff,
                benchmark=req.benchmark, costs=req.costs, seed=req.seed,
                warnings=req.warnings, data_quality=req.data_quality,
                limitations=req.limitations, required=req.required, missing=req.missing,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/snapshots/{snapshot_id}")
    def snapshots_get(snapshot_id: str) -> dict[str, Any]:
        from megatool import snapshots

        snap = snapshots.get_snapshot(snapshot_id)
        if snap is None:
            raise HTTPException(404, f"unknown snapshot {snapshot_id!r}")
        return snap

    @app.post("/api/snapshots/{snapshot_id}/rerun")
    def snapshots_rerun(snapshot_id: str) -> dict[str, Any]:
        from megatool import snapshots

        try:
            return snapshots.rerun(snapshot_id, store=get_store())
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    # ------------------------------------------------------------- research desk
    @app.get("/api/research-desk/evidence")
    def research_evidence(symbol: str) -> dict[str, Any]:
        from megatool import research_desk

        out = research_desk.build_evidence(symbol, store=get_store())
        out["disclaimer"] = DISCLAIMER
        return out

    @app.post("/api/research-desk/run")
    def research_run(req: PydanticResearchRun) -> dict[str, Any]:
        from megatool import research_desk

        out = research_desk.run_research(
            req.question, req.symbol, provider=req.provider,
            store=get_store(), max_tokens=req.max_tokens,
        )
        out["disclaimer"] = DISCLAIMER
        return out

    @app.post("/api/research-desk/review")
    def research_review(req: PydanticResearchReview) -> dict[str, Any]:
        from megatool import research_desk

        evidence = research_desk.build_evidence(req.symbol, store=get_store())
        return {"review": research_desk.skeptical_review(req.text, evidence),
                "evidence": evidence}

    @app.get("/api/research-desk/history")
    def research_history(limit: int = 50) -> dict[str, Any]:
        from megatool import research_desk

        return {"runs": research_desk.history(limit=limit)}

    # ------------------------------------------------------- natural-language query
    @app.post("/api/query/run")
    def query_run(req: PydanticNlQuery) -> dict[str, Any]:
        from megatool import nlquery

        out = nlquery.run(req.question, store=get_store())
        out["disclaimer"] = DISCLAIMER
        return out

    @app.get("/api/query/history")
    def query_history(limit: int = 50) -> dict[str, Any]:
        from megatool import nlquery

        return {"runs": nlquery.history(limit=limit)}

    # ------------------------------------------------- corporate events (NF-004/020)
    @app.post("/api/corporate-events/import")
    def corporate_events_import(req: PydanticCorporateEventsImport) -> dict[str, Any]:
        from megatool.corporate_events import (
            CorporateEventError,
            import_events,
            parse_events_csv,
        )
        from megatool.db import get_conn

        try:
            rows = parse_events_csv(req.text, source=req.source)
        except CorporateEventError as exc:
            raise HTTPException(400, str(exc)) from exc
        with get_conn() as conn:
            return import_events(rows, conn)

    @app.get("/api/corporate-events")
    def corporate_events_list(
        symbol: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        from megatool.corporate_events import list_events
        from megatool.db import get_conn

        with get_conn() as conn:
            rows = list_events(conn, symbol=symbol, event_type=event_type,
                               since=since, until=until, limit=limit)
        return {"events": rows, "count": len(rows), "disclaimer": DISCLAIMER}

    @app.get("/api/corporate-events/calendar")
    def corporate_events_calendar(since: str | None = None, until: str | None = None,
                                  limit: int = 500) -> dict[str, Any]:
        from megatool.corporate_events import calendar
        from megatool.db import get_conn

        with get_conn() as conn:
            out = calendar(conn, since=since, until=until, limit=limit)
        out["disclaimer"] = DISCLAIMER
        return out

    @app.get("/api/corporate-events/coverage")
    def corporate_events_coverage() -> dict[str, Any]:
        from megatool.corporate_events import coverage
        from megatool.db import get_conn

        with get_conn() as conn:
            return coverage(conn)

    # --------------------------------------------------------------------- #
    # Sasto Share workspace
    #
    # The reference platform's market, valuation, risk, rotation and dividend
    # views. Every route below reads the same stores the rest of the tool uses;
    # a missing input is reported as an unavailable state with a reason rather
    # than filled with a placeholder.
    # --------------------------------------------------------------------- #
    def _sasto_sector_map() -> dict[str, str]:
        from megatool.market_dashboard import _sector_map

        return _sector_map()

    def _sasto_sector_members(sector_map: dict[str, str]) -> dict[str, list[str]]:
        members: dict[str, list[str]] = {}
        for sym, sector in sector_map.items():
            members.setdefault(sector or "Unclassified", []).append(sym)
        return members

    @app.get("/api/sastoshare/pulse")
    def sastoshare_pulse() -> dict[str, Any]:
        """Barometer, sentiment, sector moving-average participation and the
        P/E / P/B / price distributions the reference dashboard shows."""
        from megatool.sastoshare import market_pulse

        sector_map = _sasto_sector_map()
        with get_conn() as conn:
            return market_pulse(get_store(), conn, sector_map)

    @app.get("/api/sastoshare/movers")
    def sastoshare_movers(
        limit: int = Query(12, ge=1, le=40),
        spark: int = Query(30, ge=5, le=120),
    ) -> dict[str, Any]:
        """Gainers / losers with a stored-close sparkline, a 250-bar range and a
        derived market capitalisation."""
        from megatool.sastoshare import movers_context

        snap = _live_service().snapshot(force=False)
        quotes = list(snap.get("quotes") or [])
        with get_conn() as conn:
            payload = movers_context(get_store(), conn, quotes, limit=limit, spark=spark)
        return payload

    @app.get("/api/sastoshare/valuation-history/{symbol}")
    def sastoshare_valuation_history(
        symbol: str,
        limit: int = Query(750, ge=60, le=5000),
    ) -> dict[str, Any]:
        """Price + P/E + P/B series, period-aligned from stored fundamentals."""
        from megatool.sastoshare import price_valuation_history

        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        sector_map = _sasto_sector_map()
        with get_conn() as conn:
            return price_valuation_history(
                get_store(), conn, symbol, sector_map, limit=limit,
                sectors=_sasto_sector_members(sector_map),
            )

    @app.get("/api/sastoshare/valuation/{symbol}")
    def sastoshare_valuation(
        symbol: str,
        growth_pct: float | None = Query(None, ge=-100, le=500),
        required_return_pct: float | None = Query(None, gt=0, le=100),
    ) -> dict[str, Any]:
        """Classical valuation models with their inputs, or the exact missing input."""
        from megatool.sastoshare import valuation_models

        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        with get_conn() as conn:
            return valuation_models(
                conn, get_store(), symbol,
                growth_override=growth_pct, required_return=required_return_pct,
            )

    @app.get("/api/sastoshare/risk/{symbol}")
    def sastoshare_risk(
        symbol: str,
        limit: int = Query(250, ge=60, le=5000),
        account_size: float = Query(100_000.0, gt=0),
        risk_fraction: float = Query(0.01, gt=0, le=1),
    ) -> dict[str, Any]:
        """Support/resistance and risk-reward framing on daily and weekly bars."""
        from megatool.sastoshare import levels_and_risk

        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        return levels_and_risk(
            get_store(), symbol, limit=limit,
            account_size=account_size, risk_fraction=risk_fraction,
        )

    @app.get("/api/sastoshare/volatility/{symbol}")
    def sastoshare_volatility(
        symbol: str,
        limit: int = Query(750, ge=60, le=5000),
    ) -> dict[str, Any]:
        """Daily/annualised volatility, three-month beta and the projection cone."""
        from megatool.sastoshare import volatility_projection

        if not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        return volatility_projection(get_store(), symbol, limit=limit)

    @app.get("/api/sastoshare/rotation")
    def sastoshare_rotation() -> dict[str, Any]:
        """Equal-weight sector indices with multi-window returns and momentum."""
        from megatool.sastoshare import sector_rotation

        return sector_rotation(get_store(), _sasto_sector_map())

    @app.get("/api/sastoshare/dividends")
    def sastoshare_dividends(symbol: str | None = None) -> dict[str, Any]:
        """Dividend notices and yields from stored rows, or the exact blocker."""
        from megatool.sastoshare import dividends

        if symbol and not valid_symbol(symbol):
            raise HTTPException(400, "invalid symbol")
        with get_conn() as conn:
            return dividends(conn, get_store(), symbol=symbol)

    @app.post("/api/sastoshare/backtest-vs-hold")
    def sastoshare_backtest_vs_hold(req: PydanticBacktestRequest) -> dict[str, Any]:
        """The real backtest plus a buy-and-hold curve on the same dates and costs."""
        from megatool.sastoshare import backtest_vs_hold

        result = _run_backtest_request(req)
        df = get_store().get_bars(req.symbol.upper(), start=req.start, end=req.end)
        return backtest_vs_hold(result, df, initial_cash=req.initial_cash)

    @app.get("/api/sectors")
    def sectors_list() -> dict[str, Any]:
        """Sector classifications from the securities table, auto-importing from
        the project's review CSVs on first access if the table is empty."""
        from megatool.sectors import auto_import_from_disk
        store = get_store()
        try:
            # Auto-import if the securities table has no sector data.
            rows = store.execute("SELECT COUNT(*) FROM security_master WHERE sector IS NOT NULL AND sector != ''").fetchone()
            if not rows or rows[0] == 0:
                try:
                    auto_import_from_disk(store=store)
                except Exception:
                    pass
            # Now read the sector map.
            sec_rows = store.execute("SELECT symbol, sector, source FROM security_master WHERE sector IS NOT NULL AND sector != ''").fetchall()
            # Group by canonical sector. The reference files spell several
            # industries both singular and plural; merging only those known
            # aliases prevents one sector appearing twice with two counts.
            sector_map = {}
            for r in sec_rows:
                sector_map[r[0]] = canonical_sector(r[1])
            by_sector: dict[str, list[str]] = {}
            for sym, sec in sector_map.items():
                by_sector.setdefault(sec, []).append(sym)
            for members in by_sector.values():
                members.sort()
            return {
                "sector_map": sector_map,
                "by_sector": by_sector,
                "total_classified": len(sector_map),
                "total_sectors": len(by_sector),
                "source": "security_master (populated from yonepse + binayabaral review sources)",
                "aliases_applied": True,
            }
        except Exception as exc:
            return {"sector_map": {}, "by_sector": {}, "total_classified": 0, "total_sectors": 0, "error": str(exc)}

    @app.get("/api/search")
    def universal_search(request: Request, q: str = "", limit: int = Query(30, ge=1, le=100)) -> dict[str, Any]:
        """Permission-aware universal search over navigation, symbols, sectors,
        report components, research topics, journal and portfolio records.

        The endpoint is intentionally read-only and uses bounded SQL filters.
        Private user records are included only for the owner (loopback + trusted).
        """
        needle = (q or "").strip().lower()
        owner = False
        try:
            from megatool.friend_access import client_is_loopback, trust_loopback
            owner = bool(trust_loopback() and client_is_loopback(request.client.host if request.client else None))
        except Exception:  # noqa: BLE001
            owner = False

        results: list[dict[str, Any]] = []
        def add(kind: str, label: str, hint: str, source: str, target: dict[str, Any] | None = None) -> None:
            if len(results) >= 500:
                return
            hay = f"{label} {hint} {source}".lower()
            if needle and needle not in hay:
                # token/prefix fallback: every query word must appear somewhere
                if not all(tok in hay for tok in needle.split()):
                    return
            results.append({
                "id": f"{kind}:{len(results)}",
                "kind": kind,
                "label": label,
                "hint": hint,
                "source": source,
                "target": target or {},
            })

        # Navigation and major modules.
        for view, label, hint in [
            ("charts", "Charts", "Price chart, overlays and drawing tools"),
            ("overview", "Market overview", "Market summary and breadth"),
            ("baba/sector", "BABA sector report", "Canonical sector report"),
            ("baba/scanner", "Fundamental Scanner", "Stored fundamentals and eligibility"),
            ("baba/quarterly", "Quarterly Analysis", "Quarterly periods and growth"),
            ("baba/builder", "Report Builder", "Shared report components and export"),
            ("baba/journal", "Trading Journal", "Journal entries and review"),
            ("baba/compare", "Company Comparison", "Side-by-side fundamentals"),
            ("portfolio", "Portfolio", "Holdings and risk"),
            ("screener", "Screener", "Financial screening"),
            ("backtest", "Backtesting", "Strategy backtests"),
        ]:
            add("view", label, hint, "navigation", {"type": "view", "view": view})

        # Symbols and sectors from the stored security master.
        try:
            meta = get_store().securities_meta()
        except Exception:  # noqa: BLE001
            meta = {}
        try:
            from megatool.report_components import review_company_names
            fallback_names = review_company_names()
        except Exception:  # noqa: BLE001
            fallback_names = {}
        for sym, info in meta.items():
            name = str(info.get("name") or fallback_names.get(sym) or "").strip()
            sector = canonical_sector(info.get("sector"))
            hint = " · ".join(x for x in [name, sector, info.get("status")] if x)
            add("symbol", sym, hint, "security_master", {"type": "symbol", "symbol": sym})
        # Symbols that only appear in review sources or fundamentals.
        for sym, name in fallback_names.items():
            if sym in meta:
                continue
            add("symbol", sym, str(name or ""), "review source", {"type": "symbol", "symbol": sym})

        # BABA report components.
        try:
            from megatool import report_builder as rb
            reg = rb._registry()
            for cid in rb.get_component_ids():
                c = reg[cid]
                if not owner and c.category in ("K_journal", "L_portfolio"):
                    continue
                add("component", c.name, c.description, f"report component · {c.category}",
                    {"type": "component", "id": c.id})
        except Exception:  # noqa: BLE001
            pass

        # Drawing tools available in the chart workspace.
        for tool_id, label, hint in [
            ("trendline", "Trendline", "Straight line between two pivots"),
            ("ray", "Ray", "Extends right through the second anchor"),
            ("extended", "Extended line", "Infinite line in both directions"),
            ("channel", "Parallel channel", "Parallel channel between anchors"),
            ("rectangle", "Rectangle", "Opposite-corner rectangle"),
            ("arrow", "Arrow", "Line with arrow head at anchor 2"),
            ("fib_retracement", "Fibonacci retracement", "Fibonacci retracement levels"),
            ("fib_extension", "Fibonacci extension", "Fibonacci extension levels"),
            ("measure", "Measure", "Price, percentage and bar difference"),
            ("xabcd", "XABCD", "Harmonic XABCD pattern"),
            ("abcd", "ABCD", "ABCD harmonic pattern"),
            ("three_drives", "Three drives", "Three-drives pattern"),
            ("elliott_impulse", "Elliott impulse", "Elliott impulse wave"),
            ("elliott_abc", "Elliott correction", "Elliott ABC correction"),
            ("fib_arc", "Fibonacci arcs", "Concentric Fibonacci arcs"),
            ("fib_spiral", "Fibonacci spiral", "Golden spiral approximation"),
            ("hns", "Head & Shoulders (manual)", "Manual head and shoulders annotation"),
            ("text", "Text note", "Editable text annotation"),
        ]:
            add("drawing", label, hint, "drawing tools", {"type": "tool", "tool": tool_id})

        # Research topics.
        try:
            topics = research_topics()
            for t in (topics.get("topics") if isinstance(topics, dict) else topics) or []:
                label = t.get("title") or t.get("topic") or str(t)
                add("research", str(label), str(t.get("summary") or t.get("description") or ""),
                    "research topics", {"type": "research", "topic": label})
        except Exception:  # noqa: BLE001
            pass

        # Algorithm / scanner / fundamental catalogue.
        try:
            from megatool import catalog as _cat
            for kind in ("scanner", "algorithm", "fundamental"):
                for t in _cat.all_tools(kind):
                    label = t.get("name") or t.get("id") or t.get("key")
                    desc = t.get("description") or t.get("short") or t.get("summary") or ""
                    add(kind, str(label), str(desc), f"{kind} catalogue",
                        {"type": "catalog", "kind": kind, "id": t.get("id") or t.get("key")})
        except Exception:  # noqa: BLE001
            pass

        # User records (owner only).
        if owner:
            try:
                with get_conn() as conn:
                    rows = conn.execute(
                        """SELECT id, symbol, strategy, thesis, outcome_notes, opened_at
                           FROM journal_entries
                           WHERE LOWER(COALESCE(symbol,'') || ' ' || COALESCE(strategy,'') || ' ' ||
                                 COALESCE(thesis,'') || ' ' || COALESCE(outcome_notes,''))
                                 LIKE ? LIMIT 20""",
                        (f"%{needle or '%'}%",),
                    ).fetchall()
                    for r in rows:
                        add("journal", f"Journal entry #{r[0]} · {r[1] or '—'}",
                            " ".join(str(x) for x in (r[2], r[3], r[4], r[5]) if x),
                            "trading journal", {"type": "journal", "id": r[0]})
            except Exception:  # noqa: BLE001
                pass
            try:
                with get_conn() as conn:
                    rows = conn.execute(
                        """SELECT name, symbols FROM watchlists
                           WHERE LOWER(name || ' ' || symbols) LIKE ? LIMIT 20""",
                        (f"%{needle or '%'}%",),
                    ).fetchall()
                    for name, symbols in rows:
                        add("watchlist", f"Watchlist {name}", str(symbols or ""), "watchlist",
                            {"type": "watchlist", "name": name})
            except Exception:  # noqa: BLE001
                pass

        # Rank exact-ish matches first.
        if needle:
            def score(r: dict[str, Any]) -> tuple[int, str]:
                hay = f"{r['label']} {r['hint']}".lower()
                if hay.startswith(needle):
                    return (0, hay)
                if needle in r["label"].lower():
                    return (1, hay)
                return (2, hay)
            results.sort(key=score)
        return {"query": q, "count": len(results), "results": results[:limit]}

    @app.get("/api/export/registry")
    def export_registry(request: Request) -> dict[str, Any]:
        """Shared, permission-aware export component discovery.

        Reuses the BABA report component registry rather than maintaining a
        second hardcoded list. Each entry states its category, formats implied
        by the report renderer, availability, and whether it is private.
        """
        owner = False
        try:
            from megatool.friend_access import client_is_loopback, trust_loopback
            owner = bool(trust_loopback() and client_is_loopback(request.client.host if request.client else None))
        except Exception:  # noqa: BLE001
            owner = False
        try:
            from megatool import report_builder as rb
            reg = rb._registry()
            components = []
            for cid in rb.get_component_ids():
                c = reg[cid]
                if not owner and c.category in ("K_journal", "L_portfolio"):
                    continue
                components.append({
                    "id": c.id,
                    "name": c.name,
                    "category": c.category,
                    "available": bool(c.available),
                    "private": c.category in ("K_journal", "L_portfolio"),
                    "formats": ["xlsx", "csv", "pdf", "json"],
                })
            return {
                "components": components,
                "count": len(components),
                "routes": [
                    {"id": "baba_report", "path": "/api/baba/report/export", "formats": ["xlsx", "csv", "pdf", "json"]},
                    {"id": "screen_export", "path": "/api/screen/export.csv", "formats": ["csv", "xlsx", "pdf"]},
                    {"id": "research_download", "path": "/api/baba/research/jobs/{job_id}/download/{fmt}", "formats": ["pdf", "xlsx", "json", "zip"]},
                ],
                "private_included": owner,
            }
        except Exception as exc:  # noqa: BLE001
            return {"components": [], "count": 0, "routes": [], "error": str(exc)}


    @app.get("/api/sector-overview")
    def sector_overview(period: int = Query(20, ge=1, le=260),
                        sectors: str = "", companies: str = "") -> dict[str, Any]:
        """Derived sector-level analytics over stored daily bars.

        Sector prices are equal-weight aggregates of members with enough history.
        Sector turnover/volume are sums of constituent bars. Missing values are
        never converted to zero in returns; they are omitted and reported.
        """
        store = get_store()
        meta = store.securities_meta()
        # Last N distinct trading dates.
        date_rows = store.execute(
            "SELECT DISTINCT trading_date FROM price_bars ORDER BY trading_date DESC LIMIT ?",
            [period],
        ).fetchall()
        dates = sorted(r[0] for r in date_rows)
        if not dates:
            return {"available": False, "reason": "no stored price bars", "sectors": [], "market": {}}
        start = dates[0]
        bar_rows = store.execute(
            "SELECT symbol, trading_date, close, turnover, volume FROM price_bars WHERE trading_date >= ?",
            [start],
        ).fetchall()
        by_symbol: dict[str, dict[Any, dict[str, Any]]] = {}
        for sym, dt, close, turnover, volume in bar_rows:
            by_symbol.setdefault(str(sym).upper(), {})[dt] = {
                "close": close, "turnover": turnover, "volume": volume,
            }

        sector_members: dict[str, list[str]] = {}
        for sym, info in meta.items():
            sec = canonical_sector(info.get("sector"))
            if sec:
                sector_members.setdefault(sec, []).append(str(sym).upper())

        selected_sectors = [x.strip() for x in sectors.split(",") if x.strip()]
        if not selected_sectors:
            selected_sectors = sorted(sector_members)

        def pct(a, b):
            if a is None or b is None or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                return None
            if b == 0:
                return None
            return (a / b - 1.0) * 100.0

        sectors_out = []
        for sec in selected_sectors:
            members = sector_members.get(sec, [])
            valid = []
            for sym in members:
                dmap = by_symbol.get(sym, {})
                if all(dt in dmap and dmap[dt].get("close") is not None for dt in dates):
                    valid.append(sym)
            # Equal-weight sector index, rebased to 100.
            index = None
            if len(valid) >= 2:
                raw = [sum(by_symbol[sym][dt]["close"] for sym in valid) / len(valid) for dt in dates]
                base = raw[0] if raw and raw[0] not in (0, None) else None
                if base:
                    index = [round((v / base) * 100.0, 2) for v in raw]
            turnover = []
            volume = []
            for dt in dates:
                t = 0.0
                v = 0.0
                have = False
                for sym in members:
                    d = by_symbol.get(sym, {}).get(dt)
                    if not d:
                        continue
                    if d.get("turnover") is not None:
                        t += float(d["turnover"]); have = True
                    if d.get("volume") is not None:
                        v += float(d["volume"])
                turnover.append(round(t, 2) if have else None)
                volume.append(round(v, 2) if have else None)

            period_return = pct(index[-1] if index else None, index[0] if index else None)
            prev_turnover = turnover[-2] if len(turnover) >= 2 else None
            turnover_change_pct = pct(turnover[-1] if turnover else None, prev_turnover)
            avg_prior = None
            if len(turnover) >= 2:
                vals = [x for x in turnover[:-1] if x is not None]
                if vals:
                    avg_prior = sum(vals) / len(vals)
            rel_turnover = (turnover[-1] / avg_prior) if (turnover and turnover[-1] is not None and avg_prior not in (0, None)) else None
            sectors_out.append({
                "sector": sec,
                "members": len(members),
                "members_with_full_history": len(valid),
                "index": index,
                "turnover": turnover,
                "volume": volume,
                "return_period_pct": round(period_return, 2) if period_return is not None else None,
                "turnover_change_pct": round(turnover_change_pct, 2) if turnover_change_pct is not None else None,
                "latest_turnover": turnover[-1] if turnover else None,
                "relative_turnover": round(rel_turnover, 2) if rel_turnover is not None else None,
                "latest_volume": volume[-1] if volume else None,
            })

        # NEPSE from index_series.
        nepse_rows = store.execute(
            "SELECT trading_date, close FROM index_series WHERE index_name='NEPSE' AND trading_date >= ? ORDER BY trading_date",
            [start],
        ).fetchall()
        nepse_map = {r[0]: r[1] for r in nepse_rows}
        nepse = [nepse_map.get(dt) for dt in dates]
        nepse_return = pct(nepse[-1] if nepse else None, nepse[0] if nepse else None)

        # Market turnover from constituents.
        market_turnover = []
        for dt in dates:
            t = 0.0
            have = False
            for sym, dmap in by_symbol.items():
                d = dmap.get(dt)
                if d and d.get("turnover") is not None:
                    t += float(d["turnover"]); have = True
            market_turnover.append(round(t, 2) if have else None)

        # Breadth.
        breadth = []
        for i, dt in enumerate(dates):
            adv = dec = unch = 0
            if i == 0:
                breadth.append({"date": str(dt), "advancing": None, "declining": None, "unchanged": None})
                continue
            prev = dates[i - 1]
            for sym, dmap in by_symbol.items():
                cur = dmap.get(dt, {}).get("close")
                old = dmap.get(prev, {}).get("close")
                if cur is None or old is None:
                    continue
                if cur > old:
                    adv += 1
                elif cur < old:
                    dec += 1
                else:
                    unch += 1
            breadth.append({"date": str(dt), "advancing": adv, "declining": dec, "unchanged": unch})

        # Turnover share and concentration.
        latest_sector_turnover = {s["sector"]: (s["latest_turnover"] or 0.0) for s in sectors_out}
        total_to = sum(v for v in latest_sector_turnover.values() if v is not None)
        shares = []
        for sec, val in latest_sector_turnover.items():
            share = (val / total_to * 100.0) if total_to else None
            shares.append({"sector": sec, "turnover": val, "share_pct": round(share, 2) if share is not None else None})
        shares.sort(key=lambda x: -(x["share_pct"] or -999))
        hhi = None
        if total_to:
            fracs = [v / total_to for v in latest_sector_turnover.values() if v is not None]
            hhi = round(sum(f * f for f in fracs), 4)

        # Rankings.
        rankings = sorted(sectors_out, key=lambda x: (x["return_period_pct"] is None, -(x["return_period_pct"] or -999)))

        # Scatter: return vs relative turnover.
        scatter = [{"sector": s["sector"], "return_pct": s["return_period_pct"],
                    "relative_turnover": s["relative_turnover"],
                    "latest_turnover": s["latest_turnover"]} for s in sectors_out]

        # Company snapshot for heatmap (latest close/turnover/period return).
        company_snapshot = []
        for sym, info in meta.items():
            dmap = by_symbol.get(str(sym).upper(), {})
            if not dmap:
                continue
            last_dt = dates[-1]
            d = dmap.get(last_dt)
            if not d or d.get("close") is None:
                continue
            first_dt = dates[0]
            first_close = dmap.get(first_dt, {}).get("close")
            ret = pct(d["close"], first_close)
            company_snapshot.append({
                "symbol": str(sym).upper(),
                "sector": canonical_sector(info.get("sector")),
                "close": d["close"],
                "turnover": d.get("turnover"),
                "return_period_pct": round(ret, 2) if ret is not None else None,
            })
        company_snapshot.sort(key=lambda x: -(x["return_period_pct"] if x["return_period_pct"] is not None else -999))

        # Turnover reconciliation between available sectors and market total.
        sector_turnover_sum = sum((s.get("latest_turnover") or 0.0) for s in sectors_out)
        market_total = market_turnover[-1] if market_turnover else None
        recon_diff = (market_total - sector_turnover_sum) if (market_total is not None) else None
        recon_pct = (recon_diff / market_total * 100.0) if (recon_diff is not None and market_total not in (0, None)) else None
        reconciliation = {
            "market_total_turnover": market_total,
            "sector_turnover_sum": round(sector_turnover_sum, 2),
            "difference": round(recon_diff, 2) if recon_diff is not None else None,
            "difference_pct": round(recon_pct, 2) if recon_pct is not None else None,
            "note": "Sector totals are sums of constituent stored bars. A difference can occur when some symbols are unclassified or have missing sector mappings.",
        }

        # Rule-based insights.
        insights = []
        if sectors_out:
            best = max(sectors_out, key=lambda x: (x["return_period_pct"] is not None, x["return_period_pct"] or -999))
            worst = min(sectors_out, key=lambda x: (x["return_period_pct"] is None, x["return_period_pct"] if x["return_period_pct"] is not None else 999))
            if best.get("return_period_pct") is not None:
                insights.append(f"{best['sector']} has the strongest selected-period return at {best['return_period_pct']}%.")
            if worst.get("return_period_pct") is not None:
                insights.append(f"{worst['sector']} has the weakest selected-period return at {worst['return_period_pct']}%.")
        high_to = max(sectors_out, key=lambda x: (x["latest_turnover"] is not None, x["latest_turnover"] or -999)) if sectors_out else None
        if high_to and high_to.get("latest_turnover") is not None:
            insights.append(f"{high_to['sector']} has the highest latest-session turnover.")
        if hhi is not None:
            insights.append(f"Latest-session turnover concentration (HHI) is {hhi}.")
        if not insights:
            insights.append("Insufficient data to generate evidence-based insights for this period.")

        return {
            "available": True,
            "period_sessions": len(dates),
            "start_date": str(dates[0]),
            "end_date": str(dates[-1]),
            "dates": [str(d) for d in dates],
            "sectors": sectors_out,
            "market": {
                "nepse": nepse,
                "nepse_return_period_pct": round(nepse_return, 2) if nepse_return is not None else None,
                "turnover": market_turnover,
                "breadth": breadth,
                "latest_total_turnover": market_turnover[-1] if market_turnover else None,
            },
            "rankings": rankings,
            "turnover_share": shares,
            "concentration_hhi": hhi,
            "turnover_reconciliation": reconciliation,
            "scatter": scatter,
            "company_snapshot": company_snapshot,
            "insights": insights,
            "data_quality": {
                "latest_date": str(dates[-1]),
                "observations": len(dates),
                "sector_count": len(sectors_out),
                "company_count": len(company_snapshot),
                "source": "stored price_bars + security_master",
                "turnover_source": "sum of constituent stored price_bars.turnover for the latest session",
                "index_source": "derived equal-weight aggregate of stored closes; not an official NEPSE sector index",
                "note": "Historical EOD data only. Dashboard live quotes use a different source and date.",
            },
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


def _mi_db_path():
    """Path to the isolated market-intelligence database (dev/prod data dir)."""
    from megatool.config import DATA_DIR
    return DATA_DIR / "market_intelligence.db"

app = create_app()


def run() -> None:
    import uvicorn

    _log_access_boundary()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":  # pragma: no cover
    run()
