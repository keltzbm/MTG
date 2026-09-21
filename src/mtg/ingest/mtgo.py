"""MTGO decklists from mtgo.com: league 5-0s, challenges, showcases, qualifiers.

Event pages render client-side. The data is one JSON object assigned to
`window.MTGO.decklists.data` in a script tag, so we lift that out instead of
parsing HTML. The monthly index (/decklists/YYYY/MM) links every event as
/decklist/<slug>, where the slug ends in the date and event id:

    modern-challenge-32-2026-04-1812839681   -> 2026-04-18, event 12839681

Each event is fetched once and stored, normalized, as
<data_dir>/mtgo/<slug>.json. Published lists don't change, so a re-run only
fetches what's new. Requests are spaced out (`delay`) to be polite.
"""

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from mtg import __version__
from mtg.config import data_dir

BASE = "https://www.mtgo.com"
HEADERS = {
    "User-Agent": f"keltzbm-mtg/{__version__} (github.com/keltzbm/MTG)",
    "Accept": "text/html",
}
KINDS = ("league", "challenge", "showcase", "qualifier", "preliminary", "other")

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
    rank: int | None = None       # final standing (challenges, showcases)
    record: str | None = None     # "5-0" for leagues

    @property
    def fingerprint(self) -> str:
        """Same 75 (main and side, any order, any printing split) -> same value.
        Groups identical lists without dropping any: a list that 5-0s twice counts twice."""
        def part(cards: list[Card]) -> str:
            return "|".join(sorted(f"{c.name.lower()}:{c.qty}" for c in cards))
        return hashlib.sha1(f"{part(self.main)}||{part(self.side)}".encode()).hexdigest()[:12]

    def to_text(self) -> str:
        """MTGO .txt: main, blank line, sideboard — readable by `mtg own`."""
        lines = [f"{c.qty} {c.name}" for c in self.main]
        if self.side:
            lines += [""] + [f"{c.qty} {c.name}" for c in self.side]
        return "\n".join(lines) + "\n"


@dataclass
class Event:
    slug: str
    event_id: str
    name: str          # "modern-challenge-32"
    format: str        # "modern"
    kind: str          # one of KINDS
    date: str          # ISO date
    decks: list[MtgoDeck] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        decks = [MtgoDeck(
            player=x["player"],
            main=[Card(**c) for c in x["main"]],
            side=[Card(**c) for c in x["side"]],
            rank=x.get("rank"),
            record=x.get("record"),
        ) for x in d["decks"]]
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
    main_rows: Iterable[dict] | None, side_rows: Iterable[dict] | None,
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
    return ([Card(n, q) for n, q in boards["main"].items()],
            [Card(n, q) for n, q in boards["side"].items()])


def _record(d: dict, kind: str) -> str | None:
    w = d.get("wins")
    if isinstance(w, dict) and w.get("wins") is not None:
        return f"{w['wins']}-{w.get('losses', 0)}"
    return "5-0" if kind == "league" else None   # MTGO only publishes 5-0 league lists


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

def _get(url: str, retries: int = 2, timeout: float = 20) -> str:
    """GET with a short retry — mtgo.com occasionally stalls instead of answering."""
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
            if attempt == retries:
                raise FetchError(f"no answer after {retries + 1} tries ({getattr(e, 'reason', e)})") from e
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


class FetchError(RuntimeError):
    """mtgo.com didn't answer."""


def _months(start: date, end: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


@dataclass
class IngestResult:
    fetched: list[Event] = field(default_factory=list)
    skipped: int = 0                                     # already stored
    pending: list[str] = field(default_factory=list)     # page up, lists not published yet
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


def ingest(
    formats: Iterable[str] | None,
    since: date,
    until: date | None = None,
    kinds: Iterable[str] | None = None,
    delay: float = 1.0,
    get: Callable[[str], str] = _get,
    progress: Callable[[str], None] = lambda _: None,
) -> IngestResult:
    """Fetch new events. formats=None means every format."""
    until = until or date.today()
    kinds = set(kinds or KINDS)
    if isinstance(formats, str):
        formats = [formats]
    fmts = {f.lower() for f in formats} if formats else None
    res = IngestResult()
    for y, m in _months(since, until):
        url = f"{BASE}/decklists/{y}/{m:02d}"
        try:
            index = get(url)
        except Exception as e:  # report and move on to the next month
            res.failed.append((url, str(e)))
            continue
        for slug in event_slugs(index):
            name, day, _ = parse_slug(slug)
            if (fmts and event_format(name) not in fmts) or classify(name) not in kinds:
                continue
            if not since.isoformat() <= day <= until.isoformat():
                continue
            if is_stored(slug):
                res.skipped += 1
                continue
            time.sleep(delay)
            try:
                page = get(f"{BASE}/decklist/{slug}")
            except Exception as e:  # one broken page shouldn't stop the run
                res.failed.append((slug, str(e)))
                continue
            try:
                event = parse_event(slug, extract_data(page))
            except ValueError:
                res.pending.append(slug)   # page is up but the data isn't yet
                continue
            if not event.decks:
                res.pending.append(slug)
                continue
            save(event)
            res.fetched.append(event)
            progress(f"{event.date}  {event.name:<32} {len(event.decks):>3} decks")
    return res
