"""HTTP fetcher with politeness and safety controls (Part 27).

- per-source rate limiting (min interval between requests)
- bounded retries with exponential backoff (never infinite)
- max response size
- descriptive User-Agent
- explicit dry-run and collection-disable switches
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_UA = "NEPSE-MarketIntelligence/0.1 (+personal research; respects robots.txt)"


@dataclass
class FetchResult:
    ok: bool
    status: int | None
    body: bytes
    url: str
    error: str | None = None
    latency_ms: int = 0


class RateLimiter:
    def __init__(self, min_interval_s: float = 2.0):
        self.min_interval = min_interval_s
        self._last: dict[str, float] = {}

    def wait(self, key: str) -> None:
        now = time.monotonic()
        last = self._last.get(key, 0.0)
        if now - last < self.min_interval:
            time.sleep(self.min_interval - (now - last))
        self._last[key] = time.monotonic()


class HttpFetcher:
    def __init__(self, *, timeout_s: float = 15.0, max_bytes: int = 2_000_000,
                 max_retries: int = 2, backoff_base_s: float = 1.0,
                 user_agent: str = DEFAULT_UA,
                 collection_enabled: bool = True, dry_run: bool = False):
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.user_agent = user_agent
        self.collection_enabled = collection_enabled
        self.dry_run = dry_run
        self.limiter = RateLimiter()

    def fetch(self, url: str, *, rate_key: str | None = None) -> FetchResult:
        if not self.collection_enabled:
            return FetchResult(False, None, b"", url, error="collection_disabled")
        if self.dry_run:
            return FetchResult(True, None, b"", url, error=None)  # no network in dry-run
        attempt = 0
        while True:
            self.limiter.wait(rate_key or url)
            t0 = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    body = resp.read(self.max_bytes + 1)
                    if len(body) > self.max_bytes:
                        return FetchResult(False, resp.status, b"", url,
                                           error="response_too_large")
                    return FetchResult(True, resp.status, body, url,
                                       latency_ms=int((time.monotonic() - t0) * 1000))
            except urllib.error.HTTPError as e:
                status = e.code
                err = f"http_{status}"
            except Exception as e:  # noqa: BLE001
                status = None
                err = f"{type(e).__name__}: {e}"
            attempt += 1
            if attempt > self.max_retries:
                return FetchResult(False, status, b"", url, error=err,
                                   latency_ms=int((time.monotonic() - t0) * 1000))
            time.sleep(self.backoff_base_s * (2 ** (attempt - 1)))
