"""Trigger representative Lumbago validation and business-rule errors."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from pydantic import ValidationError

from lumbago import (
    Account,
    AccountService,
    AccountType,
    DuplicateCodeError,
    EntrySide,
    InMemoryRepository,
    JournalEntry,
    JournalLine,
    Money,
)


def show_error(title: str, error: Exception) -> None:
    """Print a compact labeled error."""

    print(f"\n{title}:\n  {error}")


def main() -> None:
    """Demonstrate rejected states without stopping the script."""

    accounts = AccountService(InMemoryRepository(Account))
    accounts.create(Account(code="CASH", name="Cash", account_type=AccountType.ASSET))

    try:
        accounts.create(
            Account(code="cash", name="Duplicate Cash", account_type=AccountType.ASSET)
        )
    except DuplicateCodeError as error:
        show_error("Case-insensitive duplicate code", error)

    entry_id = uuid4()
    try:
        JournalEntry(
            id=entry_id,
            journal_id=uuid4(),
            transaction_date=date.today(),
            description="An entry that does not balance",
            lines=(
                JournalLine(
                    journal_entry_id=entry_id,
                    account_id=uuid4(),
                    side=EntrySide.DEBIT,
                    amount=Money(amount=Decimal("100.00"), currency="USD"),
                ),
                JournalLine(
                    journal_entry_id=entry_id,
                    account_id=uuid4(),
                    side=EntrySide.CREDIT,
                    amount=Money(amount=Decimal("99.00"), currency="USD"),
                ),
            ),
        )
    except ValidationError as error:
        show_error("Unbalanced journal entry", error)

    try:
        Account.model_validate(
            {
                "code": "1000",
                "name": "Cash",
                "account_type": "asset",
                "unexpected_field": True,
            }
        )
    except ValidationError as error:
        show_error("Unknown field", error)


if __name__ == "__main__":
    main()
