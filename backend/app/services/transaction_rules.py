"""Canonical home for transaction business rules and category constants.

Every classification/category/expensed invariant lives here so the routers,
schemas, and services share one source of truth instead of re-implementing
the rules. This module deliberately imports nothing from the app's models at
module level so it sits at the bottom of the dependency graph
(``ensure_category_registered`` defers its model import for that reason —
``models.user_settings`` itself imports this module).
"""
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

INCOME_CATEGORY = "Income"
REIMBURSEMENT_CATEGORY = "Reimbursement"
TRANSFER_CATEGORY = "Transfer"

# Reimbursements are credit-only but offset a prior expense, so they are not
# counted as income. Only true "Income" credits aggregate into income totals.
INCOME_CATEGORIES: frozenset[str] = frozenset({INCOME_CATEGORY, REIMBURSEMENT_CATEGORY})

# Categories every install must keep; they carry special aggregation semantics
# (Income/Reimbursement are credit-only, Transfer is excluded from spending).
SYSTEM_CATEGORIES: frozenset[str] = frozenset(
    {INCOME_CATEGORY, REIMBURSEMENT_CATEGORY, TRANSFER_CATEGORY}
)

DEFAULT_CATEGORIES: list[str] = [
    "Groceries", "Dining", "Transportation", "Home", "Health",
    "Subscriptions", "Shopping", "Travel", "Entertainment",
    "Personal Care", "Gifts", "Other",
    TRANSFER_CATEGORY, INCOME_CATEGORY, REIMBURSEMENT_CATEGORY,
]

def validate_amount(amount_cents: int) -> int:
    """A transaction amount is a positive integer number of cents."""
    if amount_cents <= 0:
        raise ValueError("amount_cents must be greater than 0")
    return amount_cents


def validate_category_for_type(category: Optional[str], tx_type: str) -> None:
    """Income/Reimbursement are credit-only; raise 400 when assigned to a debit."""
    if category is None or category == TRANSFER_CATEGORY:
        return
    if category in INCOME_CATEGORIES and tx_type != "credit":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Income/Reimbursement categories only apply to credit transactions",
        )


def ensure_category_registered(db: "Session", category: Optional[str]) -> bool:
    """Auto-add an unknown personal category to ``UserSettings.personal_categories``.

    Unknown ``personal_category`` values are accepted and registered rather than
    rejected (maintainer decision 2026-06-09), so a category set through the API
    always appears in the Settings list and dropdowns. The compare is
    case-insensitive; the given casing is preserved on insert. Returns True when
    a category was added. The caller owns the commit.
    """
    if not category:
        return False
    name = category.strip()
    if not name:
        return False
    from app.models.user_settings import UserSettings

    settings = db.get(UserSettings, 1)
    if settings is None:
        settings = UserSettings(id=1, personal_categories=list(DEFAULT_CATEGORIES), hidden_pages=[])
        db.add(settings)
        db.flush()
    existing = list(settings.personal_categories or [])
    if any(str(c).strip().lower() == name.lower() for c in existing):
        return False
    # Reassign (not append in place) so SQLAlchemy detects the JSON change.
    settings.personal_categories = existing + [name]
    settings.updated_at = datetime.now(timezone.utc)
    return True


def apply_classification_side_effects(
    updates: dict, current_classification: Optional[str]
) -> dict:
    """Clear expensed/personal_category when a classification change invalidates them.

    ``updates`` is a partial field map (``classification`` may be absent, meaning
    "unchanged"); ``current_classification`` is the row's classification before the
    update. Mutates and returns ``updates``:

    - ``expensed`` is forced False when the update sets a non-work classification,
      or when classification is absent/null and the row isn't currently ``work``.
    - ``personal_category`` is forced None unless the row ends up ``personal``
      (the update's classification when present, else the current one).
    """
    next_classification = updates.get("classification", current_classification)
    if updates.get("classification") != "work" and (
        updates.get("classification") is not None or current_classification != "work"
    ):
        updates["expensed"] = False
    if next_classification != "personal":
        updates["personal_category"] = None
    return updates
