import json
from datetime import date

import pytest

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
        {
            "player": "bob",
            "loginid": "2",
            "main_deck": [_row("Lightning Bolt", 3), _row("Lightning Bolt", 1), _row("Mountain", 56)],
            "sideboard_deck": [_row("Fire/Ice", 2, side=True)],
        },
        {
            "player": "alice",
            "loginid": "1",
            "main_deck": [_row("Thoughtseize", 4), _row("Swamp", 56)],
            "sideboard_deck": [_row("Lightning Bolt", 1, side=True)],
        },
    ],
    "standings": [
        {"loginid": "1", "login_name": "alice", "rank": 1},
        {"loginid": "2", "login_name": "bob", "rank": 7},
    ],
}
LEAGUE = {"decklists": [{"player": "carol", "main_deck": [_row("Thoughtseize", 2)], "sideboard_deck": []}]}


def test_slugs_and_classification():
    assert mtgo.parse_slug("modern-challenge-32-2026-04-1812839681") == (
        "modern-challenge-32",
        "2026-04-18",
        "12839681",
    )
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
    assert [d.player for d in e.decks] == ["alice", "bob"]  # sorted by rank
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
    assert res.pending == ["modern-league-2026-09-2012850002"]  # page up, no data yet
    assert not any("pioneer" in u or "2026-08-31" in u for u in calls)  # format and date filters

    again = mtgo.ingest(
        "modern", since=date(2026, 9, 1), until=date(2026, 9, 21), delay=0, get=get, kinds=["challenge"]
    )
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

    pages[url] = "<html>not rendered yet</html>"  # no data object at all: also pending
    assert mtgo.ingest("modern", **kw).pending == [slug]

    pages[url] = _page(CHALLENGE)  # published: now it's fetched
    assert [e.slug for e in mtgo.ingest("modern", **kw).fetched] == [slug]
    assert mtgo.ingest("modern", **kw).skipped == 1


def test_old_empty_files_are_refetched_and_hidden(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    slug = "modern-league-2026-09-2012850002"
    mtgo.save(mtgo.parse_event(slug, EMPTY))  # what the first version wrote
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
    assert same.fingerprint == bob.fingerprint  # order and pilot don't matter
    assert alice.fingerprint != bob.fingerprint
    moved = mtgo.MtgoDeck("zed", bob.main, [mtgo.Card("Fire/Ice", 1)])
    assert moved.fingerprint != bob.fingerprint  # sideboard counts


# ---- more parsing edge cases -------------------------------------------------------


@pytest.mark.parametrize(
    "name, fmt, kind",
    [
        ("modern-league", "modern", "league"),
        ("pauper-challenge-32", "pauper", "challenge"),
        ("modern-showcase-qualifier", "modern", "showcase"),
        ("legacy-super-qualifier", "legacy", "qualifier"),
        ("pioneer-preliminary", "pioneer", "preliminary"),
        ("duel-commander-league", "duel-commander", "league"),
        ("vintage-cube-draft", "vintage", "other"),
    ],
)
def test_format_and_kind_table(name, fmt, kind):
    assert (mtgo.event_format(name), mtgo.classify(name)) == (fmt, kind)


@pytest.mark.parametrize(
    "slug",
    [
        "premodern-league-2026-03-3110365",  # league ids are short and look like series ids
        "modern-challenge-64-2026-03-3112837908",
    ],
)
def test_real_slug_shapes_parse(slug):
    name, day, eid = mtgo.parse_slug(slug)
    assert day == "2026-03-31" and eid.isdigit() and not name.endswith("-")


@pytest.mark.parametrize(
    "start, end, months",
    [
        ((2026, 9, 1), (2026, 9, 21), [(2026, 9)]),
        ((2025, 11, 15), (2026, 2, 1), [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]),  # across a year
        ((2026, 9, 30), (2026, 10, 1), [(2026, 9), (2026, 10)]),
    ],
)
def test_months(start, end, months):
    assert mtgo._months(date(*start), date(*end)) == months


def test_main_deck_rows_flagged_sideboard_move_to_side():
    data = {
        "decklists": [
            {
                "player": "x",
                "main_deck": [_row("Bolt", 4), _row("Duress", 2, side=True)],
                "sideboard_deck": [_row("Duress", 1, side=True)],
            }
        ]
    }
    d = mtgo.parse_event("modern-league-2026-09-2012850002", data).decks[0]
    assert [(c.name, c.qty) for c in d.main] == [("Bolt", 4)]
    assert [(c.name, c.qty) for c in d.side] == [("Duress", 3)]


def test_ranks_by_login_name_and_unranked_last():
    data = {
        "decklists": [
            {"player": "Zed", "main_deck": []},
            {"player": "Amy", "main_deck": []},
            {"player": "Bo", "main_deck": []},
        ],
        "standings": [{"login_name": "amy", "rank": 2}, {"login_name": "BO", "rank": "1"}],
    }
    decks = mtgo.parse_event("modern-challenge-32-2026-09-1912850001", data).decks
    assert [(d.player, d.rank) for d in decks] == [("Bo", 1), ("Amy", 2), ("Zed", None)]


def test_rows_without_names_are_skipped_and_quantity_key_accepted():
    data = {"decklists": [{"player": "x", "main_deck": [{"quantity": 3, "card_name": "Bolt"}, {"qty": "2"}]}]}
    d = mtgo.parse_event("modern-league-2026-09-2012850002", data).decks[0]
    assert [(c.name, c.qty) for c in d.main] == [("Bolt", 3)]


def test_explicit_wins_record():
    data = {"decklists": [{"player": "x", "main_deck": [], "wins": {"wins": "4", "losses": "1"}}]}
    assert mtgo.parse_event("modern-challenge-32-2026-09-1912850001", data).decks[0].record == "4-1"


def test_bad_slug_raises():
    with pytest.raises(ValueError, match="not an event slug"):
        mtgo.parse_event("decklists", CHALLENGE)


def test_event_roundtrips_through_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    e = mtgo.parse_event("modern-challenge-32-2026-09-1912850001", CHALLENGE)
    mtgo.save(e)
    [back] = mtgo.load()
    assert back == e


def test_load_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    mtgo.save(mtgo.parse_event("modern-challenge-32-2026-09-1912850001", CHALLENGE))
    mtgo.save(mtgo.parse_event("modern-league-2026-09-2012850002", LEAGUE))
    mtgo.save(mtgo.parse_event("pioneer-league-2026-09-2012850003", LEAGUE))
    assert [e.date for e in mtgo.load("modern")] == ["2026-09-20", "2026-09-19"]  # newest first
    assert [e.kind for e in mtgo.load("modern", kinds=["league"])] == ["league"]
    assert mtgo.load("modern", since=date(2026, 9, 20))[0].kind == "league"
    assert len(mtgo.load(["modern", "pioneer"])) == 3
    assert mtgo.load(folder=tmp_path / "nowhere") == []


# ---- ingest behaviour ---------------------------------------------------------------


def _site(slugs, page=None):
    index = "".join(f'<a href="/decklist/{s}">x</a>' for s in slugs)
    pages = {"https://www.mtgo.com/decklists/2026/09": index, "https://www.mtgo.com/decklists/2026/08": ""}
    for s in slugs:
        pages[f"https://www.mtgo.com/decklist/{s}"] = page or _page(CHALLENGE)
    return pages


def test_date_bounds_are_inclusive(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    slugs = [
        "modern-league-2026-09-0112850001",
        "modern-league-2026-09-2112850002",
        "modern-league-2026-09-2212850003",
        "modern-league-2026-08-3112850004",
    ]
    pages = _site(slugs)
    res = mtgo.ingest(
        "modern", since=date(2026, 9, 1), until=date(2026, 9, 21), delay=0, get=pages.__getitem__
    )
    assert sorted(e.date for e in res.fetched) == ["2026-09-01", "2026-09-21"]


def test_kind_filter_skips_fetching(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    pages = _site(["modern-league-2026-09-2012850002", "modern-challenge-32-2026-09-1912850001"])
    fetched = []
    res = mtgo.ingest(
        "modern",
        since=date(2026, 9, 1),
        until=date(2026, 9, 21),
        delay=0,
        kinds=["challenge"],
        get=lambda u: fetched.append(u) or pages[u],
    )
    assert [e.kind for e in res.fetched] == ["challenge"]
    assert not any("league" in u for u in fetched)


def test_event_page_error_is_reported_and_run_continues(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    bad, good = "modern-league-2026-09-2012850002", "modern-challenge-32-2026-09-1912850001"
    pages = _site([bad, good])

    def get(url):
        if bad in url:
            raise mtgo.FetchError("timed out")
        return pages[url]

    res = mtgo.ingest("modern", since=date(2026, 9, 1), until=date(2026, 9, 21), delay=0, get=get)
    assert res.failed == [(bad, "timed out")] and [e.slug for e in res.fetched] == [good]


def test_index_requests_are_paced_too(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sleeps = []
    monkeypatch.setattr(mtgo.time, "sleep", sleeps.append)
    pages = {
        "https://www.mtgo.com/decklists/2026/07": "",
        "https://www.mtgo.com/decklists/2026/08": "",
        "https://www.mtgo.com/decklists/2026/09": "",
    }
    mtgo.ingest("modern", since=date(2026, 7, 1), until=date(2026, 9, 21), delay=1.5, get=pages.__getitem__)
    assert sleeps == [1.5, 1.5]  # between the 3 index pages, not before the first


def test_retrying_get(monkeypatch):
    import urllib.error

    attempts = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(req, timeout):
        attempts.append(req.full_url)
        if len(attempts) < 3:
            raise TimeoutError("slow")
        return Resp()

    monkeypatch.setattr(mtgo.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mtgo.time, "sleep", lambda s: None)
    assert mtgo._get("https://www.mtgo.com/x") == "ok" and len(attempts) == 3

    attempts.clear()

    def always_down(req, timeout):
        attempts.append(req.full_url)
        raise urllib.error.URLError("down")

    monkeypatch.setattr(mtgo.urllib.request, "urlopen", always_down)
    with pytest.raises(mtgo.FetchError, match="no answer after 3 tries"):
        mtgo._get("https://www.mtgo.com/x")
    assert len(attempts) == 3


# ---- metagame ------------------------------------------------------------------------


def test_card_stats_side_only_and_empty():
    e = mtgo.parse_event("modern-challenge-32-2026-09-1912850001", CHALLENGE)
    side = {s.name: s for s in metagame.card_stats([e], board="side")}
    assert set(side) == {"Fire/Ice", "Lightning Bolt"}
    assert side["Lightning Bolt"].main_decks == 0 and side["Lightning Bolt"].side_decks == 1
    assert metagame.card_stats([]) == []
    assert metagame.CardStat("x").share(0) == 0.0 and metagame.CardStat("x").avg == 0.0


def test_card_stats_order_is_stable():
    e = mtgo.parse_event("modern-challenge-32-2026-09-1912850001", CHALLENGE)
    names = [s.name for s in metagame.card_stats([e])]
    assert names[0] == "Lightning Bolt"  # in both decks
    assert names == [s.name for s in metagame.card_stats([e])]


def test_find_decks_card_and_player_together():
    e = mtgo.parse_event("modern-challenge-32-2026-09-1912850001", CHALLENGE)
    assert [d.player for _, d in metagame.find_decks([e], card="Lightning Bolt", player="alice")] == ["alice"]
    assert metagame.find_decks([e], card="Lightning Bolt", player="nobody") == []
