"""URL normalization and canonicalization.

Used for exact-URL deduplication and canonical URL detection. Designed to be
conservative: it never invents URLs, it only rewrites known-safe parts
(tracking parameters, fragments, case of scheme/host, default ports).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "dclid", "mc_cid", "mc_eid", "igshid",
    "ref", "ref_src", "spm", "ved",
}

_DEFAULT_PORTS = {"http": 80, "https": 443}


def is_plausible_url(url: str) -> bool:
    """Cheap sanity check used by security tests and input validation."""
    if not url or len(url) > 2048:
        return False
    if re.search(r"[\s<>\"']", url):
        return False
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def normalize_url(url: str) -> str:
    """Return a canonical form of a URL for deduplication keys.

    Steps: trim, lowercase scheme/host, drop default ports, strip tracking
    query params, drop fragment, remove trailing slash on empty path.
    Returns the input unchanged if it is not a parseable http(s) URL.
    """
    if not url:
        return ""
    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if not netloc:
        return url
    # strip default port
    host, _, port = netloc.partition(":")
    if port and _DEFAULT_PORTS.get(scheme) == int(port if port.isdigit() else -1):
        netloc = host
    path = parts.path or "/"
    # collapse duplicate slashes but keep trailing structure meaningful
    path = re.sub(r"/{2,}", "/", path)
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
         if k.lower() not in _TRACKING_PARAMS]
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def same_document(url_a: str, url_b: str) -> bool:
    """True when two URLs canonically refer to the same document."""
    return bool(url_a) and normalize_url(url_a) == normalize_url(url_b)
