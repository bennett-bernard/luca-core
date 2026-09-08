"""SQL transaction lifecycle with explicit commits and workflow savepoints."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Self, cast

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from luca.exceptions import UnitOfWorkError
from luca.models.accounting import Account, Journal, JournalEntry
from luca.models.base import utc_now
from luca.persistence.sqlalchemy.mappers import (
    account_from_row,
    account_to_row,
    entry_from_row,
    entry_to_row,
    journal_from_row,
    journal_to_row,
)
from luca.persistence.sqlalchemy.models import AccountRow, EntryRow, JournalRow
from luca.persistence.sqlalchemy.repositories import (
    SqlAuditLog,
    SqlRepository,
    translate_errors,
)
from luca.repositories.audit import AuditLog
from luca.repositories.base import Repository


class SqlAlchemyUnitOfWork:
    """One non-shared workflow scope; commit or rollback ends its useful lifetime."""

    accounts: Repository[Account]
    journals: Repository[Journal]
    journal_entries: Repository[JournalEntry]
    audit_events: AuditLog

    def __init__(
        self,
        engine: Engine,
        *,
        account_type: type[Account] = Account,
        journal_type: type[Journal] = Journal,
        entry_type: type[JournalEntry] = JournalEntry,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._engine = engine
        self._account_type = account_type
        self._journal_type = journal_type
        self._entry_type = entry_type
        self._clock = clock
        self._session: Session | None = None
        self._active = False
        self._used = False

    def __enter__(self) -> Self:
        if self._used:
            raise UnitOfWorkError("a unit of work cannot be entered twice")
        self._used = True
        self._session = Session(self._engine, expire_on_commit=False)
        self._active = True
        self.accounts = SqlRepository(
            self._session,
            self._account_type,
            AccountRow,
            account_to_row,
            lambda row: account_from_row(cast(AccountRow, row), self._account_type),
            self.ensure_active,
            self._clock,
        )
        self.journals = SqlRepository(
            self._session,
            self._journal_type,
            JournalRow,
            journal_to_row,
            lambda row: journal_from_row(cast(JournalRow, row), self._journal_type),
            self.ensure_active,
            self._clock,
        )
        self.journal_entries = SqlRepository(
            self._session,
            self._entry_type,
            EntryRow,
            entry_to_row,
            lambda row: entry_from_row(cast(EntryRow, row), self._entry_type),
            self.ensure_active,
            self._clock,
        )
        self.audit_events = SqlAuditLog(self._session, self.ensure_active)
        return self

    def __exit__(self, *args: object) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
        self._active = False

    def ensure_active(self) -> None:
        if not self._active:
            raise UnitOfWorkError(
                "enter an uncommitted unit of work before using its repositories"
            )

    def commit(self) -> None:
        self.ensure_active()
        assert self._session is not None
        try:
            with translate_errors("transaction"):
                self._session.commit()
        finally:
            self._active = False

    def rollback(self) -> None:
        self.ensure_active()
        assert self._session is not None
        self._session.rollback()
        self._active = False

    @contextmanager
    def atomic(self) -> Iterator[None]:
        self.ensure_active()
        assert self._session is not None
        with translate_errors("workflow"), self._session.begin_nested():
            yield
