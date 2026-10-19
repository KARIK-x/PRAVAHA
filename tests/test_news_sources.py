"""News-source registry tests (Milestone 5)."""

from __future__ import annotations

from megatool import news_sources as ns


def test_registry_has_no_duplicate_keys():
    keys = [s.key for s in ns.SOURCES]
    assert len(keys) == len(set(keys))


def test_every_source_states_an_explicit_permission():
    allowed = {ns.PERMITTED, ns.REVIEW_REQUIRED, ns.NOT_PERMITTED}
    for s in ns.SOURCES:
        assert s.permission in allowed, s.key
        assert s.note.strip(), s.key


def test_only_public_machine_readable_sources_are_auto_ingestible():
    for s in ns.permitted_sources():
        assert s.machine_readable
        assert s.access in {ns.ACCESS_PUBLIC_JSON, ns.ACCESS_RSS}


def test_auth_gated_source_is_never_auto_ingestible():
    gated = ns.get("nepse_authed_api")
    assert gated is not None
    assert gated.permission == ns.NOT_PERMITTED
    assert gated.auto_ingestible is False


def test_general_news_portals_await_a_licensing_ruling():
    """The documented blocker (L4): no general news portal is auto-ingestible."""
    for key in ("sharesansar", "merolagani", "kathmandupost", "onlinekhabar"):
        s = ns.get(key)
        assert s is not None
        assert s.permission == ns.REVIEW_REQUIRED
        assert s.auto_ingestible is False


def test_exchange_notices_are_the_permitted_baseline():
    permitted = {s.key for s in ns.permitted_sources()}
    assert "nepse_notices" in permitted


def test_summary_is_consistent():
    summ = ns.summary()
    assert summ["total_sources"] == len(ns.SOURCES)
    assert sum(summ["by_permission"].values()) == len(ns.SOURCES)
    assert summ["permitted_automatic_ingestion"] == [s.key for s in ns.permitted_sources()]


def test_markdown_disclaims_being_a_live_connection():
    text = ns.render_markdown()
    assert "Nothing here is a live connection" in text
    for s in ns.SOURCES:
        assert s.key in text
