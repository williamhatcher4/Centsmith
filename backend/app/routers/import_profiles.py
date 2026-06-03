from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.import_profile import ImportProfile
from app.models.user import User
from app.schemas.import_profile import (
    ImportProfileCreate,
    ImportProfileOut,
    ImportProfileUpdate,
)

router = APIRouter(prefix="/import-profiles", tags=["import-profiles"])


def _name_taken(db: Session, name: str, exclude_id: int | None = None) -> bool:
    q = db.query(ImportProfile).filter(ImportProfile.name == name)
    if exclude_id is not None:
        q = q.filter(ImportProfile.id != exclude_id)
    return db.query(q.exists()).scalar()


@router.get("", response_model=list[ImportProfileOut])
def list_import_profiles(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(ImportProfile).order_by(ImportProfile.name.asc()).all()


@router.post("", response_model=ImportProfileOut, status_code=status.HTTP_201_CREATED)
def create_import_profile(
    payload: ImportProfileCreate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if _name_taken(db, payload.name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A profile with that name already exists")
    profile = ImportProfile(**payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/{profile_id}", response_model=ImportProfileOut)
def update_import_profile(
    profile_id: int,
    payload: ImportProfileUpdate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.get(ImportProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import profile not found")
    if _name_taken(db, payload.name, exclude_id=profile_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A profile with that name already exists")
    for field, value in payload.model_dump().items():
        setattr(profile, field, value)
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_import_profile(
    profile_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.get(ImportProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import profile not found")
    db.delete(profile)
    db.commit()
