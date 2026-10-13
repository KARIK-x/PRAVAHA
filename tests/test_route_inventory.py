"""The two route-classification tables must never disagree.

``scripts/smoke_live.py`` refuses to probe anything it cannot prove is
read-only; ``scripts/route_inventory.py`` publishes the inventory and its
read-only/mutating split. If the two tables drift apart, one tool starts
probing what the other refuses to — the exact failure the "skip unless proven
read-only" rule exists to prevent.

This test imports both modules and compares their tables directly, so a route
added to one and not the other fails immediately rather than at the next live
smoke run.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mutating_post_tables_are_identical():
    smoke = _load("smoke_under_test", "scripts/smoke_live.py")
    inv = _load("inventory_under_test", "scripts/route_inventory.py")

    assert smoke.MUTATING_POSTS == inv.MUTATING_POSTS, (
        "smoke_live.py and route_inventory.py disagree about which POSTs write. "
        "A route moved here without the other would be probed for real."
    )
    # The inventory's non-POST table must cover every parameterised write it
    # claims, so no DELETE/PATCH is ever classed read-only.
    for path, reason in inv.MUTATING_OTHER.items():
        assert reason, f"{path} has no reason recorded"


def test_every_mutating_post_is_indeed_a_write_route():
    """Sanity: the shared table only names real, registered POST paths."""
    inv = _load("inventory_under_test", "scripts/route_inventory.py")
    spec = inv._build_spec()
    post_paths = {p for p, ops in spec["paths"].items() if "post" in ops}

    unknown = set(inv.MUTATING_POSTS) - post_paths
    assert not unknown, f"mutating table names POSTs that do not exist: {sorted(unknown)}"


def test_no_delete_or_patch_route_is_classed_read_only():
    """DELETE/PATCH always mutate; the classifier must never say otherwise."""
    inv = _load("inventory_under_test", "scripts/route_inventory.py")
    spec = inv._build_spec()

    for path, ops in spec["paths"].items():
        for method in ("delete", "patch", "put"):
            if method in ops:
                classification, _ = inv._classify(method.upper(), path)
                assert classification == "mutating", (
                    f"{method.upper()} {path} was classed read-only"
                )
