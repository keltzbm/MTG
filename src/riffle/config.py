"""Settings from $XDG_CONFIG_HOME/riffle/config.toml, with sensible defaults.

    vault = "~/atelier/library"

What you own comes from the ManaBox export alone: scan a precon into ManaBox
to count it.
"""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

OBSOLETE_KEYS = {
    "precons": "sealed precons are no longer counted; scan them into ManaBox and delete this line",
}


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


def config_path() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "riffle" / "config.toml"


def data_dir() -> Path:
    """Bulk data, the DuckDB file, the collection CSV and sync state.

    Never inside ~/atelier: that tree is synced.
    """
    return _xdg("XDG_DATA_HOME", ".local/share") / "riffle"


DEFAULT_CONFIG = """\
# riffle configuration
vault = "~/atelier/library"
"""


@dataclass
class Config:
    vault: Path
    obsolete: dict[str, str] | None = None  # key -> why it's ignored

    @property
    def mtg_dir(self) -> Path:
        return self.vault / "tcg" / "mtg"

    @property
    def collection_csv(self) -> Path:
        return data_dir() / "collection.csv"

    @property
    def arena_list(self) -> Path:
        return data_dir() / "arena-collection.txt"

    @property
    def downloads(self) -> Path:
        return Path.home() / "Downloads"


def load() -> Config:
    path = config_path()
    raw = tomllib.loads(path.read_text()) if path.exists() else tomllib.loads(DEFAULT_CONFIG)
    return Config(
        vault=Path(raw.get("vault", "~/atelier/library")).expanduser(),
        obsolete={k: why for k, why in OBSOLETE_KEYS.items() if k in raw} or None,
    )


def write_default() -> Path:
    path = config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG)
    return path
