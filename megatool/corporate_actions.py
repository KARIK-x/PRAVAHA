"""Verified NEPSE corporate actions — symbol mergers, renames and retirements.

WHY THIS EXISTS
---------------
The price store keeps history for every symbol NEPSE ever published, so a
symbol that was *merged away in 2023* still has bars and still looks like a
security. Nothing in the price table says the symbol stopped being tradable:
the last bar is simply old. A screening or ranking run that only reads prices
therefore happily ranks a 2023-merger stub against its live peers, using
three-year-old closes.

The sector workstream (BLOCKER 1) hit exactly this: four compiled sector
sources each list the pre-merger symbols, because they record the *issuer*
that once existed. `SRBL` ("Sunrise Bank Limited") was ranked inside
"Commercial Banks" against live banks because no source said it no longer
trades.

This module is the missing signal. It records only corporate actions that are
**attested**, and it records *how* each one is attested so a reviewer can
audit the list instead of trusting it. It never infers a status from a
symbol's name, its absence from a feed, or the mere age of its last bar.

EVIDENCE GRADE
--------------
``VERIFIED``
    Two or more independent signals agree: an authoritative source
    (acquirer/exchange notice or the successor company's own history) **and**
    the price series handoff (both parents' last bar immediately precedes the
    successor's first bar).

``SOURCE_ATTESTED``
    One compilation explicitly marks the symbol ``merged`` **and** the stored
    series is long dead (no bar for years). Status is accepted; the successor
    is left ``None`` rather than guessed.

Nothing is ever written to the production database by importing this module.

RELATIONSHIP SEMANTICS
----------------------
A merger is many-to-one: two or more parents combine into one successor. The
registry models that directly (``parents`` → ``successor``) instead of the
false one-to-one "old symbol became new symbol" that a naive rename map
implies. Sector classification is **never** inherited across the action: the
successor carries its own independently-sourced classification, and the
parents are retired. The parents' business sectors are recorded only so the
*relationship* stays auditable.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

#: Evidence grades, weakest to strongest. Nothing below ``SOURCE_ATTESTED``
#: is ever recorded: an unattested symbol is simply absent from the registry.
EVIDENCE_VERIFIED = "verified"
EVIDENCE_SOURCE_ATTESTED = "source_attested"

#: The four canonical relationship kinds this registry recognises.
#: ``merger``      — parents combine into a new legal entity (new symbol).
#: ``rename``      — same entity, new ticker (name change).
#: ``delisting``   — retired with no successor.
#: ``amalgamation``— a parent absorbed into a pre-existing listed survivor.
RELATIONSHIP_MERGER = "merger"
RELATIONSHIP_RENAME = "rename"
RELATIONSHIP_DELISTING = "delisting"
RELATIONSHIP_AMALGAMATION = "amalgamation"


@dataclass(frozen=True, slots=True)
class CorporateAction:
    """One attested corporate action involving ``symbol``.

    ``symbol`` is the retired/parent ticker. ``successor`` is the surviving
    ticker, or ``None`` when the relationship is unknown or a pure delisting.
    ``parents`` lists every ticker that combined into the successor (including
    ``symbol``), so a many-to-one merger is represented faithfully.
    """

    symbol: str
    company_name: str
    relationship: str
    successor: str | None
    successor_name: str | None
    last_trade_date: str | None
    successor_first_date: str | None
    parents: tuple[str, ...]
    evidence: tuple[str, ...]
    grade: str

    @property
    def is_active(self) -> bool:
        """Retired symbols are never active, whatever the relationship kind."""
        return False


# ---------------------------------------------------------------------------
# The registry. Every entry states its evidence; nothing is inferred from a
# name. Dates are ISO-8601 trade dates observed in the store unless the marker
# is explicitly an effective date from a public notice.
# ---------------------------------------------------------------------------

_P = "binayabaral/nepse-symbols.csv status='merged'"
_HANDOFF = "store handoff: both parents' last bar {last}; successor first bar {first}"

VERIFIED_CORPORATE_ACTIONS: tuple[CorporateAction, ...] = (
    # ---------------------------------------------------------------- banks
    CorporateAction(
        symbol="LBL",
        company_name="Laxmi Bank Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="LSL",
        successor_name="Laxmi Sunrise Bank Limited",
        last_trade_date="2023-07-13",
        successor_first_date="2023-08-28",
        parents=("LBL", "SRBL"),
        evidence=(
            _P,
            "price handoff: LBL and SRBL last bar 2023-07-13; LSL first bar 2023-08-28",
            "successor name is the concatenation of both parents' names",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    CorporateAction(
        symbol="SRBL",
        company_name="Sunrise Bank Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="LSL",
        successor_name="Laxmi Sunrise Bank Limited",
        last_trade_date="2023-07-13",
        successor_first_date="2023-08-28",
        parents=("LBL", "SRBL"),
        evidence=(
            _P,
            "price handoff: LBL and SRBL last bar 2023-07-13; LSL first bar 2023-08-28",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    CorporateAction(
        symbol="NIB",
        company_name="Nepal Investment Bank Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="NIMB",
        successor_name="Nepal Investment Mega Bank Limited",
        last_trade_date="2023-01-10",
        successor_first_date="2023-02-23",
        parents=("NIB", "MEGA"),
        evidence=(
            _P,
            "price handoff: NIB and MEGA last bar 2023-01-10; NIMB first bar 2023-02-23",
            "successor name is the concatenation of both parents' names",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    CorporateAction(
        symbol="MEGA",
        company_name="Mega Bank Nepal Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="NIMB",
        successor_name="Nepal Investment Mega Bank Limited",
        last_trade_date="2023-01-10",
        successor_first_date="2023-02-23",
        parents=("NIB", "MEGA"),
        evidence=(
            _P,
            "price handoff: NIB and MEGA last bar 2023-01-10; NIMB first bar 2023-02-23",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    # ------------------------------------------------------- life insurance
    CorporateAction(
        symbol="PLI",
        company_name="Prabhu Life Insurance Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="PMLI",
        successor_name="Prabhu Mahalaxmi Life Insurance Company Limited",
        last_trade_date="2023-07-13",
        successor_first_date="2023-12-19",
        parents=("PLI", "MLICL"),
        evidence=(
            "public merger notice: Prabhu Life Insurance Ltd and Mahalaxmi Life "
            "Insurance Ltd merged with effect from 2080-03-29 B.S. (2023-07-14 AD)",
            "PMLI company history states merger date 2023-07-14",
            "price handoff: PLI last bar 2023-07-13, the session before the effective date",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    CorporateAction(
        symbol="PLIC",
        company_name="Prime Life Insurance Company Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="HLI",
        successor_name="Himalayan Life Insurance Limited",
        last_trade_date="2023-05-08",
        successor_first_date="2023-06-22",
        parents=("PLIC", "GLICL"),
        evidence=(
            _P,
            "price handoff: PLIC and GLICL last bar 2023-05-08; HLI first bar 2023-06-22",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    CorporateAction(
        symbol="GLICL",
        company_name="Gurans Life Insurance Company Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="HLI",
        successor_name="Himalayan Life Insurance Limited",
        last_trade_date="2023-05-08",
        successor_first_date="2023-06-22",
        parents=("PLIC", "GLICL"),
        evidence=(
            _P,
            "price handoff: PLIC and GLICL last bar 2023-05-08; HLI first bar 2023-06-22",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    CorporateAction(
        symbol="SLI",
        company_name="Sanima Life Insurance Company Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="SRLI",
        successor_name="Sanima Reliance Life Insurance Limited",
        last_trade_date="2023-03-22",
        successor_first_date="2023-05-21",
        parents=("SLI", "RLI"),
        evidence=(
            _P,
            "price handoff: SLI and RLI last bar 2023-03-22; SRLI first bar 2023-05-21",
            "successor name is the concatenation of both parents' names",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    CorporateAction(
        symbol="RLI",
        company_name="Reliance Life Insurance Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="SRLI",
        successor_name="Sanima Reliance Life Insurance Limited",
        last_trade_date="2023-03-22",
        successor_first_date="2023-05-21",
        parents=("SLI", "RLI"),
        evidence=(
            _P,
            "price handoff: SLI and RLI last bar 2023-03-22; SRLI first bar 2023-05-21",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    CorporateAction(
        symbol="SLICL",
        company_name="Surya Life Insurance Company Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="SJLIC",
        successor_name="SuryaJyoti Life Insurance Company Limited",
        last_trade_date="2022-06-26",
        successor_first_date="2023-01-25",
        parents=("SLICL", "JLI"),
        evidence=(
            _P,
            "price handoff: SLICL last bar 2022-06-26 and JLI last bar 2022-06-27; "
            "SJLIC first bar 2023-01-25",
            "successor name is the concatenation of both parents' names",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    CorporateAction(
        symbol="JLI",
        company_name="Jyoti Life Insurance Company Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="SJLIC",
        successor_name="SuryaJyoti Life Insurance Company Limited",
        last_trade_date="2022-06-27",
        successor_first_date="2023-01-25",
        parents=("SLICL", "JLI"),
        evidence=(
            _P,
            "price handoff: SLICL last bar 2022-06-26 and JLI last bar 2022-06-27; "
            "SJLIC first bar 2023-01-25",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    # ---------------------------------------------------------- hydropower
    CorporateAction(
        symbol="RHPC",
        company_name="Ridi Hydropower Development Company Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="RIDI",
        successor_name="Ridi Power Company Limited",
        last_trade_date="2021-11-02",
        successor_first_date="2022-08-15",
        parents=("RHPC", "RRHP"),
        evidence=(
            "successor company history: Ridi Power Company Limited was "
            "incorporated as Ridi Hydropower Development Company Limited and "
            "merged with Rairang Hydropower Development Company Limited",
            "public listing notice: RIDI shares listed after the RHPC + RRHP merger",
            "price handoff: RHPC last bar 2021-11-02; RIDI first bar 2022-08-15",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    CorporateAction(
        symbol="RRHP",
        company_name="Rairang Hydropower Development Company Limited",
        relationship=RELATIONSHIP_MERGER,
        successor="RIDI",
        successor_name="Ridi Power Company Limited",
        last_trade_date=None,
        successor_first_date="2022-08-15",
        parents=("RHPC", "RRHP"),
        evidence=(
            _P,
            "public listing notice: RIDI shares listed after the RHPC + RRHP merger",
        ),
        grade=EVIDENCE_VERIFIED,
    ),
    # --------------- other mergers: status attested, successor not researched
    # Their price series are long dead and one compilation marks them merged,
    # so they must not enter an active universe. The successor is left unset
    # rather than guessed; ``MERGED`` with no successor is an honest state.
    *(
        CorporateAction(
            symbol=sym,
            company_name=name,
            relationship=RELATIONSHIP_MERGER,
            successor=None,
            successor_name=None,
            last_trade_date=None,
            successor_first_date=None,
            parents=(sym,),
            evidence=(_P, "stored price series ends years before the current session"),
            grade=EVIDENCE_SOURCE_ATTESTED,
        )
        for sym, name in (
            ("BOKL", "Bank of Kathmandu Limited"),
            ("CBL", "Civil Bank Limited"),
            ("CCBL", "Century Commercial Bank Limited"),
            ("NBB", "Nepal Bangladesh Bank Limited"),
            ("NCCB", "Nepal Credit and Commerce Bank Limited"),
            ("SFCL", "Samriddhi Finance Company Limited"),
            ("SHBL", "Sahara Bikas Bank Limited"),
            ("ULI", "Union Life Insurance Company Limited"),
        )
    ),
)


# ---------------------------------------------------------------------------
# Lookup / filtering API
# ---------------------------------------------------------------------------

_BY_SYMBOL: dict[str, CorporateAction] = {a.symbol.upper(): a for a in VERIFIED_CORPORATE_ACTIONS}

#: Every attestation in the registry is a retirement: merged, renamed away or
#: delisted. There is no "active" corporate action, so the whole registry is
#: the inactive set.
INACTIVE_SYMBOLS: frozenset[str] = frozenset(_BY_SYMBOL)


def get(symbol: str) -> CorporateAction | None:
    """The attested action for ``symbol``, or ``None`` when unattested."""
    return _BY_SYMBOL.get(str(symbol).strip().upper())


def is_inactive(symbol: str) -> bool:
    """True only when a corporate action attests the symbol no longer trades."""
    return str(symbol).strip().upper() in INACTIVE_SYMBOLS


def inactive_symbols() -> frozenset[str]:
    """Every symbol the registry retires (never infer more than this)."""
    return INACTIVE_SYMBOLS


def successor_of(symbol: str) -> str | None:
    """The recorded successor ticker, or ``None`` when unknown/unattested."""
    action = get(symbol)
    return action.successor if action else None


def drop_inactive(symbols: Iterable[str]) -> list[str]:
    """Order-preserving removal of every registry-retired symbol."""
    return [str(s).upper() for s in symbols if not is_inactive(str(s))]


def split_inactive(symbols: Iterable[str]) -> tuple[list[str], list[str]]:
    """Partition into ``(active, inactive)``, each order-preserving."""
    active: list[str] = []
    retired: list[str] = []
    for raw in symbols:
        sym = str(raw).upper()
        (retired if is_inactive(sym) else active).append(sym)
    return active, retired


def security_master_rows() -> list[dict[str, Any]]:
    """Registry entries shaped for :meth:`MarketStore.upsert_securities`.

    ``status`` is ``MERGED`` for every entry (all attestations are mergers or
    amalgamations). ``successor_symbol`` is included only when one is known;
    omitting the key preserves any successor already stored and never invents
    one. ``source`` carries the evidence grade so an auditor can tell a
    two-signal verification from a single-source attestion.
    """
    from megatool.market_store import STATUS_MERGED  # local: avoid import cycle

    rows: list[dict[str, Any]] = []
    for action in VERIFIED_CORPORATE_ACTIONS:
        row: dict[str, Any] = {
            "symbol": action.symbol,
            "name": action.company_name,
            "status": STATUS_MERGED,
            "source": f"corporate-action registry ({action.grade})",
        }
        if action.successor:
            row["successor_symbol"] = action.successor
        rows.append(row)
    return rows


def registry_meta(symbols: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Registry rows in :meth:`MarketStore.securities_meta` shape.

    Only symbols the caller asked for and that the registry retires are
    returned. Callers merge the result *under* any stored metadata
    (``{**registry_meta(syms), **stored}``) so a stored row always wins and
    the registry only fills the gap left by an empty/unimported master.
    """
    from megatool.market_store import STATUS_MERGED  # local: avoid import cycle

    wanted = {str(s).upper() for s in symbols}
    out: dict[str, dict[str, Any]] = {}
    for action in VERIFIED_CORPORATE_ACTIONS:
        if action.symbol not in wanted:
            continue
        out[action.symbol] = {
            "name": action.company_name,
            "sector": None,
            "sector_source": None,
            "sector_retrieved_at": None,
            "sector_observed_date": None,
            "instrument_type": None,
            "status": STATUS_MERGED,
            "delisted": False,
            "successor_symbol": action.successor,
            "source": f"corporate-action registry ({action.grade})",
        }
    return out


def _status_is_known(stored: dict[str, Any] | None) -> bool:
    """Mirror :func:`market_store.eligibility_from_meta`'s status precedence.

    A stored row counts as *known* when it carries a canonical non-UNKNOWN
    status, or the legacy ``delisted=True`` flag. Everything else is a gap the
    registry is allowed to fill.
    """
    if not stored:
        return False
    status = str(stored.get("status") or "").strip().upper()
    if status and status != "UNKNOWN":
        return True
    return stored.get("delisted") is True


def merge_into_meta(
    meta: dict[str, dict[str, Any]],
    symbols: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """Overlay registry status onto stored metadata, without overriding it.

    ``MarketStore.securities_meta`` returns an all-``None`` row for every
    requested symbol that has no stored row, so a plain dict overlay would let
    an empty master erase the registry. This fills only genuine gaps: a stored
    row with a known status always wins, and a stored name is preserved.
    """
    out = dict(meta)
    for sym, row in registry_meta(symbols).items():
        stored = out.get(sym)
        if _status_is_known(stored):
            continue
        if stored and stored.get("name") and not row.get("name"):
            row = {**row, "name": stored["name"]}
        out[sym] = row
    return out


def active_universe_note() -> dict[str, Any]:
    """A small, reportable summary of what this registry removes."""
    verified = [a.symbol for a in VERIFIED_CORPORATE_ACTIONS if a.grade == EVIDENCE_VERIFIED]
    attested = [a.symbol for a in VERIFIED_CORPORATE_ACTIONS if a.grade == EVIDENCE_SOURCE_ATTESTED]
    with_successor = {a.symbol: a.successor for a in VERIFIED_CORPORATE_ACTIONS if a.successor}
    return {
        "retired_symbols": len(INACTIVE_SYMBOLS),
        "verified": sorted(verified),
        "source_attested": sorted(attested),
        "successors_recorded": with_successor,
        "unknown_successors": sorted(
            a.symbol for a in VERIFIED_CORPORATE_ACTIONS if not a.successor
        ),
        "policy": (
            "retired symbols are excluded from the active universe; sector "
            "classification is never inherited across the action"
        ),
    }


def render_markdown() -> str:
    """A human-auditable table of every entry and its evidence."""
    lines = [
        "# Verified corporate actions (merged / renamed / retired symbols)",
        "",
        f"Entries: {len(VERIFIED_CORPORATE_ACTIONS)} "
        f"({len(active_universe_note()['verified'])} verified, "
        f"{len(active_universe_note()['source_attested'])} source-attested)",
        "",
        "**Nothing here has been written to the production database.** These are "
        "attested corporate actions; importing them is an owner-approved step.",
        "",
        "| symbol | company | relationship | successor | last trade | successor first | grade |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in sorted(VERIFIED_CORPORATE_ACTIONS, key=lambda x: x.symbol):
        lines.append(
            f"| `{a.symbol}` | {a.company_name} | {a.relationship} | "
            f"{f'`{a.successor}`' if a.successor else '_(unknown)_'} | "
            f"{a.last_trade_date or '-'} | {a.successor_first_date or '-'} | {a.grade} |"
        )
    lines += ["", "## Evidence", ""]
    for a in sorted(VERIFIED_CORPORATE_ACTIONS, key=lambda x: x.symbol):
        lines.append(f"### `{a.symbol}` — {a.company_name}")
        for e in a.evidence:
            lines.append(f"- {e}")
        if a.parents and len(a.parents) > 1:
            lines.append(f"- parents combined: {' + '.join(a.parents)} → {a.successor}")
        lines.append("")
    return "\n".join(lines)
