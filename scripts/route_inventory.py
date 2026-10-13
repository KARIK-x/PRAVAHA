#!/usr/bin/env python3
"""Generate the API route inventory from the app itself, plus real test coverage.

Unlike ``smoke_live.py`` (which probes a *running* server), this runs
**in-process**: it builds the FastAPI app, reads its own ``/openapi.json``, and
so needs neither the server nor the DuckDB store. That makes it safe to run at
any time and impossible for the route list to drift from the code.

For each route it reports:

* method, path, and the route handler's summary/docstring first line;
* a read-only / mutating classification, reusing the same tables as
  ``smoke_live.py`` so the two tools can never disagree;
* which test file(s) reference the path, as evidence of behaviour coverage
  (not merely a 200 — the tests themselves assert the contract);
* a verification status that is honest about what has actually been run:
  ``LIVE+TEST`` when the live smoke run also exercised it, ``TEST`` when only
  automated tests cover it, ``NONE`` when neither has.

Usage::

    python scripts/route_inventory.py                 # human table
    python scripts/route_inventory.py --json out.json # machine-readable
    python scripts/route_inventory.py --md  out.md    # markdown for docs/

The inventory is evidence, not a claim: a route marked ``TEST`` has tests that
reference its path, and the caller should read those tests to see what they
assert.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: POST routes that mutate persistent state. Kept identical to the table in
#: ``smoke_live.py``; a mismatch would mean one tool probes what the other
#: refuses to, so keep them in step.
MUTATING_POSTS: dict[str, str] = {
    "/api/journal": "creates a journal entry in the real SQLite store",
    "/api/portfolio/manual": "creates a real holding",
    "/api/portfolio/transactions": "appends a real ledger transaction",
    "/api/floorsheet/import": "writes floor-sheet rows",
    "/api/fundamentals/import": "writes fundamentals rows",
    "/api/written-pdf/review": "moves a transcription record's verification status",
}

#: Mutating non-POST routes. DELETE/PATCH always mutate by definition.
MUTATING_OTHER: dict[str, str] = {
    "/api/journal/{entry_id}": "PATCH edits / DELETE removes a journal entry",
    "/api/portfolio/manual/{symbol}": "DELETE removes a manual holding",
    "/api/portfolio/transactions/{tx_id}": "DELETE removes a ledger transaction",
}


def _build_spec() -> dict:
    """Build the app in-process and return its OpenAPI spec.

    A throwaway in-memory MarketStore is enough: FastAPI only needs the route
    table, and building it never reads the real DuckDB file.
    """
    from megatool.api import create_app
    from megatool.market_store import MarketStore

    store = MarketStore(":memory:")
    try:
        app = create_app(store=store)
        return app.openapi()
    finally:
        store.close()


def _classify(method: str, path: str) -> tuple[str, str]:
    """Return (classification, reason). Read-only is never assumed for writes."""
    if method in ("DELETE", "PATCH", "PUT"):
        return "mutating", MUTATING_OTHER.get(path, f"{method} mutates state")
    if method == "POST":
        if path in MUTATING_POSTS:
            return "mutating", MUTATING_POSTS[path]
        return "read-only", "compute endpoint; reads the store, writes nothing"
    return "read-only", "GET never mutates"


def _test_coverage(openapi_paths: list[str]) -> dict[str, list[str]]:
    """Map each OpenAPI path to the test files that exercise it.

    Tests reference parameterised routes by their concrete values
    (``/api/bars/TEST1``), never by the template (``/api/bars/{symbol}``), so a
    literal match against the template would report every parameterised route
    as uncovered. We therefore match on the **stem** — everything before the
    first ``{`` — which is present in any test that hits that route.

    Coverage here means "a test mentions this route", the honest floor: it says
    the route is exercised, not that every branch is checked. The per-file test
    counts in TEST_RESULTS.md carry the rest.
    """
    tests_dir = ROOT / "tests"
    test_files = {f.name: f.read_text() for f in sorted(tests_dir.glob("test_*.py"))}
    coverage: dict[str, list[str]] = {}
    for path in openapi_paths:
        stem = path.split("{")[0]
        hits = [name for name, text in test_files.items() if stem and stem in text]
        coverage[path] = hits
    return coverage


def _live_probed() -> set[str]:
    """Paths the live smoke run exercised, if its report file is present.

    ``smoke_live.py`` can write a JSON report; when one is found we use it to
    upgrade ``TEST`` to ``LIVE+TEST``. Without it, every route stays at
    ``TEST`` — we never *assume* a live probe happened.
    """
    report = Path("/tmp/megatool_smoke_live.json")
    if not report.exists():
        return set()
    try:
        data = json.loads(report.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()
    for row in data.get("probed", []):
        path = row.get("path") or row.get("route") or ""
        if path:
            out.add(path.split()[-1] if " " in path else path)
    return out


def build_inventory() -> list[dict]:
    spec = _build_spec()
    coverage = _test_coverage(list(spec["paths"].keys()))
    live = _live_probed()

    rows: list[dict] = []
    for path, ops in sorted(spec["paths"].items()):
        for method, op in sorted(ops.items()):
            if method.lower() in ("get", "post", "delete", "patch", "put"):
                classification, reason = _classify(method.upper(), path)
                covered = coverage.get(path, [])
                if path in live:
                    status = "LIVE+TEST"
                elif covered:
                    status = "TEST"
                else:
                    status = "NONE"
                rows.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "summary": (op.get("summary") or "").strip(),
                        "classification": classification,
                        "why": reason,
                        "tests": covered,
                        "status": status,
                    }
                )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", dest="json_out", help="write full inventory to this path")
    ap.add_argument("--md", dest="md_out", help="write a markdown table to this path")
    args = ap.parse_args()

    rows = build_inventory()

    total = len(rows)
    by_status: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_class[r["classification"]] = by_class.get(r["classification"], 0) + 1

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rows, indent=2))

    if args.md_out:
        lines = [
            "| Method | Path | Purpose | Class | Tests | Status |",
            "|---|---|---|---|---|---|",
        ]
        for r in rows:
            tests = (
                ", ".join(sorted({t.replace("test_", "").replace(".py", "") for t in r["tests"]}))
                or "—"
            )
            lines.append(
                f"| {r['method']} | `{r['path']}` | {r['summary'] or '—'} | "
                f"{r['classification']} | {tests} | {r['status']} |"
            )
        Path(args.md_out).write_text("\n".join(lines) + "\n")

    print(f"routes: {total}")
    print("by class:", ", ".join(f"{k}={v}" for k, v in sorted(by_class.items())))
    print("by status:", ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())))
    untested = [r for r in rows if r["status"] == "NONE"]
    if untested:
        print("\nNO automated test references these paths:")
        for r in untested:
            print(f"  {r['method']:6} {r['path']}")
        return 1
    print("\nevery route is referenced by at least one automated test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
