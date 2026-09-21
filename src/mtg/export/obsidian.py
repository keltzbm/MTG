"""Obsidian export.

Contract (DESIGN.md): this module may write inside `_generated/` and append to
`_log/`. The single exception is creating a new deck-note stub with correct
frontmatter when a deck first appears; after creation, hands off.
"""

from pathlib import Path

from mtg.models import Deck

GENERATED = "_generated"
LOG = "_log"


def write_deck_data(deck: Deck, vault: Path, con) -> Path:
    """Write tcg/mtg/_generated/<slug>.data.md — ownership marks, counts, buy total."""
    raise NotImplementedError


def write_collection_summary(vault: Path, con) -> Path:
    raise NotImplementedError


def append_price_snapshot(vault: Path, rows: list) -> None:
    """Append to _log/prices.md. Never rewrite."""
    raise NotImplementedError


def append_ownership_event(vault: Path, event: str, line: str) -> None:
    """Append to _log/ownership.md. Never rewrite."""
    raise NotImplementedError


def stub_deck_note(deck: Deck, vault: Path) -> Path | None:
    """Create an authored-zone note ONLY if it does not exist. Never overwrite."""
    raise NotImplementedError


def slug(name: str) -> str:
    """Lowercase kebab-case, matching library/: "Y'shtola Spellslinger" -> "yshtola-spellslinger"."""
    raise NotImplementedError
