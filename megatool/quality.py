"""Data-quality checks applied to every ingested price series.

Design principles (Section 5.5):
* Flag suspicious records rather than deleting them - a large gap or a sharp
  discontinuity can be a genuine market event (split, suspension, circuit hit).
* Hard-fail only on physically impossible values (negative price, high < low).
* Every flag is a short machine-readable token plus a human explanation.

Nothing here uses future observations: checks are per-row, or compare a row only
against *earlier* rows in the same series.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from megatool.models import ValidationStatus

# --- Flag tokens (stable strings; the UI and tests key off these) ---
F_MISSING_OHLC = "missing_ohlc"
F_NEGATIVE = "negative_value"
F_HIGH_LOW_INVERTED = "high_low_inverted"
F_CLOSE_OUTSIDE = "close_outside_range"
F_OPEN_OUTSIDE = "open_outside_range"
F_DUPLICATE_DATE = "duplicate_date"
F_NON_MONOTONIC_DATE = "non_monotonic_date"
F_ZERO_PRICE = "zero_price"
F_VOL_SPIKE = "volume_spike"
F_PRICE_JUMP = "price_jump"
F_STALE = "stale_series"
F_MISSING_VOLUME = "missing_volume"
F_NON_POSITIVE = "non_positive_price"

#: A day-on-day close move larger than this fraction is flagged for review.
#: NEPSE applies a ~10% daily band for most scrips, so 25% is well beyond it.
PRICE_JUMP_THRESHOLD = 0.25

#: Volume this many times the trailing 20-day median is flagged as unusual.
VOLUME_SPIKE_MULTIPLE = 8.0

#: Minimum prior observations before a trailing volume baseline is meaningful.
MIN_BASELINE_DAYS = 10

#: Series older than this many days relative to the reference date is stale.
STALE_AFTER_DAYS = 7

FLAG_HELP: dict[str, str] = {
    F_MISSING_OHLC: "No usable OHLC values in the row.",
    F_NEGATIVE: "A price or volume was negative - physically impossible.",
    F_HIGH_LOW_INVERTED: "High is below low.",
    F_CLOSE_OUTSIDE: "Close falls outside the day's low-high range.",
    F_OPEN_OUTSIDE: "Open falls outside the day's low-high range.",
    F_DUPLICATE_DATE: "Another row already exists for this trading date.",
    F_NON_MONOTONIC_DATE: "Row is not strictly after the previous row's date.",
    F_ZERO_PRICE: "High is zero.",
    F_NON_POSITIVE: "A price field (open/high/low/close) was zero - impossible for a traded price.",
    F_VOL_SPIKE: "Volume exceeded 8x the trailing 20-day median volume.",
    F_PRICE_JUMP: "Absolute close-to-close move exceeded 25% - verify against a "
    "corporate action (split/bonus) before trusting the series.",
    F_STALE: "Latest bar is older than the expected freshness window.",
    F_MISSING_VOLUME: "Volume was not supplied by the source.",
}

#: Severity of each flag. Not every flag means the row is untrustworthy.
#:
#: * ``hard``  - physically impossible; the row is INVALID.
#: * ``review``- suspicious enough to warrant a human look; the row is SUSPECT.
#: * ``info``  - a real characteristic worth surfacing, but not a reason to
#:               distrust the row. The row keeps its VALID status.
#:
#: ``open_outside_range`` is deliberately ``info``. Measured on 2026-10-11 across
#: NABIL/NICL/NMB (9,561 real rows), the source's ``open`` sits outside the
#: day's high-low range in ~15% of rows while ``close`` is inside in all but 2.
#: That is a systematic property of the source's open column, not 1,500
#: independent corruptions, so flagging all of them as SUSPECT would bury the
#: genuinely alarming flags in noise.
FLAG_SEVERITY: dict[str, str] = {
    F_MISSING_OHLC: "hard",
    F_NEGATIVE: "hard",
    F_HIGH_LOW_INVERTED: "hard",
    F_ZERO_PRICE: "hard",
    F_CLOSE_OUTSIDE: "review",
    F_NON_POSITIVE: "review",
    F_DUPLICATE_DATE: "review",
    F_NON_MONOTONIC_DATE: "review",
    F_VOL_SPIKE: "review",
    F_PRICE_JUMP: "review",
    F_OPEN_OUTSIDE: "info",
    F_MISSING_VOLUME: "info",
    F_STALE: "info",
}

SEVERITY_RANK = {"hard": 2, "review": 1, "info": 0}


def max_severity(flags: list[str]) -> int:
    """Highest severity rank among ``flags`` (0 = info only, 2 = hard)."""
    return max((SEVERITY_RANK[FLAG_SEVERITY.get(f, "review")] for f in flags), default=-1)


def explain(flags: list[str]) -> list[str]:
    """Human-readable explanations for a list of flag tokens."""
    return [FLAG_HELP.get(f, f) for f in flags]


@dataclass(slots=True)
class QualityReport:
    """Aggregate result of validating one symbol's history."""

    symbol: str
    rows_checked: int = 0
    valid: int = 0
    suspect: int = 0
    invalid: int = 0
    info_flagged: int = 0
    flag_counts: dict[str, int] = field(default_factory=dict)
    first_flagged_row: int | None = None
    stale_days: int | None = None

    def add(self, flags: list[str], status: ValidationStatus, row_index: int) -> None:
        self.rows_checked += 1
        has_info = False
        for f in flags:
            self.flag_counts[f] = self.flag_counts.get(f, 0) + 1
            if FLAG_SEVERITY.get(f) == "info":
                has_info = True
        if has_info:
            self.info_flagged += 1

        if status is ValidationStatus.VALID:
            self.valid += 1
            return

        if status is ValidationStatus.SUSPECT:
            self.suspect += 1
        else:
            self.invalid += 1
        if self.first_flagged_row is None:
            self.first_flagged_row = row_index

    @property
    def clean(self) -> bool:
        return self.suspect == 0 and self.invalid == 0

    def as_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "rows_checked": self.rows_checked,
            "valid": self.valid,
            "suspect": self.suspect,
            "invalid": self.invalid,
            "info_flagged": self.info_flagged,
            "clean": self.clean,
            "flag_counts": dict(sorted(self.flag_counts.items())),
            "flag_severity": {k: FLAG_SEVERITY[k] for k in self.flag_counts if k in FLAG_SEVERITY},
            "stale_days": self.stale_days,
            "flag_help": {k: FLAG_HELP[k] for k in self.flag_counts if k in FLAG_HELP},
        }


def validate_bar(
    open_: float | None,
    high: float | None,
    low: float | None,
    close: float | None,
    volume: int | None = None,
) -> tuple[list[str], ValidationStatus]:
    """Validate a single bar using only that bar's own values.

    Takes raw primitives so the checker never has to manufacture a ``PriceBar``
    (which would require inventing provenance metadata).
    """
    flags: list[str] = []

    if all(p is None for p in (open_, high, low, close)):
        flags.append(F_MISSING_OHLC)
        return flags, ValidationStatus.INVALID

    if any(p is not None and p < 0 for p in (open_, high, low, close)) or (
        volume is not None and volume < 0
    ):
        flags.append(F_NEGATIVE)
        return flags, ValidationStatus.INVALID

    if high is not None and low is not None and high < low:
        flags.append(F_HIGH_LOW_INVERTED)
        return flags, ValidationStatus.INVALID

    if high is not None and high == 0:
        flags.append(F_ZERO_PRICE)

    # A zero in any OHLC field is physically impossible for a traded
    # price. Before B-21 only ``high == 0`` was checked (F_ZERO_PRICE),
    # so a zero ``open``/``low``/``close`` was invisible: it reached
    # every calculation and could drag an all-time low, ATR, %B or a
    # support level to zero. The row is flagged, not excluded - whether
    # zero prices should be treated as invalid is the owner's data-policy
    # decision (register R1: note B-20's 2026-10-13 ruling covered the
    # open=previous-close convention, and whether it ALSO covers
    # F_NON_POSITIVE is exactly the open question). See B-21 / T-31.
    if any(p is not None and p == 0 for p in (open_, high, low, close)):
        flags.append(F_NON_POSITIVE)

    # Range containment is only checkable when both bounds are present.
    if low is not None and high is not None:
        if close is not None and not (low <= close <= high):
            flags.append(F_CLOSE_OUTSIDE)
        if open_ is not None and not (low <= open_ <= high):
            flags.append(F_OPEN_OUTSIDE)

    if volume is None:
        flags.append(F_MISSING_VOLUME)

    status = _status_from_flags(flags)
    return flags, status


def _status_from_flags(flags: list[str]) -> ValidationStatus:
    """Map a flag list to a status using :data:`FLAG_SEVERITY`."""
    if not flags:
        return ValidationStatus.VALID
    rank = max_severity(flags)
    if rank >= SEVERITY_RANK["hard"]:
        return ValidationStatus.INVALID
    if rank >= SEVERITY_RANK["review"]:
        return ValidationStatus.SUSPECT
    return ValidationStatus.VALID


def validate_series(
    df: pd.DataFrame, reference_date: pd.Timestamp | None = None
) -> tuple[pd.DataFrame, QualityReport]:
    """Validate one symbol's OHLCV frame and annotate it in place.

    Parameters
    ----------
    df:
        Columns ``trading_date, open, high, low, close, volume`` (others are
        tolerated), any order; re-sorted ascending internally.
    reference_date:
        Reference for staleness. Defaults to the series' own last date, so the
        report does not silently depend on the wall clock.

    Returns
    -------
    annotated_df, report
    """
    df = df.sort_values("trading_date").reset_index(drop=True)
    symbol = str(df["symbol"].iloc[0]) if len(df) and "symbol" in df.columns else "?"

    report = QualityReport(symbol=symbol)
    statuses: list[str] = []
    flags_col: list[str] = []

    has_rows = len(df) > 0
    if reference_date is None:
        ref_date = (
            pd.Timestamp(df["trading_date"].max())
            if has_rows
            else pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
        )
    else:
        ref_date = pd.Timestamp(reference_date)

    prev_close: float | None = None
    baseline_vol: list[float] = []
    seen_dates: set[pd.Timestamp] = set()
    last_date: pd.Timestamp | None = None

    for idx, row in df.iterrows():
        o = _opt_float(row.get("open"))
        h = _opt_float(row.get("high"))
        lo = _opt_float(row.get("low"))
        c = _opt_float(row.get("close"))
        v = _opt_int(row.get("volume"))

        flags, status = validate_bar(o, h, lo, c, v)

        d = pd.Timestamp(row["trading_date"])
        if d in seen_dates:
            flags.append(F_DUPLICATE_DATE)
        seen_dates.add(d)
        if last_date is not None and d <= last_date:
            flags.append(F_NON_MONOTONIC_DATE)
        last_date = d

        # Day-on-day discontinuity: informational, never auto-deleted.
        if (
            c is not None
            and prev_close not in (None, 0)
            and abs(c / prev_close - 1.0) > PRICE_JUMP_THRESHOLD
        ):
            flags.append(F_PRICE_JUMP)

        # Unusual volume vs a baseline built only from earlier rows.
        if v is not None:
            if len(baseline_vol) >= MIN_BASELINE_DAYS:
                med = float(pd.Series(baseline_vol[-20:]).median())
                if med > 0 and v > VOLUME_SPIKE_MULTIPLE * med:
                    flags.append(F_VOL_SPIKE)
            baseline_vol.append(float(v))

        if c is not None:
            prev_close = c

        # Recompute once, now that every flag for this row is known.
        status = _status_from_flags(flags)

        report.add(flags, status, idx)
        statuses.append(status.value)
        flags_col.append(",".join(flags))

    if has_rows:
        age_days = (ref_date - pd.Timestamp(df["trading_date"].max())).days
        if age_days > STALE_AFTER_DAYS:
            report.stale_days = age_days
            report.flag_counts[F_STALE] = 1

    out = df.copy()
    out["validation_status"] = statuses
    out["flags"] = flags_col
    return out, report


def _opt_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _opt_int(v: object) -> int | None:
    f = _opt_float(v)
    return None if f is None else int(round(f))
