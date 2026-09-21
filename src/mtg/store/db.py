"""DuckDB-backed Catalog over the Scryfall default-cards bulk file.

Everything a sync needs is loaded into dicts on first use (~30k cards),
so a sync is one pass over the store rather than thousands of queries.
"""

from functools import cached_property
from pathlib import Path

import duckdb

from mtg.config import data_dir
from mtg.models import Prices, Printing

BASICS = {"plains", "island", "swamp", "mountain", "forest", "wastes"}


def db_path() -> Path:
    return data_dir() / "mtg.duckdb"


def connect(path: Path | None = None, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    path = path or db_path()
    if read_only and not path.exists():
        raise FileNotFoundError("no card data yet — run: mtg ingest scryfall")
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


class DuckCatalog:
    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con

    @cached_property
    def _names(self) -> dict[str, str]:
        rows = self.con.execute(
            "SELECT DISTINCT name_lc, front_lc, oracle_id FROM printings WHERE oracle_id IS NOT NULL"
        ).fetchall()
        out: dict[str, str] = {}
        for full, front, oid in rows:
            out.setdefault(full, oid)
            out.setdefault(front, oid)
        return out

    @cached_property
    def _cards(self) -> dict[str, tuple[str, str, float | None, float | None]]:
        rows = self.con.execute("""
            SELECT oracle_id,
                   arg_min(name, released_at)                         AS name,
                   arg_min(layout, released_at)                       AS layout,
                   min(usd) FILTER (WHERE NOT coalesce(digital, false)) AS usd,
                   min(tix)                                           AS tix
            FROM printings
            WHERE oracle_id IS NOT NULL
            GROUP BY oracle_id
        """).fetchall()
        return {r[0]: (r[1], r[2], r[3], r[4]) for r in rows}

    def resolve(self, name: str) -> str | None:
        key = name.strip().lower()
        return self._names.get(key) or self._names.get(key.split(" // ")[0])

    def name(self, oracle_id: str) -> str:
        return self._cards.get(oracle_id, (oracle_id,))[0]

    def prices(self, oracle_id: str) -> Prices:
        c = self._cards.get(oracle_id)
        return Prices(usd=c[2], tix=c[3]) if c else Prices()

    def mtgo_name(self, oracle_id: str) -> str:
        name, layout = self._cards.get(oracle_id, (oracle_id, ""))[:2]
        if " // " in name:
            return name.replace(" // ", "/") if layout in {"split", "aftermath"} else name.split(" // ")[0]
        return name

    def is_basic(self, oracle_id: str) -> bool:
        return self.name(oracle_id).lower() in BASICS

    def _printing(self, where: str, args: list) -> Printing | None:
        row = self.con.execute(
            f"SELECT scryfall_id, oracle_id, name, set_code, collector_number, frame, border_color "
            f"FROM printings WHERE {where} LIMIT 1", args
        ).fetchone()
        return Printing(*row) if row else None

    def printing(self, scryfall_id: str) -> Printing | None:
        return self._printing("scryfall_id = ?", [scryfall_id])

    def printing_at(self, set_code: str, collector_number: str) -> Printing | None:
        return self._printing("set_code = lower(?) AND collector_number = ?", [set_code, collector_number])

    def printing_usd(self, scryfall_id: str) -> float | None:
        row = self.con.execute("SELECT usd FROM printings WHERE scryfall_id = ?", [scryfall_id]).fetchone()
        return row[0] if row else None
