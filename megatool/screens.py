"""Saved custom screens / analytical rules (directive M4 §11.5, Phase 5).

The scanner already evaluates an AND/OR condition tree safely
(:class:`megatool.scanner.ScreenNode`); what was missing is **persistence**, so a
researcher can build a rule in the UI, name it, and reuse it later.

Design rules kept here:

* The stored artefact is the **JSON user tree** — the same structure
  ``POST /api/screen`` accepts. Nothing executable is stored; loading a screen
  re-parses it through :meth:`ScreenNode.from_dict` and validates every metric
  against the live catalogue, so a screen saved before a metric was removed fails
  loudly instead of silently screening nothing.
* Storage is the application SQLite (``saved_screens``). The table is created
  lazily here if absent, so this module never has to touch ``db.py``.
* Nothing is invented: an unknown metric name is rejected at save time.
"""

from __future__ import annotations

import json
from typing import Any

from megatool.db import get_conn, now_iso
from megatool.scanner import METRIC_HELP, ScreenNode, validate_tree

#: Longest accepted screen name.
MAX_NAME = 80

_CREATE = """
CREATE TABLE IF NOT EXISTS saved_screens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    definition TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class ScreenError(ValueError):
    """Invalid screen input (blank name, malformed tree, unknown metric)."""


def _ensure(conn: Any) -> None:
    conn.execute(_CREATE)


def _clean_name(name: str) -> str:
    if not name or not str(name).strip():
        raise ScreenError("screen name must not be blank")
    n = str(name).strip()
    if len(n) > MAX_NAME:
        raise ScreenError(f"screen name must be at most {MAX_NAME} characters")
    return n


def validate_definition(definition: dict[str, Any]) -> ScreenNode:
    """Parse and validate a user tree; raise :class:`ScreenError` on any problem."""
    if not isinstance(definition, dict) or not definition:
        raise ScreenError("screen definition must be a non-empty object")
    try:
        node = ScreenNode.from_dict(definition)
    except (ValueError, KeyError, TypeError) as exc:
        raise ScreenError(f"invalid screen definition: {exc}") from exc
    problems = validate_tree(node)
    if problems:
        raise ScreenError("invalid screen definition: " + "; ".join(problems))
    return node


def _row(r: Any) -> dict[str, Any]:
    try:
        definition = json.loads(r["definition"])
    except (json.JSONDecodeError, TypeError):
        definition = None
    return {
        "id": int(r["id"]),
        "name": str(r["name"]),
        "definition": definition,
        "created_at": str(r["created_at"]),
        "updated_at": str(r["updated_at"]),
    }


def save_screen(
    name: str, definition: dict[str, Any], *, overwrite: bool = False, db_path: Any = None
) -> dict[str, Any]:
    node = validate_definition(definition)
    clean = _clean_name(name)
    rendered = node.render()
    payload = json.dumps(node.to_dict(), sort_keys=True)
    ts = now_iso()
    with get_conn(db_path) as conn:
        _ensure(conn)
        existing = conn.execute("SELECT id FROM saved_screens WHERE name = ?", (clean,)).fetchone()
        if existing:
            if not overwrite:
                raise ScreenError(f"a screen named {clean!r} already exists")
            conn.execute(
                "UPDATE saved_screens SET definition = ?, updated_at = ? WHERE id = ?",
                (payload, ts, existing["id"]),
            )
            row = conn.execute(
                "SELECT * FROM saved_screens WHERE id = ?", (existing["id"],)
            ).fetchone()
        else:
            cur = conn.execute(
                "INSERT INTO saved_screens (name, definition, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (clean, payload, ts, ts),
            )
            row = conn.execute(
                "SELECT * FROM saved_screens WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
    out = _row(row)
    out["rendered"] = rendered
    return out


def list_screens(db_path: Any = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        _ensure(conn)
        rows = conn.execute("SELECT * FROM saved_screens ORDER BY name COLLATE NOCASE").fetchall()
    out = []
    for r in rows:
        item = _row(r)
        try:
            item["rendered"] = validate_definition(item["definition"] or {}).render()
        except ScreenError as exc:
            item["rendered"] = None
            item["problem"] = str(exc)
        out.append(item)
    return out


def get_screen(screen_id: int, db_path: Any = None) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        _ensure(conn)
        row = conn.execute("SELECT * FROM saved_screens WHERE id = ?", (int(screen_id),)).fetchone()
    if row is None:
        raise ScreenError(f"no saved screen with id {screen_id}")
    out = _row(row)
    node = validate_definition(out["definition"] or {})
    out["rendered"] = node.render()
    return out


def update_screen(
    screen_id: int,
    *,
    new_name: str | None = None,
    definition: dict[str, Any] | None = None,
    db_path: Any = None,
) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        _ensure(conn)
        row = conn.execute("SELECT * FROM saved_screens WHERE id = ?", (int(screen_id),)).fetchone()
        if row is None:
            raise ScreenError(f"no saved screen with id {screen_id}")
        final_name = str(row["name"])
        if new_name is not None:
            final_name = _clean_name(new_name)
            if final_name != str(row["name"]):
                clash = conn.execute(
                    "SELECT 1 FROM saved_screens WHERE name = ? AND id != ?",
                    (final_name, int(screen_id)),
                ).fetchone()
                if clash:
                    raise ScreenError(f"a screen named {final_name!r} already exists")
        payload = str(row["definition"])
        if definition is not None:
            payload = json.dumps(validate_definition(definition).to_dict(), sort_keys=True)
        ts = now_iso()
        conn.execute(
            "UPDATE saved_screens SET name = ?, definition = ?, updated_at = ? WHERE id = ?",
            (final_name, payload, ts, int(screen_id)),
        )
        row = conn.execute("SELECT * FROM saved_screens WHERE id = ?", (int(screen_id),)).fetchone()
    out = _row(row)
    out["rendered"] = validate_definition(out["definition"] or {}).render()
    return out


def duplicate_screen(screen_id: int, new_name: str, db_path: Any = None) -> dict[str, Any]:
    src = get_screen(screen_id, db_path=db_path)
    return save_screen(new_name, src["definition"], db_path=db_path)


def delete_screen(screen_id: int, db_path: Any = None) -> bool:
    with get_conn(db_path) as conn:
        _ensure(conn)
        cur = conn.execute("DELETE FROM saved_screens WHERE id = ?", (int(screen_id),))
        return cur.rowcount > 0


def metric_catalogue() -> dict[str, str]:
    """The live metric catalogue (name → human explanation) for the UI."""
    return dict(METRIC_HELP)
