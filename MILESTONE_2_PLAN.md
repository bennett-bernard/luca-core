# Luca Milestone 2 Plan

## Durable relational persistence and CSV export

**Status:** Implemented and locally validated on 2026-09-07; not committed or published.

**Implementation note:** The original proposal and inline comments below are
preserved as review history. The implemented decisions are recorded in
[`docs/persistence.md`](docs/persistence.md), which supersedes conflicting
recommendations below. In particular: money uses exact hundredths and rejects
fractional hundredths at the database boundary; codes are case-insensitively
unique; there is no draft state; and saved entries are immutable under the
reviewed default. SQL dependencies are optional and the API is synchronous.

**Validation:** 183 tests passed, with 18 backend-inapplicable skips, against
transactional memory, both SQLite modes, and real PostgreSQL 17. Measured library
statement and branch coverage is 100%. Ruff, strict Mypy, lockfile, whitespace,
source/wheel builds, packaged migrations, isolated wheel installation, and all
five runnable examples passed. GitHub Actions is configured; a remote workflow
run is not part of this local validation. Review audio and generated accounting
outputs remain Git-ignored.

**Depends on:** Milestone 1 domain models, repository contracts, services, and
audit events

**Primary outcome:** Luca can persist its current accounting records safely in
SQLite and PostgreSQL, perform multi-record workflows transactionally, and
export a stable, spreadsheet-friendly posting view to CSV.

## 1. Purpose

Milestone 1 established storage-neutral Pydantic models, repository contracts,
in-memory adapters, application services, validation, and deletion audit
events. Milestone 2 should prove that those boundaries work with durable
relational storage and then build the first data-out format on top of the
resulting read model.

The milestone is intentionally ordered as follows:

1. Decide the lifecycle and precision rules that affect the database schema.
2. Add a private SQLAlchemy persistence layer without coupling public domain
   models to SQLAlchemy.
3. Implement SQLite as the first complete durable backend.
4. Exercise the same repository behavior against PostgreSQL before relying on
   SQLite-specific behavior.
5. Introduce a flattened posting projection and serialize it to CSV.

CSV export comes after persistence because it should be an output adapter over
a dependable domain and query boundary, not a second persistence system.

## 2. Milestone outcomes

At the end of Milestone 2, a Luca application should be able to:

- Connect to an in-memory SQLite database, a file-backed SQLite database, or a
  PostgreSQL database through configuration.
- Upgrade an empty database to the current schema using Alembic.
- Store and retrieve accounts, journals, journal entries, journal lines, and
  audit events without losing UUID, Decimal, timestamp, enum, or metadata
  meaning.
- Enforce parent references and code uniqueness in the database as well as in
  application services.
- Create an entry and all of its lines atomically.
- Perform an allowed hard deletion and append its audit event in the same
  transaction.
- Reject deletion when the record is needed by historical accounting data.
- Continue using the public Pydantic models without exposing SQLAlchemy rows or
  sessions.
- Export a deterministic, one-row-per-posting CSV representation with resolved
  journal and account information.
- Run the same repository contract tests against the in-memory and SQL-backed
  implementations.

## 3. Guiding principles

### 3.1 Keep domain models independent of persistence

`Account`, `Journal`, `JournalEntry`, `JournalLine`, `Money`, and `AuditEvent`
remain public Pydantic models. They must not inherit from SQLAlchemy declarative
classes or expose lazy-loaded relationships.

Private ORM row classes describe storage. Explicit mapper functions translate
between rows and public domain models:

```text
Pydantic domain model
        |
        | explicit mapper
        v
SQLAlchemy ORM row
        |
        v
SQLite or PostgreSQL
```

This separation preserves Luca's ability to support non-SQL storage adapters
and keeps database sessions out of user code. BENNETT: WHAT ARE NON-SQL STORAGE ADAPTERS? JUST LOOKING FOR INFORMATION.

### 3.2 Put business workflows in services

Repositories store and retrieve records. Services decide whether a workflow is
allowed and coordinate all required writes. A unit of work supplies the shared
transaction needed by those services. BENNETT: I DON"T UNDERSTAND THIS. EXPLAIN MORE.

### 3.3 Preserve accounting history

Database cascades must never erase historical accounting activity merely
because a parent account or journal was deleted. Historical records should
remain interpretable.

### 3.4 Prefer portable behavior

The schema should use SQLAlchemy's portable types and explicit constraints.
PostgreSQL-specific enhancements can be introduced later behind adapters, but
Milestone 2 behavior must be consistent between SQLite and PostgreSQL.

### 3.5 Make data-out independent of storage

CSV exporters consume a domain-level posting projection or iterable of rows.
They do not accept a SQLAlchemy `Session`, database URL, or ORM objects.

## 4. Scope

### 4.1 In scope

- SQLAlchemy 2.x engine, session, declarative row, and repository integration.
- Alembic migration environment and an explicit initial migration.
- SQLite in-memory and file-backed databases.
- PostgreSQL support through the same repository and unit-of-work contracts.
- Optional PostgreSQL driver packaging.
- Database constraints, indexes, and deterministic constraint names.
- A synchronous unit-of-work abstraction.
- Durable audit-event storage.
- Transactional service workflows.
- A flattened posting read model.
- CSV export to any text stream.
- Documentation, runnable examples, and comprehensive tests.

### 4.2 Explicitly out of scope

- CSV import.
- JSON Lines, Parquet, Excel, or PDF exports.
- Async SQLAlchemy APIs.
- Connection management for hosted platforms.
- Read replicas, sharding, or multi-tenant schemas.
- A generalized query language.
- Reporting totals, financial statements, or exchange-rate conversion.
- User and role tables.
- Database encryption or secret-management systems.
- A CLI or web interface.
- Automatic schema creation through normal application startup.

`MetaData.create_all()` may be used in isolated tests, but released databases
must be managed through Alembic migrations.

## 5. Decision gates before schema implementation

These choices affect stored data and become expensive to reverse. They should
be approved before the initial migration is treated as stable.

### Decision 1: Record lifecycle and deletion

**Recommendation**

- An unreferenced `Account` may be hard-deleted.
- A referenced `Account` cannot be hard-deleted; use `active=False` instead.
- An unreferenced `Journal` may be hard-deleted.
- A `Journal` containing entries cannot be hard-deleted.
- Persisted journal entries should not be hard-deleted through the normal
  accounting service. A later milestone can introduce voiding and reversing
  workflows.
- Internal cleanup of an unposted/draft entry is deferred until Luca has an
  explicit posting-state model.
- Every permitted hard deletion appends an `AuditEvent` in the same database
  transaction.
- `AuditEvent.record_id` is deliberately not a foreign key because the event
  must survive deletion of the referenced record.

**Database behavior**

- Journal entry to journal: `ON DELETE RESTRICT`.
- Journal line to account: `ON DELETE RESTRICT`.
- Journal line to journal entry: `ON DELETE CASCADE` only for internal aggregate
  cleanup, not as authorization to delete posted entries.
- SQLite foreign-key enforcement is enabled for every connection.

**Approval question**

Should Milestone 2 prohibit all journal-entry deletion immediately, or should a
temporary concept of an unposted entry be added first? BENNETT: OK WITH YOUR PLAN HERE. NO CONCEPT OF UNPOSTED YET.

### Decision 2: Exact Decimal storage BENNETT: HELP ME UNDERSTAND- WHY CAN'T ALL MONEY TYPE VALUES JUST BE EXPRESSED AS A NON-NEGATIVE NUMBER WITH ONLY TWO DECIMAL DIGITS? THE DB SCHEMA SHOULD NOT ACCEPT ANY ENTRY WITH MORE THAN TWO DECIMAL PLACES.

The current `Money` type accepts arbitrary nonnegative `Decimal` values. SQLite
does not provide a native arbitrary-precision decimal storage class, so a
portable mapping must not silently round through binary floating point.

**Required spike**

Compare these representations with SQLite and PostgreSQL round-trip tests:

1. A documented fixed `NUMERIC(precision, scale)` policy enforced by `Money`.
2. A canonical decimal string stored as text.
3. A coefficient-and-exponent representation stored in separate columns.

**Recommendation for the first spike**

Start with canonical decimal text because it preserves exact Luca values on
both backends without imposing an unreviewed currency scale. Treat amounts as
domain values and perform initial balancing and totals in Python. If database
aggregation becomes a Milestone 2 requirement, approve a fixed precision and
scale before the migration is finalized.

The selected representation must prove exact round trips for:

- `0`
- `0.01`
- `125.00`
- A value with more than two fractional digits.
- A very large valid value.
- Numerically equal values with different input exponents when serialized.

### Decision 3: Case-insensitive code uniqueness BENNETT: THIS SHOULD NOT BE ALLOWED. MAKE WHATEVER YOU NEED TO ENSURE "CASH" and "Cash" CANNOT BOTH BE RECORDS IN THE TABLE.

**Recommendation**

Add a private `code_key` column for accounts and journals. Services and mappers
populate it with Python's `casefold()` result, and the database applies a unique
constraint to `code_key`.

This preserves the caller's display casing in `code` while ensuring `CASH`,
`Cash`, and `cash` conflict consistently on SQLite and PostgreSQL.

### Decision 4: Synchronous APIs BENNETT: OK

**Recommendation**

Keep Milestone 2 synchronous. The current repository and service interfaces are
synchronous, and the expected initial consumers are library code, scripts, and
a future CLI. Async adapters can be introduced behind separate contracts when a
web workload demonstrates the need.

### Decision 5: Dependency packaging BENNETT: OK

**Recommendation**

Keep core domain use lightweight through optional dependency groups:

```text
sql       -> SQLAlchemy and migration support
postgres  -> SQL dependencies plus a PostgreSQL driver
```

SQLite uses Python's built-in `sqlite3` driver. PostgreSQL should use Psycopg 3
through a `postgresql+psycopg://` URL. Exact dependency bounds should follow the
project's existing policy of capping the next major version.

## 6. Proposed architecture BENNETT: I DONT FULLY UNDERSTAND THIS. PLEASE EXPLAIN

```text
Python caller / future CLI / future web API
                    |
                    v
        Accounting services and exporters
                    |
          +---------+----------+
          |                    |
          v                    v
      UnitOfWork          Posting projector
          |                    |
          v                    v
Repository contracts      CSV exporter
          |
      +---+-------------------+
      |                       |
      v                       v
In-memory adapters    SQLAlchemy repositories
                              |
                              v
                      SQLAlchemy Session
                              |
                   +----------+----------+
                   |                     |
                   v                     v
                SQLite              PostgreSQL
```

### 6.1 Proposed source layout BENNETT: PLEASE GIVE ME AN EXPLANATION FOR EACH FILE LISTED HERE. I NEED TO UNDERSTAND.

```text
src/luca/
    exports/
        __init__.py
        csv.py
        posting.py
    persistence/
        __init__.py
        unit_of_work.py
        sqlalchemy/
            __init__.py
            base.py
            engine.py
            mappers.py
            models.py
            repositories.py
            unit_of_work.py
    repositories/
        base.py
        memory.py
        audit.py
    services/
        accounting.py
        entries.py
        crud.py

migrations/
    env.py
    script.py.mako
    versions/
        <revision>_create_initial_accounting_schema.py

tests/
    contracts/
    exports/
    integration/
        sqlite/
        postgres/
    migrations/
```

The final names may change during implementation, but the dependency direction
must remain domain -> contracts -> adapters, never domain -> SQLAlchemy.

## 7. Relational data model

### 7.1 `accounts`

| Column | Purpose |
| --- | --- |
| `id` | UUID primary key |
| `created_at` | UTC creation timestamp |
| `updated_at` | UTC modification timestamp |
| `metadata` | JSON-compatible extension data |
| `code` | Caller-facing account code |
| `code_key` | Case-folded uniqueness key |
| `name` | Account name |
| `account_type` | Asset, liability, equity, revenue, or expense |
| `description` | Optional explanation |
| `active` | Whether new postings may reference the account |

Constraints and indexes:

- Primary key on `id`.
- Unique constraint on `code_key`.
- Index on `account_type` only if query use justifies it.
- Check constraints should mirror stable enum or length rules where portable.

### 7.2 `journals`

| Column | Purpose |
| --- | --- |
| `id` | UUID primary key |
| `created_at` | UTC creation timestamp |
| `updated_at` | UTC modification timestamp |
| `metadata` | JSON-compatible extension data |
| `code` | Caller-facing journal code |
| `code_key` | Case-folded uniqueness key |
| `name` | Journal name |
| `description` | Optional explanation |

Constraints:

- Primary key on `id`.
- Unique constraint on `code_key`.

### 7.3 `journal_entries`

| Column | Purpose |
| --- | --- |
| `id` | UUID primary key |
| `created_at` | UTC creation timestamp |
| `updated_at` | UTC modification timestamp |
| `metadata` | JSON-compatible extension data |
| `transaction_date` | Accounting recognition date |
| `description` | Entry-level explanation |
| `reference` | Optional external reference |
| `journal_id` | Owning journal foreign key |

Constraints and indexes:

- Primary key on `id`.
- Foreign key to `journals.id` with restricted deletion.
- Index on `journal_id`.
- Composite index on `(transaction_date, id)` for stable date-range traversal.

### 7.4 `journal_lines`

| Column | Purpose |
| --- | --- |
| `id` | UUID primary key |
| `journal_entry_id` | Owning entry foreign key |
| `position` | Stable order within the entry |
| `account_id` | Referenced account foreign key |
| `side` | Debit or credit |
| `amount_*` | Approved exact Decimal representation |
| `currency` | Three-letter Luca currency code |
| `description` | Optional line memo |
| `metadata` | JSON-compatible extension data, such as customer information |

Constraints and indexes:

- Primary key on `id`.
- Foreign key to `journal_entries.id`.
- Foreign key to `accounts.id` with restricted deletion.
- Unique constraint on `(journal_entry_id, position)`.
- Index on `account_id`.
- Check constraint for `side` when portable.
- Positive-amount and balancing rules remain authoritative domain validation;
  services revalidate after database reconstruction.

`position` is required because SQL tables do not preserve tuple or insertion
order automatically.

### 7.5 `audit_events`

| Column | Purpose |
| --- | --- |
| `id` | UUID primary key |
| `occurred_at` | UTC event timestamp |
| `action` | Audited action, initially `delete` |
| `record_type` | Domain type name |
| `record_id` | Affected UUID without a foreign key |
| `actor` | Optional caller-defined actor identifier |
| `snapshot` | JSON snapshot retained after deletion |

Constraints and indexes:

- Primary key on `id`.
- Composite index on `(record_type, record_id, occurred_at)`.
- No update or delete methods in the audit repository contract.

## 8. Repository and mapper behavior

### 8.1 Mapper requirements BENNETT: EXPLAIN IN LAYMENS TERMS WHY THIS IS NECESSARY

Every mapper must:

- Return a new validated Pydantic model rather than an ORM row.
- Normalize loaded timestamps to UTC.
- Reconstruct `Money` exactly.
- Reconstruct journal lines in `position` order.
- Deep-copy or reconstruct JSON data at the adapter boundary.
- Fail loudly if stored data violates current domain validation.

### 8.2 Repository requirements

SQL repositories must match the current public behavior where appropriate:

- Duplicate UUIDs raise `DuplicateRecordError`.
- Missing UUIDs raise `RecordNotFoundError`.
- Updates protect `id`, `created_at`, and `updated_at`.
- Updates rebuild and validate the complete domain model.
- Database uniqueness errors map to `DuplicateCodeError`.
- Returned records are detached domain values; callers never depend on an open
  session.
- List ordering is explicitly defined as `(created_at, id)` unless a
  record-specific query states otherwise.

Journal entries require a specialized repository because they are aggregates:

- Creating an entry inserts the parent and all lines atomically.
- Retrieving an entry eagerly loads and orders its lines.
- Updating an entry treats the submitted line tuple as the desired aggregate
  state and validates it before persistence.

## 9. Unit of work and transaction behavior

### 9.1 Contract BENNETT: I THINK I GET THIS BUT HELP ME MAKE SURE I FOLLOW BY EXPLAINING IN LAYMEN TERMS

The storage-neutral unit of work should expose repositories that share one
transaction:

```python
class UnitOfWork(Protocol):
    accounts: Repository[Account]
    journals: Repository[Journal]
    journal_entries: Repository[JournalEntry]
    audit_events: AuditLog

    def __enter__(self) -> Self: ...
    def __exit__(self, *args: object) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

The exact typing can evolve, but these semantics are required:

- Leaving a context without `commit()` rolls back.
- Exceptions roll back.
- `commit()` is explicit.
- Repositories obtained from one unit of work share one SQLAlchemy session.
- A unit-of-work instance is not reused across simultaneous workflows.

### 9.2 Required transactional workflows

1. **Create journal entry**
   - Retrieve and validate the journal.
   - Retrieve every referenced account.
   - Reject inactive or missing accounts.
   - Validate the complete entry.
   - Insert the entry and all lines.
   - Commit once.

2. **Delete unreferenced account or journal**
   - Retrieve the record.
   - Check references and lifecycle policy.
   - Construct the audit event before mutation.
   - Delete the record.
   - Append the audit event.
   - Commit both writes together.

3. **Failure behavior**
   - If audit append fails, the deletion rolls back.
   - If any line insert fails, the entire entry insert rolls back.
   - Domain errors do not leave partially updated rows.

## 10. Engine and session configuration

### 10.1 Public configuration

Provide a small configuration or factory API that accepts a SQLAlchemy database
URL without exposing engine internals to normal Luca consumers.

Example URLs:

```text
sqlite+pysqlite:///:memory:
sqlite+pysqlite:///luca.db
postgresql+psycopg://user:password@host:5432/luca
```

Configuration should support:

- Database URL.
- Optional SQL echo for local debugging.
- Pool options through an advanced adapter hook rather than many public flags.

Credentials must never be logged or included in exception messages.

### 10.2 SQLite connection behavior

Every SQLite connection must:

- Enable `PRAGMA foreign_keys=ON`.
- Use explicit modern transaction behavior appropriate to the supported Python
  version.
- Avoid sharing one session across threads.
- Use temporary files in tests rather than writing databases into the
  repository.

### 10.3 PostgreSQL behavior

- Use the Psycopg 3 SQLAlchemy dialect.
- Avoid PostgreSQL-only column types in the portable base schema unless a
  tested type variant exists.
- Run integration tests against a real PostgreSQL service, not a mock.

## 11. Alembic migrations

### 11.1 Initial migration requirements

The first migration creates all five tables, constraints, and indexes. It must:

- Upgrade a completely empty SQLite database.
- Upgrade a completely empty PostgreSQL database.
- Downgrade cleanly in an isolated test database.
- Use deterministic constraint naming conventions.
- Use Alembic batch operations when SQLite requires table recreation.
- Contain reviewed migration operations rather than trusting autogenerate
  output blindly.

### 11.2 Migration workflow

Expected developer commands should be documented, for example:

```console
uv run alembic upgrade head
uv run alembic current
uv run alembic downgrade base
```

Normal library startup must not silently mutate database schemas.

## 12. Posting projection and CSV export

### 12.1 Why use a posting projection

`JournalEntry` is a nested aggregate, while CSV is tabular. Exporting raw model
dumps would produce awkward nested values and would omit resolved account and
journal names.

Create a read-only `PostingRow` model with one row per journal line:

| Field | Source |
| --- | --- |
| `entry_id` | `JournalEntry.id` |
| `transaction_date` | `JournalEntry.transaction_date` |
| `reference` | `JournalEntry.reference` |
| `entry_description` | `JournalEntry.description` |
| `journal_id` | `Journal.id` |
| `journal_code` | `Journal.code` |
| `journal_name` | `Journal.name` |
| `line_id` | `JournalLine.id` |
| `line_position` | Entry line order |
| `account_id` | `Account.id` |
| `account_code` | `Account.code` |
| `account_name` | `Account.name` |
| `side` | `JournalLine.side` |
| `amount` | Exact decimal string |
| `currency` | `Money.currency` |
| `line_description` | `JournalLine.description` |
| `line_metadata` | Compact deterministic JSON |

Account and journal names are resolved for output; they are not duplicated in
the underlying journal-line domain model.

### 12.2 Metadata policy

The first CSV format should serialize all line metadata into one
`line_metadata` JSON column. For the example revenue posting, that value is:

```json
{"customer":"Acme Corp"}
```

A later option may promote caller-selected metadata keys such as `customer` to
dedicated CSV columns. That should not make arbitrary metadata keys part of the
stable default schema.

### 12.3 Exporter contract

The exporter should accept posting rows and a text stream:

```python
export_postings_csv(rows, output)
```

Required behavior:

- Use Python's standard `csv.DictWriter`.
- Accept any writable `TextIO` so callers can target files, memory, HTTP
  responses, or future CLI stdout.
- Use UTF-8 when Luca opens a file itself.
- Open files with `newline=""`.
- Emit a stable documented header order.
- Serialize Decimal values without floating-point conversion.
- Serialize dates and timestamps in ISO 8601 form.
- Serialize metadata as compact JSON with stable key ordering.
- Quote commas, quotes, and embedded newlines correctly.
- Preserve deterministic row ordering by entry date, entry ID, and line
  position unless a caller supplies an explicit order.

### 12.4 CSV versioning

Document the header as `luca-postings-v1`. The initial implementation may place
the version in documentation rather than inside the CSV file, but incompatible
header changes require a new named format.

## 13. Implementation phases

### Phase 0: Approve schema decisions

Deliverables:

- Recorded decisions for deletion lifecycle, Decimal representation,
  case-insensitive uniqueness, synchronous APIs, and optional dependencies.
- A small Decimal storage experiment against SQLite and PostgreSQL.

Exit criteria:

- No unresolved decision can change a primary stored representation.

### Phase 1: Persistence scaffolding

Deliverables:

- Optional SQL and PostgreSQL dependencies.
- Persistence package layout.
- Declarative base and naming conventions.
- Engine and session factories.
- SQLite foreign-key connection hook.
- Unit-of-work protocol.

Exit criteria:

- A test can open and close an in-memory SQLite unit of work without leaking a
  connection or session.

### Phase 2: Schema and migrations

Deliverables:

- ORM row classes for all five tables.
- Explicit relationships, constraints, indexes, and line positions.
- Alembic configuration.
- Reviewed initial migration.
- SQLite and PostgreSQL upgrade/downgrade tests.

Exit criteria:

- Both databases reach the same logical schema from an empty state.

### Phase 3: Mappers and SQL repositories

Deliverables:

- Bidirectional domain/row mappers.
- Account, journal, journal-entry, and audit repositories.
- Domain error translation.
- Contract-test parametrization across memory and SQLite.

Exit criteria:

- Every current CRUD contract passes against SQLite.
- Exact round trips pass for all supported field types.

### Phase 4: Transactional accounting services

Deliverables:

- SQLAlchemy unit of work.
- Entry creation service with referential and active-account checks.
- Lifecycle-aware account and journal deletion.
- Atomic deletion plus audit append.
- Rollback regression tests.

Exit criteria:

- Injected failures cannot leave partial entries or unaudited deletions.

### Phase 5: PostgreSQL parity

Deliverables:

- Psycopg optional dependency.
- PostgreSQL integration-test environment.
- Repository, migration, and transaction suites run against PostgreSQL.
- Documentation for supported connection URLs.

Exit criteria:

- PostgreSQL passes the same behavioral contract as SQLite.
- Any intentional backend difference is documented and tested.

### Phase 6: Posting projection and CSV

Deliverables:

- `PostingRow` read model.
- Projection service resolving journal and account details.
- CSV exporter.
- Golden-file and edge-case tests.
- Runnable SQLite-to-CSV example.

Exit criteria:

- A persisted journal entry exports as one deterministic row per line.
- The exported Acme revenue line retains its customer metadata.

### Phase 7: Documentation and release readiness

Deliverables:

- README persistence and export examples.
- Migration operations guide.
- SQLite file-backed walkthrough.
- PostgreSQL configuration walkthrough without real credentials.
- Public API review and package-content inspection.

Exit criteria:

- A new user can create a database, migrate it, store an entry, restart the
  process, retrieve it, and export it to CSV using documented commands.

## 14. Testing strategy

### 14.1 Test layers

1. **Unit tests**
   - Mapper conversion.
   - Decimal codec.
   - Code-key normalization.
   - Posting projection.
   - CSV serialization.

2. **Repository contract tests**
   - Create, retrieve, list, update, and delete.
   - Duplicate and missing records.
   - Defensive reconstruction.
   - Managed timestamps.
   - Aggregate line order.

3. **SQLite integration tests**
   - In-memory database.
   - Temporary file database and process-style reopen.
   - Foreign-key enforcement.
   - Transactions and rollback.

4. **PostgreSQL integration tests**
   - The same repository contract.
   - Unique and foreign-key constraint translation.
   - Transaction rollback.
   - JSON, UUID, and timestamp round trips.

5. **Migration tests**
   - Upgrade from empty to head.
   - Downgrade from head to base in disposable databases.
   - Schema objects and named constraints exist.

6. **CSV golden tests**
   - Stable headers and ordering.
   - Commas, quotes, and embedded newlines.
   - Unicode.
   - Decimal fidelity.
   - Empty optional values.
   - Metadata JSON ordering.

### 14.2 Backend matrix

| Behavior | Memory | SQLite memory | SQLite file | PostgreSQL |
| --- | ---: | ---: | ---: | ---: |
| Repository contract | Yes | Yes | Yes | Yes |
| Process restart durability | No | No | Yes | Yes |
| Foreign-key enforcement | N/A | Yes | Yes | Yes |
| Migration upgrade | N/A | Yes | Yes | Yes |
| Transaction rollback | Limited | Yes | Yes | Yes |
| Deletion plus audit atomicity | Limited | Yes | Yes | Yes |
| CSV projection | Yes | Yes | Yes | Yes |

### 14.3 Quality gates

- Ruff formatting passes.
- Ruff lint passes.
- Mypy strict mode passes.
- All unit and integration tests pass.
- Statement and branch coverage remain at 100% for Luca source unless a reviewed
  exception is documented.
- `git diff --check` passes.
- `uv lock --check` passes.
- Source distribution and wheel build successfully.
- Wheel inspection confirms persistence, export, typing, and migration support
  files are present as intended.

## 15. Documentation and examples

Add runnable examples for:

1. Creating and migrating a file-backed SQLite database.
2. Persisting accounts, a journal, and an entry.
3. Closing and reopening the application to prove durability.
4. Demonstrating a restricted deletion of a referenced account.
5. Demonstrating an allowed deletion and its durable audit event.
6. Exporting persisted postings to CSV.
7. Connecting to PostgreSQL using environment-provided configuration.

Generated database files, CSV outputs, and local credentials must remain
ignored. Documentation should use placeholder URLs and sanitized environment
examples.

## 16. Risks and mitigations

### Risk: ORM concerns leak into public models

**Mitigation:** Keep ORM rows private and require explicit mappers. Test that
services return Pydantic models after the SQLAlchemy session closes.

### Risk: SQLite behavior masks PostgreSQL incompatibilities

**Mitigation:** Run migration and repository contracts against PostgreSQL while
the schema is still small, not at the end of the project.

### Risk: Decimal values round silently

**Mitigation:** Make Decimal representation a Phase 0 decision gate and require
adversarial round-trip tests on both databases.

### Risk: Hard deletion damages historical integrity

**Mitigation:** Use restrictive foreign keys and specialized service lifecycle
rules. Prefer account deactivation and later entry reversal.

### Risk: Audit append and deletion diverge

**Mitigation:** Perform both operations through repositories sharing one unit
of work and transaction.

### Risk: ORM objects escape the session

**Mitigation:** Reconstruct complete domain models inside repositories and
never return ORM rows.

### Risk: JSON behavior differs by backend

**Mitigation:** Treat metadata as an opaque JSON-compatible value in Milestone
2. Avoid backend-specific metadata query promises.

### Risk: CSV becomes an accidental public schema

**Mitigation:** Name and document the initial posting format as version 1, use a
stable explicit header, and require a new version for incompatible changes.

### Risk: The milestone becomes too broad

**Mitigation:** Preserve the phase gates. Do not add import, reporting, async,
CLI, or web concerns while persistence and export contracts are unsettled.

## 17. Definition of done

Milestone 2 is complete when all of the following are true:

- [x] Lifecycle and Decimal storage decisions are recorded and tested.
- [x] Public domain models remain independent of SQLAlchemy.
- [x] SQLite and PostgreSQL dependencies are appropriately optional.
- [x] The initial Alembic migration works on SQLite and PostgreSQL.
- [x] SQLite foreign keys are enabled on every connection.
- [x] Account and journal codes are uniquely constrained case-insensitively.
- [x] Journal entries and lines persist atomically and retain line order.
- [x] Missing or inactive referenced accounts are rejected.
- [x] SQL repositories pass the shared repository contracts.
- [x] Domain records remain usable after the session closes.
- [x] Deletion policies protect historical accounting records.
- [x] Allowed deletion and audit append commit atomically.
- [x] PostgreSQL passes the same behavioral contract as SQLite.
- [x] Posting projection resolves account and journal display details.
- [x] CSV export is deterministic, exact, and properly quoted.
- [x] The customer metadata example survives persistence and export.
- [x] Documentation and runnable examples cover the complete workflow.
- [x] Formatting, lint, typing, tests, coverage, lock, and build checks pass.

## 18. Recommended implementation order

The shortest safe path is:

```text
Approve lifecycle and Decimal policy
                |
                v
Build SQLAlchemy and Alembic foundation
                |
                v
Implement schema, mappers, and SQLite repositories
                |
                v
Add unit-of-work transactions and lifecycle services
                |
                v
Verify PostgreSQL parity
                |
                v
Build PostingRow projection and CSV exporter
                |
                v
Document, package, and release Milestone 2
```

This order validates the riskiest storage decisions before adding convenient
output formats, while still delivering CSV as a visible end-to-end result of
the milestone.

## 19. Reference documentation

- [SQLAlchemy 2.0 documentation](https://docs.sqlalchemy.org/en/20/)
- [SQLAlchemy dialects](https://docs.sqlalchemy.org/en/20/dialects/)
- [SQLAlchemy constraints and indexes](https://docs.sqlalchemy.org/en/20/core/constraints.html)
- [SQLAlchemy SQLite dialect](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html)
- [SQLAlchemy PostgreSQL dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
- [Alembic documentation](https://alembic.sqlalchemy.org/en/latest/)
- [Python CSV documentation](https://docs.python.org/3/library/csv.html)
