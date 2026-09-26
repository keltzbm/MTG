"""MTGO decklists from mtgo.com: league 5-0s, challenges, showcases, qualifiers.

Event pages render client-side. The data is one JSON object assigned to
`window.MTGO.decklists.data` in a script tag, so we lift that out instead of
parsing HTML. The monthly index (/decklists/YYYY/MM) links every event as
/decklist/<slug>, where the slug ends in the date and event id:

    modern-challenge-32-2026-04-1812839681   -> 2026-04-18, event 12839681

Each event is fetched once and stored, normalized, as
<data_dir>/mtgo/<slug>.json. Published lists don't change, so a re-run only
fetches what's new. Requests are spaced out (`delay`) to be polite.

Throttled, mtgo.com doesn't refuse: it answers with stripped pages. How a run tells
those apart from missing data, and backs off, is described under fetching below.
"""

import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from riffle import net
from riffle.config import data_dir
from riffle.progress import SILENT, Tracker, elapsed

BASE = "https://www.mtgo.com"
KINDS = ("league", "challenge", "showcase", "qualifier", "preliminary", "other")
# The formats mtgo.com publishes decklists in, spelled as its event names spell them. Tab
# completion offers these; ingest takes whatever format an event name starts with.
FORMATS = ("standard", "pioneer", "modern", "legacy", "vintage", "pauper", "premodern", "duel-commander")

_DATA = re.compile(r"window\.MTGO\.decklists\.data\s*=\s*")
_LINK = re.compile(r'href="(?:https?://(?:www\.)?mtgo\.com)?/decklist/([a-z0-9-]+)"', re.I)
_SLUG = re.compile(r"^(?P<name>[a-z0-9-]+?)-(?P<date>\d{4}-\d{2}-\d{2})(?P<id>\d+)$")


@dataclass
class Card:
    name: str
    qty: int


@dataclass
class MtgoDeck:
    player: str
    main: list[Card] = field(default_factory=list)
    side: list[Card] = field(default_factory=list)
    rank: int | None = None  # final standing (challenges, showcases)
    record: str | None = None  # "5-0" for leagues

    @property
    def fingerprint(self) -> str:
        """Same 75 (main and side, any order, any printing split) -> same value.
        Groups identical lists without dropping any: a list that 5-0s twice counts twice."""

        def part(cards: list[Card]) -> str:
            return "|".join(sorted(f"{c.name.lower()}:{c.qty}" for c in cards))

        return hashlib.sha1(f"{part(self.main)}||{part(self.side)}".encode()).hexdigest()[:12]

    def to_text(self) -> str:
        """MTGO .txt: main, blank line, sideboard — readable by `riffle own`."""
        lines = [f"{c.qty} {c.name}" for c in self.main]
        if self.side:
            lines += [""] + [f"{c.qty} {c.name}" for c in self.side]
        return "\n".join(lines) + "\n"


@dataclass
class Event:
    slug: str
    event_id: str
    name: str  # "modern-challenge-32"
    format: str  # "modern"
    kind: str  # one of KINDS
    date: str  # ISO date
    decks: list[MtgoDeck] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        decks = [
            MtgoDeck(
                player=x["player"],
                main=[Card(**c) for c in x["main"]],
                side=[Card(**c) for c in x["side"]],
                rank=x.get("rank"),
                record=x.get("record"),
            )
            for x in d["decks"]
        ]
        return cls(**{**d, "decks": decks})


# ---- slugs and pages -----------------------------------------------------------


def parse_slug(slug: str) -> tuple[str, str, str] | None:
    """(event name, ISO date, event id), or None if it isn't an event slug."""
    m = _SLUG.match(slug)
    return (m["name"], m["date"], m["id"]) if m else None


def classify(name: str) -> str:
    for kind in ("league", "showcase", "qualifier", "preliminary", "challenge"):
        if kind in name:
            return kind
    return "other"


def event_format(name: str) -> str:
    """Format from the event name: the part before the event type."""
    parts = name.split("-")
    for i, p in enumerate(parts):
        if p in {"league", "challenge", "showcase", "qualifier", "preliminary", "super", "last", "chance"}:
            return "-".join(parts[:i]) or parts[0]
    return parts[0]


def event_slugs(index_html: str) -> list[str]:
    """Event slugs linked from a monthly index page, in page order, deduplicated."""
    return list(dict.fromkeys(s.lower() for s in _LINK.findall(index_html) if parse_slug(s.lower())))


def extract_data(page_html: str) -> dict:
    m = _DATA.search(page_html)
    if not m:
        raise ValueError("no decklist data on page — mtgo.com's layout may have changed")
    obj, _ = json.JSONDecoder().raw_decode(page_html, m.end())
    return obj


def _cards(
    main_rows: Iterable[dict] | None,
    side_rows: Iterable[dict] | None,
) -> tuple[list[Card], list[Card]]:
    """MTGO lists a card once per printing; merge by name, keep first-seen order.
    A row flagged "sideboard": "true" goes to the sideboard whichever list it's in."""
    boards: dict[str, dict[str, int]] = {"main": {}, "side": {}}
    for default, rows in (("main", main_rows), ("side", side_rows)):
        for r in rows or []:
            attrs = r.get("card_attributes") or {}
            name = attrs.get("card_name") or r.get("card_name")
            if not name:
                continue
            board = boards["side" if str(r.get("sideboard", "")).lower() == "true" else default]
            board[name] = board.get(name, 0) + int(r.get("qty") or r.get("quantity") or 0)
    return ([Card(n, q) for n, q in boards["main"].items()], [Card(n, q) for n, q in boards["side"].items()])


def _record(d: dict, kind: str) -> str | None:
    w = d.get("wins")
    if isinstance(w, dict) and w.get("wins") is not None:
        return f"{w['wins']}-{w.get('losses', 0)}"
    return "5-0" if kind == "league" else None  # MTGO only publishes 5-0 league lists


def parse_event(slug: str, data: dict) -> Event:
    parsed = parse_slug(slug)
    if not parsed:
        raise ValueError(f"not an event slug: {slug}")
    name, day, event_id = parsed
    kind = classify(name)

    ranks: dict[str, int] = {}
    for s in data.get("standings") or []:
        rank = s.get("rank")
        if rank is None:
            continue
        for key in (s.get("loginid"), s.get("login_name")):
            if key is not None:
                ranks[str(key).lower()] = int(rank)

    decks = []
    for d in data.get("decklists") or []:
        player = d.get("player") or d.get("login_name") or "?"
        main, side = _cards(d.get("main_deck"), d.get("sideboard_deck"))
        rank = ranks.get(str(d.get("loginid")).lower()) or ranks.get(player.lower())
        decks.append(MtgoDeck(player, main, side, rank, _record(d, kind)))
    decks.sort(key=lambda x: (x.rank is None, x.rank or 0))
    return Event(slug, event_id, name, event_format(name), kind, day, decks)


# ---- storage -------------------------------------------------------------------


def store_dir() -> Path:
    return data_dir() / "mtgo"


def save(event: Event) -> Path:
    path = store_dir() / f"{event.slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(event), indent=1), encoding="utf-8")
    return path


def load(
    fmt: str | Iterable[str] | None = None,
    since: date | None = None,
    kinds: Iterable[str] | None = None,
    folder: Path | None = None,
) -> list[Event]:
    """Stored events, newest first."""
    folder = folder or store_dir()
    kinds = set(kinds or KINDS)
    fmts = {fmt} if isinstance(fmt, str) else set(fmt or ())
    events = []
    for p in folder.glob("*.json") if folder.exists() else []:
        e = Event.from_dict(json.loads(p.read_text(encoding="utf-8")))
        if not e.decks:
            continue
        if fmts and e.format not in fmts:
            continue
        if since and e.date < since.isoformat():
            continue
        if e.kind in kinds:
            events.append(e)
    return sorted(events, key=lambda e: (e.date, e.event_id), reverse=True)


# ---- fetching ------------------------------------------------------------------
# A throttled answer is a 200 with a stripped page: an index with no event links, or
# an event page with no lists. Those look like an empty month or lists not published
# yet, so they're judged by age, and a run backs off when bad answers come in a row.

PENDING_DAYS = 3  # an empty page for an event younger than this is waiting for its lists
NEW_MONTH_DAYS = 2  # only a month this new may list no events
GIVE_UP_AFTER = 3  # clean empty answers, one a run, before an old event is skipped
INDEX_TIMEOUT = 20.0  # seconds; mtgo.com occasionally stalls instead of answering
EVENT_TIMEOUT = 60.0  # league pages run past 250 KB and come back slowly
BACKOFF_AFTER = 3  # bad answers in a row before a pause
BACKOFF = (30.0, 60.0, 120.0)  # seconds; a bad streak after the last pause stops the run
OUTCOMES = ("new", "not published yet", "empty", "given up", "failed")


def _today() -> date:
    """The date event ages count from; a function so tests can fix it."""
    return date.today()


def _get(url: str) -> str:
    """A page. Event pages get longer to answer than the monthly index."""
    timeout = EVENT_TIMEOUT if "/decklist/" in url else INDEX_TIMEOUT
    return net.get_text(url, accept="text/html", timeout=timeout)


def _months(start: date, end: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def misses_path() -> Path:
    """Old events that came back empty right after good answers, and on how many runs.
    It sits beside the event store, not in it: load() reads every .json in there."""
    return data_dir() / "mtgo-misses.json"


def _load_misses() -> dict[str, int]:
    try:
        misses = json.loads(misses_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return misses if isinstance(misses, dict) else {}


def _save_misses(misses: dict[str, int]) -> None:
    path = misses_path()
    if misses:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(sorted(misses.items())), indent=1) + "\n", encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


class Stopped(Exception):
    """mtgo.com kept answering badly after the longest pause."""


class _Pacer:
    """Spaces requests `delay` apart, and pauses when mtgo.com stops answering properly.

    Errors, indexes listing no events, and empty pages for old events are bad answers; a
    good one resets the count. After BACKOFF_AFTER bad answers in a row, the next request
    waits out the next pause in BACKOFF instead of the delay. Pausing before a request,
    not after the bad answer, means a run never waits with nothing left to fetch. A bad
    streak after the longest pause stops the run.
    """

    def __init__(self, delay: float, tracker: Tracker) -> None:
        self.delay, self.tracker = delay, tracker
        self.requests = 0
        self.streak = 0  # bad answers in a row
        self.pauses = 0  # pauses since the last good answer
        self.last_good = False  # whether the latest answer was good

    def wait(self) -> None:
        """Before each request. Raises Stopped once the longest pause didn't help."""
        if self.streak >= BACKOFF_AFTER:
            if self.pauses == len(BACKOFF):
                raise Stopped(f"mtgo.com still answering badly after a {elapsed(BACKOFF[-1])} pause")
            step = self.tracker.step("mtgo.com pause")
            time.sleep(BACKOFF[self.pauses])
            step.ok(f"after {self.streak} bad answers in a row")
            self.pauses += 1
            self.streak = 0
        elif self.requests:
            time.sleep(self.delay)
        self.requests += 1

    def answered(self, good: bool | None) -> None:
        """A good answer, a bad one, or neither (None): an empty page for an event too
        young to have lists, or an empty index for a month just begun."""
        self.last_good = good is True
        if good:
            self.streak = self.pauses = 0
        elif good is False:
            self.streak += 1


@dataclass
class IngestResult:
    fetched: list[Event] = field(default_factory=list)
    skipped: int = 0  # already stored
    pending: list[str] = field(default_factory=list)  # young; lists not published yet
    empty: list[str] = field(default_factory=list)  # old but empty, likely throttled; retried next run
    given_up: list[str] = field(default_factory=list)  # empty on GIVE_UP_AFTER runs; skipped from now on
    missed: int = 0  # skipped: given up on an earlier run
    left: int = 0  # found but not fetched: over max_events, or the run stopped
    stopped: str | None = None  # why the run stopped early
    failed: list[tuple[str, str]] = field(default_factory=list)


def is_stored(slug: str) -> bool:
    """Stored with decks. An empty event was saved before its lists were
    published (older versions did this) — it counts as not stored."""
    path = store_dir() / f"{slug}.json"
    if not path.exists():
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("decks"))
    except (OSError, ValueError):
        return False


def _note(counts: dict[str, int]) -> str:
    return ", ".join(f"{k} {what}" for what, k in counts.items() if k)


@dataclass
class _Run:
    """One ingest: what it looks for, and the state its steps share."""

    fmts: set[str] | None
    kinds: set[str]
    since: date
    until: date
    today: date
    get: Callable[[str], str]
    tracker: Tracker
    pacer: _Pacer
    misses: dict[str, int]
    res: IngestResult = field(default_factory=IngestResult)

    def index(self) -> list[tuple[str, str, date]]:
        """Read every month's index, newest month first. Returns (slug, format, day) for
        each event to fetch, newest first. Stored events count as skipped and given-up
        ones as missed; the step fails when a month's index couldn't be read."""
        months = _months(self.since, self.until)[::-1]
        step = self.tracker.step("mtgo.com index", total=len(months), unit="months")
        found: dict[str, tuple[str, date, int]] = {}
        seen: set[str] = set()  # an event linked from two months is fetched once
        unreadable = 0
        for i, (y, m) in enumerate(months, 1):
            try:
                self.pacer.wait()
            except Stopped as e:
                self.res.left += len(found)
                step.fail(f"stopped after {i - 1} of {len(months)} months: {e}")
                raise
            if not self.month(y, m, found, seen):
                unreadable += 1
            step.update(i)
        note = f"{len(found)} to fetch, {self.res.skipped} already stored"
        if self.res.missed:
            note += f", {self.res.missed} given up earlier"
        if unreadable:
            step.fail(f"{note}, {unreadable} unreadable")
        else:
            step.ok(note)
        newest_first = sorted(found.items(), key=lambda item: item[1][1:], reverse=True)
        return [(slug, fmt, day) for slug, (fmt, day, _) in newest_first]

    def month(self, y: int, m: int, found: dict[str, tuple[str, date, int]], seen: set[str]) -> bool:
        """One month's index into found. False when it couldn't be read: an error, or no
        events listed in a month old enough to have some."""
        url = f"{BASE}/decklists/{y}/{m:02d}"
        try:
            slugs = event_slugs(self.get(url))
        except Exception as e:  # report and move on to the next month
            self.res.failed.append((url, str(e)))
            self.pacer.answered(False)
            return False
        if not slugs:
            if (self.today - date(y, m, 1)).days < NEW_MONTH_DAYS:
                self.pacer.answered(None)
                return True
            self.res.failed.append((url, "no events listed, likely throttled"))
            self.pacer.answered(False)
            return False
        self.pacer.answered(True)
        for slug in slugs:
            parsed = parse_slug(slug)
            if parsed is None or slug in seen:
                continue
            seen.add(slug)
            name, day, event_id = parsed
            fmt = event_format(name)
            if (self.fmts and fmt not in self.fmts) or classify(name) not in self.kinds:
                continue
            if not self.since.isoformat() <= day <= self.until.isoformat():
                continue
            if is_stored(slug):
                self.res.skipped += 1
            elif self.misses.get(slug, 0) >= GIVE_UP_AFTER:
                self.res.missed += 1
            else:
                found[slug] = (fmt, date.fromisoformat(day), int(event_id))
        return True

    def fetch(self, todo: list[tuple[str, str, date]]) -> None:
        """Each format's events as a step with its total, newest first."""
        by_format: dict[str, list[tuple[str, date]]] = {}
        for slug, fmt, day in todo:
            by_format.setdefault(fmt, []).append((slug, day))
        left = len(todo)
        for fmt, events in by_format.items():
            step = self.tracker.step(f"mtgo {fmt}", total=len(events), unit="events")
            counts = dict.fromkeys(OUTCOMES, 0)
            for n, (slug, day) in enumerate(events, 1):
                try:
                    self.pacer.wait()
                except Stopped as e:
                    self.res.left += left
                    step.fail(f"{_note(counts) or 'nothing fetched'}; stopped: {e}")
                    raise
                counts[self.event(slug, day)] += 1
                left -= 1
                step.update(n)
            if counts["empty"] or counts["failed"]:
                step.fail(_note(counts))
            else:
                step.ok(_note(counts))

    def event(self, slug: str, day: date) -> str:
        """Fetch one event and store it. Returns its outcome, one of OUTCOMES."""
        clean = self.pacer.last_good  # the site was answering properly just before
        try:
            page = self.get(f"{BASE}/decklist/{slug}")
        except Exception as e:  # one broken page shouldn't stop the run
            self.res.failed.append((slug, str(e)))
            self.pacer.answered(False)
            return "failed"
        try:
            event: Event | None = parse_event(slug, extract_data(page))
        except ValueError:
            event = None  # the page is up but its data isn't
        if event is not None and event.decks:
            save(event)
            self.misses.pop(slug, None)
            self.res.fetched.append(event)
            self.pacer.answered(True)
            return "new"
        if (self.today - day).days < PENDING_DAYS:
            self.res.pending.append(slug)
            self.pacer.answered(None)
            return "not published yet"
        self.pacer.answered(False)
        if clean:  # only an empty answer while the site answers properly counts toward giving up
            self.misses[slug] = self.misses.get(slug, 0) + 1
            if self.misses[slug] >= GIVE_UP_AFTER:
                self.res.given_up.append(slug)
                return "given up"
        self.res.empty.append(slug)
        return "empty"


def ingest(
    formats: Iterable[str] | None,
    since: date,
    until: date | None = None,
    kinds: Iterable[str] | None = None,
    delay: float = 1.0,
    max_events: int | None = None,
    get: Callable[[str], str] = _get,
    tracker: Tracker = SILENT,
) -> IngestResult:
    """Fetch new events, newest first. formats=None means every format.

    Every month's index is read first, so each format's events are a step with a known
    total on the tracker. max_events caps the event pages fetched: the newest go first,
    and later runs skip what's stored and reach further back.
    """
    today = _today()
    if isinstance(formats, str):
        formats = [formats]
    run = _Run(
        fmts={f.lower() for f in formats} if formats else None,
        kinds=set(kinds or KINDS),
        since=since,
        until=until or today,
        today=today,
        get=get,
        tracker=tracker,
        pacer=_Pacer(delay, tracker),
        misses=_load_misses(),
    )
    misses = dict(run.misses)
    try:
        todo = run.index()
        if max_events is not None and len(todo) > max_events:
            run.res.left = len(todo) - max_events
            todo = todo[:max_events]
        run.fetch(todo)
    except Stopped as e:
        run.res.stopped = str(e)
    finally:
        if run.misses != misses:
            _save_misses(run.misses)
    return run.res
