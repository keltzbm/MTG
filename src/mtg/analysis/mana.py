"""Mana base checks.

Ported idea from the old getDeckColors: separate the colors the spells *demand*
from the colors the lands *supply*, and compare. A deck can be "three colors"
and still be unable to cast its commander on curve.
"""

from mtg.models import Deck


def color_demand(deck: Deck, con) -> dict[str, int]:
    """Pips required, weighted by mana value, in WUBRG order."""
    raise NotImplementedError


def color_supply(deck: Deck, con) -> dict[str, int]:
    """Sources producing each color, in WUBRG order."""
    raise NotImplementedError


def curve(deck: Deck, con) -> dict[int, int]:
    raise NotImplementedError


def land_count(deck: Deck, con) -> int:
    raise NotImplementedError
