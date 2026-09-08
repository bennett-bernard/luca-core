# Runnable examples

Run these scripts from the repository root after `uv sync --all-extras`:

```console
uv run --all-extras python examples/01_accounting_flow.py
uv run --all-extras python examples/02_validation_errors.py
uv run --all-extras python examples/03_delete_audit.py
uv run --all-extras python examples/04_custom_account.py
uv run --all-extras python examples/05_persistence_and_csv.py
```

The first four examples are independent and use the legacy in-memory adapters,
so they do not leave application data behind.

Example 5 demonstrates the transactional API using SQLite by default. It creates
or reuses demo accounts and a journal, saves a new balanced sale for customer
Acme, proves a referenced account cannot be deleted, and deletes unused records
with audit snapshots. It then opens a new database connection and exports the
saved entry to CSV. Each run adds one entry and two deletion audit events.

The database and uniquely named CSV files go under Git-ignored
`output/milestone2/`. Use `--output-dir /path/to/scratch` to select another output
directory. No earlier CSV is overwritten. To run the same example against
PostgreSQL, install the `postgres` extra and set `LUMBAGO_DATABASE_URL` to a database
you intend to populate with demo data. Do not use a production database or
commit credentials. PostgreSQL URLs use `postgresql+psycopg://...`.

See [persistence operations and decisions](../docs/persistence.md) for transaction
ownership, explicit migration commands, exact money rules, and CSV details.
