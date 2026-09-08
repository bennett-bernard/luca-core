"""Transactional accounting workflows with explicit caller-owned commits."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from lumbago.exceptions import (
    ImmutableEntryError,
    InactiveAccountError,
    ReferencedRecordError,
)
from lumbago.models.accounting import Account, Journal, JournalEntry
from lumbago.models.audit import AuditAction, AuditEvent
from lumbago.models.base import utc_now
from lumbago.persistence.unit_of_work import UnitOfWork
from lumbago.repositories.base import RecordChanges
from lumbago.services.accounting import AccountService, JournalService


class AccountingService:
    """Apply accounting rules inside an active unit of work.

    These methods never commit. Call ``uow.commit()`` once the complete caller
    workflow succeeds. Each mutation uses a savepoint so a caught failure
    cannot leave a partial operation behind.
    """

    def __init__(
        self, uow: UnitOfWork, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._uow = uow
        self._clock = clock

    def create_account(self, account: Account) -> Account:
        """Create an account with a unique code."""

        with self._uow.atomic():
            return AccountService(self._uow.accounts).create(account)

    def update_account(self, record_id: UUID, changes: RecordChanges) -> Account:
        """Update account details or deactivate the account."""

        with self._uow.atomic():
            return AccountService(self._uow.accounts).update(record_id, changes)

    def create_journal(self, journal: Journal) -> Journal:
        """Create a journal with a unique code."""

        with self._uow.atomic():
            return JournalService(self._uow.journals).create(journal)

    def update_journal(self, record_id: UUID, changes: RecordChanges) -> Journal:
        """Update journal details while preserving code uniqueness."""

        with self._uow.atomic():
            return JournalService(self._uow.journals).update(record_id, changes)

    def create_entry(self, entry: JournalEntry) -> JournalEntry:
        """Validate references and persist the complete balanced entry."""

        with self._uow.atomic():
            candidate = type(entry).model_validate(entry.model_dump(mode="python"))
            self._uow.journals.retrieve(candidate.journal_id)
            for account_id in sorted({line.account_id for line in candidate.lines}):
                account = self._uow.accounts.retrieve(account_id)
                if not account.active:
                    raise InactiveAccountError(f"Account {account_id} is inactive")
            return self._uow.journal_entries.create(candidate)

    def delete_account(self, record_id: UUID, *, actor: str | None = None) -> Account:
        """Delete an unreferenced account and append its audit snapshot atomically."""

        with self._uow.atomic():
            record = self._uow.accounts.retrieve(record_id)
            if any(
                line.account_id == record_id
                for entry in self._uow.journal_entries.list()
                for line in entry.lines
            ):
                raise ReferencedRecordError(f"Account {record_id} has journal lines")
            event = self._delete_event(record, actor)
            self._uow.accounts.delete(record_id)
            self._uow.audit_events.append(event)
            return record

    def delete_journal(self, record_id: UUID, *, actor: str | None = None) -> Journal:
        """Delete an empty journal and append its audit snapshot atomically."""

        with self._uow.atomic():
            record = self._uow.journals.retrieve(record_id)
            if any(
                entry.journal_id == record_id
                for entry in self._uow.journal_entries.list()
            ):
                raise ReferencedRecordError(f"Journal {record_id} contains entries")
            event = self._delete_event(record, actor)
            self._uow.journals.delete(record_id)
            self._uow.audit_events.append(event)
            return record

    def update_entry(self, record_id: UUID, changes: RecordChanges) -> JournalEntry:
        """Persisted entries are immutable; corrections require new entries."""

        self._uow.ensure_active()
        self._uow.journal_entries.retrieve(record_id)
        raise ImmutableEntryError("persisted journal entries cannot be updated")

    def delete_entry(self, record_id: UUID) -> JournalEntry:
        """Persisted entries cannot be deleted through accounting workflows."""

        self._uow.ensure_active()
        self._uow.journal_entries.retrieve(record_id)
        raise ImmutableEntryError("persisted journal entries cannot be deleted")

    def _delete_event(self, record: Account | Journal, actor: str | None) -> AuditEvent:
        return AuditEvent(
            occurred_at=self._clock(),
            action=AuditAction.DELETE,
            record_type=type(record).__name__,
            record_id=record.id,
            actor=actor,
            snapshot=record.model_dump(mode="json"),
        )
