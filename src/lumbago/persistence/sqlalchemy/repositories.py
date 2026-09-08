"""SQL repositories returning fully reconstructed, detached domain records."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapper, Session, selectinload

from lumbago.exceptions import (
    DuplicateCodeError,
    DuplicateRecordError,
    ImmutableEntryError,
    InvalidUpdateError,
    RecordNotFoundError,
    ReferencedRecordError,
    StorageError,
)
from lumbago.models.accounting import JournalEntry
from lumbago.models.audit import AuditEvent
from lumbago.models.base import RecordModel
from lumbago.persistence.sqlalchemy.mappers import audit_from_row, audit_to_row
from lumbago.persistence.sqlalchemy.models import (
    AccountRow,
    AuditRow,
    EntryRow,
    JournalRow,
    LineRow,
)
from lumbago.repositories.base import RecordChanges
from lumbago.repositories.memory import MANAGED_FIELDS

type Row = AccountRow | JournalRow | EntryRow


@contextmanager
def translate_errors(
    record_type: str, record_id: UUID | None = None, code: str | None = None
) -> Iterator[None]:
    """Translate expected constraints without exposing SQL or driver messages."""

    try:
        yield
    except IntegrityError as error:
        message = str(error.orig).lower()
        state = getattr(error.orig, "sqlstate", None)
        if "code_key" in message and code is not None:
            raise DuplicateCodeError(record_type, code) from None
        if state == "23503" or "foreign key" in message:
            raise ReferencedRecordError(
                "accounting references prevent this operation"
            ) from None
        if (
            state == "23505" or "unique constraint" in message
        ) and record_id is not None:
            raise DuplicateRecordError(record_type, record_id) from None
        raise StorageError("database rejected an accounting constraint") from None
    except SQLAlchemyError:
        raise StorageError(
            "database operation failed; the workflow was not committed"
        ) from None


class SqlRepository[RecordT: RecordModel]:
    """One typed aggregate repository participating in a caller-owned session."""

    def __init__(
        self,
        session: Session,
        record_type: type[RecordT],
        row_type: type[Row],
        to_row: Callable[[RecordT], Row],
        from_row: Callable[[Row], RecordT],
        ensure_active: Callable[[], None],
        clock: Callable[[], datetime],
    ) -> None:
        self._session = session
        self._record_type = record_type
        self._row_type = row_type
        self._to_row = to_row
        self._from_row = from_row
        self._ensure_active = ensure_active
        self._clock = clock

    def create(self, record: RecordT) -> RecordT:
        self._ensure_active()
        candidate = self._record_type.model_validate(record.model_dump(mode="python"))
        with (
            translate_errors(
                self._record_type.__name__,
                candidate.id,
                getattr(candidate, "code", None),
            ),
            self._session.begin_nested(),
        ):
            if (
                self._session.scalar(
                    select(self._row_type.id).where(self._row_type.id == candidate.id)
                )
                is not None
            ):
                raise DuplicateRecordError(self._record_type.__name__, candidate.id)
            if isinstance(candidate, JournalEntry):
                self._require_reference(JournalRow, "Journal", candidate.journal_id)
                for account_id in sorted({line.account_id for line in candidate.lines}):
                    self._require_reference(AccountRow, "Account", account_id)
                identifiers = [line.id for line in candidate.lines]
                duplicate = self._session.scalar(
                    select(LineRow.id).where(LineRow.id.in_(identifiers))
                )
                if duplicate is not None:
                    raise DuplicateRecordError("JournalLine", duplicate)
            row = self._to_row(candidate)
            self._session.add(row)
            self._session.flush()
            return self._from_row(row)

    def retrieve(self, record_id: UUID) -> RecordT:
        self._ensure_active()
        with translate_errors(self._record_type.__name__):
            return self._from_row(self._get_row(record_id))

    def list(self) -> tuple[RecordT, ...]:
        self._ensure_active()
        with translate_errors(self._record_type.__name__):
            statement = select(self._row_type).order_by(
                self._row_type.created_at, self._row_type.id
            )
            if self._row_type is EntryRow:
                statement = statement.options(selectinload(EntryRow.lines))
            return tuple(
                self._from_row(cast(Row, row))
                for row in self._session.scalars(statement)
            )

    def update(self, record_id: UUID, changes: RecordChanges) -> RecordT:
        self._ensure_active()
        existing = self.retrieve(record_id)
        if self._row_type is EntryRow:
            raise ImmutableEntryError("persisted journal entries cannot be updated")
        invalid = MANAGED_FIELDS.intersection(changes)
        if invalid:
            raise InvalidUpdateError(set(invalid))
        values = existing.model_dump(mode="python")
        values.update(changes)
        values["updated_at"] = self._clock()
        candidate = self._record_type.model_validate(values)
        with (
            translate_errors(
                self._record_type.__name__, record_id, getattr(candidate, "code", None)
            ),
            self._session.begin_nested(),
        ):
            row = self._get_row(record_id)
            replacement = self._to_row(candidate)
            for attribute in cast(Mapper[Row], inspect(self._row_type)).column_attrs:
                if attribute.key not in {"id", "created_at", "code_key"}:
                    setattr(row, attribute.key, getattr(replacement, attribute.key))
            self._session.flush()
            self._session.refresh(row)
            return self._from_row(row)

    def delete(self, record_id: UUID) -> RecordT:
        self._ensure_active()
        existing = self.retrieve(record_id)
        if self._row_type is EntryRow:
            raise ImmutableEntryError("persisted journal entries cannot be deleted")
        with (
            translate_errors(self._record_type.__name__, record_id),
            self._session.begin_nested(),
        ):
            self._session.delete(self._get_row(record_id))
            self._session.flush()
        return existing

    def _require_reference(
        self, row_type: type[AccountRow | JournalRow], record_name: str, record_id: UUID
    ) -> None:
        statement = (
            select(row_type.id).where(row_type.id == record_id).with_for_update()
        )
        if self._session.scalar(statement) is None:
            raise RecordNotFoundError(record_name, record_id)

    def _get_row(self, record_id: UUID) -> Row:
        statement = (
            select(self._row_type)
            .where(self._row_type.id == record_id)
            .with_for_update()
        )
        if self._row_type is EntryRow:
            statement = statement.options(selectinload(EntryRow.lines))
        row = self._session.scalar(statement.execution_options(populate_existing=True))
        if row is None:
            raise RecordNotFoundError(self._record_type.__name__, record_id)
        return cast(Row, row)


class SqlAuditLog:
    """Append-only durable audit storage sharing the accounting transaction."""

    def __init__(self, session: Session, ensure_active: Callable[[], None]) -> None:
        self._session = session
        self._ensure_active = ensure_active

    def append(self, event: AuditEvent) -> AuditEvent:
        self._ensure_active()
        candidate = AuditEvent.model_validate(event.model_dump(mode="python"))
        with translate_errors("AuditEvent", candidate.id), self._session.begin_nested():
            row = audit_to_row(candidate)
            self._session.add(row)
            self._session.flush()
            return audit_from_row(row)

    def list(self) -> tuple[AuditEvent, ...]:
        self._ensure_active()
        with translate_errors("AuditEvent"):
            return tuple(
                audit_from_row(row)
                for row in self._session.scalars(
                    select(AuditRow).order_by(AuditRow.occurred_at, AuditRow.id)
                )
            )
