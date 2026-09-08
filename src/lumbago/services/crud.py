"""Application-level CRUD operations for Lumbago records."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from lumbago.models.audit import AuditAction, AuditEvent
from lumbago.models.base import RecordModel, utc_now
from lumbago.repositories.audit import AuditLog, InMemoryAuditLog
from lumbago.repositories.base import RecordChanges, Repository


class CrudService[RecordT: RecordModel]:
    """Expose consistent record operations independently of storage technology."""

    def __init__(
        self,
        repository: Repository[RecordT],
        *,
        audit_log: AuditLog | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._audit_log = audit_log if audit_log is not None else InMemoryAuditLog()
        self._clock = clock

    def create(self, record: RecordT) -> RecordT:
        """Create a validated record."""

        return self._repository.create(record)

    def retrieve(self, record_id: UUID) -> RecordT:
        """Retrieve a record by its stable identifier."""

        return self._repository.retrieve(record_id)

    def list(self) -> tuple[RecordT, ...]:
        """List all records available to this service."""

        return self._repository.list()

    def update(self, record_id: UUID, changes: RecordChanges) -> RecordT:
        """Apply a validated partial update to a record."""

        return self._repository.update(record_id, changes)

    def delete(self, record_id: UUID, *, actor: str | None = None) -> RecordT:
        """Delete a record and append an immutable audit event."""

        existing = self.retrieve(record_id)
        event = AuditEvent(
            occurred_at=self._clock(),
            action=AuditAction.DELETE,
            record_type=type(existing).__name__,
            record_id=existing.id,
            actor=actor,
            snapshot=existing.model_dump(mode="json"),
        )
        deleted = self._repository.delete(record_id)
        self._audit_log.append(event)
        return deleted

    def list_audit_events(self) -> tuple[AuditEvent, ...]:
        """List audit events visible through this service's audit log."""

        return self._audit_log.list()
