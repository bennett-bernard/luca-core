"""Save a sale, reopen storage, demonstrate audit rules, and export postings.

Run with `uv run --all-extras python examples/05_persistence_and_csv.py`.
The default database and CSV live under the Git-ignored output/milestone2/.
Set LUMBAGO_DATABASE_URL only to a database intended for this example's writes.
"""

import argparse
import os
from datetime import date
from pathlib import Path
from uuid import uuid4

from lumbago import (
    Account,
    AccountingService,
    AccountType,
    EntrySide,
    Journal,
    JournalEntry,
    JournalLine,
    Money,
    ReferencedRecordError,
    export_postings_csv,
    project_postings,
)
from lumbago.persistence.sqlalchemy import SqlAlchemyStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output/milestone2"))
    output_dir = parser.parse_args().output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    database_url = os.environ.get(
        "LUMBAGO_DATABASE_URL", f"sqlite+pysqlite:///{output_dir / 'lumbago.db'}"
    )
    entry_id = uuid4()
    store = SqlAlchemyStore(database_url)
    try:
        store.migrate()
        with store.unit_of_work() as uow:
            service = AccountingService(uow)
            accounts = {
                record.code.casefold(): record for record in uow.accounts.list()
            }
            cash = accounts.get("demo.cash")
            if cash is None:
                cash = service.create_account(
                    Account(
                        code="DEMO.CASH",
                        name="Demo cash",
                        account_type=AccountType.ASSET,
                    )
                )
            revenue = accounts.get("demo.revenue")
            if revenue is None:
                revenue = service.create_account(
                    Account(
                        code="DEMO.REVENUE",
                        name="Demo revenue",
                        account_type=AccountType.REVENUE,
                    )
                )
            journals = {
                record.code.casefold(): record for record in uow.journals.list()
            }
            general = journals.get("demo.general")
            if general is None:
                general = service.create_journal(
                    Journal(code="DEMO.GENERAL", name="Demo general journal")
                )
            service.create_entry(
                JournalEntry(
                    id=entry_id,
                    journal_id=general.id,
                    transaction_date=date(2026, 9, 7),
                    description="Cash sale to Acme",
                    reference="DEMO-SALE",
                    lines=(
                        JournalLine(
                            journal_entry_id=entry_id,
                            account_id=cash.id,
                            side=EntrySide.DEBIT,
                            amount=Money(amount="125.00", currency="USD"),
                            metadata={"customer": "Acme"},
                        ),
                        JournalLine(
                            journal_entry_id=entry_id,
                            account_id=revenue.id,
                            side=EntrySide.CREDIT,
                            amount=Money(amount="125.00", currency="USD"),
                            metadata={"customer": "Acme"},
                        ),
                    ),
                )
            )
            try:
                service.delete_account(cash.id, actor="example")
            except ReferencedRecordError:
                print("Referenced cash account deletion correctly rejected.")
            unused_account = service.create_account(
                Account(
                    code=f"DEMO.UNUSED.{uuid4().hex}",
                    name="Unused demo account",
                    account_type=AccountType.EXPENSE,
                )
            )
            unused_journal = service.create_journal(
                Journal(code=f"DEMO.UNUSED.{uuid4().hex}", name="Unused demo journal")
            )
            service.delete_account(unused_account.id, actor="example")
            service.delete_journal(unused_journal.id, actor="example")
            uow.commit()
    finally:
        store.close()

    # A new engine reads the committed records and durable audit events.
    reopened = SqlAlchemyStore(database_url)
    try:
        with reopened.unit_of_work() as uow:
            saved = uow.journal_entries.retrieve(entry_id)
            rows = project_postings((saved,), uow.accounts.list(), uow.journals.list())
            audit_count = len(uow.audit_events.list())
        csv_path = output_dir / f"postings-{entry_id}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as output:
            export_postings_csv(rows, output)
        print(f"Reopened entry {saved.id}: {len(saved.lines)} exact, balanced lines.")
        print(f"Durable deletion audit events: {audit_count}")
        print(f"CSV written to {csv_path}")
    finally:
        reopened.close()


if __name__ == "__main__":
    main()
