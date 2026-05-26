"""Seed a deterministic test user for the Playwright e2e suite.

Reads DATABASE_URL, E2E_USERNAME, and E2E_PASSWORD from the environment.
Idempotent: re-running keeps the existing user with the same password.
"""
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.migrations import run_migrations
from app.models.user import User
from app.services.auth_service import hash_password


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    username = os.environ.get("E2E_USERNAME", "e2e_user")
    password = os.environ.get("E2E_PASSWORD", "e2e_password")
    if not db_url:
        sys.stderr.write("DATABASE_URL must be set to seed the e2e user.\n")
        return 1

    os.environ["DATABASE_URL"] = db_url
    run_migrations()

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            existing.hashed_password = hash_password(password)
        else:
            db.add(User(username=username, display_name="E2E User", hashed_password=hash_password(password)))
        db.commit()
    finally:
        db.close()
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
