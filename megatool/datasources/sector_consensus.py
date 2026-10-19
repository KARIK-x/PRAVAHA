"""Cross-source consensus for NEPSE sector classifications (BLOCKER 1).

WHY THIS EXISTS
---------------
No single public source is both complete and correctly scoped. Four
independent compilations were collected, and **they disagree by design**:

| Source | Classifies by | Coverage |
|---|---|---|
| YONEPSE `securities.json` | issuer business sector | 649 symbols |
| `NepseAPI-Unofficial/stockmap.json` | issuer business sector | 541 |
| binayabaral `nepse-symbols.csv` | issuer business sector | 274 (with sector) |
| NepalStockData `listed_company.csv` | **instrument bucket** | 654 |

The instrument-bucket source files a bank *debenture* under "Corporate
Debentures" while the issuer-sector sources file it under the bank's business
sector. Both are internally consistent; they answer different questions. A
trading platform needs **both answers kept apart**, which is why this module
resolves them separately instead of averaging them into a single meaningless
vote.

THE RESOLUTION RULE (stated, so a reviewer can audit every assignment)
----------------------------------------------------------------------
1. **Ordinary shares** take an issuer business sector, because that is the peer
   group they compete in and therefore the correct basis for sector-relative
   work. A business sector is accepted only when at least one issuer-sector
   source states it; when two or more disagree the symbol is left
   **conflicted** and never silently averaged.
2. **Non-ordinary instruments** (mutual funds, debentures, bonds, promoter
   shares, preference shares) are **never** given an ordinary company sector.
   They are classified by instrument, because "Commercial Banks" is not the
   peer group of a 4% ADBL bond.
3. Symbols no source can classify stay **unresolved** and are reported as such.
   Nothing is inferred from a symbol's name, issuer, or history.

Instrument detection uses two independent signals — a `PO` symbol suffix (the
NEPSE promoter-share convention, e.g. ``NIMBPO``) and the source's declared
instrument type — so a missed signal on one source cannot misclassify.
"""

from __future__ import annotations

import csv
import io
from typing import Any

#: Instrument buckets that must never carry an ordinary company sector.
INSTRUMENT_BUCKETS = frozenset(
    {
        "Corporate Debentures",
        "Government Bonds",
        "Promoter Shares",
        "Preference Shares",
        "Mutual Funds",
    }
)

#: Instruments treated as ordinary equity for sector purposes.
ORDINARY_INSTRUMENTS = frozenset({"ordinary"})

#: YONEPSE instrumentType -> our canonical instrument_type.
YONEPSE_INSTRUMENT_MAP = {
    "Equity": "ordinary",
    "Non-Convertible Debentures": "debenture",
    "Mutual Funds": "mutual_fund",
    "Preference Shares": "preference",
    "Convertible Debentures": "convertible_debenture",
}

#: NepalStockData column -> canonical instrument.
NSD_INSTRUMENT_MAP = {
    "Corporate_Debentures": "debenture",
    "Government_Bonds": "government_bond",
    "Preference_Share": "preference",
    "Promoter_Share": "promoter_share",
    "Mutual_Fund": "mutual_fund",
}

#: Sector-name normalisation so the four vocabularies can be compared.
SECTOR_CANON = {
    "commercial banks": "Commercial Banks",
    "commercial bank": "Commercial Banks",
    "corporate debentures": "Corporate Debentures",
    "corporate debenture": "Corporate Debentures",
    "development banks": "Development Banks",
    "development bank limited": "Development Banks",
    "development bank": "Development Banks",
    "finance": "Finance",
    "government bonds": "Government Bonds",
    "government bond": "Government Bonds",
    "hotels and tourism": "Hotels & Tourism",
    "hotels & tourism": "Hotels & Tourism",
    "hotel & tourism": "Hotels & Tourism",
    "hydropower": "Hydropower",
    "hydro power": "Hydropower",
    "investment": "Investment",
    "life insurance": "Life Insurance",
    "manufacturing and processing": "Manufacturing & Processing",
    "manufacturing & processing": "Manufacturing & Processing",
    "microfinance": "Microfinance",
    "mutual fund": "Mutual Funds",
    "mutual funds": "Mutual Funds",
    "non life insurance": "Non-Life Insurance",
    "non-life insurance": "Non-Life Insurance",
    "others": "Others",
    "preference share": "Preference Shares",
    "preference shares": "Preference Shares",
    "promoter share": "Promoter Shares",
    "promoter shares": "Promoter Shares",
    "tradings": "Tradings",
    "trading": "Tradings",
}


class SectorConsensusError(Exception):
    """A sector source could not be read."""


def canon_sector(value: str | None) -> str | None:
    """Canonical sector name, or ``None`` for blank input."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    return SECTOR_CANON.get(text.lower(), text)


def is_promoter_share_symbol(symbol: str) -> bool:
    """NEPSE promoter-share convention: an upper-case ``PO`` suffix."""
    s = (symbol or "").strip().upper()
    return len(s) > 2 and s.endswith("PO") and s[:-2].isalnum()


# ----------------------------------------------------------------- source loaders


def load_yonepse(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """symbol -> {sector, instrument, company_name} from YONEPSE securities."""
    out: dict[str, dict[str, Any]] = {}
    for rec in records:
        symbol = (rec.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        out[symbol] = {
            "sector": canon_sector(rec.get("sectorName")),
            "instrument": YONEPSE_INSTRUMENT_MAP.get(
                (rec.get("instrumentType") or "").strip(),
                (rec.get("instrumentType") or "").strip().lower().replace(" ", "_") or None,
            ),
            "company_name": (rec.get("companyName") or "").strip() or None,
        }
    return out


def load_nepalstockdata(text: str) -> dict[str, dict[str, Any]]:
    """Parse the wide 17-column master into symbol -> {instrument, sector}.

    The columns themselves are instrument buckets, so this source contributes
    an *instrument* classification and, for ordinary equities, the business
    sector the column names.
    """
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows or len(rows[0]) < 2:
        raise SectorConsensusError("listed_company.csv has no sector columns")
    header = rows[0]
    out: dict[str, dict[str, Any]] = {}
    for row in rows[1:]:
        for idx, col in enumerate(header):
            if idx >= len(row):
                continue
            symbol = row[idx].strip().upper()
            if not symbol:
                continue
            instrument = NSD_INSTRUMENT_MAP.get(col.strip())
            business = col.strip().replace("_", " ")
            out[symbol] = {
                "instrument": instrument,
                "sector": None if instrument else canon_sector(business),
                "instrument_bucket": col.strip(),
            }
    return out


def load_stockmap(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """symbol -> {sector, company_name} from the stockmap snapshot."""
    out: dict[str, dict[str, Any]] = {}
    for symbol, rec in payload.items():
        s = str(symbol).strip().upper()
        if not s:
            continue
        out[s] = {
            "sector": canon_sector(rec.get("sector")),
            "instrument": None,
            "company_name": rec.get("name") or None,
        }
    return out


def load_binayabaral(text: str) -> dict[str, dict[str, Any]]:
    """symbol -> {sector, instrument, company_name} from the reference CSV."""
    out: dict[str, dict[str, Any]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        symbol = (row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        out[symbol] = {
            "sector": canon_sector(row.get("sector")),
            "instrument": (row.get("instrument_type") or "").strip().lower() or None,
            "company_name": (row.get("name") or "").strip() or None,
        }
    return out


# ----------------------------------------------------------------------- consensus


def classify_instrument(
    symbol: str,
    sources: dict[str, dict[str, Any]],
) -> str | None:
    """Instrument type from two independent signals; promoter suffix is one of them."""
    declared = [
        src[symbol]["instrument"]
        for src in sources.values()
        if symbol in src and src[symbol].get("instrument")
    ]
    if is_promoter_share_symbol(symbol):
        return "promoter_share"
    if declared:
        # Prefer a non-ordinary classification: an explicit debenture/mutual-fund
        # tag is stronger evidence than a generic "ordinary" default.
        specific = [d for d in declared if d != "ordinary"]
        if specific:
            return specific[0]
        return declared[0]
    return None


def build_consensus(
    universe: list[str],
    *,
    yonepse: dict[str, dict[str, Any]] | None = None,
    stockmap: dict[str, dict[str, Any]] | None = None,
    binayabaral: dict[str, dict[str, Any]] | None = None,
    nepalstockdata: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve one sector/instrument classification per symbol.

    Issuer-sector votes come only from the three issuer-sector sources; the
    instrument-bucket source supplies instrument classification (and a business
    sector only for symbols it files under a business column).
    """
    yonepse = yonepse or {}
    stockmap = stockmap or {}
    binayabaral = binayabaral or {}
    nepalstockdata = nepalstockdata or {}
    # sources passed to classify_instrument
    instrument_sources = {"yonepse": yonepse, "binayabaral": binayabaral, "nsd": nepalstockdata}

    resolved: dict[str, dict[str, Any]] = {}
    conflicted: list[dict[str, Any]] = []
    unresolved: list[str] = []

    for symbol in sorted({s.upper() for s in universe}):
        votes: dict[str, str] = {}
        for name, src in (
            ("yonepse", yonepse),
            ("stockmap", stockmap),
            ("binayabaral", binayabaral),
        ):
            sector = src.get(symbol, {}).get("sector")
            if sector:
                votes[name] = sector
        # The instrument-bucket source's column is a business sector only when
        # it did NOT place the symbol in an instrument bucket.
        nsd = nepalstockdata.get(symbol)
        if nsd and nsd.get("sector") and nsd["sector"] not in INSTRUMENT_BUCKETS:
            votes["nepalstockdata"] = nsd["sector"]

        instrument = classify_instrument(symbol, instrument_sources)
        company_name = (
            (yonepse.get(symbol, {}).get("company_name"))
            or (stockmap.get(symbol, {}).get("company_name"))
            or (binayabaral.get(symbol, {}).get("company_name"))
        )

        distinct = sorted(set(votes.values()))
        if instrument and instrument != "ordinary":
            # Non-ordinary instrument: classified by instrument, never by an
            # ordinary company sector.
            bucket = {
                "mutual_fund": "Mutual Funds",
                "debenture": "Corporate Debentures",
                "convertible_debenture": "Corporate Debentures",
                "government_bond": "Government Bonds",
                "promoter_share": "Promoter Shares",
                "preference": "Preference Shares",
            }.get(instrument, instrument.replace("_", " ").title())
            resolved[symbol] = {
                "symbol": symbol,
                "sector": None,
                "instrument": instrument,
                "classification": bucket,
                "is_ordinary": False,
                "basis": "instrument, not an ordinary-company sector",
                "votes": votes,
                "company_name": company_name,
            }
            continue

        if not distinct:
            unresolved.append(symbol)
            continue
        if len(distinct) > 1:
            conflicted.append(
                {
                    "symbol": symbol,
                    "company_name": company_name,
                    "votes": votes,
                    "candidates": distinct,
                }
            )
            continue

        resolved[symbol] = {
            "symbol": symbol,
            "sector": distinct[0],
            "instrument": instrument or "ordinary",
            "classification": distinct[0],
            "is_ordinary": True,
            "basis": f"unanimous across {len(votes)} issuer-sector source(s)",
            "votes": votes,
            "company_name": company_name,
        }

    return {
        "universe_size": len({s.upper() for s in universe}),
        "resolved": resolved,
        "conflicted": conflicted,
        "unresolved": unresolved,
        "stats": {
            "resolved": len(resolved),
            "resolved_ordinary": sum(1 for r in resolved.values() if r["is_ordinary"]),
            "resolved_instrument": sum(1 for r in resolved.values() if not r["is_ordinary"]),
            "conflicted": len(conflicted),
            "unresolved": len(unresolved),
            "unanimous_ordinary": sum(
                1 for r in resolved.values() if r["is_ordinary"] and len(r["votes"]) >= 2
            ),
        },
    }


def sector_map_for_ranker(consensus: dict[str, Any]) -> dict[str, str]:
    """``symbol -> sector`` restricted to ordinary shares.

    Excludes instrument classifications, because a debenture or promoter share
    must not be ranked against ordinary companies in the same sector.
    """
    return {
        sym: rec["sector"]
        for sym, rec in consensus["resolved"].items()
        if rec["is_ordinary"] and rec["sector"]
    }


def ordinary_only_sector_map(meta: dict[str, dict[str, Any]]) -> dict[str, str]:
    """``symbol -> sector`` from stored metadata, ordinary shares only.

    This is the rule the ranking API applies. Verified against the real
    compilations: every mutual fund and every debenture carries its issuer's
    business sector, so a map built from raw sector values ranks a bank's bond
    and a bank's mutual fund against that bank's ordinary shares. A sector
    percentile describes a peer group, not an instrument list.

    A symbol with no recorded instrument type is excluded too: without knowing
    it is ordinary it cannot be placed in an ordinary-share peer group, and
    guessing is exactly what this filter exists to prevent.
    """
    return {
        symbol: m["sector"]
        for symbol, m in meta.items()
        if m.get("sector") and str(m.get("instrument_type") or "").strip().lower() == "ordinary"
    }


def non_ordinary_with_sector(meta: dict[str, dict[str, Any]]) -> dict[str, str]:
    """The symbols a raw sector map would have wrongly included."""
    return {
        symbol: str(m.get("instrument_type") or "").strip().lower() or "unspecified"
        for symbol, m in meta.items()
        if m.get("sector") and str(m.get("instrument_type") or "").strip().lower() != "ordinary"
    }
