"""The stable luca-postings-v1 CSV format."""

import csv
from collections.abc import Iterable
from typing import TextIO

from luca.exports.posting import PostingRow

CSV_FORMAT = "luca-postings-v1"
CSV_COLUMNS = (
    "entry_id",
    "transaction_date",
    "reference",
    "entry_description",
    "journal_id",
    "journal_code",
    "journal_name",
    "line_id",
    "line_position",
    "account_id",
    "account_code",
    "account_name",
    "side",
    "amount",
    "currency",
    "line_description",
    "line_metadata",
)


def export_postings_csv(
    rows: Iterable[PostingRow], output: TextIO, *, preserve_order: bool = False
) -> None:
    """Write v1 CSV without closing the caller's stream.

    Default ordering is deterministic and materializes the rows. Set
    preserve_order=True to stream an explicitly ordered iterable unchanged.
    Open disk files with encoding='utf-8' and newline=''. Text is preserved
    literally; spreadsheet users should import text columns as text.
    """

    ordered = (
        rows
        if preserve_order
        else sorted(
            rows,
            key=lambda row: (row.transaction_date, row.entry_id, row.line_position),
        )
    )
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in ordered:
        writer.writerow(row.model_dump(mode="json"))
