from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

CLASSIFICATION_VALUES = {"personal", "work"}


class Transaction(Base):
    __tablename__ = "transactions"
    # Indexes mirror the migration (0006); kept here so metadata-built test DBs
    # match. They cover the hot filters/sorts: date range + classification,
    # category, expensed status, and import-batch lookups.
    __table_args__ = (
        UniqueConstraint("source_hash", name="uq_transactions_source_hash"),
        Index("ix_transactions_transaction_date", "transaction_date"),
        Index("ix_transactions_classification_date", "classification", "transaction_date"),
        Index("ix_transactions_personal_category_date", "personal_category", "transaction_date"),
        Index("ix_transactions_expensed", "classification", "expensed"),
        Index("ix_transactions_import_batch_id", "import_batch_id"),
        Index("ix_transactions_card_id", "card_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(10), nullable=False)  # debit | credit
    classification: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # personal | work | null
    personal_category: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    expensed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    statement_format: Mapped[Optional[str]] = mapped_column(String(80))
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    import_batch_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    card_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("cards.id", ondelete="SET NULL"), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
