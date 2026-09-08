"""Domain errors raised by Luca's service and repository interfaces."""

from uuid import UUID


class LucaError(Exception):
    """Base class for expected errors raised by Luca."""


class RecordNotFoundError(LucaError):
    """Raised when a record cannot be found by its identifier."""

    def __init__(self, record_type: str, record_id: UUID) -> None:
        self.record_type = record_type
        self.record_id = record_id
        super().__init__(f"{record_type} record {record_id} was not found")


class DuplicateRecordError(LucaError):
    """Raised when creating a record whose identifier already exists."""

    def __init__(self, record_type: str, record_id: UUID) -> None:
        self.record_type = record_type
        self.record_id = record_id
        super().__init__(f"{record_type} record {record_id} already exists")


class DuplicateCodeError(LucaError):
    """Raised when a coded record would duplicate an existing code."""

    def __init__(self, record_type: str, code: str) -> None:
        self.record_type = record_type
        self.code = code
        super().__init__(
            f"{record_type} code {code!r} conflicts with an existing record"
        )


class InvalidUpdateError(LucaError):
    """Raised when an update attempts to change Luca-managed fields."""

    def __init__(self, fields: set[str]) -> None:
        self.fields = frozenset(fields)
        names = ", ".join(sorted(fields))
        super().__init__(f"update cannot change Luca-managed fields: {names}")


class ReferencedRecordError(LucaError):
    """Raised when deletion would remove a referenced accounting record."""


class ImmutableEntryError(LucaError):
    """Raised when attempting to update or delete a persisted journal entry."""


class InactiveAccountError(LucaError):
    """Raised when a new posting references an inactive account."""


class StorageError(LucaError):
    """A storage failure reported without SQL parameters or credentials."""


class UnitOfWorkError(LucaError):
    """Raised for operations outside an active, uncommitted unit of work."""
