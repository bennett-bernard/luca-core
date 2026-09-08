"""Real SQL constraints, transaction failures, and storage reconstruction."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import DBAPIError

from luca import AccountingService, StorageError
from luca.persistence.sqlalchemy import SqlAlchemyStore
from luca.persistence.sqlalchemy.models import AccountRow, EntryRow, LineRow
from tests.helpers import account, entry, journal


def seed(store: SqlAlchemyStore) -> tuple:
    cash, revenue, general = account(), account("REVENUE"), journal()
    posting = entry(cash, revenue, general)
    with store.unit_of_work() as uow:
        service = AccountingService(uow)
        service.create_account(cash)
        service.create_account(revenue)
        service.create_journal(general)
        service.create_entry(posting)
        uow.commit()
    return cash, revenue, general, posting


@pytest.mark.parametrize(
    "raw",
    [
        "12500.1",
        "999999999999999900.1",
        "'999999999999999900.1'",
        "0",
        "-1",
        "1000000000000000000",
        "'not-money'",
    ],
)
def test_database_rejects_invalid_hundredths(
    sql_store: SqlAlchemyStore, raw: str
) -> None:
    seed(sql_store)
    with pytest.raises(DBAPIError), sql_store._engine.begin() as connection:
        connection.exec_driver_sql(f"UPDATE journal_lines SET amount_minor = {raw}")
    with sql_store.unit_of_work() as uow:
        assert uow.journal_entries.list()[0].lines[0].amount.minor_units == 12500


def test_direct_sql_enforces_codes_foreign_keys_and_currency(
    sql_store: SqlAlchemyStore,
) -> None:
    cash, _, _, posting = seed(sql_store)
    for statement in (
        "UPDATE accounts SET code = 'cash' WHERE code = 'REVENUE'",
        "UPDATE accounts SET code_key = 'fake' WHERE code = 'CASH'",
        "UPDATE accounts SET code = 'cäsh' WHERE code = 'CASH'",
        "UPDATE journal_lines SET currency = 'U1D'",
        "UPDATE journal_lines SET currency = 'usd'",
        "DELETE FROM accounts WHERE code = 'CASH'",
        "DELETE FROM journals WHERE code = 'GENERAL'",
    ):
        with pytest.raises(DBAPIError), sql_store._engine.begin() as connection:
            connection.exec_driver_sql(statement)
    with sql_store._engine.begin() as connection:
        assert (
            connection.scalar(
                select(AccountRow.code_key).where(AccountRow.id == cash.id)
            )
            == "cash"
        )
        if connection.dialect.name == "sqlite":
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    with pytest.raises(DBAPIError), sql_store._engine.begin() as connection:
        connection.execute(update(LineRow).values(account_id=uuid4()))
    with sql_store.unit_of_work() as uow:
        assert uow.journal_entries.retrieve(posting.id) == posting


def test_generated_code_keys_use_ascii_case_rules(sql_store: SqlAlchemyStore) -> None:
    cash, _, _, _ = seed(sql_store)
    with sql_store._engine.begin() as connection:
        connection.execute(
            update(AccountRow).where(AccountRow.id == cash.id).values(code="INCOME")
        )
        assert (
            connection.scalar(
                select(AccountRow.code_key).where(AccountRow.id == cash.id)
            )
            == "income"
        )
    with pytest.raises(DBAPIError), sql_store._engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE accounts SET code = 'income' WHERE code = 'REVENUE'"
        )


def test_line_insert_failure_rolls_back_parent_and_all_lines(
    sql_store: SqlAlchemyStore,
) -> None:
    cash, revenue, general = account(), account("REVENUE"), journal()
    posting = entry(cash, revenue, general)

    def fail(mapper: object, connection: object, target: LineRow) -> None:
        if target.position == 1:
            raise RuntimeError("injected line insertion failure")

    with sql_store.unit_of_work() as uow:
        service = AccountingService(uow)
        service.create_account(cash)
        service.create_account(revenue)
        service.create_journal(general)
        event.listen(LineRow, "before_insert", fail)
        try:
            with pytest.raises(RuntimeError, match="injected"):
                service.create_entry(posting)
        finally:
            event.remove(LineRow, "before_insert", fail)
        assert uow.journal_entries.list() == ()
        uow.commit()
    with sql_store._engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(EntryRow)) == 0
        assert connection.scalar(select(func.count()).select_from(LineRow)) == 0


def test_invalid_stored_metadata_fails_reconstruction(
    sql_store: SqlAlchemyStore,
) -> None:
    cash, _, _, _ = seed(sql_store)
    with sql_store._engine.begin() as connection:
        connection.execute(
            update(AccountRow)
            .where(AccountRow.id == cash.id)
            .values(extensions={"id": "fake"})
        )
    with sql_store.unit_of_work() as uow, pytest.raises(ValueError, match="conflicts"):
        uow.accounts.retrieve(cash.id)


def test_schema_is_not_created_implicitly_and_sqlite_survives_process_restart(
    tmp_path: Path,
) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'persisted.db'}"
    store = SqlAlchemyStore(url)
    with store.unit_of_work() as uow, pytest.raises(StorageError):
        uow.accounts.list()
    store.migrate()
    _, _, _, posting = seed(store)
    store.close()
    script = (
        "import sys; from luca.persistence.sqlalchemy import SqlAlchemyStore; "
        "s=SqlAlchemyStore(sys.argv[1]); "
        "u=s.unit_of_work(); u.__enter__(); print(u.journal_entries.list()[0].id); "
        "u.__exit__(); s.close()"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, url], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == str(posting.id)


def test_committed_entry_is_readable_in_an_independent_process(
    sql_store: SqlAlchemyStore, backend: str
) -> None:
    if backend == "sqlite_memory":
        pytest.skip("in-memory SQLite intentionally has no process durability")
    _, _, _, posting = seed(sql_store)
    script = (
        "import os; from luca.persistence.sqlalchemy import SqlAlchemyStore; "
        "s=SqlAlchemyStore(os.environ['LUCA_REOPEN_DATABASE_URL']); "
        "u=s.unit_of_work(); u.__enter__(); "
        "entry=u.journal_entries.list()[0]; "
        "print(entry.id, entry.lines[0].amount.amount); "
        "u.__exit__(); s.close()"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env={
            **os.environ,
            "LUCA_REOPEN_DATABASE_URL": sql_store._engine.url.render_as_string(
                hide_password=False
            ),
        },
    )
    assert result.stdout.strip() == f"{posting.id} 125.00"
