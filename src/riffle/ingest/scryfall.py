"""Scryfall bulk data: download the default-cards file, load it into DuckDB,
and keep each day's prices.

Published daily; carries oracle ids, legalities, and prices — including
MTGO tix (Scryfall sources those from Cardhoarder). One API request for the
index, then one file from *.scryfall.io, which has no rate limit — at most
once a day, since prices only change daily. Headers and 429 handling: riffle.net.

Since 2026-07-20 bulk files are gzipped JSON Lines only, linked from
`jsonl_download_uri`. The old `download_uri` (one big JSON array) is gone;
it's still read if present so an older cached file keeps working.

Prices: the bulk file is replaced every day, so its prices would be lost.
snapshot_prices() keeps them: <data_dir>/scryfall/daily/<day>.jsonl.gz holds
one line per printing, {"id": ..., "prices": {...}} exactly as Scryfall gave
them (strings, in USD, EUR, and MTGO tix), where <day> is the bulk file's date.
"""

import gzip
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from riffle import net
from riffle.config import data_dir
from riffle.progress import SILENT, Tracker
from riffle.store.db import connect, db_path

BULK_INDEX = "https://api.scryfall.com/bulk-data"

COLUMNS = {
    "id": "VARCHAR",
    "oracle_id": "VARCHAR",
    "name": "VARCHAR",
    "set": "VARCHAR",
    "collector_number": "VARCHAR",
    "layout": "VARCHAR",
    "frame": "VARCHAR",
    "border_color": "VARCHAR",
    "lang": "VARCHAR",
    "digital": "BOOLEAN",
    "released_at": "DATE",
    "mtgo_id": "BIGINT",
    "arena_id": "BIGINT",
    "rarity": "VARCHAR",
    "games": "VARCHAR[]",
    "type_line": "VARCHAR",
    "cmc": "DOUBLE",
    "color_identity": "VARCHAR[]",
    "legalities": "JSON",
    "oracle_text": "VARCHAR",
    "card_faces": "JSON",
    "prices": "STRUCT(usd VARCHAR, usd_foil VARCHAR, tix VARCHAR)",
}


def meta_path() -> Path:
    return data_dir() / "bulk-meta.json"


def remote_info(kind: str = "default_cards") -> dict:
    body = net.get(BULK_INDEX, accept="application/json")
    if body is None:
        raise RuntimeError(f"Scryfall's bulk index is missing ({BULK_INDEX})")
    for entry in json.loads(body)["data"]:
        if entry["type"] == kind:
            return entry
    raise RuntimeError(f"no bulk file of type {kind}")


def is_stale(max_age_hours: float = 24) -> bool:
    if not meta_path().exists() or not db_path().exists():
        return True
    saved = json.loads(meta_path().read_text())
    loaded = datetime.fromisoformat(saved["loaded_at"])
    return (datetime.now(UTC) - loaded).total_seconds() > max_age_hours * 3600


def download_url(info: dict) -> tuple[str, str]:
    """(url, local filename) — JSONL.gz now, the old JSON array as a fallback."""
    if info.get("jsonl_download_uri"):
        return info["jsonl_download_uri"], "default-cards.jsonl.gz"
    if info.get("download_uri"):
        return info["download_uri"], "default-cards.json"
    raise RuntimeError(f"Scryfall bulk entry has no download link: {sorted(info)}")


def download(dest_dir: Path | None = None, progress: net.Progress | None = None) -> tuple[Path, dict]:
    dest_dir = dest_dir or data_dir()
    info = remote_info()
    url, filename = download_url(info)
    dest = dest_dir / filename
    fresh = dest_dir / (filename + ".new")  # checked before it replaces the last good file
    if net.download(url, fresh, progress=progress) is None:
        raise RuntimeError(f"Scryfall's bulk file is missing ({url})")
    with fresh.open("rb") as f:
        magic = f.read(2)
    if filename.endswith(".gz") and magic != b"\x1f\x8b":
        fresh.unlink()
        raise RuntimeError("downloaded bulk file isn't gzip — Scryfall's format may have changed again")
    fresh.replace(dest)
    for old in dest_dir.glob("default-cards.*"):
        if old != dest and not old.name.endswith((".part", ".new")):
            old.unlink()
    return dest, info


def load(bulk_file: Path) -> int:
    """(Re)build the printings table from a bulk file. Returns row count."""
    cols = ", ".join(f"'{k}': '{v}'" for k, v in COLUMNS.items())
    src = str(bulk_file).replace("'", "''")
    fmt = "newline_delimited" if ".jsonl" in bulk_file.name else "array"
    explicit = f"read_json('{src}', format = '{fmt}', columns = {{{cols}}})"
    inferred = f"read_json_auto('{src}', format = '{fmt}', sample_size = -1)"
    con = connect(read_only=False)
    try:
        try:
            _create(con, explicit)
        except duckdb.Error:
            # Scryfall added a field whose shape clashes with the explicit
            # schema — fall back to full inference (slower, same result).
            _create(con, inferred)
        _fold_reversibles(con)
        return con.execute("SELECT count(*) FROM printings").fetchall()[0][0]
    finally:
        con.close()


def _fold_reversibles(con: duckdb.DuckDBPyConnection) -> None:
    """Secret Lair reversible cards are listed as "Sol Ring // Sol Ring" with
    their own oracle id. Point them at the real card, so a reversible copy in
    the collection counts as owning the card and prices merge."""
    con.execute("""
        UPDATE printings AS p
        SET oracle_id = n.oracle_id, name = n.name, name_lc = n.name_lc, front_lc = n.front_lc
        FROM (
            SELECT DISTINCT ON (name_lc) name_lc, name, front_lc, oracle_id
            FROM printings
            WHERE oracle_id IS NOT NULL AND name_lc NOT LIKE '% // %'
            ORDER BY name_lc, released_at
        ) AS n
        WHERE p.name_lc = n.name_lc || ' // ' || n.name_lc
    """)


def _create(con: duckdb.DuckDBPyConnection, source: str) -> None:
    con.execute(f"""
            CREATE OR REPLACE TABLE printings AS
            SELECT
                id                                                           AS scryfall_id,
                coalesce(oracle_id, json_extract_string(to_json(card_faces), '$[0].oracle_id')) AS oracle_id,
                name,
                lower(name)                                                  AS name_lc,
                lower(split_part(name, ' // ', 1))                           AS front_lc,
                "set"                                                        AS set_code,
                collector_number, layout, frame, border_color, lang, digital,
                released_at, mtgo_id, arena_id, rarity, games, type_line, cmc, color_identity, legalities,
                oracle_text, card_faces,
                TRY_CAST(prices.usd AS DOUBLE)                               AS usd,
                TRY_CAST(prices.usd_foil AS DOUBLE)                          AS usd_foil,
                TRY_CAST(prices.tix AS DOUBLE)                               AS tix
        FROM {source}
    """)


def refresh(force: bool = False, max_age_hours: float = 24, tracker: Tracker = SILENT) -> None:
    """Download the bulk file and load it, unless the loaded one is recent. Failures are
    reported to the tracker, then raised."""
    if not force and not is_stale(max_age_hours):
        tracker.step("Scryfall bulk data").ok("current")
        return
    step = tracker.step("Scryfall bulk data", unit="bytes")
    try:
        path, info = download(progress=step.update)
    except Exception as e:
        step.fail(str(e))
        raise
    updated = str(info.get("updated_at") or "?")
    step.ok(f"{path.stat().st_size / 1e6:,.1f} MB, Scryfall {updated[:10]}")
    step = tracker.step("card catalog")
    try:
        rows = load(path)
    except Exception as e:
        step.fail(str(e))
        raise
    meta = {"updated_at": info.get("updated_at"), "loaded_at": datetime.now(UTC).isoformat(), "rows": rows}
    meta_path().write_text(json.dumps(meta))
    step.ok(f"{rows:,} printings")


def prices_dir() -> Path:
    return data_dir() / "scryfall" / "daily"


def bulk_file(dest_dir: Path | None = None) -> Path | None:
    """The downloaded bulk file, if any."""
    dest_dir = dest_dir or data_dir()
    files = [p for p in dest_dir.glob("default-cards.*") if not p.name.endswith((".part", ".new"))]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _cards(bulk: Path) -> Iterator[dict]:
    if ".jsonl" in bulk.name:
        opener = gzip.open if bulk.name.endswith(".gz") else open
        with opener(bulk, "rt", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)
    else:
        with bulk.open(encoding="utf-8") as f:
            yield from json.load(f)


def bulk_day(bulk: Path) -> date:
    """The day the bulk file's prices are for: Scryfall's updated_at, else the file's own date."""
    if meta_path().exists():
        stamp = json.loads(meta_path().read_text()).get("updated_at")
        if stamp:
            return datetime.fromisoformat(stamp).date()
    return datetime.fromtimestamp(bulk.stat().st_mtime, UTC).date()


def snapshot_prices(bulk: Path | None = None) -> tuple[Path, bool]:
    """Keep the bulk file's prices for its day. Returns (file, whether it was written now)."""
    bulk = bulk or bulk_file()
    if bulk is None:
        raise FileNotFoundError("no Scryfall bulk file yet")
    dest = prices_dir() / f"{bulk_day(bulk).isoformat()}.jsonl.gz"
    if dest.exists():
        return dest, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        with gzip.open(tmp, "wt", encoding="utf-8") as out:
            for card in _cards(bulk):
                line = json.dumps({"id": card["id"], "prices": card.get("prices")}, separators=(",", ":"))
                out.write(line + "\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(dest)
    return dest, True
