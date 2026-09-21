# mtg

What I own, what I'm building, what the gap costs — in paper and on MTGO —
rendered into my Obsidian vault. Design: [DESIGN.md](DESIGN.md).

## Install

```bash
cd ~/atelier/github/mtg
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
mtg init
```

## First run

```bash
mtg ingest scryfall                          # ~500 MB download, once a day at most
mtg ingest manabox ~/Downloads/collection.csv
mtg sync --offline
```

## Everyday

```bash
mtg sync                        # refresh prices, rewrite _generated/, append _log/
mtg decks                       # deck notes the vault holds
mtg own aesi-lands              # what's missing
mtg own aesi-lands --all        # every card, with 🟩🟦🟥
mtg price yshtola-spellslinger --budget-tix 500
mtg export aesi-lands --to moxfield --pin owned -o ~/Downloads/aesi.txt
mtg export izzet-murktide --to mtgo -o ~/Downloads/murktide.txt
mtg export aesi-lands --to tcgplayer        # mass-entry list of the shortfall
```

A deck is named by its note's slug, or by a path to any `.md` or `.txt` list.

## Where things live

| What | Where |
|---|---|
| Config | `~/.config/mtg/config.toml` — vault path, sealed precons you own |
| Card data, collection, sync state | `~/.local/share/mtg/` — outside the synced vault |
| Precon lists | `precons/` in this repo |
| Output | `tcg/mtg/_generated/` and `tcg/mtg/_log/` in the vault — nothing else |

## Invariants

- `oracle_id` is the key. Names are resolved once, at the edge; unmatched names are reported, never dropped.
- Colors are WUBRG order everywhere.
- The vault is a render target. Authored notes are read, never written.
