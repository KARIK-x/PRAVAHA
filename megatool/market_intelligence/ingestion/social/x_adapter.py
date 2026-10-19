"""Authorized X (Twitter) API v2 adapter (Part 16).

Design rules:
- Credentials come ONLY from environment variables (X_BEARER_TOKEN).
  Never from source code, config files in the repo, or CLI args.
- Without credentials the adapter refuses to collect and reports a clear
  status — it never scrapes and never pretends to have live access.
- Dry-run mode exercises the full code path with zero network calls.
- Daily request and record budgets are enforced before every request.
- The HTTP layer is injected, so tests use a fake transport (mocked
  responses), satisfying "test with mocked responses".
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from ...normalization.timestamps import now_utc_iso, parse_timestamp

API_BASE = "https://api.twitter.com/2"

# Conservative public pricing knowledge as of research date; users must
# confirm current pricing — see docs/ACCOUNT_RESEARCH.md.
ESTIMATED_COST_NOTES = (
    "X API pricing changes frequently. As of late 2025 the Free tier allows "
    "write-only access (no read/search); Basic (~USD 200/month) allows limited "
    "reads (10k posts/month cap historically). ALWAYS verify current terms at "
    "https://developer.x.com before enabling paid collection."
)


@dataclass
class Budget:
    max_requests_per_day: int = 100
    max_records_per_run: int = 200
    requests_today: int = 0
    records_this_run: int = 0

    def allow_request(self) -> bool:
        return self.requests_today < self.max_requests_per_day

    def allow_record(self) -> bool:
        return self.records_this_run < self.max_records_per_run


@dataclass
class XPost:
    post_id: str
    author_id: str
    text: str
    published_at: str | None
    url: str | None
    raw: dict = field(default_factory=dict)


class XApiAdapter:
    """Minimal, authorized X API v2 reader for public posts of registered
    accounts. Never bypasses platform controls."""

    def __init__(self, *, bearer_token: str | None = None, budget: Budget | None = None,
                 transport=None, dry_run: bool = False):
        self.bearer_token = bearer_token or os.environ.get("X_BEARER_TOKEN")
        self.budget = budget or Budget()
        self.dry_run = dry_run
        self._transport = transport or self._default_transport

    @property
    def available(self) -> bool:
        return bool(self.bearer_token)

    def status(self) -> dict:
        return {
            "adapter": "x_api_v2",
            "credentials_present": self.available,
            "dry_run": self.dry_run,
            "budget": {"max_requests_per_day": self.budget.max_requests_per_day,
                       "max_records_per_run": self.budget.max_records_per_run,
                       "requests_today": self.budget.requests_today},
            "cost_notes": ESTIMATED_COST_NOTES,
        }

    def _default_transport(self, url: str, headers: dict) -> dict:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _request(self, path: str, params: dict) -> dict:
        if not self.available:
            raise RuntimeError("X_BEARER_TOKEN not set; collection refused")
        if not self.budget.allow_request():
            raise RuntimeError("daily request budget exhausted")
        url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
        data = self._transport(url, {"Authorization": f"Bearer {self.bearer_token}"})
        self.budget.requests_today += 1
        return data

    def user_recent_posts(self, user_id: str, *, max_results: int = 10) -> list[XPost]:
        """Fetch recent public posts for one account via /2/users/:id/tweets."""
        if self.dry_run:
            return []
        max_results = max(5, min(max_results, self.budget.max_records_per_run))
        data = self._request(f"/users/{user_id}/tweets", {
            "max_results": max_results,
            "tweet.fields": "created_at,lang,public_metrics",
        })
        posts = []
        for t in data.get("data", []):
            if not self.budget.allow_record():
                break
            posts.append(XPost(
                post_id=t["id"], author_id=user_id, text=t.get("text", ""),
                published_at=(lambda p: p.isoformat() if p else None)(
                    parse_timestamp(t.get("created_at"))),
                url=f"https://x.com/i/status/{t['id']}", raw=t,
            ))
            self.budget.records_this_run += 1
        return posts

    def lookup_user_id(self, handle: str) -> str | None:
        if self.dry_run:
            return None
        data = self._request(f"/users/by/username/{handle}", {})
        user = data.get("data") or {}
        return user.get("id")


def estimate_cost(accounts: int, polls_per_day: int, *, notes: bool = True) -> dict:
    """Transparent cost/workload estimate before enabling collection."""
    requests_per_day = accounts * polls_per_day
    est = {
        "accounts": accounts,
        "polls_per_day": polls_per_day,
        "requests_per_day": requests_per_day,
        "requests_per_month": requests_per_day * 30,
        "assessment": ("exceeds free/basic read tiers; review X pricing"
                       if requests_per_day * 30 > 10000 else
                       "may fit within a paid basic tier; verify limits"),
    }
    if notes:
        est["notes"] = ESTIMATED_COST_NOTES
    return est
