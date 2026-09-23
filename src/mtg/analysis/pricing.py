"""Paper and MTGO prices for a deck: cheapest printing of each card.

USD is paper nonfoil. Tix is MTGO; Scryfall takes it from Cardhoarder, so
it's roughly what a Cardhoarder rental or purchase costs. MTGO totals use
the whole list — a digital collection doesn't share your paper cards.
"""

from dataclasses import dataclass

from mtg.analysis.ownership import Row
from mtg.store import Catalog


@dataclass
class Line:
    name: str
    needed: int
    to_buy: int
    usd: float | None
    tix: float | None


@dataclass
class DeckPrice:
    lines: list[Line]

    @property
    def usd_total(self) -> float:
        return round(sum((l.usd or 0) * l.needed for l in self.lines), 2)

    @property
    def usd_to_buy(self) -> float:
        return round(sum((l.usd or 0) * l.to_buy for l in self.lines), 2)

    @property
    def tix_total(self) -> float:
        return round(sum((l.tix or 0) * l.needed for l in self.lines), 2)

    @property
    def missing_on_mtgo(self) -> list[str]:
        return [l.name for l in self.lines if l.tix is None]

    @property
    def unpriced(self) -> list[str]:
        return [l.name for l in self.lines if l.usd is None and l.to_buy]


def price(rows: list[Row], catalog: Catalog) -> DeckPrice:
    return DeckPrice(
        [
            Line(r.name, r.needed, r.shortfall, *(lambda p: (p.usd, p.tix))(catalog.prices(r.oracle_id)))
            for r in rows
        ]
    )
