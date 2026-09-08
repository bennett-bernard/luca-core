"""Tests for Lumbago's core accounting data model."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from lumbago import (
    Account,
    AccountType,
    BaseTransaction,
    EntrySide,
    JournalEntry,
    JournalLine,
    Money,
)

DEBIT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")
CREDIT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000002")
JOURNAL_ID = UUID("00000000-0000-0000-0000-000000000003")
ENTRY_ID = UUID("00000000-0000-0000-0000-000000000004")


def make_line(
    side: EntrySide,
    amount: str = "100.00",
    currency: str = "USD",
    *,
    line_id: UUID | None = None,
    journal_entry_id: UUID = ENTRY_ID,
) -> JournalLine:
    """Build a representative journal line for tests."""

    account_id = DEBIT_ACCOUNT_ID if side is EntrySide.DEBIT else CREDIT_ACCOUNT_ID
    values: dict[str, object] = {
        "journal_entry_id": journal_entry_id,
        "account_id": account_id,
        "side": side,
        "amount": Money(amount=Decimal(amount), currency=currency),
    }
    if line_id is not None:
        values["id"] = line_id
    return JournalLine.model_validate(values)


def make_entry(*lines: JournalLine, entry_id: UUID = ENTRY_ID) -> JournalEntry:
    """Build a journal entry from the supplied lines."""

    return JournalEntry(
        id=entry_id,
        journal_id=JOURNAL_ID,
        transaction_date=date(2026, 8, 22),
        description="Record a cash sale",
        reference="SALE-42",
        lines=lines or (make_line(EntrySide.DEBIT), make_line(EntrySide.CREDIT)),
    )


def test_money_uses_decimal_and_normalizes_currency() -> None:
    money = Money(amount="12.34", currency=" usd ")

    assert money.amount == Decimal("12.34")
    assert money.currency == "USD"


@pytest.mark.parametrize("currency", ["US", "USDX", "U1D", 840])
def test_money_rejects_invalid_currency_codes(currency: object) -> None:
    with pytest.raises(ValidationError):
        Money.model_validate({"amount": "1.00", "currency": currency})


def test_journal_line_requires_a_positive_amount() -> None:
    with pytest.raises(ValidationError, match="greater than zero"):
        JournalLine(
            journal_entry_id=ENTRY_ID,
            account_id=DEBIT_ACCOUNT_ID,
            side=EntrySide.DEBIT,
            amount=Money(amount="0", currency="USD"),
        )


def test_journal_entry_accepts_balanced_lines() -> None:
    entry = make_entry()

    assert len(entry.lines) == 2
    assert entry.lines[0].journal_entry_id == entry.id
    assert entry.lines[0].side is EntrySide.DEBIT
    assert entry.lines[1].side is EntrySide.CREDIT


def test_journal_entry_balances_every_currency_independently() -> None:
    entry = make_entry(
        make_line(EntrySide.DEBIT, "100.00", "USD"),
        make_line(EntrySide.CREDIT, "100.00", "USD"),
        make_line(EntrySide.DEBIT, "75.00", "EUR"),
        make_line(EntrySide.CREDIT, "75.00", "EUR"),
    )

    assert {line.amount.currency for line in entry.lines} == {"EUR", "USD"}


def test_journal_entry_rejects_unbalanced_lines() -> None:
    with pytest.raises(ValidationError, match="unbalanced currencies: USD"):
        make_entry(
            make_line(EntrySide.DEBIT, "100.00"),
            make_line(EntrySide.CREDIT, "99.99"),
        )


def test_journal_entry_rejects_lines_from_another_parent() -> None:
    with pytest.raises(ValidationError, match="owning journal entry"):
        make_entry(
            make_line(EntrySide.DEBIT, journal_entry_id=uuid4()),
            make_line(EntrySide.CREDIT),
        )


def test_journal_entry_rejects_duplicate_line_identifiers() -> None:
    line_id = uuid4()

    with pytest.raises(ValidationError, match="identifiers must be unique"):
        make_entry(
            make_line(EntrySide.DEBIT, line_id=line_id),
            make_line(EntrySide.CREDIT, line_id=line_id),
        )


def test_records_require_ordered_timezone_aware_timestamps() -> None:
    with pytest.raises(ValidationError, match="updated_at must be on or after"):
        Account(
            code="1000",
            name="Cash",
            account_type=AccountType.ASSET,
            created_at=datetime(2026, 8, 23, tzinfo=UTC),
            updated_at=datetime(2026, 8, 22, tzinfo=UTC),
        )

    with pytest.raises(ValidationError):
        Account(
            code="1000",
            name="Cash",
            account_type=AccountType.ASSET,
            created_at=datetime(2026, 8, 22),
            updated_at=datetime(2026, 8, 22),
        )


def test_records_normalize_aware_timestamps_to_utc() -> None:
    eastern = timezone(timedelta(hours=-4))
    account = Account(
        code="1000",
        name="Cash",
        account_type=AccountType.ASSET,
        created_at=datetime(2026, 8, 22, 8, 0, tzinfo=eastern),
        updated_at=datetime(2026, 8, 22, 9, 0, tzinfo=eastern),
    )

    assert account.created_at == datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    assert account.updated_at == datetime(2026, 8, 22, 13, 0, tzinfo=UTC)
    assert account.created_at.tzinfo is UTC
    assert account.updated_at.tzinfo is UTC


def test_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Account.model_validate(
            {
                "code": "1000",
                "name": "Cash",
                "account_type": "asset",
                "unexpected": True,
            }
        )


def test_subclasses_can_declare_additional_fields() -> None:
    class ProjectAccount(Account):
        project_code: str

    account = ProjectAccount(
        code="1000",
        name="Cash",
        account_type=AccountType.ASSET,
        project_code="LUMBAGO",
    )

    assert account.project_code == "LUMBAGO"


def test_journal_entry_round_trips_through_json() -> None:
    entry = make_entry()

    restored = JournalEntry.model_validate_json(entry.model_dump_json())

    assert restored == entry


def test_public_schema_contains_verbose_field_descriptions() -> None:
    schema = BaseTransaction.model_json_schema()

    assert "Accounting date" in schema["properties"]["transaction_date"]["description"]
    assert "external" in schema["properties"]["reference"]["description"]
