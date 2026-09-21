"""Card and Printing.

A Card is an oracle identity: one rules text, one set of legalities, one color
identity. A Printing is a physical object: set, collector number, finish,
price, border. Ownership attaches to printings; decklists attach to cards.
"""

from pydantic import BaseModel


class Printing(BaseModel):
    scryfall_id: str
    oracle_id: str
    set_code: str
    collector_number: str
    border_color: str            # black | white | borderless | silver | gold
    frame: str                   # 1993 | 1997 | 2003 | 2015 | future
    finishes: list[str]          # nonfoil | foil | etched
    usd: float | None = None
    usd_foil: float | None = None

    @property
    def is_old_border(self) -> bool:
        """Pre-modern frame. Preferred printing for constant-use singles."""
        return self.frame in {"1993", "1997"}


class Card(BaseModel):
    oracle_id: str               # the key. Never match on name.
    name: str
    mana_cost: str | None
    mana_value: float
    type_line: str
    oracle_text: str | None
    colors: list[str]            # WUBRG order
    color_identity: list[str]    # WUBRG order
    legalities: dict[str, str]
    printings: list[Printing] = []
