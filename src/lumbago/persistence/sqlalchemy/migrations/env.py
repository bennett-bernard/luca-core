"""Alembic entry point, usable from an installed wheel or the repository."""

import os

from alembic import context
from sqlalchemy.engine import Connection

from lumbago.persistence.sqlalchemy import models  # noqa: F401
from lumbago.persistence.sqlalchemy.base import Base
from lumbago.persistence.sqlalchemy.engine import create_lumbago_engine


def run(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=Base.metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Lumbago migrations require a database connection")

connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    url = os.environ.get("LUMBAGO_DATABASE_URL")
    if not url:
        raise RuntimeError("set LUMBAGO_DATABASE_URL to the database to migrate")
    engine = create_lumbago_engine(url)
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()
