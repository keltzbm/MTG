"""A Printing is a physical (or digital) object; many share one oracle_id."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Printing:
    scryfall_id: str
    oracle_id: str
    name: str
    set_code: str
    collector_number: str
    frame: str = ""
    border_color: str = ""

    @property
    def is_old_border(self) -> bool:
        return self.frame in {"1993", "1997"}


@dataclass(frozen=True)
class Prices:
    """Cheapest across all printings of one card."""

    usd: float | None = None   # paper, nonfoil
    tix: float | None = None   # MTGO, via Scryfall (Cardhoarder)
