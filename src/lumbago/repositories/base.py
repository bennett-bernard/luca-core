"""Storage-neutral repository contracts for Lumbago records."""

from collections.abc import Mapping
from typing import Protocol, TypeVar, runtime_checkable
from uuid import UUID

from lumbago.models.base import RecordModel

RecordT = TypeVar("RecordT", bound=RecordModel)
RecordChanges = Mapping[str, object]


@runtime_checkable
class Repository(Protocol[RecordT]):
    """CRUD operations required from every Lumbago persistence adapter."""

    def create(self, record: RecordT) -> RecordT:
        """Store and return a new record."""

        ...

    def retrieve(self, record_id: UUID) -> RecordT:
        """Return one record or raise ``RecordNotFoundError``."""

        ...

    def list(self) -> tuple[RecordT, ...]:
        """Return all records in deterministic repository order."""

        ...

    def update(self, record_id: UUID, changes: RecordChanges) -> RecordT:
        """Validate, store, and return an updated record."""

        ...

    def delete(self, record_id: UUID) -> RecordT:
        """Remove and return a record or raise ``RecordNotFoundError``."""

        ...
