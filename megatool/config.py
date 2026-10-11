"""Runtime configuration for Mega Tool.

All paths resolve relative to the project root so the application can be started
from any working directory. Secrets are read from environment variables / .env and
are never hard-coded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # dotenv is optional; the app runs fine without a .env file
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - environment dependent
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("MEGATOOL_DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EXPORT_DIR = DATA_DIR / "exports"
WEB_DIR = PROJECT_ROOT / "web" / "static"

# Bounded network defaults (Rule 5: never wait indefinitely).
HTTP_TIMEOUT_SECONDS = float(os.getenv("MEGATOOL_HTTP_TIMEOUT", "20"))
HTTP_MAX_RETRIES = int(os.getenv("MEGATOOL_HTTP_RETRIES", "3"))
HTTP_BACKOFF_SECONDS = float(os.getenv("MEGATOOL_HTTP_BACKOFF", "1.0"))

# Polite rate limit for public dataset downloads (requests per second ceiling).
DOWNLOAD_RPS = float(os.getenv("MEGATOOL_DOWNLOAD_RPS", "4"))

# Optional external AI provider. Never required; the rest of the app works without it.
AI_PROVIDER = os.getenv("MEGATOOL_AI_PROVIDER", "").strip()
AI_API_KEY = os.getenv("MEGATOOL_AI_API_KEY", "").strip()
AI_MODEL = os.getenv("MEGATOOL_AI_MODEL", "").strip()

HOST = os.getenv("MEGATOOL_HOST", "127.0.0.1")
PORT = int(os.getenv("MEGATOOL_PORT", "8710"))


@dataclass(slots=True)
class Paths:
    """Resolved on-disk locations. Created lazily by :func:`ensure_dirs`."""

    data: Path = DATA_DIR
    raw: Path = RAW_DIR
    processed: Path = PROCESSED_DIR
    exports: Path = EXPORT_DIR
    web: Path = WEB_DIR
    extra: dict[str, Path] = field(default_factory=dict)

    @property
    def app_db(self) -> Path:
        """SQLite database: application state, watchlists, portfolio, journal."""
        return self.processed / "megatool_state.sqlite"

    @property
    def market_db(self) -> Path:
        """DuckDB database: analytical market history."""
        return self.processed / "megatool_market.duckdb"


def ensure_dirs(paths: Paths | None = None) -> Paths:
    """Create the local directory tree if it does not exist."""
    p = paths or Paths()
    for d in (p.data, p.raw, p.processed, p.exports):
        d.mkdir(parents=True, exist_ok=True)
    return p


PATHS = Paths()
