"""TCGplayer price history from tcgcsv.com's daily archive — every game at once.

tcgcsv mirrors TCGplayer's catalog and prices nightly and keeps one archive
per day, back to 2024-02-08:

    https://tcgcsv.com/archive/tcgplayer/prices-2026-09-21.ppmd.7z

One file holds that day's prices for every category (Magic, Flesh and Blood,
One Piece, ...), laid out inside as <date>/<categoryId>/<groupId>/prices.
So a day of history for every game is one request, not a walk over
thousands of groups.

Files are stored exactly as downloaded, still compressed, in
<data_dir>/tcgcsv/archive/. Nothing here opens them: loading into a database
is a later step, and it will need 7-Zip for the PPMd compression.

A day that isn't published yet answers 404; it's reported as pending and
tried again next run. tcgcsv asks for a descriptive User-Agent and a pause
between requests (their FAQ and docs).
"""

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from mtg import __version__
from mtg.config import data_dir

BASE = "https://tcgcsv.com"
FIRST_DAY = date(2024, 2, 8)
SEVEN_ZIP_MAGIC = b"7z\xbc\xaf\x27\x1c"
HEADERS = {"User-Agent": f"keltzbm-mtg/{__version__} (github.com/keltzbm/MTG)"}


def store_dir() -> Path:
    return data_dir() / "tcgcsv" / "archive"


def archive_name(day: date) -> str:
    return f"prices-{day.isoformat()}.ppmd.7z"


def archive_url(day: date) -> str:
    return f"{BASE}/archive/tcgplayer/{archive_name(day)}"


def archive_path(day: date) -> Path:
    return store_dir() / archive_name(day)


def stored_days() -> list[date]:
    """Days already on disk, oldest first."""
    folder = store_dir()
    days = []
    for p in folder.glob("prices-*.ppmd.7z") if folder.exists() else []:
        try:
            days.append(date.fromisoformat(p.name.removeprefix("prices-").removesuffix(".ppmd.7z")))
        except ValueError:
            continue
    return sorted(days)


def stored_bytes() -> int:
    folder = store_dir()
    return sum(p.stat().st_size for p in folder.glob("prices-*.ppmd.7z")) if folder.exists() else 0


class FetchError(RuntimeError):
    """tcgcsv didn't answer."""


def _get(url: str, retries: int = 2, timeout: float = 60) -> bytes | None:
    """The file's bytes, or None when it doesn't exist (404). Retries stalls."""
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries:
                raise FetchError(f"HTTP {e.code}") from e
        except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
            if attempt == retries:
                raise FetchError(f"no answer after {retries + 1} tries ({getattr(e, 'reason', e)})") from e
        time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def _days(since: date, until: date) -> list[date]:
    since = max(since, FIRST_DAY)
    return [since + timedelta(days=i) for i in range((until - since).days + 1)]


@dataclass
class ArchiveResult:
    fetched: list[date] = field(default_factory=list)
    skipped: int = 0  # already stored
    pending: list[date] = field(default_factory=list)  # not published yet (404)
    failed: list[tuple[date, str]] = field(default_factory=list)


def save(day: date, data: bytes) -> Path:
    """Write via a .part file so an interrupted run never leaves a truncated archive."""
    if not data.startswith(SEVEN_ZIP_MAGIC):
        raise ValueError("not a 7z archive — tcgcsv's archive format may have changed")
    dest = archive_path(day)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def ingest(
    since: date,
    until: date | None = None,
    delay: float = 0.25,
    get: Callable[[str], bytes | None] = _get,
    progress: Callable[[str], None] = lambda _: None,
) -> ArchiveResult:
    """Download every day's archive in [since, until] that isn't stored yet."""
    until = until or date.today()
    have = set(stored_days())
    res = ArchiveResult()
    requested = 0
    for day in _days(since, until):
        if day in have:
            res.skipped += 1
            continue
        if requested:
            time.sleep(delay)
        requested += 1
        try:
            data = get(archive_url(day))
        except Exception as e:  # one bad day shouldn't stop a long backfill
            res.failed.append((day, str(e)))
            continue
        if data is None:
            res.pending.append(day)
            continue
        try:
            save(day, data)
        except ValueError as e:
            res.failed.append((day, str(e)))
            continue
        res.fetched.append(day)
        progress(f"{day}  {len(data) / 1e6:6.1f} MB")
    return res
