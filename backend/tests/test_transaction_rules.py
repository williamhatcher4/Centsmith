"""Unit tests for the shared transaction-rules module (plan item P1.3).

These rules are also exercised end-to-end through the API tests; the unit
tests here pin the rule semantics directly so the four delegating call sites
(manual create, update, bulk-categorize, settings relabel) share one truth.
"""

import pytest
from fastapi import HTTPException

from app.services.transaction_rules import (
    DEFAULT_CATEGORIES,
    INCOME_CATEGORIES,
    INCOME_CATEGORY,
    REIMBURSEMENT_CATEGORY,
    SYSTEM_CATEGORIES,
    TRANSFER_CATEGORY,
    apply_classification_side_effects,
    ensure_category_registered,
    validate_amount,
    validate_category_for_type,
)


class TestConstants:
    def test_income_categories_are_the_credit_only_set(self):
        assert INCOME_CATEGORIES == {INCOME_CATEGORY, REIMBURSEMENT_CATEGORY}

    def test_system_categories_extend_income_with_transfer(self):
        assert SYSTEM_CATEGORIES == INCOME_CATEGORIES | {TRANSFER_CATEGORY}

    def test_default_categories_include_every_system_category(self):
        assert SYSTEM_CATEGORIES <= set(DEFAULT_CATEGORIES)


class TestValidateAmount:
    def test_positive_amount_returned_unchanged(self):
        assert validate_amount(450) == 450

    @pytest.mark.parametrize("cents", [0, -1, -500])
    def test_non_positive_amount_rejected(self, cents):
        with pytest.raises(ValueError):
            validate_amount(cents)


class TestValidateCategoryForType:
    @pytest.mark.parametrize("tx_type", ["debit", "credit"])
    def test_none_and_transfer_allowed_for_any_type(self, tx_type):
        validate_category_for_type(None, tx_type)
        validate_category_for_type(TRANSFER_CATEGORY, tx_type)

    @pytest.mark.parametrize("category", sorted(INCOME_CATEGORIES))
    def test_income_categories_allowed_on_credits(self, category):
        validate_category_for_type(category, "credit")

    @pytest.mark.parametrize("category", sorted(INCOME_CATEGORIES))
    def test_income_categories_rejected_on_debits(self, category):
        with pytest.raises(HTTPException) as exc_info:
            validate_category_for_type(category, "debit")
        assert exc_info.value.status_code == 400
        assert "credit transactions" in exc_info.value.detail

    def test_ordinary_category_allowed_on_debits(self):
        validate_category_for_type("Groceries", "debit")


class TestApplyClassificationSideEffects:
    def test_classify_personal_clears_expensed(self):
        updates = apply_classification_side_effects({"classification": "personal"}, "work")
        assert updates == {"classification": "personal", "expensed": False}

    def test_classify_work_clears_personal_category(self):
        updates = apply_classification_side_effects({"classification": "work"}, "personal")
        assert updates == {"classification": "work", "personal_category": None}

    def test_classification_absent_on_personal_row_clears_expensed_only(self):
        updates = apply_classification_side_effects({"description": "x"}, "personal")
        assert updates == {"description": "x", "expensed": False}

    def test_classification_absent_on_work_row_keeps_expensed(self):
        updates = apply_classification_side_effects({"description": "x"}, "work")
        assert updates == {"description": "x", "personal_category": None}

    def test_explicit_null_classification_clears_personal_category(self):
        updates = apply_classification_side_effects({"classification": None}, "personal")
        assert updates["personal_category"] is None
        assert updates["expensed"] is False

    def test_personal_category_in_update_survives_personal_classification(self):
        updates = apply_classification_side_effects(
            {"classification": "personal", "personal_category": "Dining"}, None
        )
        assert updates["personal_category"] == "Dining"
        assert updates["expensed"] is False


@pytest.fixture()
def rules_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.models import user_settings  # noqa: F401 — registers the table

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


class TestEnsureCategoryRegistered:
    """Unknown personal categories are auto-added, not rejected (P3.3)."""

    def _categories(self, db):
        from app.models.user_settings import UserSettings

        settings = db.get(UserSettings, 1)
        return list(settings.personal_categories) if settings else None

    def test_creates_settings_row_with_defaults_and_appends(self, rules_db):
        assert ensure_category_registered(rules_db, "Hobbies") is True
        rules_db.commit()
        assert self._categories(rules_db) == list(DEFAULT_CATEGORIES) + ["Hobbies"]

    def test_appends_to_existing_settings_preserving_given_casing(self, rules_db):
        from app.models.user_settings import UserSettings

        rules_db.add(UserSettings(id=1, personal_categories=["Groceries"], hidden_pages=[]))
        rules_db.commit()
        assert ensure_category_registered(rules_db, "  HoBBies  ") is True
        rules_db.commit()
        assert self._categories(rules_db) == ["Groceries", "HoBBies"]

    def test_case_insensitive_duplicate_is_not_double_added(self, rules_db):
        from app.models.user_settings import UserSettings

        rules_db.add(UserSettings(id=1, personal_categories=["Hobbies"], hidden_pages=[]))
        rules_db.commit()
        assert ensure_category_registered(rules_db, "hobbies") is False
        assert ensure_category_registered(rules_db, "HOBBIES") is False
        rules_db.commit()
        assert self._categories(rules_db) == ["Hobbies"]

    @pytest.mark.parametrize("category", [None, "", "   "])
    def test_blank_categories_are_ignored(self, rules_db, category):
        assert ensure_category_registered(rules_db, category) is False

    def test_system_category_is_not_duplicated(self, rules_db):
        assert ensure_category_registered(rules_db, INCOME_CATEGORY) is False
        rules_db.commit()
        assert self._categories(rules_db) == list(DEFAULT_CATEGORIES)
