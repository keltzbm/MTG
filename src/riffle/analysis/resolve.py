"""Names -> card ids, once, at the edge. Unresolved names are reported,
never silently dropped."""

from collections import Counter

from riffle.models import Deck, Holding
from riffle.store import Catalog


def resolve_deck(deck: Deck, catalog: Catalog) -> list[str]:
    missing = []
    for e in deck.entries:
        e.card_id = catalog.resolve(e.name)
        if e.card_id is None:
            missing.append(e.name)
    return missing


def resolve_holdings(holdings: list[Holding], catalog: Catalog) -> list[str]:
    """Each row by its Scryfall ID, else its set and collector number, else its name."""
    by_id = catalog.printings({h.scryfall_id for h in holdings if h.scryfall_id})
    places = {
        (h.set_code, h.collector_number)
        for h in holdings
        if h.scryfall_id not in by_id and h.set_code and h.collector_number
    }
    by_place = catalog.printings_at(places)
    missing = []
    for h in holdings:
        p = by_id.get(h.scryfall_id or "") or by_place.get((h.set_code or "", h.collector_number or ""))
        h.card_id = p.card_id if p else catalog.resolve(h.name)
        if h.card_id is None:
            missing.append(h.name)
    return missing


def counts(holdings: list[Holding]) -> Counter:
    c: Counter = Counter()
    for h in holdings:
        if h.card_id:
            c[h.card_id] += h.quantity
    return c
