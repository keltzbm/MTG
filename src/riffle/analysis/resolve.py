"""Names -> oracle ids, once, at the edge. Unresolved names are reported,
never silently dropped."""

from collections import Counter

from riffle.models import Deck, Holding
from riffle.store import Catalog


def resolve_deck(deck: Deck, catalog: Catalog) -> list[str]:
    missing = []
    for e in deck.entries:
        e.oracle_id = catalog.resolve(e.name)
        if e.oracle_id is None:
            missing.append(e.name)
    return missing


def resolve_holdings(holdings: list[Holding], catalog: Catalog) -> list[str]:
    missing = []
    for h in holdings:
        oid = None
        if h.scryfall_id:
            p = catalog.printing(h.scryfall_id)
            oid = p.oracle_id if p else None
        if oid is None and h.set_code and h.collector_number:
            p = catalog.printing_at(h.set_code, h.collector_number)
            oid = p.oracle_id if p else None
        if oid is None:
            oid = catalog.resolve(h.name)
        h.oracle_id = oid
        if oid is None:
            missing.append(h.name)
    return missing


def counts(holdings: list[Holding]) -> Counter:
    c: Counter = Counter()
    for h in holdings:
        if h.oracle_id:
            c[h.oracle_id] += h.quantity
    return c
