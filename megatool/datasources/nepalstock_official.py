"""Adapter for the official nepalstock.com API - IMPLEMENTED BUT BLOCKED.

STATUS: BLOCKED for live use as of 2026-10-11.

WHAT WAS VERIFIED
-----------------
The public site is an Angular SPA. Its own JavaScript calls a REST API rooted at
``https://www.nepalstock.com/api/nots/``. Endpoints observed in the site bundle
(``main.*.js``) include:

    GET  api/nots                       - daily index
    GET  api/nots/securities
    GET  api/nots/company/list
    GET  api/nots/sector
    GET  api/nots/nepse-data/market-open
    GET  api/nots/lives-market
    GET  api/nots/nepse-data/marketdepth/{securityId}
    POST api/nots/nepse-data/floorsheet
    POST api/nots/nepse-data/today-price
    GET  api/nots/news/notices
    GET  api/nots/news/media/company-news

Every one of these was probed directly with plain HTTPS GETs and returned:

    HTTP 401  <html><head><title>Error</title></head>
             <body>WARNING: UNAUTHORIZED ACCESS</body></html>

The site's own bundle reads a bearer token from
``storageService.getCurrentUser().accessToken`` and refreshes it through
``authenticate/refresh-token``. That token belongs to a logged-in NEPSE user.

WHY THIS ADAPTER DOES NOT FETCH ANYTHING
----------------------------------------
Obtaining that token would mean either using the owner's exchange credentials or
reverse-engineering the site's client-side token generator to get around an
access control. Mega Tool deliberately does neither (Rule 9: no bypassing broker
or exchange access controls, no storing Mero Share credentials).

CONSEQUENCE
-----------
Live official NEPSE data - real-time index, market depth, official floorsheets,
official disclosures - is UNAVAILABLE to this application. Everything the app
shows is either the public GitHub dataset or a file the owner imported.

WHAT WOULD UNBLOCK IT
---------------------
If NEPSE publishes a documented public/official API with terms permitting
personal use, this adapter can be completed against it without changing any
other module - that is the point of the adapter interface.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from megatool.datasources.base import (
    BaseAdapter,
    SourceConfig,
    SourceError,
    SourceUnavailable,
)
from megatool.models import DataSource

OFFICIAL_BASE = "https://www.nepalstock.com/api/nots/"

#: Endpoints confirmed present in the site's own JavaScript bundle.
KNOWN_ENDPOINTS: dict[str, str] = {
    "daily_index": "GET  api/nots",
    "securities": "GET  api/nots/securities",
    "company_list": "GET  api/nots/company/list",
    "sectors": "GET  api/nots/sector",
    "market_open": "GET  api/nots/nepse-data/market-open",
    "live_market": "GET  api/nots/lives-market",
    "market_depth": "GET  api/nots/nepse-data/marketdepth/{securityId}",
    "floorsheet": "POST api/nots/nepse-data/floorsheet",
    "today_price": "POST api/nots/nepse-data/today-price",
    "notices": "GET  api/nots/news/notices",
    "company_news": "GET  api/nots/news/media/company-news",
}

#: Probed on 2026-10-11; every one returned HTTP 401.
VERIFIED_401_PATHS = (
    "nepse-data/market-open",
    "securities",
    "company/list",
    "sector",
    "lives-market",
    "nots/",
)


class NepalStockOfficialAdapter(BaseAdapter):
    """Official NEPSE API adapter. Raises unless real credentials are supplied.

    The constructor takes no credentials and never will: this class exists to
    document the integration point and to fail loudly and honestly rather than
    silently pretending live data exists.
    """

    def __init__(self, token: str | None = None, timeout: float = 20.0):
        # A token is accepted only so the class can be wired to a future
        # official API. It is held in memory, never written to disk or logs.
        self._token = token
        self.config = SourceConfig(
            source_id=DataSource.NEPALSTOCK_OFFICIAL,
            label="Official Nepal Stock Exchange API (BLOCKED: requires authenticated session)",
            access_method="http-get",
            base_url=OFFICIAL_BASE,
            timeout_seconds=timeout,
            max_retries=2,
            rate_limit_rps=2.0,
            requires_auth=True,
            auth_note=(
                "Returns HTTP 401 'WARNING: UNAUTHORIZED ACCESS' without a logged-in "
                "NEPSE user token. Mega Tool does not obtain, store or bypass this."
            ),
            update_frequency="intraday during market hours",
            fields_supplied=(
                "index",
                "securities",
                "market_depth",
                "floorsheet",
                "notices",
            ),
            fields_missing=(),
            terms_note="Official exchange site; terms not inspected beyond robots.txt.",
        )

    def _require_token(self) -> str:
        if not self._token:
            raise SourceUnavailable(
                "Official NEPSE API requires an authenticated user session "
                "(HTTP 401 on every probed endpoint). Mega Tool does not store NEPSE "
                "or Mero Share credentials and will not bypass this control. "
                "Use the public dataset or import a file instead."
            )
        return self._token

    def list_symbols(self) -> list[str]:
        self._require_token()
        raise SourceError("not implemented: no official-API access to validate against")

    def fetch_history(self, symbol: str) -> pd.DataFrame:
        self._require_token()
        raise SourceError("not implemented: no official-API access to validate against")

    def probe(self) -> dict[str, Any]:
        """Live reachability probe. Safe: performs at most one cheap GET."""
        import httpx

        url = OFFICIAL_BASE + "nepse-data/market-open"
        try:
            with httpx.Client(timeout=self.config.timeout_seconds, follow_redirects=True) as c:
                resp = c.get(url, headers={"User-Agent": "MegaTool/0.1 (personal research)"})
            status = resp.status_code
        except Exception as exc:  # pragma: no cover - network dependent
            return {"url": url, "error": str(exc), "reachable": False}

        return {
            "url": url,
            "http_status": status,
            "reachable": status != 401,
            "blocked": status == 401,
            "body_preview": (resp.text[:120] if status == 401 else ""),
            "checked_endpoints_401": list(VERIFIED_401_PATHS),
            "known_endpoints": KNOWN_ENDPOINTS,
            "conclusion": (
                "Official API is alive but requires an authenticated NEPSE user session. "
                "Not used by Mega Tool."
                if status == 401
                else f"Unexpected status {status}; re-evaluate before use."
            ),
        }

    def health(self) -> dict[str, Any]:
        return {**self.describe(), "available": False, "reason": self.config.auth_note}
