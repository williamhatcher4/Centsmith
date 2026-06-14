"""Tests for Phase 1: manual transaction create and delete endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings as app_settings
from app.dependencies import get_db
from app.main import app
from app.migrations import run_migrations
from app.models.user import User
from app.services.auth_service import hash_password


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test_phase1.db"
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


_BASE_PAYLOAD = {
    "transaction_date": "2026-05-01",
    "description": "Test coffee",
    "amount_cents": 450,
    "transaction_type": "debit",
}


# ---------------------------------------------------------------------------
# POST /api/v1/transactions/manual
# ---------------------------------------------------------------------------


class TestCreateManualTransaction:
    def test_requires_auth(self, client):
        resp = client.post("/api/v1/transactions/manual", json=_BASE_PAYLOAD)
        assert resp.status_code == 401

    def test_creates_transaction(self, authed_client):
        resp = authed_client.post("/api/v1/transactions/manual", json=_BASE_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert data["description"] == "Test coffee"
        assert data["amount_cents"] == 450
        assert data["is_manual"] is True
        assert data["statement_format"] is None

    def test_source_hash_starts_with_manual(self, authed_client, db_session):
        from app.models.transaction import Transaction

        authed_client.post("/api/v1/transactions/manual", json=_BASE_PAYLOAD)
        tx = db_session.query(Transaction).filter(Transaction.is_manual.is_(True)).first()
        assert tx is not None
        assert tx.source_hash.startswith("manual:")

    def test_two_manual_rows_get_unique_hashes(self, authed_client, db_session):
        from app.models.transaction import Transaction

        authed_client.post("/api/v1/transactions/manual", json=_BASE_PAYLOAD)
        authed_client.post("/api/v1/transactions/manual", json=_BASE_PAYLOAD)
        rows = db_session.query(Transaction).filter(Transaction.is_manual.is_(True)).all()
        assert len(rows) == 2
        assert rows[0].source_hash != rows[1].source_hash

    def test_missing_required_field_rejected(self, authed_client):
        payload = {k: v for k, v in _BASE_PAYLOAD.items() if k != "description"}
        resp = authed_client.post("/api/v1/transactions/manual", json=payload)
        assert resp.status_code == 422

    def test_income_category_on_debit_rejected(self, authed_client):
        payload = {**_BASE_PAYLOAD, "classification": "personal", "personal_category": "Income"}
        resp = authed_client.post("/api/v1/transactions/manual", json=payload)
        assert resp.status_code == 400

    def test_income_category_on_credit_accepted(self, authed_client):
        payload = {**_BASE_PAYLOAD, "transaction_type": "credit", "classification": "personal", "personal_category": "Income"}
        resp = authed_client.post("/api/v1/transactions/manual", json=payload)
        assert resp.status_code == 201

    def test_expensed_without_work_classification_rejected(self, authed_client):
        payload = {**_BASE_PAYLOAD, "expensed": True, "classification": "personal"}
        resp = authed_client.post("/api/v1/transactions/manual", json=payload)
        assert resp.status_code == 400

    def test_personal_category_without_personal_classification_rejected(self, authed_client):
        payload = {**_BASE_PAYLOAD, "personal_category": "Dining", "classification": "work"}
        resp = authed_client.post("/api/v1/transactions/manual", json=payload)
        assert resp.status_code == 400

    def test_optional_fields_default(self, authed_client):
        resp = authed_client.post("/api/v1/transactions/manual", json=_BASE_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert data["classification"] is None
        assert data["personal_category"] is None
        assert data["expensed"] is False

    def test_with_classification_and_category(self, authed_client):
        payload = {**_BASE_PAYLOAD, "classification": "personal", "personal_category": "Dining"}
        resp = authed_client.post("/api/v1/transactions/manual", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["classification"] == "personal"
        assert data["personal_category"] == "Dining"


# ---------------------------------------------------------------------------
# DELETE /api/v1/transactions/{tx_id}
# ---------------------------------------------------------------------------


class TestDeleteTransaction:
    def _create(self, authed_client):
        resp = authed_client.post("/api/v1/transactions/manual", json=_BASE_PAYLOAD)
        assert resp.status_code == 201
        return resp.json()

    def test_requires_auth(self, client):
        resp = client.delete("/api/v1/transactions/1")
        assert resp.status_code == 401

    def test_returns_deleted_payload(self, authed_client):
        tx = self._create(authed_client)
        resp = authed_client.delete(f"/api/v1/transactions/{tx['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tx["id"]
        assert data["description"] == "Test coffee"

    def test_row_is_gone_after_delete(self, authed_client, db_session):
        from app.models.transaction import Transaction

        tx = self._create(authed_client)
        authed_client.delete(f"/api/v1/transactions/{tx['id']}")
        row = db_session.query(Transaction).filter(Transaction.id == tx["id"]).first()
        assert row is None

    def test_delete_nonexistent_returns_404(self, authed_client):
        resp = authed_client.delete("/api/v1/transactions/999999")
        assert resp.status_code == 404

    def test_delete_imported_transaction_also_works(self, authed_client, db_session):
        from datetime import date
        from app.models.transaction import Transaction

        imported = Transaction(
            transaction_date=date(2026, 1, 1),
            description="Imported row",
            amount_cents=1000,
            transaction_type="debit",
            is_manual=False,
            source_hash="sha256abcdef1234567890",
        )
        db_session.add(imported)
        db_session.commit()
        db_session.refresh(imported)

        resp = authed_client.delete(f"/api/v1/transactions/{imported.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == imported.id

    def test_delete_imported_transaction_decrements_batch_row_count(self, authed_client, db_session):
        from datetime import date, datetime, timezone
        from app.models.import_batch import ImportBatch
        from app.models.transaction import Transaction

        batch = ImportBatch(
            id="batch-two-rows",
            filename="statement.csv",
            statement_format="Account Activity CSV",
            imported_at=datetime.now(timezone.utc),
            row_count=2,
            created_by_action="import",
        )
        first = Transaction(
            transaction_date=date(2026, 1, 1),
            description="Imported one",
            amount_cents=1000,
            transaction_type="debit",
            is_manual=False,
            source_hash="hash-imported-one",
            import_batch_id=batch.id,
        )
        second = Transaction(
            transaction_date=date(2026, 1, 2),
            description="Imported two",
            amount_cents=2000,
            transaction_type="debit",
            is_manual=False,
            source_hash="hash-imported-two",
            import_batch_id=batch.id,
        )
        db_session.add_all([batch, first, second])
        db_session.commit()
        db_session.refresh(first)

        resp = authed_client.delete(f"/api/v1/transactions/{first.id}")

        assert resp.status_code == 200
        refreshed = db_session.get(ImportBatch, batch.id)
        assert refreshed is not None
        assert refreshed.row_count == 1

    def test_delete_last_imported_transaction_removes_batch(self, authed_client, db_session):
        from datetime import date, datetime, timezone
        from app.models.import_batch import ImportBatch
        from app.models.transaction import Transaction

        batch = ImportBatch(
            id="batch-one-row",
            filename="statement.csv",
            statement_format="Account Activity CSV",
            imported_at=datetime.now(timezone.utc),
            row_count=1,
            created_by_action="import",
        )
        imported = Transaction(
            transaction_date=date(2026, 1, 1),
            description="Only imported row",
            amount_cents=1000,
            transaction_type="debit",
            is_manual=False,
            source_hash="hash-only-imported",
            import_batch_id=batch.id,
        )
        db_session.add_all([batch, imported])
        db_session.commit()
        db_session.refresh(imported)

        resp = authed_client.delete(f"/api/v1/transactions/{imported.id}")

        assert resp.status_code == 200
        assert db_session.get(ImportBatch, batch.id) is None

    def test_delete_manual_transaction_leaves_import_batch_unchanged(self, authed_client, db_session):
        from datetime import date, datetime, timezone
        from app.models.import_batch import ImportBatch
        from app.models.transaction import Transaction

        batch = ImportBatch(
            id="batch-manual-untouched",
            filename="statement.csv",
            statement_format="Account Activity CSV",
            imported_at=datetime.now(timezone.utc),
            row_count=1,
            created_by_action="import",
        )
        imported = Transaction(
            transaction_date=date(2026, 1, 1),
            description="Imported row",
            amount_cents=1000,
            transaction_type="debit",
            is_manual=False,
            source_hash="hash-manual-test-imported",
            import_batch_id=batch.id,
        )
        manual = Transaction(
            transaction_date=date(2026, 1, 2),
            description="Manual row",
            amount_cents=2000,
            transaction_type="debit",
            is_manual=True,
            source_hash="manual:batch-untouched",
        )
        db_session.add_all([batch, imported, manual])
        db_session.commit()
        db_session.refresh(manual)

        resp = authed_client.delete(f"/api/v1/transactions/{manual.id}")

        assert resp.status_code == 200
        refreshed = db_session.get(ImportBatch, batch.id)
        assert refreshed is not None
        assert refreshed.row_count == 1


# ---------------------------------------------------------------------------
# Server-side amount/description validation (P0.2): the React form validates
# too, but the API is the real boundary — SQLite ignores String(255).
# ---------------------------------------------------------------------------


class TestAmountAndDescriptionValidation:
    def test_negative_amount_rejected(self, authed_client):
        resp = authed_client.post("/api/v1/transactions/manual", json={**_BASE_PAYLOAD, "amount_cents": -500})
        assert resp.status_code == 422

    def test_zero_amount_rejected(self, authed_client):
        resp = authed_client.post("/api/v1/transactions/manual", json={**_BASE_PAYLOAD, "amount_cents": 0})
        assert resp.status_code == 422

    def test_oversize_description_rejected(self, authed_client):
        resp = authed_client.post("/api/v1/transactions/manual", json={**_BASE_PAYLOAD, "description": "x" * 256})
        assert resp.status_code == 422

    def test_boundary_255_description_accepted(self, authed_client):
        resp = authed_client.post("/api/v1/transactions/manual", json={**_BASE_PAYLOAD, "description": "x" * 255})
        assert resp.status_code == 201
        assert resp.json()["description"] == "x" * 255

    def test_blank_description_rejected(self, authed_client):
        resp = authed_client.post("/api/v1/transactions/manual", json={**_BASE_PAYLOAD, "description": "   "})
        assert resp.status_code == 422

    def test_description_is_trimmed(self, authed_client):
        resp = authed_client.post("/api/v1/transactions/manual", json={**_BASE_PAYLOAD, "description": "  Test coffee  "})
        assert resp.status_code == 201
        assert resp.json()["description"] == "Test coffee"

    def _create(self, authed_client):
        resp = authed_client.post("/api/v1/transactions/manual", json=_BASE_PAYLOAD)
        assert resp.status_code == 201
        return resp.json()

    def test_update_oversize_description_rejected(self, authed_client):
        tx = self._create(authed_client)
        resp = authed_client.put(f"/api/v1/transactions/{tx['id']}", json={"description": "x" * 256})
        assert resp.status_code == 422

    def test_update_blank_description_rejected(self, authed_client):
        tx = self._create(authed_client)
        resp = authed_client.put(f"/api/v1/transactions/{tx['id']}", json={"description": "   "})
        assert resp.status_code == 422

    def test_update_boundary_255_description_accepted(self, authed_client):
        tx = self._create(authed_client)
        resp = authed_client.put(f"/api/v1/transactions/{tx['id']}", json={"description": "y" * 255})
        assert resp.status_code == 200
        assert resp.json()["description"] == "y" * 255


# ---------------------------------------------------------------------------
# P3.3: unknown personal categories are accepted and auto-added to settings
# (maintainer decision 2026-06-09) on every path that sets a category.
# ---------------------------------------------------------------------------


class TestAutoAddUnknownCategory:
    def _settings_categories(self, authed_client):
        resp = authed_client.get("/api/v1/settings")
        assert resp.status_code == 200
        return resp.json()["personal_categories"]

    def _create_personal(self, authed_client, **overrides):
        payload = {**_BASE_PAYLOAD, "classification": "personal", **overrides}
        resp = authed_client.post("/api/v1/transactions/manual", json=payload)
        assert resp.status_code == 201
        return resp.json()

    def test_manual_create_with_unknown_category_registers_it(self, authed_client):
        assert "Hobbies" not in self._settings_categories(authed_client)
        tx = self._create_personal(authed_client, personal_category="Hobbies")
        assert tx["personal_category"] == "Hobbies"
        assert "Hobbies" in self._settings_categories(authed_client)

    def test_update_with_unknown_category_registers_it(self, authed_client):
        tx = self._create_personal(authed_client)
        resp = authed_client.put(f"/api/v1/transactions/{tx['id']}", json={"personal_category": "Woodworking"})
        assert resp.status_code == 200
        assert resp.json()["personal_category"] == "Woodworking"
        assert "Woodworking" in self._settings_categories(authed_client)

    def test_bulk_categorize_with_unknown_category_registers_it(self, authed_client):
        tx = self._create_personal(authed_client)
        resp = authed_client.post(
            "/api/v1/transactions/bulk-categorize-personal",
            json={"transaction_ids": [tx["id"]], "personal_category": "Garden"},
        )
        assert resp.status_code == 200
        assert "Garden" in self._settings_categories(authed_client)

    def test_case_insensitive_duplicate_is_not_double_added(self, authed_client):
        before = self._settings_categories(authed_client)
        assert "Groceries" in before
        self._create_personal(authed_client, personal_category="groceries")
        after = self._settings_categories(authed_client)
        assert after == before
        assert sum(1 for c in after if c.lower() == "groceries") == 1

    def test_system_category_on_credit_is_not_duplicated(self, authed_client):
        before = self._settings_categories(authed_client)
        self._create_personal(authed_client, transaction_type="credit", personal_category="Income")
        after = self._settings_categories(authed_client)
        assert after == before
        assert after.count("Income") == 1


# ---------------------------------------------------------------------------
# PUT /api/v1/transactions/{id} — amount/type editing for manual rows (P4.3)
# ---------------------------------------------------------------------------


class TestManualAmountTypeEditing:
    def _create_manual(self, authed_client, **overrides):
        payload = {**_BASE_PAYLOAD, **overrides}
        resp = authed_client.post("/api/v1/transactions/manual", json=payload)
        assert resp.status_code == 201
        return resp.json()

    def _create_imported(self, db_session):
        from datetime import date
        from app.models.transaction import Transaction

        imported = Transaction(
            transaction_date=date(2026, 1, 1),
            description="Imported immutable row",
            amount_cents=1000,
            transaction_type="debit",
            is_manual=False,
            source_hash="sha256-immutable-row",
        )
        db_session.add(imported)
        db_session.commit()
        db_session.refresh(imported)
        return imported

    def test_manual_amount_editable(self, authed_client):
        tx = self._create_manual(authed_client)
        resp = authed_client.put(f"/api/v1/transactions/{tx['id']}", json={"amount_cents": 999})
        assert resp.status_code == 200
        assert resp.json()["amount_cents"] == 999

    def test_manual_type_editable(self, authed_client):
        tx = self._create_manual(authed_client)
        resp = authed_client.put(f"/api/v1/transactions/{tx['id']}", json={"transaction_type": "credit"})
        assert resp.status_code == 200
        assert resp.json()["transaction_type"] == "credit"

    def test_manual_amount_and_type_together(self, authed_client):
        tx = self._create_manual(authed_client)
        resp = authed_client.put(
            f"/api/v1/transactions/{tx['id']}",
            json={"amount_cents": 12345, "transaction_type": "credit"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["amount_cents"] == 12345
        assert data["transaction_type"] == "credit"

    def test_imported_row_amount_rejected(self, authed_client, db_session):
        imported = self._create_imported(db_session)
        resp = authed_client.put(f"/api/v1/transactions/{imported.id}", json={"amount_cents": 999})
        assert resp.status_code == 400
        assert "manually added" in resp.json()["detail"]
        db_session.refresh(imported)
        assert imported.amount_cents == 1000

    def test_imported_row_type_rejected(self, authed_client, db_session):
        imported = self._create_imported(db_session)
        resp = authed_client.put(f"/api/v1/transactions/{imported.id}", json={"transaction_type": "credit"})
        assert resp.status_code == 400
        db_session.refresh(imported)
        assert imported.transaction_type == "debit"

    def test_imported_row_other_fields_still_editable(self, authed_client, db_session):
        imported = self._create_imported(db_session)
        resp = authed_client.put(f"/api/v1/transactions/{imported.id}", json={"classification": "personal"})
        assert resp.status_code == 200
        assert resp.json()["classification"] == "personal"

    def test_type_flip_with_income_category_rejected(self, authed_client):
        tx = self._create_manual(
            authed_client,
            transaction_type="credit",
            classification="personal",
            personal_category="Income",
        )
        resp = authed_client.put(f"/api/v1/transactions/{tx['id']}", json={"transaction_type": "debit"})
        assert resp.status_code == 400
        assert "credit" in resp.json()["detail"]

    def test_type_flip_with_plain_category_allowed(self, authed_client):
        tx = self._create_manual(
            authed_client,
            classification="personal",
            personal_category="Groceries",
        )
        resp = authed_client.put(f"/api/v1/transactions/{tx['id']}", json={"transaction_type": "credit"})
        assert resp.status_code == 200
        assert resp.json()["transaction_type"] == "credit"

    def test_category_set_validates_against_new_type(self, authed_client):
        # Flipping to debit while assigning Income in the same PUT must 400.
        tx = self._create_manual(authed_client, transaction_type="credit", classification="personal")
        resp = authed_client.put(
            f"/api/v1/transactions/{tx['id']}",
            json={"transaction_type": "debit", "personal_category": "Income"},
        )
        assert resp.status_code == 400

    def test_income_category_accepted_when_flipping_to_credit(self, authed_client):
        tx = self._create_manual(authed_client, classification="personal")
        resp = authed_client.put(
            f"/api/v1/transactions/{tx['id']}",
            json={"transaction_type": "credit", "personal_category": "Income"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["transaction_type"] == "credit"
        assert data["personal_category"] == "Income"

    def test_update_negative_amount_rejected(self, authed_client):
        tx = self._create_manual(authed_client)
        resp = authed_client.put(f"/api/v1/transactions/{tx['id']}", json={"amount_cents": -500})
        assert resp.status_code == 422

    def test_update_zero_amount_rejected(self, authed_client):
        tx = self._create_manual(authed_client)
        resp = authed_client.put(f"/api/v1/transactions/{tx['id']}", json={"amount_cents": 0})
        assert resp.status_code == 422
