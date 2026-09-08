"""Storage coordination contracts, independent of optional SQL dependencies."""

from lumbago.persistence.unit_of_work import UnitOfWork

__all__ = ["UnitOfWork"]
