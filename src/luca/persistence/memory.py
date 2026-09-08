"""Transactional in-memory storage implementing the same workflow contract."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Self
from uuid import UUID

from luca.exceptions import (
    DuplicateCodeError,
    DuplicateRecordError,
    ImmutableEntryError,
    InvalidUpdateError,
    ReferencedRecordError,
    UnitOfWorkError,
)
from luca.models.accounting import Account, Journal, JournalEntry
from luca.models.audit import AuditEvent
from luca.models.base import RecordModel, utc_now
from luca.repositories.audit import AuditLog, InMemoryAuditLog
from luca.repositories.base import RecordChanges, Repository
from luca.repositories.memory import MANAGED_FIELDS, InMemoryRepository

type Snapshot = tuple[
    tuple[Account, ...],
    tuple[Journal, ...],
    tuple[JournalEntry, ...],
    tuple[AuditEvent, ...],
]


class InMemoryStore:
    """Keep committed state between sequential units of work; nothing is durable."""

    def __init__(
        self,
        *,
        account_type: type[Account] = Account,
        journal_type: type[Journal] = Journal,
        entry_type: type[JournalEntry] = JournalEntry,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._state: Snapshot = ((), (), (), ())
        self._in_use = False
        self._account_type = account_type
        self._journal_type = journal_type
        self._entry_type = entry_type
        self._clock = clock

    def unit_of_work(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self)


class _MemoryRepository[RecordT: RecordModel](InMemoryRepository[RecordT]):
    """Add relational and lifetime checks to the lightweight generic adapter."""

    def __init__(self, record_type: type[RecordT], uow: InMemoryUnitOfWork) -> None:
        super().__init__(record_type, clock=uow._store._clock)
        self._uow = uow

    def create(self, record: RecordT) -> RecordT:
        self._uow.ensure_active()
        candidate = self._validated_copy(record)
        if candidate.id in self._records:
            raise DuplicateRecordError(self._record_name, candidate.id)
        self._check_code(candidate)
        if isinstance(candidate, JournalEntry):
            self._uow.journals.retrieve(candidate.journal_id)
            used = {
                line.id
                for entry in self._uow.journal_entries.list()
                for line in entry.lines
            }
            for line in candidate.lines:
                self._uow.accounts.retrieve(line.account_id)
                if line.id in used:
                    raise DuplicateRecordError("JournalLine", line.id)
        return super().create(candidate)

    def retrieve(self, record_id: UUID) -> RecordT:
        self._uow.ensure_active()
        return super().retrieve(record_id)

    def list(self) -> tuple[RecordT, ...]:
        self._uow.ensure_active()
        return tuple(
            sorted(super().list(), key=lambda record: (record.created_at, record.id))
        )

    def update(self, record_id: UUID, changes: RecordChanges) -> RecordT:
        self._uow.ensure_active()
        existing = self.retrieve(record_id)
        if isinstance(existing, JournalEntry):
            raise ImmutableEntryError("persisted journal entries cannot be updated")
        invalid = MANAGED_FIELDS.intersection(changes)
        if invalid:
            raise InvalidUpdateError(set(invalid))
        values = existing.model_dump(mode="python")
        values.update(changes)
        self._check_code(
            self._record_type.model_validate(values), excluding_id=record_id
        )
        return super().update(record_id, changes)

    def delete(self, record_id: UUID) -> RecordT:
        self._uow.ensure_active()
        record = self.retrieve(record_id)
        if isinstance(record, JournalEntry):
            raise ImmutableEntryError("persisted journal entries cannot be deleted")
        for entry in self._uow.journal_entries.list():
            if isinstance(record, Journal) and entry.journal_id == record_id:
                raise ReferencedRecordError("journal contains entries")
            if isinstance(record, Account) and any(
                line.account_id == record_id for line in entry.lines
            ):
                raise ReferencedRecordError("account has journal lines")
        return super().delete(record_id)

    def _check_code(self, record: RecordT, *, excluding_id: UUID | None = None) -> None:
        if isinstance(record, Account | Journal) and any(
            isinstance(existing, Account | Journal)
            and existing.id != excluding_id
            and existing.code.casefold() == record.code.casefold()
            for existing in self._records.values()
        ):
            raise DuplicateCodeError(type(record).__name__, record.code)


class _MemoryAuditLog(InMemoryAuditLog):
    def __init__(self, ensure_active: Callable[[], None]) -> None:
        super().__init__()
        self._ensure_active = ensure_active

    def append(self, event: AuditEvent) -> AuditEvent:
        self._ensure_active()
        return super().append(event)

    def list(self) -> tuple[AuditEvent, ...]:
        self._ensure_active()
        return tuple(
            sorted(super().list(), key=lambda event: (event.occurred_at, event.id))
        )


class InMemoryUnitOfWork:
    """Snapshot transactions and savepoints for deterministic local workflows."""

    accounts: Repository[Account]
    journals: Repository[Journal]
    journal_entries: Repository[JournalEntry]
    audit_events: AuditLog

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._active = False
        self._entered = False
        self._used = False

    def __enter__(self) -> Self:
        if self._used or self._store._in_use:
            raise UnitOfWorkError(
                "use a fresh unit of work; memory workflows cannot overlap"
            )
        self._used = self._entered = self._active = self._store._in_use = True
        self._accounts = _MemoryRepository(self._store._account_type, self)
        self._journals = _MemoryRepository(self._store._journal_type, self)
        self._entries = _MemoryRepository(self._store._entry_type, self)
        self._audit = _MemoryAuditLog(self.ensure_active)
        self.accounts, self.journals = self._accounts, self._journals
        self.journal_entries, self.audit_events = self._entries, self._audit
        self._load(self._store._state)
        return self

    def __exit__(self, *args: object) -> None:
        if self._entered:
            self._store._in_use = False
        self._entered = self._active = False

    def ensure_active(self) -> None:
        if not self._active:
            raise UnitOfWorkError(
                "enter an uncommitted unit of work before using its repositories"
            )

    def commit(self) -> None:
        self.ensure_active()
        self._store._state = self._dump()
        self._active = False

    def rollback(self) -> None:
        self.ensure_active()
        self._active = False

    @contextmanager
    def atomic(self) -> Iterator[None]:
        self.ensure_active()
        snapshot = self._dump()
        try:
            yield
        except BaseException:
            self._load(snapshot)
            raise

    def _dump(self) -> Snapshot:
        return (
            self._accounts.list(),
            self._journals.list(),
            self._entries.list(),
            self._audit.list(),
        )

    def _load(self, snapshot: Snapshot) -> None:
        self._accounts._records = {
            record.id: self._accounts._validated_copy(record) for record in snapshot[0]
        }
        self._journals._records = {
            record.id: self._journals._validated_copy(record) for record in snapshot[1]
        }
        self._entries._records = {
            record.id: self._entries._validated_copy(record) for record in snapshot[2]
        }
        self._audit._events = {
            event.id: self._audit._validated_copy(event) for event in snapshot[3]
        }
