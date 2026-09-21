"""Connection, schema bootstrap, and upserts.

The store lives outside ~/atelier entirely. A multi-hundred-MB bulk cache and a
DuckDB file being written mid-query do not belong anywhere a sync client can see.
"""

import os
from pathlib import Path

import duckdb


def data_dir() -> Path:
    """$XDG_DATA_HOME/mtg, default ~/.local/share/mtg. Never inside the vault."""
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "mtg"


DEFAULT_PATH = data_dir() / "mtg.duckdb"


def connect(path: Path = DEFAULT_PATH) -> duckdb.DuckDBPyConnection:
    """Open the store, creating the schema if absent."""
    raise NotImplementedError


def upsert_cards(con: duckdb.DuckDBPyConnection, cards: list) -> int:
    raise NotImplementedError


def upsert_collection(con: duckdb.DuckDBPyConnection, entries: list) -> int:
    raise NotImplementedError
