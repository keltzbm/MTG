"""Daily tcgcsv price snapshots: one request per file, stored as returned, a day fetched once."""

import gzip
import json
from datetime import UTC, date, datetime

import pytest

from riffle import net
from riffle.ingest import tcgcsv

B = tcgcsv.BASE
STAMP = b"2026-09-24T20:05:50+0000\n"
DAY = date(2026, 9, 24)
CATS = json.dumps(
    {
        "success": True,
        "errors": [],
        "results": [
            {"categoryId": 1, "name": "Magic"},
            {"categoryId": 62, "name": "Flesh & Blood TCG"},
            {"categoryId": 68, "name": "One Piece Card Game"},
        ],
    }
).encode()
FAB = {"fab": "Flesh & Blood TCG"}


def groups(*ids: int) -> bytes:
    results = [{"groupId": i, "name": f"g{i}"} for i in ids]
    return json.dumps({"success": True, "errors": [], "results": results}).encode()


def prices(*product_ids: int) -> bytes:
    rows = [{"productId": p, "lowPrice": 1.5, "subTypeName": "Normal"} for p in product_ids]
    return json.dumps({"success": True, "errors": [], "results": rows}).encode()


def fake_fetch(answers: dict[str, bytes | None | Exception]):
    """answers: url -> body, None (404), or an exception to raise. Records every url asked for."""
    asked: list[str] = []

    def fetch(url: str) -> bytes | None:
        asked.append(url)
        answer = answers.get(url)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return fetch, asked


def fab_answers(**overrides):
    answers = {
        f"{B}/last-updated.txt": STAMP,
        f"{B}/tcgplayer/categories": CATS,
        f"{B}/tcgplayer/62/groups": groups(200, 100),
        f"{B}/tcgplayer/62/100/prices": prices(1, 2),
        f"{B}/tcgplayer/62/200/prices": prices(3),
    }
    answers.update(overrides)
    return answers


def lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path / "riffle"


@pytest.fixture
def sleeps(monkeypatch):
    calls: list[float] = []
    monkeypatch.setattr(tcgcsv.time, "sleep", calls.append)
    return calls


def test_last_updated_parses_tcgcsv_stamp():
    fetch, _ = fake_fetch({f"{B}/last-updated.txt": STAMP})
    assert tcgcsv.last_updated(fetch) == datetime(2026, 9, 24, 20, 5, 50, tzinfo=UTC)
    fetch, _ = fake_fetch({f"{B}/last-updated.txt": b"<html>down</html>"})
    with pytest.raises(net.FetchError, match="last-updated"):
        tcgcsv.last_updated(fetch)


def test_resolve_matches_category_names_regardless_of_case():
    cats = [{"categoryId": 1, "name": "MAGIC"}, {"categoryId": 62, "name": "Flesh & Blood TCG"}, {"x": 1}]
    wanted = {"mtg": "Magic", "fab": "flesh & blood tcg", "op": "One Piece Card Game"}
    assert tcgcsv.resolve(cats, wanted) == {"mtg": 1, "fab": 62}


def test_snapshot_stores_a_game_as_returned_under_tcgcsv_day(data_dir, sleeps):
    fetch, asked = fake_fetch(fab_answers())
    snap = tcgcsv.snapshot(FAB, delay=0.1, fetch=fetch)
    assert (snap.day, snap.fetched, snap.skipped, snap.failed) == (DAY, ["fab"], [], [])
    assert snap.groups == {"fab": 2} and snap.requests == 5
    day = data_dir / "tcgcsv" / "daily" / "2026-09-24"
    assert (day / "last-updated.txt").read_bytes() == STAMP.strip()
    assert (day / "fab" / "groups.json").read_bytes() == groups(200, 100)
    assert lines(day / "fab" / "prices.jsonl.gz") == [
        {"groupId": 100, "response": json.loads(prices(1, 2))},
        {"groupId": 200, "response": json.loads(prices(3))},
    ]
    by_id = [f"{B}/tcgplayer/62/100/prices", f"{B}/tcgplayer/62/200/prices"]
    assert asked[-2:] == by_id  # sorted by id, not in the listing's order
    assert sleeps == [0.1, 0.1]  # one pause before each price file
    assert tcgcsv.stored_days(FAB) == [DAY]
    assert not list(day.rglob("*.part"))


def test_a_stored_day_costs_one_request(data_dir, sleeps):
    fetch, asked = fake_fetch(fab_answers())
    tcgcsv.snapshot(FAB, fetch=fetch)
    fetch, asked = fake_fetch(fab_answers())
    snap = tcgcsv.snapshot(FAB, fetch=fetch)
    assert asked == [f"{B}/last-updated.txt"]
    assert (snap.fetched, snap.skipped, snap.requests) == ([], ["fab"], 1)


def test_missing_price_file_is_kept_as_null(data_dir, sleeps):
    fetch, _ = fake_fetch(fab_answers(**{f"{B}/tcgplayer/62/200/prices": None}))
    snap = tcgcsv.snapshot(FAB, fetch=fetch)
    assert snap.fetched == ["fab"]
    assert lines(tcgcsv.day_dir(DAY, "fab") / "prices.jsonl.gz")[1] == {"groupId": 200, "response": None}


def test_a_failed_game_keeps_nothing_and_the_others_continue(data_dir, sleeps):
    answers = fab_answers(
        **{
            f"{B}/tcgplayer/62/200/prices": net.FetchError("HTTP 503"),
            f"{B}/tcgplayer/68/groups": groups(7),
            f"{B}/tcgplayer/68/7/prices": prices(9),
        }
    )
    fetch, _ = fake_fetch(answers)
    snap = tcgcsv.snapshot({"fab": "Flesh & Blood TCG", "op": "One Piece Card Game"}, fetch=fetch)
    assert snap.failed == [("fab", "HTTP 503")] and snap.fetched == ["op"]
    assert not (tcgcsv.day_dir(DAY, "fab") / "prices.jsonl.gz").exists()
    assert not list(tcgcsv.daily_dir().rglob("*.part"))
    assert (tcgcsv.day_dir(DAY, "op") / "prices.jsonl.gz").exists()
    assert tcgcsv.stored_days({"fab": "x", "op": "x"}) == []  # a day counts only when every game has it


def test_unknown_category_is_reported_without_guessing(data_dir, sleeps):
    fetch, asked = fake_fetch(fab_answers())
    snap = tcgcsv.snapshot({"xx": "Nope"}, fetch=fetch)
    assert snap.failed == [("xx", "tcgcsv has no category named 'Nope'")]
    assert asked == [f"{B}/last-updated.txt", f"{B}/tcgplayer/categories"]


def test_an_unexpected_page_fails_the_game_cleanly(data_dir, sleeps):
    fetch, _ = fake_fetch(fab_answers(**{f"{B}/tcgplayer/62/groups": b"<html>maintenance</html>"}))
    snap = tcgcsv.snapshot(FAB, fetch=fetch)
    assert snap.failed == [("fab", "groups: not the expected JSON")]
    assert not (tcgcsv.day_dir(DAY, "fab") / "groups.json").exists()


def test_pretty_printed_response_still_takes_one_line(data_dir, sleeps):
    pretty = json.dumps(json.loads(prices(1)), indent=2).encode()
    fetch, _ = fake_fetch(fab_answers(**{f"{B}/tcgplayer/62/100/prices": pretty}))
    tcgcsv.snapshot(FAB, fetch=fetch)
    path = tcgcsv.day_dir(DAY, "fab") / "prices.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as f:
        assert len(f.read().splitlines()) == 2
    assert lines(path)[0] == {"groupId": 100, "response": json.loads(prices(1))}


def test_default_games_are_the_three_riffle_covers():
    assert list(tcgcsv.GAMES) == ["mtg", "fab", "op"]
