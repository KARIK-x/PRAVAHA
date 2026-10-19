"""Corporate-action registry tests (Milestone 1).

These tests enforce the *decision rules* rather than pinning every factual
entry: the registry must (a) never claim a successor it cannot attest,
(b) represent a merger as many-to-one, (c) retire both parents, and
(d) plug into the same eligibility gate the scanner and API already use, so
a merged symbol is excluded from the active universe even though the
production ``security_master`` is empty.

Nothing here writes to a real database: the store is a throwaway DuckDB file.
"""

from __future__ import annotations

from megatool import corporate_actions as ca
from megatool.market_store import (
    STATUS_MERGED,
    MarketStore,
    eligibility_from_meta,
)

# --------------------------------------------------------------- registry shape


def test_every_entry_is_a_retirement():
    for action in ca.VERIFIED_CORPORATE_ACTIONS:
        assert action.is_active is False
        assert ca.is_inactive(action.symbol)


def test_symbols_are_unique():
    syms = [a.symbol for a in ca.VERIFIED_CORPORATE_ACTIONS]
    assert len(syms) == len(set(syms))


def test_successor_is_never_a_dimensionless_guess():
    """A successor is either a real ticker or absent — never empty/fabricated."""
    for action in ca.VERIFIED_CORPORATE_ACTIONS:
        if action.successor is not None:
            assert action.successor.strip() == action.successor
            assert action.successor
            assert action.successor != action.symbol


def test_merger_is_many_to_one_not_a_rename():
    """LBL is not "Laxmi Sunrise"; LBL *and* SRBL combine into LSL."""
    lsl_parents = {a.symbol for a in ca.VERIFIED_CORPORATE_ACTIONS if a.successor == "LSL"}
    assert lsl_parents == {"LBL", "SRBL"}
    for sym in ("LBL", "SRBL"):
        action = ca.get(sym)
        assert action.relationship == ca.RELATIONSHIP_MERGER
        assert action.parents == ("LBL", "SRBL")


def test_the_seven_reconciled_symbols_all_resolve():
    """The exact set Milestone 1 was chartered to decide."""
    expected = {
        "LBL": "LSL",
        "NIB": "NIMB",
        "PLI": "PMLI",
        "PLIC": "HLI",
        "RHPC": "RIDI",
        "SLI": "SRLI",
        "SLICL": "SJLIC",
    }
    for sym, successor in expected.items():
        assert ca.successor_of(sym) == successor, sym


def test_unresearched_successors_are_null_not_guessed():
    """SOURCE_ATTESTED entries must not carry an invented successor."""
    for action in ca.VERIFIED_CORPORATE_ACTIONS:
        if action.grade == ca.EVIDENCE_SOURCE_ATTESTED:
            assert action.successor is None


def test_every_entry_cites_evidence():
    for action in ca.VERIFIED_CORPORATE_ACTIONS:
        assert action.evidence, action.symbol
        assert all(e.strip() for e in action.evidence)


# ------------------------------------------------------------- filtering helpers


def test_split_inactive_partitions_in_order():
    active, retired = ca.split_inactive(["NABIL", "LBL", "SRBL", "ADBL", "nib"])
    assert active == ["NABIL", "ADBL"]
    assert retired == ["LBL", "SRBL", "NIB"]


def test_unattested_symbol_is_not_dropped():
    assert ca.drop_inactive(["NABIL", "ADBL"]) == ["NABIL", "ADBL"]
    assert ca.is_inactive("NABIL") is False


# ------------------------------------------------------ security-master export


def test_security_master_rows_shape():
    rows = {r["symbol"]: r for r in ca.security_master_rows()}
    assert rows["LBL"]["status"] == STATUS_MERGED
    assert rows["LBL"]["successor_symbol"] == "LSL"
    # A source-attested entry omits successor_symbol entirely (never NULL-guess).
    assert "successor_symbol" not in rows["BOKL"]
    assert all(r["source"] for r in rows.values())


# ------------------------------------------------- eligibility integration


def test_registry_excludes_merged_symbol_from_active_universe():
    """The core Milestone-1 property: a merged symbol is ineligible without
    any stored metadata row, because the registry supplies the status."""
    registry = ca.registry_meta(["LBL", "NABIL"])
    assert registry["LBL"]["status"] == STATUS_MERGED

    allowed, reason = eligibility_from_meta(registry["LBL"], exclude_delisted=True)
    assert allowed is False and "MERGED" in reason

    # A symbol the registry does not retire and that has no row stays allowed.
    allowed, reason = eligibility_from_meta(registry.get("NABIL"), exclude_delisted=True)
    assert allowed is True


def test_stored_metadata_wins_over_registry():
    """A stored ACTIVE row must override the registry (provenance precedence)."""
    stored = {"LBL": {"status": "ACTIVE"}}
    merged = {**ca.registry_meta(["LBL"]), **stored}
    assert merged["LBL"]["status"] == "ACTIVE"


def test_research_mode_still_reaches_a_retired_symbol():
    allowed, _ = eligibility_from_meta(ca.registry_meta(["LBL"])["LBL"], exclude_delisted=False)
    assert allowed is True


def test_registry_status_is_not_silently_delisted():
    row = ca.registry_meta(["LBL"])["LBL"]
    assert row["status"] == STATUS_MERGED
    assert row["status"] != "DELISTED"
    assert row["delisted"] is False


# ------------------------------------------------------------ store round-trip


def test_upsert_of_registry_rows_reads_back_as_merged(tmp_path):
    store = MarketStore(tmp_path / "ca.duckdb")
    try:
        store.upsert_securities(ca.security_master_rows())
        meta = store.securities_meta(["LBL", "NIB", "BOKL"])
        assert meta["LBL"]["status"] == STATUS_MERGED
        assert meta["LBL"]["successor_symbol"] == "LSL"
        assert meta["NIB"]["successor_symbol"] == "NIMB"
        # Attested-but-unresearched successor round-trips as NULL, not "".
        assert meta["BOKL"]["successor_symbol"] is None
        assert meta["BOKL"]["status"] == STATUS_MERGED
    finally:
        store.close()


def test_unrelated_symbol_has_no_registry_status():
    assert ca.registry_meta(["NABIL"]) == {}
    assert ca.get("NABIL") is None


# --------------------------------------------------------------- markdown audit


def test_markdown_lists_every_entry_and_disclaims_writes():
    text = ca.render_markdown()
    for action in ca.VERIFIED_CORPORATE_ACTIONS:
        assert action.symbol in text
    assert "Nothing here has been written to the production database" in text
