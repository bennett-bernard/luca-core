"""Accounting-specific services and cross-record business rules."""

from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from luca.exceptions import DuplicateCodeError
from luca.models.accounting import Account, Journal
from luca.repositories.base import RecordChanges
from luca.services.crud import CrudService


class _CodedRecord(Protocol):
    id: UUID
    code: str


def _require_unique_code(
    record_type: str,
    records: Iterable[_CodedRecord],
    code: str,
    *,
    excluding_id: UUID | None = None,
) -> None:
    normalized_code = code.casefold()
    if any(
        record.id != excluding_id and record.code.casefold() == normalized_code
        for record in records
    ):
        raise DuplicateCodeError(record_type, code)


class AccountService(CrudService[Account]):
    """Manage accounts while enforcing case-insensitive code uniqueness."""

    def create(self, record: Account) -> Account:
        """Create an account whose code is not already in use."""

        _require_unique_code("Account", self.list(), record.code)
        return super().create(record)

    def update(self, record_id: UUID, changes: RecordChanges) -> Account:
        """Update an account without duplicating another account's code."""

        if "code" in changes:
            existing = self.retrieve(record_id)
            values = existing.model_dump(mode="python")
            values.update(changes)
            candidate = type(existing).model_validate(values)
            _require_unique_code(
                "Account",
                self.list(),
                candidate.code,
                excluding_id=record_id,
            )
        return super().update(record_id, changes)


class JournalService(CrudService[Journal]):
    """Manage journals while enforcing case-insensitive code uniqueness."""

    def create(self, record: Journal) -> Journal:
        """Create a journal whose code is not already in use."""

        _require_unique_code("Journal", self.list(), record.code)
        return super().create(record)

    def update(self, record_id: UUID, changes: RecordChanges) -> Journal:
        """Update a journal without duplicating another journal's code."""

        if "code" in changes:
            existing = self.retrieve(record_id)
            values = existing.model_dump(mode="python")
            values.update(changes)
            candidate = type(existing).model_validate(values)
            _require_unique_code(
                "Journal",
                self.list(),
                candidate.code,
                excluding_id=record_id,
            )
        return super().update(record_id, changes)
