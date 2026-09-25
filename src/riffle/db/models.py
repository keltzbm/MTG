"""ORM models: the schema's definition. Migrations must build exactly this;
tests/test_postgres.py compares the two on every run. Alembic compares every
table, column, key, and index, but not exclusion constraints, so the one on
printings is checked by a test of its behavior instead.

The catalog tables are shared by every game and carry game_id in every row and
every foreign key, so the database itself refuses, say, a Flesh and Blood
printing of a Magic card. Each game adds its own columns in extension tables
(mtg_cards, mtg_printings), one row per shared row. Design: DESIGN.md and the
schema notes; how rows get their IDs: riffle.db.ids.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, ExcludeConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Constraint and index names follow fixed rules, so a later migration can
# name any of them to drop or change it without looking it up.
NAMING = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(column_0_N_label)s",
}

LEGALITY_STATUSES = ("legal", "not_legal", "banned", "restricted", "suspended", "living_legend")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Game(Base):
    """A card game. Every other table carries its game_id."""

    __tablename__ = "games"

    game_id: Mapped[str] = mapped_column(Text, primary_key=True)  # our code: mtg, fab, op
    name: Mapped[str] = mapped_column(Text)
    tcgplayer_category: Mapped[int | None] = mapped_column(Integer, unique=True)


class Format(Base):
    """A format cards are legal, banned, or restricted in: modern, cc, blitz. Never deleted."""

    __tablename__ = "formats"

    game_id: Mapped[str] = mapped_column(Text, ForeignKey("games.game_id"), primary_key=True)
    format: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)


class Set(Base):
    """A set as its game publishes it: mh3, WTR, OP01. Promo and token sets name their parent."""

    __tablename__ = "sets"
    __table_args__ = (
        UniqueConstraint("game_id", "code"),
        UniqueConstraint("game_id", "set_id"),  # what child rows' (game_id, set_id) keys reference
        ForeignKeyConstraint(["game_id", "parent_set_id"], ["sets.game_id", "sets.set_id"]),
    )

    set_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    game_id: Mapped[str] = mapped_column(Text, ForeignKey("games.game_id"))
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    set_type: Mapped[str | None] = mapped_column(Text)  # the source's vocabulary
    released_at: Mapped[date | None] = mapped_column(Date)
    parent_set_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )  # the source stopped listing it


class Card(Base):
    """The canonical card: a Magic oracle card, a FaB name and pitch, a One Piece base card number."""

    __tablename__ = "cards"
    __table_args__ = (UniqueConstraint("game_id", "card_id"),)

    card_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    game_id: Mapped[str] = mapped_column(Text, ForeignKey("games.game_id"))
    name: Mapped[str] = mapped_column(Text)  # not unique: FaB repeats a name across pitch values
    type_line: Mapped[str | None] = mapped_column(Text)
    rules_text: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Name resolution looks cards up by lowercased name within a game.
Index("ix_cards_game_id_lower_name", Card.game_id, func.lower(Card.name))


class Printing(Base):
    """One physical version of a card: a Scryfall card object, a fab-cube printing, a One Piece parallel."""

    __tablename__ = "printings"
    __table_args__ = (
        UniqueConstraint("game_id", "printing_id"),
        ForeignKeyConstraint(["game_id", "card_id"], ["cards.game_id", "cards.card_id"]),
        ForeignKeyConstraint(["game_id", "set_id"], ["sets.game_id", "sets.set_id"]),
        # A Magic printing is one set, number, and language; FaB editions and One Piece
        # parallels share numbers, so only Magic's rows are held to it. An exclusion
        # constraint, unlike a unique index, can be both partial and deferred: checked
        # at commit, so two printings can swap numbers in one load, and a printing the
        # source replaced is retired in the same transaction its successor arrives.
        ExcludeConstraint(
            (text("set_id"), "="),
            (text("collector_number"), "="),
            (text("lang"), "="),
            name="ex_printings_set_id_collector_number_lang",
            using="btree",
            where=text("game_id = 'mtg' AND retired_at IS NULL"),
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    printing_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    game_id: Mapped[str] = mapped_column(Text)
    card_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    set_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    collector_number: Mapped[str] = mapped_column(Text)  # 123, WTR001, OP01-001
    lang: Mapped[str] = mapped_column(Text, server_default=text("'en'"))
    rarity: Mapped[str | None] = mapped_column(Text)
    released_at: Mapped[date | None] = mapped_column(Date)
    image_url: Mapped[str | None] = mapped_column(Text)  # linked from its official source, never hosted
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Legality(Base):
    """A card's status in one format, as its source gives it now."""

    __tablename__ = "legalities"
    __table_args__ = (
        ForeignKeyConstraint(["game_id", "format"], ["formats.game_id", "formats.format"]),
        ForeignKeyConstraint(["game_id", "card_id"], ["cards.game_id", "cards.card_id"]),
        CheckConstraint(f"status IN {LEGALITY_STATUSES!r}", name="status"),
    )

    game_id: Mapped[str] = mapped_column(Text, primary_key=True)
    format: Mapped[str] = mapped_column(Text, primary_key=True)
    card_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    status: Mapped[str] = mapped_column(Text)


class ExternalId(Base):
    """The ID registry: an upstream source's ID for a card, printing, or set, and ours."""

    __tablename__ = "external_ids"
    __table_args__ = (
        ForeignKeyConstraint(["game_id", "card_id"], ["cards.game_id", "cards.card_id"]),
        ForeignKeyConstraint(["game_id", "printing_id"], ["printings.game_id", "printings.printing_id"]),
        ForeignKeyConstraint(["game_id", "set_id"], ["sets.game_id", "sets.set_id"]),
        CheckConstraint("num_nonnulls(card_id, printing_id, set_id) = 1", name="one_target"),
    )

    source: Mapped[str] = mapped_column(Text, primary_key=True)  # scryfall_oracle, scryfall, mtgo, arena
    external_id: Mapped[str] = mapped_column(Text, primary_key=True)
    game_id: Mapped[str] = mapped_column(Text)
    card_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    printing_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    set_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )  # the source data that last listed it


class MtgCard(Base):
    """Magic's own columns for a card: one row per Magic row in cards."""

    __tablename__ = "mtg_cards"
    __table_args__ = (
        ForeignKeyConstraint(["game_id", "card_id"], ["cards.game_id", "cards.card_id"]),
        CheckConstraint("game_id = 'mtg'", name="game_id"),
        CheckConstraint("colors <@ '{W,U,B,R,G}' AND color_identity <@ '{W,U,B,R,G}'", name="colors"),
    )

    card_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    game_id: Mapped[str] = mapped_column(Text, server_default=text("'mtg'"))
    mana_cost: Mapped[str | None] = mapped_column(Text)
    mana_value: Mapped[Decimal] = mapped_column(Numeric)
    colors: Mapped[list[str]] = mapped_column(ARRAY(Text))  # WUBRG order
    color_identity: Mapped[list[str]] = mapped_column(ARRAY(Text))  # WUBRG order
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text))
    layout: Mapped[str] = mapped_column(Text)
    reserved: Mapped[bool] = mapped_column(Boolean)


class MtgPrinting(Base):
    """Magic's own columns for a printing, today's prices included: one row per Magic printing."""

    __tablename__ = "mtg_printings"
    __table_args__ = (
        ForeignKeyConstraint(["game_id", "printing_id"], ["printings.game_id", "printings.printing_id"]),
        CheckConstraint("game_id = 'mtg'", name="game_id"),
    )

    printing_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    game_id: Mapped[str] = mapped_column(Text, server_default=text("'mtg'"))
    finishes: Mapped[list[str]] = mapped_column(ARRAY(Text))  # nonfoil, foil, etched
    promo: Mapped[bool] = mapped_column(Boolean)
    digital: Mapped[bool] = mapped_column(Boolean)
    border_color: Mapped[str | None] = mapped_column(Text)
    frame: Mapped[str | None] = mapped_column(Text)
    usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    usd_foil: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    usd_etched: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    eur: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    eur_foil: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    tix: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # MTGO; only Scryfall has it
