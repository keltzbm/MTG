"""DuckCatalog against a tiny in-memory printings table — the real SQL, no download.

This layer is where the "newest printing decides legality" bug lived; the
first test here reproduces it.
"""

import json

import duckdb
import pytest

from riffle.store.db import DuckCatalog

SCHEMA = """
CREATE TABLE printings (
    scryfall_id VARCHAR, oracle_id VARCHAR, name VARCHAR, name_lc VARCHAR, front_lc VARCHAR,
    set_code VARCHAR, collector_number VARCHAR, layout VARCHAR, frame VARCHAR, border_color VARCHAR,
    digital BOOLEAN, released_at DATE, rarity VARCHAR, games VARCHAR[], type_line VARCHAR,
    color_identity VARCHAR[], legalities JSON, oracle_text VARCHAR, card_faces JSON,
    usd DOUBLE, tix DOUBLE
)"""

LEGAL = {"commander": "legal", "modern": "not_legal", "legacy": "legal", "vintage": "legal"}
NOWHERE = {k: "not_legal" for k in LEGAL}


def _row(
    sid,
    oid,
    name,
    set_code,
    released,
    *,
    layout="normal",
    type_line="Enchantment",
    ci=("G",),
    legal=LEGAL,
    text="text",
    faces=None,
    usd=1.0,
    tix=0.1,
    digital=False,
    rarity="rare",
):
    front = name.split(" // ")[0]
    return (
        sid,
        oid,
        name,
        name.lower(),
        front.lower(),
        set_code,
        "1",
        layout,
        "2015",
        "black",
        digital,
        released,
        rarity,
        ["paper", "mtgo"],
        type_line,
        list(ci),
        json.dumps(legal),
        text,
        json.dumps(faces) if faces is not None else None,
        usd,
        tix,
    )


ROWS = [
    # the bug: a newer non-tournament printing (gold border, not_legal everywhere)
    _row("s1", "o-lib", "Sylvan Library", "ema", "2016-06-10"),
    _row("s2", "o-lib", "Sylvan Library", "wc26", "2026-08-01", legal=NOWHERE, usd=None),
    # a Secret Lair reversible folded onto the real card (newer, doubled type line)
    _row("s3", "o-sol", "Sol Ring", "c21", "2021-04-23", type_line="Artifact", ci=()),
    _row(
        "s4",
        "o-sol",
        "Sol Ring",
        "sld",
        "2026-01-01",
        layout="reversible_card",
        type_line="Artifact // Artifact",
        ci=(),
    ),
    # a split card and an MDFC whose text lives only on the faces
    _row(
        "s5",
        "o-fire",
        "Fire // Ice",
        "mh2",
        "2021-06-18",
        layout="split",
        type_line="Instant // Instant",
        ci=("U", "R"),
    ),
    _row(
        "s6",
        "o-mdfc",
        "Valakut Awakening // Valakut Stoneforge",
        "znr",
        "2020-09-25",
        layout="modal_dfc",
        type_line="Instant // Land",
        ci=("R",),
        text=None,
        faces=[{"oracle_text": "Put any number of cards"}, {"oracle_text": "{T}: Add {R}."}],
    ),
    # banned somewhere on one printing only
    _row("s7", "o-crypt", "Mana Crypt", "2xm", "2020-08-07", legal={**LEGAL, "commander": "banned"}),
    _row("s8", "o-crypt", "Mana Crypt", "sld", "2025-01-01"),
]


@pytest.fixture
def catalog():
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA)
    con.executemany(f"INSERT INTO printings VALUES ({', '.join(['?'] * 21)})", ROWS)
    yield DuckCatalog(con)
    con.close()


def test_odd_newer_printing_cannot_hide_legality(catalog):
    r = catalog.rules("o-lib")
    assert r.legalities["commander"] == "legal" and r.legalities["legacy"] == "legal"


def test_banned_on_any_printing_wins(catalog):
    assert catalog.rules("o-crypt").legalities["commander"] == "banned"


def test_reversible_never_supplies_the_type_line(catalog):
    assert catalog.rules("o-sol").type_line == "Artifact"


def test_mdfc_text_comes_from_faces(catalog):
    text = catalog.rules("o-mdfc").oracle_text
    assert "Put any number of cards" in text and "{T}: Add {R}." in text


def test_color_identity_is_a_tuple(catalog):
    assert catalog.rules("o-fire").color_identity == ("U", "R")
    assert catalog.rules("o-sol").color_identity == ()


@pytest.mark.parametrize(
    "name, oid",
    [
        ("Fire // Ice", "o-fire"),
        ("fire // ice", "o-fire"),
        ("Fire/Ice", "o-fire"),
        ("Fire", "o-fire"),
        ("  Sylvan Library ", "o-lib"),
        ("Valakut Awakening", "o-mdfc"),
        ("Not A Card", None),
    ],
)
def test_resolve(catalog, name, oid):
    assert catalog.resolve(name) == oid


def test_unknown_card_has_no_rules(catalog):
    assert catalog.rules("o-nope") is None


def test_card_data_from_before_oracle_text_gives_no_rules():
    """An old mtg.duckdb without the new columns: rules() is None, not a crash."""
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA.replace("oracle_text VARCHAR, card_faces JSON,", ""))
    assert DuckCatalog(con).rules("o-lib") is None
    con.close()


def test_printing_lookups(catalog):
    p = catalog.printing("s3")
    assert (p.oracle_id, p.name, p.set_code, p.collector_number) == ("o-sol", "Sol Ring", "c21", "1")
    assert catalog.printing_at("C21", "1").scryfall_id == "s3"  # ManaBox writes set codes uppercase
    assert catalog.printing_usd("s1") == 1.0
    assert catalog.printing_usd("s2") is None  # printing exists, no paper price


def test_unknown_printings_are_none(catalog):
    assert catalog.printing("nope") is None
    assert catalog.printing_at("zzz", "1") is None
    assert catalog.printing_usd("nope") is None
