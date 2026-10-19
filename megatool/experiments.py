"""Reproducible research experiments (directive M4 §11.5, overview Phase 4).

An *experiment* is a saved, self-describing backtest run: the exact request
configuration, the result snapshot, a content hash of the configuration, the
data cut-off it ran against, and the engine version. Saving it is not enough —
the mandate requires that a saved experiment can be **reproduced** and that
results can be **compared**, so this module also provides the comparison and
export building blocks.

Design choices that keep honest results honest:

* The **configuration hash** is a SHA-256 over the canonical JSON of the request
  (sorted keys, no whitespace). Two runs with the same hash ran with identical
  inputs; a different hash means something changed, and comparison says what.
* Nothing here re-runs a strategy — the caller passes in the already-computed
  result. Reproduce rebuilds the request from the stored config and runs it
  through the *same* backtest path as a live request, then compares metric by
  metric with an explicit tolerance and flags divergences.
* The table is created lazily on first use with ``CREATE TABLE IF NOT EXISTS``
  and lives in the application SQLite beside the other owner state. It never
  touches the market database.

Storage is intentionally additive: this module does not alter ``db.py``'s
schema-init path and cannot disturb an already-running process.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from megatool import __version__
from megatool.db import get_conn, now_iso

#: Metrics carried into the comparison table. Percent-valued ``*_pct`` fields
#: are already scaled (e.g. ``total_return_pct`` = 12.5 means +12.5%).
COMPARABLE_METRICS: tuple[str, ...] = (
    "final_equity",
    "total_return_pct",
    "cagr_pct",
    "max_drawdown_pct",
    "sharpe",
    "win_rate_pct",
    "trades",
    "exposure_pct",
    "fees_paid",
    "benchmark_total_return_pct",
)

#: Metrics quotient/percent differences below this are treated as identical.
DEFAULT_TOLERANCE = 1e-6

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    label          TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    strategy       TEXT NOT NULL,
    config_hash    TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    data_as_of     TEXT,
    config         TEXT NOT NULL,   -- canonical JSON of the request
    result         TEXT NOT NULL,   -- the backtest payload
    created_at     TEXT NOT NULL
)
"""


class ExperimentError(ValueError):
    """Invalid experiment input or a missing experiment."""


def _ensure_schema(conn: Any) -> None:
    conn.execute(_SCHEMA)


def canonical_config(config: dict[str, Any]) -> str:
    """Canonical JSON of a config (sorted keys, compact) for stable hashing."""
    return json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)


def config_hash(config: dict[str, Any]) -> str:
    """SHA-256 of the canonical configuration. Identical inputs → identical hash."""
    return hashlib.sha256(canonical_config(config).encode("utf-8")).hexdigest()


def metric_subset(result: dict[str, Any]) -> dict[str, Any]:
    """The comparable metrics pulled from a backtest payload."""
    metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
    return {k: metrics.get(k) for k in COMPARABLE_METRICS}


def save_experiment(
    label: str,
    config: dict[str, Any],
    result: dict[str, Any],
    *,
    db_path: Any = None,
) -> dict[str, Any]:
    """Persist a run. ``config`` is the request dict, ``result`` the payload."""
    if not label or not str(label).strip():
        raise ExperimentError("experiment label must not be blank")
    if not isinstance(config, dict) or "symbol" not in config or "strategy" not in config:
        raise ExperimentError("config must include at least 'symbol' and 'strategy'")
    if not isinstance(result, dict):
        raise ExperimentError("result must be a backtest payload object")
    cfg_json = canonical_config(config)
    row = {
        "label": str(label).strip()[:120],
        "symbol": str(config["symbol"]).upper(),
        "strategy": str(config["strategy"]),
        "config_hash": config_hash(config),
        "engine_version": __version__,
        "data_as_of": result.get("data_as_of"),
        "config": cfg_json,
        "result": canonical_config(result),
        "created_at": now_iso(),
    }
    with get_conn(db_path) as conn:
        _ensure_schema(conn)
        cur = conn.execute(
            "INSERT INTO experiments "
            "(label, symbol, strategy, config_hash, engine_version, data_as_of, config, result, created_at) "
            "VALUES (:label, :symbol, :strategy, :config_hash, :engine_version, :data_as_of, :config, :result, :created_at)",
            row,
        )
        new_id = int(cur.lastrowid)
    return get_experiment(new_id, db_path=db_path)


def _summary(row: Any) -> dict[str, Any]:
    payload = json.loads(row["result"])
    return {
        "id": row["id"],
        "label": row["label"],
        "symbol": row["symbol"],
        "strategy": row["strategy"],
        "config_hash": row["config_hash"],
        "engine_version": row["engine_version"],
        "data_as_of": row["data_as_of"],
        "created_at": row["created_at"],
        "metrics": metric_subset(payload),
    }


def list_experiments(db_path: Any = None, limit: int = 200) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT * FROM experiments ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
    return [_summary(r) for r in rows]


def get_experiment(exp_id: int, db_path: Any = None) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        _ensure_schema(conn)
        row = conn.execute("SELECT * FROM experiments WHERE id = ?", (int(exp_id),)).fetchone()
    if row is None:
        raise ExperimentError(f"no experiment with id {exp_id}")
    out = _summary(row)
    out["config"] = json.loads(row["config"])
    out["result"] = json.loads(row["result"])
    out["parameter_changes"] = _parameter_changes(out["config"])
    return out


def delete_experiment(exp_id: int, db_path: Any = None) -> bool:
    with get_conn(db_path) as conn:
        _ensure_schema(conn)
        cur = conn.execute("DELETE FROM experiments WHERE id = ?", (int(exp_id),))
        return cur.rowcount > 0


# ----------------------------------------------------------------- comparison
def _delta(key: str, a: Any, b: Any) -> dict[str, Any]:
    if a is None or b is None:
        return {"metric": key, "a": a, "b": b, "delta": None, "same": a == b}
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return {"metric": key, "a": a, "b": b, "delta": None, "same": a == b}
    return {
        "metric": key,
        "a": fa,
        "b": fb,
        "delta": round(fb - fa, 6),
        "same": abs(fb - fa) <= DEFAULT_TOLERANCE,
    }


def _parameter_changes(config: dict[str, Any]) -> list[str]:
    """Human-readable list of non-default-looking knobs in a config.

    This is descriptive only: it lists the parameters the run carried so two
    experiments can be told apart, without claiming any of them is "better".
    """
    changes: list[str] = []
    for key in (
        "strategy",
        "params",
        "start",
        "end",
        "initial_cash",
        "fee_rate",
        "execution",
        "slippage",
    ):
        if key in config and config[key] not in (None, "", {}, []):
            changes.append(f"{key}={config[key]}")
    return changes


def compare_experiments(
    a: dict[str, Any], b: dict[str, Any], *, tolerance: float = DEFAULT_TOLERANCE
) -> dict[str, Any]:
    """Compare two saved experiments. ``a``/``b`` are dicts from get_experiment."""
    ma, mb = a.get("metrics", {}), b.get("metrics", {})
    rows = []
    for key in COMPARABLE_METRICS:
        row = _delta(key, ma.get(key), mb.get(key))
        if row["delta"] is not None:
            row["same"] = abs(row["delta"]) <= tolerance
        rows.append(row)
    return {
        "a": {"id": a.get("id"), "label": a.get("label"), "config_hash": a.get("config_hash")},
        "b": {"id": b.get("id"), "label": b.get("label"), "config_hash": b.get("config_hash")},
        "identical_config": a.get("config_hash") == b.get("config_hash"),
        "metrics": rows,
        "parameter_changes": {
            "a": a.get("parameter_changes", _parameter_changes(a.get("config", {}))),
            "b": b.get("parameter_changes", _parameter_changes(b.get("config", {}))),
        },
    }


def to_markdown(exp: dict[str, Any]) -> str:
    """A one-page Markdown export of a saved experiment."""
    m = exp.get("metrics", {})
    cfg = exp.get("config", {})
    lines = [
        f"# Experiment {exp.get('id')} — {exp.get('label')}",
        "",
        f"- **Symbol:** {exp.get('symbol')}",
        f"- **Strategy:** {exp.get('strategy')}",
        f"- **Config hash:** `{exp.get('config_hash')}`",
        f"- **Engine version:** {exp.get('engine_version')}",
        f"- **Data as of:** {exp.get('data_as_of')}",
        f"- **Created:** {exp.get('created_at')}",
        "",
        "## Configuration",
        "```json",
        json.dumps(cfg, indent=2, sort_keys=True, default=str),
        "```",
        "",
        "## Metrics (percent fields are already scaled)",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for key in COMPARABLE_METRICS:
        if key in m:
            lines.append(f"| {key} | {m.get(key)} |")
    result = exp.get("result", {})
    assumptions = result.get("assumptions") or []
    warnings = result.get("warnings") or []
    if assumptions:
        lines += ["", "## Assumptions", *[f"- {a}" for a in assumptions]]
    if warnings:
        lines += ["", "## Warnings", *[f"- {w}" for w in warnings]]
    lines += [
        "",
        "> Historical calculation only. Reproduce by resubmitting the configuration; "
        "past performance does not indicate future results.",
    ]
    return "\n".join(lines)
