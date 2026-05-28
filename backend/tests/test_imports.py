"""Tests for the /api/v1/imports endpoint (Phase 2: undo import)."""

import csv
import io
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings as app_settings
from app.dependencies import get_db
from app.main import app
from app.migrations import run_migrations
from app.models.import_batch import ImportBatch
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
    db_path = tmp_path / "test_imports.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setattr(app_settings, "database_url", db_url)
    run_migrations()
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    db.add(User(username="user1", display_name="User 1", hashed_password=hash_password("password")))
    db.commit()
    try:
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
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


@pytest.fixture()
def authed_client(client):
    resp = client.post("/api/v1/auth/login", data={"username": "user1", "password": "password"})
    assert resp.status_code == 200
    return client


def statement_file(rows: list[list[str]]) -> dict:
    body = io.StringIO()
    writer = csv.writer(body)
    for row in rows:
        writer.writerow(row)
    return {"file": ("statement.csv", body.getvalue().encode(), "text/csv")}


def import_card_statement(client: TestClient, rows: list[list[str]]) -> dict:
    resp = client.post("/api/v1/transactions/import/confirm", files=statement_file(rows))
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuth:
    def test_list_requires_auth(self, client):
        assert client.get("/api/v1/imports").status_code == 401

    def test_delete_requires_auth(self, client):
        assert client.delete("/api/v1/imports/some-id").status_code == 401


# ---------------------------------------------------------------------------
# Confirm creates a batch
# ---------------------------------------------------------------------------


class TestImportCreatesBatch:
    def test_confirm_returns_batch_id(self, authed_client):
        body = import_card_statement(authed_client, [
            ["2026-05-01", "Coffee", "4.25", ""],
            ["2026-05-02", "Lunch", "12.00", ""],
        ])
        assert body["imported"] == 2
        assert body["batch_id"] is not None

    def test_confirm_returns_null_batch_when_nothing_imported(self, authed_client):
        # First import creates one batch with one row.
        first = import_card_statement(authed_client, [["2026-05-01", "Coffee", "4.25", ""]])
        assert first["batch_id"] is not None
        # Second import is all duplicates -> no batch should be created.
        second = import_card_statement(authed_client, [["2026-05-01", "Coffee", "4.25", ""]])
        assert second["imported"] == 0
        assert second["batch_id"] is None

    def test_only_one_batch_exists_per_import(self, authed_client, db_session):
        import_card_statement(authed_client, [
            ["2026-05-01", "Coffee", "4.25", ""],
            ["2026-05-02", "Lunch", "12.00", ""],
        ])
        batches = db_session.query(ImportBatch).all()
        assert len(batches) == 1
        assert batches[0].row_count == 2
        assert batches[0].filename == "statement.csv"
        assert batches[0].statement_format

    def test_imported_rows_are_stamped_with_batch_id(self, authed_client, db_session):
        body = import_card_statement(authed_client, [
            ["2026-05-01", "Coffee", "4.25", ""],
        ])
        rows = db_session.query(Transaction).all()
        assert len(rows) == 1
        assert rows[0].import_batch_id == body["batch_id"]


# ---------------------------------------------------------------------------
# GET /api/v1/imports
# ---------------------------------------------------------------------------


class TestListImports:
    def test_empty_when_no_imports(self, authed_client):
        resp = authed_client.get("/api/v1/imports")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_imports_newest_first(self, authed_client, db_session):
        # Manually insert two batches with distinct timestamps.
        older = ImportBatch(
            id="batch-old",
            filename="old.csv",
            statement_format="Test",
            imported_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
            row_count=1,
            created_by_action="import",
        )
        newer = ImportBatch(
            id="batch-new",
            filename="new.csv",
            statement_format="Test",
            imported_at=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
            row_count=2,
            created_by_action="import",
        )
        db_session.add_all([older, newer])
        db_session.commit()

        data = authed_client.get("/api/v1/imports").json()
        assert [b["id"] for b in data] == ["batch-new", "batch-old"]

    def test_includes_row_count(self, authed_client):
        import_card_statement(authed_client, [
            ["2026-05-01", "Coffee", "4.25", ""],
            ["2026-05-02", "Lunch", "12.00", ""],
            ["2026-05-03", "Books", "20.00", ""],
        ])
        data = authed_client.get("/api/v1/imports").json()
        assert len(data) == 1
        assert data[0]["row_count"] == 3


# ---------------------------------------------------------------------------
# DELETE /api/v1/imports/{batch_id}
# ---------------------------------------------------------------------------


class TestDeleteImportBatch:
    def test_404_when_batch_missing(self, authed_client):
        resp = authed_client.delete("/api/v1/imports/no-such-batch")
        assert resp.status_code == 404

    def test_deletes_all_rows_and_batch(self, authed_client, db_session):
        body = import_card_statement(authed_client, [
            ["2026-05-01", "Coffee", "4.25", ""],
            ["2026-05-02", "Lunch", "12.00", ""],
        ])
        assert db_session.query(Transaction).count() == 2

        resp = authed_client.delete(f"/api/v1/imports/{body['batch_id']}")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["removed_rows"] == 2
        assert payload["classified_rows"] == 0
        assert payload["categorized_rows"] == 0

        assert db_session.query(Transaction).count() == 0
        assert db_session.query(ImportBatch).count() == 0

    def test_reports_classified_and_categorized_counts(self, authed_client, db_session):
        body = import_card_statement(authed_client, [
            ["2026-05-01", "Coffee", "4.25", ""],
            ["2026-05-02", "Lunch", "12.00", ""],
            ["2026-05-03", "Books", "20.00", ""],
        ])
        # Classify two rows; categorize one.
        rows = db_session.query(Transaction).order_by(Transaction.transaction_date).all()
        rows[0].classification = "personal"
        rows[0].personal_category = "Dining"
        rows[1].classification = "work"
        db_session.commit()

        resp = authed_client.delete(f"/api/v1/imports/{body['batch_id']}")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["removed_rows"] == 3
        assert payload["classified_rows"] == 2
        assert payload["categorized_rows"] == 1
        assert db_session.query(Transaction).count() == 0

    def test_deletes_only_matching_batch(self, authed_client, db_session):
        first = import_card_statement(authed_client, [["2026-05-01", "Coffee", "4.25", ""]])
        second = import_card_statement(authed_client, [["2026-06-01", "Lunch", "12.00", ""]])

        resp = authed_client.delete(f"/api/v1/imports/{first['batch_id']}")
        assert resp.status_code == 200
        assert resp.json()["removed_rows"] == 1

        remaining = db_session.query(Transaction).all()
        assert len(remaining) == 1
        assert remaining[0].description == "Lunch"
        assert db_session.query(ImportBatch).count() == 1

    def test_does_not_touch_manual_rows(self, authed_client, db_session):
        body = import_card_statement(authed_client, [["2026-05-01", "Coffee", "4.25", ""]])
        # Create a manual row that has no batch_id.
        manual = Transaction(
            transaction_date=date(2026, 5, 5),
            description="Manual entry",
            amount_cents=1000,
            transaction_type="debit",
            classification=None,
            personal_category=None,
            expensed=False,
            is_manual=True,
            statement_format=None,
            source_hash="manual:abc123",
            imported_at=datetime.now(timezone.utc),
        )
        db_session.add(manual)
        db_session.commit()

        resp = authed_client.delete(f"/api/v1/imports/{body['batch_id']}")
        assert resp.status_code == 200

        rows = db_session.query(Transaction).all()
        assert len(rows) == 1
        assert rows[0].is_manual is True
        assert rows[0].description == "Manual entry"
