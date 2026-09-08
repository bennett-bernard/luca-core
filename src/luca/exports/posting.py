"""Flat posting data suitable for spreadsheets and other output adapters."""

import json
from collections.abc import Iterable
from datetime import date
from uuid import UUID

from pydantic import Field

from luca.exceptions import RecordNotFoundError
from luca.models.accounting import Account, EntrySide, Journal, JournalEntry
from luca.models.base import LucaModel


class PostingRow(LucaModel):
    """One journal line with account and journal names resolved at export time."""

    entry_id: UUID
    transaction_date: date
    reference: str | None
    entry_description: str
    journal_id: UUID
    journal_code: str
    journal_name: str
    line_id: UUID
    line_position: int = Field(ge=0)
    account_id: UUID
    account_code: str
    account_name: str
    side: EntrySide
    amount: str = Field(pattern=r"^[0-9]+\.[0-9]{2}$")
    currency: str
    line_description: str | None
    line_metadata: str


def project_postings(
    entries: Iterable[JournalEntry],
    accounts: Iterable[Account],
    journals: Iterable[Journal],
) -> tuple[PostingRow, ...]:
    """Resolve references once; order by entry date, UUID, and zero-based position.

    This is a current-name projection, not a historical-name snapshot. Supply
    all inputs from one unit of work when consistency with concurrent edits is
    needed. Entries and master records are materialized in this first version.
    """

    account_map = {account.id: account for account in accounts}
    journal_map = {journal.id: journal for journal in journals}
    rows: list[PostingRow] = []
    for entry in sorted(entries, key=lambda item: (item.transaction_date, item.id)):
        if entry.journal_id not in journal_map:
            raise RecordNotFoundError("Journal", entry.journal_id)
        journal = journal_map[entry.journal_id]
        for position, line in enumerate(entry.lines):
            if line.account_id not in account_map:
                raise RecordNotFoundError("Account", line.account_id)
            account = account_map[line.account_id]
            rows.append(
                PostingRow(
                    entry_id=entry.id,
                    transaction_date=entry.transaction_date,
                    reference=entry.reference,
                    entry_description=entry.description,
                    journal_id=journal.id,
                    journal_code=journal.code,
                    journal_name=journal.name,
                    line_id=line.id,
                    line_position=position,
                    account_id=account.id,
                    account_code=account.code,
                    account_name=account.name,
                    side=line.side,
                    amount=format(line.amount.amount, ".2f"),
                    currency=line.amount.currency,
                    line_description=line.description,
                    line_metadata=json.dumps(
                        line.metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ),
                )
            )
    return tuple(rows)
