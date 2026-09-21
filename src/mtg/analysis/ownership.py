"""Have / need. Milestone 1 — the thing needed twice before it existed."""

from collections import Counter
from dataclasses import dataclass

from mtg.models import Deck
from mtg.store import Catalog

OWN, PRECON, BUY = "own", "precon", "buy"
MARK = {OWN: "🟩", PRECON: "🟦", BUY: "🟥"}


@dataclass
class Row:
    oracle_id: str
    name: str
    needed: int
    owned: int
    in_precon: int

    @property
    def status(self) -> str:
        if self.owned >= self.needed:
            return OWN
        if self.owned + self.in_precon >= self.needed:
            return PRECON
        return BUY

    @property
    def shortfall(self) -> int:
        return max(0, self.needed - self.owned - self.in_precon)


def diff(deck: Deck, owned: Counter, precon: Counter, catalog: Catalog) -> list[Row]:
    """Assumes resolve_deck() has run. Plain basics always count as owned."""
    needed: Counter = Counter()
    for e in deck.entries:
        if e.oracle_id:
            needed[e.oracle_id] += e.quantity
    rows = []
    for oid, n in needed.items():
        have = n if catalog.is_basic(oid) else owned.get(oid, 0)
        rows.append(Row(oid, catalog.name(oid), n, have, precon.get(oid, 0)))
    return sorted(rows, key=lambda r: ({BUY: 0, PRECON: 1, OWN: 2}[r.status], r.name))


def summary(rows: list[Row]) -> dict[str, int]:
    out = {OWN: 0, PRECON: 0, BUY: 0}
    for r in rows:
        out[r.status] += 1
    return out


RARITIES = ("mythic", "rare", "uncommon", "common")


def wildcards(rows: list[Row], catalog: Catalog) -> dict[str, int]:
    """Arena wildcards needed for the shortfall, by rarity; "not on Arena" for the rest."""
    out = {r: 0 for r in RARITIES} | {"not on Arena": 0}
    for r in rows:
        if r.status == BUY:
            out[catalog.arena_rarity(r.oracle_id) or "not on Arena"] += r.shortfall
    return out
