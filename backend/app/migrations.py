import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.exc import DatabaseError as SQLAlchemyDatabaseError

from app.config import settings

# How many pre-migration-*.db snapshots to keep in the backups folder.
PRE_MIGRATION_SNAPSHOT_KEEP = 3


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    backend_dir = _backend_dir()
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def _sqlite_file_path(database_url: str) -> Optional[Path]:
    """The on-disk file behind a ``sqlite:///`` URL, or None when not file-based."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return None
    raw = database_url[len(prefix):]
    if not raw or raw == ":memory:":
        return None
    return Path(raw)


def _stored_revision(db_file: Path) -> Optional[str]:
    """The alembic revision recorded in the DB file, or None when absent.

    Uses a direct sqlite3 connection rather than the app engine — this runs
    before the app is fully wired up at startup.
    """
    conn = sqlite3.connect(str(db_file))
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "alembic_version" not in tables:
            return None
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _configured_backup_folder(db_file: Path) -> Optional[Path]:
    """The user-configured backup folder from user_settings, or None.

    Read with a direct sqlite3 connection (this runs pre-engine at startup).
    Older databases without the column/table simply fall back to the default —
    notably the very upgrade that *adds* ``backup_folder`` runs through here.
    """
    conn = sqlite3.connect(str(db_file))
    try:
        try:
            row = conn.execute("SELECT backup_folder FROM user_settings WHERE id = 1").fetchone()
        except sqlite3.Error:
            return None
    finally:
        conn.close()
    if row and row[0] and str(row[0]).strip():
        return Path(str(row[0]).strip())
    return None


def _snapshot_before_migration(config: Config) -> None:
    """Snapshot the DB to ``backups/pre-migration-<rev>-<ts>.db`` before upgrading.

    Startup migrations run unconditionally against the user's only data copy
    (auto-update + first launch), so any upgrade that will actually change the
    schema first copies the database with the SQLite backup API. Fresh installs
    (no ``alembic_version`` table) and databases already at head skip the
    snapshot. Snapshots land in the same ``backups/`` folder the maintenance
    endpoints list, so one-click restore picks them up automatically. Only the
    newest ``PRE_MIGRATION_SNAPSHOT_KEEP`` snapshots are kept.
    """
    db_file = _sqlite_file_path(settings.database_url)
    if db_file is None or not db_file.exists():
        return
    revision = _stored_revision(db_file)
    if revision is None:
        return
    head = ScriptDirectory.from_config(config).get_current_head()
    if revision == head:
        return

    backups = _configured_backup_folder(db_file) or (db_file.parent / "backups")
    try:
        backups.mkdir(parents=True, exist_ok=True)
    except OSError:
        # A configured folder that can't be created (unplugged drive, revoked
        # permissions) must not block the snapshot — fall back to the default.
        backups = db_file.parent / "backups"
        backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    dest = backups / f"pre-migration-{revision}-{stamp}.db"
    src = sqlite3.connect(str(db_file))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    snapshots = sorted(
        backups.glob("pre-migration-*.db"),
        key=lambda p: (p.stat().st_mtime_ns, p.name),
        reverse=True,
    )
    for stale in snapshots[PRE_MIGRATION_SNAPSHOT_KEEP:]:
        stale.unlink(missing_ok=True)


def _corrupt_db_message(exc: Exception) -> str:
    """Build a recovery-pointing message for a DB that can't be read/upgraded.

    A corrupt SQLite file otherwise surfaces as a raw ``sqlite3.DatabaseError``
    (and, on desktop, a blank loader window — see P4.1). This names the file,
    states it may be corrupted, and points at the backups folder plus the
    automatic pre-migration snapshot so a user or support reading the log knows
    recovery exists. The corrupt file itself is never modified, moved, or
    deleted — only read.
    """
    db_file = _sqlite_file_path(settings.database_url)
    if db_file is None:
        db_path = settings.database_url
        backups = "<data-dir>/backups"
    else:
        db_path = str(db_file)
        # Safe even on a corrupt DB: _configured_backup_folder swallows
        # sqlite3 errors and falls back to None.
        backups = str(_configured_backup_folder(db_file) or (db_file.parent / "backups"))
    return (
        f"Could not open or upgrade the database at {db_path}: the database file "
        f"may be corrupted ({exc.__class__.__name__}: {exc}). The file was left "
        f"untouched. To recover, restore a recent backup from {backups} — "
        f"including any automatic pre-migration-*.db snapshot taken before the "
        f"last update."
    )


def run_migrations() -> None:
    # Assumes a single backend process owns the database — there is no
    # cross-process lock around Alembic's `upgrade`. Safe in desktop mode
    # because only the Tauri-spawned backend touches the SQLite file.
    config = _alembic_config()
    try:
        # Order matters: the snapshot is taken strictly before the upgrade, so a
        # mid-upgrade failure always leaves a pre-migration snapshot behind.
        _snapshot_before_migration(config)
        command.upgrade(config, "head")
    except (sqlite3.DatabaseError, SQLAlchemyDatabaseError) as exc:
        raise RuntimeError(_corrupt_db_message(exc)) from exc
