"""Non-production validation of the YONEPSE / binayabaral source pipeline.

WHAT THIS IS
------------
A single, reviewable script that proves each available source conversion
actually reaches the app's existing loaders end to end, using the real
snapshots already downloaded into ``data/review/source_probe_*/``. It exists
so the owner can approve a production import from *measured* evidence rather
than from the existence of an adapter.

WHAT THIS IS NOT
----------------
It is not an import. Every database it touches lives in a fresh temporary
directory: the production DuckDB is only ever **read** (to copy it), and the
SQLite app DB is created from scratch under the temp dir. Nothing here writes
to ``data/processed/``, nothing here talks to the network, and nothing here
requires a decision — the artifacts are inputs to the owner's decision.

Usage::

    .venv/bin/python scripts/validate_source_pipeline.py \\
        --raw data/review/source_probe_2026-10-15 \\
        --out data/review/source_validation
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from megatool import corporate_actions  # noqa: E402
from megatool import fundamentals as fund  # noqa: E402
from megatool import news as news_mod  # noqa: E402
from megatool.datasources import (  # noqa: E402
    binayabaral,
    sector_consensus,
    socrateai,
    yonepse,
)
from megatool.db import get_conn, init_app_db  # noqa: E402
from megatool.index_series import import_index_series  # noqa: E402
from megatool.market_store import MarketStore  # noqa: E402
from megatool.ranking import (
    DEFAULT_WEIGHTS,
    SECTOR_FACTOR_KEY,
    RankConfig,
    rank_universe,
    sector_availability,
)

#: Maximum symbols pulled from the store for the ranking exercise. The ranker
#: is O(universe) on frames, and the point is to prove the factor is computed
#: from real data, not to benchmark a 372-symbol universe.
RANK_LIMIT = 60


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_raw(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.exists():
            raise SystemExit(f"raw snapshot directory not found: {explicit}")
        return explicit
    candidates = sorted(Path("data/review").glob("source_probe_*"), reverse=True)
    if not candidates:
        raise SystemExit(
            "no source_probe_* directory under data/review/; download the "
            "snapshots first (see docs/DATA_SOURCES.md)"
        )
    return candidates[0]


def _load_sector_sources(raw: Path) -> dict[str, dict[str, Any]]:
    """Load every sector source found in the snapshot directory."""
    out: dict[str, dict[str, Any]] = {}
    for name, loader in (
        (
            "yonepse",
            lambda: sector_consensus.load_yonepse(_read_json(raw / "yonepse_securities.json")),
        ),
        (
            "nepalstockdata",
            lambda: sector_consensus.load_nepalstockdata(
                (raw / "nepalstockdata_listed_company.csv").read_text()
            ),
        ),
        (
            "stockmap",
            lambda: sector_consensus.load_stockmap(_read_json(raw / "surajrimal_stockmap.json")),
        ),
        (
            "binayabaral",
            lambda: sector_consensus.load_binayabaral(
                (raw / "binayabaral_symbols.csv").read_text()
            ),
        ),
    ):
        try:
            out[name] = loader()
        except Exception:
            # a missing probe file must not abort the whole run
            out[name] = {}
    return out


def _checkpoint_3b_socrateai_index(raw: Path, store: MarketStore) -> dict[str, Any]:
    """Validate and import the socrateai sector-index sample.

    The full dataset is 5,350 daily files (2003-07-17 -> 2026-10-15); the stored
    probe holds a stratified sample of 141 sessions drawn from the trading dates
    of the independent binayabaral series, so the two sources overlap exactly.
    """
    sample_dir = raw / "socrateai_index_sample"
    if not sample_dir.is_dir() or not any(sample_dir.glob("adj_*.csv")):
        return {
            "blocker": "3b. socrateai sector indices",
            "available": False,
            "reason": "no socrateai_index_sample directory in the snapshot",
        }

    observations: list[dict[str, Any]] = []
    missing = 0
    for csv_path in sorted(sample_dir.glob("adj_*.csv")):
        day = csv_path.stem[4:]
        parsed = socrateai.parse_index_csv(csv_path.read_text(), trading_date=day)
        observations += parsed["observations"]
        missing += len(parsed["missing"])

    report = socrateai.validate_observations(observations)
    indices = sorted({o["index_name"] for o in observations})

    # Cross-check the composite against the independent binayabaral series.
    bin_idx = {}
    with open(raw / "binayabaral_index.csv") as f:
        for r in csv.DictReader(f):
            bin_idx[r["published_date"].strip()] = float(r["close"])
    nepse = {o["date"]: o["close"] for o in observations if o["index_name"] == "NEPSE"}
    overlap = sorted(set(nepse) & set(bin_idx))
    identical = sum(1 for d in overlap if abs(nepse[d] - bin_idx[d]) < 0.005)
    worst = max((abs(nepse[d] - bin_idx[d]) for d in overlap), default=0.0)

    # Import every index into the isolated store.
    rows = socrateai.to_index_rows(observations, source="socrateai/ohlc_index")
    written = store.upsert_index_rows(rows)

    return {
        "blocker": "3b. socrateai sector indices",
        "available": True,
        "sample_files": len(list(sample_dir.glob("adj_*.csv"))),
        "observations": report["checked"],
        "indices": indices,
        "index_count": len(indices),
        "missing_numeric_rows": missing,
        "genuine_inversions": len(report["inverted"]),
        "rounding_artefacts": len(report["rounding_artefacts"]),
        "non_positive_closes": len(report["non_positive_close"]),
        "cross_check": {
            "overlap_dates": len(overlap),
            "identical_to_the_cent": identical,
            "identical_pct": round(identical / len(overlap) * 100, 2) if overlap else 0.0,
            "worst_absolute_difference": round(worst, 4),
        },
        "rows_written_to_isolated_store": written,
        "evidence": "stratified sample of the real dataset; isolated store copy",
    }


def _checkpoint_1b_sector_consensus(raw: Path, store: MarketStore) -> dict[str, Any]:
    """Cross-source sector consensus over the four compilations."""
    srcs = _load_sector_sources(raw)
    universe = store.symbols(min_bars=1)
    consensus = sector_consensus.build_consensus(
        universe,
        yonepse=srcs["yonepse"],
        stockmap=srcs["stockmap"],
        binayabaral=srcs["binayabaral"],
        nepalstockdata=srcs["nepalstockdata"],
    )
    unresolved = consensus["unresolved"]
    return {
        "blocker": "1b. Sector consensus across sources",
        "sources": {k: len(v) for k, v in srcs.items()},
        "store_universe": len(universe),
        "stats": consensus["stats"],
        "resolved_ordinary_symbols": sorted(sector_consensus.sector_map_for_ranker(consensus))[:15],
        "instrument_classified_count": consensus["stats"]["resolved_instrument"],
        "unresolved_symbols": unresolved,
        "unresolved_detail": [
            {
                "symbol": s,
                "bars": len(store.get_bars(s)),
                "note": "no source classifies it; stays sector=NULL",
            }
            for s in unresolved
        ],
        "evidence": "all four public sources, isolated store copy",
    }


def _checkpoint_1_sectors(store: MarketStore, securities: list[dict[str, Any]]) -> dict[str, Any]:
    """Sector classification: import, coverage and stored provenance."""
    before = store.securities_meta()
    universe = store.symbols(min_bars=1)
    with_sector_before = sum(1 for m in before.values() if m.get("sector"))

    rows = yonepse.securities_to_sector_rows(securities)
    sectors = {r["symbol"]: r["sector"] for r in rows}
    provenance = {
        r["symbol"]: {
            "source": r["source"],
            "retrieved_at": r["retrieved_at"],
            "observed_date": r["observed_date"],
        }
        for r in rows
    }
    # Only symbols already in the master can be assigned; the rest are reported.
    assignable = {s: v for s, v in sectors.items() if s in universe}
    result = store.set_sectors(assignable, provenance=provenance)

    after = store.securities_meta()
    with_sector_after = sum(1 for m in after.values() if m.get("sector"))
    with_prov = sum(
        1
        for m in after.values()
        if m.get("sector") and m.get("sector_source") and m.get("sector_retrieved_at")
    )
    coverage = sector_availability(sectors, universe, 0.5)

    # Idempotence: a second identical call must change nothing further.
    before_again = store.securities_meta()
    store.set_sectors(assignable, provenance=provenance)
    unchanged = store.securities_meta() == before_again

    return {
        "blocker": "1. Sector classifications",
        "symbols_in_store": len(universe),
        "with_sector_before": with_sector_before,
        "with_sector_after": with_sector_after,
        "with_full_provenance": with_prov,
        "assigned": result["updated"],
        "unmatched_source_symbols": len(result["unknown"]),
        "unmatched_examples": sorted(result["unknown"])[:10],
        "coverage": {
            "available": coverage.available,
            "coverage_pct": round(coverage.coverage * 100, 2),
            "classified": coverage.classified,
            "universe_size": coverage.universe_size,
            "reason": coverage.reason,
        },
        "reimport_is_idempotent": unchanged,
        "evidence": "isolated copy of the production store; YONEPSE data/other/securities.json",
    }


def _checkpoint_1c_corporate_actions(store: MarketStore, raw: Path) -> dict[str, Any]:
    """Milestone 1: retired symbols are labelled and kept out of the active set.

    The four sector sources record the *issuer* that once existed, so they
    still classify merged symbols. Without the corporate-action registry those
    symbols enter the sector map and get ranked against live peers on
    years-old closes. This checkpoint measures exactly that exposure.
    """
    srcs = _load_sector_sources(raw)
    consensus = sector_consensus.build_consensus(store.symbols(min_bars=1), **srcs)
    universe = store.symbols(min_bars=1)
    active, retired = corporate_actions.split_inactive(universe)
    sourced = sector_consensus.sector_map_for_ranker(consensus)
    retired_with_source_sector = {s: sourced[s] for s in retired if s in sourced}
    last_bar = {}
    for s in retired:
        bars = store.get_bars(s)
        if bars is not None and not getattr(bars, "empty", True):
            last_bar[s] = str(bars["trading_date"].max())[:10]

    rows = corporate_actions.security_master_rows()
    return {
        "blocker": "1c. Corporate actions (merged / retired symbols)",
        "registry_entries": len(rows),
        "registry_note": corporate_actions.active_universe_note(),
        "universe_size": len(universe),
        "active_universe_size": len(active),
        "retired_in_store": len(retired),
        "retired_with_source_sector": retired_with_source_sector,
        "retired_last_trade_date": {s: last_bar.get(s) for s in sorted(retired)},
        "active_symbols_have_a_sector": sum(1 for s in active if s in sourced),
        "active_symbols_unresolved": sorted(s for s in active if s not in sourced),
        "evidence": (
            "verified corporate actions (public merger notices + price-series "
            "handoff) cross-checked against the four sector sources"
        ),
    }


def _checkpoint_2_ranking(
    raw: Path, store: MarketStore, securities: list[dict[str, Any]]
) -> dict[str, Any]:
    """Sector-relative ranking: computed from real sectors on real bars.

    ``sector_percentile`` is an **opt-in** factor: it carries no default weight,
    so :func:`rank_universe` never computes it unless the caller gives it one.
    Both states are exercised below — default weights (factor dormant) and an
    explicit opt-in (factor actually computed) — so the evidence states exactly
    what a caller must do to get the feature.
    """
    # The sector map used for ranking must contain ORDINARY SHARES ONLY.
    # Building it from YONEPSE's raw sectorName would pull in 63 mutual funds
    # and 89 debentures, each tagged with its issuer's business sector, and
    # rank those instruments against the bank's ordinary shares.
    srcs = _load_sector_sources(raw)
    consensus = sector_consensus.build_consensus(
        store.symbols(min_bars=1),
        yonepse=srcs["yonepse"],
        stockmap=srcs["stockmap"],
        binayabaral=srcs["binayabaral"],
        nepalstockdata=srcs["nepalstockdata"],
    )
    sectors = sector_consensus.sector_map_for_ranker(consensus)
    # A merged symbol must not enter the ranked universe: it is attested dead,
    # and ranking it against live peers uses its years-old final close.
    retired_with_sector = sorted(s for s in sectors if corporate_actions.is_inactive(s))
    sectors = {s: v for s, v in sectors.items() if not corporate_actions.is_inactive(s)}
    non_ordinary_with_sector = sorted(
        sym for sym, rec in consensus["resolved"].items() if not rec["is_ordinary"] and rec["votes"]
    )

    universe, retired_universe = corporate_actions.split_inactive(store.symbols(min_bars=1))
    # Rank the symbols with the longest history so the momentum factors have room.
    bar_counts = {}
    for sym in universe:
        try:
            bar_counts[sym] = len(store.get_bars(sym))
        except Exception:  # pragma: no cover - defensive
            bar_counts[sym] = 0
    chosen = sorted(
        [s for s in universe if s in sectors], key=lambda s: (-bar_counts.get(s, 0), s)
    )[:RANK_LIMIT]

    frames: dict[str, Any] = {}
    for sym in chosen:
        bars = store.get_bars(sym)
        if bars is not None and not getattr(bars, "empty", True):
            bars = bars.rename(columns={"trading_date": "date"})
            bars["date"] = bars["date"].astype(str).str.slice(0, 10)
            frames[sym] = bars.reset_index(drop=True)

    ranked_sectors = {s: sectors[s] for s in frames}

    # 1. Default weights: the factor exists but is dormant (documented opt-in).
    default_result = rank_universe(frames, RankConfig(), sectors=ranked_sectors)

    # 2. Explicit opt-in: the caller gives the factor a positive weight.
    opt_in_weights = {**DEFAULT_WEIGHTS, SECTOR_FACTOR_KEY: 0.3}
    result = rank_universe(frames, RankConfig(weights=opt_in_weights), sectors=ranked_sectors)

    with_pct = [r for r in result.ranked if r.percentiles.get(SECTOR_FACTOR_KEY) is not None]
    scored_syms = [r for r in result.ranked if SECTOR_FACTOR_KEY in r.contributions]

    # Counterfactual: with sector data removed the factor must be unavailable.
    no_sector = rank_universe(frames, RankConfig(weights=opt_in_weights), sectors=None)

    # Coverage actually seen by the ranker (computed from live data).
    coverage = sector_availability(ranked_sectors, list(frames), 0.5)

    # Milestone 2: over the FULL active universe every symbol with a sector
    # must receive a percentile. The 60-symbol RANK_LIMIT above is a speed
    # choice only; an earlier "58 of 60" reading was an artefact of that
    # sampling (NTC/Others and CIT/Investment were singletons *within the
    # sample*), not a missing value. Measure the real universe here.
    full_frames: dict[str, Any] = {}
    for sym in universe:
        if sym not in sectors:
            continue
        bars = store.get_bars(sym)
        if bars is None or getattr(bars, "empty", True):
            continue
        bars = bars.rename(columns={"trading_date": "date"})
        bars["date"] = bars["date"].astype(str).str.slice(0, 10)
        full_frames[sym] = bars.reset_index(drop=True)
    full_sectors = {s: sectors[s] for s in full_frames}
    full_result = rank_universe(
        full_frames, RankConfig(weights=opt_in_weights), sectors=full_sectors
    )
    full_with_pct = [
        r.symbol for r in full_result.ranked if r.percentiles.get(SECTOR_FACTOR_KEY) is not None
    ]
    full_missing = sorted(
        r.symbol for r in full_result.ranked if r.percentiles.get(SECTOR_FACTOR_KEY) is None
    )

    return {
        "blocker": "2. Sector-relative ranking",
        "symbols_ranked": len(result.ranked),
        "symbol_excluded": len(result.excluded),
        "symbols_with_real_sector": len(ranked_sectors),
        "sector_percentiles_computed": len(with_pct),
        "sector_percentiles_scored": len(scored_syms),
        "sector_percentile_available_with_optin": (SECTOR_FACTOR_KEY not in result.unavailable),
        "dormant_at_default_weights": (
            SECTOR_FACTOR_KEY in default_result.unavailable
            or SECTOR_FACTOR_KEY not in default_result.weights
        ),
        "correctly_unavailable_without_data": SECTOR_FACTOR_KEY in no_sector.unavailable,
        "coverage": {
            "available": coverage.available,
            "coverage_pct": round(coverage.coverage * 100, 2),
            "classified": coverage.classified,
            "universe_size": coverage.universe_size,
        },
        "sample": [
            {
                "symbol": r.symbol,
                "sector": ranked_sectors.get(r.symbol),
                "sector_pct": r.percentiles.get(SECTOR_FACTOR_KEY),
            }
            for r in with_pct[:8]
        ],
        "distinct_sectors_represented": len({sectors[s] for s in ranked_sectors}),
        "still_unavailable": sorted(result.unavailable),
        "required_weight": 0.3,
        "instrument_classified_excluded": non_ordinary_with_sector,
        "instrument_classified_excluded_count": len(non_ordinary_with_sector),
        "sector_map_size": len(sectors),
        "retired_with_sector_dropped": retired_with_sector,
        "full_universe": {
            "ranked": len(full_result.ranked),
            "symbols_with_sector": len(full_sectors),
            "with_percentile": len(full_with_pct),
            "missing_percentile": full_missing,
            "note": (
                "every active symbol carrying a sector receives a percentile; "
                "the RANK_LIMIT sample is not the universe"
            ),
        },
        "evidence": (
            "isolated store copy; bars from the production price table; sectors "
            "from the four-source consensus restricted to ordinary shares"
        ),
    }


def _checkpoint_3_index(raw: Path, store: MarketStore) -> dict[str, Any]:
    """Historical NEPSE index: import the series and cross-check a second source."""
    index_text = (raw / "binayabaral_index.csv").read_text(encoding="utf-8")
    converted = binayabaral.index_to_index_csv(index_text)
    out = import_index_series(
        converted,
        index_name="NEPSE",
        source="binayabaral/nepal-market-data/data/nepse/NEPSE_INDEX.csv",
        store=store,
    )
    rows = store.query_rows(
        "SELECT trading_date, close FROM index_series WHERE index_name = 'NEPSE' "
        "ORDER BY trading_date"
    )

    # Independent cross-check against the socrateai snapshot for the same date.
    cross = {
        "performed": False,
        "reason": "socrateai index snapshot not present in the raw directory",
    }
    soc_path = raw / "socrateai_index_2026-10-13.csv"
    if soc_path.exists():
        soc_rows = [
            ln.split(",") for ln in soc_path.read_text(encoding="utf-8").strip().splitlines()[1:]
        ]
        soc_close = None
        for fields in soc_rows:
            if len(fields) > 7 and fields[6] == "NEPSE_index":
                day = fields[8]
                if day == "2026-10-13":
                    soc_close = float(fields[4])
        bin_close = None
        for trading_date, close in rows:
            if str(trading_date)[:10] == "2026-10-13":
                bin_close = float(close)
        cross = {
            "performed": soc_close is not None and bin_close is not None,
            "comparison_date": "2026-10-13",
            "binayabaral_close": bin_close,
            "socrateai_close": soc_close,
            "identical": (soc_close == bin_close) if (soc_close and bin_close) else None,
            "note": (
                "two independently compiled repositories agreeing to the cent on "
                "the headline index close; not an official exchange confirmation"
            ),
        }

    # Gap sanity: count trading-day gaps in the imported series.
    days = [str(r[0])[:10] for r in rows]
    gaps = sum(
        1
        for a, b in zip(days, days[1:], strict=False)
        if (date.fromisoformat(b) - date.fromisoformat(a)).days > 4
    )

    return {
        "blocker": "3. Historical NEPSE index data",
        "import": out,
        "rows_in_store": len(rows),
        "first_date": days[0] if days else None,
        "last_date": days[-1] if days else None,
        "suspicious_gaps_over_4_days": gaps,
        "independent_cross_check": cross,
        "evidence": "isolated store copy; index_series table (not the production database)",
    }


def _checkpoint_4_fundamentals(raw: Path) -> dict[str, Any]:
    """Fundamentals Lab: convert, load into an isolated SQLite, compute ratios."""
    records = _read_json(raw / "yonepse_financials.json")
    _, dedupe_stats = yonepse.dedupe_financial_reports(records)
    rows = yonepse.financials_to_fundamental_rows(records)
    pit = yonepse.point_in_time_available(rows)
    loaded = fund.records_from_rows(rows)

    app_db = Path(tempfile.mkdtemp(prefix="megatool_srcval_")) / "app.sqlite"
    init_app_db(app_db)
    with get_conn(app_db) as conn:
        written = fund.import_records(loaded, conn)
        summary = fund.fundamentals_summary(conn)

    return {
        "blocker": "4. Fundamentals Lab",
        "source_symbols": len(records),
        "rows_converted": len(rows),
        "records_loaded": len(loaded),
        "dedupe": dedupe_stats,
        "point_in_time": {
            "rows": pit["rows"],
            "rows_with_filed_at": pit["rows_with_filed_at"],
            "coverage_pct": pit["coverage_pct"],
            "earliest": pit["earliest"],
            "latest": pit["latest"],
        },
        "written": written,
        "summary": {
            "total": summary["total"],
            "symbols": summary["symbols"],
            "by_field": summary["by_field"],
            "without_period": summary["without_period"],
        },
        "evidence": f"isolated SQLite app DB at {app_db}; nothing written to the production app DB",
    }


def _checkpoint_5_news(raw: Path) -> dict[str, Any]:
    """News and events: convert YONEPSE notify files and import them."""
    disclosures = _read_json(raw / "yonepse_disclosures.json")
    exchange_messages = _read_json(raw / "yonepse_exchange_messages.json")
    notices = _read_json(raw / "yonepse_notices.json")
    rows = yonepse.notify_to_news_rows(disclosures, exchange_messages, notices)
    csv_text = yonepse.news_csv(rows)

    app_db = Path(tempfile.mkdtemp(prefix="megatool_srcval_")) / "app.sqlite"
    result = news_mod.import_news(csv_text, fmt="csv", source_file="yonepse", db_path=app_db)
    summary = news_mod.news_summary(db_path=app_db)
    undated = yonepse.notices_without_publication_date(notices)
    return {
        "blocker": "5. News and events",
        "rows_converted": len(rows),
        "general_notices_undated_excluded": len(undated),
        "general_notices_exclusion_reason": (
            "the snapshot carries no publication date for general notices; "
            "expiresAt is an expiry, not a publication date"
        ),
        "imported": {
            "rows": result["rows"],
            "added": result["added"],
            "duplicates": result["duplicates"],
            "skipped": result["skipped"],
        },
        "totals": summary["totals"],
        "distinct_symbols_linked": len(summary["by_symbol"]),
        "recent_sample": [
            {
                "published_at": r["published_at"],
                "title": (r["title"] or "")[:80],
                "event": r["event"]["category"],
            }
            for r in summary["recent"][:5]
        ],
        "evidence": f"isolated SQLite app DB at {app_db}; YONEPSE data/notify/*.json",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=None, help="snapshot directory")
    parser.add_argument("--out", type=Path, default=Path("data/review/source_validation"))
    parser.add_argument(
        "--market-db",
        type=Path,
        default=Path("data/processed/megatool_market.duckdb"),
        help="production store to COPY from (read-only; never written)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="run against a fresh empty store instead of a copy of production",
    )
    args = parser.parse_args(argv)

    raw = _find_raw(args.raw)
    securities = _read_json(raw / "yonepse_securities.json")
    print(f"raw snapshots      : {raw}")
    print(f"securities records : {len(securities)}")

    workdir = Path(tempfile.mkdtemp(prefix="megatool_source_validation_"))
    market_db = workdir / "market.duckdb"
    source_used = "synthetic empty store (no production data read)"
    if args.synthetic or not args.market_db.exists():
        MarketStore(market_db, read_only=False).query_rows("SELECT 1")
    else:
        shutil.copy2(args.market_db, market_db)
        source_used = f"copy of {args.market_db} (production file opened read-only)"
    print(f"market store       : {market_db}")
    print(f"  source           : {source_used}")

    store = MarketStore(market_db, read_only=False)
    store.query_rows("SELECT 1")

    blocks: list[dict[str, Any]] = []
    # The index is imported first so the ranking run can observe whether the
    # imported series changes anything downstream.
    try:
        b3 = _checkpoint_3_index(raw, store)
        b3b = _checkpoint_3b_socrateai_index(raw, store)
        b1b = _checkpoint_1b_sector_consensus(raw, store)
        b1c = _checkpoint_1c_corporate_actions(store, raw)
        for b in (b3, b3b, b1b, b1c):
            blocks.append(b)
        print(
            f"[3] index     : {b3['rows_in_store']} rows "
            f"{b3['first_date']} -> {b3['last_date']}; "
            f"cross-check identical={b3['independent_cross_check'].get('identical')}"
        )
        print(
            f"[1c] corp act : {b1c['retired_in_store']} retired symbols excluded "
            f"({len(b1c['retired_with_source_sector'])} had a source sector), "
            f"active universe {b1c['active_universe_size']}"
        )
        print(
            f"[3b] sector ix: {b3b.get('index_count')} indices from "
            f"{b3b.get('sample_files')} sampled sessions, "
            f"composite identical={b3b['cross_check']['identical_pct']}% "
            f"(worst {b3b['cross_check']['worst_absolute_difference']})"
        )
        print(
            f"[1b] consensus: {b1b['stats']['resolved']} resolved "
            f"({b1b['stats']['resolved_ordinary']} ordinary, "
            f"{b1b['stats']['resolved_instrument']} instrument), "
            f"{b1b['stats']['conflicted']} conflicting, "
            f"{b1b['stats']['unresolved']} unresolved"
        )
        b1 = _checkpoint_1_sectors(store, securities)
        blocks.append(b1)
        print(
            f"[1] sectors   : {b1['with_sector_after']}/{b1['symbols_in_store']} "
            f"symbols classified ({b1['coverage']['coverage_pct']}% coverage), "
            f"provenance stored on {b1['with_full_provenance']}"
        )
        b2 = _checkpoint_2_ranking(raw, store, securities)
        blocks.append(b2)
        print(
            f"[2] ranking   : sector percentiles computed for "
            f"{b2['sector_percentiles_computed']} of {b2['symbols_ranked']} ranked "
            f"symbols ({b2['distinct_sectors_represented']} real sectors, "
            f"{b2['coverage']['coverage_pct']}% coverage); full universe "
            f"{b2['full_universe']['with_percentile']}/"
            f"{b2['full_universe']['ranked']} with a percentile"
        )
        b4 = _checkpoint_4_fundamentals(raw)
        blocks.append(b4)
        print(
            f"[4] fundamentals: {b4['records_loaded']} records / "
            f"{b4['summary']['symbols']} symbols; "
            f"filed_at on {b4['point_in_time']['coverage_pct']}%"
        )
        b5 = _checkpoint_5_news(raw)
        blocks.append(b5)
        print(
            f"[5] news      : {b5['imported']['added']} items imported from "
            f"{b5['rows_converted']} converted rows"
        )
    finally:
        store.close()

    # Report in the six-blocker order regardless of execution order.
    order = {"1.": 0, "1b": 1, "1c": 1.5, "2.": 2, "3.": 3, "3b": 4, "4.": 5, "5.": 6}
    blocks.sort(key=lambda b: order.get(b["blocker"][:2], 9))

    report: dict[str, Any] = {
        "tool": "validate-source-pipeline",
        "version": 1,
        "generated_on": date.today().isoformat(),
        "raw_directory": str(raw),
        "market_store": str(market_db),
        "market_store_source": source_used,
        "production_written": False,
        "blockers": blocks,
        "blocker_6": {
            "blocker": "6. Official NEPSE API HTTP 401",
            "status": "BLOCKED",
            "finding": (
                "The official API returns HTTP 401 without a session token. No "
                "authentication bypass, credential use, or reverse-engineering was "
                "attempted. The five sources above supply historical, reference "
                "and disclosure data permitted for local research; live-market "
                "reads remain unavailable."
            ),
        },
    }

    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / "validation.json"
    md_path = args.out / "validation.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")

    print(f"\nevidience JSON  : {json_path}")
    print(f"evidence report : {md_path}")
    print("production db written: False")
    return 0


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Source-pipeline validation — no production import",
        "",
        f"- Generated: {report['generated_on']}",
        f"- Raw snapshots: `{report['raw_directory']}`",
        f"- Market store used: `{report['market_store']}` ({report['market_store_source']})",
        "- Production database written: **False**",
        "",
        "Every figure below was measured against the real downloaded snapshots.",
        "",
        "## Results",
        "",
        "| Blocker | Result |",
        "|---|---|",
    ]
    for b in report["blockers"]:
        if b["blocker"].startswith("1."):
            lines.append(
                f"| {b['blocker']} | {b['with_sector_after']}/{b['symbols_in_store']} symbols "
                f"classified ({b['coverage']['coverage_pct']}%), provenance on "
                f"{b['with_full_provenance']}, idempotent={b['reimport_is_idempotent']} |"
            )
        elif b["blocker"].startswith("2."):
            lines.append(
                f"| {b['blocker']} | sector percentiles computed for "
                f"{b['sector_percentiles_computed']}/{b['symbols_ranked']} ranked symbols |"
            )
        elif b["blocker"].startswith("3."):
            cc = b["independent_cross_check"]
            cc_txt = (
                f"independent cross-check identical={cc.get('identical')} "
                f"({cc.get('binayabaral_close')} vs {cc.get('socrateai_close')})"
                if cc.get("performed")
                else "no cross-check snapshot"
            )
            lines.append(
                f"| {b['blocker']} | {b['rows_in_store']} rows "
                f"{b['first_date']} -> {b['last_date']}; {cc_txt} |"
            )
        elif b["blocker"].startswith("4."):
            lines.append(
                f"| {b['blocker']} | {b['records_loaded']} records / "
                f"{b['summary']['symbols']} symbols; {b['dedupe']['conflicting_periods_resolved']} "
                f"conflicting periods resolved by the documented rule |"
            )
        elif b["blocker"].startswith("5."):
            lines.append(
                f"| {b['blocker']} | {b['imported']['added']} items imported, "
                f"{b['distinct_symbols_linked']} symbols linked |"
            )
    lines.append(
        f"| {report['blocker_6']['blocker']} | **{report['blocker_6']['status']}** — {report['blocker_6']['finding'][:120]}… |"
    )
    lines += ["", "## Notes", ""]
    for b in report["blockers"]:
        lines.append(f"- **{b['blocker']}** — {b['evidence']}")
    lines += [
        "",
        "This script wrote nothing to `data/processed/`. A production import still",
        "requires the owner's explicit approval.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
