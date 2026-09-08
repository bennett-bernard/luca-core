"""Run the same contracts against memory, SQLite, and isolated PostgreSQL schemas."""

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from luca import InMemoryStore
from luca.persistence.sqlalchemy import SqlAlchemyStore
from tests.helpers import UPDATED

type Store = InMemoryStore | SqlAlchemyStore


@pytest.fixture(params=["memory", "sqlite_memory", "sqlite_file", "postgres"])
def backend(request: pytest.FixtureRequest) -> str:
    if request.param == "postgres" and not os.environ.get("LUCA_TEST_POSTGRES_URL"):
        pytest.skip("set LUCA_TEST_POSTGRES_URL to run real PostgreSQL contracts")
    return str(request.param)


@pytest.fixture
def store_factory(backend: str, tmp_path: Path) -> Iterator[Callable[..., Store]]:
    cleanups: list[Callable[[], None]] = []

    def make_store(**options: Any) -> Store:
        if backend == "memory":
            return InMemoryStore(clock=lambda: UPDATED, **options)
        if backend == "postgres":
            url = make_url(os.environ["LUCA_TEST_POSTGRES_URL"])
            schema = "luca_test_" + uuid4().hex
            admin = create_engine(url, hide_parameters=True)
            with admin.begin() as connection:
                connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            scoped = url.update_query_dict({"options": "-csearch_path=" + schema})

            def drop_schema() -> None:
                try:
                    with admin.begin() as connection:
                        connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
                finally:
                    admin.dispose()

            cleanups.append(drop_schema)
            database_url = scoped.render_as_string(hide_password=False)
        else:
            database_url = (
                "sqlite+pysqlite:///:memory:"
                if backend == "sqlite_memory"
                else f"sqlite+pysqlite:///{tmp_path / (uuid4().hex + '.db')}"
            )
        store = SqlAlchemyStore(database_url, clock=lambda: UPDATED, **options)
        cleanups.append(store.close)
        store.migrate()
        return store

    try:
        yield make_store
    finally:
        for cleanup in reversed(cleanups):
            cleanup()


@pytest.fixture
def store(store_factory: Callable[..., Store]) -> Store:
    return store_factory()


@pytest.fixture
def sql_store(store: Store) -> SqlAlchemyStore:
    if not isinstance(store, SqlAlchemyStore):
        pytest.skip("SQL-specific constraint test")
    return store
