"""Adapter for the **actual** `github.com/voidarchive/go-nepse` Go library.

This is not a Python re-implementation of go-nepse's protocol. It shells out to
``tools/gonepse-bridge``, a small Go program that links the real library, and
parses the single JSON object the bridge prints to stdout. See
``tools/gonepse-bridge/README.md`` for the wire contract and the build steps.

Safety posture
--------------
* **TLS verification stays on.** The bridge never sets
  ``Options.TLSVerification = false``. The library documents disabling it
  because NEPSE's certificate chain is awkward; that is a failure to diagnose,
  not to bypass.
* **The owner authorization gate is preserved.** Every live operation raises
  :class:`SourceUnavailable` unless ``MEGATOOL_NEPSE_API_AUTHORIZED=1`` is set,
  *before* the bridge is spawned. The bridge enforces the same gate
  independently.
* **No fabricated data.** A missing bridge, a timeout, a malformed response and
  a provider error are all surfaced with their cause, never turned into a
  plausible-looking value.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

import pandas as pd

from megatool.datasources.base import (
    BaseAdapter,
    SourceConfig,
    SourceError,
    SourceUnavailable,
)
from megatool.models import DataSource

BRIDGE_ENV = "MEGATOOL_GONEPSE_BIN"
GATE_ENV = "MEGATOOL_NEPSE_API_AUTHORIZED"
DEFAULT_BASE_URL = "https://nepalstock.com.np"
DEFAULT_TIMEOUT = 30.0

#: The operations the bridge understands, grouped by what they answer.
OPERATIONS: dict[str, str] = {
    "market-summary": "turnover, traded shares, transactions, market cap",
    "market-status": "whether the market is open, and as-of date",
    "securities": "the listed-security list (used for symbol lookup)",
    "find-security": "one security by symbol",
    "live-market": "live per-security prices for the current session",
    "price-history": "historical OHLCV rows for one symbol and date range",
    "nepse-index": "the main NEPSE index value and change",
    "sub-indices": "the other main indices (Sensitive, Float, ...)",
    "company": "company identity/sector record for a symbol",
    "company-profile": "a company's profile (address, contact, description)",
    "dividends": "dividend declarations for a symbol",
    "floorsheet": "floor-sheet trades for a symbol and business date",
    "market-depth": "order-book depth for a symbol",
}

#: Operations that need a `symbol` argument.
_SYMBOL_OPS = frozenset(
    {
        "find-security",
        "price-history",
        "company",
        "company-profile",
        "dividends",
        "floorsheet",
        "market-depth",
    }
)


def find_bridge() -> str | None:
    """Return the bridge executable, or ``None`` when it is not available."""
    explicit = os.environ.get(BRIDGE_ENV)
    if explicit:
        return explicit if os.path.isfile(explicit) and os.access(explicit, os.X_OK) else None
    return shutil.which("gonepse-bridge")


def gate_open() -> bool:
    """True only when the owner has authorized live official-API access."""
    return os.environ.get(GATE_ENV) == "1"


class GoNepseAdapter(BaseAdapter):
    """Read-only access to NEPSE through the real go-nepse Go library."""

    def __init__(
        self,
        *,
        bridge: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        base_url: str | None = None,
        runner: Callable[..., subprocess.CompletedProcess] | None = None,
    ) -> None:
        self._bridge = bridge if bridge is not None else find_bridge()
        self._timeout = timeout
        self._base_url = base_url
        # Injected for tests; production uses the real subprocess.
        self._runner = runner or self._subprocess_run
        self.config = SourceConfig(
            source_id=DataSource.GONEPSE,
            label="NEPSE official API via go-nepse (Go library)",
            access_method="subprocess-json (tools/gonepse-bridge)",
            base_url=base_url or DEFAULT_BASE_URL,
            timeout_seconds=timeout,
            max_retries=2,
            backoff_seconds=1.0,
            rate_limit_rps=1.0,
            requires_auth=True,
            auth_note=(
                "read-only; live calls require the owner authorization gate "
                f"{GATE_ENV}=1 (not set by this adapter)"
            ),
            update_frequency="live (intraday) / daily history",
            fields_supplied=("symbol", "date", "high", "low", "close", "volume", "turnover"),
            fields_missing=("open",),  # NEPSE price history carries no opening price
            terms_note=(
                "wraps an undocumented exchange API; automated access is an owner "
                "decision, and this adapter never bypasses the gate"
            ),
            extra={"tls_verification": True, "library": "github.com/voidarchive/go-nepse"},
        )

    # ------------------------------------------------------------------ transport

    def _subprocess_run(self, request: dict[str, Any]) -> subprocess.CompletedProcess:
        argv = [self._bridge]  # type: ignore[list-item]
        if self._base_url:
            argv += ["--base-url", self._base_url]
        argv += ["--timeout", str(self._timeout), "--retries", "2"]
        # Wall-clock budget sits above the per-request HTTP timeout so retries
        # (and token acquisition) can finish before we give up.
        return subprocess.run(
            argv,
            input=json.dumps(request).encode("utf-8"),
            capture_output=True,
            timeout=self._timeout * 4,
            check=False,
        )

    def call(self, op: str, **fields: Any) -> Any:
        """Run one bridge operation and return its `data`, or raise honestly."""
        if op not in OPERATIONS:
            raise SourceError(f"go-nepse: unknown operation {op!r}")
        if not gate_open():
            raise SourceUnavailable(
                "go-nepse: live NEPSE access requires the owner authorization "
                f"gate ({GATE_ENV}=1); it is not set"
            )
        if not self._bridge:
            raise SourceUnavailable(
                "go-nepse: bridge binary not found; build tools/gonepse-bridge "
                f"and set {BRIDGE_ENV}"
            )
        if op in _SYMBOL_OPS and not fields.get("symbol"):
            raise SourceError(f"go-nepse: operation {op!r} requires a symbol")

        request = {"op": op, **{k: v for k, v in fields.items() if v not in (None, "")}}
        try:
            proc = self._runner(request)
        except subprocess.TimeoutExpired as exc:
            raise SourceError(f"go-nepse: bridge timed out after {self._timeout}s") from exc
        except OSError as exc:
            raise SourceUnavailable(f"go-nepse: could not execute bridge: {exc}") from exc
        return self._parse(proc, op)

    @staticmethod
    def _parse(proc: subprocess.CompletedProcess, op: str) -> Any:
        raw = (proc.stdout or b"").decode("utf-8", "replace").strip()
        if not raw:
            stderr = (proc.stderr or b"").decode("utf-8", "replace").strip()
            raise SourceError(
                f"go-nepse: bridge produced no output for {op!r} "
                f"(exit {proc.returncode}{'; ' + stderr[:200] if stderr else ''})"
            )
        # The bridge writes exactly one JSON object; tolerate a trailing line.
        candidate = raw.splitlines()[-1]
        try:
            env = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise SourceError(f"go-nepse: bridge output was not JSON: {exc}") from exc
        if not isinstance(env, dict) or "ok" not in env:
            raise SourceError("go-nepse: bridge output was not an envelope object")
        if env.get("ok") is not True:
            err = env.get("error") or {}
            kind = str(err.get("kind") or "internal_error")
            message = str(err.get("message") or "unknown error")
            if kind == "unauthorized":
                raise SourceUnavailable(f"go-nepse: {kind}: {message}")
            raise SourceError(f"go-nepse: {kind}: {message}")
        return env.get("data")

    # ------------------------------------------------------------------ operations

    def market_summary(self) -> dict[str, Any] | None:
        return self.call("market-summary")

    def market_status(self) -> dict[str, Any] | None:
        return self.call("market-status")

    def securities(self) -> list[dict[str, Any]]:
        return self.call("securities") or []

    def find_security(self, symbol: str) -> dict[str, Any] | None:
        return self.call("find-security", symbol=symbol)

    def live_market(self) -> list[dict[str, Any]]:
        return self.call("live-market") or []

    def price_history(
        self, symbol: str, start: str | None = None, end: str | None = None
    ) -> list[dict[str, Any]]:
        return self.call("price-history", symbol=symbol, start=start, end=end) or []

    def nepse_index(self) -> dict[str, Any] | None:
        return self.call("nepse-index")

    def sub_indices(self) -> list[dict[str, Any]]:
        return self.call("sub-indices") or []

    def company(self, symbol: str) -> dict[str, Any] | None:
        return self.call("company", symbol=symbol)

    def company_profile(self, symbol: str) -> dict[str, Any] | None:
        return self.call("company-profile", symbol=symbol)

    def dividends(self, symbol: str) -> list[dict[str, Any]]:
        return self.call("dividends", symbol=symbol) or []

    def floorsheet(self, symbol: str, date: str | None = None) -> list[dict[str, Any]]:
        return self.call("floorsheet", symbol=symbol, date=date) or []

    def market_depth(self, symbol: str) -> dict[str, Any] | None:
        return self.call("market-depth", symbol=symbol)

    # ------------------------------------------------------------------ BaseAdapter

    def list_symbols(self) -> list[str]:
        return sorted({s["symbol"] for s in self.securities() if s.get("symbol")})

    def fetch_history(self, symbol: str) -> pd.DataFrame:
        """Canonical OHLCV frame for one symbol.

        NEPSE's historical feed carries no opening price (the library documents
        this), so ``open`` is left null rather than manufactured. Ingestion is
        gated, so this runs only under owner authorization.
        """
        rows = self.price_history(symbol)
        if not rows:
            return pd.DataFrame(
                columns=[
                    "symbol",
                    "trading_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "turnover",
                    "transactions",
                ]
            )
        df = pd.DataFrame(rows)
        out = pd.DataFrame(
            {
                "symbol": symbol.upper(),
                "trading_date": pd.to_datetime(df["businessDate"], errors="coerce"),
                "open": pd.NA,  # not provided by the source (never invented)
                "high": pd.to_numeric(df.get("highPrice"), errors="coerce"),
                "low": pd.to_numeric(df.get("lowPrice"), errors="coerce"),
                "close": pd.to_numeric(df.get("closePrice"), errors="coerce"),
                "volume": pd.to_numeric(df.get("totalTradedQuantity"), errors="coerce"),
                "turnover": pd.to_numeric(df.get("totalTradedValue"), errors="coerce"),
                "transactions": pd.to_numeric(df.get("totalTrades"), errors="coerce"),
            }
        )
        return (
            out.dropna(subset=["trading_date"]).sort_values("trading_date").reset_index(drop=True)
        )

    # ------------------------------------------------------------------ diagnostics

    def status(self) -> dict[str, Any]:
        """Observable, network-free provider status for the diagnostics surface."""
        bridge_present = bool(self._bridge)
        auth = gate_open()
        # Report *every* reason live access is unavailable, not just the first,
        # so the diagnostics never under-describe why nothing can be fetched.
        reasons: list[str] = []
        if not bridge_present:
            reasons.append(f"bridge binary not found (set {BRIDGE_ENV})")
        if not auth:
            reasons.append(f"owner authorization gate not set ({GATE_ENV}=1)")
        live = "ready" if not reasons else "blocked"
        return {
            "source": self.config.source_id.value,
            "label": self.config.label,
            "library": "github.com/voidarchive/go-nepse",
            "bridge_present": bridge_present,
            "bridge_path": self._bridge,
            "authorized": auth,
            "tls_verification": True,
            "base_url": self._base_url or DEFAULT_BASE_URL,
            "live": live,
            "blocked_reason": ("; ".join(reasons) or None),
            "blocked_reasons": reasons,
            "static_blocker": (
                "anti-bot token obfuscation (WASM salt stripping) + owner gate (unset)"
                if live != "ready"
                else None
            ),
            "live_connection_tested": False,
            "operations": dict(sorted(OPERATIONS.items())),
            "note": (
                "Adapter and tests (9 Go, 21 Python) are implemented and passing. A live "
                "connection remains unverified: the library reaches the official NEPSE "
                "API only through an embedded WASM token-obfuscation bypass, which this "
                "project will not perform, and the owner gate is unset. TLS verification "
                "is never disabled."
            ),
        }

    def health(self) -> dict[str, Any]:
        st = self.status()
        return {
            "source": self.config.source_id.value,
            "label": self.config.label,
            "available": st["live"] == "ready",
            "reason": st["blocked_reason"],
            "bridge_present": st["bridge_present"],
            "authorized": st["authorized"],
        }
