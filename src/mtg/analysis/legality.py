"""Format legality and playset eligibility.

Playset rule: buy 4 only if the card is legal AND playable in a format being
built (Modern, Legacy, Pioneer, Pauper). Commander-only cards stay at one copy
and rotate between decks.
"""

BUILT_FORMATS = ("modern", "legacy", "pioneer", "pauper")


def is_legal(oracle_id: str, fmt: str, con) -> bool:
    raise NotImplementedError


def playset_eligible(oracle_id: str, con) -> bool:
    """Legal in at least one actively built constructed format."""
    raise NotImplementedError
