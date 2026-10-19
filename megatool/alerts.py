"""Explanatory alert engine (Phase 2, feature 9).

Deterministic, stored-data-only alerting. Each condition is evaluated against
the symbol's stored bars; when it first becomes true an alert row is written
to ``alert_history`` (SQLite app DB) with an explainable message naming the
actual numbers, and the schema's ``UNIQUE (alert_key, symbol)`` dedup key
prevents the same condition firing again on every poll cycle. An alert
re-arms only after the owner clears the history.

Condition vocabulary (all thresholds are explicit condition parameters; no
condition invents a price, and none requires a live feed — the engine works
entirely on stored history):

* ``price_above`` / ``price_below`` — last close vs a threshold;
* ``volume_spike`` — last volume vs ``multiple`` × the 20-day median volume;
* ``momentum_above`` / ``momentum_below`` — trailing 60-session return vs ±pct;
* ``new_high`` / ``new_low`` — last close vs the trailing 250-session max/min;
* ``regime_change`` — market regime label changed vs the previous session
  (uses :mod:`megatool.regime`; symbol is the market proxy).

Alerts describe stored/historical signals only — never predictions.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from megatool import DISCLAIMER

#: Trailing windows (in sessions) used by the condition vocabulary.
VOLUME_WINDOW = 20
MOMENTUM_WINDOW = 60
HIGH_LOW_WINDOW = 250

#: Documented alert severities. Order is the display order (most severe first
#: is decided by the UI). ``warning`` is the default so an unlabelled condition
#: is not silently presented as harmless *or* as an emergency.
SEVERITIES = ("info", "warning", "critical")
DEFAULT_SEVERITY = "warning"

_CONDITION_KEYS = (
    "price_above",
    "price_below",
    "volume_spike",
    "momentum_above",
    "momentum_below",
    "new_high",
    "new_low",
    "regime_change",
)


@dataclass(slots=True)
class Alert:
    """One fired alert: what triggered, the numbers, and when."""

    alert_key: str
    symbol: str | None
    condition: str
    message: str
    date: str
    value: float | None = None
    threshold: float | None = None
    severity: str = DEFAULT_SEVERITY
    fire_count: int = 1


@dataclass(slots=True)
class AlertEvaluation:
    """Outcome of evaluating a condition set against the store."""

    evaluated: int
    fired: list[Alert] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    already_active: int = 0
    cooldown_held: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluated": self.evaluated,
            "fired": [
                {
                    "alert_key": a.alert_key,
                    "symbol": a.symbol,
                    "condition": a.condition,
                    "message": a.message,
                    "date": a.date,
                    "value": a.value,
                    "threshold": a.threshold,
                    "severity": a.severity,
                    "fire_count": a.fire_count,
                }
                for a in self.fired
            ],
            "rejected": self.rejected,
            "already_active": self.already_active,
            "cooldown_held": self.cooldown_held,
        }


def make_alert_key(condition: dict[str, Any]) -> str:
    """Stable dedup key: condition + symbol + params.

    The same condition with a *different* threshold is a different alert, so
    canonical params are part of the key; the symbol is upper-cased so case
    variants of one symbol share a key.
    """
    symbol = str(condition.get("symbol") or "MARKET").upper()
    params = condition.get("params") or {}
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    payload = f"{condition.get('key')}|{symbol}|{canonical}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def validate_condition(condition: dict[str, Any]) -> list[str]:
    """Problems with one condition definition; empty list means usable."""
    problems: list[str] = []
    key = condition.get("key")
    if key not in _CONDITION_KEYS:
        problems.append(f"unknown condition {key!r}; known: {', '.join(_CONDITION_KEYS)}")
        return problems
    symbol = str(condition.get("symbol") or "").upper()
    params = condition.get("params") or {}
    if key != "regime_change" and not symbol:
        problems.append(f"{key!r} needs a 'symbol'")
    if key in ("price_above", "price_below") and "threshold" not in params:
        problems.append(f"{key!r} needs params.threshold")
    if key == "volume_spike" and "multiple" not in params:
        problems.append("volume_spike needs params.multiple")
    if key in ("momentum_above", "momentum_below") and "pct" not in params:
        problems.append(f"{key!r} needs params.pct")
    severity = condition.get("severity")
    if severity is not None and severity not in SEVERITIES:
        problems.append(f"severity must be one of {', '.join(SEVERITIES)}; got {severity!r}")
    cooldown = condition.get("cooldown_minutes")
    if cooldown is not None and (
        not isinstance(cooldown, int) or isinstance(cooldown, bool) or cooldown < 0
    ):
        problems.append(f"cooldown_minutes must be a non-negative integer; got {cooldown!r}")
    return problems


def condition_severity(condition: dict[str, Any]) -> str:
    """The condition's declared severity, defaulting to ``warning``."""
    sev = condition.get("severity")
    return sev if sev in SEVERITIES else DEFAULT_SEVERITY


def condition_cooldown(condition: dict[str, Any]) -> int | None:
    """Minutes before a fired condition may fire again.

    ``None`` (the default) keeps the original contract: an alert re-arms only
    when the history is cleared. ``0`` re-arms on the next evaluation.
    """
    cooldown = condition.get("cooldown_minutes")
    if cooldown is None:
        return None
    if not isinstance(cooldown, int) or isinstance(cooldown, bool) or cooldown < 0:
        return None
    return int(cooldown)


def alert_is_active(conn: sqlite3.Connection, alert_key: str, symbol: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM alert_history WHERE alert_key = ? AND symbol = ?", (alert_key, symbol)
    ).fetchone()
    return row is not None


def alert_last_fired(conn: sqlite3.Connection, alert_key: str, symbol: str) -> str | None:
    """The ``created_at`` of an existing alert row, or ``None``."""
    row = conn.execute(
        "SELECT created_at FROM alert_history WHERE alert_key = ? AND symbol = ?",
        (alert_key, symbol),
    ).fetchone()
    return row[0] if row else None


def cooldown_elapsed(
    last_fired: str | None, cooldown_minutes: int | None, now: pd.Timestamp | None = None
) -> bool:
    """Whether a condition may fire again given its cooldown.

    ``cooldown_minutes is None`` → never elapsed (the original once-until-cleared
    contract). A row with an unparseable timestamp is treated as *not* elapsed,
    so a corrupt value can only suppress an alert, never spam one.
    """
    if last_fired is None:
        return True
    if cooldown_minutes is None:
        return False
    try:
        previous = pd.Timestamp(last_fired)
    except (ValueError, TypeError):
        return False
    if previous.tzinfo is None:
        previous = previous.tz_localize("UTC")
    current = now if now is not None else pd.Timestamp.now(tz="UTC")
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    return bool(current - previous >= pd.Timedelta(minutes=cooldown_minutes))


def alert_history_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM alert_history").fetchone()[0])


def _last_bars(store: Any, symbol: str) -> pd.DataFrame | None:
    try:
        df = store.get_bars(symbol.upper())
    except Exception:
        return None
    if df is None or df.empty or len(df) < HIGH_LOW_WINDOW:
        return None
    return df.sort_values("trading_date").reset_index(drop=True)


def _condition_is_true(
    store: Any, condition: dict[str, Any]
) -> tuple[bool, str, float | None, float | None]:
    """Evaluate one condition. Returns (true, explanation, value, threshold)."""
    key = condition["key"]
    params = condition.get("params") or {}
    symbol = str(condition.get("symbol") or "").upper()

    if key == "regime_change":
        from megatool.regime import detect_regimes

        closes = store.all_closes()
        result = detect_regimes(closes)
        if result.status != "ok" or len(result.history) < 2:
            return False, "market history too short for a regime comparison", None, None
        last, prev = result.history[-1], result.history[-2]
        changed = (
            last["trend"] != prev["trend"]
            or last["volatility"] != prev["volatility"]
            or last["momentum"] != prev["momentum"]
        )
        if not changed:
            return (
                False,
                f"market regime unchanged at {last['trend']}/{last['volatility']}/{last['momentum']}",
                None,
                None,
            )
        msg = (
            f"Market regime changed on {last['date']}: "
            f"{prev['trend']}/{prev['volatility']}/{prev['momentum']} → "
            f"{last['trend']}/{last['volatility']}/{last['momentum']}"
        )
        return True, msg, None, None

    df = _last_bars(store, symbol)
    if df is None:
        return (
            False,
            f"{symbol}: not enough stored history (needs {HIGH_LOW_WINDOW} bars)",
            None,
            None,
        )
    last = df.iloc[-1]
    date = str(last["trading_date"])[:10]
    close = float(last["close"])

    if key in ("price_above", "price_below"):
        threshold = float(params["threshold"])
        if key == "price_above" and close > threshold:
            return (
                True,
                f"{symbol} closed at {close}, above the {threshold} threshold ({date})",
                close,
                threshold,
            )
        if key == "price_below" and close < threshold:
            return (
                True,
                f"{symbol} closed at {close}, below the {threshold} threshold ({date})",
                close,
                threshold,
            )
        return False, f"{symbol} close {close} did not cross {threshold}", close, threshold

    if key == "volume_sppike":
        multiple = float(params["multiple"])
        vol = float(last["volume"])
        med = float(df["volume"].tail(VOLUME_WINDOW).median())
        if med > 0 and vol >= multiple * med:
            return (
                True,
                (
                    f"{symbol} volume {vol:,.0f} is {vol / med:.1f}× its 20-session median "
                    f"({med:,.0f}) on {date}"
                ),
                vol,
                multiple * med,
            )
        return (
            False,
            f"{symbol} volume {vol:,.0f} below {multiple}× median {med:,.0f}",
            vol,
            multiple * med,
        )

    if key == "volume_spike":
        multiple = float(params["multiple"])
        vol = float(last["volume"])
        med = float(df["volume"].tail(VOLUME_WINDOW).median())
        if med > 0 and vol >= multiple * med:
            return (
                True,
                (
                    f"{symbol} volume {vol:,.0f} is {vol / med:.1f}× its 20-session median "
                    f"({med:,.0f}) on {date}"
                ),
                vol,
                multiple * med,
            )
        return (
            False,
            f"{symbol} volume {vol:,.0f} below {multiple}× median {med:,.0f}",
            vol,
            multiple * med,
        )

    if key in ("momentum_above", "momentum_below"):
        pct = float(params["pct"]) / 100.0
        trail = df["close"].iloc[-MOMENTUM_WINDOW - 1 :]
        if len(trail) < 2:
            return False, f"{symbol}: not enough bars for a momentum window", None, None
        ret = float(df["close"].iloc[-1] / trail.iloc[0] - 1.0)
        if key == "momentum_above" and ret > pct:
            return (
                True,
                f"{symbol} returned {ret:+.1%} over {len(trail) - 1} sessions, above {pct:+.0%} ({date})",
                ret,
                pct,
            )
        if key == "momentum_below" and ret < -pct:
            return (
                True,
                f"{symbol} returned {ret:+.1%} over {len(trail) - 1} sessions, below -{pct:.0%} ({date})",
                ret,
                -pct,
            )
        return False, f"{symbol} trailing return {ret:+.1%} inside the ±{pct:.0%} band", ret, pct

    if key in ("new_high", "new_low"):
        window = df["close"].iloc[-HIGH_LOW_WINDOW:]
        extreme = float(window.max()) if key == "new_high" else float(window.min())
        hit = close >= extreme if key == "new_high" else close <= extreme
        if hit:
            word = "high" if key == "new_high" else "low"
            return (
                True,
                (
                    f"{symbol} closed at {close}, a {HIGH_LOW_WINDOW}-session {word} "
                    f"(window extreme {extreme}, {date})"
                ),
                close,
                extreme,
            )
        return (
            False,
            f"{symbol} close {close} is not a {HIGH_LOW_WINDOW}-session extreme",
            close,
            extreme,
        )

    return False, f"unhandled condition {key!r}", None, None


def evaluate_conditions(
    store: Any,
    conn: sqlite3.Connection,
    conditions: list[dict[str, Any]],
    now: pd.Timestamp | None = None,
) -> AlertEvaluation:
    """Evaluate conditions; firings are recorded in alert_history.

    Dedup contract (the table's ``UNIQUE (alert_key, symbol)``): a condition
    with a history row fires again only when its declared ``cooldown_minutes``
    has elapsed — and with no cooldown declared, never again until the owner
    clears the history (``DELETE /api/alerts/clear``). A re-fire **updates** the
    existing row (last-fired time, message, severity) and increments
    ``fire_count`` rather than inserting a second row, so the table stays one
    row per (condition, symbol) and the count is an explicit field.

    ``now`` is injectable for tests; alerted timestamps are stored in UTC.
    """
    current = now if now is not None else pd.Timestamp.now(tz="UTC")
    stamp = current.isoformat(timespec="seconds")
    result = AlertEvaluation(evaluated=0)
    for condition in conditions:
        problems = validate_condition(condition)
        if problems:
            result.rejected.append({"condition": condition, "problems": problems})
            continue
        result.evaluated += 1
        key = make_alert_key(condition)
        symbol = str(condition.get("symbol") or "MARKET").upper()
        severity = condition_severity(condition)
        cooldown = condition_cooldown(condition)
        last_fired = alert_last_fired(conn, key, symbol)
        if last_fired is not None:
            if not cooldown_elapsed(last_fired, cooldown, current):
                result.already_active += 1
                continue
            result.cooldown_held += 1 if cooldown is not None else 0
        is_true, message, value, threshold = _condition_is_true(store, condition)
        if not is_true:
            continue
        if last_fired is None:
            conn.execute(
                "INSERT INTO alert_history "
                "(alert_key, symbol, message, created_at, severity, fire_count) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                (key, symbol, message, stamp, severity),
            )
            fire_count = 1
        else:
            conn.execute(
                "UPDATE alert_history SET message = ?, created_at = ?, severity = ?, "
                "fire_count = fire_count + 1, acknowledged_at = NULL "
                "WHERE alert_key = ? AND symbol = ?",
                (message, stamp, severity, key, symbol),
            )
            row = conn.execute(
                "SELECT fire_count FROM alert_history WHERE alert_key = ? AND symbol = ?",
                (key, symbol),
            ).fetchone()
            fire_count = int(row[0]) if row else 2
        conn.commit()
        result.fired.append(
            Alert(
                alert_key=key,
                symbol=symbol,
                condition=str(condition.get("key")),
                message=message,
                date=str(current.date()),
                value=value,
                threshold=threshold,
                severity=severity,
                fire_count=fire_count,
            )
        )
    return result


def list_alerts(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    """Newest-first alert history rows, including severity and acknowledgement."""
    rows = conn.execute(
        "SELECT id, alert_key, symbol, message, created_at, severity, fire_count, "
        "acknowledged_at FROM alert_history ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "alert_key": r[1],
            "symbol": r[2],
            "message": r[3],
            "created_at": r[4],
            "severity": r[5] if r[5] in SEVERITIES else DEFAULT_SEVERITY,
            "fire_count": int(r[6] or 1),
            "acknowledged_at": r[7],
            "acknowledged": r[7] is not None,
        }
        for r in rows
    ]


def acknowledge_alerts(
    conn: sqlite3.Connection,
    *,
    alert_ids: list[int] | None = None,
    all_alerts: bool = False,
    now: pd.Timestamp | None = None,
) -> int:
    """Mark alerts acknowledged. Returns how many rows changed.

    Acknowledgement is bookkeeping, not removal: it silences the alert in the
    UI and records when the owner saw it. It does **not** change the cooldown
    or dedup key, so an acknowledged alert cannot be made to re-arm by acking.
    """
    stamp = (now if now is not None else pd.Timestamp.now(tz="UTC")).isoformat(timespec="seconds")
    if all_alerts:
        cur = conn.execute(
            "UPDATE alert_history SET acknowledged_at = ? WHERE acknowledged_at IS NULL", (stamp,)
        )
    elif alert_ids:
        marks = ",".join("?" for _ in alert_ids)
        cur = conn.execute(
            f"UPDATE alert_history SET acknowledged_at = ? "
            f"WHERE acknowledged_at IS NULL AND id IN ({marks})",
            [stamp, *alert_ids],
        )
    else:
        return 0
    conn.commit()
    return int(cur.rowcount or 0)


def clear_alerts(conn: sqlite3.Connection) -> int:
    """Clear alert history so conditions can re-arm. Owner-invoked only."""
    before = alert_history_count(conn)
    conn.execute("DELETE FROM alert_history")
    conn.commit()
    return before


__all__ = [
    "DEFAULT_SEVERITY",
    "SEVERITIES",
    "Alert",
    "AlertEvaluation",
    "acknowledge_alerts",
    "alert_history_count",
    "clear_alerts",
    "condition_cooldown",
    "condition_severity",
    "cooldown_elapsed",
    "evaluate_conditions",
    "list_alerts",
    "make_alert_key",
    "validate_condition",
    "DISCLAIMER",
]
