"""Loading one game's catalog into Postgres: stage everything, then merge, in one transaction.

A source's loader (riffle.ingest.scryfall_catalog for Magic) turns what the
source lists into a Batch: sets, cards, printings, legalities, and other
sources' IDs for printings, each row named by its ref, the creating source's
own ID for it. load() then

1. derives every row's ID from its ref (riffle.db.ids), references between rows
   included: a printing's card and set, a set's parent;
2. copies the rows into temporary staging tables with COPY, the fast path for
   bulk data, and ANALYZEs them so the planner knows how big they are;
3. retires the game's rows the batch no longer lists (retired_at), and
4. merges each table in turn:

       INSERT INTO cards (...)
       SELECT s.* FROM stage_cards s LEFT JOIN cards c USING (card_id)
       WHERE c.card_id IS NULL OR (c.name, ...) IS DISTINCT FROM (s.name, ...)
       ON CONFLICT (card_id) DO UPDATE SET ..., updated_at = now()
       WHERE (cards.name, ...) IS DISTINCT FROM (excluded.name, ...)

   The join drops unchanged rows in one hashed pass, so only new and changed
   rows reach the upsert, and the upsert's own WHERE keeps it from rewriting a
   row that didn't change. updated_at means what it says, and loading the same
   data twice writes nothing the second time. A retired row the batch lists
   again is un-retired by the same statement.

Legalities are the source's current word, so a loaded card's legality in a
format the source stopped listing is deleted. Nothing else is ever deleted: an
external ID the batch no longer names, or names on several printings, keeps its
row, and its last_seen says when the source last named it unambiguously.

The caller owns the transaction: a load lands whole or not at all.
"""

from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import cache
from itertools import chain
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from sqlalchemy import (
    Column,
    Connection,
    MetaData,
    Table,
    and_,
    delete,
    func,
    null,
    or_,
    select,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert

from riffle.db import ids
from riffle.db.models import Base

TABLES = Base.metadata.tables

# Each game's own columns, one table for cards and one for printings.
EXTENSIONS: dict[str, tuple[Table, Table]] = {"mtg": (TABLES["mtg_cards"], TABLES["mtg_printings"])}

Rows = Iterable[Sequence[Any]]
Plan = list[tuple[Table, Sequence[str], Rows]]  # (table, columns, rows) in load order; rows made as copied


@dataclass(slots=True)
class SetRow:
    ref: str  # the creating source's ID for the set
    code: str
    name: str
    set_type: str | None = None
    released_at: date | None = None
    parent: str | None = None  # the parent set's ref
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CardRow:
    ref: str
    name: str
    type_line: str | None = None
    rules_text: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    specific: dict[str, Any] = field(default_factory=dict)  # the game's own columns (mtg_cards)


@dataclass(slots=True)
class PrintingRow:
    ref: str
    card: str  # the card's ref
    set: str  # the set's ref
    collector_number: str
    lang: str = "en"
    rarity: str | None = None
    released_at: date | None = None
    image_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    specific: dict[str, Any] = field(default_factory=dict)  # the game's own columns (mtg_printings)


@dataclass
class Batch:
    """Everything a game's creating source lists, as of one moment."""

    game: str
    seen_at: datetime  # when the source published this data; becomes external_ids.last_seen
    formats: dict[str, str] = field(default_factory=dict)  # code -> name
    sets: list[SetRow] = field(default_factory=list)
    cards: list[CardRow] = field(default_factory=list)
    printings: list[PrintingRow] = field(default_factory=list)
    legalities: dict[str, dict[str, str]] = field(default_factory=dict)  # card ref -> format -> status
    printing_ids: list[tuple[str, str, str]] = field(default_factory=list)  # (source, its ID, printing ref)


@dataclass
class LoadResult:
    sets: int
    cards: int
    printings: int
    written: dict[str, int] = field(default_factory=dict)  # table -> rows inserted, changed, retired, deleted
    shared: dict[str, int] = field(default_factory=dict)  # source -> IDs naming several printings, not mapped

    @property
    def changed(self) -> int:
        return sum(self.written.values())


def loaded_through(conn: Connection, game: str) -> datetime | None:
    """When the source data the game's catalog was last loaded from was published, or None if never."""
    external_ids = TABLES["external_ids"]
    newest = select(func.max(external_ids.c.last_seen)).where(
        external_ids.c.source == ids.CREATORS[game].printing
    )
    return conn.execute(newest).scalar()


def load(conn: Connection, batch: Batch, aliases: ids.Aliases | None = None) -> LoadResult:
    """Merge a batch into the game's catalog on conn, inside the caller's transaction."""
    _check(batch)
    plan, shared = _plan(batch, ids.load_aliases() if aliases is None else aliases)
    staged = {table.name: _stage(conn, table, columns, rows) for table, columns, rows in plan}
    written: Counter[str] = Counter()
    for name in ("sets", "cards", "printings"):
        written[name] += _retire(conn, TABLES[name], staged[name], batch.game)
    for table, _, _ in plan:  # parents before children, as the foreign keys need
        written[table.name] += _merge(conn, table, staged[table.name])
    written["legalities"] += _drop_stale_legalities(conn, staged["cards"], staged["legalities"], batch.game)
    for stage in staged.values():
        conn.exec_driver_sql(f"DROP TABLE {stage.name}")
    return LoadResult(
        sets=len(batch.sets),
        cards=len(batch.cards),
        printings=len(batch.printings),
        written={name: n for name, n in written.items() if n},
        shared=shared,
    )


def _check(batch: Batch) -> None:
    """The game has a creating source, refs are unique, and every reference names a row
    in the batch: the merge would otherwise fail half-way, or quietly attach a printing
    to a retired card."""
    if batch.game not in ids.CREATORS:
        raise ValueError(f"no creating source is registered for {batch.game!r}")
    specific = [c.specific for c in batch.cards] + [p.specific for p in batch.printings]
    if batch.game not in EXTENSIONS and any(specific):
        raise ValueError(f"{batch.game} has no tables of its own for game-specific columns")

    def once(kind: str, keys: Iterable[str]) -> set[str]:
        counts = Counter(keys)
        twice = [k for k, n in counts.items() if n > 1]
        if twice:
            raise ValueError(f"{len(twice)} {kind} listed twice, e.g. {twice[0]}")
        return set(counts)

    sets = once("sets", (s.ref for s in batch.sets))
    cards = once("cards", (c.ref for c in batch.cards))
    once("printings", (p.ref for p in batch.printings))
    formats = {fmt for by_format in batch.legalities.values() for fmt in by_format}
    missing = [f"set {s.parent} (parent of {s.ref})" for s in batch.sets if s.parent and s.parent not in sets]
    missing += [f"card {p.card} (of printing {p.ref})" for p in batch.printings if p.card not in cards]
    missing += [f"set {p.set} (of printing {p.ref})" for p in batch.printings if p.set not in sets]
    missing += [f"card {ref} (legalities)" for ref in batch.legalities if ref not in cards]
    missing += [f"format {fmt}" for fmt in sorted(formats - set(batch.formats))]
    if missing:
        raise ValueError(f"{len(missing)} references to rows the batch lacks, e.g. {missing[0]}")


def _plan(batch: Batch, aliases: ids.Aliases) -> tuple[Plan, dict[str, int]]:
    """Every table's rows, IDs derived from refs, in an order the foreign keys accept."""
    creators = ids.CREATORS[batch.game]
    set_id = _deriver(creators.set, aliases)
    card_id = _deriver(creators.card, aliases)
    printing_id = _deriver(creators.printing, aliases)
    game, seen = batch.game, batch.seen_at

    def set_row(s: SetRow) -> tuple[Any, ...]:
        parent = set_id(s.parent) if s.parent else None
        return (set_id(s.ref), game, s.code, s.name, s.set_type, s.released_at, parent, Jsonb(s.extra))

    def card_row(c: CardRow) -> tuple[Any, ...]:
        return (card_id(c.ref), game, c.name, c.type_line, c.rules_text, Jsonb(c.extra))

    def printing_row(p: PrintingRow) -> tuple[Any, ...]:
        place = (card_id(p.card), set_id(p.set), p.collector_number, p.lang)
        return (printing_id(p.ref), game, *place, p.rarity, p.released_at, p.image_url, Jsonb(p.extra))

    def legality_rows() -> Iterator[tuple[Any, ...]]:
        for ref, by_format in batch.legalities.items():
            for fmt, status in by_format.items():
                yield (game, fmt, card_id(ref), status)

    mapped, shared = _unambiguous(batch.printing_ids)
    external = chain(
        ((creators.set, s.ref, game, None, None, set_id(s.ref), seen) for s in batch.sets),
        ((creators.card, c.ref, game, card_id(c.ref), None, None, seen) for c in batch.cards),
        ((creators.printing, p.ref, game, None, printing_id(p.ref), None, seen) for p in batch.printings),
        ((source, ext, game, None, printing_id(ref), None, seen) for source, ext, ref in mapped),
    )
    plan: Plan = [
        (TABLES["formats"], ("game_id", "format", "name"), [(game, f, n) for f, n in batch.formats.items()]),
        (
            TABLES["sets"],
            ("set_id", "game_id", "code", "name", "set_type", "released_at", "parent_set_id", "extra"),
            map(set_row, batch.sets),
        ),
        (
            TABLES["cards"],
            ("card_id", "game_id", "name", "type_line", "rules_text", "extra"),
            map(card_row, batch.cards),
        ),
        (
            TABLES["printings"],
            ("printing_id", "game_id", "card_id", "set_id", "collector_number", "lang")
            + ("rarity", "released_at", "image_url", "extra"),
            map(printing_row, batch.printings),
        ),
        (TABLES["legalities"], ("game_id", "format", "card_id", "status"), legality_rows()),
    ]
    if game in EXTENSIONS:
        card_table, printing_table = EXTENSIONS[game]
        plan.append(_extension(card_table, game, ((card_id(c.ref), c.specific) for c in batch.cards)))
        plan.append(
            _extension(printing_table, game, ((printing_id(p.ref), p.specific) for p in batch.printings))
        )
    plan.append(
        (
            TABLES["external_ids"],
            ("source", "external_id", "game_id", "card_id", "printing_id", "set_id", "last_seen"),
            external,
        )
    )
    return plan, shared


def _deriver(source: str, aliases: ids.Aliases) -> Callable[[str], UUID]:
    """ids.derive for one source, remembered: a card is named by every one of its printings."""

    @cache
    def derive(ref: str) -> UUID:
        return ids.derive(source, ref, aliases)

    return derive


def _unambiguous(pairs: Iterable[tuple[str, str, str]]) -> tuple[list[tuple[str, str, str]], dict[str, int]]:
    """Other sources' IDs that name exactly one printing, and per source how many name
    more than one: an ID in the registry means one row, so a shared one maps to none."""
    creating = ids.creating_sources()
    targets: dict[tuple[str, str], str | None] = {}  # None once a second printing claims the ID
    for source, external_id, ref in pairs:
        if source in creating:
            raise ValueError(f"{source} creates catalog rows; it can't also map IDs onto them")
        key = (source, external_id)
        if key not in targets:
            targets[key] = ref
        elif targets[key] != ref:
            targets[key] = None
    kept = [(source, ext, ref) for (source, ext), ref in targets.items() if ref is not None]
    shared = Counter(source for (source, _), ref in targets.items() if ref is None)
    return kept, dict(shared)


def _extension(
    table: Table, game: str, rows: Iterable[tuple[UUID, dict[str, Any]]]
) -> tuple[Table, Sequence[str], Rows]:
    """A game's own table: its key, game_id, then the columns every row's specific dict must name."""
    key = [c.name for c in table.primary_key.columns]
    columns = [c.name for c in table.columns if c.name not in (*key, "game_id")]
    expected = set(columns)

    def made() -> Iterator[tuple[Any, ...]]:
        for k, values in rows:
            if values.keys() != expected:
                wrong = ", ".join(sorted(expected ^ values.keys()))
                raise ValueError(f"{table.name}: a row's columns differ from the table's: {wrong}")
            yield (k, game, *(values[c] for c in columns))

    return table, (*key, "game_id", *columns), made()


def _stage(conn: Connection, table: Table, columns: Sequence[str], rows: Rows) -> Table:
    """A temporary table with table's column types and these rows, copied in with COPY and
    analyzed: without statistics the planner guesses, and guesses nested loops."""
    stage = Table(f"stage_{table.name}", MetaData(), *(Column(c, table.c[c].type) for c in columns))
    quote = conn.dialect.identifier_preparer.quote
    names = ", ".join(quote(c) for c in columns)
    source = f"SELECT {names} FROM {quote(table.name)}"
    conn.exec_driver_sql(f"CREATE TEMP TABLE {stage.name} ON COMMIT DROP AS {source} WITH NO DATA")
    raw = conn.connection.driver_connection
    if raw is None:
        raise RuntimeError("the database connection is closed")
    with raw.cursor() as cur, cur.copy(f"COPY {stage.name} ({names}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
    conn.exec_driver_sql(f"ANALYZE {stage.name}")
    return stage


def _retire(conn: Connection, table: Table, stage: Table, game: str) -> int:
    """Stamp retired_at on the game's rows the batch doesn't list; they're never deleted."""
    (key,) = table.primary_key.columns
    listed = select(stage.c[key.name]).where(stage.c[key.name] == key).exists()
    stmt = (
        update(table)
        .where(table.c.game_id == game, table.c.retired_at.is_(None), ~listed)
        .values(retired_at=func.now())
    )
    return conn.execute(stmt).rowcount


def _merge(conn: Connection, table: Table, stage: Table) -> int:
    """Insert new rows and update changed ones, keyed by the primary key; unchanged rows
    aren't touched. Returns how many rows were written."""
    columns = [c.name for c in stage.columns]
    key = [c.name for c in table.primary_key.columns]
    changing = [c for c in columns if c not in key]
    retires = "retired_at" in table.c

    def differs(old: Any, new: Any) -> Any:
        """The row old names differs from new's, retirement included: a listed row isn't retired."""
        before = [old[c] for c in changing] + ([old["retired_at"]] if retires else [])
        after = [new[c] for c in changing] + ([null()] if retires else [])
        return tuple_(*before).is_distinct_from(tuple_(*after))

    current = table.alias("current")
    joined = stage.outerjoin(current, and_(*(current.c[k] == stage.c[k] for k in key)))
    new_or_changed = or_(current.c[key[0]].is_(None), differs(current.c, stage.c))
    stmt = insert(table).from_select(
        columns, select(*stage.columns).select_from(joined).where(new_or_changed)
    )
    values: dict[str, Any] = {c: stmt.excluded[c] for c in changing}
    if retires:
        values["retired_at"] = null()
    if "updated_at" in table.c:
        values["updated_at"] = func.now()
    upsert = stmt.on_conflict_do_update(
        index_elements=key, set_=values, where=differs(table.c, stmt.excluded)
    )
    return conn.execute(upsert.execution_options(preserve_rowcount=True)).rowcount


def _drop_stale_legalities(conn: Connection, cards: Table, legalities: Table, game: str) -> int:
    """Delete a loaded card's legality in a format the batch no longer gives for it."""
    table = TABLES["legalities"]
    listed = (
        select(legalities.c.card_id)
        .where(legalities.c.card_id == table.c.card_id, legalities.c.format == table.c.format)
        .exists()
    )
    loaded = table.c.card_id.in_(select(cards.c.card_id))  # a semi-join, safe however many rows go
    return conn.execute(delete(table).where(table.c.game_id == game, loaded, ~listed)).rowcount
