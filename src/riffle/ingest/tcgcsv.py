"""Daily TCGplayer prices from tcgcsv.com, one snapshot per day per game.

tcgcsv mirrors TCGplayer's catalog and prices once a day and serves them as
plain JSON, no key needed:

    https://tcgcsv.com/last-updated.txt                     when today's data was published
    https://tcgcsv.com/tcgplayer/categories                 every game, with its categoryId
    https://tcgcsv.com/tcgplayer/{categoryId}/groups        a game's sets ("groups")
    https://tcgcsv.com/tcgplayer/{categoryId}/{groupId}/prices

It used to publish a daily archive of every price file at once. That was taken
down in September 2026 (server costs; the maintainer is waiting on TCGplayer
for terms), with the request that clients fetch the price files one at a time
and never the same file twice in a day. So Riffle keeps its own history: once
a day, for each game it covers, it fetches every group's price file and stores
the responses as returned, in

    <data_dir>/tcgcsv/daily/<day>/<game>/groups.json        the groups response
    <data_dir>/tcgcsv/daily/<day>/<game>/prices.jsonl.gz    one line per group:
                                                            {"groupId": ..., "response": <the price file>}

<day> is the date from last-updated.txt, so a day is fetched once however
often sync runs. Games are named by their tcgcsv category and resolved to IDs
at run time. Nothing here reads the files back: the price loader (v0.4.0)
does. Headers, retries, and 429 handling: riffle.net.
"""

import gzip
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from riffle import net
from riffle.config import data_dir
from riffle.progress import SILENT, Step, Tracker

BASE = "https://tcgcsv.com"
# Game code -> the game's category name on tcgcsv; IDs are looked up at run time.
GAMES = {"mtg": "Magic", "fab": "Flesh & Blood TCG", "op": "One Piece Card Game"}

Fetch = Callable[[str], bytes | None]  # url -> body, or None for 404


@dataclass
class Snapshot:
    day: date
    fetched: list[str] = field(default_factory=list)  # games stored this run
    skipped: list[str] = field(default_factory=list)  # games already stored for the day
    failed: list[tuple[str, str]] = field(default_factory=list)  # (game, why)
    groups: dict[str, int] = field(default_factory=dict)  # game -> price files fetched
    requests: int = 0


def _get(url: str) -> bytes | None:
    return net.get(url, accept="application/json")


def daily_dir() -> Path:
    return data_dir() / "tcgcsv" / "daily"


def day_dir(day: date, game: str) -> Path:
    return daily_dir() / day.isoformat() / game


def stored_days(games: dict[str, str] = GAMES) -> list[date]:
    """Days with a price file for every game, oldest first."""
    if not daily_dir().exists():
        return []
    days = []
    for entry in daily_dir().iterdir():
        try:
            day = date.fromisoformat(entry.name)
        except ValueError:
            continue
        if all((entry / game / "prices.jsonl.gz").exists() for game in games):
            days.append(day)
    return sorted(days)


def last_updated(fetch: Fetch = _get) -> datetime:
    """When tcgcsv last refreshed its data, e.g. 2026-09-24T20:05:50+0000."""
    body = fetch(f"{BASE}/last-updated.txt")
    if body is None:
        raise net.FetchError("HTTP 404")
    text = body.decode().strip()
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError as e:
        raise net.FetchError(f"unexpected last-updated.txt: {text[:40]!r}") from e


def _parse(body: bytes, what: str) -> dict:
    """The response as a dict with a "results" list, or a FetchError naming what came back instead."""
    try:
        doc = json.loads(body)
        if not isinstance(doc, dict) or not isinstance(doc["results"], list):
            raise KeyError("results")
    except (ValueError, KeyError, TypeError) as e:
        raise net.FetchError(f"{what}: not the expected JSON") from e
    return doc


def _results(body: bytes, what: str) -> list[dict]:
    return _parse(body, what)["results"]


def _one_line(body: bytes, what: str) -> str:
    """The response verbatim if it's one line, else compacted: the file is one JSON object per line."""
    doc = _parse(body, what)
    text = body.decode("utf-8").strip()
    return text if "\n" not in text and "\r" not in text else json.dumps(doc, separators=(",", ":"))


def categories(fetch: Fetch = _get) -> list[dict]:
    body = fetch(f"{BASE}/tcgplayer/categories")
    if body is None:
        raise net.FetchError("categories: HTTP 404")
    return _results(body, "categories")


def resolve(cats: list[dict], games: dict[str, str] = GAMES) -> dict[str, int]:
    """Game code -> tcgcsv categoryId, matched by name (case-insensitive). Unknown games are left out."""
    by_name = {str(c.get("name", "")).casefold(): int(c["categoryId"]) for c in cats if "categoryId" in c}
    return {code: by_name[name.casefold()] for code, name in games.items() if name.casefold() in by_name}


def _write(dest: Path, body: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(body)
    tmp.replace(dest)


def _fetch_game(
    game: str,
    category: int,
    target: Path,
    fetch: Fetch,
    delay: float,
    step: Step,
    snap: Snapshot,
) -> None:
    """Every price file of one game into target, all or nothing."""
    groups_body = fetch(f"{BASE}/tcgplayer/{category}/groups")
    snap.requests += 1
    if groups_body is None:
        raise net.FetchError("groups: HTTP 404")
    group_ids = sorted(int(g["groupId"]) for g in _results(groups_body, "groups"))
    _write(target.parent / "groups.json", groups_body)
    step.update(0, len(group_ids))
    tmp = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with gzip.open(tmp, "wt", encoding="utf-8") as out:
            for n, gid in enumerate(group_ids, 1):
                time.sleep(delay)
                body = fetch(f"{BASE}/tcgplayer/{category}/{gid}/prices")
                snap.requests += 1
                if body is None:
                    out.write(f'{{"groupId": {gid}, "response": null}}\n')
                else:
                    out.write(f'{{"groupId": {gid}, "response": {_one_line(body, f"group {gid}")}}}\n')
                step.update(n)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(target)
    snap.groups[game] = len(group_ids)


def snapshot(
    games: dict[str, str] = GAMES,
    delay: float = 0.1,
    fetch: Fetch = _get,
    tracker: Tracker = SILENT,
) -> Snapshot:
    """Store today's price files for every game that doesn't have them yet.

    "Today" is tcgcsv's last-updated date. A game whose file exists is skipped
    without a request; a game that fails part-way keeps nothing, so the next
    run fetches it whole. delay is the pause before each request (tcgcsv asks
    for ~100 ms). Each game is a step on the tracker, including stored ones.
    """
    stamp = last_updated(fetch)
    snap = Snapshot(day=stamp.date())
    snap.requests += 1
    todo = {game: day_dir(snap.day, game) / "prices.jsonl.gz" for game in games}
    for game, target in list(todo.items()):
        if target.exists():
            snap.skipped.append(game)
            tracker.step(f"tcgcsv {game}").ok(f"already have {snap.day}")
            del todo[game]
    if not todo:
        return snap
    ids = resolve(categories(fetch), games)
    snap.requests += 1
    stamp_file = daily_dir() / snap.day.isoformat() / "last-updated.txt"
    _write(stamp_file, stamp.strftime("%Y-%m-%dT%H:%M:%S%z").encode())
    for game, target in todo.items():
        step = tracker.step(f"tcgcsv {game}", unit="groups")
        why = None if game in ids else f"tcgcsv has no category named {games[game]!r}"
        if why is None:
            try:
                _fetch_game(game, ids[game], target, fetch, delay, step, snap)
            except net.FetchError as e:
                why = str(e)
        if why is not None:
            snap.failed.append((game, why))
            step.fail(why)
            continue
        snap.fetched.append(game)
        step.ok(f"{snap.groups[game]} groups")
    return snap
