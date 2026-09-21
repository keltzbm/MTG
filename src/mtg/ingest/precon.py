"""Precon contents.

Sealed precons are owned but absent from collection exports, which is how 30
owned cards read as "need to buy." Precon lists are stored as flat text files
keyed by set code and loaded as CollectionEntry rows with source="precon".
"""

from pathlib import Path

from mtg.models import CollectionEntry


def load(code: str, lists_dir: Path) -> list[CollectionEntry]:
    """Load a precon list, e.g. M3C-tricky-terrain."""
    raise NotImplementedError
