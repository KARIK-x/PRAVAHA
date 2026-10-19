"""Canonical internal schemas.

These are the single contract every data source must produce. Source-specific
field names are normalised here so the rest of the application never has to
know which adapter supplied a record.

Units and types are explicit:
* prices are in NPR per share (float)
* quantity is in shares (int)
* turnover (traded_amount) is in NPR (float)
* dates are pandas Timestamps at day granularity (NEPSE has no intraday history)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DataSource(StrEnum):
    """Provenance label attached to every stored record."""

    GITHUB_NEPSE_DATA = "github.com/Aabishkar2/nepse-data"
    NEPALSTOCK_OFFICIAL = "nepalstock.com/api/nots"
    GONEPSE = "go-nepse (github.com/voidarchive/go-nepse)"
    LOCAL_IMPORT = "local-file-import"
    SYNTHETIC_TEST = "SYNTHETIC-TEST-FIXTURE"


class ValidationStatus(StrEnum):
    VALID = "valid"
    SUSPECT = "suspect"  # flagged, retained - may be a genuine market event
    INVALID = "invalid"  # rejected by a hard rule


class AdjustmentStatus(StrEnum):
    """Corporate-action adjustment state of a price series."""

    UNADJUSTED = "unadjusted"
    PARTIALLY_ADJUSTED = "partially_adjusted"
    FULLY_ADJUSTED = "fully_adjusted"
    UNKNOWN = "unknown"


class PriceBar(BaseModel):
    """One security's OHLCV for one trading day.

    Optional fields stay ``None`` when a source does not supply them; they are
    never invented (Rule 6).
    """

    model_config = {"extra": "forbid"}

    symbol: str = Field(description="Trading symbol, e.g. NABIL")
    trading_date: date = Field(description="NEPSE trading date (Asia/Kathmandu)")
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = Field(default=None, description="traded_quantity, shares")
    turnover: float | None = Field(default=None, description="traded_amount, NPR")
    percent_change: float | None = Field(default=None, description="pct change vs prior close")
    transactions: int | None = Field(default=None, description="transaction count if supplied")

    source: DataSource
    source_url: str | None = None
    retrieved_at: datetime
    validation_status: ValidationStatus = ValidationStatus.VALID
    adjustment_status: AdjustmentStatus = AdjustmentStatus.UNADJUSTED
    flags: list[str] = Field(default_factory=list)

    @field_validator("symbol")
    @classmethod
    def _normalise_symbol(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("symbol must not be empty")
        return v

    @field_validator("open", "high", "low", "close")
    @classmethod
    def _positive_price(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("price must not be negative")
        return v


class Security(BaseModel):
    """A listed security in the market universe (security master)."""

    model_config = {"extra": "forbid"}

    symbol: str
    name: str | None = None
    sector: str | None = None
    instrument_type: str | None = None
    listed_date: date | None = None
    delisted: bool = False
    source: DataSource
    first_seen: datetime | None = None
    last_updated: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def _normalise_symbol(cls, v: str) -> str:
        return v.strip().upper()


class IngestResult(BaseModel):
    """Outcome of one ingestion run - always recorded, success or failure."""

    model_config = {"extra": "allow"}

    source: DataSource
    started_at: datetime
    finished_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Overwritten with the true completion time at the end of a run.",
    )
    symbols_requested: int = 0
    symbols_succeeded: int = 0
    symbols_failed: int = 0
    rows_read: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_skipped_duplicate: int = 0
    rows_flagged: int = 0
    rows_rejected: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    dataset_label: str = ""
    coverage_start: date | None = None
    coverage_end: date | None = None
    synthetic: bool = False

    @property
    def ok(self) -> bool:
        return self.symbols_failed == 0 and not self.errors


def bar_to_row(b: PriceBar) -> dict[str, Any]:
    """Flatten a PriceBar into the DuckDB ``price_bars`` row layout."""
    return {
        "symbol": b.symbol,
        "trading_date": b.trading_date,
        "open": b.open,
        "high": b.high,
        "low": b.low,
        "close": b.close,
        "volume": b.volume,
        "turnover": b.turnover,
        "percent_change": b.percent_change,
        "transactions": b.transactions,
        "source": b.source.value,
        "source_url": b.source_url,
        "retrieved_at": b.retrieved_at,
        "validation_status": b.validation_status.value,
        "adjustment_status": b.adjustment_status.value,
        "flags": ",".join(b.flags),
    }
