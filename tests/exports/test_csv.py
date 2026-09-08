"""Versioned CSV serialization and persisted posting projections."""

import csv
import io
from uuid import UUID

import pytest

from luca import (
    AccountingService,
    RecordNotFoundError,
    export_postings_csv,
    project_postings,
)
from luca.exports import CSV_COLUMNS, CSV_FORMAT
from tests.conftest import Store
from tests.helpers import account, entry, journal


def test_persisted_postings_export_on_every_backend(store: Store) -> None:
    cash, revenue, general = account(), account("REVENUE"), journal()
    posting = entry(cash, revenue, general)
    with store.unit_of_work() as uow:
        service = AccountingService(uow)
        service.create_account(cash)
        service.create_account(revenue)
        service.create_journal(general)
        service.create_entry(posting)
        uow.commit()
    with store.unit_of_work() as uow:
        rows = project_postings(
            uow.journal_entries.list(), uow.accounts.list(), uow.journals.list()
        )
    output = io.StringIO(newline="")
    export_postings_csv(reversed(rows), output)
    assert not output.closed
    reader = csv.DictReader(io.StringIO(output.getvalue()))
    assert tuple(reader.fieldnames) == CSV_COLUMNS
    data = list(reader)
    assert [row["side"] for row in data] == ["debit", "credit"]
    assert data[0]["entry_description"] == posting.description
    assert data[0]["account_name"] == "Cash, operating"
    assert data[0]["reference"] == "" and data[0]["amount"] == "125.00"
    assert data[1]["line_metadata"] == '{"customer":"Acme Corp","z":"élève"}'
    assert CSV_FORMAT == "luca-postings-v1"


def test_csv_golden_output_and_explicit_order() -> None:
    cash = account(id=UUID(int=1), name="Cash")
    revenue = account("REVENUE", id=UUID(int=2), name="Revenue")
    general = journal(id=UUID(int=3))
    original = entry(cash, revenue, general, entry_id=UUID(int=4))
    values = original.model_dump(mode="python")
    values["description"] = "Sale"
    for position, line in enumerate(values["lines"]):
        line["id"] = UUID(int=5 + position)
    original = type(original).model_validate(values)
    rows = project_postings([original], [cash, revenue], [general])
    output = io.StringIO()
    export_postings_csv(rows, output)
    expected = ",".join(CSV_COLUMNS) + "\n"
    expected += "00000000-0000-0000-0000-000000000004,2026-09-01,,Sale,00000000-0000-0000-0000-000000000003,GENERAL,General Journal,00000000-0000-0000-0000-000000000005,0,00000000-0000-0000-0000-000000000001,CASH,Cash,debit,125.00,USD,,{}\n"
    expected += '00000000-0000-0000-0000-000000000004,2026-09-01,,Sale,00000000-0000-0000-0000-000000000003,GENERAL,General Journal,00000000-0000-0000-0000-000000000006,1,00000000-0000-0000-0000-000000000002,REVENUE,Revenue,credit,125.00,USD,,"{""customer"":""Acme Corp"",""z"":""élève""}"\n'
    assert output.getvalue() == expected
    ordered = io.StringIO()
    export_postings_csv(reversed(rows), ordered, preserve_order=True)
    assert next(csv.DictReader(io.StringIO(ordered.getvalue())))["side"] == "credit"
    empty = io.StringIO()
    export_postings_csv([], empty)
    assert empty.getvalue() == ",".join(CSV_COLUMNS) + "\n"


def test_projection_requires_resolvable_references_and_sorts_entries() -> None:
    cash, revenue, general = account(), account("REVENUE"), journal()
    first = entry(cash, revenue, general, entry_id=UUID(int=1))
    second = entry(cash, revenue, general, entry_id=UUID(int=2))
    with pytest.raises(RecordNotFoundError, match="Journal"):
        project_postings([first], [cash, revenue], [])
    with pytest.raises(RecordNotFoundError, match="Account"):
        project_postings([first], [], [general])
    rows = project_postings([second, first], [cash, revenue], [general])
    assert [row.entry_id for row in rows] == [first.id, first.id, second.id, second.id]
