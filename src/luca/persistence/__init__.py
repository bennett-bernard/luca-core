"""Storage coordination contracts, independent of optional SQL dependencies."""

from luca.persistence.unit_of_work import UnitOfWork

__all__ = ["UnitOfWork"]
