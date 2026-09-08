"""Exact money and balancing regressions independent of ambient Decimal settings."""

from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from luca import EntrySide, JournalEntry, Money
from luca.models.money import (
    MAX_AMOUNT,
    MAX_MINOR_UNITS,
    from_minor_units,
    to_minor_units,
)
from tests.helpers import account, entry, journal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", "0.00"),
        ("12", "12.00"),
        ("12.3", "12.30"),
        ("12.34", "12.34"),
        ("12.34000", "12.34"),
        ("0.01", "0.01"),
        (str(MAX_AMOUNT), str(MAX_AMOUNT)),
    ],
)
def test_money_normalizes_without_rounding(raw: str, expected: str) -> None:
    with localcontext() as context:
        context.prec = 2
        amount = Money(amount=raw, currency="usd")
        assert str(amount.amount) == expected
        assert from_minor_units(amount.minor_units) == amount.amount


@pytest.mark.parametrize(
    "value", ["12.345", "0.001", "-0.01", "NaN", "Infinity", "1E28", "1E-10000", 12.34]
)
def test_money_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValidationError):
        Money.model_validate({"amount": value, "currency": "USD"})


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("-1"), Decimal("1E30")])
def test_encoder_checks_range(value: Decimal) -> None:
    with pytest.raises(ValueError):
        to_minor_units(value)


@pytest.mark.parametrize("value", [-1, MAX_MINOR_UNITS + 1, Decimal("1.1"), True])
def test_decoder_rejects_invalid_hundredths(value: object) -> None:
    with pytest.raises(ValueError):
        from_minor_units(value)


def test_balance_does_not_lose_small_lines_or_depend_on_decimal_context() -> None:
    original = entry(account(), account("REVENUE"), journal(), amount=str(MAX_AMOUNT))
    values = original.model_dump(mode="python")
    extra = dict(
        values["lines"][0],
        id=uuid4(),
        amount={"amount": "0.01", "currency": "USD"},
    )
    values["lines"] = [*values["lines"], extra]
    with localcontext() as context:
        context.prec = 2
        with pytest.raises(ValidationError, match="unbalanced"):
            JournalEntry.model_validate(values)
        values["lines"].append(dict(extra, id=uuid4(), side=EntrySide.CREDIT))
        assert len(JournalEntry.model_validate(values).lines) == 4
