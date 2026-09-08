"""Storage-neutral audit logging and an in-memory implementation."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from lumbago.exceptions import DuplicateRecordError
from lumbago.models.audit import AuditEvent


@runtime_checkable
class AuditLog(Protocol):
    """Append-only storage required for Lumbago audit events."""

    def append(self, event: AuditEvent) -> AuditEvent:
        """Store and return a new audit event."""

        ...

    def list(self) -> tuple[AuditEvent, ...]:
        """Return all audit events in deterministic order."""

        ...


class InMemoryAuditLog:
    """Store append-only audit events in memory for tests and local workflows."""

    def __init__(self) -> None:
        self._events: dict[UUID, AuditEvent] = {}

    def append(self, event: AuditEvent) -> AuditEvent:
        """Append an event while rejecting duplicate identifiers."""

        if event.id in self._events:
            raise DuplicateRecordError("AuditEvent", event.id)

        stored = self._validated_copy(event)
        self._events[stored.id] = stored
        return self._validated_copy(stored)

    def list(self) -> tuple[AuditEvent, ...]:
        """Return defensive event copies in insertion order."""

        return tuple(self._validated_copy(event) for event in self._events.values())

    @staticmethod
    def _validated_copy(event: AuditEvent) -> AuditEvent:
        return AuditEvent.model_validate(event.model_dump(mode="python"))
