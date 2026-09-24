"""ORM models: the schema's definition. Migrations must build exactly this;
tests/test_postgres.py compares the two on every run."""

from sqlalchemy import Integer, MetaData, Text
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


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Game(Base):
    """A card game. Every other table carries its game_id."""

    __tablename__ = "games"

    game_id: Mapped[str] = mapped_column(Text, primary_key=True)  # our code: mtg, fab, op
    name: Mapped[str] = mapped_column(Text)
    tcgplayer_category: Mapped[int | None] = mapped_column(Integer, unique=True)
