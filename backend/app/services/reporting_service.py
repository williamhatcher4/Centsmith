"""Financial aggregation queries shared by the dashboard and report endpoints.

All "last N months" figures derive their window from :func:`activity_window`
so the dashboard and the spending/income pages always cover the same months.
Functions return plain Python values (dicts/tuples); response-schema mapping
stays in the routers.
"""
import re
from typing import Iterable, Optional

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.services.transaction_rules import INCOME_CATEGORIES, TRANSFER_CATEGORY


def personal_signed_amount():
    """Personal spend sums debits positive and credits (refunds) negative."""
    return case(
        (Transaction.transaction_type == "debit", Transaction.amount_cents),
        else_=-Transaction.amount_cents,
    )


def personal_spending_filters():
    return [
        Transaction.classification == "personal",
        func.coalesce(Transaction.personal_category, "") != TRANSFER_CATEGORY,
        ~(
            (Transaction.transaction_type == "credit")
            & (Transaction.personal_category.in_(list(INCOME_CATEGORIES)))
        ),
    ]


def _work_spending_filters():
    return [
        Transaction.transaction_type == "debit",
        Transaction.classification == "work",
        func.coalesce(Transaction.personal_category, "") != TRANSFER_CATEGORY,
    ]


def _income_filters(categories: Iterable[str]):
    return [
        Transaction.transaction_type == "credit",
        Transaction.classification == "personal",
        Transaction.personal_category.in_(list(categories)),
    ]


def activity_window(db: Session, months: int) -> list[str]:
    """Most recent `months` calendar months that have any tracked activity.

    Union of personal-spend, work-spend, and income months, sorted ascending,
    last `months` entries. The dashboard and the spending-page spending/income
    endpoints all derive their window from this so every "last N months"
    figure covers the same months.
    """
    rows = db.query(
        func.strftime("%Y-%m", Transaction.transaction_date)
    ).filter(
        or_(
            and_(*personal_spending_filters()),
            and_(*_work_spending_filters()),
            and_(*_income_filters(INCOME_CATEGORIES)),
        )
    ).distinct().all()
    return sorted({month for (month,) in rows})[-months:]


def monthly_personal_spend(db: Session, window: list[str]) -> dict[str, int]:
    """Signed personal spend per window month: ``{month: cents}``."""
    if not window:
        return {}
    rows = db.query(
        func.strftime("%Y-%m", Transaction.transaction_date).label("month"),
        func.sum(personal_signed_amount()).label("amount"),
    ).filter(
        *personal_spending_filters(),
        func.strftime("%Y-%m", Transaction.transaction_date).in_(window),
    ).group_by("month").order_by("month").all()
    return {month: int(amount or 0) for month, amount in rows}


def monthly_work_spend(db: Session, window: list[str]) -> dict[str, int]:
    """Work debit spend per window month: ``{month: cents}``."""
    if not window:
        return {}
    rows = db.query(
        func.strftime("%Y-%m", Transaction.transaction_date).label("month"),
        func.sum(Transaction.amount_cents).label("amount"),
    ).filter(
        *_work_spending_filters(),
        func.strftime("%Y-%m", Transaction.transaction_date).in_(window),
    ).group_by("month").order_by("month").all()
    return {month: int(amount or 0) for month, amount in rows}


def monthly_income(
    db: Session, window: list[str], categories: Iterable[str] = INCOME_CATEGORIES
) -> list[tuple[str, str, int]]:
    """Income credits per window month and category: ``[(month, category, cents)]``."""
    if not window:
        return []
    rows = db.query(
        func.strftime("%Y-%m", Transaction.transaction_date).label("month"),
        Transaction.personal_category.label("category"),
        func.sum(Transaction.amount_cents).label("amount"),
    ).filter(
        *_income_filters(categories),
        func.strftime("%Y-%m", Transaction.transaction_date).in_(window),
    ).group_by("month", "category").order_by("month", "category").all()
    return [(month, category, int(amount or 0)) for month, category, amount in rows]


def category_breakdown(db: Session, window: list[str]) -> list[tuple[str, str, int]]:
    """Signed personal spend per window month and category: ``[(month, category, cents)]``."""
    if not window:
        return []
    rows = db.query(
        func.strftime("%Y-%m", Transaction.transaction_date).label("month"),
        func.coalesce(Transaction.personal_category, "Uncategorized").label("category"),
        func.sum(personal_signed_amount()).label("amount"),
    ).filter(
        *personal_spending_filters(),
        func.strftime("%Y-%m", Transaction.transaction_date).in_(window),
    ).group_by("month", "category").order_by("month", "category").all()
    return [(month, category, int(amount or 0)) for month, category, amount in rows]


# Merchant-name normalization for the dashboard "Top merchants" rollup.
# SQLite string munging is brittle, so this is done in Python after fetching rows.
_STORE_NUM_RE = re.compile(r"#\s*\d+")
_MASKED_REF_RE = re.compile(r"\bX{2,}\d*\b", re.IGNORECASE)
_DATE_FRAG_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_TRAILING_REF_RE = re.compile(r"\d{3,}$")


def normalize_merchant(description: Optional[str]) -> str:
    """Collapse a raw bank description into a stable merchant key.

    Uppercases, strips store numbers (``#1234``), masked card refs (``XXXX1234``),
    embedded date fragments, and a trailing all-numeric auth/store code so that
    e.g. ``STARBUCKS #1234`` and ``STARBUCKS #5678`` group together.
    """
    if not description:
        return ""
    text = description.upper()
    text = _STORE_NUM_RE.sub(" ", text)
    text = _MASKED_REF_RE.sub(" ", text)
    text = _DATE_FRAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = text.split(" ")
    # Drop a trailing reference/auth number left on the tail (e.g. "AMAZON 1234567").
    while len(parts) > 1 and _TRAILING_REF_RE.search(parts[-1]) and not any(c.isalpha() for c in parts[-1]):
        parts.pop()
    return " ".join(parts).strip()


def top_merchants(db: Session, window: list[str], limit: int = 5) -> list[tuple[str, int, int]]:
    """Top personal-debit merchants over the window: ``[(name, cents, count)]``."""
    if not window:
        return []
    merchant_rows = db.query(
        Transaction.description,
        Transaction.amount_cents,
    ).filter(
        Transaction.classification == "personal",
        Transaction.transaction_type == "debit",
        func.coalesce(Transaction.personal_category, "") != TRANSFER_CATEGORY,
        func.strftime("%Y-%m", Transaction.transaction_date).in_(window),
    ).all()
    merchant_totals: dict[str, list[int]] = {}
    for description, amount in merchant_rows:
        name = normalize_merchant(description)
        if not name:
            continue
        bucket = merchant_totals.setdefault(name, [0, 0])
        bucket[0] += int(amount or 0)
        bucket[1] += 1
    return [
        (name, cents, count)
        for name, (cents, count) in sorted(
            merchant_totals.items(), key=lambda kv: kv[1][0], reverse=True
        )
        if cents > 0
    ][:limit]


def unexpensed_work(db: Session) -> tuple[int, int]:
    """Work money still owed back (debit work rows not yet expensed): ``(cents, count)``."""
    cents, count = db.query(
        func.coalesce(func.sum(Transaction.amount_cents), 0),
        func.count(Transaction.id),
    ).filter(
        Transaction.transaction_type == "debit",
        Transaction.classification == "work",
        Transaction.expensed.is_(False),
        func.coalesce(Transaction.personal_category, "") != TRANSFER_CATEGORY,
    ).one()
    return int(cents or 0), int(count or 0)


def uncategorized_income(db: Session) -> tuple[int, int]:
    """Personal credits with no category yet: ``(cents, count)``."""
    cents, count = db.query(
        func.coalesce(func.sum(Transaction.amount_cents), 0),
        func.count(Transaction.id),
    ).filter(
        Transaction.transaction_type == "credit",
        Transaction.classification == "personal",
        Transaction.personal_category.is_(None),
    ).one()
    return int(cents or 0), int(count or 0)


def unsorted_count(db: Session) -> int:
    return db.query(Transaction).filter(Transaction.classification.is_(None)).count()
