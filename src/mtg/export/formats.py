"""Decklists other apps import.

    moxfield   Commander / Deck sections, "1 Name (SET) 123" when pinned
    manabox    one card per line, "1 Name (SET) 123" when pinned
    mtgo       .txt: main deck, blank line, sideboard — the commander goes
               in the sideboard, which is how MTGO reads Commander lists
    tcgplayer  mass entry for what's missing: only cards you still need

Pinning (pin="owned") writes the set and collector number of a printing you
actually own, so an import stops picking arbitrary printings. Cards you
don't own stay unpinned.
"""

from mtg.analysis.ownership import BUY, Row
from mtg.models import Deck, DeckEntry, Holding
from mtg.store import Catalog

FORMATS = ("moxfield", "manabox", "mtgo", "tcgplayer")


def owned_printings(holdings: list[Holding]) -> dict[str, Holding]:
    """oracle_id -> the owned printing to pin: most copies, then non-foil."""
    best: dict[str, Holding] = {}
    for h in holdings:
        if not (h.oracle_id and h.set_code and h.collector_number) or h.source != "manabox":
            continue
        cur = best.get(h.oracle_id)
        if cur is None or (h.quantity, not h.foil) > (cur.quantity, not cur.foil):
            best[h.oracle_id] = h
    return best


def _line(e: DeckEntry, name: str, pins: dict[str, Holding]) -> str:
    h = pins.get(e.oracle_id or "")
    if h:
        return f"{e.quantity} {name} ({h.set_code}) {h.collector_number}"
    if e.set_code and e.collector_number:
        return f"{e.quantity} {name} ({e.set_code}) {e.collector_number}"
    return f"{e.quantity} {name}"


def _name(e: DeckEntry, catalog: Catalog | None) -> str:
    return catalog.name(e.oracle_id) if (catalog and e.oracle_id) else e.name


def moxfield(deck: Deck, catalog: Catalog | None = None, pins: dict | None = None) -> str:
    pins = pins or {}
    out = []
    for board, header in (("commander", "Commander"), ("companion", "Companion"),
                          ("main", "Deck"), ("sideboard", "Sideboard")):
        cards = deck.board(board)
        if cards:
            out += [header] + [_line(e, _name(e, catalog), pins) for e in cards] + [""]
    return "\n".join(out).rstrip() + "\n"


def manabox(deck: Deck, catalog: Catalog | None = None, pins: dict | None = None) -> str:
    pins = pins or {}
    ordered = deck.board("commander") + deck.board("companion") + deck.board("main") + deck.board("sideboard")
    return "\n".join(_line(e, _name(e, catalog), pins) for e in ordered) + "\n"


def mtgo(deck: Deck, catalog: Catalog | None = None, pins: dict | None = None) -> str:
    def nm(e: DeckEntry) -> str:
        return catalog.mtgo_name(e.oracle_id) if (catalog and e.oracle_id) else e.name.split(" // ")[0]

    main = [f"{e.quantity} {nm(e)}" for e in deck.board("main")]
    side = [f"{e.quantity} {nm(e)}" for e in deck.board("commander") + deck.board("companion") + deck.board("sideboard")]
    return "\n".join(main + ([""] + side if side else [])) + "\n"


def tcgplayer(rows: list[Row]) -> str:
    return "\n".join(f"{r.shortfall} {r.name}" for r in rows if r.status == BUY) + "\n"


def render(fmt: str, deck: Deck, rows: list[Row], catalog: Catalog | None, pins: dict | None) -> str:
    if fmt == "tcgplayer":
        return tcgplayer(rows)
    return {"moxfield": moxfield, "manabox": manabox, "mtgo": mtgo}[fmt](deck, catalog, pins)
