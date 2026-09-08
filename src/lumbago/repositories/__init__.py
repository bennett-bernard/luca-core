"""Repository contracts and built-in adapters."""

from lumbago.repositories.audit import AuditLog, InMemoryAuditLog
from lumbago.repositories.base import RecordChanges, Repository
from lumbago.repositories.memory import InMemoryRepository

__all__ = [
    "AuditLog",
    "InMemoryAuditLog",
    "InMemoryRepository",
    "RecordChanges",
    "Repository",
]
