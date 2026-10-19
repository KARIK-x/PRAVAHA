"""Verified registry of Nepal market-news / disclosure sources (Milestone 5).

WHY THIS EXISTS
---------------
The news/events workstream (register item 7 / L4) stores exactly what the owner
imports and fetches nothing, because **no general-news feed has a confirmed
right to automated ingestion**. Without a written record of which sources exist,
what each one actually offers, and whether we may pull from it, the same
question is re-litigated every session.

This module is that record. It is deliberately conservative: a source is marked
``permitted`` for automatic ingestion only when its access model is a public,
machine-readable endpoint that an ordinary unauthenticated client may poll —
i.e. the exchange's own notices/disclosures. Everything else is
``review_required`` (needs the owner's licensing decision) or ``not_permitted``.

It deliberately does **not** encode any credential, bypass, or scraping recipe.
A source listed here is a *candidate*, not a connection: connecting one is a
separate, owner-approved step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: What kind of publisher a source is. Scope matters: the platform's news
#: feature is scoped to exchange notices, regulatory disclosures and verified
#: corporate filings — not general journalism.
KIND_EXCHANGE = "exchange"
KIND_REGULATOR = "regulator"
KIND_DISCLOSURE = "disclosure_aggregator"
KIND_FILING = "corporate_filing"
KIND_NEWS = "news_portal"
KIND_DEVELOPMENT = "development_agency"

#: How the source is accessed, for a plain unauthenticated client.
ACCESS_PUBLIC_JSON = "public_json"  # a documented static/JSON endpoint
ACCESS_PUBLIC_HTML = "public_html"  # pages rendered for humans
ACCESS_RSS = "rss"
ACCESS_MANUAL_EXPORT = "manual_export"  # the owner supplies a file
ACCESS_AUTH_REQUIRED = "auth_required"  # a login/token the project must not bypass

#: May we ingest it automatically?
PERMITTED = "permitted"  # public, machine-readable disclosures; no login needed
REVIEW_REQUIRED = "review_required"  # terms/licence undecided — owner decision
NOT_PERMITTED = "not_permitted"  # no right to automated ingestion


@dataclass(frozen=True, slots=True)
class NewsSource:
    key: str
    name: str
    homepage: str
    kind: str
    access: str
    permission: str
    machine_readable: bool
    note: str

    @property
    def auto_ingestible(self) -> bool:
        return self.permission == PERMITTED and self.machine_readable


SOURCES: tuple[NewsSource, ...] = (
    # -- the only class with a confirmed right to automatic ingestion ----------
    NewsSource(
        key="nepse_notices",
        name="Nepal Stock Exchange — notices, disclosures and exchange messages",
        homepage="https://www.nepalstock.com",
        kind=KIND_EXCHANGE,
        access=ACCESS_PUBLIC_JSON,
        permission=PERMITTED,
        machine_readable=True,
        note=(
            "already connected via the YONEPSE mirror (data/notify/*.json); the "
            "official /api/nots/* endpoints return 401 and are not bypassed"
        ),
    ),
    NewsSource(
        key="sebon",
        name="Securities Board of Nepal — notices and directives",
        homepage="https://www.sebon.gov.np",
        kind=KIND_REGULATOR,
        access=ACCESS_PUBLIC_HTML,
        permission=REVIEW_REQUIRED,
        machine_readable=False,
        note="public regulator pages; no documented JSON feed; terms not confirmed",
    ),
    NewsSource(
        key="nrb",
        name="Nepal Rastra Bank — press releases and circulars",
        homepage="https://www.nrb.org.np",
        kind=KIND_REGULATOR,
        access=ACCESS_PUBLIC_HTML,
        permission=REVIEW_REQUIRED,
        machine_readable=False,
        note="public regulator pages; no documented JSON feed; terms not confirmed",
    ),
    NewsSource(
        key="nef",
        name="Nepal Economic Forum",
        homepage="https://www.nef.org.np",
        kind=KIND_REGULATOR,
        access=ACCESS_PUBLIC_HTML,
        permission=REVIEW_REQUIRED,
        machine_readable=False,
        note="policy commentary; licensing undecided",
    ),
    NewsSource(
        key="world_bank_nepal",
        name="World Bank — Nepal",
        homepage="https://www.worldbank.org/en/country/nepal",
        kind=KIND_DEVELOPMENT,
        access=ACCESS_RSS,
        permission=REVIEW_REQUIRED,
        machine_readable=True,
        note="publishes open data and RSS; per-dataset terms vary — verify before use",
    ),
    NewsSource(
        key="undp_nepal",
        name="UNDP Nepal",
        homepage="https://www.undp.org/nepal",
        kind=KIND_DEVELOPMENT,
        access=ACCESS_RSS,
        permission=REVIEW_REQUIRED,
        machine_readable=True,
        note="open data and publications; per-item terms vary — verify before use",
    ),
    # -- Nepali financial news publishers (all need an owner licensing ruling) --
    *(
        NewsSource(
            key=key,
            name=name,
            homepage=home,
            kind=KIND_NEWS,
            access=ACCESS_PUBLIC_HTML,
            permission=REVIEW_REQUIRED,
            machine_readable=False,
            note="no confirmed right to automated ingestion (register L4)",
        )
        for key, name, home in (
            ("sharesansar", "ShareSansar", "https://www.sharesansar.com"),
            ("merolagani", "Mero Lagani", "https://merolagani.com"),
            ("nepalipaisa", "Nepali Paisa", "https://nepalipaisa.com"),
            ("arthasansar", "Artha Sansar", "https://arthasansar.com"),
            ("bizmandu", "Bizmandu", "https://www.bizmandu.com"),
            ("business360", "Business 360", "https://www.b360nepal.com"),
            ("fiscalnepal", "Fiscal Nepal", "https://fiscalnepal.com"),
            ("capitalnepal", "Capital Nepal", "https://www.capitalnepal.com"),
            ("kathmandupost", "The Kathmandu Post", "https://kathmandupost.com"),
            ("myrepublica", "MyRepublica", "https://myrepublica.nagariknetwork.com"),
            ("nagarik", "Nagarik", "https://nagariknews.nagariknetwork.com"),
            ("onlinekhabar", "Onlinekhabar", "https://english.onlinekhabar.com"),
        )
    ),
    # -- auth-gated: explicitly out of scope -----------------------------------
    NewsSource(
        key="nepse_authed_api",
        name="NEPSE authenticated data API (Salter token)",
        homepage="https://www.nepalstock.com",
        kind=KIND_EXCHANGE,
        access=ACCESS_AUTH_REQUIRED,
        permission=NOT_PERMITTED,
        machine_readable=True,
        note=(
            "data endpoints require a derived Authorization header; deriving it "
            "would be access-control work and is refused by policy"
        ),
    ),
)


_BY_KEY = {s.key: s for s in SOURCES}

#: Placeholder for the mission's "others" bucket — declared so the registry is
#: complete without inventing a source.
OTHER_NOTE = (
    "the mission's 'and others' is not enumerated; add a source here only with "
    "a documented access model and permission status"
)


def get(key: str) -> NewsSource | None:
    return _BY_KEY.get(key)


def permitted_sources() -> tuple[NewsSource, ...]:
    """Sources we may actually ingest automatically today."""
    return tuple(s for s in SOURCES if s.auto_ingestible)


def review_required_sources() -> tuple[NewsSource, ...]:
    return tuple(s for s in SOURCES if s.permission == REVIEW_REQUIRED)


def summary() -> dict[str, Any]:
    by_permission: dict[str, int] = {}
    for s in SOURCES:
        by_permission[s.permission] = by_permission.get(s.permission, 0) + 1
    return {
        "total_sources": len(SOURCES),
        "by_permission": by_permission,
        "permitted_automatic_ingestion": [s.key for s in permitted_sources()],
        "review_required": [s.key for s in review_required_sources()],
        "policy": (
            "only public, machine-readable exchange/regulator disclosures with no "
            "login are auto-ingestible; general news portals await an owner "
            "licensing ruling; auth-gated exchange endpoints are out of scope"
        ),
        "other_note": OTHER_NOTE,
    }


def render_markdown() -> str:
    lines = [
        "# Nepal market-news / disclosure source registry (Milestone 5)",
        "",
        f"Sources recorded: {len(SOURCES)}. Auto-ingestible today: {len(permitted_sources())}.",
        "",
        "**Nothing here is a live connection.** This is a candidate registry; "
        "connecting a source is a separate owner-approved step.",
        "",
        "| key | name | kind | access | permission | machine-readable |",
        "|---|---|---|---|---|---|",
    ]
    for s in SOURCES:
        lines.append(
            f"| `{s.key}` | {s.name} | {s.kind} | {s.access} | **{s.permission}** | "
            f"{'yes' if s.machine_readable else 'no'} |"
        )
    lines += ["", "## Notes", ""]
    for s in SOURCES:
        lines.append(f"- `{s.key}` — {s.note}")
    return "\n".join(lines)
