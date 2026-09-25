# Changelog

All notable changes, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/) (0.x: anything may change at a minor bump).
Work in progress goes under **Unreleased** and moves into a version heading at release time.

## [Unreleased]

### Added
- Daily price snapshots, Riffle's own price history: `riffle ingest prices` (and `riffle sync`) fetch every
  set's TCGplayer price file from tcgcsv.com for Magic, Flesh and Blood, and One Piece, one file at a time and
  once per day, into `~/.local/share/riffle/tcgcsv/daily/<day>/<game>/`, and keep each Magic printing's
  Scryfall prices from the bulk file already downloaded, in `scryfall/daily/<day>.jsonl.gz`. Files are stored
  as the sources returned them. Game category IDs are looked up on tcgcsv by name, never hard-coded.
- CI on GitHub Actions for every push to `main` and every pull request: `ruff check`, `ruff format --check`,
  and the test suite on Linux and macOS with Python 3.12, 3.13, and 3.14 (the versions `requires-python`
  allows).
- `mypy src` runs in CI; the code type-checks clean.
- Postgres: `riffle db up` starts a local Postgres 18 with Docker Compose (`compose.yaml`) and waits until
  it's healthy; `riffle db upgrade` applies migrations; `riffle db status` shows the server and schema
  revision and exits 1 if the database is unreachable or behind. Migrations (Alembic) ship inside the
  package. The first one creates `games` with Magic, Flesh and Blood, and One Piece.
- `database_url` config key, default `postgresql+psycopg://tcg@localhost:5432/tcg`. The password comes
  from `~/.pgpass`, never from config; `riffle init` shows the URL.
- Database tests against a separate `tcg_test` database, recreated each run, each test rolled back. They
  skip when no Postgres is reachable; CI's Linux jobs run them against a `postgres:18` service.
- Dependencies: SQLAlchemy, psycopg (with its bundled libpq), Alembic.
- A dev container for GitHub Codespaces (`.devcontainer/`): Docker, uv, the GitHub CLI, and an SSH server
  for `gh codespace ssh`. Creating a codespace installs the project and a database password; every start
  brings Postgres up and migrates it, so the database tests run there instead of skipping.

### Removed
- **Breaking:** `riffle ingest tcgcsv` and the daily price-archive download. tcgcsv.com took the archive down
  (September 2026) and asks clients to fetch price files individually instead; the snapshots above replace it.
  `riffle sync --offline` still keeps the Scryfall prices, which need no request.

### Changed
- CI's test job is split in two: Linux with a Postgres service, macOS without (its runners have no Docker).
- `.env`, which holds the local database password for Compose, is ignored by git.
- **Breaking:** the project is now Riffle (github.com/keltzbm/riffle). The package and command are
  `riffle` instead of `mtg`, config lives in `~/.config/riffle/`, data in `~/.local/share/riffle/`, and the
  launchd job's label is `com.keltzbm.riffle-sync`. Nothing is migrated automatically: move the old
  config and data directories, remove the old job, and set the schedule again. Behavior is otherwise
  unchanged; generated notes name `riffle sync`, and requests identify as `riffle/<version>`.
- `tests/test_sync.py` formatted with `ruff format`; the whole repo now passes the format check.
- Development Python pinned to 3.14 in `.python-version`: `uv run` and the CI lint job use it; the test
  matrix still covers 3.12 through 3.14.
- Type fixes found by mypy: code that uses a card's oracle id now receives it as a definite string instead
  of re-reading an optional field, and `riffle sync` no longer reuses one variable for the price archive and
  the sync result.

## [0.3.0] — 2026-09-23

### Added
- `mtg ingest tcgcsv`: daily TCGplayer price archives from tcgcsv.com, every game in one file per day,
  stored as downloaded under `~/.local/share/mtg/tcgcsv/archive/`. `--since 2024-02-08` backfills the whole
  archive; already-stored days are skipped, unpublished days are retried next run. `mtg sync` fetches the
  last few days, so the scheduled job keeps the archive current.
- `mtg schedule` is now a command group: `mtg schedule` / `show` (times, next run, loaded, runs,
  last exit, log), `set 07:00 19:30` (several daily 24-hour times, validated), `remove`.
- `CHANGELOG.md`.
- Tests: scheduling (fake launchctl), DuckDB catalog against an in-memory table, decklist / vault /
  file-ingest edge cases, and many more legality and MTGO cases — table-driven with
  `pytest.mark.parametrize`.

### Changed
- **Breaking:** `mtg schedule --at HH:MM` → `mtg schedule set HH:MM`; `--remove` → `remove`.
- The launchd plist is written with `plistlib` instead of a string template.
- MTGO ingest paces the monthly index requests as well as event pages (long backfills).
- `ruff check src tests` is clean: Typer's `Option`/`Argument` defaults are allowed in config, ambiguous
  single-letter names renamed, long test strings split. No behavior change.
- Resolving a collection loads every printing in one query and looks rows up in memory, instead of one
  query per ManaBox row (twice per row in the collection summary). `mtg sync --offline` went from 6.0 s to
  0.24 s on a three-deck vault.
- Owned counts are computed once per sync instead of once per deck.
- Clearer code in a few places: the deck-price builder, decklist set codes, and pairs that must line up
  one-to-one now fail loudly (`zip(strict=True)`) instead of silently truncating.
- One HTTP layer (`net.py`) for Scryfall, mtgo.com, and tcgcsv: the same User-Agent everywhere, retries on
  stalls and server errors, and a wait on 429 — for `Retry-After` when sent — as Scryfall requires. Client
  errors like 403 fail at once instead of being retried.
- Downloads stream to disk with a live size on a terminal (tcgcsv archives, the Scryfall bulk file); the
  scheduled job's log gets plain lines. A bad Scryfall download no longer replaces the last good file.

### Removed
- `analysis/mana.py`: stubs that were never implemented. Mana analysis is listed as not started in DESIGN.
- **Breaking:** sealed precon lists (`precons/`) and the `precons` config key. A precon counts as owned
  only once it's scanned into ManaBox, so nothing is ever counted twice. `mtg init` flags a leftover
  `precons` line; it's otherwise ignored.

### Fixed
- Maybeboard / Considering / Tokens sections in a decklist were counted as deck cards, so `mtg own`
  listed cards you were only considering. They're skipped now.
- Zero-quantity lines are skipped instead of added as entries.
- A byte-order mark at the start of a Windows-made list no longer corrupts the first card name.
- A heading like "Important notes" no longer passes for the "Moxfield import" heading.
- Arena CSVs with blank or zero counts no longer error or add empty holdings.
- Invalid schedule times (`7pm`, `25:00`) are rejected instead of crashing or writing a broken job.

## [0.2.0] — 2026-09-21

The file-based rewrite.

### Added
- Scryfall bulk ingest (JSON Lines) into DuckDB, keyed by `oracle_id`.
- ManaBox collection ingest (newest export picked up from ~/Downloads), sealed precons, Arena lists.
- `mtg own`, `price` (paper + MTGO tix), `export` (Moxfield, ManaBox, MTGO, Arena, TCGplayer;
  owned printings pinned), `sync`, `watch`, `schedule`.
- Obsidian output: `_generated/<deck>-data.md`, `_log/` prices and list versions.
- `mtg legal`: format legality, copy limits, deck size, sideboard, commander color identity;
  playset eligibility.
- MTGO decklists: `mtg ingest mtgo` (leagues, challenges, showcases; `-f all`), `mtg meta cards /
  decks / show`, deck fingerprints.

### Fixed
- `mtg schedule` wrote the launchd plist but never loaded it.
- Legality came from a card's newest printing, so non-tournament printings (e.g. gold-border
  World Championship decks) made Sylvan Library, Vampiric Tutor, and Blast Zone read "not legal".
  Now merged across all printings.
- MTGO events published before their lists were stored empty and never retried.
- Secret Lair reversible printings counted as separate cards.

## [0.1.0] — 2022

Original scripts: Firestore, Selenium scraping, dict-backed classes. Preserved as a tag.
