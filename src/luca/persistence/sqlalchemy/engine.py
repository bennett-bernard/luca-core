"""Explicit database configuration without schema creation at startup."""

import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

from luca.exceptions import StorageError


def create_luca_engine(url: str, *, echo: bool = False) -> Engine:
    """Create a supported engine; keep parameters and credentials out of errors.

    SQLite workflows use BEGIN IMMEDIATE to serialize writers before reference
    checks. File-backed databases can still be read by other connections. One
    in-memory engine must not be shared between simultaneous units of work.
    """

    try:
        parsed = make_url(url)
        if parsed.drivername not in {"sqlite", "sqlite+pysqlite", "postgresql+psycopg"}:
            raise StorageError(
                "supported URLs use sqlite+pysqlite or postgresql+psycopg"
            )
        memory = parsed.get_backend_name() == "sqlite" and parsed.database in {
            None,
            "",
            ":memory:",
        }
        engine = create_engine(
            parsed,
            echo=echo,
            hide_parameters=True,
            poolclass=StaticPool if memory else None,
            isolation_level="REPEATABLE READ"
            if parsed.get_backend_name() == "postgresql"
            else None,
        )
    except (ArgumentError, ModuleNotFoundError):
        raise StorageError(
            "invalid database configuration or missing optional driver"
        ) from None
    if parsed.get_backend_name() == "sqlite":
        event.listen(engine, "connect", _configure_sqlite)
        event.listen(engine, "begin", _begin_sqlite)
    return engine


def _configure_sqlite(
    connection: sqlite3.Connection, record: ConnectionPoolEntry
) -> None:
    connection.isolation_level = None
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")


def _begin_sqlite(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN IMMEDIATE")
