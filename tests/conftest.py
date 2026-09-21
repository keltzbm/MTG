"""An in-memory Catalog so the logic is testable without DuckDB or a download."""

import pytest

from mtg.models import CardRules, Prices, Printing

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
    "o-bolt": ("Lightning Bolt", "normal", 1.0, 0.02),
    "o-rats": ("Relentless Rats", "normal", 0.2, 0.01),
    "o-crypt": ("Mana Crypt", "normal", 150.0, 20.0),
}

_CMDR = {"commander": "legal", "duel": "legal"}
RULES = {
    # oracle_id: (legalities, color_identity, type_line, oracle_text)
    "o-sol": ({**_CMDR, "modern": "not_legal", "legacy": "banned", "vintage": "restricted"},
              (), "Artifact", "{T}: Add {C}{C}."),
    "o-rift": ({**_CMDR, "modern": "not_legal", "legacy": "legal"}, ("U",), "Instant", "Overload {6}{U}"),
    "o-forest": ({**_CMDR, "modern": "legal"}, ("G",), "Basic Land — Forest", "({T}: Add {G}.)"),
    "o-snowf": ({**_CMDR, "modern": "legal"}, ("G",), "Basic Snow Land — Forest", "({T}: Add {G}.)"),
    "o-aesi": ({**_CMDR, "modern": "legal"}, ("U", "G"), "Legendary Creature — Serpent",
               "You may play an additional land on each of your turns."),
    "o-fire": ({**_CMDR, "modern": "legal"}, ("U", "R"), "Instant // Instant", "Fire\nIce"),
    "o-bolt": ({**_CMDR, "modern": "legal", "pioneer": "not_legal"}, ("R",), "Instant",
               "Lightning Bolt deals 3 damage to any target."),
    "o-rats": ({**_CMDR, "modern": "legal"}, ("B",), "Creature — Rat",
               "A deck can have any number of cards named Relentless Rats."),
    "o-crypt": ({"commander": "banned", "duel": "banned", "modern": "not_legal", "vintage": "restricted"},
                (), "Artifact", "At the beginning of your upkeep, flip a coin."),
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

    def arena_rarity(self, oid):
        return {"o-sol": "uncommon", "o-rift": "mythic", "o-aesi": "rare"}.get(oid)

    def is_basic(self, oid):
        return CARDS[oid][0] in {"Forest", "Island", "Plains", "Swamp", "Mountain", "Wastes"}

    def rules(self, oid):
        r = RULES.get(oid)
        return CardRules(*r) if r else None


@pytest.fixture
def cat():
    return FakeCatalog()
