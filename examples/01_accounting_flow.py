"""Create accounts, a journal, and a balanced journal entry."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from lumbago import (
    Account,
    AccountService,
    AccountType,
    CrudService,
    EntrySide,
    InMemoryRepository,
    Journal,
    JournalEntry,
    JournalLine,
    JournalService,
    Money,
)


def main() -> None:
    """Run a complete in-memory accounting flow."""

    accounts = AccountService(InMemoryRepository(Account))
    journals = JournalService(InMemoryRepository(Journal))
    entries = CrudService(InMemoryRepository(JournalEntry))

    cash = accounts.create(
        Account(code="1000", name="Operating Cash", account_type=AccountType.ASSET)
    )
    revenue = accounts.create(
        Account(code="4000", name="Sales Revenue", account_type=AccountType.REVENUE)
    )
    general = journals.create(Journal(code="GENERAL", name="General Journal"))

    entry_id = uuid4()
    entry = entries.create(
        JournalEntry(
            id=entry_id,
            journal_id=general.id,
            transaction_date=date.today(),
            description="Record a cash sale",
            reference="SALE-001",
            lines=(
                JournalLine(
                    journal_entry_id=entry_id,
                    account_id=cash.id,
                    side=EntrySide.DEBIT,
                    amount=Money(amount=Decimal("125.00"), currency="USD"),
                ),
                JournalLine(
                    journal_entry_id=entry_id,
                    account_id=revenue.id,
                    side=EntrySide.CREDIT,
                    amount=Money(amount=Decimal("125.00"), currency="USD"),
                    metadata={"customer": "Acme Corp"},
                ),
            ),
        )
    )

    print("Created a balanced journal entry:")
    print(entry.model_dump_json(indent=2))

    accounts_by_id = {account.id: account for account in accounts.list()}
    print("\nPosting summary (account details resolved from account_id):")
    for line in entry.lines:
        account = accounts_by_id[line.account_id]
        customer = line.metadata.get("customer")
        customer_label = f" | customer: {customer}" if customer else ""
        print(
            f"  {line.side.value}: {account.code} - {account.name} | "
            f"{line.amount.amount} {line.amount.currency}{customer_label}"
        )

    print(f"\nStored accounts: {len(accounts.list())}")
    print(f"Stored journals: {len(journals.list())}")
    print(f"Stored entries: {len(entries.list())}")


if __name__ == "__main__":
    main()
