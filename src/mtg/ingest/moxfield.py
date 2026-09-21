"""Moxfield decklists in, mass-entry text out.

Moxfield stays the source of truth for decklists. Import resolves each line to
an oracle_id; export writes plain "1 Card Name" lines with an optional set code
when a specific printing matters.
"""

from pathlib import Path

from mtg.models import Deck


def parse(text: str, name: str, format: str) -> Deck:
    """Parse a Moxfield / Archidekt style list."""
    raise NotImplementedError


def to_import_block(deck: Deck, pin_printings: bool = False) -> str:
    """Render a paste-ready import block, optionally pinning set codes."""
    raise NotImplementedError


def load(path: Path, name: str, format: str) -> Deck:
    raise NotImplementedError
