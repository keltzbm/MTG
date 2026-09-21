import json
from datetime import date

from mtg.analysis import metagame
from mtg.ingest import mtgo
from mtg.ingest.decklist import parse_text

INDEX = """
<a href="/decklist/modern-challenge-32-2026-09-1912850001">Modern Challenge 32</a>
<a href="https://www.mtgo.com/decklist/modern-league-2026-09-2012850002">Modern League</a>
<a href="/decklist/pioneer-league-2026-09-2012850003">Pioneer League</a>
<a href="/decklist/modern-showcase-challenge-2026-08-3112840000">last month</a>
<a href="/decklist/modern-league-2026-09-2012850002">duplicate link</a>
<a href="/decklists/2026/08">not an event</a>
"""


def _row(name, qty, side=False):
    return {"qty": str(qty), "sideboard": "true" if side else "false", "card_attributes": {"card_name": name}}


def _page(data):
    return f"<html><script>window.MTGO.decklists.data = {json.dumps(data)};\nother();</script></html>"


CHALLENGE = {
    "decklists": [
        {"player": "bob", "loginid": "2",
         "main_deck": [_row("Lightning Bolt", 3), _row("Lightning Bolt", 1), _row("Mountain", 56)],
         "sideboard_deck": [_row("Fire/Ice", 2, side=True)]},
        {"player": "alice", "loginid": "1",
         "main_deck": [_row("Thoughtseize", 4), _row("Swamp", 56)],
         "sideboard_deck": [_row("Lightning Bolt", 1, side=True)]},
    ],
    "standings": [{"loginid": "1", "login_name": "alice", "rank": 1},
                  {"loginid": "2", "login_name": "bob", "rank": 7}],
}
LEAGUE = {"decklists": [{"player": "carol", "main_deck": [_row("Thoughtseize", 2)], "sideboard_deck": []}]}


def test_slugs_and_classification():
    assert mtgo.parse_slug("modern-challenge-32-2026-04-1812839681") == \
        ("modern-challenge-32", "2026-04-18", "12839681")
    assert mtgo.parse_slug("decklists") is None
    assert mtgo.classify("modern-showcase-challenge") == "showcase"
    assert mtgo.classify("modern-league") == "league"
    assert mtgo.classify("modern-super-qualifier") == "qualifier"
    assert mtgo.event_format("modern-showcase-challenge") == "modern"
    assert mtgo.event_format("duel-commander-league") == "duel-commander"


def test_index_links_are_deduplicated():
    assert mtgo.event_slugs(INDEX) == [
        "modern-challenge-32-2026-09-1912850001",
        "modern-league-2026-09-2012850002",
        "pioneer-league-2026-09-2012850003",
        "modern-showcase-challenge-2026-08-3112840000",
    ]


def test_parse_event_merges_printings_and_ranks():
    e = mtgo.parse_event("modern-challenge-32-2026-09-1912850001", mtgo.extract_data(_page(CHALLENGE)))
    assert (e.format, e.kind, e.date, e.event_id) == ("modern", "challenge", "2026-09-19", "12850001")
    assert [d.player for d in e.decks] == ["alice", "bob"]          # sorted by rank
    bob = e.decks[1]
    assert bob.rank == 7 and bob.record is None
    assert [(c.name, c.qty) for c in bob.main] == [("Lightning Bolt", 4), ("Mountain", 56)]
    assert [(c.name, c.qty) for c in bob.side] == [("Fire/Ice", 2)]


def test_league_record_and_text_roundtrip():
    e = mtgo.parse_event("modern-league-2026-09-2012850002", LEAGUE)
    assert e.decks[0].record == "5-0"
    deck = parse_text(e.decks[0].to_text())
    assert [(x.name, x.quantity, x.board) for x in deck.entries] == [("Thoughtseize", 2, "main")]
    bob = mtgo.parse_event("modern-challenge-32-2026-09-1912850001", CHALLENGE).decks[1]
    boards = {(x.name, x.board) for x in parse_text(bob.to_text()).entries}
    assert ("Fire/Ice", "sideboard") in boards


def test_missing_data_is_an_error():
    try:
        mtgo.extract_data("<html>no script</html>")
    except ValueError as e:
        assert "layout may have changed" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_ingest_filters_skips_and_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    pages = {
        "https://www.mtgo.com/decklists/2026/09": INDEX,
        "https://www.mtgo.com/decklist/modern-challenge-32-2026-09-1912850001": _page(CHALLENGE),
        "https://www.mtgo.com/decklist/modern-league-2026-09-2012850002": "<html>broken</html>",
    }
    calls = []

    def get(url):
        calls.append(url)
        return pages[url]

    res = mtgo.ingest("modern", since=date(2026, 9, 1), until=date(2026, 9, 21), delay=0, get=get)
    assert [e.slug for e in res.fetched] == ["modern-challenge-32-2026-09-1912850001"]
    assert res.pending == ["modern-league-2026-09-2012850002"]   # page up, no data yet
    assert not any("pioneer" in u or "2026-08-31" in u for u in calls)   # format and date filters

    again = mtgo.ingest("modern", since=date(2026, 9, 1), until=date(2026, 9, 21), delay=0,
                        get=get, kinds=["challenge"])
    assert again.skipped == 1 and not again.fetched

    stored = mtgo.load(fmt="modern", since=date(2026, 9, 1))
    assert [e.slug for e in stored] == ["modern-challenge-32-2026-09-1912850001"]
    assert stored[0].decks[0].main[0].name == "Thoughtseize"


def test_card_stats_and_find():
    e1 = mtgo.parse_event("modern-challenge-32-2026-09-1912850001", CHALLENGE)
    e2 = mtgo.parse_event("modern-league-2026-09-2012850002", LEAGUE)
    stats = {s.name: s for s in metagame.card_stats([e1, e2])}
    bolt = stats["Lightning Bolt"]
    assert (bolt.decks, bolt.main_decks, bolt.side_decks, bolt.copies) == (2, 1, 1, 5)
    assert stats["Thoughtseize"].decks == 2 and stats["Thoughtseize"].avg == 3.0
    assert "Fire/Ice" not in {s.name for s in metagame.card_stats([e1], board="main")}
    assert [d.player for _, d in metagame.find_decks([e1, e2], card="thoughtseize")] == ["alice", "carol"]
    assert [d.player for _, d in metagame.find_decks([e1, e2], player="BOB")] == ["bob"]


def test_unreachable_index_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    def get(url):
        raise mtgo.FetchError("timed out")

    res = mtgo.ingest("modern", since=date(2026, 9, 1), until=date(2026, 9, 21), delay=0, get=get)
    assert not res.fetched
    assert res.failed == [("https://www.mtgo.com/decklists/2026/09", "timed out")]


EMPTY = {"decklists": []}


def test_empty_events_are_pending_then_fetched(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    slug = "modern-challenge-32-2026-09-1912850001"
    url = f"https://www.mtgo.com/decklist/{slug}"
    pages = {"https://www.mtgo.com/decklists/2026/09": f'<a href="/decklist/{slug}">x</a>', url: _page(EMPTY)}
    kw = dict(since=date(2026, 9, 1), until=date(2026, 9, 21), delay=0, get=pages.__getitem__)

    first = mtgo.ingest("modern", **kw)
    assert first.pending == [slug] and not first.fetched and not mtgo.is_stored(slug)

    pages[url] = "<html>not rendered yet</html>"          # no data object at all: also pending
    assert mtgo.ingest("modern", **kw).pending == [slug]

    pages[url] = _page(CHALLENGE)                         # published: now it's fetched
    assert [e.slug for e in mtgo.ingest("modern", **kw).fetched] == [slug]
    assert mtgo.ingest("modern", **kw).skipped == 1


def test_old_empty_files_are_refetched_and_hidden(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    slug = "modern-league-2026-09-2012850002"
    mtgo.save(mtgo.parse_event(slug, EMPTY))              # what the first version wrote
    assert not mtgo.is_stored(slug)
    assert mtgo.load("modern") == []


def test_all_formats(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    pages = {"https://www.mtgo.com/decklists/2026/09": INDEX}
    for slug in mtgo.event_slugs(INDEX):
        pages[f"https://www.mtgo.com/decklist/{slug}"] = _page(CHALLENGE)
    kw = dict(since=date(2026, 9, 1), until=date(2026, 9, 21), delay=0, get=pages.__getitem__)
    got = mtgo.ingest(None, **kw)
    assert {e.format for e in got.fetched} == {"modern", "pioneer"}
    assert {e.format for e in mtgo.load(["pioneer"])} == {"pioneer"}


def test_fingerprint_groups_identical_lists_only():
    e = mtgo.parse_event("modern-challenge-32-2026-09-1912850001", CHALLENGE)
    alice, bob = e.decks
    same = mtgo.MtgoDeck("zed", list(reversed(bob.main)), bob.side)
    assert same.fingerprint == bob.fingerprint              # order and pilot don't matter
    assert alice.fingerprint != bob.fingerprint
    moved = mtgo.MtgoDeck("zed", bob.main, [mtgo.Card("Fire/Ice", 1)])
    assert moved.fingerprint != bob.fingerprint             # sideboard counts
