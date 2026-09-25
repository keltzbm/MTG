"""Riffle's own IDs for cards, printings, and sets, derived from their creating source's IDs.

Each gets a UUIDv5: a hash of a fixed namespace and a seed, "<source>:<id>"
(scryfall_oracle:<oracle id> for a Magic card, scryfall:<id> for a printing,
scryfall_set:<id> for a set). The same seed gives the same UUID on every
machine, forever, so loading the sources into an empty database reproduces
every ID. The source only seeds an ID; the ID is ours, and outlives the source.

Exactly one source per game creates catalog rows (CREATORS); every other source
maps its IDs onto rows that exist, through external_ids.

aliases.toml, beside this file, covers the rare upstream rename (Scryfall
occasionally gives a card a new oracle id): it maps the new ID to the one the
row was first derived from, so the row keeps its UUID. Derivation always
applies it, so the database stays equal to a rebuild from the sources: an alias
added after the renamed ID was first loaded moves that ID's rows back on the
next load, and the row derived from the new ID is retired.

Only the catalog loader derives IDs. Everything else looks them up in
external_ids, which also holds the IDs other sources use.
"""

import tomllib
import uuid
from collections.abc import Mapping
from dataclasses import astuple, dataclass
from pathlib import Path

# uuid5(NAMESPACE_URL, "https://github.com/keltzbm/riffle"). Fixed forever: changing it changes every ID.
NAMESPACE = uuid.UUID("342dbddf-684c-583b-ac93-fd7c00cca17c")

ALIASES_FILE = Path(__file__).with_name("aliases.toml")

Aliases = Mapping[str, Mapping[str, str]]  # source -> {renamed ID: the ID the row was first derived from}


@dataclass(frozen=True)
class Creators:
    """The sources whose IDs seed one game's cards, printings, and sets."""

    card: str
    printing: str
    set: str


CREATORS: dict[str, Creators] = {
    "mtg": Creators(card="scryfall_oracle", printing="scryfall", set="scryfall_set"),
}


def creating_sources() -> set[str]:
    return {source for creators in CREATORS.values() for source in astuple(creators)}


def seed(source: str, external_id: str, aliases: Aliases | None = None) -> str:
    """What an ID is derived from: "<source>:<id>", after any alias."""
    first = (aliases or {}).get(source, {}).get(external_id, external_id)
    return f"{source}:{first}"


def derive(source: str, external_id: str, aliases: Aliases | None = None) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, seed(source, external_id, aliases))


def load_aliases(path: Path = ALIASES_FILE) -> dict[str, dict[str, str]]:
    """The alias tables, checked: known creating sources, string IDs, and no chains (an alias
    points at the ID the row was first derived from, never at another alias)."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    known = creating_sources()
    for source, table in raw.items():
        if source not in known:
            raise ValueError(f"{path.name}: [{source}] isn't a creating source ({', '.join(sorted(known))})")
        if not isinstance(table, dict) or not all(isinstance(v, str) for v in table.values()):
            raise ValueError(f"{path.name}: [{source}] must map IDs to IDs, both quoted")
        chained = sorted(new for new, first in table.items() if first in table)
        if chained:
            raise ValueError(
                f"{path.name}: [{source}] {', '.join(chained)} point at other aliases; "
                "point them at the first ID instead"
            )
    return raw
