"""Contract tests for the in-memory repository and CRUD service."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from lumbago import (
    Account,
    AccountType,
    CrudService,
    DuplicateRecordError,
    InMemoryRepository,
    InvalidUpdateError,
    RecordNotFoundError,
    Repository,
)

CREATED_AT = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
UPDATED_AT = datetime(2026, 8, 22, 11, 0, tzinfo=UTC)


def make_account(
    record_id: UUID | None = None,
    *,
    code: str = "1000",
) -> Account:
    """Build a deterministic account record for repository tests."""

    return Account(
        id=record_id or uuid4(),
        code=code,
        name="Operating Cash",
        account_type=AccountType.ASSET,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
        metadata={"source": {"system": "test"}},
    )


def make_repository() -> InMemoryRepository[Account]:
    return InMemoryRepository(Account, clock=lambda: UPDATED_AT)


def test_repository_implements_storage_neutral_contract() -> None:
    assert isinstance(make_repository(), Repository)


def test_create_retrieve_and_list_records() -> None:
    repository = make_repository()
    first = make_account(code="1000")
    second = make_account(code="1100")

    created = repository.create(first)
    repository.create(second)

    assert created == first
    assert created is not first
    assert repository.retrieve(first.id) == first
    assert repository.list() == (first, second)


def test_repository_returns_defensive_copies() -> None:
    repository = make_repository()
    account = repository.create(make_account())

    source = account.metadata["source"]
    assert isinstance(source, dict)
    source["system"] = "mutated"

    assert repository.retrieve(account.id).metadata == {"source": {"system": "test"}}


def test_repository_preserves_declared_subclass_fields() -> None:
    class ProjectAccount(Account):
        project_code: str

    repository = InMemoryRepository(ProjectAccount)
    account = ProjectAccount(
        code="1000",
        name="Project Cash",
        account_type=AccountType.ASSET,
        project_code="LUMBAGO",
    )

    assert repository.create(account).project_code == "LUMBAGO"
    assert repository.retrieve(account.id) == account


def test_create_rejects_duplicate_identifiers() -> None:
    repository = make_repository()
    record_id = uuid4()
    repository.create(make_account(record_id))

    with pytest.raises(DuplicateRecordError, match="already exists"):
        repository.create(make_account(record_id, code="1001"))


def test_update_revalidates_data_and_manages_timestamps() -> None:
    repository = make_repository()
    account = repository.create(make_account())

    updated = repository.update(account.id, {"name": "Cash on Hand"})

    assert updated.id == account.id
    assert updated.created_at == CREATED_AT
    assert updated.updated_at == UPDATED_AT
    assert updated.name == "Cash on Hand"


def test_failed_update_does_not_change_stored_record() -> None:
    repository = make_repository()
    account = repository.create(make_account())

    with pytest.raises(ValidationError):
        repository.update(account.id, {"name": ""})

    assert repository.retrieve(account.id) == account


@pytest.mark.parametrize("field", ["id", "created_at", "updated_at"])
def test_update_rejects_changes_to_managed_fields(field: str) -> None:
    repository = make_repository()
    account = repository.create(make_account())

    with pytest.raises(InvalidUpdateError, match=field):
        repository.update(account.id, {field: uuid4()})


def test_delete_returns_record_and_removes_it() -> None:
    repository = make_repository()
    account = repository.create(make_account())

    assert repository.delete(account.id) == account

    with pytest.raises(RecordNotFoundError, match="was not found"):
        repository.retrieve(account.id)


def test_missing_records_raise_domain_error() -> None:
    repository = make_repository()
    missing_id = uuid4()

    with pytest.raises(RecordNotFoundError) as error:
        repository.retrieve(missing_id)

    assert error.value.record_type == "Account"
    assert error.value.record_id == missing_id

    with pytest.raises(RecordNotFoundError):
        repository.delete(missing_id)


def test_crud_service_exposes_full_record_lifecycle() -> None:
    service = CrudService(make_repository())
    account = make_account()

    assert service.create(account) == account
    assert service.retrieve(account.id) == account
    assert service.update(account.id, {"active": False}).active is False
    assert len(service.list()) == 1
    assert service.delete(account.id).id == account.id
    assert service.list() == ()
