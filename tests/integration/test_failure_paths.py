"""Adapter corruption, configuration, concurrency, and cleanup regressions."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import sqlite
from sqlalchemy.exc import OperationalError

from luca import (
    AccountingService,
    DuplicateCodeError,
    InMemoryStore,
    StorageError,
    UnitOfWorkError,
)
from luca.persistence.sqlalchemy import SqlAlchemyStore
from luca.persistence.sqlalchemy.base import UTCDateTime, WholeHundredths
from luca.persistence.sqlalchemy.engine import create_luca_engine
from luca.persistence.sqlalchemy.models import AccountRow
from tests.conftest import Store
from tests.helpers import account, entry, journal


def test_type_codecs_reject_corruption_and_naive_times() -> None:
    dialect = sqlite.dialect()
    timestamps = UTCDateTime()
    assert timestamps.process_bind_param(None, dialect) is None
    assert timestamps.process_result_value(None, dialect) is None
    with pytest.raises(ValueError, match="timezone-aware"):
        timestamps.process_bind_param(datetime(2026, 9, 1), dialect)
    offset = datetime(2026, 9, 1, 12, tzinfo=timezone(timedelta(hours=2)))
    assert timestamps.process_bind_param(offset, dialect) == datetime(
        2026, 9, 1, 10, tzinfo=UTC
    )
    codec = WholeHundredths()
    assert codec.process_result_value(None, dialect) is None
    with pytest.raises(ValueError, match="whole"):
        codec.process_result_value(Decimal("12500.1"), dialect)


@pytest.mark.parametrize(
    "url", ["invalid-url", "mysql://user:secret@localhost/database"]
)
def test_bad_configuration_does_not_expose_url(url: str) -> None:
    with pytest.raises(StorageError) as error:
        create_luca_engine(url)
    assert "secret" not in str(error.value) and url not in str(error.value)


def test_missing_driver_is_reported_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(*args: object, **kwargs: object) -> None:
        raise ModuleNotFoundError("driver unavailable with secret context")

    monkeypatch.setattr("luca.persistence.sqlalchemy.engine.create_engine", missing)
    with pytest.raises(StorageError) as error:
        create_luca_engine("postgresql+psycopg://user:secret@localhost/test")
    assert "secret" not in str(error.value)


def test_base_package_does_not_import_optional_sql_dependencies() -> None:
    script = """import importlib.abc, sys
class BlockSql(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'sqlalchemy', 'alembic', 'psycopg'}:
            raise ImportError('optional dependency imported by core')
sys.meta_path.insert(0, BlockSql())
import luca
assert luca.Money(amount='12.34', currency='USD').minor_units == 1234
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True)


def test_cleanup_can_be_called_twice_without_reopening_scope(store: Store) -> None:
    scope = store.unit_of_work()
    with scope:
        pass
    scope.__exit__()
    with pytest.raises(UnitOfWorkError):
        scope.ensure_active()


def test_memory_store_refuses_overlapping_transactions() -> None:
    store = InMemoryStore()
    with store.unit_of_work(), pytest.raises(UnitOfWorkError), store.unit_of_work():
        pass


def test_repository_constraint_error_is_sanitized_and_recoverable(
    sql_store: SqlAlchemyStore,
) -> None:
    original = account()
    with sql_store.unit_of_work() as uow:
        uow.accounts.create(original)

        def corrupt(mapper: object, connection: object, target: AccountRow) -> None:
            target.account_type = "invalid"

        event.listen(AccountRow, "before_update", corrupt)
        try:
            with pytest.raises(StorageError, match="constraint"):
                uow.accounts.update(original.id, {"name": "Changed"})
        finally:
            event.remove(AccountRow, "before_update", corrupt)
        assert uow.accounts.retrieve(original.id) == original
        uow.commit()


def test_failed_commit_disables_scope_and_rolls_back(
    sql_store: SqlAlchemyStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = account()
    with sql_store.unit_of_work() as uow:
        uow.accounts.create(record)

        def fail() -> None:
            raise OperationalError("SQL containing secret", {}, Exception("secret"))

        monkeypatch.setattr(uow._session, "commit", fail)
        with pytest.raises(StorageError) as error:
            uow.commit()
        assert "secret" not in str(error.value)
        with pytest.raises(UnitOfWorkError):
            uow.accounts.list()
    with sql_store.unit_of_work() as uow:
        assert uow.accounts.list() == ()


@pytest.mark.parametrize("amount", ["0.01", "9999999999999999.99"])
def test_money_boundaries_survive_every_backend(store: Store, amount: str) -> None:
    cash, revenue, general = account(), account("REVENUE"), journal()
    posting = entry(cash, revenue, general, amount=amount)
    with store.unit_of_work() as uow:
        service = AccountingService(uow)
        service.create_account(cash)
        service.create_account(revenue)
        service.create_journal(general)
        service.create_entry(posting)
        uow.commit()
    with store.unit_of_work() as uow:
        assert (
            str(uow.journal_entries.retrieve(posting.id).lines[0].amount.amount)
            == amount
        )


def test_simultaneous_code_creation_has_one_winner(
    sql_store: SqlAlchemyStore, backend: str
) -> None:
    if backend == "sqlite_memory":
        pytest.skip("single-connection SQLite memory stores require sequential use")
    barrier = Barrier(2)

    def create(code: str) -> str:
        barrier.wait(timeout=10)
        try:
            with sql_store.unit_of_work() as uow:
                uow.accounts.create(account(code))
                uow.commit()
            return "created"
        except DuplicateCodeError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, ["CASH", "Cash"])) == ["created", "duplicate"]
    with sql_store.unit_of_work() as uow:
        assert len(uow.accounts.list()) == 1
