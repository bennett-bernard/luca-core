# Milestone 2: persistence decisions and operations

This is the implemented persistence contract for version 0.2.

## Decisions

| Question | Implemented rule |
| --- | --- |
| Draft/posting state | None: a successfully saved entry is accounting history. |
| Entry changes | Saved entries cannot be edited or deleted through transactional stores. Immutability is the reviewed default used pending an explicit alternative. |
| Account deletion | Only unused accounts; deactivate referenced accounts instead. |
| Journal deletion | Only journals without entries. |
| Deletion evidence | Delete and full record audit snapshot succeed or roll back together through `AccountingService`. |
| Monetary precision | Nonnegative, exact hundredths; reject fractional hundredths, never round. Journal lines must be positive. |
| Code uniqueness | Case-insensitive within accounts and within journals separately; `CASH` and `Cash` cannot coexist in one collection. |
| API/dependencies | Synchronous; SQL and PostgreSQL dependencies are optional extras. |
| Transaction ownership | Callers explicitly commit complete workflows. Exiting without commit rolls back. |

Account and journal details may change, including codes and names. New entries
cannot use inactive accounts. Existing entries remain readable after an account
is deactivated. Corrections to entries require new balanced entries; a reversal
helper and an update-audit design are outside this milestone.

## Exact amounts, including direct SQL

`Money` accepts `Decimal`, decimal strings, and integers, not binary floats. The
range is `0.00` through `9999999999999999.99` inclusive. More than two
*significant fractional places* is invalid: `12.345` fails, while `12.3400`
normalizes to `12.34`. Balancing and conversion use integer hundredths and are
independent of the ambient Decimal precision. Currency is a three-letter ASCII
code; this milestone does not implement currency-specific decimal scales.

The SQL column is `journal_lines.amount_minor`: `125.00` is stored as `12500`.
It must contain a whole number from 1 through 999999999999999999. The adapters
deliberately use different physical declarations for the same exact contract:

- SQLite: a no-affinity column (declared `BLOB`) plus
  `CHECK(typeof(amount_minor) = 'integer')`. **Stored values are integers, not
  binary blobs.** Avoiding numeric affinity prevents SQLite from rounding a
  large fractional numeric/text input into an integer before the check runs.
- PostgreSQL: unrestricted `NUMERIC`, a whole-number check using `trunc`, and
  the same range check. Fixed-scale `NUMERIC(p, 0)` and integer casts could
  round before checks, so neither is used for the column declaration.

The tests exercise raw SQL fractional, malformed, negative, zero, and overflow
inputs as well as the maximum exact domain amount. Callers must still supply
exact values: a database cannot recover precision already lost by a client-side
float calculation or explicit SQL rounding/cast before assignment.

`code_key` is a database-generated `lower(code)` value with a unique constraint;
callers cannot supply a misleading key. Codes are limited to the domain's ASCII
letters, numbers, dots, underscores, and hyphens, beginning with a letter/number.
PostgreSQL code columns use `C` collation so lowercasing remains consistent with
ASCII case rules regardless of database locale. SQLite requires generated-column
support (3.31+). UUIDs, enums, ordered lines, UTC timestamps, and JSON metadata
round-trip to validated public models.

## Store and unit-of-work API

```python
from lumbago import AccountingService, InMemoryStore

store = InMemoryStore()
with store.unit_of_work() as uow:
    service = AccountingService(uow)
    # service.create_account(...), create_journal(...), create_entry(...)
    # service.update_account(...), delete_account(..., actor="...")
    uow.commit()
```

For SQL, import `SqlAlchemyStore` from `lumbago.persistence.sqlalchemy`, construct it
with a URL, call `store.migrate()` explicitly when appropriate, and close it when
finished. Supported URLs are `sqlite:///...`, `sqlite+pysqlite:///...`, and
`postgresql+psycopg://...`; SQLite memory uses `sqlite+pysqlite:///:memory:`.
The store owns connectivity. Its factory returns a new one-use unit of work with
`accounts`, `journals`, `journal_entries`, and `audit_events` repositories. All
return detached Pydantic objects, not ORM rows.

Each service mutation and SQL repository mutation uses a savepoint. A caught
operation failure therefore cannot leave half an entry or an unaudited service
deletion behind, even if the caller subsequently commits unrelated work. An
uncaught exception rolls back the entire unfinished workflow. `commit()` or
`rollback()` ends a scope's usable lifetime; do not reuse it or its repositories
before entering, after exit, or after transaction completion. Create another
unit of work instead. Failed commits close the active scope and are reported
without raw SQL parameters.

Use `AccountingService` for complete accounting workflows, particularly audited
deletions. Direct repository deletion has storage/reference guards but does not
coordinate an audit event; that is a service responsibility. The legacy
standalone `InMemoryRepository`, `AccountService`, and `JournalService` retain
their original low-level/nontransactional interfaces for compatibility. The
new transactional stores add history safeguards and deterministic listing by
`(created_at, id)`; legacy memory listing remains insertion ordered. Audit events
are listed by `(occurred_at, id)`.

### Concurrency and scope limits

- File-backed SQLite uses foreign keys, a five-second busy timeout, and
  `BEGIN IMMEDIATE`. Workflows acquire the write reservation before business
  checks, serializing writers. Keep scopes short, including read-only scopes.
- In-memory SQLite uses one engine-owned connection; use sequential scopes, not
  overlapping threads. `InMemoryStore` also rejects overlapping scopes on one
  store and snapshots records/audits for real rollback.
- PostgreSQL uses repeatable-read transactions. Retrieval locks rows used by
  reference/deactivation/deletion checks; accounts in entry creation are locked
  in UUID order. Unique constraints decide concurrent code collisions.
  Serialization failures, deadlocks, or lock timeouts may still occur and become
  `StorageError`; applications may retry an appropriate **whole workflow in a
  new unit of work**, not only the failed statement. No automatic retry occurs.

All inputs to a consistent posting projection should be read inside the same
unit of work. A store is intended to be reused across workflows; a unit of work
must not be shared across threads. Large lists and reference checks currently
materialize records. Pagination and specialized reporting queries are future
work, not promised performance characteristics of this version.

### What the database does not guarantee

Foreign keys, unique/generated codes, positive exact hundredths, and basic row
constraints protect against many direct SQL mistakes. Complete-entry balancing,
entry immutability, active-account checks, and service audit coordination are
application guarantees, not database-wide trigger rules. A privileged raw SQL
writer can bypass these workflows or tamper with audit records. The append-only
audit interface is not a cryptographic or permissions-based tamper-proof log.
Do not expose unrestricted database writes as an equivalent accounting API.

## Declared model extensions

The stores accept configured subclasses and keep their declared fields in a
separate `extensions` JSON column, without hiding them in user `metadata`:

```python
from lumbago import Account
from lumbago.persistence.sqlalchemy import SqlAlchemyStore


class DepartmentAccount(Account):
    department: str


store = SqlAlchemyStore("sqlite+pysqlite:///lumbago.db", account_type=DepartmentAccount)
```

Use the same compatible `account_type`, `journal_type`, and `entry_type` when
reopening storage. Retrieved records and updates are validated against those
configured models. Custom field schema changes remain the application's
responsibility. Nested custom journal-line model persistence is not a separate
extension contract in this milestone.

## Migrations and deployment

Creating a store never creates tables. `store.migrate()` explicitly upgrades to
the current head using the migrations bundled in the installed wheel. The
initial revision creates accounts, journals, entry headers, ordered lines, and
audit events with named constraints and indexes. Re-running an upgrade at head
is safe. Existing 0.1 in-memory records are not automatically imported.

From this repository, the equivalent command is:

```console
LUMBAGO_DATABASE_URL=sqlite+pysqlite:///lumbago.db uv run --extra sql alembic upgrade head
LUMBAGO_DATABASE_URL=sqlite+pysqlite:///lumbago.db uv run --extra sql alembic current
```

Supply PostgreSQL connection details through protected application/environment
configuration, never committed credentials. Coordinate production migrations as
an explicit deployment step with appropriate backups. Offline SQL generation is
not supported by this first migration environment. Downgrading the initial
revision deletes the accounting tables: only migration tests use that operation
on disposable data. Future schema changes require new frozen revisions rather
than editing a revision already applied to a released database.

Migration scripts live inside the Python package, not a repository-only
`migrations/` directory. They contain frozen schema definitions independent of
live ORM row classes, and are tested for upgrade, downgrade, and ORM parity on
both supported SQL dialects.

## CSV: `lumbago-postings-v1`

`project_postings(entries, accounts, journals)` returns immutable `PostingRow`
models, one per journal line. It resolves the **current** account and journal
names/codes, not snapshots of their names at entry creation. Missing references
raise an error rather than silently omitting data. The default order is entry
date, entry UUID, then zero-based line position. Line positions preserve original
entry order. The initial projection materializes its inputs and output.

The exact header, in order, is:

```text
entry_id,transaction_date,reference,entry_description,journal_id,journal_code,journal_name,line_id,line_position,account_id,account_code,account_name,side,amount,currency,line_description,line_metadata
```

Amounts are fixed two-decimal strings without currency symbols or separators;
sides are `debit` or `credit`; dates are ISO dates. Missing optional text is empty.
Line metadata is compact, key-sorted JSON in a single quoted CSV field, preserving
Unicode, not an expanding set of customer-specific columns. Arbitrary metadata,
including `customer`, does not change the fixed CSV schema. No format preamble is
inserted before the header; `CSV_FORMAT` identifies the contract in code.

`export_postings_csv(rows, stream)` uses standard CSV quoting and LF line endings.
Open files with `encoding="utf-8", newline=""`. The caller owns and closes the
stream. Default export sorts rows deterministically; `preserve_order=True`
streams an already ordered iterable without sorting or materializing it again.
Empty input produces just the header. Formula-like text is preserved literally:
when importing untrusted content into a spreadsheet, explicitly import text
columns as text rather than allowing formula interpretation.

## Verification

The shared suite covers transactional memory, in-memory and file-backed SQLite,
and real PostgreSQL. It tests exact money, complete rollback, deletion/audit
failure atomicity, concurrent code collisions, schema constraints, UTC/UUID/JSON
round trips, model extensions, migrations, optional imports, and golden CSV
output. See the README for reproducible quality commands and the runnable
end-to-end example under `examples/`.
