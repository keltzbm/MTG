from collections import Counter

from mtg.analysis.ownership import BUY, OWN, PRECON, diff, summary
from mtg.analysis.resolve import counts, resolve_deck, resolve_holdings
from mtg.ingest.decklist import parse_text
from mtg.models import Holding


def test_precon_contents_count_as_owned(cat):
    """30 cards in a sealed precon must not read as 'need to buy'."""
    deck = parse_text("1 Sol Ring\n1 Cyclonic Rift\n1 Aesi, Tyrant of Gyre Strait\n")
    resolve_deck(deck, cat)
    rows = {r.name: r.status for r in diff(deck, Counter({"o-sol": 1}), Counter({"o-rift": 1}), cat)}
    assert rows == {"Sol Ring": OWN, "Cyclonic Rift": PRECON, "Aesi, Tyrant of Gyre Strait": BUY}


def test_name_is_not_a_key_holdings_resolve_by_printing_first(cat):
    """A ManaBox row with a wrong or odd name still counts via its Scryfall ID."""
    hs = [Holding("Sol Ring (Retro)", 1, scryfall_id="s-sol-m3c"),
          Holding("whatever", 1, set_code="2X2", collector_number="45")]
    assert resolve_holdings(hs, cat) == []
    assert counts(hs) == Counter({"o-sol": 1, "o-rift": 1})


def test_plain_basics_always_owned_snow_basics_are_not(cat):
    deck = parse_text("5 Forest\n2 Snow-Covered Forest\n")
    resolve_deck(deck, cat)
    rows = {r.name: (r.status, r.shortfall) for r in diff(deck, Counter(), Counter(), cat)}
    assert rows == {"Forest": (OWN, 0), "Snow-Covered Forest": (BUY, 2)}


def test_partial_ownership_reports_shortfall(cat):
    deck = parse_text("3 Snow-Covered Forest\n")
    resolve_deck(deck, cat)
    (row,) = diff(deck, Counter({"o-snowf": 1}), Counter(), cat)
    assert (row.status, row.shortfall) == (BUY, 2)
    assert summary([row]) == {"own": 0, "precon": 0, "buy": 1}


def test_unmatched_names_are_reported_not_dropped(cat):
    deck = parse_text("1 Sol Rnig\n")
    assert resolve_deck(deck, cat) == ["Sol Rnig"]
