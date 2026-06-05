"""Tests for the /api/v1/cards endpoints and card association."""

import csv
import io
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings as app_settings
from app.dependencies import get_db
from app.main import app
from app.migrations import run_migrations
from app.models.card import Card
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
    db_path = tmp_path / "test_cards.db"
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


def make_card(client: TestClient, name="Amex", last4="1009", statement_day=21) -> dict:
    resp = client.post(
        "/api/v1/cards",
        json={"name": name, "last4": last4, "statement_day": statement_day},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_tx(db, *, card_id=None, amount_cents=1000, tx_type="debit", on=date(2026, 5, 1), desc="X", hash_suffix=""):
    tx = Transaction(
        transaction_date=on,
        description=desc,
        amount_cents=amount_cents,
        transaction_type=tx_type,
        classification=None,
        source_hash=f"test:{desc}:{on}:{amount_cents}:{tx_type}:{hash_suffix}",
        card_id=card_id,
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


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuth:
    def test_list_requires_auth(self, client):
        assert client.get("/api/v1/cards").status_code == 401

    def test_create_requires_auth(self, client):
        assert client.post("/api/v1/cards", json={"name": "X"}).status_code == 401


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestCardCrud:
    def test_create_and_list(self, authed_client):
        card = make_card(authed_client)
        assert card["name"] == "Amex"
        assert card["last4"] == "1009"
        assert card["statement_day"] == 21
        listed = authed_client.get("/api/v1/cards").json()
        assert [c["id"] for c in listed] == [card["id"]]

    def test_create_rejects_empty_name(self, authed_client):
        assert authed_client.post("/api/v1/cards", json={"name": "  "}).status_code == 422

    def test_create_rejects_bad_statement_day(self, authed_client):
        assert authed_client.post("/api/v1/cards", json={"name": "X", "statement_day": 40}).status_code == 422

    def test_create_rejects_bad_last4(self, authed_client):
        assert authed_client.post("/api/v1/cards", json={"name": "X", "last4": "12ab"}).status_code == 422

    def test_create_allows_minimal(self, authed_client):
        resp = authed_client.post("/api/v1/cards", json={"name": "Cash card"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["last4"] is None
        assert body["statement_day"] is None

    def test_update(self, authed_client):
        card = make_card(authed_client)
        resp = authed_client.put(
            f"/api/v1/cards/{card['id']}",
            json={"name": "Amex Gold", "last4": "2002", "statement_day": 15},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Amex Gold"
        assert resp.json()["statement_day"] == 15

    def test_update_missing_404(self, authed_client):
        assert authed_client.put("/api/v1/cards/999", json={"name": "Nope"}).status_code == 404

    def test_delete_nulls_out_card_id(self, authed_client, db_session):
        card = make_card(authed_client)
        tx = add_tx(db_session, card_id=card["id"])
        resp = authed_client.delete(f"/api/v1/cards/{card['id']}")
        assert resp.status_code == 200
        db_session.expire_all()
        assert db_session.query(Transaction).get(tx.id).card_id is None
        assert db_session.query(Card).count() == 0

    def test_delete_missing_404(self, authed_client):
        assert authed_client.delete("/api/v1/cards/999").status_code == 404


# ---------------------------------------------------------------------------
# Statement aggregation
# ---------------------------------------------------------------------------


class TestStatement:
    def test_charges_payments_net(self, authed_client, db_session):
        card = make_card(authed_client)
        cid = card["id"]
        add_tx(db_session, card_id=cid, amount_cents=10000, tx_type="debit", on=date(2026, 4, 22), desc="A")
        add_tx(db_session, card_id=cid, amount_cents=5000, tx_type="debit", on=date(2026, 5, 21), desc="B")
        add_tx(db_session, card_id=cid, amount_cents=3000, tx_type="credit", on=date(2026, 5, 10), desc="Pay")
        resp = authed_client.get(
            f"/api/v1/cards/{cid}/statement",
            params={"start_date": "2026-04-22", "end_date": "2026-05-21"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["charges_cents"] == 15000
        assert body["payments_cents"] == 3000
        assert body["net_cents"] == 12000
        assert body["charge_count"] == 2
        assert body["payment_count"] == 1

    def test_window_boundaries_inclusive_and_exclusive(self, authed_client, db_session):
        card = make_card(authed_client)
        cid = card["id"]
        # On both boundaries -> included.
        add_tx(db_session, card_id=cid, amount_cents=100, on=date(2026, 4, 22), desc="start")
        add_tx(db_session, card_id=cid, amount_cents=200, on=date(2026, 5, 21), desc="end")
        # Just outside -> excluded.
        add_tx(db_session, card_id=cid, amount_cents=999, on=date(2026, 4, 21), desc="before")
        add_tx(db_session, card_id=cid, amount_cents=999, on=date(2026, 5, 22), desc="after")
        body = authed_client.get(
            f"/api/v1/cards/{cid}/statement",
            params={"start_date": "2026-04-22", "end_date": "2026-05-21"},
        ).json()
        assert body["charges_cents"] == 300
        assert body["charge_count"] == 2

    def test_isolated_by_card(self, authed_client, db_session):
        a = make_card(authed_client, name="A", last4="1111")
        b = make_card(authed_client, name="B", last4="2222")
        add_tx(db_session, card_id=a["id"], amount_cents=100, on=date(2026, 5, 1), desc="a1")
        add_tx(db_session, card_id=b["id"], amount_cents=900, on=date(2026, 5, 1), desc="b1")
        body = authed_client.get(
            f"/api/v1/cards/{a['id']}/statement",
            params={"start_date": "2026-05-01", "end_date": "2026-05-31"},
        ).json()
        assert body["charges_cents"] == 100

    def test_statement_missing_card_404(self, authed_client):
        resp = authed_client.get(
            "/api/v1/cards/999/statement",
            params={"start_date": "2026-05-01", "end_date": "2026-05-31"},
        )
        assert resp.status_code == 404

    def test_statement_rejects_inverted_window(self, authed_client):
        card = make_card(authed_client)
        resp = authed_client.get(
            f"/api/v1/cards/{card['id']}/statement",
            params={"start_date": "2026-05-31", "end_date": "2026-05-01"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Bulk assign + list filter
# ---------------------------------------------------------------------------


class TestBulkAssignAndFilter:
    def test_bulk_assign_and_unassign(self, authed_client, db_session):
        card = make_card(authed_client)
        t1 = add_tx(db_session, desc="t1")
        t2 = add_tx(db_session, desc="t2")
        resp = authed_client.post(
            "/api/v1/transactions/bulk-assign-card",
            json={"transaction_ids": [t1.id, t2.id], "card_id": card["id"]},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 2
        db_session.expire_all()
        assert db_session.query(Transaction).get(t1.id).card_id == card["id"]
        # Unassign with null.
        resp = authed_client.post(
            "/api/v1/transactions/bulk-assign-card",
            json={"transaction_ids": [t1.id], "card_id": None},
        )
        assert resp.status_code == 200
        db_session.expire_all()
        assert db_session.query(Transaction).get(t1.id).card_id is None

    def test_bulk_assign_missing_card_404(self, authed_client, db_session):
        t1 = add_tx(db_session, desc="t1")
        resp = authed_client.post(
            "/api/v1/transactions/bulk-assign-card",
            json={"transaction_ids": [t1.id], "card_id": 999},
        )
        assert resp.status_code == 404

    def test_bulk_assign_missing_tx_404(self, authed_client, db_session):
        card = make_card(authed_client)
        resp = authed_client.post(
            "/api/v1/transactions/bulk-assign-card",
            json={"transaction_ids": [999], "card_id": card["id"]},
        )
        assert resp.status_code == 404

    def test_list_filter_by_card(self, authed_client, db_session):
        card = make_card(authed_client)
        on = date(2026, 5, 1)
        assigned = add_tx(db_session, card_id=card["id"], desc="assigned", on=on)
        add_tx(db_session, desc="unassigned", on=on)
        # Include a credit row on the card to confirm the filter returns both types.
        add_tx(db_session, card_id=card["id"], tx_type="credit", desc="payment", on=on)
        resp = authed_client.get("/api/v1/transactions", params={"card_id": card["id"]})
        assert resp.status_code == 200
        items = resp.json()["items"]
        descs = {i["description"] for i in items}
        assert descs == {"assigned", "payment"}
        assert all(i["card_id"] == card["id"] for i in items)


# ---------------------------------------------------------------------------
# Import stamps card_id
# ---------------------------------------------------------------------------


class TestImportWithCard:
    def test_import_stamps_card_id(self, authed_client, db_session):
        card = make_card(authed_client)
        resp = authed_client.post(
            "/api/v1/transactions/import/confirm",
            files=statement_file([["2026-05-01", "Coffee", "4.25", ""]]),
            data={"card_id": str(card["id"])},
        )
        assert resp.status_code == 200
        assert resp.json()["imported"] == 1
        rows = db_session.query(Transaction).all()
        assert len(rows) == 1
        assert rows[0].card_id == card["id"]

    def test_import_unknown_card_404(self, authed_client):
        resp = authed_client.post(
            "/api/v1/transactions/import/confirm",
            files=statement_file([["2026-05-01", "Coffee", "4.25", ""]]),
            data={"card_id": "999"},
        )
        assert resp.status_code == 404

    def test_import_without_card_leaves_null(self, authed_client, db_session):
        resp = authed_client.post(
            "/api/v1/transactions/import/confirm",
            files=statement_file([["2026-05-01", "Coffee", "4.25", ""]]),
        )
        assert resp.status_code == 200
        rows = db_session.query(Transaction).all()
        assert rows[0].card_id is None
