"""Focused tests for the NEPSE historical index OHLC recovery data."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from megatool.api import app
from megatool.config import PATHS, APP_DB_ENV
import os

STAGING = Path("data/staging/socrateai_nepse_index")
DB = Path('/Users/ashim/Downloads/AI trading NEPSE/data/dev/release/processed/megatool_state.sqlite')



@pytest.fixture(autouse=True)
def _populate_index_ohlc(monkeypatch, tmp_path):
    """Ensure the isolated DB has index_ohlc_history table with sample data."""
    db_path = tmp_path / "isolated_state.sqlite"
    # The conftest already set MEGATOOL_APP_DB to this path; init_app_db creates base schema
    from megatool.db import init_app_db
    init_app_db(db_path)
    conn = __import__("sqlite3").connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS index_ohlc_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            index_name TEXT NOT NULL,
            trading_date DATE NOT NULL,
            open REAL, high REAL, low REAL, close REAL NOT NULL,
            volume REAL, volume_type TEXT, ohlc_status TEXT NOT NULL,
            source TEXT NOT NULL, source_file TEXT, retrieved_at TIMESTAMP,
            close_diff_vs_index_series REAL,
            UNIQUE(index_name, trading_date)
        )
    """)
    # Insert 3 sample rows
    samples = [
        ("NEPSE", "2026-10-13", 2595.0, 2600.0, 2590.0, 2599.93, 4736923427.0, "turnover_npr", "genuine"),
        ("NEPSE", "2026-10-14", 2607.14, 2621.26, 2592.15, 2621.26, 4134895525.73, "turnover_npr", "genuine"),
        ("NEPSE", "2003-07-17", 204.41, 204.41, 204.41, 204.41, None, None, "placeholder"),
    ]
    for s in samples:
        conn.execute("""
            INSERT OR REPLACE INTO index_ohlc_history
            (index_name, trading_date, open, high, low, close, volume, volume_type, ohlc_status, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'test')
        """, s)
    conn.commit()
    conn.close()

@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_staging_csv_exists():
    assert (STAGING / "nepse_index_ohlc.csv").is_file()
    assert (STAGING / "metadata.json").is_file()


def test_staging_csv_has_expected_columns():
    with open(STAGING / "nepse_index_ohlc.csv") as f:
        reader = csv.DictReader(f)
        assert set(reader.fieldnames) == {"date", "open", "high", "low", "close", "volume", "symbol"}
        rows = list(reader)
    assert len(rows) == 5350


def test_staging_metadata():
    meta = json.loads((STAGING / "metadata.json").read_text())
    assert meta["source"] == "socrateai-official/nepse-open-data"
    assert meta["license"] == "MIT"
    assert meta["rows_collected"] == 5350
    assert meta["date_range"] == ["2003-07-17", "2026-10-15"]


def test_db_table_exists():
    conn = sqlite3.connect(str(DB))
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='index_ohlc_history'"
    ).fetchall()]
    assert "index_ohlc_history" in tables
    conn.close()


def test_db_row_count():
    conn = sqlite3.connect(str(DB))
    count = conn.execute("SELECT COUNT(*) FROM index_ohlc_history").fetchone()[0]
    assert count == 5350
    conn.close()


def test_db_no_duplicate_dates():
    conn = sqlite3.connect(str(DB))
    total = conn.execute("SELECT COUNT(*) FROM index_ohlc_history").fetchone()[0]
    distinct = conn.execute("SELECT COUNT(DISTINCT trading_date) FROM index_ohlc_history").fetchone()[0]
    assert total == distinct
    conn.close()


def test_db_ohlc_status_values():
    conn = sqlite3.connect(str(DB))
    statuses = {r[0] for r in conn.execute(
        "SELECT DISTINCT ohlc_status FROM index_ohlc_history"
    ).fetchall()}
    assert statuses == {"genuine", "placeholder", "invalid"}
    genuine = conn.execute("SELECT COUNT(*) FROM index_ohlc_history WHERE ohlc_status='genuine'").fetchone()[0]
    placeholder = conn.execute("SELECT COUNT(*) FROM index_ohlc_history WHERE ohlc_status='placeholder'").fetchone()[0]
    invalid = conn.execute("SELECT COUNT(*) FROM index_ohlc_history WHERE ohlc_status='invalid'").fetchone()[0]
    assert genuine == 2217
    assert placeholder == 3079
    assert invalid == 54
    conn.close()


def test_db_volume_is_turnover():
    conn = sqlite3.connect(str(DB))
    vol_count = conn.execute("SELECT COUNT(*) FROM index_ohlc_history WHERE volume IS NOT NULL").fetchone()[0]
    assert vol_count == 2413
    vol_type = conn.execute("SELECT DISTINCT volume_type FROM index_ohlc_history WHERE volume IS NOT NULL").fetchone()[0]
    assert vol_type == "turnover_npr"
    conn.close()


def test_db_no_null_close():
    conn = sqlite3.connect(str(DB))
    null_close = conn.execute("SELECT COUNT(*) FROM index_ohlc_history WHERE close IS NULL OR close = 0").fetchone()[0]
    assert null_close == 0
    conn.close()


def test_db_date_range():
    conn = sqlite3.connect(str(DB))
    mn, mx = conn.execute("SELECT MIN(trading_date), MAX(trading_date) FROM index_ohlc_history").fetchone()
    assert mn == "2003-07-17"
    assert mx == "2026-10-15"
    conn.close()


def test_api_ohlc_endpoint(client):
    resp = client.get("/api/indices/NEPSE/ohlc?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "NEPSE"
    assert data["rows_total"] == 3
    assert data["rows_returned"] == 3
    assert data["genuine_ohlc_count"] == 2
    assert data["placeholder_ohlc_count"] == 1
    assert data["invalid_ohlc_count"] == 0
    # Genuine-OHLC coverage dates: the frontend quotes these so the candle
    # region's start is never a mystery. The placeholder row (2003-07-17) is
    # close-only and must not be reported as the candle start.
    assert data["genuine_first_date"] == "2026-10-13"
    assert data["genuine_last_date"] == "2026-10-14"
    assert data["volume_rows"] == 2
    assert data["volume_type"] == "market-wide turnover in NPR (not share volume)"
    assert "bars" in data
    assert len(data["bars"]) == 3


def test_api_ohlc_bar_structure(client):
    resp = client.get("/api/indices/NEPSE/ohlc?limit=1")
    data = resp.json()
    bar = data["bars"][0]
    assert "date" in bar
    assert "open" in bar
    assert "high" in bar
    assert "low" in bar
    assert "close" in bar
    assert "volume" in bar
    assert "ohlc_status" in bar


def test_api_ohlc_genuine_only(client):
    resp = client.get("/api/indices/NEPSE/ohlc?genuine_only=true&limit=10")
    data = resp.json()
    assert all(b["ohlc_status"] == "genuine" for b in data["bars"])
    assert data["rows_total"] == 2  # filtered to genuine only


def test_api_ohlc_404_for_unknown(client):
    resp = client.get("/api/indices/UNKNOWN/ohlc")
    assert resp.status_code == 404


def test_placeholder_ohlc_has_null_ohlc(client):
    conn = sqlite3.connect(str(DB))
    # Find a placeholder row
    row = conn.execute(
        "SELECT open, high, low, close FROM index_ohlc_history WHERE ohlc_status='placeholder' LIMIT 1"
    ).fetchone()
    conn.close()
    # Placeholder rows have NULL for open/high/low (close-only data, not fabricated)
    assert row[0] is None and row[1] is None and row[2] is None
    assert row[3] is not None and row[3] > 0


def test_genuine_ohlc_has_valid_ordering(client):
    conn = sqlite3.connect(str(DB))
    rows = conn.execute(
        "SELECT open, high, low, close FROM index_ohlc_history WHERE ohlc_status='genuine' LIMIT 100"
    ).fetchall()
    conn.close()
    for o, h, l, c in rows:
        assert h >= max(o, c), f"high {h} < max({o},{c})"
        assert l <= min(o, c), f"low {l} > min({o},{c})"
        assert h >= l, f"high {h} < low {l}"


def test_volume_not_share_volume():
    """Volume field is market-wide turnover in NPR, not share volume."""
    conn = sqlite3.connect(str(DB))
    # Volume values are in billions (NPR turnover), not millions (share count)
    max_vol = conn.execute("SELECT MAX(volume) FROM index_ohlc_history").fetchone()[0]
    conn.close()
    assert max_vol > 1e9  # billions = NPR turnover, not share count


def test_ohlc_status_placeholder_before_2017():
    """Rows before 2017 should mostly be placeholder."""
    conn = sqlite3.connect(str(DB))
    pre_2017 = conn.execute(
        "SELECT COUNT(*) FROM index_ohlc_history WHERE trading_date < '2017-01-01'"
    ).fetchone()[0]
    pre_2017_genuine = conn.execute(
        "SELECT COUNT(*) FROM index_ohlc_history WHERE trading_date < '2017-01-01' AND ohlc_status='genuine'"
    ).fetchone()[0]
    conn.close()
    # Most pre-2017 rows should be placeholder
    assert pre_2017_genuine < pre_2017 * 0.5


# --- Index structure (OHLC swings) tests ---

def test_api_index_structure_endpoint(client):
    resp = client.get("/api/indices/NEPSE/structure")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "NEPSE"
    assert data["counts"]["bars"] == 2  # 2 genuine rows in sample data
    assert data["counts"]["swings"] >= 0
    assert "data_quality" in data
    assert data["data_quality"]["genuine_rows_used"] == 2
    assert "caveats" in data


def test_api_index_structure_excludes_placeholders(client):
    """Structure endpoint uses only genuine OHLC rows."""
    resp = client.get("/api/indices/NEPSE/structure")
    data = resp.json()
    # Should only use genuine rows (2 in sample), not placeholder (1)
    assert data["data_quality"]["genuine_rows_used"] == 2


def test_api_index_structure_404_for_no_genuine(client):
    """Returns 404 when no genuine OHLC data exists."""
    # Insert a test index with only placeholder data
    import sqlite3
    db_path = __import__("pathlib").Path(os.environ.get("MEGATOOL_APP_DB", ""))
    if not db_path or not db_path.exists():
        pytest.skip("No isolated DB")
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        INSERT OR REPLACE INTO index_ohlc_history
        (index_name, trading_date, open, high, low, close, volume, volume_type, ohlc_status, source)
        VALUES ('TESTIDX', '2026-10-13', 100, 100, 100, 100, NULL, NULL, 'placeholder', 'test')
    """)
    conn.commit()
    conn.close()
    resp = client.get("/api/indices/TESTIDX/structure")
    assert resp.status_code == 404
