#!/usr/bin/env python3
"""Live end-to-end smoke test against a running Mega Tool server.

Why this exists
---------------
The pytest suite exercises the API through FastAPI's test client against
temporary databases. That proves the routes are implemented; it does **not**
prove that the packaged app starts, connects to the real DuckDB, and answers
correctly with the real 514,018-row store behind it. This script closes that
gap and is meant to be re-run after any change, so "it works on the live app"
is a reproducible claim rather than a memory.

What it does
------------
1. Reads ``/openapi.json`` so the probe list is derived from the server's own
   route table rather than a hand-maintained list that can drift out of date.
2. Probes every **read-only** route (all GETs, plus the compute POSTs:
   screen / rank / backtest / forecast / research / planning).
3. **Never** calls a route that writes. Every mutating verb (DELETE/PUT/PATCH)
   and every POST not explicitly classified as a compute route is listed as
   SKIPPED with its reason, because hitting one would put smoke-test rows into
   the owner's real journal, portfolio or imported-record tables. The default
   is "skip unless proven read-only", never the reverse.
4. Reports status, latency and payload size for every probe.

Exit codes
----------
``0`` every probed route returned an expected status
``1`` at least one route returned an unexpected status
``2`` could not reach the server at all

A 404 on ``/api/journal/{id}`` when the journal is empty is **expected**, not
a failure: there genuinely is no entry, and inventing one to make the probe
green would defeat the point.

Usage
-----
    python scripts/smoke_live.py                      # default base URL
    python scripts/smoke_live.py --base http://127.0.0.1:8710
    python scripts/smoke_live.py --json report.json   # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE = "http://127.0.0.1:8710"

#: POST routes that mutate persistent state. Never probed automatically —
#: a smoke test has no business writing to the owner's journal, portfolio or
#: imported-record tables.
MUTATING_POSTS: dict[str, str] = {
    "/api/journal": "creates a journal entry in the real SQLite store",
    "/api/portfolio/manual": "creates a real holding",
    "/api/portfolio/transactions": "appends a real ledger transaction",
    "/api/floorsheet/import": "writes floor-sheet rows",
    "/api/fundamentals/import": "writes fundamentals rows",
    "/api/written-pdf/review": "moves a transcription record's verification status",
}


#: Read-only POST routes and the payload that satisfies their contract.
#: Field names are taken from the OpenAPI schema, not guessed.
def read_only_posts(symbol: str) -> dict[str, tuple[str, Any]]:
    tree = {
        "op": "and",
        "conditions": [
            {"metric": "close", "operator": "gt", "value": 1},
            {"metric": "return_60d", "operator": "gt", "value": 0.0},
        ],
    }
    return {
        "/api/screen": ("POST", {"tree": tree}),
        "/api/rank": ("POST", {"top": 5}),
        "/api/backtest": (
            "POST",
            {
                "symbol": symbol,
                "strategy": "sma_cross",
                "start": "2022-01-01",
                "end": "2024-12-31",
            },
        ),
        "/api/forecast": ("POST", {"symbol": symbol, "model": "naive", "horizon": 5}),
        "/api/forecast/compare": ("POST", {"symbol": symbol, "horizon": 5}),
        "/api/research/ask": ("POST", {"symbol": symbol, "question": "trend"}),
        "/api/planning": (
            "POST",
            {"entry": 100.0, "stop": 95.0, "target": 112.0, "capital": 100000.0, "risk_pct": 1.0},
        ),
        # Grading a trade requires knowing how it actually ended: without
        # exit_price the endpoint correctly refuses (400) rather than guessing.
        "/api/planning/grade": (
            "POST",
            {
                "entry": 100.0,
                "stop": 95.0,
                "target": 112.0,
                "exit_price": 112.0,
                "capital": 100000.0,
                "risk_pct": 1.0,
            },
        ),
    }


def _request(
    base: str, path: str, payload: Any | None = None, timeout: float = 60.0
) -> tuple[int | str, bytes, float]:
    """Return ``(status, body, seconds)``. ``status`` is ``"ERR"`` on transport failure."""
    url = base + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if data is not None else "GET",
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, body, time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), time.perf_counter() - started
    except Exception as exc:  # noqa: BLE001 - report, never crash the probe
        return "ERR", f"{type(exc).__name__}: {exc}".encode(), time.perf_counter() - started


def _discover_symbol(base: str) -> str:
    """Pick a symbol that actually has stored bars, so bar routes aren't 404 by construction."""
    status, body, _ = _request(base, "/api/securities?limit=50")
    if status == 200:
        try:
            payload = json.loads(body)
            items = payload if isinstance(payload, list) else payload.get("items") or []
            for item in items:
                sym = item.get("symbol")
                if sym:
                    s, _, _ = _request(base, f"/api/bars/{sym}?limit=5")
                    if s == 200:
                        return sym
        except Exception:  # noqa: BLE001
            pass
    return "NABIL"


def _journal_entry_id(base: str) -> str | None:
    """Return a real journal entry id, or ``None`` when the journal is empty."""
    status, body, _ = _request(base, "/api/journal")
    if status != 200:
        return None
    try:
        entries = json.loads(body)
        if isinstance(entries, list) and entries:
            return str(entries[0].get("id") or entries[0].get("entry_id"))
    except Exception:  # noqa: BLE001
        return None
    return None


def run(base: str) -> dict[str, Any]:
    status, body, _ = _request(base, "/openapi.json", timeout=20.0)
    if status != 200:
        raise SystemExit(f"cannot reach {base} (openapi.json -> {status}); is the server running?")

    spec = json.loads(body)
    symbol = _discover_symbol(base)
    entry_id = _journal_entry_id(base)
    posts = read_only_posts(symbol)

    results: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for path, ops in sorted(spec.get("paths", {}).items()):
        for method, op in ops.items():
            method = method.upper()
            if method == "DELETE" or method in {"PUT", "PATCH"}:
                skipped.append(
                    {"path": f"{method} {path}", "reason": "mutating verb; never probed"}
                )
                continue
            if method not in {"GET", "POST"}:
                skipped.append({"path": f"{method} {path}", "reason": "unsupported method"})
                continue

            concrete = path.replace("{symbol}", symbol).replace("{entry_id}", entry_id or "0")
            query = ""
            expected = {200}
            note = ""

            # A journal route with an empty journal has no id to fetch: 404 is the
            # truthful answer, and inventing an entry to make the probe green
            # would put fake data in the owner's journal.
            if "{entry_id}" in path and entry_id is None:
                note = "journal empty; 404 expected"
                expected = {404}

            # Required query parameters, read from the server's own spec.
            for param in op.get("parameters", []):
                if not param.get("required") or param.get("in") != "query":
                    continue
                name = param["name"]
                if name == "tree":
                    tree = {
                        "op": "and",
                        "conditions": [{"metric": "close", "operator": "gt", "value": 1}],
                    }
                    query += f"?tree={urllib.parse.quote(json.dumps(tree))}"
                elif name == "name":
                    query += ("&" if query else "?") + "name=sma&period=20"

            if method == "GET":
                st, b, secs = _request(base, concrete + query)
                results.append(_row(method, path, st, b, secs, expected, note))
                continue

            # POST
            if path in MUTATING_POSTS:
                skipped.append({"path": f"{method} {path}", "reason": MUTATING_POSTS[path]})
                continue
            if path not in posts:
                skipped.append(
                    {
                        "path": f"{method} {path}",
                        "reason": "not classified read-only; skipped rather than risk a write",
                    }
                )
                continue
            _, payload = posts[path]
            st, b, secs = _request(base, concrete, payload)
            results.append(_row(method, path, st, b, secs, {200}, note))

    unexpected = [r for r in results if not r["ok"]]
    return {
        "base": base,
        "symbol": symbol,
        "journal_entries": entry_id is not None,
        "probed": len(results),
        "ok": len(results) - len(unexpected),
        "unexpected": len(unexpected),
        "skipped_writes": len(skipped),
        "results": results,
        "skipped": skipped,
    }


def _row(
    method: str,
    path: str,
    status: int | str,
    body: bytes,
    secs: float,
    expected: set[int],
    note: str,
) -> dict[str, Any]:
    ok = status in expected
    return {
        "method": method,
        "path": path,
        "status": status,
        "bytes": len(body),
        "ms": round(secs * 1000, 1),
        "ok": ok,
        "expected": sorted(expected),
        "note": note,
        "error": "" if ok or not body else body[:160].decode("utf-8", "replace"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke-test a running Mega Tool server")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--json", dest="json_out", help="write the full report to this path")
    args = ap.parse_args()

    try:
        report = run(args.base.rstrip("/"))
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2

    print(f"Mega Tool live smoke test — {report['base']}")
    print(f"  symbol used : {report['symbol']}")
    print(f"  journal     : {'non-empty' if report['journal_entries'] else 'empty (404 expected)'}")
    print()
    print(f"{'METHOD':<7}{'STATUS':<8}{'MS':>9}{'BYTES':>10}  PATH")
    for r in report["results"]:
        flag = "" if r["ok"] else "  <== UNEXPECTED"
        extra = f"  ({r['note']})" if r["note"] else ""
        print(
            f"{r['method']:<7}{r['status']!s:<8}{r['ms']:>9}{r['bytes']:>10}  {r['path']}{flag}{extra}"
        )
        if not r["ok"] and r["error"]:
            print(f"{'':<7}        {r['error']}")

    print()
    print("Not probed (mutating; would write to the real stores):")
    for s in report["skipped"]:
        print(f"  {s['path']:<44} {s['reason']}")

    print()
    print(
        f"probed {report['probed']} · expected {report['ok']} · "
        f"unexpected {report['unexpected']} · skipped {report['skipped_writes']} writes"
    )

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"report written to {args.json_out}")

    return 1 if report["unexpected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
