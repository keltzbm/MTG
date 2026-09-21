"""Have / need diff. Milestone 1 — the thing needed twice already.

Counts every source of ownership (ManaBox rows, precon contents, manual adds),
respects the one-copy-rotated-between-decks rule by reporting where a card
currently lives, and never matches on name.
"""

from dataclasses import dataclass

from mtg.models import Deck


@dataclass
class OwnershipRow:
    oracle_id: str
    name: str
    needed: int
    owned: int
    in_precon: int
    located_in: str | None

    @property
    def shortfall(self) -> int:
        return max(0, self.needed - self.owned - self.in_precon)

    @property
    def conflict(self) -> bool:
        """Owned, but currently sleeved in a different deck."""
        return self.located_in is not None and self.shortfall == 0


def diff(deck: Deck, con) -> list[OwnershipRow]:
    raise NotImplementedError
