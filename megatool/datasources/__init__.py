"""Adapter package: pluggable market-data sources."""

from megatool.datasources.base import (
    BaseAdapter,
    SourceConfig,
    SourceError,
    SourceUnavailable,
)

__all__ = ["BaseAdapter", "SourceConfig", "SourceError", "SourceUnavailable"]
