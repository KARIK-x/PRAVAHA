"""Local file import adapter.

This is the guaranteed path: it always works, needs no network, and is how the
owner can load anything - a broker export, a spreadsheet, a dataset snapshot.

HONESTY RULE
------------
Imported files are stamped ``source = local-file-import`` and keep the original
filename plus the import timestamp on every row. A file can never masquerade as
an exchange feed.

SUPPORTED LAYOUTS
-----------------
* ``symbol`` column present -> multi-symbol file.
* no ``symbol`` column -> single-symbol file; the symbol is supplied by the
  caller (or inferred from the filename).

Column aliases cover the common NEPSE export spellings.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from megatool.datasources.base import BaseAdapter, SourceConfig, SourceError
from megatool.models import DataSource

#: canonical -> accepted source spellings (lowered, non-alnum collapsed).
_ALIASES: dict[str, tuple[str, ...]] = {
    "trading_date": (
        "published_date", "date", "trading date", "trade date", "nepse date",
        "business date", "datetime",
    ),
    "open": ("open", "opening", "open price", "l_open", "open价"),
    "high": ("high", "high price", "l_high", "max"),
    "low": ("low", "low price", "l_low", "min"),
    "close": ("close", "closing", "close price", "l_close", "last", "closing price"),
    "volume": ("volume", "traded_quantity", "traded quantity", "qty", "quantity",
               "shares traded", "units"),
    "turnover": ("turnover", "traded_amount", "traded amount", "amount",
                 "transaction amount", "revenue"),
    "percent_change": ("percent_change", "per_change", "per change", "pct change",
                       "% change", "change", "change_percent"),
    "transactions": ("transactions", "trades", "no_of_transactions", "deal_count"),
    "symbol": ("symbol", "scrip", "security", "code", "ticker", "stock"),
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9%]+", " ", str(name).strip().lower()).strip()


def _build_alias_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for canonical, alts in _ALIASES.items():
        for a in alts:
            idx[_norm(a)] = canonical
        idx[_norm(canonical)] = canonical
    return idx


ALIAS_INDEX = _build_alias_index()


def canonicalise_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Rename recognised columns to the canonical schema.

    Returns the renamed frame and a mapping of ``original -> canonical`` so the
    caller can report what it understood. Unrecognised columns are preserved.
    """
    mapping: dict[str, str] = {}
    rename: dict[str, str] = {}
    for col in df.columns:
        key = _norm(col)
        if key in ALIAS_INDEX:
            canonical = ALIAS_INDEX[key]
            if canonical not in mapping.values():
                rename[col] = canonical
                mapping[col] = canonical
    return df.rename(columns=rename), mapping


class LocalFileAdapter(BaseAdapter):
    """Imports OHLCV history from a CSV/TSV/Parquet file on this machine."""

    def __init__(self, path: Path | str, symbol: str | None = None):
        self.path = Path(path)
        if not self.path.exists():
            raise SourceError(f"file does not exist: {self.path}")
        self.forced_symbol = symbol.upper().strip() if symbol else None
        self._mapping: dict[str, str] = {}
        self.config = SourceConfig(
            source_id=DataSource.LOCAL_IMPORT,
            label=f"Local file import ({self.path.name})",
            access_method="local-file",
            base_url=None,
            requires_auth=False,
            update_frequency="on demand",
            fields_supplied=(),
            fields_missing=(),
            terms_note="Owner-supplied file. Origin is the owner's responsibility.",
            extra={"filename": self.path.name, "bytes": self.path.stat().st_size},
        )

    def list_symbols(self) -> list[str]:
        df = self._read()
        if "symbol" in df.columns:
            return sorted(str(s).upper().strip() for s in df["symbol"].dropna().unique())
        if self.forced_symbol:
            return [self.forced_symbol]
        raise SourceError(
            "file has no symbol column and no symbol was supplied to the importer"
        )

    def fetch_history(self, symbol: str) -> pd.DataFrame:
        df = self._read()
        if "symbol" in df.columns:
            df = df[df["symbol"].astype(str).str.upper().str.strip() == symbol.upper()]
        elif self.forced_symbol and symbol.upper() != self.forced_symbol:
            raise SourceError(
                f"file was imported as {self.forced_symbol}, not {symbol.upper()}"
            )
        if df.empty:
            raise SourceError(f"no rows for {symbol} in {self.path.name}")
        return self.normalise(df, symbol)

    def _read(self) -> pd.DataFrame:
        suffix = self.path.suffix.lower()
        try:
            if suffix in (".parquet", ".pq"):
                df = pd.read_parquet(self.path)
            elif suffix == ".tsv":
                df = pd.read_csv(self.path, sep="\t")
            elif suffix == ".txt":
                # Sniff the delimiter; text exports vary.
                df = pd.read_csv(self.path, sep=None, engine="python")
            else:
                df = pd.read_csv(self.path)
        except Exception as exc:
            raise SourceError(f"could not read {self.path.name}: {exc}") from exc

        df, mapping = canonicalise_columns(df)
        self._mapping = mapping
        return df

    @property
    def column_mapping(self) -> dict[str, str]:
        return dict(self._mapping)

    def normalise(self, raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
        if "trading_date" not in raw.columns:
            raise SourceError(
                f"{self.path.name}: no date column recognised. "
                f"Header seen: {list(raw.columns)}"
            )
        df = raw.copy()
        df["trading_date"] = pd.to_datetime(df["trading_date"], errors="coerce")
        df = df.dropna(subset=["trading_date"])

        if "close" not in df.columns:
            raise SourceError(
                f"{self.path.name}: no close-price column recognised. "
                f"Header seen: {list(raw.columns)}"
            )

        for col in ("open", "high", "low", "close", "turnover", "percent_change"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")
        if "transactions" in df.columns:
            df["transactions"] = pd.to_numeric(df["transactions"], errors="coerce").astype("Int64")

        df["symbol"] = symbol.upper()
        df = df.sort_values("trading_date").drop_duplicates("trading_date", keep="last")
        keep = [
            "symbol", "trading_date", "open", "high", "low", "close",
            "volume", "turnover", "percent_change", "transactions",
        ]
        return df[[c for c in keep if c in df.columns]].reset_index(drop=True)

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "filename": self.path.name,
            "column_mapping": self.column_mapping,
        }
