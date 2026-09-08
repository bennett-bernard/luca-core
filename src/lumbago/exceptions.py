"""Domain errors raised by Lumbago's service and repository interfaces."""

from uuid import UUID


class LumbagoError(Exception):
    """Base class for expected errors raised by Lumbago."""


class RecordNotFoundError(LumbagoError):
    """Raised when a record cannot be found by its identifier."""

    def __init__(self, record_type: str, record_id: UUID) -> None:
        self.record_type = record_type
        self.record_id = record_id
        super().__init__(f"{record_type} record {record_id} was not found")


class DuplicateRecordError(LumbagoError):
    """Raised when creating a record whose identifier already exists."""

    def __init__(self, record_type: str, record_id: UUID) -> None:
        self.record_type = record_type
        self.record_id = record_id
        super().__init__(f"{record_type} record {record_id} already exists")


class DuplicateCodeError(LumbagoError):
    """Raised when a coded record would duplicate an existing code."""

    def __init__(self, record_type: str, code: str) -> None:
        self.record_type = record_type
        self.code = code
        super().__init__(
            f"{record_type} code {code!r} conflicts with an existing record"
        )


class InvalidUpdateError(LumbagoError):
    """Raised when an update attempts to change Lumbago-managed fields."""

    def __init__(self, fields: set[str]) -> None:
        self.fields = frozenset(fields)
        names = ", ".join(sorted(fields))
        super().__init__(f"update cannot change Lumbago-managed fields: {names}")


class ReferencedRecordError(LumbagoError):
    """Raised when deletion would remove a referenced accounting record."""


class ImmutableEntryError(LumbagoError):
    """Raised when attempting to update or delete a persisted journal entry."""


class InactiveAccountError(LumbagoError):
    """Raised when a new posting references an inactive account."""


class StorageError(LumbagoError):
    """A storage failure reported without SQL parameters or credentials."""


class UnitOfWorkError(LumbagoError):
    """Raised for operations outside an active, uncommitted unit of work."""
