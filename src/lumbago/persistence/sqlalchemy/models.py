"""Private SQL rows for the initial Lumbago accounting schema."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lumbago.persistence.sqlalchemy.base import Base, UTCDateTime, WholeHundredths

CODE_TYPE = String(64).with_variant(String(64, collation="C"), "postgresql")


class RecordColumns:
    """Shared identity, timestamps, metadata, and declared extension fields."""

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    attributes: Mapped[dict[str, JsonValue]] = mapped_column(
        "metadata", JSON, nullable=False
    )
    extensions: Mapped[dict[str, JsonValue]] = mapped_column(
        JSON, nullable=False, default=dict
    )


def code_checks() -> tuple[CheckConstraint, ...]:
    """Keep generated lower(code) equivalent to the domain's ASCII casefold."""

    return (
        CheckConstraint("length(code) BETWEEN 1 AND 64", name="code_length"),
        CheckConstraint(
            "code NOT GLOB '*[^A-Za-z0-9._-]*' AND substr(code, 1, 1) GLOB '[A-Za-z0-9]'",
            name="code_ascii_sqlite",
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            "code ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$'", name="code_ascii_postgres"
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),
        CheckConstraint("updated_at >= created_at", name="timestamp_order"),
    )


class AccountRow(RecordColumns, Base):
    """Chart-of-accounts storage with database-generated uniqueness keys."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("code_key"),
        CheckConstraint(
            "account_type IN ('asset','liability','equity','revenue','expense')",
            name="account_type",
        ),
        *code_checks(),
    )

    code: Mapped[str] = mapped_column(CODE_TYPE, nullable=False)
    code_key: Mapped[str] = mapped_column(
        CODE_TYPE, Computed("lower(code)", persisted=True), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="active_boolean"), nullable=False
    )


class JournalRow(RecordColumns, Base):
    """Journal storage with the same code rules as accounts."""

    __tablename__ = "journals"
    __table_args__ = (UniqueConstraint("code_key"), *code_checks())

    code: Mapped[str] = mapped_column(CODE_TYPE, nullable=False)
    code_key: Mapped[str] = mapped_column(
        CODE_TYPE, Computed("lower(code)", persisted=True), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))


class EntryRow(RecordColumns, Base):
    """Entry header; financial content is immutable through Lumbago repositories."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        Index("ix_journal_entries_transaction_date_id", "transaction_date", "id"),
        CheckConstraint("updated_at >= created_at", name="timestamp_order"),
        CheckConstraint(
            "length(description) BETWEEN 1 AND 1000", name="description_length"
        ),
    )

    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200))
    journal_id: Mapped[UUID] = mapped_column(
        ForeignKey("journals.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lines: Mapped[list[LineRow]] = relationship(
        cascade="all, delete-orphan", order_by="LineRow.position", lazy="raise"
    )


class LineRow(Base):
    """One ordered posting, stored as an exact integer number of hundredths."""

    __tablename__ = "journal_lines"
    __table_args__ = (
        UniqueConstraint("journal_entry_id", "position"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("side IN ('debit', 'credit')", name="side"),
        CheckConstraint(
            "amount_minor BETWEEN 1 AND 999999999999999999", name="amount_range"
        ),
        CheckConstraint(
            "typeof(amount_minor) = 'integer'", name="amount_whole_sqlite"
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            "amount_minor = trunc(amount_minor)", name="amount_whole_postgres"
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("length(currency) = 3", name="currency_length"),
        CheckConstraint(
            "currency NOT GLOB '*[^A-Z]*'", name="currency_ascii_sqlite"
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="currency_ascii_postgres"
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    journal_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    side: Mapped[str] = mapped_column(String(6), nullable=False)
    amount_minor: Mapped[int] = mapped_column(WholeHundredths, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    attributes: Mapped[dict[str, JsonValue]] = mapped_column(
        "metadata", JSON, nullable=False
    )


class AuditRow(Base):
    """Durable audit snapshot, deliberately independent of deleted records."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index(
            "ix_audit_events_record_history", "record_type", "record_id", "occurred_at"
        ),
        CheckConstraint("action = 'delete'", name="action"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    record_type: Mapped[str] = mapped_column(String(200), nullable=False)
    record_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor: Mapped[str | None] = mapped_column(String(200))
    snapshot: Mapped[dict[str, JsonValue]] = mapped_column(JSON, nullable=False)
