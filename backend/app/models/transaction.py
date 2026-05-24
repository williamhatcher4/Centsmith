from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

CLASSIFICATION_VALUES = {"personal", "work"}


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("source_hash", name="uq_transactions_source_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(10), nullable=False)  # debit | credit
    classification: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # personal | work | null
    personal_category: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    expensed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    statement_format: Mapped[Optional[str]] = mapped_column(String(80))
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
