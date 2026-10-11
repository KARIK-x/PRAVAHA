"""Source-adapter contract.

Every adapter exposes the same shape so the ingestion pipeline never needs to
know where data came from. Each adapter declares its own timeouts, retry
behaviour and provenance label (Section 5.1).

Adapters return *raw* normalised ``PriceBar`` objects or DataFrames; validation
and persistence happen upstream in ``megatool.ingest``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from megatool.models import DataSource


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class SourceConfig:
    """Declared behaviour of a source - reviewed before any request is made."""

    source_id: DataSource
    label: str
    access_method: str  # http-get | http-post | local-file
    base_url: str | None = None
    timeout_seconds: float = 20.0
    max_retries: int = 3
    backoff_seconds: float = 1.0
    rate_limit_rps: float = 4.0
    requires_auth: bool = False
    auth_note: str = ""
    update_frequency: str = "daily"
    fields_supplied: tuple[str, ...] = ()
    fields_missing: tuple[str, ...] = ()
    terms_note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class SourceError(Exception):
    """Raised when a source cannot deliver. Carries a user-facing explanation."""


class SourceUnavailable(SourceError):
    """The source is reachable in principle but blocked for us right now."""


class BaseAdapter(ABC):
    """Abstract source adapter."""

    config: SourceConfig

    @abstractmethod
    def list_symbols(self) -> list[str]:
        """Return the symbols this adapter can currently serve."""

    @abstractmethod
    def fetch_history(self, symbol: str) -> pd.DataFrame:
        """Return one symbol's history as a canonical DataFrame.

        Must include: ``trading_date, open, high, low, close, volume``.
        May include: ``turnover, percent_change, transactions``.
        """

    def health(self) -> dict[str, Any]:
        """Cheap reachability check. Never raises."""
        try:
            syms = self.list_symbols()
            return {
                "source": self.config.source_id.value,
                "label": self.config.label,
                "available": True,
                "symbols": len(syms),
            }
        except SourceError as exc:
            return {
                "source": self.config.source_id.value,
                "label": self.config.label,
                "available": False,
                "reason": str(exc),
            }
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "source": self.config.source_id.value,
                "label": self.config.label,
                "available": False,
                "reason": f"unexpected error: {exc}",
            }

    def describe(self) -> dict[str, Any]:
        c = self.config
        return {
            "source": c.source_id.value,
            "label": c.label,
            "access_method": c.access_method,
            "base_url": c.base_url,
            "requires_auth": c.requires_auth,
            "auth_note": c.auth_note,
            "update_frequency": c.update_frequency,
            "timeout_seconds": c.timeout_seconds,
            "max_retries": c.max_retries,
            "rate_limit_rps": c.rate_limit_rps,
            "fields_supplied": list(c.fields_supplied),
            "fields_missing": list(c.fields_missing),
            "terms_note": c.terms_note,
        }


class _RateLimiter:
    """Simple monotonic-clock limiter; keeps public endpoints polite."""

    def __init__(self, rps: float):
        import time

        self._time = time.monotonic
        self._min_interval = 1.0 / rps if rps > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        import time

        if self._min_interval <= 0:
            return
        now = self._time()
        delta = now - self._last
        if delta < self._min_interval:
            time.sleep(self._min_interval - delta)
        self._last = self._time()
