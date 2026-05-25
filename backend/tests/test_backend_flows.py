import csv
import io
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.dependencies import get_db
from app.main import app
from app.migrations import run_migrations
from app.models.transaction import Transaction
from app.models.user import User
from app.services.auth_service import clear_all_login_failures, hash_password
from app.services.desktop_auth_service import reset_desktop_token_for_tests


@pytest.fixture(autouse=True)
def reset_auth_state():
    clear_all_login_failures()
    reset_desktop_token_for_tests()
    yield
    clear_all_login_failures()
    reset_desktop_token_for_tests()


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setattr(settings, "database_url", db_url)

    run_migrations()

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        db.add(User(username="user1", display_name="User 1", hashed_password=hash_password("password")))
        db.commit()
        yield db
    finally:
        db.close()
        engine.dispose()


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


def test_bad_login_returns_401_and_lockout_returns_429(client, monkeypatch):
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 2)
    monkeypatch.setattr(settings, "login_rate_limit_window_seconds", 900)

    first = client.post("/api/v1/auth/login", data={"username": "user1", "password": "bad"})
    second = client.post("/api/v1/auth/login", data={"username": "user1", "password": "bad"})
    locked = client.post("/api/v1/auth/login", data={"username": "user1", "password": "bad"})

    assert first.status_code == 401
    assert second.status_code == 401
    assert locked.status_code == 429


def test_successful_login_clears_failed_attempts(client, monkeypatch):
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 2)
    monkeypatch.setattr(settings, "login_rate_limit_window_seconds", 900)

    assert client.post("/api/v1/auth/login", data={"username": "user1", "password": "bad"}).status_code == 401
    login(client)

    assert client.post("/api/v1/auth/login", data={"username": "user1", "password": "bad"}).status_code == 401


def test_desktop_login_token_sets_session(client, monkeypatch):
    monkeypatch.setattr(settings, "desktop_mode", True)
    monkeypatch.setattr(settings, "desktop_auth_token", "desktop-token")

    assert client.get("/api/v1/auth/me").status_code == 401
    response = client.post("/desktop-login", data={"token": "desktop-token"})

    assert response.status_code == 200
    assert client.get("/api/v1/auth/me").json()["username"] == "local"


def test_desktop_login_rejects_missing_invalid_and_reused_tokens(client, monkeypatch):
    monkeypatch.setattr(settings, "desktop_mode", True)
    monkeypatch.setattr(settings, "desktop_auth_token", "desktop-token")

    assert client.post("/desktop-login").status_code == 401
    assert client.post("/desktop-login", data={"token": "wrong"}).status_code == 401
    assert client.post("/desktop-login", data={"token": "desktop-token"}).status_code == 200
    assert client.post("/desktop-login", data={"token": "desktop-token"}).status_code == 401


def test_desktop_bootstrap_serves_html_only_in_desktop_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "desktop_mode", False)
    assert client.get("/desktop-bootstrap").status_code == 404

    monkeypatch.setattr(settings, "desktop_mode", True)
    response = client.get("/desktop-bootstrap")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Signing you in" in response.text


def test_transaction_lists_show_debits_default_and_credits_in_unsorted(client, db_session):
    debit = add_transaction(db_session, description="Coffee", amount_cents=425, transaction_type="debit")
    refund = add_transaction(db_session, description="Refund", amount_cents=425, transaction_type="credit")
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
    assert {row["id"] for row in response.json()} == {debit.id, refund.id}

    dashboard = client.get("/api/v1/transactions/dashboard").json()
    assert dashboard["unsorted_count"] == 2
    assert dashboard["work_total_cents"] == 3200


def test_import_preview_and_confirm_ignore_card_payment_credits(client, db_session):
    login(client)
    files = statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-02", "PAYMENT - THANK YOU", "", "100.00"],
    ])

    preview = client.post("/api/v1/transactions/import/preview", files=files)
    assert preview.status_code == 200
    assert preview.json()["total"] == 2
    assert preview.json()["ignored_credits"] == 1
    assert preview.json()["to_import"] == 1
    assert [row["transaction_type"] for row in preview.json()["rows"]] == ["debit"]

    confirm = client.post("/api/v1/transactions/import/confirm", files=statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-02", "PAYMENT - THANK YOU", "", "100.00"],
    ]))
    assert confirm.status_code == 200
    assert confirm.json() == {"imported": 1, "skipped": 0, "ignored_credits": 1, "skipped_errors": 0}

    stored = db_session.query(Transaction).all()
    assert len(stored) == 1
    assert stored[0].transaction_type == "debit"


def test_import_rejects_oversized_upload_while_reading(client):
    login(client)
    too_large = b"x" * (10 * 1024 * 1024 + 1)

    response = client.post(
        "/api/v1/transactions/import/preview",
        files={"file": ("huge.csv", too_large, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File too large (max 10 MB)"


def test_duplicate_import_reports_skipped_debits_separately_from_payments(client):
    login(client)
    files = statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-02", "PAYMENT RECEIVED - THANK YOU", "", "100.00"],
    ])
    assert client.post("/api/v1/transactions/import/confirm", files=files).status_code == 200

    duplicate = client.post("/api/v1/transactions/import/confirm", files=statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-02", "PAYMENT RECEIVED - THANK YOU", "", "100.00"],
    ]))

    assert duplicate.status_code == 200
    assert duplicate.json() == {"imported": 0, "skipped": 1, "ignored_credits": 1, "skipped_errors": 0}


def test_import_keeps_refund_credits_but_drops_payment_credits(client, db_session):
    login(client)
    files = statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-02", "PAYMENT - THANK YOU", "", "100.00"],
        ["2026-05-03", "REFUND - STARBUCKS", "", "4.25"],
    ])

    confirm = client.post("/api/v1/transactions/import/confirm", files=files)
    assert confirm.status_code == 200
    assert confirm.json() == {"imported": 2, "skipped": 0, "ignored_credits": 1, "skipped_errors": 0}

    stored = db_session.query(Transaction).order_by(Transaction.transaction_date).all()
    assert [(tx.description, tx.transaction_type) for tx in stored] == [
        ("Coffee", "debit"),
        ("REFUND - STARBUCKS", "credit"),
    ]


def test_payment_match_is_case_insensitive(client, db_session):
    login(client)
    files = statement_file([
        ["2026-05-01", "  payment - thank you  ", "", "100.00"],
    ])
    confirm = client.post("/api/v1/transactions/import/confirm", files=files)
    assert confirm.json()["ignored_credits"] == 1
    assert db_session.query(Transaction).count() == 0


def test_payment_match_does_not_catch_substring(client, db_session):
    login(client)
    files = statement_file([
        ["2026-05-01", "PAYMENT TO VENDOR - THANK YOU", "", "100.00"],
    ])
    confirm = client.post("/api/v1/transactions/import/confirm", files=files)
    assert confirm.json() == {"imported": 1, "skipped": 0, "ignored_credits": 0, "skipped_errors": 0}
    stored = db_session.query(Transaction).one()
    assert stored.transaction_type == "credit"


def test_inbox_query_includes_unclassified_credits(client, db_session):
    debit = add_transaction(db_session, description="Coffee", amount_cents=425, transaction_type="debit")
    refund = add_transaction(db_session, description="REFUND - AMAZON", amount_cents=1200, transaction_type="credit")

    login(client)

    response = client.get("/api/v1/transactions", params={"classification": "unsorted"})
    assert response.status_code == 200
    assert {row["id"] for row in response.json()} == {debit.id, refund.id}


def test_credit_can_be_assigned_spending_category(client, db_session):
    refund = add_transaction(
        db_session,
        description="REFUND - GROCERIES",
        amount_cents=1500,
        transaction_type="credit",
        classification="personal",
    )

    login(client)

    response = client.put(f"/api/v1/transactions/{refund.id}", json={"personal_category": "Groceries"})
    assert response.status_code == 200
    assert response.json()["personal_category"] == "Groceries"


def test_personal_refund_offsets_spending(client, db_session):
    add_transaction(
        db_session,
        description="Dinner",
        amount_cents=5000,
        transaction_type="debit",
        classification="personal",
        personal_category="Dining",
        transaction_date=date(2026, 5, 1),
    )
    add_transaction(
        db_session,
        description="Refund",
        amount_cents=1000,
        transaction_type="credit",
        classification="personal",
        personal_category="Dining",
        transaction_date=date(2026, 5, 5),
    )

    login(client)

    response = client.get("/api/v1/transactions/spending/personal", params={"months": 12})
    assert response.status_code == 200
    body = response.json()
    assert body["total_cents"] == 4000
    dining = next(row for row in body["by_category"] if row["category_name"] == "Dining")
    assert dining["amount_cents"] == 4000


def test_dashboard_personal_cents_offsets_refunds(client, db_session):
    add_transaction(
        db_session,
        description="Dinner",
        amount_cents=5000,
        transaction_type="debit",
        classification="personal",
        personal_category="Dining",
        transaction_date=date(2026, 5, 1),
    )
    add_transaction(
        db_session,
        description="Refund",
        amount_cents=1000,
        transaction_type="credit",
        classification="personal",
        personal_category="Dining",
        transaction_date=date(2026, 5, 5),
    )

    login(client)

    dashboard = client.get("/api/v1/transactions/dashboard").json()
    assert dashboard["personal_total_cents"] == 4000


def test_personal_list_includes_categorized_refund_credits(client, db_session):
    debit = add_transaction(
        db_session,
        description="Dinner",
        amount_cents=5000,
        transaction_type="debit",
        classification="personal",
        personal_category="Dining",
    )
    refund = add_transaction(
        db_session,
        description="Refund",
        amount_cents=1000,
        transaction_type="credit",
        classification="personal",
        personal_category="Dining",
    )

    login(client)

    response = client.get("/api/v1/transactions", params={"classification": "personal"})
    assert response.status_code == 200
    assert {row["id"] for row in response.json()} == {debit.id, refund.id}


def test_income_credits_do_not_offset_personal_spending(client, db_session):
    add_transaction(
        db_session,
        description="Dinner",
        amount_cents=5000,
        transaction_type="debit",
        classification="personal",
        personal_category="Dining",
        transaction_date=date(2026, 5, 1),
    )
    add_transaction(
        db_session,
        description="Paycheck",
        amount_cents=200000,
        transaction_type="credit",
        classification="personal",
        personal_category="Income",
        transaction_date=date(2026, 5, 15),
    )

    login(client)

    body = client.get("/api/v1/transactions/spending/personal").json()
    assert body["total_cents"] == 5000


def test_legitimately_duplicate_rows_in_one_file_are_both_imported(client, db_session):
    login(client)
    files = statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-01", "Coffee", "4.25", ""],
    ])
    response = client.post("/api/v1/transactions/import/confirm", files=files)
    assert response.status_code == 200
    assert response.json() == {"imported": 2, "skipped": 0, "ignored_credits": 0, "skipped_errors": 0}

    stored = db_session.query(Transaction).filter(Transaction.description == "Coffee").all()
    assert len(stored) == 2
    assert stored[0].source_hash != stored[1].source_hash


def test_overlap_import_with_legitimate_duplicate_imports_only_new_occurrence(client, db_session):
    login(client)
    first = client.post("/api/v1/transactions/import/confirm", files=statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
    ]))
    assert first.json()["imported"] == 1

    second = client.post("/api/v1/transactions/import/confirm", files=statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-01", "Coffee", "4.25", ""],
    ]))
    assert second.status_code == 200
    assert second.json() == {"imported": 1, "skipped": 1, "ignored_credits": 0, "skipped_errors": 0}
    assert db_session.query(Transaction).filter(Transaction.description == "Coffee").count() == 2


def test_preview_marks_only_overlapping_occurrence_as_duplicate(client):
    login(client)
    client.post("/api/v1/transactions/import/confirm", files=statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
    ]))
    preview = client.post("/api/v1/transactions/import/preview", files=statement_file([
        ["2026-05-01", "Coffee", "4.25", ""],
        ["2026-05-01", "Coffee", "4.25", ""],
    ]))
    assert preview.status_code == 200
    body = preview.json()
    assert body["total"] == 2
    assert body["duplicates"] == 1
    assert body["to_import"] == 1
    assert [row["is_duplicate"] for row in body["rows"]] == [True, False]


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


def test_migrations_create_empty_sqlite_database(tmp_path, monkeypatch):
    db_path = tmp_path / "empty.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")

    run_migrations()

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    assert {"users", "transactions", "alembic_version"}.issubset(set(inspector.get_table_names()))
    transaction_columns = {column["name"] for column in inspector.get_columns("transactions")}
    assert {"expensed", "personal_category"}.issubset(transaction_columns)


def test_migrations_upgrade_existing_sqlite_database_missing_new_columns(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER NOT NULL,
                username VARCHAR(50) NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                created_at DATETIME,
                PRIMARY KEY (id),
                UNIQUE (username)
            )
        """))
        conn.execute(text("""
            CREATE TABLE transactions (
                id INTEGER NOT NULL,
                transaction_date DATE NOT NULL,
                description VARCHAR(255) NOT NULL,
                amount_cents INTEGER NOT NULL,
                transaction_type VARCHAR(10) NOT NULL,
                classification VARCHAR(20),
                statement_format VARCHAR(80),
                source_hash VARCHAR(64) NOT NULL,
                imported_at DATETIME,
                updated_at DATETIME,
                PRIMARY KEY (id),
                CONSTRAINT uq_transactions_source_hash UNIQUE (source_hash)
            )
        """))
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")

    run_migrations()

    inspector = inspect(engine)
    transaction_columns = {column["name"] for column in inspector.get_columns("transactions")}
    assert {"expensed", "personal_category"}.issubset(transaction_columns)
    assert "alembic_version" in inspector.get_table_names()
