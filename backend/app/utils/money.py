from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def cents_to_display(cents: int) -> str:
    """Convert integer cents to a display string: 123456 -> '$1,234.56'"""
    dollars = abs(cents) / 100
    sign = "-" if cents < 0 else ""
    return f"{sign}${dollars:,.2f}"


def display_to_cents(value: str) -> int:
    """Convert a display string to integer cents: '$1,234.56' -> 123456"""
    cleaned = value.replace("$", "").replace(",", "").strip()
    negative = cleaned.startswith("-")
    cleaned = cleaned.lstrip("-")
    try:
        cents = int((Decimal(cleaned) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        return 0
    return -cents if negative else cents
