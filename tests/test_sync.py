
from mtg import sync

NOTE = """---
game: mtg
format: commander
---

## Moxfield import

```
Commander
1 Aesi, Tyrant of Gyre Strait

Deck
1 Sol Ring
1 Cyclonic Rift
```

- [ ] 🟢 **[[Cyclonic Rift]]** · ~$30 #mtg/buy
"""


def _vault(tmp_path):
    mtg = tmp_path / "library" / "tcg" / "mtg"
    (mtg / "commander").mkdir(parents=True)
    (mtg / "commander" / "aesi-lands.md").write_text(NOTE)
    return mtg


def test_sync_writes_only_machine_zones(tmp_path, cat, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    mtg = _vault(tmp_path)
    before = (mtg / "commander" / "aesi-lands.md").read_text()
    inv = sync.Inventory([])
    res = sync.run(mtg, inv, cat, today="2026-09-21")

    assert res.decks == ["aesi-lands"]
    assert (mtg / "commander" / "aesi-lands.md").read_text() == before
    written = {p.relative_to(mtg).parts[0] for p in mtg.rglob("*") if p.is_file()}
    assert written == {"commander", "_generated", "_log"}
    data = (mtg / "_generated" / "aesi-lands-data.md").read_text()
    assert "3 cards" in data and "[[Cyclonic Rift]]" in data


def test_price_log_is_append_only_once_per_day(tmp_path, cat, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    mtg = _vault(tmp_path)
    inv = sync.Inventory([])
    assert sync.run(mtg, inv, cat, today="2026-09-21").prices_logged == 1
    assert sync.run(mtg, inv, cat, today="2026-09-21").prices_logged == 0
    assert sync.run(mtg, inv, cat, today="2026-09-22").prices_logged == 1
    log = (mtg / "_log" / "prices.md").read_text()
    assert "2026-09-21 | Cyclonic Rift | $30.00 | 2.00" in log
    assert "2026-09-22 | Cyclonic Rift" in log


def test_versions_log_records_changes_only(tmp_path, cat, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    mtg = _vault(tmp_path)
    inv = sync.Inventory([])
    assert sync.run(mtg, inv, cat, today="2026-09-21").versions == ["aesi-lands"]
    assert sync.run(mtg, inv, cat, today="2026-09-21").versions == []
    note = mtg / "commander" / "aesi-lands.md"
    note.write_text(note.read_text().replace("1 Sol Ring\n", "1 Fire // Ice\n"))
    assert sync.run(mtg, inv, cat, today="2026-09-22").versions == ["aesi-lands"]
    log = (mtg / "_log" / "aesi-lands-versions.md").read_text()
    assert "\\+ 1 [[Fire // Ice]]" in log and "\\- 1 [[Sol Ring]]" in log


def test_generated_note_not_rewritten_when_unchanged(tmp_path, cat, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    mtg = _vault(tmp_path)
    inv = sync.Inventory([])
    first = sync.run(mtg, inv, cat, today="2026-09-21").changed_notes
    assert first == 2
    assert sync.run(mtg, inv, cat, today="2026-09-21").changed_notes == 0


def test_generated_note_carries_import_blocks_and_stale_notes_are_pruned(tmp_path, cat, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    mtg = _vault(tmp_path)
    gen = mtg / "_generated"
    gen.mkdir(parents=True)
    (gen / "aesi-lands.data.md").write_text("old name")
    res = sync.run(mtg, sync.Inventory([]), cat, today="2026-09-21")
    assert res.removed == ["aesi-lands.data.md"]
    data = (gen / "aesi-lands-data.md").read_text()
    assert "## Moxfield import" in data and "## MTGO import" in data
    assert "| 🟥 1 | [[Cyclonic Rift]] |" in data


def test_old_dotted_versions_log_is_renamed_not_lost(tmp_path, cat, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    mtg = _vault(tmp_path)
    (mtg / "_log").mkdir(parents=True)
    (mtg / "_log" / "aesi-lands.versions.md").write_text("history\n")
    sync.run(mtg, sync.Inventory([]), cat, today="2026-09-21")
    assert (mtg / "_log" / "aesi-lands-versions.md").read_text().startswith("history")
    assert not (mtg / "_log" / "aesi-lands.versions.md").exists()


def test_rename_happens_even_when_the_list_is_unchanged(tmp_path, cat, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    mtg = _vault(tmp_path)
    sync.run(mtg, sync.Inventory([]), cat, today="2026-09-21")
    new = mtg / "_log" / "aesi-lands-versions.md"
    new.rename(mtg / "_log" / "aesi-lands.versions.md")
    sync.run(mtg, sync.Inventory([]), cat, today="2026-09-21")
    assert new.exists()
