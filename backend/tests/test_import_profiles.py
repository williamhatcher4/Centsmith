"""Phase 1: import profile CRUD + reuse through the import preview."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings as app_settings
from app.dependencies import get_db
from app.main import app
from app.migrations import run_migrations
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
    db_path = tmp_path / "test_import_profiles.db"
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
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


@pytest.fixture()
def authed_client(client):
    resp = client.post("/api/v1/auth/login", data={"username": "user1", "password": "password"})
    assert resp.status_code == 200
    return client


def _profile_payload(**overrides):
    payload = {
        "name": "My Bank",
        "source_type": "card",
        "date_column": 0,
        "description_column": 1,
        "amount_column": 2,
        "amount_convention": "signed",
        "ignored_payment_patterns": [],
    }
    payload.update(overrides)
    return payload


def test_requires_auth(client):
    assert client.get("/api/v1/import-profiles").status_code == 401


def test_profile_crud_lifecycle(authed_client):
    created = authed_client.post("/api/v1/import-profiles", json=_profile_payload())
    assert created.status_code == 201
    pid = created.json()["id"]

    listing = authed_client.get("/api/v1/import-profiles")
    assert listing.status_code == 200
    assert [p["name"] for p in listing.json()] == ["My Bank"]

    updated = authed_client.put(
        f"/api/v1/import-profiles/{pid}", json=_profile_payload(name="Renamed Bank")
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed Bank"

    assert authed_client.delete(f"/api/v1/import-profiles/{pid}").status_code == 204
    assert authed_client.get("/api/v1/import-profiles").json() == []


def test_duplicate_name_rejected(authed_client):
    assert authed_client.post("/api/v1/import-profiles", json=_profile_payload()).status_code == 201
    dup = authed_client.post("/api/v1/import-profiles", json=_profile_payload())
    assert dup.status_code == 409


def test_update_missing_profile_404(authed_client):
    assert authed_client.put("/api/v1/import-profiles/999", json=_profile_payload()).status_code == 404


def test_mapping_required_then_profile_reuse(authed_client):
    unknown_csv = b"Col A,Col B,Col C\n2026-05-01,Coffee,-4.25\n2026-05-02,Lunch,-9.50\n"

    # Without a mapping the preview asks the user to map columns.
    preview = authed_client.post(
        "/api/v1/transactions/import/preview",
        files={"file": ("statement.csv", unknown_csv, "text/csv")},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["mapping_required"] is True
    assert body["available_columns"] == ["Col A", "Col B", "Col C"]

    # Save a profile, then reuse it to import the same file without re-mapping.
    pid = authed_client.post("/api/v1/import-profiles", json=_profile_payload(name="ColBank")).json()["id"]
    reused = authed_client.post(
        "/api/v1/transactions/import/preview",
        files={"file": ("statement.csv", unknown_csv, "text/csv")},
        data={"profile_id": str(pid)},
    )
    assert reused.status_code == 200
    reused_body = reused.json()
    assert reused_body["mapping_required"] is False
    assert reused_body["to_import"] == 2


def test_inline_column_mapping_on_preview(authed_client):
    unknown_csv = b"Col A,Col B,Col C\n2026-05-01,Coffee,-4.25\n"
    mapping = '{"date_column":0,"description_column":1,"amount_column":2,"amount_convention":"signed"}'
    preview = authed_client.post(
        "/api/v1/transactions/import/preview",
        files={"file": ("statement.csv", unknown_csv, "text/csv")},
        data={"column_mapping": mapping},
    )
    assert preview.status_code == 200
    assert preview.json()["to_import"] == 1


# ---------------------------------------------------------------------------
# P3.4: saved date convention (day-first imports)
# ---------------------------------------------------------------------------


def test_date_convention_round_trips_through_profile_crud(authed_client):
    created = authed_client.post(
        "/api/v1/import-profiles", json=_profile_payload(name="DMY Bank", date_convention="dmy")
    )
    assert created.status_code == 201
    assert created.json()["date_convention"] == "dmy"

    listed = authed_client.get("/api/v1/import-profiles").json()
    assert listed[0]["date_convention"] == "dmy"

    pid = created.json()["id"]
    updated = authed_client.put(
        f"/api/v1/import-profiles/{pid}", json=_profile_payload(name="DMY Bank", date_convention=None)
    )
    assert updated.status_code == 200
    assert updated.json()["date_convention"] is None


def test_profile_defaults_to_no_date_convention(authed_client):
    created = authed_client.post("/api/v1/import-profiles", json=_profile_payload())
    assert created.status_code == 201
    assert created.json()["date_convention"] is None


def test_invalid_date_convention_rejected(authed_client):
    resp = authed_client.post(
        "/api/v1/import-profiles", json=_profile_payload(date_convention="ymd")
    )
    assert resp.status_code == 422


def test_profile_date_convention_applies_without_the_toggle(authed_client):
    ambiguous_csv = b"Col A,Col B,Col C\n04/05/2026,Coffee,-4.25\n"
    pid = authed_client.post(
        "/api/v1/import-profiles", json=_profile_payload(name="Canadian Bank", date_convention="dmy")
    ).json()["id"]

    preview = authed_client.post(
        "/api/v1/transactions/import/preview",
        files={"file": ("statement.csv", ambiguous_csv, "text/csv")},
        data={"profile_id": str(pid)},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["day_first"] is True
    assert body["rows"][0]["date"] == "2026-05-04"

    # An explicit toggle wins over the profile's saved convention.
    overridden = authed_client.post(
        "/api/v1/transactions/import/preview",
        files={"file": ("statement.csv", ambiguous_csv, "text/csv")},
        data={"profile_id": str(pid), "day_first": "false"},
    )
    assert overridden.status_code == 200
    assert overridden.json()["day_first"] is False
    assert overridden.json()["rows"][0]["date"] == "2026-04-05"


def test_inline_column_mapping_accepts_date_convention(authed_client):
    unknown_csv = b"Col A,Col B,Col C\n04/05/2026,Coffee,-4.25\n"
    mapping = '{"date_column":0,"description_column":1,"amount_column":2,"amount_convention":"signed","date_convention":"dmy"}'
    preview = authed_client.post(
        "/api/v1/transactions/import/preview",
        files={"file": ("statement.csv", unknown_csv, "text/csv")},
        data={"column_mapping": mapping},
    )
    assert preview.status_code == 200
    assert preview.json()["rows"][0]["date"] == "2026-05-04"


def test_profile_ignored_patterns_exclude_rows(authed_client):
    csv_bytes = b"Col A,Col B,Col C\n2026-05-01,COFFEE,-4.25\n2026-05-02,AUTOPAY THANKS,-50.00\n"
    pid = authed_client.post(
        "/api/v1/import-profiles",
        json=_profile_payload(name="IgnoreBank", ignored_payment_patterns=["AUTOPAY"]),
    ).json()["id"]
    preview = authed_client.post(
        "/api/v1/transactions/import/preview",
        files={"file": ("statement.csv", csv_bytes, "text/csv")},
        data={"profile_id": str(pid)},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["ignored_credits"] == 1
    assert body["to_import"] == 1
