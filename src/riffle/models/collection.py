from dataclasses import dataclass


@dataclass
class Holding:
    """One row of owned cards: a printing and how many."""

    name: str
    quantity: int
    scryfall_id: str | None = None
    set_code: str | None = None
    collector_number: str | None = None
    foil: bool = False
    source: str = "manabox"  # manabox | arena
    card_id: str | None = None
