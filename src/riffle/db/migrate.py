"""Schema migrations with Alembic, the scripts shipped inside the package.

No alembic.ini: `riffle db upgrade` builds the configuration here, so it works
from any directory, the launchd job and the home server included. Migrations
are written by hand; a test checks that they build what the models define.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine

SCRIPTS = Path(__file__).parent / "migrations"


def _config(connection: Connection | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(SCRIPTS))
    if connection is not None:
        cfg.attributes["connection"] = connection  # env.py migrates on this connection
    return cfg


def scripts() -> ScriptDirectory:
    return ScriptDirectory.from_config(_config())


def head() -> str:
    """The newest revision. There is always exactly one: migrations form a line."""
    heads = scripts().get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"migrations should have one head, found {len(heads)}: {', '.join(heads)}")
    return heads[0]


def revision(conn: Connection) -> str | None:
    """The revision of the database conn is on, or None before the first migration."""
    return MigrationContext.configure(conn).get_current_revision()


def current(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return revision(conn)


def upgrade(engine: Engine, revision: str = "head") -> None:
    """Migrate forward, all in one transaction: a failure leaves the schema as it was."""
    with engine.begin() as conn:
        command.upgrade(_config(conn), revision)


def downgrade(engine: Engine, revision: str) -> None:
    with engine.begin() as conn:
        command.downgrade(_config(conn), revision)
