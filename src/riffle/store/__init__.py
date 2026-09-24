"""Card data lookups. Catalog is the interface; DuckCatalog the real one."""

from typing import Protocol

from riffle.models import CardRules, Prices, Printing


class Catalog(Protocol):
    def resolve(self, name: str) -> str | None:
        """Card name (full or front face, any case) -> oracle_id."""

    def name(self, oracle_id: str) -> str: ...

    def prices(self, oracle_id: str) -> Prices: ...

    def printing(self, scryfall_id: str) -> Printing | None: ...

    def printing_at(self, set_code: str, collector_number: str) -> Printing | None: ...

    def printing_usd(self, scryfall_id: str) -> float | None: ...

    def mtgo_name(self, oracle_id: str) -> str: ...

    def arena_rarity(self, oracle_id: str) -> str | None:
        """Lowest rarity the card has on Arena — the wildcard it costs — or None if not on Arena."""

    def is_basic(self, oracle_id: str) -> bool:
        """Plains, Island, Swamp, Mountain, Forest, Wastes. Snow basics are not."""

    def rules(self, oracle_id: str) -> CardRules | None:
        """Legalities, color identity, type line, oracle text — None if the card
        data predates these fields (re-run: riffle ingest scryfall --force)."""
