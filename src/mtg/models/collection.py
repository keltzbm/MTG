"""What is physically owned, and where it currently lives."""

from pydantic import BaseModel


class CollectionEntry(BaseModel):
    scryfall_id: str
    oracle_id: str
    quantity: int
    foil: bool = False
    source: str = "manabox"      # manabox | precon | manual
    located_in: str | None = None  # deck name, or None for the binder
