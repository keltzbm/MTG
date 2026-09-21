"""Scryfall bulk data.

The default-cards bulk file is published daily and carries oracle text, types,
color identity, legalities, and prices. It replaces both the old scraper and
most of the old price module. No rate limits, no HTML parsing.
"""

from pathlib import Path

from mtg.models import Card

BULK_INDEX = "https://api.scryfall.com/bulk-data"


def download_bulk(dest: Path, kind: str = "default_cards", force: bool = False) -> Path:
    """Fetch the bulk file if the cached copy is stale."""
    raise NotImplementedError


def load_cards(bulk_path: Path) -> list[Card]:
    """Parse bulk JSON into Cards, grouping printings under oracle_id."""
    raise NotImplementedError
