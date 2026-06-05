"""Phase 3: backup / restore / support-bundle endpoints."""

import io
import sqlite3
import zipfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings as app_settings
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


def _add_tx(db, description, source_hash):
    db.add(Transaction(
        transaction_date=date(2026, 5, 1),
        description=description,
        amount_cents=4242,
        transaction_type="debit",
        classification="personal",
        personal_category="Groceries",
        source_hash=source_hash,
    ))
    db.commit()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db_path = tmp_path / "centsmith.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setattr(app_settings, "database_url", db_url)
    run_migrations()
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    seed = Session()
    seed.add(User(username="user1", display_name="User 1", hashed_password=hash_password("password")))
    seed.commit()
    _add_tx(seed, "ORIGINAL MERCHANT", "A1")
    seed.close()

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.post("/api/v1/auth/login", data={"username": "user1", "password": "password"})
    try:
        yield SimpleNamespace(client=client, engine=engine, Session=Session, db_path=db_path)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_requires_auth(env):
    app.dependency_overrides.clear()
    client = TestClient(app)
    assert client.get("/api/v1/maintenance/backup").status_code == 401


def test_data_location_returns_db_folder(env):
    resp = env.client.get("/api/v1/maintenance/data-location")
    assert resp.status_code == 200
    assert resp.json()["path"] == str(env.db_path.parent)


def test_open_data_folder_invokes_launcher(env, monkeypatch):
    # Don't actually pop an Explorer window during the test; assert the backend
    # targets the DB folder and reports whether the launcher succeeded.
    revealed = {}

    def fake_reveal(path):
        revealed["path"] = path
        return True

    monkeypatch.setattr("app.routers.maintenance.reveal_in_file_manager", fake_reveal)
    resp = env.client.post("/api/v1/maintenance/open-data-folder")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"opened": True, "path": str(env.db_path.parent)}
    assert str(revealed["path"]) == str(env.db_path.parent)


def test_open_data_folder_reports_failure(env, monkeypatch):
    monkeypatch.setattr("app.routers.maintenance.reveal_in_file_manager", lambda _p: False)
    resp = env.client.post("/api/v1/maintenance/open-data-folder")
    assert resp.status_code == 200
    assert resp.json() == {"opened": False, "path": str(env.db_path.parent)}


def test_open_data_folder_requires_auth(env):
    app.dependency_overrides.clear()
    client = TestClient(app)
    assert client.post("/api/v1/maintenance/open-data-folder").status_code == 401


def test_backup_is_valid_sqlite(env):
    resp = env.client.get("/api/v1/maintenance/backup")
    assert resp.status_code == 200
    assert resp.content.startswith(b"SQLite format 3\x00")


def test_backup_to_disk_writes_file_in_backups_folder(env):
    resp = env.client.post("/api/v1/maintenance/backup-to-disk")
    assert resp.status_code == 200
    dest = Path(resp.json()["path"])
    assert dest.exists()
    assert dest.parent == env.db_path.parent / "backups"
    assert dest.read_bytes().startswith(b"SQLite format 3\x00")


def test_backup_to_disk_requires_auth(env):
    app.dependency_overrides.clear()
    client = TestClient(app)
    assert client.post("/api/v1/maintenance/backup-to-disk").status_code == 401


def test_list_backups_is_empty_then_lists_written_backup(env):
    assert env.client.get("/api/v1/maintenance/backups").json() == {"backups": []}

    written = Path(env.client.post("/api/v1/maintenance/backup-to-disk").json()["path"])
    listed = env.client.get("/api/v1/maintenance/backups").json()["backups"]
    assert [b["name"] for b in listed] == [written.name]
    assert listed[0]["size_bytes"] > 0
    assert "modified" in listed[0]


def test_restore_from_disk_round_trip(env):
    # Snapshot to the backups folder (only ORIGINAL MERCHANT / A1 present).
    name = Path(env.client.post("/api/v1/maintenance/backup-to-disk").json()["path"]).name

    # Mutate the live DB, then restore the on-disk backup by name.
    db = env.Session()
    _add_tx(db, "LATER MERCHANT", "B2")
    db.close()

    resp = env.client.post("/api/v1/maintenance/restore-from-disk", json={"name": name})
    assert resp.status_code == 200

    check = env.Session()
    hashes = {h for (h,) in check.query(Transaction.source_hash).all()}
    check.close()
    assert hashes == {"A1"}


def test_restore_from_disk_rejects_path_traversal(env):
    resp = env.client.post(
        "/api/v1/maintenance/restore-from-disk",
        json={"name": "../centsmith.db"},
    )
    assert resp.status_code == 400
    # The live data is untouched after a rejected restore.
    check = env.Session()
    hashes = {h for (h,) in check.query(Transaction.source_hash).all()}
    check.close()
    assert hashes == {"A1"}


def test_restore_from_disk_rejects_missing_file(env):
    resp = env.client.post(
        "/api/v1/maintenance/restore-from-disk",
        json={"name": "does-not-exist.db"},
    )
    assert resp.status_code == 400


def test_backup_then_restore_round_trip(env):
    # Snapshot the original DB (contains only ORIGINAL MERCHANT / A1).
    backup = env.client.get("/api/v1/maintenance/backup").content

    # Mutate the live DB: add a second transaction the backup doesn't have.
    db = env.Session()
    _add_tx(db, "LATER MERCHANT", "B2")
    db.close()

    # Restore the earlier backup — the later row must disappear.
    resp = env.client.post(
        "/api/v1/maintenance/restore",
        files={"file": ("backup.db", backup, "application/x-sqlite3")},
    )
    assert resp.status_code == 200

    check = env.Session()
    hashes = {h for (h,) in check.query(Transaction.source_hash).all()}
    check.close()
    assert hashes == {"A1"}


def test_restore_rejects_non_sqlite(env):
    resp = env.client.post(
        "/api/v1/maintenance/restore",
        files={"file": ("notes.txt", b"this is not a database", "text/plain")},
    )
    assert resp.status_code == 400
    assert "SQLite" in resp.json()["detail"]


def test_restore_rejects_incompatible_schema(env, tmp_path):
    # A valid SQLite file, but missing Centsmith's required tables.
    foreign = tmp_path / "foreign.db"
    conn = sqlite3.connect(str(foreign))
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()

    resp = env.client.post(
        "/api/v1/maintenance/restore",
        files={"file": ("foreign.db", foreign.read_bytes(), "application/x-sqlite3")},
    )
    assert resp.status_code == 400

    # The original data is still intact after a rejected restore.
    check = env.Session()
    hashes = {h for (h,) in check.query(Transaction.source_hash).all()}
    check.close()
    assert hashes == {"A1"}


def test_restore_rejects_backup_missing_users_table(env, tmp_path):
    # A SQLite file that has transactions + a head alembic_version but no users
    # table. Migrations would consider it up to date and never recreate users,
    # so restore must reject it instead of leaving the app without auth data.
    broken = tmp_path / "broken.db"
    conn = sqlite3.connect(str(broken))
    conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
    conn.execute("INSERT INTO alembic_version (version_num) VALUES ('20260602_0006')")
    conn.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    resp = env.client.post(
        "/api/v1/maintenance/restore",
        files={"file": ("broken.db", broken.read_bytes(), "application/x-sqlite3")},
    )
    assert resp.status_code == 400

    # Original data and users survive the rejected restore.
    check = env.Session()
    hashes = {h for (h,) in check.query(Transaction.source_hash).all()}
    users = check.query(User).count()
    check.close()
    assert hashes == {"A1"}
    assert users == 1


def test_support_bundle_excludes_secrets_and_financial_data(env, tmp_path, monkeypatch):
    # Point the log directory at a temp folder containing a secret-bearing line.
    data_dir = tmp_path / "datadir"
    data_dir.mkdir()
    (data_dir / "shell.log").write_text(
        "[1] backend started on port 8012\n[2] session secret=supersecrettoken123\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.config._user_data_dir", lambda: data_dir)

    resp = env.client.get("/api/v1/maintenance/support-bundle")
    assert resp.status_code == 200

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "metadata.json" in names
        blob = b"".join(zf.read(n) for n in names)

    text = blob.decode("utf-8", errors="replace")
    # No financial row data and no secret material leaks into the bundle.
    assert "ORIGINAL MERCHANT" not in text
    assert "4242" not in text
    assert "supersecrettoken123" not in text
    assert "[redacted]" in text
    # Non-financial settings summary is present.
    assert "Groceries" in text
