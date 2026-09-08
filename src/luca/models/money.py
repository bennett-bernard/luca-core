"""Validated monetary values used throughout Luca."""

from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints, field_validator

from luca.models.base import LucaModel

CurrencyCode = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
        strip_whitespace=True,
    ),
]

MAX_MINOR_UNITS = 999_999_999_999_999_999
MAX_AMOUNT = Decimal("9999999999999999.99")


def to_minor_units(value: Decimal) -> int:
    """Convert an exact two-place amount without using the decimal context."""

    if not value.is_finite() or value < 0 or value > MAX_AMOUNT:
        raise ValueError(f"amount must be between 0 and {MAX_AMOUNT}")
    if value.is_zero():
        return 0
    _, digits, exponent = value.as_tuple()
    assert isinstance(exponent, int)
    shift = exponent + 2
    if shift < 0:
        if any(digits[shift:]):
            raise ValueError("amount must not have more than two decimal places")
        digits = digits[:shift]
        shift = 0
    return int(int("".join(map(str, digits))) * 10**shift)


def from_minor_units(value: int) -> Decimal:
    """Decode whole hundredths without arithmetic rounding."""

    if type(value) is not int or not 0 <= value <= MAX_MINOR_UNITS:
        raise ValueError("minor units must be a nonnegative integer within range")
    return Decimal(f"{value // 100}.{value % 100:02d}")


class Money(LucaModel):
    """A nonnegative, exact two-decimal amount denominated in one currency."""

    amount: Decimal = Field(
        ge=0,
        le=MAX_AMOUNT,
        description=(
            "Nonnegative monetary quantity with at most two decimal places, "
            "normalized to two places without rounding. Use string, Decimal, or "
            "integer inputs; binary floating-point inputs are rejected."
        ),
        examples=["1250.00"],
    )

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float_amounts(cls, value: object) -> object:
        """Require callers to supply amounts without binary floating-point loss."""

        if isinstance(value, float):
            raise ValueError("use a string or Decimal for monetary amounts, not float")
        return value

    @field_validator("amount")
    @classmethod
    def normalize_amount(cls, value: Decimal) -> Decimal:
        """Reject fractional hundredths and retain a fixed two-place encoding."""

        return from_minor_units(to_minor_units(value))

    @property
    def minor_units(self) -> int:
        """Return the amount as an exact number of hundredths."""

        return to_minor_units(self.amount)

    currency: CurrencyCode = Field(
        description=(
            "Three-letter uppercase currency code, normally an ISO 4217 code such as "
            "USD, EUR, or GBP."
        ),
        examples=["USD"],
    )

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        """Accept human-friendly lowercase codes while storing a canonical value."""

        if isinstance(value, str):
            return value.strip().upper()
        return value
