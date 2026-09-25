"""Postgres, the system of record from v0.4.0 on.

The URL comes from the `database_url` config key and carries no password:
libpq reads it from ~/.pgpass, so psql, psycopg, and DuckDB's postgres
extension all connect the same way, the launchd job included.
"""

from sqlalchemy import Engine, create_engine, make_url

from riffle import config

CONNECT_TIMEOUT = 5  # seconds: a stopped or unreachable server fails fast instead of hanging


def engine(url: str | None = None) -> Engine:
    return create_engine(url or config.load().database_url, connect_args={"connect_timeout": CONNECT_TIMEOUT})


def display(url: str) -> str:
    """The URL for messages, any password masked."""
    return make_url(url).render_as_string(hide_password=True)


def reason(e: BaseException) -> str:
    """An error's own first line: the driver's message for a database error."""
    lines = str(getattr(e, "orig", None) or e).strip().splitlines()
    return lines[0] if lines else type(e).__name__
