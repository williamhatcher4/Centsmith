import secrets

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.config import settings
from app.database import SessionLocal
from app.models.user import User

LOCAL_USER_USERNAME = "local"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_local_user(db: Session) -> User:
    if not settings.desktop_mode:
        raise RuntimeError("ensure_local_user is only valid in desktop mode")
    user = db.query(User).filter(User.username == LOCAL_USER_USERNAME).first()
    if user:
        return user
    from app.services.auth_service import hash_password
    user = User(
        username=LOCAL_USER_USERNAME,
        display_name="Local",
        hashed_password=hash_password(secrets.token_urlsafe(32)),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
