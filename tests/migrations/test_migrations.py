"""Exercise packaged Alembic revisions against both supported SQL dialects."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from luca.persistence.sqlalchemy import SqlAlchemyStore
from luca.persistence.sqlalchemy.base import Base


def test_upgrade_downgrade_and_schema_parity(sql_store: SqlAlchemyStore) -> None:
    sql_store.migrate()
    config = Config("alembic.ini")
    with sql_store._engine.begin() as connection:
        inspector = inspect(connection)
        assert set(inspector.get_table_names()) == {
            "accounts",
            "journals",
            "journal_entries",
            "journal_lines",
            "audit_events",
            "alembic_version",
        }
        assert (
            inspector.get_unique_constraints("accounts")[0]["name"]
            == "uq_accounts_code_key"
        )
        assert len(inspector.get_foreign_keys("journal_lines")) == 2
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() == "0001_initial"
        assert compare_metadata(context, Base.metadata) == []
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
    with sql_store.unit_of_work() as uow:
        assert uow.accounts.list() == ()
