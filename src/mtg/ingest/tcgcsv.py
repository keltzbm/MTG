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
tried again next run. tcgcsv asks for a pause between requests (their FAQ
and docs); headers, retries and streaming live in mtg.net.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial
from pathlib import Path

from mtg import net
from mtg.config import data_dir

BASE = "https://tcgcsv.com"
FIRST_DAY = date(2024, 2, 8)
SEVEN_ZIP_MAGIC = b"7z\xbc\xaf\x27\x1c"

Download = Callable[[str, Path, net.Progress | None], int | None]
Meter = Callable[[date, int, int | None], None]  # (day, bytes so far, total if known)


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


def _days(since: date, until: date) -> list[date]:
    since = max(since, FIRST_DAY)
    return [since + timedelta(days=i) for i in range((until - since).days + 1)]


@dataclass
class ArchiveResult:
    fetched: list[date] = field(default_factory=list)
    skipped: int = 0  # already stored
    pending: list[date] = field(default_factory=list)  # not published yet (404)
    failed: list[tuple[date, str]] = field(default_factory=list)


def _is_7z(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(len(SEVEN_ZIP_MAGIC)) == SEVEN_ZIP_MAGIC


def _download(url: str, dest: Path, progress: net.Progress | None) -> int | None:
    return net.download(url, dest, progress=progress)


def ingest(
    since: date,
    until: date | None = None,
    delay: float = 0.25,
    download: Download = _download,
    progress: Callable[[str], None] = lambda _: None,
    meter: Meter | None = None,
) -> ArchiveResult:
    """Download every day's archive in [since, until] that isn't stored yet.

    progress gets one line per finished day; meter, if given, gets byte counts
    while a file streams — for a live display on a terminal.
    """
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
        dest = archive_path(day)
        try:
            size = download(archive_url(day), dest, partial(meter, day) if meter else None)
        except Exception as e:  # one bad day shouldn't stop a long backfill
            res.failed.append((day, str(e)))
            continue
        if size is None:
            res.pending.append(day)
            continue
        if not _is_7z(dest):
            dest.unlink()
            res.failed.append((day, "not a 7z archive — tcgcsv's archive format may have changed"))
            continue
        res.fetched.append(day)
        progress(f"{day}  {size / 1e6:6.1f} MB")
    return res
