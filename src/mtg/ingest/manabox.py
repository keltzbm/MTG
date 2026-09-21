"""ManaBox collection export.

Gotchas that cost time before, encoded here so they cost it once:
  * The file carries a UTF-8 BOM. Read with encoding="utf-8-sig".
  * Compare names with .strip().lower() on both sides.
  * One row per printing; sum Quantity across rows for a card total.
  * Precon contents are NOT in this export. See ingest/precon.py.
"""

from pathlib import Path

from mtg.models import CollectionEntry

ENCODING = "utf-8-sig"


def load(csv_path: Path) -> list[CollectionEntry]:
    """Parse a ManaBox export, resolving each row to a printing."""
    raise NotImplementedError
