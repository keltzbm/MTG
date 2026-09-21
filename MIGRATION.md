# Migration from the original scripts

The original scripts are preserved at tag `v0.1.0`. Read any of them without
checking anything out: `git show v0.1.0:classes.py`

| Old | Fate | New home |
|---|---|---|
| `scrapeCards.py` | Dropped — Scryfall bulk data | `ingest/scryfall.py` |
| `api.py` | Dropped where it wrapped Scryfall's REST API | `ingest/scryfall.py` |
| `prices.py` | Replaced — prices ship in bulk data, paper and MTGO | `analysis/pricing.py` |
| `classes.py` → `colorArchetypes` | Ported, WUBRG re-keyed | `analysis/colors.py` |
| `classes.py` → dict-as-object | Dropped | `models/` |
| `analysis.py` → `getDeckColors` | To port: demand vs. supply | `analysis/mana.py` (stub) |
| `deckCreation.py` | Rewritten as list parsing + ownership | `ingest/decklist.py`, `analysis/ownership.py` |
| `arenaCollection.py` | Replaced by ManaBox ingest | `ingest/manabox.py` |
| `scrapeDecks.py` | Deferred — milestone 5, MTGO lists only | — |

## Data gotchas, handled

- ManaBox exports have a UTF-8 BOM — `utf-8-sig`.
- One row per printing — quantities are summed per `oracle_id`.
- Sealed precon contents aren't in the export — `precons/` + config.
- Alphabetical color sorting gives `BGU` — `wubrg_sort()`.
- The repo sits beside a synced vault — card data lives in `~/.local/share/mtg`.
