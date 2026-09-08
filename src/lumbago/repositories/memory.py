"""In-memory repository for testing and lightweight local workflows."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from lumbago.exceptions import (
    DuplicateRecordError,
    InvalidUpdateError,
    RecordNotFoundError,
)
from lumbago.models.base import RecordModel, utc_now
from lumbago.repositories.base import RecordChanges

MANAGED_FIELDS = frozenset({"id", "created_at", "updated_at"})


class InMemoryRepository[RecordT: RecordModel]:
    """Store validated records in memory behind the repository contract.

    Returned records are defensive copies so caller mutations of nested metadata
    cannot alter the repository's stored state.
    """

    def __init__(
        self,
        record_type: type[RecordT],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._record_type = record_type
        self._clock = clock
        self._records: dict[UUID, RecordT] = {}

    def create(self, record: RecordT) -> RecordT:
        """Store a new record, rejecting duplicate identifiers."""

        if record.id in self._records:
            raise DuplicateRecordError(self._record_name, record.id)

        stored = self._validated_copy(record)
        self._records[stored.id] = stored
        return self._validated_copy(stored)

    def retrieve(self, record_id: UUID) -> RecordT:
        """Retrieve a record by identifier."""

        try:
            record = self._records[record_id]
        except KeyError as error:
            raise RecordNotFoundError(self._record_name, record_id) from error
        return self._validated_copy(record)

    def list(self) -> tuple[RecordT, ...]:
        """Return records in insertion order."""

        return tuple(self._validated_copy(record) for record in self._records.values())

    def update(self, record_id: UUID, changes: RecordChanges) -> RecordT:
        """Apply a validated partial update while preserving managed fields."""

        existing = self.retrieve(record_id)
        invalid_fields = MANAGED_FIELDS.intersection(changes)
        if invalid_fields:
            raise InvalidUpdateError(set(invalid_fields))

        values = existing.model_dump(mode="python")
        values.update(changes)
        values["updated_at"] = self._clock()
        updated = self._record_type.model_validate(values)
        self._records[record_id] = updated
        return self._validated_copy(updated)

    def delete(self, record_id: UUID) -> RecordT:
        """Remove and return a record by identifier."""

        try:
            record = self._records.pop(record_id)
        except KeyError as error:
            raise RecordNotFoundError(self._record_name, record_id) from error
        return self._validated_copy(record)

    @property
    def _record_name(self) -> str:
        return self._record_type.__name__

    def _validated_copy(self, record: RecordT) -> RecordT:
        return self._record_type.model_validate(record.model_dump(mode="python"))
