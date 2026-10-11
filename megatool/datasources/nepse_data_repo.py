"""Adapter for the public ``Aabishkar2/nepse-data`` GitHub dataset.

WHAT THIS IS
------------
A community-maintained, openly published CSV collection of NEPSE daily history:
one CSV per trading symbol, columns ``published_date, open, high, low, close,
per_change, traded_quantity, traded_amount, status``. Verified on 2026-10-11 to
carry real data through 2026-10-09 for NABIL, NICL and NMB.

ACCESS & ETIQUETTE
------------------
* Plain HTTPS GETs against raw.githubusercontent.com / api.github.com.
* No authentication, no cookies, no access-control bypass.
* Requests are rate-limited locally and served from a local cache when fresh,
  so we do not hammer GitHub (it is a free shared resource).
* No LICENSE file is published in that repository. It is therefore treated as
  third-party content used for private research, with attribution retained on
  every stored row. See docs/DATA_SOURCES.md for the open licensing question.

LIMITS (declared honestly)
--------------------------
* It is a *derived* dataset scraped from NEPSE, not the exchange's own feed.
  It can lag, and it can carry the scraper's own errors.
* No sector, no corporate actions, no fundamentals, no intraday data.
* Price series are UNADJUSTED. Bonus/split announcements are not published
  here, so apparent discontinuities must not be assumed to be splits.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from megatool.config import HTTP_BACKOFF_SECONDS, HTTP_MAX_RETRIES, HTTP_TIMEOUT_SECONDS, PATHS
from megatool.datasources.base import (
    BaseAdapter,
    SourceConfig,
    SourceError,
    SourceUnavailable,
    _RateLimiter,
    utcnow,
)
from megatool.models import DataSource

DEFAULT_OWNER = "Aabishkar2"
DEFAULT_REPO = "nepse-data"
DEFAULT_BRANCH = "main"

_RAW_COLUMNS = {
    "published_date": "trading_date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "per_change": "percent_change",
    "traded_quantity": "volume",
    "traded_amount": "turnover",
}


class NepseDataRepoAdapter(BaseAdapter):
    """Reads the public GitHub NEPSE CSV dataset, with a local file cache."""

    def __init__(
        self,
        owner: str = DEFAULT_OWNER,
        repo: str = DEFAULT_REPO,
        branch: str = DEFAULT_BRANCH,
        cache_dir: Path | None = None,
        cache_ttl_hours: float = 12.0,
        timeout: float = HTTP_TIMEOUT_SECONDS,
        max_retries: int = HTTP_MAX_RETRIES,
    ):
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.cache_dir = cache_dir or (PATHS.raw / "nepse_data_repo")
        self.cache_ttl_seconds = cache_ttl_hours * 3600.0
        self._limiter = _RateLimiter(4.0)
        self._symbols_cache: list[str] | None = None
        self.config = SourceConfig(
            source_id=DataSource.GITHUB_NEPSE_DATA,
            label="Public GitHub NEPSE daily dataset (community-maintained)",
            access_method="http-get",
            base_url=f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/data/company-wise/",
            timeout_seconds=timeout,
            max_retries=max_retries,
            backoff_seconds=HTTP_BACKOFF_SECONDS,
            rate_limit_rps=4.0,
            requires_auth=False,
            update_frequency="daily (upstream GitHub Actions)",
            fields_supplied=(
                "trading_date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
                "percent_change",
            ),
            fields_missing=(
                "transactions",
                "sector",
                "corporate_actions",
                "indices",
                "intraday",
            ),
            terms_note=(
                "Publicly downloadable repository; no LICENSE file published. "
                "Attribution retained per row. Used for private research only."
            ),
        )

    # ------------------------------------------------------------ transport
    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.config.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "MegaTool/0.1 (personal research; +local)"},
        )

    def _get(self, url: str, **params: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            self._limiter.wait()
            try:
                with self._client() as client:
                    resp = client.get(url, params=params or None)
                if resp.status_code == 200:
                    return resp
                if resp.status_code in (404,):
                    raise SourceError(f"not found: {url} (HTTP 404)")
                if resp.status_code in (403, 429):
                    # Back off harder; GitHub rate limits are transient.
                    last_exc = SourceUnavailable(
                        f"rate limited or forbidden (HTTP {resp.status_code}) for {url}"
                    )
                else:
                    last_exc = SourceError(f"HTTP {resp.status_code} for {url}")
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = SourceError(f"network error for {url}: {exc}")
            import time

            if attempt < self.config.max_retries:
                time.sleep(self.config.backoff_seconds * attempt)
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------- caching
    def _cache_path(self, symbol: str) -> Path:
        return self.cache_dir / f"{symbol.upper()}.csv"

    def _cache_is_fresh(self, path: Path) -> bool:
        return path.exists() and (utcnow().timestamp() - path.stat().st_mtime) < self.cache_ttl_seconds

    # --------------------------------------------------------------- API
    def list_symbols(self, use_cache: bool = True) -> list[str]:
        """Symbols available in the dataset, via the GitHub contents API."""
        if use_cache and self._symbols_cache:
            return list(self._symbols_cache)

        cached_index = self.cache_dir / "_symbols.json"
        if use_cache and cached_index.exists():
            try:
                data = json.loads(cached_index.read_text())
                if utcnow().timestamp() - data.get("_fetched_at", 0) < self.cache_ttl_seconds:
                    self._symbols_cache = data["symbols"]
                    return list(self._symbols_cache)
            except (json.JSONDecodeError, KeyError):
                pass

        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents/data/company-wise"
        try:
            resp = self._get(url, ref=self.branch)
        except SourceError:
            # Fall back to whatever symbol CSVs are already cached locally.
            local = sorted(p.stem for p in self.cache_dir.glob("*.csv"))
            if local:
                self._symbols_cache = local
                return list(local)
            raise

        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise SourceError(f"unexpected payload from {url}: {exc}") from exc

        if not isinstance(payload, list):
            raise SourceError(f"unexpected payload shape from {url}")

        symbols = sorted(
            item["name"][:-4]
            for item in payload
            if item.get("type") == "file" and item.get("name", "").endswith(".csv")
        )
        if not symbols:
            raise SourceError("dataset listed no CSV files")

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached_index.write_text(
            json.dumps({"symbols": symbols, "_fetched_at": utcnow().timestamp()})
        )
        self._symbols_cache = symbols
        return list(symbols)

    def csv_url(self, symbol: str) -> str:
        return f"{self.config.base_url}{symbol.upper()}.csv"

    def fetch_history(self, symbol: str, use_cache: bool = True) -> pd.DataFrame:
        """Download (or read from cache) one symbol's full history."""
        sym = symbol.upper().strip()
        path = self._cache_path(sym)

        if not (use_cache and self._cache_is_fresh(path)):
            url = self.csv_url(sym)
            resp = self._get(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(resp.content)

        try:
            raw = pd.read_csv(path)
        except Exception as exc:
            raise SourceError(f"could not parse cached CSV for {sym}: {exc}") from exc

        return self.normalise(raw, sym)

    def normalise(self, raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Map the source's column names onto the canonical schema."""
        missing = {"published_date", "close"} - set(raw.columns)
        if missing:
            raise SourceError(
                f"{symbol}: source CSV is missing expected columns {sorted(missing)}"
            )

        df = raw.rename(columns=_RAW_COLUMNS).copy()
        df["trading_date"] = pd.to_datetime(df["trading_date"], errors="coerce")
        df = df.dropna(subset=["trading_date"])

        for col in ("open", "high", "low", "close", "percent_change", "turnover"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            else:
                df[col] = pd.NA

        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")
        else:
            df["volume"] = pd.NA

        # The source's derived `status` column is redundant with OHLC; drop it.
        df = df.drop(columns=[c for c in ("status",) if c in df.columns], errors="ignore")

        df["symbol"] = symbol.upper()
        df = df.sort_values("trading_date").drop_duplicates("trading_date", keep="last")
        keep = [
            "symbol",
            "trading_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "percent_change",
        ]
        return df[[c for c in keep if c in df.columns]].reset_index(drop=True)

    def health(self) -> dict[str, Any]:
        try:
            syms = self.list_symbols()
        except SourceError as exc:
            return {**self.describe(), "available": False, "reason": str(exc)}
        return {**self.describe(), "available": True, "symbols_listed": len(syms)}
