"""Scryfall bulk data: download the default-cards file, load it into DuckDB.

Published daily; carries oracle ids, legalities, and prices — including
MTGO tix (Scryfall sources those from Cardhoarder). No scraping, no rate
limits. Scryfall asks every client to send a User-Agent and Accept header.

Since 2026-07-20 bulk files are gzipped JSON Lines only, linked from
`jsonl_download_uri`. The old `download_uri` (one big JSON array) is gone;
it's still read if present so an older cached file keeps working.
"""

import json
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from mtg import __version__
from mtg.config import data_dir
from mtg.store.db import connect, db_path

BULK_INDEX = "https://api.scryfall.com/bulk-data"
HEADERS = {
    "User-Agent": f"keltzbm-mtg/{__version__} (github.com/keltzbm/MTG)",
    "Accept": "application/json",
}

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
    "card_faces": "JSON",
    "prices": "STRUCT(usd VARCHAR, usd_foil VARCHAR, tix VARCHAR)",
}


def _get(url: str) -> urllib.request.addinfourl:
    return urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60)


def meta_path() -> Path:
    return data_dir() / "bulk-meta.json"


def remote_info(kind: str = "default_cards") -> dict:
    with _get(BULK_INDEX) as r:
        for entry in json.load(r)["data"]:
            if entry["type"] == kind:
                return entry
    raise RuntimeError(f"no bulk file of type {kind}")


def is_stale(max_age_hours: float = 24) -> bool:
    if not meta_path().exists() or not db_path().exists():
        return True
    saved = json.loads(meta_path().read_text())
    loaded = datetime.fromisoformat(saved["loaded_at"])
    return (datetime.now(timezone.utc) - loaded).total_seconds() > max_age_hours * 3600


def download_url(info: dict) -> tuple[str, str]:
    """(url, local filename) — JSONL.gz now, the old JSON array as a fallback."""
    if info.get("jsonl_download_uri"):
        return info["jsonl_download_uri"], "default-cards.jsonl.gz"
    if info.get("download_uri"):
        return info["download_uri"], "default-cards.json"
    raise RuntimeError(f"Scryfall bulk entry has no download link: {sorted(info)}")


def download(dest_dir: Path | None = None) -> tuple[Path, dict]:
    dest_dir = dest_dir or data_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    info = remote_info()
    url, filename = download_url(info)
    dest = dest_dir / filename
    tmp = dest_dir / (filename + ".part")
    with _get(url) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    with tmp.open("rb") as f:
        magic = f.read(2)
    if filename.endswith(".gz") and magic != b"\x1f\x8b":
        tmp.unlink()
        raise RuntimeError("downloaded bulk file isn't gzip — Scryfall's format may have changed again")
    tmp.replace(dest)
    for old in dest_dir.glob("default-cards.*"):
        if old != dest and not old.name.endswith(".part"):
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
        return con.execute("SELECT count(*) FROM printings").fetchone()[0]
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
                TRY_CAST(prices.usd AS DOUBLE)                               AS usd,
                TRY_CAST(prices.usd_foil AS DOUBLE)                          AS usd_foil,
                TRY_CAST(prices.tix AS DOUBLE)                               AS tix
        FROM {source}
    """)


def refresh(force: bool = False, max_age_hours: float = 24) -> str:
    if not force and not is_stale(max_age_hours):
        return "card data is current"
    path, info = download()
    rows = load(path)
    meta_path().write_text(json.dumps({
        "updated_at": info.get("updated_at"),
        "loaded_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    }))
    return f"loaded {rows:,} printings (Scryfall {info.get('updated_at', '?')})"
