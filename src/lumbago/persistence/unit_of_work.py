"""The transaction contract shared by accounting storage implementations."""

from contextlib import AbstractContextManager
from typing import Protocol, Self

from lumbago.models.accounting import Account, Journal, JournalEntry
from lumbago.repositories.audit import AuditLog
from lumbago.repositories.base import Repository


class UnitOfWork(Protocol):
    """Coordinate repositories; only an explicit commit persists the batch.

    A context supports one commit or rollback. Repositories must not be used
    after either operation or after context exit. ``atomic`` protects one
    workflow even if the caller catches its failure within the outer context.
    """

    accounts: Repository[Account]
    journals: Repository[Journal]
    journal_entries: Repository[JournalEntry]
    audit_events: AuditLog

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def atomic(self) -> AbstractContextManager[None]: ...

    def ensure_active(self) -> None: ...
