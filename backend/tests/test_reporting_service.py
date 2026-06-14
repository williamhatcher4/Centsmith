"""Direct unit tests for the reporting service (plan item P1.1).

The dashboard/spending/income API tests cover the composed behavior; these
tests pin the shared window helper and the aggregation primitives directly.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.card import Card  # noqa: F401 — register FK target tables on Base
from app.models.import_batch import ImportBatch  # noqa: F401
from app.models.transaction import Transaction
from app.services import reporting_service


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def add_tx(
    db,
    *,
    transaction_date: date,
    amount_cents: int,
    transaction_type: str = "debit",
    classification: str | None = "personal",
    personal_category: str | None = None,
    expensed: bool = False,
    description: str = "Row",
):
    tx = Transaction(
        transaction_date=transaction_date,
        description=description,
        amount_cents=amount_cents,
        transaction_type=transaction_type,
        classification=classification,
        personal_category=personal_category,
        expensed=expensed,
        statement_format="test",
        source_hash=f"{transaction_date.isoformat()}-{description}-{transaction_type}-{amount_cents}",
        imported_at=datetime.now(timezone.utc),
    )
    db.add(tx)
    db.commit()
    return tx


class TestActivityWindow:
    def test_empty_db_returns_empty_window(self, db):
        assert reporting_service.activity_window(db, 12) == []

    def test_sparse_months_take_most_recent_activity(self, db):
        # The P0.1 repro fixture: one old personal purchase, then work-only months.
        add_tx(db, transaction_date=date(2025, 1, 10), amount_cents=5000, personal_category="Groceries")
        add_tx(db, transaction_date=date(2026, 4, 5), amount_cents=30000, classification="work")
        add_tx(db, transaction_date=date(2026, 5, 5), amount_cents=20000, classification="work")
        add_tx(db, transaction_date=date(2026, 6, 5), amount_cents=4000, classification="work")
        assert reporting_service.activity_window(db, 3) == ["2026-04", "2026-05", "2026-06"]

    def test_fewer_months_than_requested_returns_all(self, db):
        add_tx(db, transaction_date=date(2026, 5, 1), amount_cents=1000)
        add_tx(db, transaction_date=date(2026, 6, 1), amount_cents=1000)
        assert reporting_service.activity_window(db, 12) == ["2026-05", "2026-06"]

    def test_income_months_count_as_activity(self, db):
        add_tx(db, transaction_date=date(2026, 3, 1), amount_cents=100000,
               transaction_type="credit", personal_category="Income")
        assert reporting_service.activity_window(db, 6) == ["2026-03"]

    def test_unsorted_and_transfer_rows_do_not_open_months(self, db):
        add_tx(db, transaction_date=date(2026, 1, 1), amount_cents=1000, classification=None)
        add_tx(db, transaction_date=date(2026, 2, 1), amount_cents=1000, personal_category="Transfer")
        assert reporting_service.activity_window(db, 6) == []


class TestAggregates:
    def test_monthly_personal_spend_signs_categorized_credits_negative(self, db):
        # A categorized credit is a refund and offsets the month's spend.
        # (An *uncategorized* credit is excluded — it's pending income triage.)
        add_tx(db, transaction_date=date(2026, 6, 1), amount_cents=5000, personal_category="Shopping")
        add_tx(db, transaction_date=date(2026, 6, 2), amount_cents=2000,
               transaction_type="credit", personal_category="Shopping", description="Refund")
        assert reporting_service.monthly_personal_spend(db, ["2026-06"]) == {"2026-06": 3000}

    def test_empty_window_short_circuits(self, db):
        add_tx(db, transaction_date=date(2026, 6, 1), amount_cents=5000)
        assert reporting_service.monthly_personal_spend(db, []) == {}
        assert reporting_service.monthly_work_spend(db, []) == {}
        assert reporting_service.monthly_income(db, []) == []
        assert reporting_service.category_breakdown(db, []) == []
        assert reporting_service.top_merchants(db, []) == []

    def test_category_breakdown_labels_null_as_uncategorized(self, db):
        add_tx(db, transaction_date=date(2026, 6, 1), amount_cents=5000)
        add_tx(db, transaction_date=date(2026, 6, 2), amount_cents=1500, personal_category="Dining")
        assert reporting_service.category_breakdown(db, ["2026-06"]) == [
            ("2026-06", "Dining", 1500),
            ("2026-06", "Uncategorized", 5000),
        ]

    def test_monthly_income_defaults_to_income_and_reimbursement(self, db):
        add_tx(db, transaction_date=date(2026, 6, 1), amount_cents=100000,
               transaction_type="credit", personal_category="Income")
        add_tx(db, transaction_date=date(2026, 6, 2), amount_cents=2500,
               transaction_type="credit", personal_category="Reimbursement", description="Repay")
        assert reporting_service.monthly_income(db, ["2026-06"]) == [
            ("2026-06", "Income", 100000),
            ("2026-06", "Reimbursement", 2500),
        ]
        assert reporting_service.monthly_income(db, ["2026-06"], categories={"Income"}) == [
            ("2026-06", "Income", 100000),
        ]

    def test_top_merchants_groups_store_numbers(self, db):
        add_tx(db, transaction_date=date(2026, 6, 1), amount_cents=500, description="STARBUCKS #1234")
        add_tx(db, transaction_date=date(2026, 6, 2), amount_cents=700, description="STARBUCKS #5678")
        add_tx(db, transaction_date=date(2026, 6, 3), amount_cents=300, description="LIBRARY CAFE")
        assert reporting_service.top_merchants(db, ["2026-06"]) == [
            ("STARBUCKS", 1200, 2),
            ("LIBRARY CAFE", 300, 1),
        ]

    def test_unexpensed_work_and_uncategorized_income(self, db):
        add_tx(db, transaction_date=date(2026, 6, 1), amount_cents=4000,
               classification="work", description="Hotel")
        add_tx(db, transaction_date=date(2026, 6, 2), amount_cents=6000,
               classification="work", expensed=True, description="Flight")
        add_tx(db, transaction_date=date(2026, 6, 3), amount_cents=9000,
               transaction_type="credit", description="Mystery deposit")
        assert reporting_service.unexpensed_work(db) == (4000, 1)
        assert reporting_service.uncategorized_income(db) == (9000, 1)

    def test_normalize_merchant_strips_refs_and_dates(self):
        assert reporting_service.normalize_merchant("Starbucks #1234") == "STARBUCKS"
        assert reporting_service.normalize_merchant("AMAZON 1234567") == "AMAZON"
        assert reporting_service.normalize_merchant("PAYPAL XXXX4321") == "PAYPAL"
        assert reporting_service.normalize_merchant("NETFLIX 05/12") == "NETFLIX"
        assert reporting_service.normalize_merchant(None) == ""
