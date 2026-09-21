# Migration from the old `keltzbm/MTG`

The old scripts move to `legacy/` on the rewrite branch so they're in the tree
as reference while the new package is built, then get deleted once each row
below is done.

The old repo is the specification, not the starting point. Nothing gets ported
file-for-file; the domain knowledge below is lifted and the plumbing is
rewritten.

| Old | Fate | New home |
|---|---|---|
| `scrapeCards.py` | **Drop.** Scryfall bulk JSON replaces it. | `ingest/scryfall.py` |
| `api.py` | **Drop** if it wraps the Scryfall REST API — bulk data replaces per-card calls. Keep anything that isn't Scryfall. | `ingest/` |
| `prices.py` | **Mostly drop.** Prices ship in bulk data. Keep the snapshot-logging idea. | `ingest/scryfall.py`, `export/obsidian.py` |
| `classes.py` → `colorArchetypes` | **Port.** Four-color names included, re-keyed to WUBRG. | `analysis/colors.py` |
| `classes.py` → dict-as-object | **Drop.** Why `getattr` is everywhere. | `models/` |
| `analysis.py` → `getDeckColors` | **Port and promote.** Demand vs. supply as a first-class mana check. | `analysis/mana.py` |
| `analysis.py` → the rest | **Rewrite** behind CLI subcommands. | `analysis/`, `cli.py` |
| `deckCreation.py` | **Rewrite** as list parsing + ownership diff. | `ingest/moxfield.py`, `analysis/ownership.py` |
| `arenaCollection.py` | **Replace** with ManaBox ingest — paper collection is the source of truth now. Revisit only if Arena comes back. | `ingest/manabox.py` |
| `scrapeDecks.py` | **Defer.** Milestone 5, MTGO decklists only. | `ingest/mtgo.py` (later) |

## Known data gotchas, carried forward

- ManaBox exports use a UTF-8 BOM — read with `encoding="utf-8-sig"`.
- The `Name` column needs `.strip().lower()` on both sides of any comparison.
- The same card appears on multiple rows (one per printing); sum `Quantity`.
- **Precon contents are not in the collection export.** Ingest precon lists
  separately or every card in a sealed precon reads as "need to buy."
- Sorting colors alphabetically produces `BGU`; everything external says `UBG`.
- The repo lives inside a synced vault. Never write cache, bulk data, or the
  DuckDB file into the repo tree — use `~/.local/share/mtg`.
