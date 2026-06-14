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


# --- License token (moved from Tauri IPC to the local backend) -----------------


def _license_file(env) -> Path:
    """The token file lives beside the database — the path the updater reads."""
    return env.db_path.parent / "license.token"


def test_license_status_absent_by_default(env):
    resp = env.client.get("/api/v1/maintenance/license")
    assert resp.status_code == 200
    assert resp.json() == {"present": False, "hint": None}
    assert not _license_file(env).exists()


def test_set_license_writes_token_and_masks_hint(env):
    resp = env.client.post("/api/v1/maintenance/license", json={"token": "  lic-ABCD1234  "})
    assert resp.status_code == 200
    # Never returns the full token — only present + a masked tail.
    assert resp.json() == {"present": True, "hint": "…1234"}
    # The trimmed token lands in the file the Tauri updater reads.
    assert _license_file(env).read_text(encoding="utf-8") == "lic-ABCD1234"

    # A follow-up status read reflects the stored token.
    status = env.client.get("/api/v1/maintenance/license")
    assert status.json() == {"present": True, "hint": "…1234"}


def test_set_blank_license_clears_existing(env):
    env.client.post("/api/v1/maintenance/license", json={"token": "real-token"})
    assert _license_file(env).exists()
    resp = env.client.post("/api/v1/maintenance/license", json={"token": "   "})
    assert resp.status_code == 200
    assert resp.json() == {"present": False, "hint": None}
    assert not _license_file(env).exists()


def test_delete_license_is_idempotent(env):
    # Removing a non-existent token succeeds.
    resp = env.client.delete("/api/v1/maintenance/license")
    assert resp.status_code == 200
    assert resp.json() == {"present": False, "hint": None}

    env.client.post("/api/v1/maintenance/license", json={"token": "real-token"})
    assert _license_file(env).exists()
    resp = env.client.delete("/api/v1/maintenance/license")
    assert resp.status_code == 200
    assert resp.json() == {"present": False, "hint": None}
    assert not _license_file(env).exists()


def test_license_endpoints_require_auth(env):
    app.dependency_overrides.clear()
    client = TestClient(app)
    assert client.get("/api/v1/maintenance/license").status_code == 401
    assert client.post("/api/v1/maintenance/license", json={"token": "x"}).status_code == 401
    assert client.delete("/api/v1/maintenance/license").status_code == 401


# --- Update-check status (P2.2: written by the desktop shell) ------------------


def _update_check_file(env) -> Path:
    """The status file lives beside the database — where the shell writes it."""
    return env.db_path.parent / "update-check.json"


def test_update_status_absent_when_no_check_recorded(env):
    resp = env.client.get("/api/v1/maintenance/update-status")
    assert resp.status_code == 200
    assert resp.json() == {"present": False, "checked_at": None, "result": None, "detail": None}


def test_update_status_returns_recorded_check(env):
    _update_check_file(env).write_text(
        '{"checked_at": "2026-06-09T08:15:00Z", "result": "ok-uptodate", "detail": ""}',
        encoding="utf-8",
    )
    resp = env.client.get("/api/v1/maintenance/update-status")
    assert resp.status_code == 200
    assert resp.json() == {
        "present": True,
        "checked_at": "2026-06-09T08:15:00Z",
        "result": "ok-uptodate",
        "detail": "",
    }


def test_update_status_surfaces_error_result(env):
    _update_check_file(env).write_text(
        '{"checked_at": "2026-06-09T08:15:00Z", "result": "error", "detail": "connection refused"}',
        encoding="utf-8",
    )
    body = env.client.get("/api/v1/maintenance/update-status").json()
    assert body["present"] is True
    assert body["result"] == "error"
    assert body["detail"] == "connection refused"


def test_update_status_tolerates_malformed_file(env):
    _update_check_file(env).write_text("not json {", encoding="utf-8")
    resp = env.client.get("/api/v1/maintenance/update-status")
    assert resp.status_code == 200
    assert resp.json() == {"present": False, "checked_at": None, "result": None, "detail": None}


def test_update_status_tolerates_non_object_json(env):
    _update_check_file(env).write_text('["unexpected"]', encoding="utf-8")
    assert env.client.get("/api/v1/maintenance/update-status").json()["present"] is False


def test_update_status_ignores_unknown_and_non_string_fields(env):
    _update_check_file(env).write_text(
        '{"checked_at": 12345, "result": "ok-uptodate", "extra": "x"}',
        encoding="utf-8",
    )
    body = env.client.get("/api/v1/maintenance/update-status").json()
    # Non-string fields coerce to None and unknown keys are dropped.
    assert body == {"present": True, "checked_at": None, "result": "ok-uptodate", "detail": None}


def test_update_status_requires_auth(env):
    app.dependency_overrides.clear()
    client = TestClient(app)
    assert client.get("/api/v1/maintenance/update-status").status_code == 401


# --- Pre-migration auto-backup (P0.3) ------------------------------------------


EARLIER_REVISION = "20260602_0006"


@pytest.fixture()
def older_rev_db(tmp_path, monkeypatch):
    """A real database migrated to an older revision, with settings pointed at it."""
    from alembic import command

    from app import migrations

    db_path = tmp_path / "older.db"
    monkeypatch.setattr(app_settings, "database_url", f"sqlite:///{db_path}")
    command.upgrade(migrations._alembic_config(), EARLIER_REVISION)
    return db_path


def _pre_migration_snapshots(db_path: Path) -> list[Path]:
    folder = db_path.parent / "backups"
    return sorted(folder.glob("pre-migration-*.db")) if folder.is_dir() else []


def _revision_of(db_file: Path) -> str:
    conn = sqlite3.connect(str(db_file))
    try:
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        conn.close()


def test_pre_migration_snapshot_created(older_rev_db):
    run_migrations()
    snaps = _pre_migration_snapshots(older_rev_db)
    assert len(snaps) == 1
    assert EARLIER_REVISION in snaps[0].name
    # The snapshot preserves the pre-upgrade revision; the live DB moved to head.
    assert _revision_of(snaps[0]) == EARLIER_REVISION
    assert _revision_of(older_rev_db) != EARLIER_REVISION


def test_no_snapshot_when_at_head(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr(app_settings, "database_url", f"sqlite:///{db_path}")
    # Fresh install: no alembic_version table yet — no snapshot.
    run_migrations()
    assert _pre_migration_snapshots(db_path) == []
    # Second startup at head — still no snapshot.
    run_migrations()
    assert _pre_migration_snapshots(db_path) == []


def test_pre_migration_snapshot_retention(older_rev_db):
    import os

    backups = older_rev_db.parent / "backups"
    backups.mkdir()
    seeded = []
    for i in range(3):
        stale = backups / f"pre-migration-oldrev-old{i}.db"
        stale.write_bytes(b"stale snapshot")
        os.utime(stale, (1_000_000 + i, 1_000_000 + i))
        seeded.append(stale.name)

    run_migrations()

    names = [p.name for p in _pre_migration_snapshots(older_rev_db)]
    assert len(names) == 3
    # The oldest seeded snapshot was pruned; the freshly created one is kept.
    assert seeded[0] not in names
    assert seeded[1] in names and seeded[2] in names
    assert any(EARLIER_REVISION in n for n in names)


# --- Configurable backup folder (P4.4) ------------------------------------------


def _set_backup_folder(env, folder):
    """Set user_settings.backup_folder directly (validation is covered in
    test_settings.py; these tests exercise the service-level routing)."""
    from app.routers.settings import _get_or_create

    db = env.Session()
    obj = _get_or_create(db)
    obj.backup_folder = folder
    db.commit()
    db.close()


def test_backup_to_disk_honors_configured_folder(env, tmp_path):
    external = tmp_path / "external-drive"
    external.mkdir()
    _set_backup_folder(env, str(external))

    dest = Path(env.client.post("/api/v1/maintenance/backup-to-disk").json()["path"])
    assert dest.parent == external
    assert dest.read_bytes().startswith(b"SQLite format 3\x00")
    # The default folder beside the DB is untouched.
    assert not (env.db_path.parent / "backups").exists()

    listed = env.client.get("/api/v1/maintenance/backups").json()["backups"]
    assert [b["name"] for b in listed] == [dest.name]


def test_restore_from_disk_reads_configured_folder(env, tmp_path):
    external = tmp_path / "external-restore"
    external.mkdir()
    _set_backup_folder(env, str(external))
    name = Path(env.client.post("/api/v1/maintenance/backup-to-disk").json()["path"]).name

    db = env.Session()
    _add_tx(db, "AFTER CONFIGURED BACKUP", "C3")
    db.close()

    resp = env.client.post("/api/v1/maintenance/restore-from-disk", json={"name": name})
    assert resp.status_code == 200

    check = env.Session()
    hashes = {h for (h,) in check.query(Transaction.source_hash).all()}
    check.close()
    assert hashes == {"A1"}


def test_blank_configured_folder_falls_back_to_default(env):
    _set_backup_folder(env, "   ")
    dest = Path(env.client.post("/api/v1/maintenance/backup-to-disk").json()["path"])
    assert dest.parent == env.db_path.parent / "backups"


def test_backup_to_disk_unavailable_configured_folder_returns_400(env, tmp_path):
    # The folder was valid when saved but is unusable now (here: a path
    # component is a file — same shape as an unplugged drive). The route must
    # answer a clear 400, not let the OSError escape as a 500.
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("not a directory")
    _set_backup_folder(env, str(blocker / "sub"))

    resp = env.client.post("/api/v1/maintenance/backup-to-disk")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Could not write the backup" in detail
    assert str(blocker / "sub") in detail


def test_open_backup_folder_targets_default_backups_dir(env, monkeypatch):
    revealed = {}

    def fake_reveal(path):
        revealed["path"] = path
        return True

    monkeypatch.setattr("app.routers.maintenance.reveal_in_file_manager", fake_reveal)
    resp = env.client.post("/api/v1/maintenance/open-backup-folder")
    assert resp.status_code == 200
    assert resp.json() == {"opened": True, "path": str(env.db_path.parent / "backups")}
    assert str(revealed["path"]) == str(env.db_path.parent / "backups")


def test_open_backup_folder_honors_configured_folder(env, tmp_path, monkeypatch):
    external = tmp_path / "external-open"
    external.mkdir()
    _set_backup_folder(env, str(external))

    revealed = {}

    def fake_reveal(path):
        revealed["path"] = path
        return True

    monkeypatch.setattr("app.routers.maintenance.reveal_in_file_manager", fake_reveal)
    resp = env.client.post("/api/v1/maintenance/open-backup-folder")
    assert resp.status_code == 200
    assert resp.json() == {"opened": True, "path": str(external)}
    assert str(revealed["path"]) == str(external)


def test_open_backup_folder_requires_auth(env):
    app.dependency_overrides.clear()
    client = TestClient(app)
    assert client.post("/api/v1/maintenance/open-backup-folder").status_code == 401


def test_configured_backup_folder_missing_column_returns_none(older_rev_db):
    # Older schemas predate the backup_folder column; the pre-migration
    # snapshot read must fall back instead of raising — this is exactly the
    # upgrade that adds the column.
    from app.migrations import _configured_backup_folder

    assert _configured_backup_folder(older_rev_db) is None


def test_pre_migration_snapshot_honors_configured_folder(tmp_path, monkeypatch):
    from app import migrations

    db_path = tmp_path / "head.db"
    monkeypatch.setattr(app_settings, "database_url", f"sqlite:///{db_path}")
    run_migrations()  # head schema, including backup_folder

    external = tmp_path / "snapshot-target"
    external.mkdir()
    # Configure the folder on the migration-seeded settings row, and stamp an
    # older revision so the snapshot triggers; snapshot directly (running the
    # full upgrade against an already-head schema is not the point).
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE user_settings SET backup_folder = ? WHERE id = 1", (str(external),))
    conn.execute("UPDATE alembic_version SET version_num = ?", (EARLIER_REVISION,))
    conn.commit()
    conn.close()

    migrations._snapshot_before_migration(migrations._alembic_config())

    snaps = sorted(external.glob("pre-migration-*.db"))
    assert len(snaps) == 1
    assert EARLIER_REVISION in snaps[0].name
    assert not (db_path.parent / "backups").exists()


def test_pre_migration_snapshot_falls_back_when_folder_unavailable(tmp_path, monkeypatch):
    from app import migrations

    db_path = tmp_path / "head2.db"
    monkeypatch.setattr(app_settings, "database_url", f"sqlite:///{db_path}")
    run_migrations()

    blocker = tmp_path / "blocker.txt"
    blocker.write_text("not a directory")
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE user_settings SET backup_folder = ? WHERE id = 1", (str(blocker / "sub"),))
    conn.execute("UPDATE alembic_version SET version_num = ?", (EARLIER_REVISION,))
    conn.commit()
    conn.close()

    migrations._snapshot_before_migration(migrations._alembic_config())

    # An uncreatable configured folder must not block the snapshot — it lands
    # in the default backups/ folder beside the database instead.
    snaps = sorted((db_path.parent / "backups").glob("pre-migration-*.db"))
    assert len(snaps) == 1


# --- Data-safety failure modes (P5.8) ------------------------------------------


def test_startup_with_corrupt_db_raises_clear_error(tmp_path, monkeypatch):
    # A corrupt .db file (garbage where a SQLite header should be) must surface
    # as a clear RuntimeError pointing at recovery — not a raw DatabaseError
    # traceback (and, on desktop, a blank loader window).
    db_path = tmp_path / "corrupt.db"
    garbage = b"this is definitely not a SQLite database file\x00\x01\x02" * 8
    db_path.write_bytes(garbage)
    monkeypatch.setattr(app_settings, "database_url", f"sqlite:///{db_path}")

    with pytest.raises(RuntimeError) as excinfo:
        run_migrations()

    message = str(excinfo.value)
    assert str(db_path) in message
    assert "may be corrupted" in message
    assert str(db_path.parent / "backups") in message
    assert "pre-migration-*.db" in message

    # The corrupt file is never modified, moved, or deleted.
    assert db_path.exists()
    assert db_path.read_bytes() == garbage


def test_failed_migration_preserves_snapshot(older_rev_db, monkeypatch):
    # Build a DB at an earlier revision, then make the upgrade itself fail
    # mid-flight. The pre-migration snapshot (taken strictly before the upgrade)
    # must already exist, and the live DB's revision must be untouched. This is
    # the ordering regression guard for P0.3 — snapshot strictly before upgrade.
    pre_upgrade_bytes = older_rev_db.read_bytes()

    def boom(*_args, **_kwargs):
        raise sqlite3.DatabaseError("disk image is malformed")

    monkeypatch.setattr("alembic.command.upgrade", boom)

    with pytest.raises(RuntimeError):
        run_migrations()

    snaps = _pre_migration_snapshots(older_rev_db)
    assert len(snaps) == 1
    assert _revision_of(snaps[0]) == EARLIER_REVISION
    # The live DB never advanced past the earlier revision (upgrade failed)...
    assert _revision_of(older_rev_db) == EARLIER_REVISION
    # ...and was not mutated at all by the failed run.
    assert older_rev_db.read_bytes() == pre_upgrade_bytes
