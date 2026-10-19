"""Company / entity alias registry and resolution (Part 13).

The registry is JSON (stdlib; see docs/ARCHITECTURE.md for the JSON-over-YAML
decision). Each entity has English, Devanagari and romanized aliases,
former names and a ticker. Resolution rules:

- exact ticker match (word-boundary, uppercase) -> confidence 1.0
- exact alias match (case-insensitive, word-boundary) -> 0.9
- ambiguous alias (maps to 2+ entities) -> status "ambiguous", kept for review
- no match -> unresolved; never guessed
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Entity:
    entity_id: str
    official_name: str
    ticker: str | None
    exchange: str = "NEPSE"
    sector: str = "unknown"
    aliases: list[str] = field(default_factory=list)
    nepali_name: str = ""
    devanagari_aliases: list[str] = field(default_factory=list)
    romanized_aliases: list[str] = field(default_factory=list)
    former_names: list[str] = field(default_factory=list)
    verification_status: str = "unverified"


@dataclass
class MatchResult:
    entity_id: str | None
    ticker: str | None
    matched_alias: str
    confidence: float
    status: str  # resolved | ambiguous | unresolved
    candidates: list[str] = field(default_factory=list)


class EntityRegistry:
    """Alias index with multi-entity ambiguity detection."""

    def __init__(self, entities: list[Entity]):
        self.entities = {e.entity_id: e for e in entities}
        self.alias_map: dict[str, list[str]] = {}
        self.ticker_map: dict[str, str] = {}
        for e in entities:
            if e.ticker:
                self.ticker_map[e.ticker.upper()] = e.entity_id
            all_aliases = ([e.official_name] + e.aliases + e.devanagari_aliases
                           + e.romanized_aliases + e.former_names
                           + ([e.nepali_name] if e.nepali_name else []))
            for a in all_aliases:
                a = (a or "").strip()
                if len(a) < 2:
                    continue
                self.alias_map.setdefault(a.casefold(), [])
                if e.entity_id not in self.alias_map[a.casefold()]:
                    self.alias_map[a.casefold()].append(e.entity_id)

    @classmethod
    def load(cls, path: str | Path) -> "EntityRegistry":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([Entity(**row) for row in data["entities"]])

    def _candidate_patterns(self, text: str):
        """Yield (alias, entity_ids) found in text via word-boundary match."""
        low = text.casefold()
        for alias_key, ids in self.alias_map.items():
            if alias_key and alias_key in low:
                # word-boundary check on the original-case alias
                pat = re.compile(r"(?<![\wऀ-ॿ])" + re.escape(alias_key) + r"(?![\wऀ-ॿ])")
                if pat.search(low):
                    yield alias_key, ids

    def resolve(self, text: str) -> list[MatchResult]:
        """Resolve all entity mentions in text. Ambiguous aliases are
        reported with all candidates and never silently resolved."""
        results: list[MatchResult] = []
        seen: set[str] = set()

        # 1) tickers — strongest signal
        for m in re.finditer(r"\b([A-Z]{2,6})\b", text):
            tick = m.group(1)
            if tick in self.ticker_map and self.ticker_map[tick] not in seen:
                eid = self.ticker_map[tick]
                seen.add(eid)
                results.append(MatchResult(eid, tick, tick, 1.0, "resolved"))

        # 2) aliases
        matched_alias_owner: dict[str, str] = {}
        for alias_key, ids in self._candidate_patterns(text):
            if len(ids) > 1:
                results.append(MatchResult(None, None, alias_key, 0.3, "ambiguous",
                                           candidates=ids))
                continue
            eid = ids[0]
            if eid in seen:
                continue
            seen.add(eid)
            matched_alias_owner[alias_key] = eid
            e = self.entities[eid]
            conf = 0.95 if alias_key == e.official_name.casefold() else 0.85
            results.append(MatchResult(eid, e.ticker, alias_key, conf, "resolved"))
        return results

    def sectors(self) -> set[str]:
        return {e.sector for e in self.entities.values()}
