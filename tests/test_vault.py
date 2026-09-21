from mtg import vault

NOTE = """---
game: mtg
format: commander
colors: [U, G]
aliases: [Aesi Lands, Tricky Terrain]   # comment
commander: Aesi, Tyrant of Gyre Strait
tags:
  - mtg
---

# Aesi Lands

```
not a decklist
```

## Moxfield import

```
Commander
1 Aesi, Tyrant of Gyre Strait

Deck
1 Sol Ring
2 Forest
```

- [ ] 🟢 **[[Sol Ring]]** · ~$1 #mtg/buy
- [x] 🟢 **[[Cyclonic Rift]]** · ~$30 #mtg/buy
- [ ] 🟢 **[[buy-list|Buy List]]** is not a card
"""


def test_frontmatter_subset():
    fm = vault.frontmatter(NOTE)
    assert fm["colors"] == ["U", "G"]
    assert fm["aliases"] == ["Aesi Lands", "Tricky Terrain"]
    assert fm["commander"] == "Aesi, Tyrant of Gyre Strait"
    assert fm["tags"] == ["mtg"]


def test_reads_the_import_block_not_the_first_block(tmp_path):
    p = tmp_path / "tcg" / "mtg" / "commander" / "aesi-lands.md"
    p.parent.mkdir(parents=True)
    p.write_text(NOTE)
    d = vault.find(tmp_path / "tcg" / "mtg", "aesi-lands")
    assert d.count() == 4
    assert d.board("commander")[0].name == "Aesi, Tyrant of Gyre Strait"


def test_generated_and_archetype_notes_are_not_decks(tmp_path):
    mtg = tmp_path / "tcg" / "mtg"
    for sub in ("_generated", "archetypes", "commander"):
        (mtg / sub).mkdir(parents=True)
        (mtg / sub / "x.md").write_text(NOTE)
    assert [d.meta["path"].split("/")[-2] for d in vault.decks(mtg)] == ["commander"]


def test_buy_cards_only_unticked_and_only_tagged(tmp_path):
    (tmp_path / "a.md").write_text(NOTE)
    assert vault.buy_cards(tmp_path) == ["Sol Ring"]


def test_stub_with_empty_list_is_not_a_deck(tmp_path):
    p = tmp_path / "stub.md"
    p.write_text("---\ngame: mtg\n---\n\n## Moxfield import\n\n```\n\n```\n")
    assert vault.read_deck(p) is None
