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
import subprocess
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


def reveal_in_file_manager(path: Path) -> bool:
    """Open a folder in the OS file manager from the local backend process.

    The desktop shell and the backend run on the same machine in the same user
    session, so the backend can reveal the data folder directly — this avoids
    relying on the Tauri webview's remote-origin IPC, which is unreliable for the
    backend-served page. Returns False (rather than raising) when the launcher is
    unavailable so the caller can fall back to just displaying the path.
    """
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606  (Windows-only)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception:
        return False


def backups_dir(engine: Engine) -> Path:
    """The ``backups/`` folder beside the database where on-disk backups live."""
    return database_path(engine).parent / "backups"


# Filename of the update-license token, kept beside the database. This is the
# SAME path the desktop shell's updater reads (``user_data_dir()/license.token``
# in Rust), because the database lives in that data dir — so writing it here from
# the local backend is what makes the token visible to the Tauri updater. The
# license commands moved from Tauri IPC to the backend because the webview's
# remote-origin IPC is unreliable (same reason as backup/open-data-folder).
LICENSE_FILE_NAME = "license.token"


def license_token_path(engine: Engine) -> Path:
    """Where the update-license token is stored (beside the database)."""
    return database_path(engine).parent / LICENSE_FILE_NAME


def _mask_token(token: str) -> str:
    """Mask a token to its last four characters (e.g. ``…AB12``) for display."""
    return "…" + token.strip()[-4:]


def read_license_token(engine: Engine) -> Optional[str]:
    """Return the stored license token, or None when absent/blank."""
    path = license_token_path(engine)
    try:
        trimmed = path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None
    return trimmed or None


def license_status(engine: Engine) -> dict:
    """Report whether a license is stored, with a masked hint for display.

    Never returns the full token — only ``present`` plus a masked tail, matching
    the desktop shell's old ``LicenseStatus`` shape the UI already expects.
    """
    token = read_license_token(engine)
    if token is None:
        return {"present": False, "hint": None}
    return {"present": True, "hint": _mask_token(token)}


def write_license_token(engine: Engine, token: str) -> dict:
    """Persist a license token (blank clears it, mirroring the shell) and return status."""
    trimmed = token.strip()
    if not trimmed:
        return clear_license_token(engine)
    license_token_path(engine).write_text(trimmed, encoding="utf-8")
    return license_status(engine)


def clear_license_token(engine: Engine) -> dict:
    """Remove the stored license token (idempotent) and return status."""
    license_token_path(engine).unlink(missing_ok=True)
    return license_status(engine)


def write_backup_to_disk(engine: Engine) -> Path:
    """Write a backup file into a ``backups/`` folder beside the database.

    The desktop shell can't reliably save a download (WebView2 ignores
    `<a download>` blob clicks and the webview's remote-origin IPC is
    unreliable), so the local backend writes the file itself and returns the
    path for the UI to display. Returns the full path to the created file.
    """
    folder = backups_dir(engine)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = folder / f"centsmith-backup-{stamp}.db"
    dest.write_bytes(backup_database(engine))
    return dest


def list_disk_backups(engine: Engine) -> list[dict]:
    """List ``.db`` backups in the backups folder, newest first.

    Each entry carries ``name`` (filename only), ``size_bytes`` and an ISO
    ``modified`` timestamp so the UI can offer one-click restore without the
    user navigating the filesystem.
    """
    folder = backups_dir(engine)
    if not folder.is_dir():
        return []
    entries = []
    for path in folder.glob("*.db"):
        if not path.is_file():
            continue
        stat = path.stat()
        entries.append(
            {
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }
        )
    entries.sort(key=lambda e: e["modified"], reverse=True)
    return entries


def restore_from_disk(engine: Engine, name: str) -> None:
    """Restore a backup that already lives in the backups folder, by filename.

    ``name`` must be a bare filename within the backups folder — any path
    traversal or missing file raises ValueError so a request can never read
    outside that directory.
    """
    folder = backups_dir(engine)
    candidate = (folder / name).resolve()
    if candidate.parent != folder.resolve() or not candidate.is_file():
        raise ValueError("That backup file was not found.")
    restore_database(engine, candidate.read_bytes())


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
