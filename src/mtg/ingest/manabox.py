"""ManaBox collection export (CSV).

Encoded here so they cost time once:
  * UTF-8 with a BOM — read with utf-8-sig.
  * One row per printing; the same card appears on several rows.
  * Scryfall ID is the best key when present; set code + collector number
    next; the name is the last resort.
"""

import csv
from pathlib import Path

from mtg.models import Holding


def _get(row: dict, *keys: str) -> str:
    for k in keys:
        if row.get(k):
            return row[k].strip()
    return ""


def load(path: Path) -> list[Holding]:
    out = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = _get(row, "Name", "name")
            if not name:
                continue
            qty = int(_get(row, "Quantity", "quantity", "Count") or 1)
            out.append(Holding(
                name=name,
                quantity=qty,
                scryfall_id=_get(row, "Scryfall ID", "scryfall_id") or None,
                set_code=(_get(row, "Set code", "Set Code", "set_code").upper() or None),
                collector_number=_get(row, "Collector number", "Collector Number") or None,
                foil=_get(row, "Foil", "foil").lower() in {"foil", "etched", "true", "yes"},
            ))
    return out


def newest_export(folder: Path) -> Path | None:
    """Most recent ManaBox export in a folder (ManaBox names them ManaBox_*.csv)."""
    found = sorted(folder.glob("ManaBox*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0] if found else None
