"""catalog: formats, sets, cards, printings, legalities, external_ids, and Magic's extension tables.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def _stamps() -> list[sa.Column]:
    """updated_at and retired_at, on every table of rows a source creates."""
    return [
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _extra() -> sa.Column:
    return sa.Column("extra", postgresql.JSONB(), server_default=sa.text("'{}'"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "formats",
        sa.Column("game_id", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("game_id", "format", name=op.f("pk_formats")),
        sa.ForeignKeyConstraint(["game_id"], ["games.game_id"], name=op.f("fk_formats_game_id_games")),
    )
    op.create_table(
        "sets",
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("set_type", sa.Text(), nullable=True),
        sa.Column("released_at", sa.Date(), nullable=True),
        sa.Column("parent_set_id", sa.Uuid(), nullable=True),
        _extra(),
        *_stamps(),
        sa.PrimaryKeyConstraint("set_id", name=op.f("pk_sets")),
        sa.UniqueConstraint("game_id", "code", name=op.f("uq_sets_game_id_code")),
        sa.UniqueConstraint("game_id", "set_id", name=op.f("uq_sets_game_id_set_id")),
        sa.ForeignKeyConstraint(["game_id"], ["games.game_id"], name=op.f("fk_sets_game_id_games")),
        sa.ForeignKeyConstraint(
            ["game_id", "parent_set_id"],
            ["sets.game_id", "sets.set_id"],
            name=op.f("fk_sets_game_id_parent_set_id_sets"),
        ),
    )
    op.create_table(
        "cards",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type_line", sa.Text(), nullable=True),
        sa.Column("rules_text", sa.Text(), nullable=True),
        _extra(),
        *_stamps(),
        sa.PrimaryKeyConstraint("card_id", name=op.f("pk_cards")),
        sa.UniqueConstraint("game_id", "card_id", name=op.f("uq_cards_game_id_card_id")),
        sa.ForeignKeyConstraint(["game_id"], ["games.game_id"], name=op.f("fk_cards_game_id_games")),
    )
    op.create_index(op.f("ix_cards_game_id_lower_name"), "cards", ["game_id", sa.text("lower(name)")])
    op.create_table(
        "printings",
        sa.Column("printing_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Text(), nullable=False),
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("collector_number", sa.Text(), nullable=False),
        sa.Column("lang", sa.Text(), server_default=sa.text("'en'"), nullable=False),
        sa.Column("rarity", sa.Text(), nullable=True),
        sa.Column("released_at", sa.Date(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        _extra(),
        *_stamps(),
        sa.PrimaryKeyConstraint("printing_id", name=op.f("pk_printings")),
        sa.UniqueConstraint("game_id", "printing_id", name=op.f("uq_printings_game_id_printing_id")),
        sa.ForeignKeyConstraint(
            ["game_id", "card_id"],
            ["cards.game_id", "cards.card_id"],
            name=op.f("fk_printings_game_id_card_id_cards"),
        ),
        sa.ForeignKeyConstraint(
            ["game_id", "set_id"],
            ["sets.game_id", "sets.set_id"],
            name=op.f("fk_printings_game_id_set_id_sets"),
        ),
        postgresql.ExcludeConstraint(
            (sa.text("set_id"), "="),
            (sa.text("collector_number"), "="),
            (sa.text("lang"), "="),
            name=op.f("ex_printings_set_id_collector_number_lang"),
            using="btree",
            where=sa.text("game_id = 'mtg' AND retired_at IS NULL"),
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(op.f("ix_printings_card_id"), "printings", ["card_id"])
    op.create_table(
        "legalities",
        sa.Column("game_id", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("game_id", "format", "card_id", name=op.f("pk_legalities")),
        sa.ForeignKeyConstraint(
            ["game_id", "format"],
            ["formats.game_id", "formats.format"],
            name=op.f("fk_legalities_game_id_format_formats"),
        ),
        sa.ForeignKeyConstraint(
            ["game_id", "card_id"],
            ["cards.game_id", "cards.card_id"],
            name=op.f("fk_legalities_game_id_card_id_cards"),
        ),
        sa.CheckConstraint(
            "status IN ('legal', 'not_legal', 'banned', 'restricted', 'suspended', 'living_legend')",
            name=op.f("ck_legalities_status"),
        ),
    )
    op.create_table(
        "external_ids",
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("game_id", sa.Text(), nullable=False),
        sa.Column("card_id", sa.Uuid(), nullable=True),
        sa.Column("printing_id", sa.Uuid(), nullable=True),
        sa.Column("set_id", sa.Uuid(), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source", "external_id", name=op.f("pk_external_ids")),
        sa.ForeignKeyConstraint(
            ["game_id", "card_id"],
            ["cards.game_id", "cards.card_id"],
            name=op.f("fk_external_ids_game_id_card_id_cards"),
        ),
        sa.ForeignKeyConstraint(
            ["game_id", "printing_id"],
            ["printings.game_id", "printings.printing_id"],
            name=op.f("fk_external_ids_game_id_printing_id_printings"),
        ),
        sa.ForeignKeyConstraint(
            ["game_id", "set_id"],
            ["sets.game_id", "sets.set_id"],
            name=op.f("fk_external_ids_game_id_set_id_sets"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(card_id, printing_id, set_id) = 1", name=op.f("ck_external_ids_one_target")
        ),
    )
    op.create_index(op.f("ix_external_ids_card_id"), "external_ids", ["card_id"])
    op.create_index(op.f("ix_external_ids_printing_id"), "external_ids", ["printing_id"])
    op.create_index(op.f("ix_external_ids_set_id"), "external_ids", ["set_id"])
    op.create_table(
        "mtg_cards",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Text(), server_default=sa.text("'mtg'"), nullable=False),
        sa.Column("mana_cost", sa.Text(), nullable=True),
        sa.Column("mana_value", sa.Numeric(), nullable=False),
        sa.Column("colors", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("color_identity", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("layout", sa.Text(), nullable=False),
        sa.Column("reserved", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("card_id", name=op.f("pk_mtg_cards")),
        sa.ForeignKeyConstraint(
            ["game_id", "card_id"],
            ["cards.game_id", "cards.card_id"],
            name=op.f("fk_mtg_cards_game_id_card_id_cards"),
        ),
        sa.CheckConstraint("game_id = 'mtg'", name=op.f("ck_mtg_cards_game_id")),
        sa.CheckConstraint(
            "colors <@ '{W,U,B,R,G}' AND color_identity <@ '{W,U,B,R,G}'", name=op.f("ck_mtg_cards_colors")
        ),
    )
    op.create_table(
        "mtg_printings",
        sa.Column("printing_id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Text(), server_default=sa.text("'mtg'"), nullable=False),
        sa.Column("finishes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("promo", sa.Boolean(), nullable=False),
        sa.Column("digital", sa.Boolean(), nullable=False),
        sa.Column("border_color", sa.Text(), nullable=True),
        sa.Column("frame", sa.Text(), nullable=True),
        *(
            sa.Column(price, sa.Numeric(10, 2), nullable=True)
            for price in ("usd", "usd_foil", "usd_etched", "eur", "eur_foil", "tix")
        ),
        sa.PrimaryKeyConstraint("printing_id", name=op.f("pk_mtg_printings")),
        sa.ForeignKeyConstraint(
            ["game_id", "printing_id"],
            ["printings.game_id", "printings.printing_id"],
            name=op.f("fk_mtg_printings_game_id_printing_id_printings"),
        ),
        sa.CheckConstraint("game_id = 'mtg'", name=op.f("ck_mtg_printings_game_id")),
    )


def downgrade() -> None:
    for table in (
        "mtg_printings",
        "mtg_cards",
        "external_ids",
        "legalities",
        "printings",
        "cards",
        "sets",
        "formats",
    ):
        op.drop_table(table)
