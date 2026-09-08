"""Tests for append-only audit logging and audited service deletion."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from lumbago import (
    Account,
    AccountType,
    AuditAction,
    AuditEvent,
    AuditLog,
    CrudService,
    DuplicateRecordError,
    InMemoryAuditLog,
    InMemoryRepository,
    RecordNotFoundError,
)

DELETED_AT = datetime(2026, 8, 28, 14, 0, tzinfo=timezone(timedelta(hours=-4)))


def make_account() -> Account:
    """Build an account for audit tests."""

    return Account(
        code="1000",
        name="Operating Cash",
        account_type=AccountType.ASSET,
        metadata={"source": {"system": "test"}},
    )


def test_in_memory_audit_log_is_append_only_and_returns_defensive_copies() -> None:
    audit_log = InMemoryAuditLog()
    event = AuditEvent(
        action=AuditAction.DELETE,
        record_type="Account",
        record_id=uuid4(),
        snapshot={"metadata": {"source": "test"}},
    )

    stored = audit_log.append(event)
    metadata = stored.snapshot["metadata"]
    assert isinstance(metadata, dict)
    metadata["source"] = "mutated"

    assert isinstance(audit_log, AuditLog)
    assert audit_log.list() == (event,)

    with pytest.raises(DuplicateRecordError):
        audit_log.append(event)


def test_service_delete_removes_record_and_appends_audit_event() -> None:
    repository = InMemoryRepository(Account)
    audit_log = InMemoryAuditLog()
    service = CrudService(
        repository,
        audit_log=audit_log,
        clock=lambda: DELETED_AT,
    )
    account = service.create(make_account())

    deleted = service.delete(account.id, actor=" Bennett ")

    assert deleted == account
    with pytest.raises(RecordNotFoundError):
        service.retrieve(account.id)

    events = service.list_audit_events()
    assert len(events) == 1
    event = events[0]
    assert event.action is AuditAction.DELETE
    assert event.record_type == "Account"
    assert event.record_id == account.id
    assert event.actor == "Bennett"
    assert event.occurred_at == datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
    assert event.occurred_at.tzinfo is UTC
    assert event.snapshot["id"] == str(account.id)
    assert event.snapshot["code"] == account.code


def test_invalid_audit_actor_does_not_delete_record() -> None:
    service = CrudService(InMemoryRepository(Account))
    account = service.create(make_account())

    with pytest.raises(ValidationError):
        service.delete(account.id, actor="")

    assert service.retrieve(account.id) == account
    assert service.list_audit_events() == ()


def test_audit_event_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        AuditEvent(
            occurred_at=datetime(2026, 8, 28),
            action=AuditAction.DELETE,
            record_type="Account",
            record_id=UUID("00000000-0000-0000-0000-000000000001"),
            snapshot={},
        )
