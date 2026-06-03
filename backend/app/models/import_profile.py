from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Amount conventions for a single signed Amount column. ``signed`` keeps the
# column as-is (already correctly signed), ``charges_positive`` inverts it
# (purchases listed as positive), ``charges_negative`` keeps it (purchases
# listed as negative).
AMOUNT_CONVENTIONS: frozenset[str] = frozenset({"signed", "charges_positive", "charges_negative"})
PROFILE_SOURCE_TYPES: frozenset[str] = frozenset({"card", "checking"})


class ImportProfile(Base):
    """A saved per-bank column mapping + sign convention reusable across imports."""

    __tablename__ = "import_profiles"
    __table_args__ = (
        UniqueConstraint("name", name="uq_import_profiles_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="card")
    date_column: Mapped[int] = mapped_column(Integer, nullable=False)
    description_column: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_column: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    debit_column: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    credit_column: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    amount_convention: Mapped[str] = mapped_column(String(20), nullable=False, default="signed")
    ignored_payment_patterns: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
