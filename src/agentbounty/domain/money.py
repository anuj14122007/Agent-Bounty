"""Money handling utility for AgentBounty.

CRITICAL FINANCIAL SAFETY INVARIANT:
Floating-point values (Python float) must NEVER be used for monetary calculations or storage.
Float arithmetic introduces precision and rounding errors that are unacceptable in financial systems.

Architecture & Storage Rules:
1. Application-level calculations: Use Python `decimal.Decimal`.
2. Database persistence: Stored strictly as signed 64-bit integers representing minor units
   (e.g., cents in USD: $5.00 -> 500, $0.50 -> 50, $12.34 -> 1234).
3. Precision: USD allows at most 2 decimal places. Sub-cent amounts are rejected, never silently rounded.
4. Currencies: ISO 4217 currency codes. Initially, AgentBounty strictly supports "USD" (minor unit exponent = 2).
   Future currencies (e.g. EUR, JPY, GBP) can be registered in SUPPORTED_CURRENCIES by defining their minor unit
   exponent (e.g. JPY exponent 0, EUR exponent 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from agentbounty.exceptions import InvalidMoneyError

# Registry of supported ISO 4217 currencies and their minor unit exponents (number of decimal places)
# USD is the primary fiat currency for AgentBounty hackathon milestones.
SUPPORTED_CURRENCIES: dict[str, int] = {
    "USD": 2,
}

DEFAULT_CURRENCY = "USD"


def validate_currency(currency: str) -> str:
    """Validate that the currency code is a supported ISO 4217 code.

    Args:
        currency: The 3-letter currency code (case-insensitive).

    Returns:
        The normalized uppercase currency code.

    Raises:
        InvalidMoneyError: If currency is not supported or not a string.
    """
    if not isinstance(currency, str):
        raise InvalidMoneyError(f"Currency code must be a string, got {type(currency).__name__}")

    normalized = currency.strip().upper()
    if normalized not in SUPPORTED_CURRENCIES:
        supported_list = ", ".join(SUPPORTED_CURRENCIES.keys())
        raise InvalidMoneyError(
            f"Unsupported currency '{currency}'. Currently supported currencies: {supported_list}. "
            "To support additional ISO 4217 currencies, register them with their minor unit exponent."
        )
    return normalized


def to_minor_units(
    amount: Decimal,
    currency: str = DEFAULT_CURRENCY,
    allow_negative: bool = False,
) -> int:
    """Safely convert a Decimal monetary amount to integer minor units.

    Args:
        amount: The monetary amount as a Decimal.
        currency: The ISO 4217 currency code.
        allow_negative: Whether negative amounts are permitted (default False).

    Returns:
        The integer minor units (e.g., 500 for $5.00).

    Raises:
        InvalidMoneyError: If amount is a float, NaN, infinity, negative (when not allowed),
                           or has fractional minor units.
    """
    if isinstance(amount, float):
        raise InvalidMoneyError(
            "Floating-point values are strictly forbidden for monetary amounts. Use decimal.Decimal."
        )

    if not isinstance(amount, Decimal):
        raise InvalidMoneyError(f"Expected decimal.Decimal, got {type(amount).__name__}")

    if amount.is_nan() or amount.is_infinite():
        raise InvalidMoneyError("Monetary amounts cannot be NaN or Infinite.")

    if not allow_negative and amount < Decimal(0):
        raise InvalidMoneyError(f"Negative monetary amount {amount} is not allowed.")

    curr = validate_currency(currency)
    exponent = SUPPORTED_CURRENCIES[curr]
    scale_factor = Decimal(10**exponent)

    scaled = amount * scale_factor
    # Reject amounts that would require rounding (fractional minor units / sub-cents)
    integral_scaled = scaled.to_integral_value()
    if scaled != integral_scaled:
        raise InvalidMoneyError(
            f"Monetary amount {amount} has precision exceeding {exponent} decimal places for {curr}. "
            "Silent rounding is strictly forbidden."
        )

    return int(integral_scaled)


def from_minor_units(
    minor_units: int,
    currency: str = DEFAULT_CURRENCY,
    allow_negative: bool = False,
) -> Decimal:
    """Safely convert integer minor units to a Decimal monetary amount.

    Args:
        minor_units: The integer minor units (e.g., 500 for $5.00).
        currency: The ISO 4217 currency code.
        allow_negative: Whether negative amounts are permitted (default False).

    Returns:
        The monetary amount as a Decimal with exact precision.

    Raises:
        InvalidMoneyError: If minor_units is a float, not an integer, or negative when not allowed.
    """
    if isinstance(minor_units, bool) or not isinstance(minor_units, int):
        raise InvalidMoneyError(
            f"Minor units must be an integer (got {type(minor_units).__name__}). "
            "Floats and other types are strictly forbidden."
        )

    if not allow_negative and minor_units < 0:
        raise InvalidMoneyError(f"Negative minor units {minor_units} are not allowed.")

    curr = validate_currency(currency)
    exponent = SUPPORTED_CURRENCIES[curr]

    # Convert using exact decimal scaling
    result = Decimal(minor_units) / (Decimal(10) ** exponent)
    # Quantize to ensure representation matches currency precision (e.g., '5.00')
    quantum = Decimal(10) ** (-exponent)
    return result.quantize(quantum)


@dataclass(frozen=True)
class Money:
    """Immutable domain Value Object representing a monetary amount in a specific currency."""

    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise InvalidMoneyError(
                "Floating-point values are strictly forbidden for monetary amounts. Use decimal.Decimal."
            )
        if not isinstance(self.amount, Decimal):
            raise InvalidMoneyError(f"Expected decimal.Decimal, got {type(self.amount).__name__}")
        if self.amount.is_nan() or self.amount.is_infinite():
            raise InvalidMoneyError("Monetary amounts cannot be NaN or Infinite.")
        if self.amount < Decimal(0):
            raise InvalidMoneyError(f"Negative monetary amount {self.amount} is not allowed.")

        normalized_currency = validate_currency(self.currency)
        object.__setattr__(self, "currency", normalized_currency)

        # Enforce no fractional sub-cents
        exponent = SUPPORTED_CURRENCIES[normalized_currency]
        scale = Decimal(10**exponent)
        scaled = self.amount * scale
        if scaled != scaled.to_integral_value():
            raise InvalidMoneyError(
                f"Monetary amount {self.amount} exceeds allowed {exponent} decimal places for {normalized_currency}."
            )
        quantum = Decimal(10) ** (-exponent)
        object.__setattr__(self, "amount", self.amount.quantize(quantum))

    @classmethod
    def from_minor_units(cls, minor_units: int, currency: str = DEFAULT_CURRENCY) -> Money:
        """Create a Money instance from database minor units."""
        decimal_val = from_minor_units(minor_units, currency=currency)
        return cls(amount=decimal_val, currency=currency)

    @classmethod
    def from_string(cls, amount_str: str, currency: str = DEFAULT_CURRENCY) -> Money:
        """Create a Money instance from a string representation (e.g. '5.00')."""
        try:
            val = Decimal(amount_str)
        except InvalidOperation as err:
            raise InvalidMoneyError(f"Invalid monetary string '{amount_str}'") from err
        return cls(amount=val, currency=currency)

    @property
    def minor_units(self) -> int:
        """Return the integer minor units for database persistence."""
        return to_minor_units(self.amount, self.currency)

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"

    def __add__(self, other: Any) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise InvalidMoneyError(
                f"Cannot add money of different currencies: {self.currency} and {other.currency}"
            )
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Any) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise InvalidMoneyError(
                f"Cannot subtract money of different currencies: {self.currency} and {other.currency}"
            )
        new_amount = self.amount - other.amount
        if new_amount < Decimal(0):
            raise InvalidMoneyError("Monetary amounts cannot become negative.")
        return Money(amount=new_amount, currency=self.currency)
