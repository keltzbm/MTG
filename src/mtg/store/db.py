"""DuckDB-backed Catalog over the Scryfall default-cards bulk file.

Everything a sync needs is loaded into dicts on first use (~30k cards),
so a sync is one pass over the store rather than thousands of queries.
"""

import json
from functools import cached_property
from pathlib import Path

import duckdb

from mtg.config import data_dir
from mtg.models import CardRules, Prices, Printing, merge_legalities

BASICS = {"plains", "island", "swamp", "mountain", "forest", "wastes"}


def db_path() -> Path:
    return data_dir() / "mtg.duckdb"


def connect(path: Path | None = None, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    path = path or db_path()
    if read_only and not path.exists():
        raise FileNotFoundError("no card data yet — run: mtg ingest scryfall")
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def _json(v):
    """JSON columns come back as text; inferred-schema columns as Python objects."""
    return json.loads(v) if isinstance(v, str) else v


class DuckCatalog:
    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con

    @cached_property
    def _names(self) -> tuple[dict[str, str], dict[str, str]]:
        """(exact full names, front faces) -> oracle_id. Where two cards share
        a name, the one with more printings wins — never a reprint oddity."""
        rows = self.con.execute("""
            SELECT name_lc, front_lc, oracle_id, count(*) AS n
            FROM printings WHERE oracle_id IS NOT NULL
            GROUP BY name_lc, front_lc, oracle_id
            ORDER BY n DESC
        """).fetchall()
        exact: dict[str, str] = {}
        front: dict[str, str] = {}
        for full, fr, oid, _ in rows:
            exact.setdefault(full, oid)
            front.setdefault(fr, oid)
        return exact, front

    @cached_property
    def _cards(self) -> dict[str, tuple[str, str, float | None, float | None]]:
        rows = self.con.execute("""
            SELECT oracle_id,
                   arg_min(name, length(name))                        AS name,
                   arg_min(layout, released_at)                       AS layout,
                   min(usd) FILTER (WHERE NOT coalesce(digital, false)) AS usd,
                   min(tix)                                           AS tix
            FROM printings
            WHERE oracle_id IS NOT NULL
            GROUP BY oracle_id
        """).fetchall()
        return {r[0]: (r[1], r[2], r[3], r[4]) for r in rows}

    @cached_property
    def _arena(self) -> dict[str, str]:
        order = "CASE rarity WHEN 'common' THEN 0 WHEN 'uncommon' THEN 1 WHEN 'rare' THEN 2 ELSE 3 END"
        try:
            rows = self.con.execute(f"""
                SELECT oracle_id, arg_min(rarity, {order})
                FROM printings
                WHERE oracle_id IS NOT NULL AND list_contains(games, 'arena')
                GROUP BY oracle_id
            """).fetchall()
        except Exception:
            return {}  # card data loaded before rarity was stored — re-run ingest
        return dict(rows)

    @cached_property
    def _rules(self) -> dict[str, CardRules]:
        """Legalities merged across every printing (see merge_legalities). For the
        rest, the newest printing wins, but never a Secret Lair reversible (its
        type line and faces are doubled)."""
        key = (
            "coalesce(date_diff('day', DATE '1990-01-01', released_at), 0)"
            " + CASE WHEN layout = 'reversible_card' THEN 0 ELSE 1000000 END"
        )
        try:
            legal_rows = self.con.execute("""
                SELECT DISTINCT oracle_id, CAST(to_json(legalities) AS VARCHAR)
                FROM printings WHERE oracle_id IS NOT NULL
            """).fetchall()
            rows = self.con.execute(f"""
                SELECT oracle_id,
                       arg_max(color_identity, {key}),
                       arg_max(type_line, {key}), arg_max(oracle_text, {key}),
                       arg_max(card_faces, {key})
                FROM printings WHERE oracle_id IS NOT NULL
                GROUP BY oracle_id
            """).fetchall()
        except duckdb.Error:
            return {}  # card data loaded before oracle_text was stored — re-run ingest
        by_card: dict[str, list[dict]] = {}
        for oid, legal in legal_rows:
            by_card.setdefault(oid, []).append(_json(legal) or {})
        out = {}
        for oid, ci, type_line, text, faces in rows:
            faces = _json(faces) or []
            if not text:
                text = "\n".join(f.get("oracle_text") or "" for f in faces if isinstance(f, dict))
            out[oid] = CardRules(
                legalities=merge_legalities(by_card.get(oid, [])),
                color_identity=tuple(ci or ()),
                type_line=type_line or "",
                oracle_text=text or "",
            )
        return out

    def rules(self, oracle_id: str) -> CardRules | None:
        return self._rules.get(oracle_id)

    def arena_rarity(self, oracle_id: str) -> str | None:
        r = self._arena.get(oracle_id)
        return "mythic" if r in {"mythic", "special", "bonus"} else r

    def resolve(self, name: str) -> str | None:
        key = name.strip().lower()
        exact, front = self._names
        if key.startswith("a-"):  # Arena rebalanced cards, "A-Name"
            key = key[2:]
        if "/" in key and " // " not in key:  # MTGO writes split cards as "Fire/Ice"
            key = key.replace("/", " // ")
        return exact.get(key) or front.get(key) or front.get(key.split(" // ")[0])

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
            f"FROM printings WHERE {where} LIMIT 1",
            args,
        ).fetchone()
        return Printing(*row) if row else None

    def printing(self, scryfall_id: str) -> Printing | None:
        return self._printing("scryfall_id = ?", [scryfall_id])

    def printing_at(self, set_code: str, collector_number: str) -> Printing | None:
        return self._printing("set_code = lower(?) AND collector_number = ?", [set_code, collector_number])

    def printing_usd(self, scryfall_id: str) -> float | None:
        row = self.con.execute("SELECT usd FROM printings WHERE scryfall_id = ?", [scryfall_id]).fetchone()
        return row[0] if row else None
