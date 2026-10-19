"""Certificate-expiry and source-health cache.

Two jobs, both deliberately small:

* **Certificate inspection** — open a real TLS connection with verification ON
  (``ssl.create_default_context``) and read the peer certificate's expiry. It
  never disables verification and never records keys, tokens or handshake
  secrets — only the public subject/issuer/validity dates.

* **A health cache** — a plain JSON file that records the *last observed*
  certificate and circuit state per source. The API reads this file; it never
  performs a network or TLS check itself. That keeps the honest claim small:
  we report *"last checked at <time>"*, never *"monitored continuously"*.

Nothing here runs on its own. A health file exists only after an authorised
collector or health-check actually ran.
"""

from __future__ import annotations

import json
import os
import ssl
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from megatool.config import DATA_DIR

#: Warn this many days before ``notAfter``.
DEFAULT_WARN_DAYS = 30

#: The exchange certificate expires 2026-12-10; used in docs/tests as the known case.
KNOWN_NEPSE_NOT_AFTER = "2026-12-10"


def health_path() -> Path:
    """Location of the health cache (override with ``MEGATOOL_HEALTH_PATH``)."""
    override = os.environ.get("MEGATOOL_HEALTH_PATH")
    if override:
        return Path(override)
    return DATA_DIR / "health" / "source_health.json"


# ------------------------------------------------------------------- TLS read
def _flat_name(entries: Any) -> str | None:
    """Flatten ``getpeercert()['subject']`` into a single ``k=v`` string."""
    if not entries:
        return None
    parts: list[str] = []
    for rdn in entries:
        for key, value in rdn:
            parts.append(f"{key}={value}")
    return ", ".join(parts) or None


def _parse_cert_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromtimestamp(ssl.cert_time_to_seconds(value), tz=UTC)
    except (ValueError, OverflowError):
        return None


def certificate_info(host: str, port: int = 443, timeout: float = 10.0) -> dict[str, Any]:
    """Open a verified TLS connection and describe the peer certificate.

    Hostname and chain verification are performed by the default context; a
    failure raises rather than being papered over.
    """
    import socket

    context = ssl.create_default_context()  # verification is ON and stays ON
    with (
        socket.create_connection((host, port), timeout=timeout) as sock,
        context.wrap_socket(sock, server_hostname=host) as tls,
    ):
        cert = tls.getpeercert()
        version = tls.version()

    now = datetime.now(UTC)
    not_after = _parse_cert_time(cert.get("notAfter"))
    not_before = _parse_cert_time(cert.get("notBefore"))
    days = None if not_after is None else round((not_after - now).total_seconds() / 86400.0, 1)
    return {
        "host": host,
        "checked_at_utc": now.isoformat(),
        "subject": _flat_name(cert.get("subject")),
        "issuer": _flat_name(cert.get("issuer")),
        "not_before": not_before.isoformat() if not_before else None,
        "not_after": not_after.isoformat() if not_after else None,
        "days_remaining": days,
        "tls_version": version,
        "verified": True,
        # Deliberately NO private keys, tokens, cookies or handshake bytes.
    }


def certificate_warning(
    info: dict[str, Any] | None, warn_days: int = DEFAULT_WARN_DAYS
) -> str | None:
    """Return a warning string when the certificate is close to expiry, else None."""
    if not info:
        return "certificate expiry unknown (no check recorded)"
    days = info.get("days_remaining")
    if days is None:
        return "certificate expiry unknown (notAfter absent from the peer certificate)"
    if days <= 0:
        return f"certificate EXPIRED ({info.get('not_after')})"
    if days <= warn_days:
        return (
            f"certificate expires in {days:.0f} days ({info.get('not_after')}) — renew before then"
        )
    return None


# ----------------------------------------------------------------- health file
def read_health(path: Path | None = None) -> dict[str, Any]:
    """Read the health cache; an absent or unreadable file reads as empty."""
    p = path or health_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def update_source_health(
    source: str,
    updates: dict[str, Any],
    path: Path | None = None,
) -> dict[str, Any]:
    """Merge ``updates`` into ``source``'s record and write the cache atomically."""
    p = path or health_path()
    data = read_health(p)
    existing = data.get(source)
    merged = dict(existing) if isinstance(existing, dict) else {}
    merged.update(updates)
    data[source] = merged
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return data


def source_health_view(source: str, path: Path | None = None) -> dict[str, Any]:
    """A safe, read-only view of one source's cached health for the API."""
    rec = read_health(path).get(source)
    if not isinstance(rec, dict):
        return {"checked": False, "reason": "no health check recorded yet"}
    cert = rec.get("certificate") if isinstance(rec.get("certificate"), dict) else None
    return {
        "checked": True,
        "last_checked_at_utc": rec.get("last_checked_at_utc"),
        "certificate": cert,
        "certificate_warning": certificate_warning(cert),
        "circuit": rec.get("circuit"),
        "note": "last recorded check; this is not a continuous monitor",
    }
