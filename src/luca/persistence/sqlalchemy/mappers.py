"""Explicit, defensive translations between SQL rows and public Luca values."""

from copy import deepcopy

from luca.models.accounting import Account, Journal, JournalEntry, JournalLine
from luca.models.audit import AuditEvent
from luca.models.base import RecordModel
from luca.models.money import from_minor_units
from luca.persistence.sqlalchemy.models import (
    AccountRow,
    AuditRow,
    EntryRow,
    JournalRow,
    LineRow,
    RecordColumns,
)


def record_values(
    record: RecordModel, base_type: type[RecordModel]
) -> dict[str, object]:
    """Separate stable storage fields from JSON-serializable subclass additions."""

    values = record.model_dump(mode="json")
    return {
        "id": record.id,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "attributes": deepcopy(record.metadata),
        "extensions": {
            key: value
            for key, value in values.items()
            if key not in base_type.model_fields
        },
    }


def domain_values(
    row: RecordColumns, base_type: type[RecordModel]
) -> dict[str, object]:
    """Never let extension data overwrite the authoritative core columns."""

    if set(row.extensions) & base_type.model_fields.keys():
        raise ValueError("stored extension data conflicts with core fields")
    return {
        **deepcopy(row.extensions),
        "id": row.id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "metadata": deepcopy(row.attributes),
    }


def account_to_row(record: Account) -> AccountRow:
    return AccountRow(
        **record_values(record, Account),
        code=record.code,
        name=record.name,
        account_type=record.account_type.value,
        description=record.description,
        active=record.active,
    )


def account_from_row(row: AccountRow, model: type[Account] = Account) -> Account:
    return model.model_validate(
        {
            **domain_values(row, Account),
            "code": row.code,
            "name": row.name,
            "account_type": row.account_type,
            "description": row.description,
            "active": row.active,
        }
    )


def journal_to_row(record: Journal) -> JournalRow:
    return JournalRow(
        **record_values(record, Journal),
        code=record.code,
        name=record.name,
        description=record.description,
    )


def journal_from_row(row: JournalRow, model: type[Journal] = Journal) -> Journal:
    return model.model_validate(
        {
            **domain_values(row, Journal),
            "code": row.code,
            "name": row.name,
            "description": row.description,
        }
    )


def entry_to_row(record: JournalEntry) -> EntryRow:
    return EntryRow(
        **record_values(record, JournalEntry),
        journal_id=record.journal_id,
        transaction_date=record.transaction_date,
        description=record.description,
        reference=record.reference,
        lines=[
            LineRow(
                id=line.id,
                journal_entry_id=record.id,
                position=position,
                account_id=line.account_id,
                side=line.side.value,
                amount_minor=line.amount.minor_units,
                currency=line.amount.currency,
                description=line.description,
                attributes=deepcopy(line.metadata),
            )
            for position, line in enumerate(record.lines)
        ],
    )


def entry_from_row(
    row: EntryRow, model: type[JournalEntry] = JournalEntry
) -> JournalEntry:
    return model.model_validate(
        {
            **domain_values(row, JournalEntry),
            "journal_id": row.journal_id,
            "transaction_date": row.transaction_date,
            "description": row.description,
            "reference": row.reference,
            "lines": tuple(
                JournalLine.model_validate(
                    {
                        "id": line.id,
                        "journal_entry_id": row.id,
                        "account_id": line.account_id,
                        "side": line.side,
                        "amount": {
                            "amount": from_minor_units(line.amount_minor),
                            "currency": line.currency,
                        },
                        "description": line.description,
                        "metadata": deepcopy(line.attributes),
                    }
                )
                for line in sorted(row.lines, key=lambda item: item.position)
            ),
        }
    )


def audit_to_row(event: AuditEvent) -> AuditRow:
    values = event.model_dump(mode="python")
    values["snapshot"] = deepcopy(event.snapshot)
    return AuditRow(**values)


def audit_from_row(row: AuditRow) -> AuditEvent:
    return AuditEvent.model_validate(
        {
            "id": row.id,
            "occurred_at": row.occurred_at,
            "action": row.action,
            "record_type": row.record_type,
            "record_id": row.record_id,
            "actor": row.actor,
            "snapshot": deepcopy(row.snapshot),
        }
    )
