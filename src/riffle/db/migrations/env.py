"""Alembic's entry point, run by riffle.db.migrate on the connection it passes in."""

from alembic import context

from riffle.db.models import Base

if context.is_offline_mode():
    raise RuntimeError("offline (--sql) migrations aren't supported")

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("run migrations through riffle.db.migrate, e.g. `riffle db upgrade`")

context.configure(connection=connection, target_metadata=Base.metadata)
with context.begin_transaction():
    context.run_migrations()
