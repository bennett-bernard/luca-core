"""Representative accounting data shared by backend contract tests."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from lumbago import (
    Account,
    AccountType,
    EntrySide,
    Journal,
    JournalEntry,
    JournalLine,
    Money,
)

CREATED = datetime(2026, 9, 1, 12, tzinfo=UTC)
UPDATED = datetime(2026, 9, 2, 12, tzinfo=UTC)


def account(code: str = "CASH", **kwargs: object) -> Account:
    return Account.model_validate(
        {
            "code": code,
            "name": "Cash, operating",
            "account_type": AccountType.ASSET,
            "created_at": CREATED,
            "updated_at": CREATED,
            "metadata": {"source": {"name": "测试"}},
            **kwargs,
        }
    )


def journal(code: str = "GENERAL", **kwargs: object) -> Journal:
    return Journal.model_validate(
        {
            "code": code,
            "name": "General Journal",
            "created_at": CREATED,
            "updated_at": CREATED,
            **kwargs,
        }
    )


def entry(
    cash: Account,
    revenue: Account,
    general: Journal,
    *,
    amount: str = "125.00",
    entry_id: UUID | None = None,
) -> JournalEntry:
    identity = entry_id or uuid4()
    return JournalEntry(
        id=identity,
        journal_id=general.id,
        transaction_date=date(2026, 9, 1),
        created_at=CREATED,
        updated_at=CREATED,
        description='Sale, with "quotes"\nand a newline',
        lines=(
            JournalLine(
                journal_entry_id=identity,
                account_id=cash.id,
                side=EntrySide.DEBIT,
                amount=Money(amount=amount, currency="USD"),
            ),
            JournalLine(
                journal_entry_id=identity,
                account_id=revenue.id,
                side=EntrySide.CREDIT,
                amount=Money(amount=amount, currency="USD"),
                metadata={"z": "élève", "customer": "Acme Corp"},
            ),
        ),
    )
