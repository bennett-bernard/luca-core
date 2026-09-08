# Repository Guidelines

## Project Structure & Module Organization

Lumbago is a Python 3.12+ library using a `src/` layout. Public Pydantic models live
in `src/lumbago/models/`, workflows in `services/`, storage contracts in
`repositories/`, transactional adapters in `persistence/`, and posting/CSV
adapters in `exports/`. SQLAlchemy rows are private implementation details.
Versioned migrations are packaged under
`src/lumbago/persistence/sqlalchemy/migrations/` so installed wheels can migrate.
Keep tests under `tests/`, runnable walkthroughs under `examples/`, and longer
design/operation notes under `docs/`. Root files contain project configuration.

## Build, Test, and Development Commands

- `uv sync --locked --all-extras` — install the complete development environment.
- `uv run --all-extras ruff check .` — lint source, tests, and examples.
- `uv run --all-extras ruff format --check .` — verify formatting.
- `uv run --all-extras mypy src` — run strict library type checks.
- `uv run --all-extras pytest --cov=lumbago --cov-branch --cov-fail-under=100` — run
  tests and enforce full library statement/branch coverage.
- `uv lock --check` and `uv build` — validate dependencies and build distributions.
- `git status --short`, `git diff --check`, and `rg --files` — inspect changes.

PostgreSQL integration tests require `LUMBAGO_TEST_POSTGRES_URL` for a disposable
database whose user can create schemas. Tests remove only their own uniquely
named schemas. Without this variable PostgreSQL tests skip; do not describe
that as PostgreSQL validation. Never test against production data.

## Coding Style & Naming Conventions

Use UTF-8, LF endings, trailing newlines, descriptive `snake_case` names, and
Ruff's configured formatting and lint rules. Library code is strictly typed.
Keep optional SQL dependencies out of the top-level `lumbago` import. Domain
models must not depend on ORM rows, sessions, or lazy relationships. Services
and repositories never commit: callers own unit-of-work boundaries.

## Testing Guidelines

Include regression tests for fixes and shared contract tests for adapter
behavior. Exercise memory, in-memory SQLite, file-backed SQLite, and real
PostgreSQL. Check rollback and injected failure paths, not just happy paths.
Migration tests must upgrade from empty, compare against the ORM schema, and
round-trip downgrade/upgrade using disposable databases. Treat applied migration
revisions as immutable; future schema changes require new revisions.

## Commit & Pull Request Guidelines

Use concise, imperative, sentence-case subjects and keep commits focused.
Explain what changed and why, list actual validation performed, and link relevant
issues. Preserve unrelated local changes and user comments in planning files.
Do not commit or push unless requested.

## Security & Configuration

Never commit credentials, tokens, private keys, populated environment files,
generated databases, or review audio. `output/` and `dist/` are ignored. Add local
configuration patterns to `.gitignore` before introducing them; provide sanitized
examples where useful. Use explicit database URLs from application configuration
and opt-in migration commands. SQL logging is off by default and bind parameters
are hidden. Database constraints supplement, but do not replace, validated and
audited application workflows.
