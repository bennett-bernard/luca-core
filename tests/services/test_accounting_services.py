"""Tests for accounting-specific service rules."""

from uuid import uuid4

import pytest

from lumbago import (
    Account,
    AccountService,
    AccountType,
    DuplicateCodeError,
    InMemoryRepository,
    InvalidUpdateError,
    Journal,
    JournalService,
)


def make_account(code: str) -> Account:
    """Build an account with the supplied code."""

    return Account(
        code=code,
        name=f"Account {code}",
        account_type=AccountType.ASSET,
    )


def make_journal(code: str) -> Journal:
    """Build a journal with the supplied code."""

    return Journal(code=code, name=f"Journal {code}")


def test_account_service_enforces_case_insensitive_code_uniqueness() -> None:
    service = AccountService(InMemoryRepository(Account))
    cash = service.create(make_account("Cash"))
    receivables = service.create(make_account("AR"))

    with pytest.raises(DuplicateCodeError) as error:
        service.create(make_account("cash"))

    assert error.value.record_type == "Account"
    assert error.value.code == "cash"
    assert service.list() == (cash, receivables)

    with pytest.raises(DuplicateCodeError):
        service.update(receivables.id, {"code": " CASH "})

    updated = service.update(cash.id, {"code": "CASH"})
    assert updated.code == "CASH"
    assert service.update(receivables.id, {"name": "Receivables"}).name == "Receivables"


def test_journal_service_enforces_case_insensitive_code_uniqueness() -> None:
    service = JournalService(InMemoryRepository(Journal))
    general = service.create(make_journal("GENERAL"))
    sales = service.create(make_journal("SALES"))

    with pytest.raises(DuplicateCodeError) as error:
        service.create(make_journal("general"))

    assert error.value.record_type == "Journal"
    assert error.value.code == "general"
    assert service.list() == (general, sales)

    with pytest.raises(DuplicateCodeError):
        service.update(sales.id, {"code": "General"})

    renamed = service.update(general.id, {"code": "general"})
    assert renamed.code == "general"
    assert service.update(sales.id, {"description": "Sales journal"}).description == (
        "Sales journal"
    )


def test_uniqueness_update_still_validates_the_complete_record() -> None:
    service = AccountService(InMemoryRepository(Account))
    account = service.create(make_account("1000"))

    with pytest.raises(ValueError):
        service.update(account.id, {"code": "invalid code"})

    with pytest.raises(InvalidUpdateError):
        service.update(account.id, {"id": uuid4(), "code": "2000"})
