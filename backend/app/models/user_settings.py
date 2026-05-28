from datetime import datetime, timezone
from sqlalchemy import DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

DEFAULT_CATEGORIES: list[str] = [
    "Groceries", "Dining", "Transportation", "Home", "Health",
    "Subscriptions", "Shopping", "Travel", "Entertainment",
    "Personal Care", "Gifts", "Other", "Transfer", "Income", "Reimbursement",
]

SYSTEM_CATEGORIES: frozenset[str] = frozenset({"Income", "Reimbursement", "Transfer"})


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)  # always 1 (single-user app)
    personal_categories: Mapped[list] = mapped_column(JSON, nullable=False)
    hidden_pages: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
