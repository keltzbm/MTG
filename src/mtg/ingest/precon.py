"""Sealed precon contents, kept as text lists in the repo's precons/ folder.

A precon still in its box isn't in the ManaBox export, which is how 30
owned cards once read as "need to buy". List the ones you own in config.
"""

from pathlib import Path

from mtg.ingest.decklist import parse_text
from mtg.models import Holding


def load(name: str, precon_dir: Path) -> list[Holding]:
    path = precon_dir / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"no precon list {path}")
    deck = parse_text(path.read_text(encoding="utf-8"), slug=name)
    return [Holding(name=e.name, quantity=e.quantity, source=f"precon:{name}") for e in deck.entries]


def available(precon_dir: Path) -> list[str]:
    return sorted(p.stem for p in precon_dir.glob("*.txt"))
