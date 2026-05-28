"""Tests for the /api/v1/settings endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings as app_settings
from app.dependencies import get_db
from app.main import app
from app.migrations import run_migrations
from app.models.user import User
from app.models.user_settings import DEFAULT_CATEGORIES, SYSTEM_CATEGORIES
from app.services.auth_service import hash_password
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test_settings.db"
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


# ---------------------------------------------------------------------------
# GET /api/v1/settings
# ---------------------------------------------------------------------------


class TestGetSettings:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 401

    def test_returns_default_categories_on_first_call(self, authed_client):
        resp = authed_client.get("/api/v1/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["personal_categories"] == list(DEFAULT_CATEGORIES)
        assert data["hidden_pages"] == []

    def test_idempotent_when_called_twice(self, authed_client):
        r1 = authed_client.get("/api/v1/settings")
        r2 = authed_client.get("/api/v1/settings")
        assert r1.json() == r2.json()

    def test_system_categories_present(self, authed_client):
        data = authed_client.get("/api/v1/settings").json()
        present = set(data["personal_categories"])
        for cat in SYSTEM_CATEGORIES:
            assert cat in present, f"System category '{cat}' missing from defaults"


# ---------------------------------------------------------------------------
# PUT /api/v1/settings
# ---------------------------------------------------------------------------


class TestUpdateSettings:
    def test_requires_auth(self, client):
        resp = client.put("/api/v1/settings", json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": []})
        assert resp.status_code == 401

    def test_add_custom_category(self, authed_client):
        new_cats = list(DEFAULT_CATEGORIES) + ["Coffee"]
        resp = authed_client.put("/api/v1/settings", json={"personal_categories": new_cats, "hidden_pages": []})
        assert resp.status_code == 200
        assert "Coffee" in resp.json()["personal_categories"]

    def test_persisted_after_get(self, authed_client):
        new_cats = list(DEFAULT_CATEGORIES) + ["Tea"]
        authed_client.put("/api/v1/settings", json={"personal_categories": new_cats, "hidden_pages": []})
        data = authed_client.get("/api/v1/settings").json()
        assert "Tea" in data["personal_categories"]

    def test_reorder_categories(self, authed_client):
        reordered = list(reversed(DEFAULT_CATEGORIES))
        resp = authed_client.put("/api/v1/settings", json={"personal_categories": reordered, "hidden_pages": []})
        assert resp.status_code == 200
        assert resp.json()["personal_categories"] == reordered

    def test_hide_a_page(self, authed_client):
        resp = authed_client.put(
            "/api/v1/settings",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": ["/spending"]},
        )
        assert resp.status_code == 200
        assert resp.json()["hidden_pages"] == ["/spending"]

    # ------------------------------------------------------------------
    # System-category protection
    # ------------------------------------------------------------------

    def test_cannot_remove_income_category(self, authed_client):
        cats_without_income = [c for c in DEFAULT_CATEGORIES if c != "Income"]
        resp = authed_client.put("/api/v1/settings", json={"personal_categories": cats_without_income, "hidden_pages": []})
        assert resp.status_code == 422
        detail = str(resp.json())
        assert "Income" in detail

    def test_cannot_remove_reimbursement_category(self, authed_client):
        cats = [c for c in DEFAULT_CATEGORIES if c != "Reimbursement"]
        resp = authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        assert resp.status_code == 422

    def test_cannot_remove_transfer_category(self, authed_client):
        cats = [c for c in DEFAULT_CATEGORIES if c != "Transfer"]
        resp = authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        assert resp.status_code == 422

    def test_empty_category_name_rejected(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + [""]
        resp = authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        assert resp.status_code == 422

    def test_whitespace_only_category_rejected(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["   "]
        resp = authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        assert resp.status_code == 422

    def test_category_over_80_chars_rejected(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["A" * 81]
        resp = authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        assert resp.status_code == 422

    def test_duplicate_category_rejected(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["Groceries"]
        resp = authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        assert resp.status_code == 422

    def test_duplicate_category_case_insensitive(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["groceries"]
        resp = authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        assert resp.status_code == 422

    # ------------------------------------------------------------------
    # Hidden pages validation
    # ------------------------------------------------------------------

    def test_unknown_page_slug_rejected(self, authed_client):
        resp = authed_client.put(
            "/api/v1/settings",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": ["/unknown"]},
        )
        assert resp.status_code == 422

    def test_hiding_all_pages_rejected(self, authed_client):
        all_pages = ["/", "/inbox", "/personal-inbox", "/transactions", "/spending", "/exports"]
        resp = authed_client.put(
            "/api/v1/settings",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": all_pages},
        )
        assert resp.status_code == 422

    def test_hiding_all_but_one_is_allowed(self, authed_client):
        pages = ["/inbox", "/personal-inbox", "/transactions", "/spending", "/exports"]
        resp = authed_client.put(
            "/api/v1/settings",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": pages},
        )
        assert resp.status_code == 200

    def test_whitespace_stripped_from_category_name(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["  Cafe  "]
        resp = authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        assert resp.status_code == 200
        assert "Cafe" in resp.json()["personal_categories"]
        assert "  Cafe  " not in resp.json()["personal_categories"]


# ---------------------------------------------------------------------------
# GET /api/v1/settings/category-usage
# ---------------------------------------------------------------------------


def _seed_transaction(authed_client, *, description: str, category: str | None, tx_type: str = "debit", classification: str | None = "personal"):
    payload = {
        "transaction_date": "2026-05-01",
        "description": description,
        "amount_cents": 1000,
        "transaction_type": tx_type,
        "classification": classification,
    }
    if category is not None:
        payload["personal_category"] = category
    resp = authed_client.post("/api/v1/transactions/manual", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCategoryUsage:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/settings/category-usage")
        assert resp.status_code == 401

    def test_empty_when_no_transactions(self, authed_client):
        resp = authed_client.get("/api/v1/settings/category-usage")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_counts_per_category(self, authed_client):
        _seed_transaction(authed_client, description="Latte", category="Dining")
        _seed_transaction(authed_client, description="Burger", category="Dining")
        _seed_transaction(authed_client, description="Apples", category="Groceries")
        resp = authed_client.get("/api/v1/settings/category-usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["Dining"] == 2
        assert data["Groceries"] == 1

    def test_excludes_uncategorized(self, authed_client):
        _seed_transaction(authed_client, description="No cat", category=None, classification=None)
        resp = authed_client.get("/api/v1/settings/category-usage")
        assert resp.status_code == 200
        assert resp.json() == {}


# ---------------------------------------------------------------------------
# PUT /api/v1/settings with on_delete=relabel
# ---------------------------------------------------------------------------


class TestDeleteCategoryWithRelabel:
    def test_remove_unused_category_succeeds_by_default(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["Coffee"]
        authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        # No transactions reference "Coffee" yet, removal should succeed.
        resp = authed_client.put(
            "/api/v1/settings",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": []},
        )
        assert resp.status_code == 200
        assert "Coffee" not in resp.json()["personal_categories"]

    def test_remove_in_use_category_rejects_by_default(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["Coffee"]
        authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        _seed_transaction(authed_client, description="Latte", category="Coffee")
        resp = authed_client.put(
            "/api/v1/settings",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": []},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert "Coffee" in body["detail"]["in_use"]
        assert body["detail"]["in_use"]["Coffee"] == 1

    def test_remove_in_use_with_relabel_moves_rows(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["Coffee"]
        authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        _seed_transaction(authed_client, description="Latte", category="Coffee")
        _seed_transaction(authed_client, description="Mocha", category="Coffee")
        resp = authed_client.put(
            "/api/v1/settings?on_delete=relabel&relabel_target=Dining",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": []},
        )
        assert resp.status_code == 200
        usage = authed_client.get("/api/v1/settings/category-usage").json()
        assert "Coffee" not in usage
        assert usage["Dining"] == 2

    def test_relabel_requires_target_in_new_categories(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["Coffee"]
        authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        _seed_transaction(authed_client, description="Latte", category="Coffee")
        resp = authed_client.put(
            "/api/v1/settings?on_delete=relabel&relabel_target=NotARealCategory",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": []},
        )
        assert resp.status_code == 400

    def test_relabel_requires_target_param(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["Coffee"]
        authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        _seed_transaction(authed_client, description="Latte", category="Coffee")
        resp = authed_client.put(
            "/api/v1/settings?on_delete=relabel",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": []},
        )
        assert resp.status_code == 400

    def test_rename_via_in_place_swap_with_relabel(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["Coffee"]
        authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        _seed_transaction(authed_client, description="Latte", category="Coffee")
        _seed_transaction(authed_client, description="Mocha", category="Coffee")
        renamed_cats = list(DEFAULT_CATEGORIES) + ["Cafe"]
        resp = authed_client.put(
            "/api/v1/settings?on_delete=relabel&relabel_target=Cafe",
            json={"personal_categories": renamed_cats, "hidden_pages": []},
        )
        assert resp.status_code == 200
        usage = authed_client.get("/api/v1/settings/category-usage").json()
        assert "Coffee" not in usage
        assert usage["Cafe"] == 2

    def test_multiple_removed_categories_all_relabel_to_target(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["Coffee", "Tea"]
        authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        _seed_transaction(authed_client, description="Latte", category="Coffee")
        _seed_transaction(authed_client, description="Earl Grey", category="Tea")
        resp = authed_client.put(
            "/api/v1/settings?on_delete=relabel&relabel_target=Other",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": []},
        )
        assert resp.status_code == 200
        usage = authed_client.get("/api/v1/settings/category-usage").json()
        assert "Coffee" not in usage
        assert "Tea" not in usage
        assert usage["Other"] == 2

    def test_debit_category_cannot_relabel_to_income(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["Coffee"]
        authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        _seed_transaction(authed_client, description="Latte", category="Coffee")

        resp = authed_client.put(
            "/api/v1/settings?on_delete=relabel&relabel_target=Income",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": []},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Income/Reimbursement categories only apply to credit transactions"

    def test_debit_category_cannot_relabel_to_reimbursement(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["Coffee"]
        authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        _seed_transaction(authed_client, description="Latte", category="Coffee")

        resp = authed_client.put(
            "/api/v1/settings?on_delete=relabel&relabel_target=Reimbursement",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": []},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Income/Reimbursement categories only apply to credit transactions"

    def test_credit_category_can_relabel_to_income(self, authed_client):
        cats = list(DEFAULT_CATEGORIES) + ["Bonus"]
        authed_client.put("/api/v1/settings", json={"personal_categories": cats, "hidden_pages": []})
        _seed_transaction(authed_client, description="Payroll bonus", category="Bonus", tx_type="credit")

        resp = authed_client.put(
            "/api/v1/settings?on_delete=relabel&relabel_target=Income",
            json={"personal_categories": list(DEFAULT_CATEGORIES), "hidden_pages": []},
        )

        assert resp.status_code == 200
        usage = authed_client.get("/api/v1/settings/category-usage").json()
        assert "Bonus" not in usage
        assert usage["Income"] == 1
