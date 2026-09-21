"""Settings from $XDG_CONFIG_HOME/mtg/config.toml, with sensible defaults.

    vault   = "~/atelier/library"
    precons = ["M3C-tricky-terrain", "FIC-scions-spellcraft"]

Precons listed here are sealed boxes you own whose cards are NOT in the
ManaBox export. Anything already scanned into ManaBox should not be listed.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


def config_path() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "mtg" / "config.toml"


def data_dir() -> Path:
    """Bulk data, the DuckDB file, the collection CSV and sync state.

    Never inside ~/atelier: that tree is synced.
    """
    return _xdg("XDG_DATA_HOME", ".local/share") / "mtg"


DEFAULT_CONFIG = """\
# mtg configuration
vault = "~/atelier/library"

# Sealed precons you own whose cards aren't in your ManaBox export.
# Names match files in the repo's precons/ folder.
precons = ["M3C-tricky-terrain", "FIC-scions-spellcraft"]
"""


@dataclass
class Config:
    vault: Path
    precons: list[str] = field(default_factory=list)

    @property
    def mtg_dir(self) -> Path:
        return self.vault / "tcg" / "mtg"

    @property
    def collection_csv(self) -> Path:
        return data_dir() / "collection.csv"

    @property
    def precon_dir(self) -> Path:
        return REPO_ROOT / "precons"


def load() -> Config:
    path = config_path()
    raw = tomllib.loads(path.read_text()) if path.exists() else tomllib.loads(DEFAULT_CONFIG)
    return Config(
        vault=Path(raw.get("vault", "~/atelier/library")).expanduser(),
        precons=list(raw.get("precons", [])),
    )


def write_default() -> Path:
    path = config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG)
    return path
