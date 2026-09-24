# Riffle

[![CI](https://github.com/keltzbm/riffle/actions/workflows/ci.yml/badge.svg)](https://github.com/keltzbm/riffle/actions/workflows/ci.yml)

What I own, what I'm building, what the gap costs — in paper and on MTGO —
rendered into my Obsidian vault. Design: [DESIGN.md](DESIGN.md).

## Install

```bash
cd ~/atelier/github/riffle
uv sync                      # creates .venv, installs the package + dev tools
source .venv/bin/activate    # or prefix commands with `uv run`
riffle init
```

## First run

```bash
riffle ingest scryfall                          # ~500 MB download, once a day at most
riffle ingest manabox ~/Downloads/collection.csv
riffle sync --offline
```

## Everyday

```bash
riffle sync                        # picks up a new ManaBox export from ~/Downloads, refreshes
                                   # prices, rewrites _generated/, appends _log/
riffle decks                       # deck notes the vault holds
riffle own aesi-lands              # 🟥 what to buy (default); numbers are copies in the deck
riffle own aesi-lands -a           # 🟥 buy, then 🟩 own
riffle own aesi-lands -s own       # just what you have
riffle own aesi-lands --arena      # against your Arena collection, with wildcard counts
riffle price yshtola-spellslinger --budget-tix 500
riffle export aesi-lands --to moxfield -o ~/Downloads/aesi.txt   # owned printings pinned
riffle export all --to manabox -o ~/Downloads/mtg-exports        # every deck, one file each
riffle export izzet-murktide --to mtgo
riffle export aesi-lands --to tcgplayer        # mass-entry list of the shortfall
riffle ingest arena ~/Downloads/mtga_collection.txt              # text list or CSV
riffle legal aesi-lands            # size, copies, bans, commander color identity
riffle legal all                   # every deck; exits 1 if any is illegal
riffle legal my-deck -f modern     # check against a different format
```

## Metagame (MTGO)

```bash
riffle ingest mtgo -f modern --days 7          # league 5-0s, challenges, showcases from mtgo.com
riffle ingest mtgo -f pauper -k league          # just leagues; -k repeats
riffle meta cards -f modern --days 14           # most-played cards: share, avg copies, main/side
riffle meta decks -f modern --card "Psychic Frog"
riffle meta show <event-slug> <player> -o ~/Downloads/list.txt
riffle own ~/Downloads/list.txt                  # what that list costs you
```

Events are stored once each under `~/.local/share/riffle/mtgo/`; re-running only
fetches new ones.

A deck is named by its note's slug, or by a path to any `.md` or `.txt` list.

## Price history (every game)

```bash
riffle ingest tcgcsv                           # last 7 days of TCGplayer price archives from tcgcsv.com
riffle ingest tcgcsv --since 2024-02-08        # full backfill; the archive starts on that day
```

One compressed file per day holds TCGplayer prices for every game (Magic,
Flesh and Blood, One Piece, ...). Files are stored as downloaded under
`~/.local/share/riffle/tcgcsv/archive/`; loading them into a database comes later.
`riffle sync` fetches the last few days on its own, so the scheduled job keeps the
archive current.

## Keeping the vault current

Every ingest resyncs the vault afterwards (`--no-sync` to skip). Beyond that:

```bash
riffle watch                       # resync on every deck-note save or new ManaBox export
riffle schedule set 07:00 19:30    # launchd job at these 24-hour times; replaces any old schedule
riffle schedule                    # times, next run, last result, log path
riffle schedule remove
```

## Where things live

| What | Where |
|---|---|
| Config | `~/.config/riffle/config.toml` — vault path |
| Card data, collection, sync state, MTGO events, price archive | `~/.local/share/riffle/` — outside the synced vault |
| Output | `tcg/mtg/_generated/` and `tcg/mtg/_log/` in the vault — nothing else |

## Invariants

- `oracle_id` is the key. Names are resolved once, at the edge; unmatched names are reported, never dropped.
- Colors are WUBRG order everywhere.
- The vault is a render target. Authored notes are read, never written.
