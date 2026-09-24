"""games: the card games Riffle covers, seeded.

Revision ID: 0001
Revises: none
"""

from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

GAMES: list[dict[str, Any]] = [
    {"game_id": "mtg", "name": "Magic: The Gathering", "tcgplayer_category": 1},
    {"game_id": "fab", "name": "Flesh and Blood", "tcgplayer_category": 62},
    # One Piece's category is resolved by name from tcgcsv when its ingest is built
    {"game_id": "op", "name": "One Piece Card Game", "tcgplayer_category": None},
]


def upgrade() -> None:
    games = op.create_table(
        "games",
        sa.Column("game_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("tcgplayer_category", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("game_id", name=op.f("pk_games")),
        sa.UniqueConstraint("tcgplayer_category", name=op.f("uq_games_tcgplayer_category")),
    )
    op.bulk_insert(games, GAMES)


def downgrade() -> None:
    op.drop_table("games")
