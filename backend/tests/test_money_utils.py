import pytest

from app.utils.money import cents_to_display, display_to_cents


@pytest.mark.parametrize(
    "cents,expected",
    [
        (0, "$0.00"),
        (1, "$0.01"),
        (99, "$0.99"),
        (100, "$1.00"),
        (123456, "$1,234.56"),
        (-425, "-$4.25"),
        (-100000000, "-$1,000,000.00"),
    ],
)
def test_cents_to_display_formats_with_sign_and_commas(cents, expected):
    assert cents_to_display(cents) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$1,234.56", 123456),
        ("1234.56", 123456),
        ("$0.99", 99),
        ("-$4.25", -425),
        ("-4.25", -425),
        (" $1,234.56 ", 123456),
    ],
)
def test_display_to_cents_strips_currency_and_separators(raw, expected):
    assert display_to_cents(raw) == expected


def test_display_to_cents_returns_zero_for_garbage():
    assert display_to_cents("not-a-number") == 0


def test_display_to_cents_uses_half_up_rounding():
    assert display_to_cents("0.005") == 1
    assert display_to_cents("-0.005") == -1


def test_round_trip_preserves_value():
    for cents in (0, 1, 99, 100, 123456, -425, -100000000):
        assert display_to_cents(cents_to_display(cents)) == cents
