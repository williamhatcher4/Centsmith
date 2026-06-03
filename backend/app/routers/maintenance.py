import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.user_settings import UserSettings
from app.services.maintenance_service import (
    backup_database,
    build_support_bundle,
    database_path,
    restore_database,
)

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
