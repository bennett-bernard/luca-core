"""Core accounting records for accounts, journals, and journal entries."""

from collections import defaultdict
from datetime import date
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import Field, JsonValue, field_validator, model_validator

from luca.models.base import LucaModel, RecordModel
from luca.models.money import Money


class AccountType(StrEnum):
    """Fundamental accounting classification for an account."""

    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class EntrySide(StrEnum):
    """The debit or credit side of a journal line."""

    DEBIT = "debit"
    CREDIT = "credit"


class Account(RecordModel):
    """A minimal account that can be referenced by journal lines."""

    code: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description=(
            "Human-facing identifier from the chart of accounts, such as 1000 or "
            "cash.operating. Codes are unique within a Luca data store."
        ),
        examples=["1000"],
    )
    name: str = Field(
        min_length=1,
        max_length=200,
        description="Concise human-readable name of the account.",
        examples=["Operating Cash"],
    )
    account_type: AccountType = Field(
        description=(
            "Fundamental accounting classification used to interpret the account's "
            "role in financial activity."
        ),
        examples=[AccountType.ASSET],
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional explanation of the account's intended use.",
    )
    active: bool = Field(
        default=True,
        description=(
            "Whether the account can be used for new journal lines. Inactive accounts "
            "remain available for historical records."
        ),
    )


class Journal(RecordModel):
    """A named collection used to organize journal entries."""

    code: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description=(
            "Short human-facing identifier for the journal, unique within a Luca data "
            "store."
        ),
        examples=["GENERAL"],
    )
    name: str = Field(
        min_length=1,
        max_length=200,
        description="Concise human-readable name of the journal.",
        examples=["General Journal"],
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional explanation of the journal's intended use.",
    )


class JournalLine(LucaModel):
    """One debit or credit posting within a journal entry."""

    id: UUID = Field(
        default_factory=uuid4,
        description="Stable unique identifier for this line within its journal entry.",
    )
    journal_entry_id: UUID = Field(
        description="Identifier of the journal entry that owns this line."
    )
    account_id: UUID = Field(
        description="Identifier of the account affected by this journal line."
    )
    side: EntrySide = Field(
        description="Whether the amount is posted as a debit or a credit."
    )
    amount: Money = Field(
        description=(
            "Positive amount and currency posted to the selected side of the account."
        )
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional line-level explanation or memo.",
    )
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Caller-defined JSON-compatible attributes for this line.",
    )

    @field_validator("amount")
    @classmethod
    def require_positive_amount(cls, value: Money) -> Money:
        """Reject zero-value lines, which carry no accounting effect."""

        if value.amount == 0:
            raise ValueError("journal line amount must be greater than zero")
        return value


class BaseTransaction(RecordModel):
    """Common identity and descriptive fields for accounting transactions."""

    transaction_date: date = Field(
        description=(
            "Accounting date on which the transaction is recognized, independent of "
            "the timestamp when it was entered into Luca."
        ),
        examples=["2026-08-22"],
    )
    description: str = Field(
        min_length=1,
        max_length=1000,
        description="Human-readable explanation of the transaction's purpose.",
        examples=["Record monthly office rent"],
    )
    reference: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Optional external or human-facing reference, such as an invoice number "
            "or source-system identifier."
        ),
        examples=["INV-2026-0042"],
    )


class JournalEntry(BaseTransaction):
    """A balanced collection of debit and credit journal lines."""

    journal_id: UUID = Field(
        description="Identifier of the journal that owns this entry."
    )
    lines: tuple[JournalLine, ...] = Field(
        min_length=2,
        description=(
            "Two or more postings that balance debits and credits independently for "
            "every currency represented in the entry."
        ),
    )

    @model_validator(mode="after")
    def validate_lines(self) -> Self:
        """Require unique lines and balanced debits and credits per currency."""

        mismatched_parent_ids = [
            line.id for line in self.lines if line.journal_entry_id != self.id
        ]
        if mismatched_parent_ids:
            raise ValueError(
                "every journal line must reference its owning journal entry"
            )

        line_ids = [line.id for line in self.lines]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("journal entry line identifiers must be unique")

        totals: dict[str, dict[EntrySide, int]] = defaultdict(
            lambda: {EntrySide.DEBIT: 0, EntrySide.CREDIT: 0}
        )
        for line in self.lines:
            totals[line.amount.currency][line.side] += line.amount.minor_units

        unbalanced = [
            currency
            for currency, sides in sorted(totals.items())
            if sides[EntrySide.DEBIT] != sides[EntrySide.CREDIT]
        ]
        if unbalanced:
            currencies = ", ".join(unbalanced)
            raise ValueError(
                "journal entry debits and credits must balance for each currency; "
                f"unbalanced currencies: {currencies}"
            )
        return self
