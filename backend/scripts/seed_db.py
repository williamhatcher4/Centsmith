import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models.user import User
from app.models.transaction import Transaction  # noqa: F401
from app.services.auth_service import hash_password


def seed():
    Base.metadata.create_all(bind=engine)

    if settings.desktop_mode:
        print("Desktop mode: skipping admin seed; local user is provisioned on first request.")
        return

    username = (settings.admin_username or "").strip()
    password = settings.admin_password or ""
    if not username or not password:
        print(
            "ERROR: ADMIN_USERNAME and ADMIN_PASSWORD must be set in backend/.env "
            "before first run. See README.md for setup instructions.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            db.add(User(
                username=username,
                display_name=username,
                hashed_password=hash_password(password),
            ))
            db.commit()
            print(f"Created user {username}")
        else:
            print(f"User {username} already exists")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
