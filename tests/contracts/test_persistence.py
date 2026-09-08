"""Storage-neutral behavioral contracts and failure-atomic workflows."""

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from luca import (
    Account,
    AccountingService,
    AuditAction,
    AuditEvent,
    DuplicateCodeError,
    DuplicateRecordError,
    ImmutableEntryError,
    InactiveAccountError,
    InvalidUpdateError,
    RecordNotFoundError,
    ReferencedRecordError,
    UnitOfWorkError,
)
from tests.conftest import Store
from tests.helpers import CREATED, UPDATED, account, entry, journal


@pytest.mark.parametrize("kind", ["accounts", "journals"])
def test_crud_ordering_validation_and_duplicates(store: Store, kind: str) -> None:
    factory = account if kind == "accounts" else journal
    first = factory("FIRST", id=UUID(int=2))
    second = factory("SECOND", id=UUID(int=1))
    with store.unit_of_work() as uow:
        repository = getattr(uow, kind)
        assert repository.create(first) == first
        repository.create(second)
        assert repository.list() == (second, first)
        assert repository.retrieve(first.id) == first
        with pytest.raises(DuplicateRecordError):
            repository.create(first)
        with pytest.raises(DuplicateCodeError):
            repository.create(factory("first"))
        with pytest.raises(DuplicateCodeError):
            repository.update(first.id, {"code": "second"})
        with pytest.raises(ValidationError):
            repository.update(first.id, {"name": ""})
        for protected in ("id", "created_at", "updated_at"):
            with pytest.raises(InvalidUpdateError):
                repository.update(first.id, {protected: uuid4()})
        updated = repository.update(first.id, {"name": "Revised", "code": "First"})
        assert updated.name == "Revised" and updated.code == "First"
        assert updated.created_at == CREATED and updated.updated_at == UPDATED
        assert repository.delete(second.id) == second
        for operation in (repository.retrieve, repository.delete):
            with pytest.raises(RecordNotFoundError):
                operation(uuid4())
        with pytest.raises(RecordNotFoundError):
            repository.update(uuid4(), {})
        uow.commit()
    with store.unit_of_work() as uow:
        assert getattr(uow, kind).list() == (updated,)


def test_declared_subclass_fields_survive_storage(
    store_factory: Callable[..., Store],
) -> None:
    class ProjectAccount(Account):
        project_code: str

    store = store_factory(account_type=ProjectAccount)
    record = ProjectAccount(**account().model_dump(), project_code="LUCA")
    with store.unit_of_work() as uow:
        service = AccountingService(uow)
        service.create_account(record)
        changed = service.update_account(
            record.id, {"code": "PROJECT", "project_code": "TWO"}
        )
        assert changed.project_code == "TWO"
        uow.commit()
    with store.unit_of_work() as uow:
        assert uow.accounts.retrieve(record.id) == changed


def test_complete_entry_and_audit_workflow(store: Store) -> None:
    cash, revenue, general = account(), account("REVENUE"), journal()
    posting = entry(cash, revenue, general)
    with store.unit_of_work() as uow:
        service = AccountingService(uow, clock=lambda: UPDATED)
        service.create_account(cash)
        service.create_account(revenue)
        service.create_journal(general)
        assert service.create_entry(posting) == posting
        assert uow.journal_entries.list() == (posting,)
        assert uow.journal_entries.retrieve(posting.id) == posting
        for operation in (service.delete_account, uow.accounts.delete):
            with pytest.raises(ReferencedRecordError):
                operation(cash.id)
        for operation in (service.delete_journal, uow.journals.delete):
            with pytest.raises(ReferencedRecordError):
                operation(general.id)
        for operation in (service.delete_entry, uow.journal_entries.delete):
            with pytest.raises(ImmutableEntryError):
                operation(posting.id)
        for operation in (service.update_entry, uow.journal_entries.update):
            with pytest.raises(ImmutableEntryError):
                operation(posting.id, {"description": "Changed"})
        service.update_account(cash.id, {"active": False})
        with pytest.raises(InactiveAccountError):
            service.create_entry(entry(cash, revenue, general))
        service.update_journal(general.id, {"name": "Renamed General"})
        unused = service.create_account(account("UNUSED"))
        empty = service.create_journal(journal("EMPTY"))
        assert service.delete_account(unused.id, actor="tester") == unused
        assert service.delete_journal(empty.id) == empty
        uow.commit()
    with store.unit_of_work() as uow:
        restored = uow.journal_entries.retrieve(posting.id)
        assert restored == posting
        assert tuple(line.id for line in restored.lines) == tuple(
            line.id for line in posting.lines
        )
        audit = uow.audit_events.list()
        assert len(audit) == 2
        deleted = next(event for event in audit if event.record_id == unused.id)
        assert deleted.snapshot == unused.model_dump(mode="json")
        assert deleted.actor == "tester" and deleted.occurred_at == UPDATED
        assert restored.lines[1].metadata["customer"] == "Acme Corp"
        returned = uow.accounts.retrieve(revenue.id)
        returned.metadata["source"]["name"] = "mutated"
        assert uow.accounts.retrieve(revenue.id).metadata["source"]["name"] == "测试"
        restored.lines[1].metadata["customer"] = "mutated"
        assert (
            uow.journal_entries.retrieve(posting.id).lines[1].metadata["customer"]
            == "Acme Corp"
        )
        deleted.snapshot["code"] = "mutated"
        assert all(
            event.snapshot["code"] != "mutated" for event in uow.audit_events.list()
        )


def test_repository_missing_references_have_consistent_errors(store: Store) -> None:
    cash, revenue, general = account(), account("REVENUE"), journal()
    posting = entry(cash, revenue, general)
    with store.unit_of_work() as uow:
        with pytest.raises(RecordNotFoundError) as missing_journal:
            uow.journal_entries.create(posting)
        assert missing_journal.value.record_type == "Journal"
        assert missing_journal.value.record_id == general.id
        uow.journals.create(general)
        uow.accounts.create(cash)
        with pytest.raises(RecordNotFoundError) as missing_account:
            uow.journal_entries.create(posting)
        assert missing_account.value.record_type == "Account"
        assert missing_account.value.record_id == revenue.id
        assert uow.journal_entries.list() == ()
        uow.commit()
    with store.unit_of_work() as uow:
        assert uow.journal_entries.list() == ()
        assert uow.journals.retrieve(general.id) == general


def test_missing_references_and_duplicate_lines(store: Store) -> None:
    cash, revenue, general = account(), account("REVENUE"), journal()
    with store.unit_of_work() as uow:
        service = AccountingService(uow)
        with pytest.raises(RecordNotFoundError):
            service.create_entry(entry(cash, revenue, general))
        service.create_journal(general)
        with pytest.raises(RecordNotFoundError):
            service.create_entry(entry(cash, revenue, general))
        service.create_account(cash)
        service.create_account(revenue)
        first = service.create_entry(entry(cash, revenue, general))
        duplicate = first.model_dump(mode="python")
        duplicate["id"] = uuid4()
        duplicate["lines"] = [
            dict(line, journal_entry_id=duplicate["id"]) for line in duplicate["lines"]
        ]
        with pytest.raises(DuplicateRecordError):
            service.create_entry(type(first).model_validate(duplicate))
        assert uow.journal_entries.list() == (first,)
        uow.commit()


@pytest.mark.parametrize("failure", ["no_commit", "exception", "rollback"])
def test_uncommitted_batches_do_not_escape(store: Store, failure: str) -> None:
    record = account()
    try:
        with store.unit_of_work() as uow:
            uow.accounts.create(record)
            if failure == "exception":
                raise RuntimeError("abort")
            if failure == "rollback":
                uow.rollback()
    except RuntimeError:
        pass
    with store.unit_of_work() as uow:
        assert uow.accounts.list() == ()


@pytest.mark.parametrize("kind", ["account", "journal"])
def test_audit_failure_restores_deletion_even_when_caught(
    store: Store, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    record = account() if kind == "account" else journal()
    with store.unit_of_work() as uow:
        service = AccountingService(uow)
        getattr(service, f"create_{kind}")(record)
        append = uow.audit_events.append

        def fail(event: AuditEvent) -> AuditEvent:
            append(event)
            raise RuntimeError("injected audit failure after append")

        monkeypatch.setattr(uow.audit_events, "append", fail)
        with pytest.raises(RuntimeError, match="injected"):
            getattr(service, f"delete_{kind}")(record.id)
        assert getattr(uow, f"{kind}s").retrieve(record.id) == record
        assert uow.audit_events.list() == ()
        uow.commit()
    with store.unit_of_work() as uow:
        assert getattr(uow, f"{kind}s").retrieve(record.id) == record


def test_audit_duplicate_and_ordering(store: Store) -> None:
    first = AuditEvent(
        id=UUID(int=2),
        occurred_at=CREATED,
        action=AuditAction.DELETE,
        record_type="Account",
        record_id=uuid4(),
        snapshot={"value": [1]},
    )
    second = first.model_copy(update={"id": UUID(int=1)})
    with store.unit_of_work() as uow:
        assert uow.audit_events.append(first) == first
        uow.audit_events.append(second)
        with pytest.raises(DuplicateRecordError):
            uow.audit_events.append(first)
        assert uow.audit_events.list() == (second, first)
        uow.commit()


def test_uow_lifetime_guards(store: Store) -> None:
    scope = store.unit_of_work()
    with pytest.raises(UnitOfWorkError):
        scope.commit()
    with scope as uow:
        with pytest.raises(UnitOfWorkError):
            scope.__enter__()
        uow.commit()
        with pytest.raises(UnitOfWorkError):
            uow.accounts.list()
        with pytest.raises(UnitOfWorkError):
            uow.rollback()
    with pytest.raises(UnitOfWorkError):
        scope.__enter__()
    with pytest.raises(UnitOfWorkError):
        scope.audit_events.list()
