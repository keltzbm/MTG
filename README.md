# mtg

Personal Magic tooling: one source of truth for what I own, what I'm building,
and what the gap costs. Renders into an Obsidian vault.

Design and rationale: [DESIGN.md](DESIGN.md). Old-repo mapping:
[MIGRATION.md](MIGRATION.md).

## Install

Lives at `~/atelier/github/mtg`, beside the vault at `~/atelier/library`.

```bash
cd ~/atelier/github/mtg
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

Bulk data and the DuckDB file go to `$XDG_DATA_HOME/mtg` (default
`~/.local/share/mtg`), **not** into the repo — the Scryfall default-cards bulk
file is several hundred MB.

## Use

```bash
mtg ingest scryfall                   # download + load bulk default cards
mtg ingest manabox ~/Downloads/collection.csv
mtg ingest precon M3C-tricky-terrain  # precon contents, not in the export

mtg own decks/aesi-lands.txt          # have / need against real inventory
mtg analyze mana decks/aesi-lands.txt  # color demand vs. supply, curve, land count
mtg prices refresh                    # append snapshot to the vault price log

mtg export obsidian --vault ~/atelier/library
```

## Invariants

- `oracle_id` is the key. Never match on name.
- Colors are emitted in WUBRG order everywhere.
- The vault is a render target. The repo writes `library/tcg/mtg/_generated/` and
  `library/tcg/mtg/_log/` only.
- Nothing large or generated lives under `~/atelier/` except those two folders.
