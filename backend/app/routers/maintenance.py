import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.user_settings import UserSettings
from app.services.maintenance_service import (
    backup_database,
    backups_dir,
    build_support_bundle,
    clear_license_token,
    database_path,
    license_status,
    list_disk_backups,
    restore_database,
    restore_from_disk,
    reveal_in_file_manager,
    update_check_status,
    write_backup_to_disk,
    write_license_token,
)


class RestoreFromDiskRequest(BaseModel):
    name: str


class LicenseTokenRequest(BaseModel):
    token: str

router = APIRouter(prefix="/maintenance", tags=["maintenance"])

MAX_RESTORE_BYTES = 500 * 1024 * 1024


def _engine(db: Session) -> Engine:
    bind = db.get_bind()
    if not isinstance(bind, Engine):
        bind = bind.engine  # Connection -> Engine
    return bind


def _timestamp_name() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


@router.get("/data-location")
def data_location(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Where the SQLite database lives — shown when the OS folder can't be opened."""
    return {"path": str(database_path(_engine(db)).parent)}


@router.post("/open-data-folder")
def open_data_folder(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reveal the data folder in the OS file manager (backend runs locally).

    Returns ``opened`` so the UI can fall back to displaying ``path`` if the
    launcher is unavailable (e.g. a headless environment).
    """
    folder = database_path(_engine(db)).parent
    return {"opened": reveal_in_file_manager(folder), "path": str(folder)}


@router.post("/open-backup-folder")
def open_backup_folder(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reveal the backup folder in the OS file manager.

    Distinct from the data folder: with a configured ``backup_folder`` the two
    differ, and the backup-saved toast must open where the file actually went.
    """
    folder = backups_dir(_engine(db))
    return {"opened": reveal_in_file_manager(folder), "path": str(folder)}


@router.get("/backup")
def download_backup(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = backup_database(_engine(db))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"centsmith-backup-{_timestamp_name()}.db"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/x-sqlite3",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/backup-to-disk")
def backup_to_disk(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Write a backup file locally and return its path (desktop save fallback)."""
    try:
        dest = write_backup_to_disk(_engine(db))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(dest)}


@router.get("/backups")
def list_backups(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Backups saved on disk (newest first) for one-click in-app restore."""
    return {"backups": list_disk_backups(_engine(db))}


@router.post("/restore-from-disk")
def restore_backup_from_disk(
    payload: RestoreFromDiskRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    engine = _engine(db)
    # Release this request's connection before the engine is disposed and the
    # underlying file is swapped (mirrors the upload-based restore).
    db.close()
    try:
        restore_from_disk(engine, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "restored", "message": "Data restored. Reload the app to see your restored data."}


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if file.size and file.size > MAX_RESTORE_BYTES:
        raise HTTPException(status_code=400, detail="Backup file is too large.")
    data = await file.read()
    if len(data) > MAX_RESTORE_BYTES:
        raise HTTPException(status_code=400, detail="Backup file is too large.")
    engine = _engine(db)
    # Release this request's connection before the engine is disposed and the
    # underlying file is swapped.
    db.close()
    try:
        restore_database(engine, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "restored", "message": "Data restored. Reload the app to see your restored data."}


@router.get("/license")
def get_license(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Whether an update license is stored, with a masked hint (never the token).

    Licensing moved off Tauri IPC to the local backend: the desktop webview is
    served from a remote origin where ``window.__TAURI__`` invoke is unreliable,
    so the token is read/written here and lands beside the database — the same
    file the Tauri updater reads as a bearer header.
    """
    return license_status(_engine(db))


@router.post("/license")
def set_license(
    payload: LicenseTokenRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store the pasted update license (blank clears it); returns masked status."""
    return write_license_token(_engine(db), payload.token)


@router.delete("/license")
def delete_license(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the stored update license; returns status."""
    return clear_license_token(_engine(db))


@router.get("/update-status")
def get_update_status(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Last auto-update check outcome, recorded by the desktop shell.

    The shell writes ``update-check.json`` beside the database after every
    check attempt (sanitized — never the license token); this surfaces it so
    Settings can show whether updates are flowing instead of failing silently.
    """
    return update_check_status(_engine(db))


@router.get("/support-bundle")
def download_support_bundle(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    obj = db.get(UserSettings, 1)
    settings_summary = {
        "personal_categories": list(obj.personal_categories) if obj else [],
        "hidden_pages": list(obj.hidden_pages) if obj else [],
    }
    data = build_support_bundle(_engine(db), settings_summary)
    filename = f"centsmith-support-{_timestamp_name()}.zip"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
