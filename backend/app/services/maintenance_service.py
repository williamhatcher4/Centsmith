"""Backup / restore / support-bundle helpers for the local SQLite database.

All of this is intentionally local-only. Backups use the SQLite online backup
API so they stay consistent even while the app holds the database open. The
support bundle is built to be safe to share: it excludes the database file,
transaction rows, secrets, and log lines that look like they carry credentials.
"""

import io
import json
import os
import platform
import re
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.migrations import run_migrations

# Foundational tables present in every Centsmith database since the initial
# migration (0001). ``users`` is auth-critical and intentionally required: a
# backup whose alembic_version claims it is at head would NOT have these
# recreated by migrations, so a missing core table must be rejected up front.
# Later-added tables (user_settings, import_batches, import_profiles) are
# deliberately excluded so genuinely older backups still validate and get
# brought up to schema by the restore migration step.
REQUIRED_TABLES = {"alembic_version", "transactions", "users"}
SUPPORT_LOG_TAIL_LINES = 500

# Log lines mentioning any of these get redacted before entering a support
# bundle, belt-and-suspenders on top of never writing secrets to the log.
_SECRET_LINE_RE = re.compile(
    r"(secret|token|password|passwd|authorization|cookie|api[_-]?key|private[_-]?key|dpapi)",
    re.IGNORECASE,
)


def _app_version() -> str:
    try:
        return version("centsmith")
    except PackageNotFoundError:
        return "unknown"


def database_path(engine: Engine) -> Path:
    """Resolve the on-disk SQLite file path backing an engine."""
    db = engine.url.database
    if not db or db == ":memory:":
        raise ValueError("Backups require a file-based SQLite database")
    return Path(db)


def backup_database(engine: Engine) -> bytes:
    """Return a consistent snapshot of the database as bytes (SQLite backup API)."""
    src_path = database_path(engine)
    with tempfile.TemporaryDirectory() as tmp:
        dest_path = Path(tmp) / "backup.db"
        src = sqlite3.connect(str(src_path))
        try:
            dest = sqlite3.connect(str(dest_path))
            try:
                src.backup(dest)
            finally:
                dest.close()
        finally:
            src.close()
        return dest_path.read_bytes()


def validate_sqlite_backup(data: bytes) -> None:
    """Raise ValueError unless ``data`` is a valid Centsmith SQLite database."""
    if not data:
        raise ValueError("The uploaded file is empty.")
    # SQLite files start with this 16-byte magic header.
    if not data.startswith(b"SQLite format 3\x00"):
        raise ValueError("That file is not a SQLite database backup.")
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / "candidate.db"
        candidate.write_bytes(data)
        conn = sqlite3.connect(str(candidate))
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise ValueError("The backup file failed an integrity check.")
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = REQUIRED_TABLES - tables
            if missing:
                raise ValueError("The backup is missing required Centsmith tables.")
        finally:
            conn.close()


def restore_database(engine: Engine, data: bytes) -> None:
    """Validate and swap in an uploaded backup, migrating it to the current schema.

    Disposes the engine's connections, keeps a rollback copy of the current
    database, overwrites the live file, then runs migrations. On any failure the
    previous database is restored so the app is never left broken.
    """
    validate_sqlite_backup(data)
    target = database_path(engine)
    rollback = target.with_suffix(target.suffix + ".rollback")

    # Snapshot the current DB for rollback, then release file handles.
    current = backup_database(engine)
    engine.dispose()
    rollback.write_bytes(current)

    try:
        target.write_bytes(data)
        # Bring an older backup up to the current schema.
        run_migrations()
    except Exception as exc:
        # Roll back to the pre-restore database and surface a safe error.
        try:
            engine.dispose()
            target.write_bytes(rollback.read_bytes())
        finally:
            _safe_unlink(rollback)
        raise ValueError("Restore failed and the previous data was kept.") from exc

    _safe_unlink(rollback)


def _safe_unlink(path: Path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _user_data_dir() -> Optional[Path]:
    # Mirror app.config without importing its private helper; only used to find logs.
    try:
        from app.config import _user_data_dir as cfg_user_data_dir

        return cfg_user_data_dir()
    except Exception:
        return None


def _sanitized_log_tail(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    tail = lines[-SUPPORT_LOG_TAIL_LINES:]
    return "\n".join("[redacted]" if _SECRET_LINE_RE.search(line) else line for line in tail)


def _alembic_revision(engine: Engine) -> Optional[str]:
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _db_health(engine: Engine) -> str:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


def build_support_bundle(engine: Engine, settings_summary: dict) -> bytes:
    """Build a shareable diagnostics zip with no secrets or financial row data.

    Includes app/OS/migration/health metadata, a non-financial settings summary
    (category names + page visibility), and a sanitized tail of the shell log.
    Explicitly excludes the database file, transaction rows, and credentials.
    """
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_version": _app_version(),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "alembic_revision": _alembic_revision(engine),
        "database_health": _db_health(engine),
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps(metadata, indent=2))
        zf.writestr("settings-summary.json", json.dumps(settings_summary, indent=2))
        data_dir = _user_data_dir()
        if data_dir is not None:
            log_path = data_dir / "shell.log"
            if log_path.exists():
                zf.writestr("logs/shell.log", _sanitized_log_tail(log_path))
    return buffer.getvalue()
