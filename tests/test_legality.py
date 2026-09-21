from mtg.analysis import legality
from mtg.ingest.decklist import parse_text


def _deck(text, fmt):
    d = parse_text(text, slug="t")
    d.meta["format"] = fmt
    return d


def _modern(extra=""):
    return _deck(f"Deck\n4 Lightning Bolt\n56 Forest\n{extra}", "modern")


def _messages(rep):
    return [(i.severity, i.card, i.message) for i in rep.issues]


def test_card_status_and_copy_limits(cat):
    assert legality.is_legal("o-bolt", "modern", cat)
    assert not legality.is_legal("o-bolt", "pioneer", cat)
    assert legality.is_legal("o-sol", "vintage", cat)               # restricted still counts as legal
    assert legality.copy_limit("o-sol", "vintage", cat) == 1
    assert legality.copy_limit("o-bolt", "modern", cat) == 4
    assert legality.copy_limit("o-bolt", "commander", cat) == 1
    assert legality.copy_limit("o-snowf", "commander", cat) is None  # snow basics are basics
    assert legality.copy_limit("o-rats", "commander", cat) is None   # "any number of cards named"


def test_playset_eligibility(cat):
    assert legality.playset_eligible("o-bolt", cat)
    assert legality.target_copies("o-bolt", cat) == 4
    assert not legality.playset_eligible("o-crypt", cat)    # vintage isn't a built format
    assert legality.target_copies("o-sol", cat) == 1


def test_format_aliases():
    assert legality.normalize_format("EDH") == "commander"
    assert legality.normalize_format("Pauper Commander") == "paupercommander"
    assert legality.normalize_format("duel-commander") == "duel"


def test_legal_modern_deck(cat):
    rep = legality.check_deck(_modern("\nSideboard\n3 Relentless Rats"), cat)
    assert rep.legal, _messages(rep)


def test_modern_errors(cat):
    rep = legality.check_deck(_deck("Deck\n5 Lightning Bolt\n1 Sol Ring\n20 Forest\n", "modern"), cat)
    msgs = _messages(rep)
    assert ("error", "Lightning Bolt", "5 copies — max 4") in msgs
    assert ("error", "Sol Ring", "not legal in modern") in msgs
    assert any("needs at least 60" in m for _, _, m in msgs)


def test_sideboard_copies_count_toward_limit(cat):
    rep = legality.check_deck(_modern("\nSideboard\n1 Lightning Bolt"), cat)
    assert ("error", "Lightning Bolt", "5 copies — max 4") in _messages(rep)


def test_restricted(cat):
    rep = legality.check_deck(_deck("Deck\n2 Mana Crypt\n58 Forest\n", "vintage"), cat)
    assert ("error", "Mana Crypt", "2 copies — restricted") in _messages(rep)


def _commander(body, total_forests):
    return _deck(f"Commander\n1 Aesi, Tyrant of Gyre Strait\n\nDeck\n{body}{total_forests} Forest\n", "commander")


def test_legal_commander_deck(cat):
    rep = legality.check_deck(_commander("1 Cyclonic Rift\n1 Sol Ring\n", 97), cat)
    assert rep.legal, _messages(rep)


def test_commander_errors(cat):
    rep = legality.check_deck(
        _commander("1 Lightning Bolt\n2 Sol Ring\n1 Mana Crypt\n30 Relentless Rats\n", 50), cat)
    msgs = _messages(rep)
    assert ("error", "Lightning Bolt", "outside color identity (R)") in msgs
    assert ("error", "Relentless Rats", "outside color identity (B)") in msgs
    assert ("error", "Sol Ring", "2 copies — max 1") in msgs
    assert ("error", "Mana Crypt", "banned in commander") in msgs
    assert ("error", None, "85 cards — commander decks are exactly 100") in msgs
    assert not any(c == "Relentless Rats" and "copies" in m for _, c, m in msgs)


def test_missing_commander_and_unmatched(cat):
    rep = legality.check_deck(_deck("Deck\n1 Not A Card\n99 Forest\n", "commander"), cat)
    msgs = _messages(rep)
    assert ("error", "Not A Card", "not matched to a card") in msgs
    assert ("error", None, "no commander — add a Commander section") in msgs


def test_unknown_format(cat):
    rep = legality.check_deck(_modern(), cat, fmt="jumpstart-ish")
    assert not rep.legal and "unknown format" in rep.issues[0].message


def test_stale_card_data(cat, monkeypatch):
    monkeypatch.setattr(type(cat), "rules", lambda self, oid: None)
    rep = legality.check_deck(_modern(), cat)
    assert [i.message for i in rep.issues] == [legality.STALE]


def test_one_odd_printing_cannot_hide_a_legal_card():
    from mtg.models import merge_legalities
    normal = {"commander": "legal", "vintage": "restricted", "modern": "not_legal"}
    gold_border = {"commander": "not_legal", "vintage": "not_legal", "modern": "not_legal"}
    assert merge_legalities([gold_border, normal]) == normal
    assert merge_legalities([normal, gold_border]) == normal          # order doesn't matter
    banned = {"commander": "banned"}
    assert merge_legalities([normal, banned])["commander"] == "banned"
    assert merge_legalities([]) == {}
