from datetime import datetime, date
from typing import Literal, Optional
from pydantic import BaseModel, field_validator

Classification = Literal["personal", "work"]
TransactionType = Literal["debit", "credit"]


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str

    model_config = {"from_attributes": True}


class TransactionOut(BaseModel):
    id: int
    transaction_date: date
    description: str
    amount_cents: int
    transaction_type: TransactionType
    classification: Optional[Classification]
    personal_category: Optional[str]
    expensed: bool
    is_manual: bool
    statement_format: Optional[str]
    imported_at: datetime

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    transaction_date: date
    description: str
    amount_cents: int
    transaction_type: TransactionType
    classification: Optional[Classification] = None
    personal_category: Optional[str] = None
    expensed: bool = False


class TransactionUpdate(BaseModel):
    classification: Optional[Classification] = None
    personal_category: Optional[str] = None
    description: Optional[str] = None
    transaction_date: Optional[date] = None
    expensed: Optional[bool] = None


class BulkClassifyRequest(BaseModel):
    transaction_ids: list[int]
    classification: Classification

    @field_validator("transaction_ids")
    @classmethod
    def validate_ids(cls, value: list[int]) -> list[int]:
        ids = sorted(set(value))
        if not ids:
            raise ValueError("transaction_ids cannot be empty")
        if len(ids) > 500:
            raise ValueError("cannot update more than 500 transactions at once")
        return ids


class BulkClassifyResult(BaseModel):
    updated: int


class BulkCategorizeRequest(BaseModel):
    transaction_ids: list[int]
    personal_category: str

    @field_validator("transaction_ids")
    @classmethod
    def validate_ids(cls, value: list[int]) -> list[int]:
        ids = sorted(set(value))
        if not ids:
            raise ValueError("transaction_ids cannot be empty")
        if len(ids) > 500:
            raise ValueError("cannot update more than 500 transactions at once")
        return ids

    @field_validator("personal_category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        category = value.strip()
        if not category:
            raise ValueError("personal_category cannot be empty")
        if len(category) > 80:
            raise ValueError("personal_category cannot exceed 80 characters")
        return category


class BulkCategorizeResult(BaseModel):
    updated: int


class ImportPreviewRow(BaseModel):
    row_number: int
    date: date
    description: str
    amount_cents: int
    transaction_type: TransactionType
    is_duplicate: bool


class ImportPreview(BaseModel):
    rows: list[ImportPreviewRow]
    total: int
    duplicates: int
    ignored_credits: int
    to_import: int
    statement_format: str
    skipped_errors: int = 0


class ImportResult(BaseModel):
    imported: int
    skipped: int
    ignored_credits: int
    skipped_errors: int = 0
    batch_id: Optional[str] = None


class ImportBatchOut(BaseModel):
    id: str
    filename: str
    statement_format: Optional[str]
    imported_at: datetime
    row_count: int
    created_by_action: str

    model_config = {"from_attributes": True}


class ImportBatchDeleteResult(BaseModel):
    removed_rows: int
    classified_rows: int
    categorized_rows: int


class SpendingPoint(BaseModel):
    label: str
    amount_cents: int
    by_category: list["SpendingByCategory"] = []


class SpendingByCategory(BaseModel):
    category_name: str
    amount_cents: int
    percent: float


class SpendingSummary(BaseModel):
    total_cents: int
    average_per_month_cents: int
    points: list[SpendingPoint]
    by_category: list[SpendingByCategory]


class DashboardMonth(BaseModel):
    month: str
    personal_cents: int
    work_cents: int
    income_cents: int = 0
    reimbursement_cents: int = 0


class DashboardSummary(BaseModel):
    personal_total_cents: int
    work_total_cents: int
    unsorted_count: int
    latest_month: Optional[str]
    months: list[DashboardMonth]
    income_total_cents: int = 0
    reimbursement_total_cents: int = 0
    uncategorized_income_cents: int = 0
    uncategorized_income_count: int = 0
