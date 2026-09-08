# Lumbago Core

[A short introduction to Lumbago](https://bennett-bernard.github.io/luca-core/).

Lumbago Core is the foundational library for the open-source Lumbago accounting
framework. It represents accounting transactions in a minimal form while
enforcing strong data validation.

The project aims to provide low-level scaffolding for defining basic
transactions using the lowest common denominator of accounting data. Its
simplicity is intentional: Lumbago is designed to be easy to understand, extend,
and adapt without forcing every use case into a complex accounting system.

Lumbago's code and data structures are intended to be readable by both people and
AI agents. This gives accounting professionals a foundation for building
bespoke tools and systems without repeatedly reinventing core transaction
types.

## Core principles

### Data

- Provide a strongly validated core data model built with Pydantic classes.
- Keep common workflows simple by default while allowing additional complexity
  when a use case requires it.

### Reporting

- Provide ORM-based persistence for databases such as SQLite, PostgreSQL,
  MariaDB, and others.
- Make it easy to write data to common file formats, including plain text,
  JSON, and CSV.
- Include a built-in web interface for browsing and sharing data.

### Governance

- Offer effective, straightforward user management.
- Make audit trails part of the core data model through events.

### Experience

- Include a CLI designed for convenient use by people and AI agents alike.

## Project status

Lumbago is in early development. Version 0.2 implements Milestone 2 and provides:

- Validated models for accounts, journals, monetary values, journal lines, and
  journal entries.
- Double-entry validation that balances debits and credits independently for
  each currency.
- Stable record identifiers, UTC-normalized timestamps, descriptive generated
  schemas, and JSON serialization.
- Storage-neutral contracts, transactional in-memory storage, and optional
  SQLite and PostgreSQL persistence with packaged Alembic migrations.
- Caller-owned transactions that save complete entries atomically and roll back
  unfinished workflows.
- Case-insensitive account and journal codes, protected historical references,
  and atomic deletion audit snapshots for unused accounts and journals.
- Exact, nonnegative monetary amounts with at most two decimal places, checked
  in both the domain models and SQL storage.
- Deterministic, one-row-per-posting CSV export with resolved account and journal
  information.

Persisted entries have no draft state and cannot be updated or deleted through
the transactional repositories. Corrections require new entries. The web
interface, CLI, user governance, financial reports, and other SQL dialects are
still planned capabilities. This is an early library API, not a complete
accounting application.

## Installation

Python 3.12 or newer is required. SQL dependencies remain optional:

```console
pip install lumbago-core               # Models, memory storage, and CSV
pip install 'lumbago-core[sql]'        # Also SQLite and migrations
pip install 'lumbago-core[postgres]'   # Also PostgreSQL with psycopg
```

For an unpublished checkout, use `uv sync --all-extras` instead.

## Core model example

```python
from datetime import date
from decimal import Decimal
from uuid import uuid4

from lumbago import EntrySide, JournalEntry, JournalLine, Money

cash_account_id = uuid4()
revenue_account_id = uuid4()
entry_id = uuid4()

entry = JournalEntry(
    id=entry_id,
    journal_id=uuid4(),
    transaction_date=date(2026, 8, 22),
    description="Record a cash sale",
    lines=(
        JournalLine(
            journal_entry_id=entry_id,
            account_id=cash_account_id,
            side=EntrySide.DEBIT,
            amount=Money(amount=Decimal("125.00"), currency="USD"),
        ),
        JournalLine(
            journal_entry_id=entry_id,
            account_id=revenue_account_id,
            side=EntrySide.CREDIT,
            amount=Money(amount=Decimal("125.00"), currency="USD"),
        ),
    ),
)
```

Unbalanced entries, zero-value lines, invalid currency codes, unknown fields,
and naive audit timestamps are rejected during validation. Pass monetary values
as `Decimal`, decimal strings, or integers, not binary floats. Values with
fractional hundredths such as `"12.345"` are rejected, not rounded; harmless
trailing zeros such as `"12.3400"` normalize to `"12.34"`. The maximum monetary
amount is `9999999999999999.99`. These are intentional changes from 0.1.

## Durable persistence and export

Create a store, migrate explicitly, and commit each successful workflow:

```python
from lumbago import (
    Account,
    AccountType,
    AccountingService,
    export_postings_csv,
    project_postings,
)
from lumbago.persistence.sqlalchemy import SqlAlchemyStore
from pathlib import Path

store = SqlAlchemyStore("sqlite+pysqlite:///lumbago.db")
try:
    store.migrate()  # Explicit schema upgrade, never an automatic startup action
    with store.unit_of_work() as uow:
        service = AccountingService(uow)
        service.create_account(
            Account(code="CASH", name="Cash", account_type=AccountType.ASSET)
        )
        uow.commit()  # No commit means rollback on exit

    with store.unit_of_work() as uow:
        rows = project_postings(
            uow.journal_entries.list(), uow.accounts.list(), uow.journals.list()
        )
    Path("output").mkdir(exist_ok=True)
    with open("output/postings.csv", "w", encoding="utf-8", newline="") as output:
        export_postings_csv(rows, output)
finally:
    store.close()
```

Use a fresh database for this short example; running it twice rejects duplicate
`CASH`. The complete, rerunnable [persistence example](examples/05_persistence_and_csv.py)
creates a balanced sale, reopens storage, demonstrates deletion protection and
audit events, and exports the resulting postings. Replace the URL with
`postgresql+psycopg://...` to use PostgreSQL.

See [persistence decisions and operations](docs/persistence.md) for the exact
transaction, precision, migration, subclassing, CSV, and concurrency contracts.
Use `InMemoryStore` for the same transactional API without a database. The
original standalone `InMemoryRepository` remains available with its legacy,
nontransactional behavior.

More runnable walkthroughs are available in [`examples/`](examples/README.md),
including validation failures, audited deletion, and model subclassing.

## Development

Install the locked development environment and run the quality checks with
`uv`:

```console
uv sync --locked --all-extras
uv run --all-extras ruff check .
uv run --all-extras ruff format --check .
uv run --all-extras mypy src
uv run --all-extras pytest --cov=lumbago --cov-branch --cov-fail-under=100
uv lock --check
uv build
```

PostgreSQL tests skip unless `LUMBAGO_TEST_POSTGRES_URL` points to a disposable
PostgreSQL database. Tests create and remove uniquely named schemas there;
never use a production database. The test user must be allowed to create
schemas. CI runs the contracts against memory, both SQLite modes, and a real
PostgreSQL 17 service. Generated databases, `output/`, and `dist/` (including
review audio) are ignored by Git.

GitHub Pages publishes `docs/index.html` from the `main` branch. Changes to
that page are published automatically. `docs/.nojekyll` keeps it as plain HTML.

## License

Lumbago is available under the [MIT License](LICENSE).
