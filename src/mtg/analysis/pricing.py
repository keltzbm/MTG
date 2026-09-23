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
        return round(sum((line.usd or 0) * line.needed for line in self.lines), 2)

    @property
    def usd_to_buy(self) -> float:
        return round(sum((line.usd or 0) * line.to_buy for line in self.lines), 2)

    @property
    def tix_total(self) -> float:
        return round(sum((line.tix or 0) * line.needed for line in self.lines), 2)

    @property
    def missing_on_mtgo(self) -> list[str]:
        return [line.name for line in self.lines if line.tix is None]

    @property
    def unpriced(self) -> list[str]:
        return [line.name for line in self.lines if line.usd is None and line.to_buy]


def price(rows: list[Row], catalog: Catalog) -> DeckPrice:
    lines = []
    for row in rows:
        p = catalog.prices(row.oracle_id)
        lines.append(Line(row.name, row.needed, row.shortfall, p.usd, p.tix))
    return DeckPrice(lines)
