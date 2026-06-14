from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
# Canonical definitions live in transaction_rules; re-exported here because the
# category lists predate that module and existing imports point at the model.
from app.services.transaction_rules import DEFAULT_CATEGORIES, SYSTEM_CATEGORIES

__all__ = ["UserSettings", "DEFAULT_CATEGORIES", "SYSTEM_CATEGORIES"]


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)  # always 1 (single-user app)
    personal_categories: Mapped[list] = mapped_column(JSON, nullable=False)
    hidden_pages: Mapped[list] = mapped_column(JSON, nullable=False)
    # Optional custom backup destination; NULL means backups/ beside the DB.
    backup_folder: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
