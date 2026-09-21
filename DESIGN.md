# MTG Tooling — Design

Rewrite of `keltzbm/MTG`. The old repo is eight flat scripts; this keeps its
domain knowledge and replaces the plumbing.

## Purpose

One source of truth for what cards I own, what decks I'm building, and what the
gap between them costs. Everything else follows from that.

Two problems motivated the rewrite, both hit in practice:

1. **Wrong printings on import** — decklists matched by card *name*, so a
   Moxfield import picked arbitrary printings.
2. **Ownership checks returning false** — a precon's contents weren't in the
   collection export, so 30 cards physically owned read as "need to buy."

Both are the same bug: **name is not a key.**

## Decisions

| Decision | Why |
|---|---|
| Key everything by Scryfall `oracle_id` | Names collide, change, and differ across printings. Printings keyed by `scryfall_id` underneath. |
| Scryfall bulk JSON, not scraping | Published daily, authoritative; includes oracle text, types, color identity, legalities, prices. No rate limits, no fragile HTML. |
| DuckDB over SQLite | Analytical queries over ~100k cards; reads Parquet and JSON directly; no server. |
| Typed models (Pydantic), snake_case | The old `self.__dict__ = values` with keys like `"Card Name"` is why `getattr` is everywhere. |
| WUBRG color ordering | The old `sorted()` produces `BGU`; every external source uses `UBG`. Match the world. |
| Vault is a render target | Moxfield owns decklists, ManaBox owns the collection. Never edit a note to fix data. |

## Ported from the old repo

- **`colorArchetypes` dict** (`classes.py`) — full mapping including the
  four-color names (Glint, Dune, Witch, Yore, Ink) and Five-Color. Re-key to
  WUBRG order; keep as the lookup behind the `color-archetype` property.
- **Demand/supply color split** (`getDeckColors`) — separating colors the
  spells *require* from colors the lands *produce*. Worth keeping as a
  first-class mana-base check.

Dropped: `scrapeCards.py`, most of `prices.py` (both replaced by bulk data),
and the untyped dict-as-object pattern throughout.

## Vault write contract

The repo never writes authored files.

```
~/atelier/library/tcg/mtg/
├── _generated/     wholesale rewrite — current state, safe to wipe
│   ├── aesi-lands.data.md
│   └── collection-summary.md
├── _log/           append-only — events, never rewritten
│   ├── prices.md
│   ├── ownership.md              bought / sold / moved between decks
│   └── aesi-lands.versions.md
└── commander/ …    authored by hand — reasoning, decisions, plans
```

Authored notes embed generated ones with `![[aesi-lands.data]]`.

**Rules**

- Scripts write only `_generated/` and `_log/`.
- One exception: creating a *new* deck note stub with correct frontmatter.
  After creation, hands off.
- `_generated/` is regenerated wholesale; never hand-edit it.
- `_log/` is append-only; never hand-edit it either.
- Logs get rolled up periodically — recent entries plus a dated summary — so
  vault search doesn't fill with stale price lines.
- **One writer per file.** The moment both touch the same file you have a merge
  problem, and append-only doesn't save you there — it just makes the conflict
  silent.

Why the split: current-state content gets *revised*, not appended. An
append-only file of design decisions is a transcript you'd have to diff
mentally to find the current plan.

## Milestones

**1. Collection truth** — Scryfall bulk ingest, ManaBox ingest, precon ingest,
`ownership.py` diff. Deliverable: `mtg own <decklist>` prints have/need against
real inventory. This is the thing needed twice already.

**2. Obsidian export** — `_generated/` notes carrying the vault frontmatter,
TCGplayer mass-entry blocks, buy-list totals.

**3. Analysis** — color demand/supply, curve, land-count checks, legality and
playset eligibility across formats.

**4. Prices and logging** — price snapshots appended to `_log/prices.md`,
buy-list valuation, trend over time.

**5. Metagame ingest** — MTGO decklists only, narrowly scoped. Deck sites are
fragile HTML and murky on terms; leave them last or never.

## Stack

Python 3.12+, `typer` (CLI), `pydantic` (models), `duckdb` (store), `httpx`
(fetch), `jinja2` (templates), `pytest` + `ruff` + `mypy`. `uv` for env and
locking.

## Layout

```
~/atelier/github/mtg/
├── src/mtg/
│   ├── models/     card, printing, deck, collection — typed, oracle_id-keyed
│   ├── ingest/     scryfall bulk, manabox csv, moxfield, precon lists
│   ├── store/      duckdb connection, schema, upserts, queries
│   ├── analysis/   ownership diff, mana base, legality, color archetypes
│   ├── export/     obsidian notes, tcgplayer mass entry (jinja2)
│   └── cli.py      typer app — the only entry point
├── tests/          mirrors src/mtg
└── pyproject.toml

~/.local/share/mtg/    bulk cache + mtg.duckdb — outside the vault entirely
```

## Where the repo lives

`~/atelier/github/mtg`, **beside** the vault (`~/atelier/library`), not inside
it. Obsidian never indexes the repo's own markdown or Jinja templates, and the
repo reaches into the vault at exactly two paths:

```
~/atelier/library/tcg/mtg/_generated/
~/atelier/library/tcg/mtg/_log/
```

The vault path is the one piece of configuration:
`mtg export obsidian --vault ~/atelier/library`.

Bulk data and the DuckDB file live in `~/.local/share/mtg` regardless. If pCloud
syncs all of `~/atelier` rather than just `library/`, anything under `github/`
is in the sync folder — a several-hundred-MB bulk file and a DuckDB file being
written mid-query don't belong there, and `.git` takes bursts of small writes
during rebases that sync clients handle badly. Syncing `library/` only avoids
all of it.
