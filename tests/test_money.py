"""Tests for money handling, precision enforcement, and currency validation."""

from decimal import Decimal

import pytest

from agentbounty.domain.money import (
    DEFAULT_CURRENCY,
    Money,
    from_minor_units,
    to_minor_units,
    validate_currency,
)
from agentbounty.domain.schemas import BountyCreate, PaymentAuthorizationCreate, PaymentTransactionCreate
from agentbounty.exceptions import InvalidMoneyError


def test_to_minor_units_exact() -> None:
    """Exact conversions: $5.00 -> 500, $0.50 -> 50, $12.34 -> 1234."""
    assert to_minor_units(Decimal("5.00")) == 500
    assert to_minor_units(Decimal("0.50")) == 50
    assert to_minor_units(Decimal("12.34")) == 1234
    assert to_minor_units(Decimal("0.00"), allow_negative=False) == 0
    assert to_minor_units(Decimal("0.01")) == 1


def test_from_minor_units_exact() -> None:
    """Exact reverse conversions: 500 -> $5.00, 50 -> $0.50, 1234 -> $12.34."""
    assert from_minor_units(500) == Decimal("5.00")
    assert from_minor_units(50) == Decimal("0.50")
    assert from_minor_units(1234) == Decimal("12.34")
    assert from_minor_units(0) == Decimal("0.00")
    assert from_minor_units(1) == Decimal("0.01")


def test_round_trip_conversion() -> None:
    """Round-trip conversion preserves identity."""
    values = ["0.01", "0.50", "1.00", "5.00", "12.34", "99.99"]
    for val_str in values:
        original = Decimal(val_str)
        minor = to_minor_units(original)
        reconstituted = from_minor_units(minor)
        assert reconstituted == original


def test_reject_float_in_to_minor_units() -> None:
    """Floating-point values must be strictly rejected."""
    with pytest.raises(InvalidMoneyError, match="Floating-point values are strictly forbidden"):
        to_minor_units(5.00)  # type: ignore[arg-type]

    with pytest.raises(InvalidMoneyError, match="Floating-point values are strictly forbidden"):
        to_minor_units(0.5)  # type: ignore[arg-type]


def test_reject_float_in_from_minor_units() -> None:
    """Floating-point values for minor units must be rejected."""
    with pytest.raises(InvalidMoneyError, match="Minor units must be an integer"):
        from_minor_units(500.0)  # type: ignore[arg-type]


def test_reject_non_integral_subcents() -> None:
    """Sub-cent amounts must be rejected; silent rounding is forbidden."""
    with pytest.raises(InvalidMoneyError, match="Silent rounding is strictly forbidden"):
        to_minor_units(Decimal("5.005"))

    with pytest.raises(InvalidMoneyError, match="Silent rounding is strictly forbidden"):
        to_minor_units(Decimal("0.1234"))


def test_reject_nan_and_infinities() -> None:
    """NaN and infinity Decimal values must be rejected."""
    with pytest.raises(InvalidMoneyError, match="cannot be NaN or Infinite"):
        to_minor_units(Decimal("NaN"))

    with pytest.raises(InvalidMoneyError, match="cannot be NaN or Infinite"):
        to_minor_units(Decimal("Infinity"))

    with pytest.raises(InvalidMoneyError, match="cannot be NaN or Infinite"):
        to_minor_units(Decimal("-Infinity"))


def test_reject_negative_when_disallowed() -> None:
    """Negative values must be rejected by default."""
    with pytest.raises(InvalidMoneyError, match="Negative monetary amount"):
        to_minor_units(Decimal("-5.00"), allow_negative=False)

    with pytest.raises(InvalidMoneyError, match="Negative minor units"):
        from_minor_units(-500, allow_negative=False)


def test_currency_validation() -> None:
    """Supported currencies pass and normalize; unsupported currencies are rejected."""
    assert validate_currency("USD") == "USD"
    assert validate_currency("usd") == "USD"
    assert validate_currency(" usd ") == "USD"

    with pytest.raises(InvalidMoneyError, match="Unsupported currency 'EUR'"):
        validate_currency("EUR")

    with pytest.raises(InvalidMoneyError, match="Currency code must be a string"):
        validate_currency(123)  # type: ignore[arg-type]


def test_money_value_object() -> None:
    """Money value object behaves immutably and safely."""
    m1 = Money(Decimal("5.00"))
    assert m1.amount == Decimal("5.00")
    assert m1.currency == DEFAULT_CURRENCY
    assert m1.minor_units == 500

    m2 = Money.from_minor_units(50)
    assert m2.amount == Decimal("0.50")
    assert m2.minor_units == 50

    m3 = Money.from_string("12.34")
    assert m3.amount == Decimal("12.34")
    assert m3.minor_units == 1234

    # Addition
    sum_money = m1 + m2
    assert sum_money.amount == Decimal("5.50")
    assert sum_money.minor_units == 550

    # Subtraction
    diff_money = m1 - m2
    assert diff_money.amount == Decimal("4.50")

    # Reject subtraction into negative
    with pytest.raises(InvalidMoneyError, match="cannot become negative"):
        _ = m2 - m1

    # String representation
    assert str(m1) == "5.00 USD"


def test_pydantic_schemas_reject_float_money() -> None:
    """Pydantic domain schemas must reject float inputs for financial fields."""
    with pytest.raises(InvalidMoneyError, match="Floating-point values are strictly forbidden"):
        BountyCreate(task_id="test-task", amount=5.0)  # type: ignore[arg-type]

    with pytest.raises(InvalidMoneyError, match="Floating-point values are strictly forbidden"):
        PaymentAuthorizationCreate(
            task_id="t1",
            bounty_id="b1",
            authorized_by="user1",
            decision="AUTHORIZED",  # type: ignore[arg-type]
            authorized_amount=5.0,  # type: ignore[arg-type]
        )

    with pytest.raises(InvalidMoneyError, match="Floating-point values are strictly forbidden"):
        PaymentTransactionCreate(
            task_id="t1",
            bounty_id="b1",
            provider_name="mock",
            execution_mode="SIMULATED",  # type: ignore[arg-type]
            amount=5.0,  # type: ignore[arg-type]
            idempotency_key="unique-key-12345",
        )
