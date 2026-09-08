"""Private SQL foundations and lossless portable column types."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

from sqlalchemy import BigInteger, DateTime, MetaData, Numeric
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator, TypeEngine

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Private declarative base; public models never inherit from this."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UTCDateTime(TypeDecorator[datetime]):
    """Store aware UTC timestamps; restore SQLite's missing timezone marker."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )


class WholeHundredths(TypeDecorator[int]):
    """Store integer hundredths without PostgreSQL's implicit integer rounding.

    PostgreSQL uses unrestricted NUMERIC plus a whole-number CHECK. Specifying
    NUMERIC(p, 0) or BIGINT would round a fractional input before CHECK runs.
    SQLite uses no affinity plus an explicit integer typeof CHECK, so fractional
    numeric inputs cannot be coerced to integers before validation.
    """

    impl = BigInteger
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[int]:
        storage_type = (
            Numeric(asdecimal=True) if dialect.name == "postgresql" else BigInteger()
        )
        return cast(TypeEngine[int], dialect.type_descriptor(storage_type))

    def process_result_value(
        self, value: Decimal | int | None, dialect: Dialect
    ) -> int | None:
        if value is None:
            return None
        if value != int(value):
            raise ValueError("stored monetary hundredths must be whole numbers")
        return int(value)


@compiles(WholeHundredths, "sqlite")
def compile_sqlite_hundredths(
    type_: WholeHundredths, compiler: object, **kwargs: object
) -> str:
    """BLOB means no SQLite affinity; the CHECK permits only integer storage."""

    return "BLOB"
