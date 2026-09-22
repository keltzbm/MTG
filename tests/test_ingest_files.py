"""ManaBox, Arena, precon lists, and config: the files the tool reads."""

import pytest

from mtg import config
from mtg.analysis.resolve import counts, resolve_holdings
from mtg.ingest import arena, manabox, precon
from mtg.models import Holding

MANABOX = (
    "\ufeffName,Set code,Set name,Collector number,Foil,Rarity,Quantity,ManaBox ID,Scryfall ID,Language\n"
    "Sol Ring,m3c,MH3 Commander,283,normal,uncommon,2,1,s-sol-m3c,en\n"
    "Sol Ring,cmr,Commander Legends,472,foil,uncommon,1,2,,en\n"
    "Cyclonic Rift,2x2,Double Masters 2022,45,etched,rare,1,3,,en\n"
    ",,,,,,,,,\n"
    "Forest,m3c,MH3 Commander,300,normal,common,,4,,en\n"
)


def test_manabox_export_shape(tmp_path):
    p = tmp_path / "ManaBox_Collection.csv"
    p.write_text(MANABOX, encoding="utf-8")
    hs = manabox.load(p)
    assert [(h.name, h.quantity, h.set_code, h.collector_number, h.foil) for h in hs] == [
        ("Sol Ring", 2, "M3C", "283", False),
        ("Sol Ring", 1, "CMR", "472", True),
        ("Cyclonic Rift", 1, "2X2", "45", True),
        ("Forest", 1, "M3C", "300", False),      # blank quantity reads as 1
    ]
    assert hs[0].scryfall_id == "s-sol-m3c" and hs[1].scryfall_id is None
    assert all(h.source == "manabox" for h in hs)


def test_manabox_rows_resolve_and_sum_per_card(tmp_path, cat):
    p = tmp_path / "c.csv"
    p.write_text(MANABOX, encoding="utf-8")
    hs = manabox.load(p)
    assert resolve_holdings(hs, cat) == []
    c = counts(hs)
    assert c["o-sol"] == 3 and c["o-rift"] == 1 and c["o-forest"] == 1


def test_unresolved_holdings_are_reported_and_not_counted(cat):
    hs = [Holding("Not A Card", 2), Holding("Sol Ring", 1)]
    assert resolve_holdings(hs, cat) == ["Not A Card"]
    assert dict(counts(hs)) == {"o-sol": 1}


def test_bad_scryfall_id_falls_back_to_set_number_then_name(cat):
    hs = [Holding("x", 1, scryfall_id="nope", set_code="2X2", collector_number="45"),
          Holding("Sol Ring", 1, scryfall_id="nope", set_code="XXX", collector_number="1")]
    assert resolve_holdings(hs, cat) == []
    assert [h.oracle_id for h in hs] == ["o-rift", "o-sol"]


@pytest.mark.parametrize("header, row", [
    ("Name,Count", "Sol Ring,4"),
    ("name,quantity", "Sol Ring,4"),
    ("Card Name,Qty", "Sol Ring,4"),
    (" Card , Owned ", "Sol Ring,4"),
])
def test_arena_csv_column_names(tmp_path, header, row):
    p = tmp_path / "a.csv"
    p.write_text(f"{header}\n{row}\n")
    assert [(h.name, h.quantity) for h in arena.load(p)] == [("Sol Ring", 4)]


def test_arena_csv_skips_bad_counts_zero_counts_and_blank_names(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("Name,Count\nSol Ring,4\n,3\nCyclonic Rift,x\nForest,\nIsland,0\n")
    assert [(h.name, h.quantity) for h in arena.load(p)] == [("Sol Ring", 4)]


def test_arena_csv_without_usable_columns_is_an_error(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("Card,Set\nSol Ring,CMR\n")
    with pytest.raises(ValueError, match="expected columns"):
        arena.load(p)


def test_precon_lists_and_missing_precons(tmp_path):
    (tmp_path / "M3C-tricky-terrain.txt").write_text("Commander\n1 Omo, Queen of Vesuva\n\nDeck\n1 Sol Ring\n")
    hs = precon.load("M3C-tricky-terrain", tmp_path)
    assert [(h.name, h.source) for h in hs] == [
        ("Omo, Queen of Vesuva", "precon:M3C-tricky-terrain"), ("Sol Ring", "precon:M3C-tricky-terrain")]
    assert precon.available(tmp_path) == ["M3C-tricky-terrain"]
    with pytest.raises(FileNotFoundError):
        precon.load("nope", tmp_path)


def test_repo_precon_files_parse_to_full_decks():
    """The lists shipped in precons/ must parse to 100 cards with a commander."""
    names = precon.available(config.REPO_ROOT / "precons")
    assert names, "no precon lists found"
    for name in names:
        hs = precon.load(name, config.REPO_ROOT / "precons")
        assert sum(h.quantity for h in hs) == 100, name


def test_config_defaults_and_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    cfg = config.load()
    assert cfg.precons == [] and cfg.vault.name == "library"
    assert config.data_dir() == tmp_path / "data" / "mtg"
    assert cfg.mtg_dir == cfg.vault / "tcg" / "mtg"
    assert cfg.collection_csv == tmp_path / "data" / "mtg" / "collection.csv"


def test_config_file_is_read_and_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = config.write_default()
    path.write_text('vault = "~/elsewhere"\nprecons = ["M3C-tricky-terrain"]\n')
    assert config.write_default() == path
    cfg = config.load()
    assert cfg.precons == ["M3C-tricky-terrain"]
    assert "~" not in str(cfg.vault) and cfg.vault.name == "elsewhere"
