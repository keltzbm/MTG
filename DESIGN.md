# MTG Tooling — Design

Rewrite of `keltzbm/MTG`. The original scripts are tagged `v0.1.0`.

## Purpose

One source of truth for what cards I own, what decks I'm building, and what
the gap costs — paper and MTGO. Everything else follows from that.

Two problems motivated the rewrite, both hit in practice:

1. **Wrong printings on import** — decklists matched by name, so a Moxfield
   import picked arbitrary printings.
2. **Ownership checks returning false** — a precon's contents weren't in the
   collection export, so 30 owned cards read as "need to buy." Fixed by
   scanning precons into ManaBox: the export is the one record of what you own.

Both are the same bug: **name is not a key.**

## Decisions

| Decision | Why |
|---|---|
| Key everything by Scryfall `oracle_id` | Names collide and differ across printings. Resolve once, at the edge. |
| Scryfall bulk JSON, not scraping (MTGO decklists are the one scrape — no API exists) | Daily, authoritative, includes legalities and prices — **paper USD and MTGO tix** (Scryfall sources tix from Cardhoarder). |
| tcgcsv daily archives for price history, stored raw | One request per day covers every game's TCGplayer prices, back to 2024-02-08. Kept compressed and untouched so any later loader can re-read them. |
| DuckDB for card data only | Loads the ~500 MB bulk file directly. The collection is re-read from the ManaBox CSV each run — 2,500 rows don't need a database. |
| Dataclasses, stdlib where possible | Validation happens at ingest; runtime deps are just `typer` and `duckdb`. |
| WUBRG color ordering | The old `sorted()` produced `BGU`; every external source says `UBG`. |
| Vault is a render target | Moxfield owns decklists, ManaBox owns the collection, deck notes own reasoning. |
| Deck notes are an input | The fenced list under "Moxfield import" in each note is what the tool reads. |

## Vault write contract

```
~/atelier/library/tcg/mtg/
├── _generated/     rewritten every sync — only when content changes
│   ├── <deck>.data.md          owned/buy counts, paper and MTGO totals, buy table
│   └── collection-summary.md
├── _log/           append-only
│   ├── prices.md               one snapshot per day of every unticked #mtg/buy card
│   └── <deck>.versions.md      a +/- diff each time a list changes
└── commander/ …    authored — read, never written
```

Authored notes embed generated ones with `![[aesi-lands.data]]`.
One writer per file: scripts never write authored notes; you never edit logs.

## Where things live

`~/atelier/github/mtg` sits **beside** the vault, not in it. Card data, the
collection CSV, and sync state live in `~/.local/share/mtg`, outside anything
pCloud syncs. Config is `~/.config/mtg/config.toml`.

## Milestones

| | | Status |
|---|---|---|
| 1 | Collection truth: Scryfall + ManaBox, `mtg own` | done |
| 2 | Obsidian export: `_generated/`, `mtg sync` | done |
| 3 | Analysis: mana demand/supply, curve, legality, playset eligibility | legality + playsets done; mana stubs |
| 4 | Prices and logging: paper + MTGO, price log, list versions | done — log rollup still to do |
| 5 | Metagame ingest: MTGO decklists only | ingest + card stats done |
| — | Export: Moxfield, ManaBox, MTGO .txt, TCGplayer mass entry, owned-printing pins | done |

## Layout

```
src/mtg/
├── config.py       XDG paths, config.toml
├── vault.py        read deck notes, frontmatter, buy lines — read-only
├── sync.py         the work behind `mtg sync`, CLI- and DB-free
├── models/         Printing, Prices, Deck, DeckEntry, Holding
├── ingest/         scryfall, manabox, decklist, arena, mtgo, tcgcsv
├── store/          Catalog protocol + DuckDB implementation
├── analysis/       resolve, ownership, pricing, colors, legality, metagame, mana*
├── export/         formats (moxfield/manabox/mtgo/tcgplayer), obsidian
└── cli.py          typer app — the only entry point
tests/              run against an in-memory Catalog; no download needed
```
