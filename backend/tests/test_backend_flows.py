import csv
import io
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.dependencies import get_db
from app.main import app
from app.models.transaction import Transaction
from app.models.user import User
from app.services.auth_service import hash_password


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        db.add(User(username="user1", display_name="User 1", hashed_password=hash_password("password")))
        db.commit()
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient):
    response = client.post("/api/v1/auth/login", data={"username": "user1", "password": "password"})
    assert response.status_code == 200
    return response


def add_transaction(
    db,
    *,
    description: str,
    amount_cents: int,
    transaction_type: str,
    classification: str | None = None,
    personal_category: str | None = None,
    expensed: bool = False,
    transaction_date: date = date(2026, 5, 1),
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
    db.refresh(tx)
    return tx


def statement_file(rows: list[list[str]]) -> dict:
    body = io.StringIO()
    writer = csv.writer(body)
    for row in rows:
        writer.writerow(row)
    return {"file": ("statement.csv", body.getvalue().encode(), "text/csv")}


def test_auth_required_and_login_sets_session(client):
    assert client.get("/api/v1/transactions").status_code == 401

    login(client)

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["username"] == "user1"


def test_transaction_lists_and_dashboard_count_only_debits(client, db_session):
    debit = add_transaction(db_session, description="Coffee", amount_cents=425, transaction_type="debit")
    add_transaction(db_session, description="Refund", amount_cents=425, transaction_type="credit")
    add_transaction(
        db_session,
        description="Client lunch",
        amount_cents=3200,
        transaction_type="debit",
        classification="work",
    )

    login(client)

    response = client.get("/api/v1/transactions", params={"limit": 1000})
    assert response.status_code == 200
    rows = response.json()
    assert {row["id"] for row in rows} == {debit.id, debit.id + 2}
    assert all(row["transaction_type"] == "debit" for row in rows)

    response = client.get("/api/v1/transactions", params={"classification": "unsorted"})
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [debit.id]

    dashboard = client.get("/api/v1/transactions/dashboard").json()
    assert dashboard["unsorted_count"] == 1
    assert dashboard["work_total_cents"] == 3200


def test_import_preview_and_confirm_ignore_credits(client, db_session):
    login(client)
    files = statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-02", "Refund", "", "4.25"],
    ])

    preview = client.post("/api/v1/transactions/import/preview", files=files)
    assert preview.status_code == 200
    assert preview.json()["total"] == 2
    assert preview.json()["ignored_credits"] == 1
    assert preview.json()["to_import"] == 1
    assert [row["transaction_type"] for row in preview.json()["rows"]] == ["debit"]

    confirm = client.post("/api/v1/transactions/import/confirm", files=statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-02", "Refund", "", "4.25"],
    ]))
    assert confirm.status_code == 200
    assert confirm.json() == {"imported": 1, "skipped": 0, "ignored_credits": 1}

    stored = db_session.query(Transaction).all()
    assert len(stored) == 1
    assert stored[0].transaction_type == "debit"


def test_duplicate_import_reports_skipped_debits_separately_from_credits(client):
    login(client)
    files = statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-02", "Refund", "", "4.25"],
    ])
    assert client.post("/api/v1/transactions/import/confirm", files=files).status_code == 200

    duplicate = client.post("/api/v1/transactions/import/confirm", files=statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-02", "Refund", "", "4.25"],
    ]))

    assert duplicate.status_code == 200
    assert duplicate.json() == {"imported": 0, "skipped": 1, "ignored_credits": 1}


def test_exports_include_only_debit_rows(client, db_session):
    add_transaction(db_session, description="Dinner", amount_cents=5500, transaction_type="debit", classification="personal")
    add_transaction(db_session, description="Refund", amount_cents=5500, transaction_type="credit", classification="personal")
    add_transaction(db_session, description="Supplies", amount_cents=1299, transaction_type="debit", classification="work")

    login(client)

    response = client.get("/api/v1/transactions/export/personal")
    assert response.status_code == 200
    assert "Dinner" in response.text
    assert "Refund" not in response.text
    assert ",debit,-55.00" in response.text


def test_work_transactions_can_be_marked_and_filtered_by_expensed(client, db_session):
    pending = add_transaction(
        db_session,
        description="Pending work item",
        amount_cents=1000,
        transaction_type="debit",
        classification="work",
    )
    expensed = add_transaction(
        db_session,
        description="Expensed work item",
        amount_cents=2000,
        transaction_type="debit",
        classification="work",
        expensed=True,
    )
    add_transaction(
        db_session,
        description="Personal item",
        amount_cents=3000,
        transaction_type="debit",
        classification="personal",
    )

    login(client)

    work_rows = client.get("/api/v1/transactions", params={"classification": "work"}).json()
    assert [row["id"] for row in work_rows] == [pending.id, expensed.id]
    assert [row["expensed"] for row in work_rows] == [False, True]

    filtered = client.get("/api/v1/transactions", params={"classification": "work", "expensed": False}).json()
    assert [row["id"] for row in filtered] == [pending.id]

    response = client.put(f"/api/v1/transactions/{pending.id}", json={"expensed": True})
    assert response.status_code == 200
    assert response.json()["expensed"] is True

    refreshed = client.get("/api/v1/transactions", params={"classification": "work"}).json()
    refreshed_pending = next(row for row in refreshed if row["id"] == pending.id)
    assert refreshed_pending["expensed"] is True

    expensed_only = client.get("/api/v1/transactions", params={"classification": "work", "expensed": True}).json()
    assert {row["id"] for row in expensed_only} == {pending.id, expensed.id}


def test_only_work_transactions_can_be_marked_expensed(client, db_session):
    personal = add_transaction(
        db_session,
        description="Personal item",
        amount_cents=3000,
        transaction_type="debit",
        classification="personal",
    )

    login(client)

    response = client.put(f"/api/v1/transactions/{personal.id}", json={"expensed": True})
    assert response.status_code == 400
    assert response.json()["detail"] == "Only work transactions can be marked as expensed"


def test_work_export_includes_expensed_status(client, db_session):
    add_transaction(db_session, description="Pending", amount_cents=1000, transaction_type="debit", classification="work")
    add_transaction(db_session, description="Done", amount_cents=2000, transaction_type="debit", classification="work", expensed=True)

    login(client)

    response = client.get("/api/v1/transactions/export/work")
    assert response.status_code == 200
    assert "Date,Description,Classification,Type,Amount,Expensed" in response.text
    assert "Pending,work,debit,-10.00,no" in response.text
    assert "Done,work,debit,-20.00,yes" in response.text


def test_personal_transactions_can_be_categorized_and_listed(client, db_session):
    personal = add_transaction(
        db_session,
        description="Grocery run",
        amount_cents=4200,
        transaction_type="debit",
        classification="personal",
    )
    add_transaction(
        db_session,
        description="Client supplies",
        amount_cents=1500,
        transaction_type="debit",
        classification="work",
    )
    add_transaction(
        db_session,
        description="Dinner",
        amount_cents=2600,
        transaction_type="debit",
        classification="personal",
        personal_category="Dining",
    )

    login(client)

    uncategorized = client.get("/api/v1/transactions", params={"classification": "personal", "personal_category": "uncategorized"})
    assert uncategorized.status_code == 200
    assert [row["id"] for row in uncategorized.json()] == [personal.id]

    response = client.post(
        "/api/v1/transactions/bulk-categorize-personal",
        json={"transaction_ids": [personal.id], "personal_category": "Groceries"},
    )
    assert response.status_code == 200
    assert response.json() == {"updated": 1}

    refreshed = client.get("/api/v1/transactions", params={"classification": "personal"}).json()
    assert next(row for row in refreshed if row["id"] == personal.id)["personal_category"] == "Groceries"


def test_personal_category_can_be_saved_with_transaction_update(client, db_session):
    personal = add_transaction(
        db_session,
        description="Coffee",
        amount_cents=625,
        transaction_type="debit",
        classification="personal",
    )

    login(client)

    response = client.put(f"/api/v1/transactions/{personal.id}", json={"personal_category": "Dining"})
    assert response.status_code == 200
    assert response.json()["personal_category"] == "Dining"

    uncategorized = client.get("/api/v1/transactions", params={"classification": "personal", "personal_category": "uncategorized"})
    assert uncategorized.status_code == 200
    assert personal.id not in {row["id"] for row in uncategorized.json()}


def test_personal_spending_includes_category_breakdown(client, db_session):
    add_transaction(
        db_session,
        description="Groceries",
        amount_cents=4200,
        transaction_type="debit",
        classification="personal",
        personal_category="Groceries",
        transaction_date=date(2026, 5, 1),
    )
    add_transaction(
        db_session,
        description="Restaurant",
        amount_cents=1800,
        transaction_type="debit",
        classification="personal",
        personal_category="Dining",
        transaction_date=date(2026, 5, 2),
    )
    add_transaction(
        db_session,
        description="Mystery",
        amount_cents=1000,
        transaction_type="debit",
        classification="personal",
        transaction_date=date(2026, 5, 3),
    )
    add_transaction(
        db_session,
        description="Work",
        amount_cents=9999,
        transaction_type="debit",
        classification="work",
        transaction_date=date(2026, 5, 4),
    )

    login(client)

    response = client.get("/api/v1/transactions/spending/personal", params={"months": 12})
    assert response.status_code == 200
    body = response.json()
    assert body["total_cents"] == 7000
    assert [row["category_name"] for row in body["by_category"]] == ["Groceries", "Dining", "Uncategorized"]
    assert body["points"][0]["by_category"][0]["category_name"] == "Groceries"
