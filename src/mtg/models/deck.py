"""Decklist models. A decklist is cards plus quantities, not printings."""

from pydantic import BaseModel


class DeckEntry(BaseModel):
    oracle_id: str
    name: str                    # display only; never used for lookup
    quantity: int
    is_commander: bool = False


class Deck(BaseModel):
    name: str                    # vault filename, e.g. "Aesi Lands"
    format: str
    strategy: str | None = None  # Taxonomy closed list
    archetype: str | None = None # Taxonomy open list
    colors: list[str] = []       # WUBRG order
    bracket: int | None = None
    entries: list[DeckEntry] = []
