#!/usr/bin/env python
"""Record a NEPSE source-health snapshot: certificate expiry + circuit state.

This is the ONLY thing that writes the health cache that ``GET /api/sources``
reads. It exists so the API can show a *last recorded* certificate check without
ever performing TLS handshakes per request.

GATED: it contacts ``nepalstock.com.np`` (TLS handshake and, when authorised, a
lightweight API probe) only when ``MEGATOOL_NEPSE_API_AUTHORIZED=1``. Without
that flag it prints how to enable it and exits 0. TLS verification is always on,
and the recorded data never contains tokens, cookies or keys.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from megatool import source_health as sh  # noqa: E402
from megatool.datasources import nepse_official_live as ol  # noqa: E402

SOURCE_KEY = "nepse-official"
HOST = "nepalstock.com.np"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default=HOST)
    p.add_argument("--warn-days", type=int, default=sh.DEFAULT_WARN_DAYS)
    p.add_argument("--health-path", type=Path, help="override the health cache path")
    p.add_argument("--json", action="store_true", help="print the health record as JSON")
    args = p.parse_args()

    if os.environ.get(ol.AUTH_ENV) != "1":
        print(
            f"source health check is gated: set {ol.AUTH_ENV}=1 to authorise "
            "contact with the NEPSE host (the collector stays off until the owner "
            "makes that ruling).",
            file=sys.stderr,
        )
        return 0

    updates: dict = {"last_checked_at_utc": datetime.now(UTC).isoformat()}

    # 1) Peer certificate (verified TLS handshake).
    try:
        cert = sh.certificate_info(args.host)
        updates["certificate"] = cert
    except Exception as exc:  # noqa: BLE001
        cert = None
        updates["certificate"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 2) Lightweight authorized probe + circuit state.
    try:
        with ol.NepseOfficialLiveClient() as client:
            status = ol.market_status_summary(client.market_status())
            updates["circuit"] = client.breaker_snapshot()
            updates["last_market_status"] = status
    except Exception as exc:  # noqa: BLE001
        updates["circuit"] = {"state": "unknown", "error": f"{type(exc).__name__}: {exc}"}

    sh.update_source_health(SOURCE_KEY, updates, args.health_path)

    warning = sh.certificate_warning(cert, args.warn_days)
    if args.json:
        print(json.dumps(updates, indent=2))
    else:
        print(f"source        : {SOURCE_KEY} ({args.host})")
        if cert and cert.get("not_after"):
            print(f"certificate   : {cert.get('subject')}")
            print(
                f"not_after     : {cert.get('not_after')}  "
                f"({cert.get('days_remaining')} days remaining)"
            )
        print(f"circuit       : {updates.get('circuit', {}).get('state')}")
        print(f"warning       : {warning or 'none'}")
        print(f"health cache  : {sh.health_path() if not args.health_path else args.health_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
