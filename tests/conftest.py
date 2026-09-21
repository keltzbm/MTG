"""An in-memory Catalog so the logic is testable without DuckDB or a download."""

import pytest

from mtg.models import Prices, Printing

CARDS = {
    # oracle_id: (name, layout, usd, tix)
    "o-sol": ("Sol Ring", "normal", 1.0, 0.05),
    "o-rift": ("Cyclonic Rift", "normal", 30.0, 2.0),
    "o-forest": ("Forest", "normal", 0.1, 0.01),
    "o-snowf": ("Snow-Covered Forest", "normal", 0.5, 0.02),
    "o-aesi": ("Aesi, Tyrant of Gyre Strait", "normal", 5.0, 0.3),
    "o-fire": ("Fire // Ice", "split", 1.0, 0.1),
    "o-rider": ("Murderous Rider // Swift End", "adventure", 2.0, None),
    "o-yshtola": ("Y'shtola, Night's Blessed", "normal", 3.0, None),
}
PRINTINGS = {
    "s-sol-m3c": Printing("s-sol-m3c", "o-sol", "Sol Ring", "m3c", "283"),
    "s-rift-2x2": Printing("s-rift-2x2", "o-rift", "Cyclonic Rift", "2x2", "45"),
}


class FakeCatalog:
    def resolve(self, name):
        key = name.strip().lower()
        for oid, (n, *_ ) in CARDS.items():
            if n.lower() == key or n.lower().split(" // ")[0] == key.split(" // ")[0]:
                return oid
        return None

    def name(self, oid):
        return CARDS[oid][0]

    def prices(self, oid):
        c = CARDS.get(oid)
        return Prices(c[2], c[3]) if c else Prices()

    def printing(self, sid):
        return PRINTINGS.get(sid)

    def printing_at(self, set_code, num):
        for p in PRINTINGS.values():
            if p.set_code == set_code.lower() and p.collector_number == num:
                return p
        return None

    def printing_usd(self, sid):
        return None

    def mtgo_name(self, oid):
        name, layout = CARDS[oid][:2]
        if " // " in name:
            return name.replace(" // ", "/") if layout == "split" else name.split(" // ")[0]
        return name

    def is_basic(self, oid):
        return CARDS[oid][0] in {"Forest", "Island", "Plains", "Swamp", "Mountain", "Wastes"}


@pytest.fixture
def cat():
    return FakeCatalog()
