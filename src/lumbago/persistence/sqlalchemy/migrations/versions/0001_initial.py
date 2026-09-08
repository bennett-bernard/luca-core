"""Create the initial accounting schema, frozen independently of live ORM rows."""

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def record_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("extensions", sa.JSON(), nullable=False),
    ]


def code_columns(sqlite: bool) -> list[sa.Column[Any]]:
    code_type = sa.String(64, collation=None if sqlite else "C")
    return [
        sa.Column("code", code_type, nullable=False),
        sa.Column(
            "code_key",
            code_type,
            sa.Computed("lower(code)", persisted=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000)),
    ]


def code_constraints(table: str, sqlite: bool) -> list[sa.Constraint]:
    expression = (
        "code NOT GLOB '*[^A-Za-z0-9._-]*' AND substr(code, 1, 1) GLOB '[A-Za-z0-9]'"
        if sqlite
        else "code ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$'"
    )
    suffix = "sqlite" if sqlite else "postgres"
    return [
        sa.UniqueConstraint("code_key", name=f"uq_{table}_code_key"),
        sa.CheckConstraint(
            "length(code) BETWEEN 1 AND 64", name=op.f(f"ck_{table}_code_length")
        ),
        sa.CheckConstraint(expression, name=op.f(f"ck_{table}_code_ascii_{suffix}")),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 200", name=op.f(f"ck_{table}_name_length")
        ),
        sa.CheckConstraint(
            "updated_at >= created_at", name=op.f(f"ck_{table}_timestamp_order")
        ),
    ]


def upgrade() -> None:
    sqlite = op.get_bind().dialect.name == "sqlite"
    op.create_table(
        "accounts",
        *record_columns(),
        *code_columns(sqlite),
        sa.Column("account_type", sa.String(20), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(create_constraint=True, name="active_boolean"),
            nullable=False,
        ),
        *code_constraints("accounts", sqlite),
        sa.CheckConstraint(
            "account_type IN ('asset','liability','equity','revenue','expense')",
            name=op.f("ck_accounts_account_type"),
        ),
    )
    op.create_table(
        "journals",
        *record_columns(),
        *code_columns(sqlite),
        *code_constraints("journals", sqlite),
    )
    op.create_table(
        "journal_entries",
        *record_columns(),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("reference", sa.String(200)),
        sa.Column("journal_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["journal_id"],
            ["journals.id"],
            ondelete="RESTRICT",
            name="fk_journal_entries_journal_id_journals",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at", name=op.f("ck_journal_entries_timestamp_order")
        ),
        sa.CheckConstraint(
            "length(description) BETWEEN 1 AND 1000",
            name=op.f("ck_journal_entries_description_length"),
        ),
    )
    op.create_index("ix_journal_entries_journal_id", "journal_entries", ["journal_id"])
    op.create_index(
        "ix_journal_entries_transaction_date_id",
        "journal_entries",
        ["transaction_date", "id"],
    )
    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("side", sa.String(6), nullable=False),
        sa.Column[Any](
            "amount_minor", sa.BLOB() if sqlite else sa.Numeric(), nullable=False
        ),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            ondelete="CASCADE",
            name="fk_journal_lines_journal_entry_id_journal_entries",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            ondelete="RESTRICT",
            name="fk_journal_lines_account_id_accounts",
        ),
        sa.UniqueConstraint(
            "journal_entry_id", "position", name="uq_journal_lines_journal_entry_id"
        ),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_journal_lines_position_nonnegative")
        ),
        sa.CheckConstraint(
            "side IN ('debit','credit')", name=op.f("ck_journal_lines_side")
        ),
        sa.CheckConstraint(
            "amount_minor BETWEEN 1 AND 999999999999999999",
            name=op.f("ck_journal_lines_amount_range"),
        ),
        sa.CheckConstraint(
            "typeof(amount_minor) = 'integer'"
            if sqlite
            else "amount_minor = trunc(amount_minor)",
            name=op.f(
                "ck_journal_lines_amount_whole_sqlite"
                if sqlite
                else "ck_journal_lines_amount_whole_postgres"
            ),
        ),
        sa.CheckConstraint(
            "length(currency) = 3", name=op.f("ck_journal_lines_currency_length")
        ),
        sa.CheckConstraint(
            "currency NOT GLOB '*[^A-Z]*'" if sqlite else "currency ~ '^[A-Z]{3}$'",
            name=op.f(
                "ck_journal_lines_currency_ascii_sqlite"
                if sqlite
                else "ck_journal_lines_currency_ascii_postgres"
            ),
        ),
    )
    op.create_index("ix_journal_lines_account_id", "journal_lines", ["account_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("record_type", sa.String(200), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("actor", sa.String(200)),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint("action = 'delete'", name=op.f("ck_audit_events_action")),
    )
    op.create_index(
        "ix_audit_events_record_history",
        "audit_events",
        ["record_type", "record_id", "occurred_at"],
    )


def downgrade() -> None:
    for table in (
        "audit_events",
        "journal_lines",
        "journal_entries",
        "journals",
        "accounts",
    ):
        op.drop_table(table)
