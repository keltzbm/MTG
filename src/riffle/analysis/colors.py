"""Color naming and ordering.

Ported wholesale from the old classes.py colorArchetypes dict, re-keyed to
WUBRG order. The old sorted() produced BGU; every external source says UBG.
"""

from riffle import WUBRG

COLOR_ARCHETYPES: dict[tuple[str, ...], str] = {
    ("W",): "Mono White",
    ("U",): "Mono Blue",
    ("B",): "Mono Black",
    ("R",): "Mono Red",
    ("G",): "Mono Green",
    ("W", "U"): "Azorius",
    ("U", "B"): "Dimir",
    ("B", "R"): "Rakdos",
    ("R", "G"): "Gruul",
    ("W", "G"): "Selesnya",
    ("W", "B"): "Orzhov",
    ("U", "R"): "Izzet",
    ("B", "G"): "Golgari",
    ("W", "R"): "Boros",
    ("U", "G"): "Simic",
    ("W", "U", "B"): "Esper",
    ("U", "B", "R"): "Grixis",
    ("B", "R", "G"): "Jund",
    ("W", "R", "G"): "Naya",
    ("W", "U", "G"): "Bant",
    ("W", "B", "G"): "Abzan",
    ("W", "U", "R"): "Jeskai",
    ("U", "B", "G"): "Sultai",
    ("W", "B", "R"): "Mardu",
    ("U", "R", "G"): "Temur",
    ("W", "U", "B", "R"): "Yore",
    ("U", "B", "R", "G"): "Glint",
    ("W", "B", "R", "G"): "Dune",
    ("W", "U", "R", "G"): "Ink",
    ("W", "U", "B", "G"): "Witch",
    ("W", "U", "B", "R", "G"): "Five-Color",
}


def wubrg_sort(colors: list[str]) -> list[str]:
    """Canonical order. Never use sorted()."""
    return [c for c in WUBRG if c in colors]


def archetype_name(colors: list[str]) -> str:
    """Guild / shard / wedge name for a color set."""
    key = tuple(wubrg_sort(colors))
    return COLOR_ARCHETYPES.get(key, "Colorless" if not key else "/".join(key))
