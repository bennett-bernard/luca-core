"""Optional SQL storage. Install lumbago-core[sql] or lumbago-core[postgres] to use it."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config

from lumbago.models.accounting import Account, Journal, JournalEntry
from lumbago.models.base import utc_now
from lumbago.persistence.sqlalchemy.engine import create_lumbago_engine
from lumbago.persistence.sqlalchemy.repositories import translate_errors
from lumbago.persistence.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork

__all__ = ["SqlAlchemyStore", "SqlAlchemyUnitOfWork"]


class SqlAlchemyStore:
    """Own database connectivity; schema changes happen only via migrate()."""

    def __init__(
        self,
        url: str,
        *,
        echo: bool = False,
        account_type: type[Account] = Account,
        journal_type: type[Journal] = Journal,
        entry_type: type[JournalEntry] = JournalEntry,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._engine = create_lumbago_engine(url, echo=echo)
        self._account_type = account_type
        self._journal_type = journal_type
        self._entry_type = entry_type
        self._clock = clock

    def migrate(self) -> None:
        """Explicitly upgrade this database using packaged, versioned migrations."""

        config = Config()
        config.set_main_option(
            "script_location", str(Path(__file__).with_name("migrations"))
        )
        with translate_errors("migration"), self._engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        """Create a fresh, caller-owned transactional scope."""

        return SqlAlchemyUnitOfWork(
            self._engine,
            account_type=self._account_type,
            journal_type=self._journal_type,
            entry_type=self._entry_type,
            clock=self._clock,
        )

    def close(self) -> None:
        """Release the engine's pooled connections when the application is done."""

        self._engine.dispose()
