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


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    skip: int
    limit: int
    has_more: bool
    next_skip: Optional[int] = None


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


class SkippedRowOut(BaseModel):
    row_number: int
    raw_date: str
    raw_amount: str
    raw_description: str
    reason_code: str
    message: str


class ImportPreview(BaseModel):
    rows: list[ImportPreviewRow]
    total: int
    duplicates: int
    ignored_credits: int
    to_import: int
    statement_format: str
    skipped_errors: int = 0
    # True when the file used a single signed Amount column on a card statement,
    # so the charges-positive vs charges-negative convention can be toggled.
    amount_sign_adjustable: bool = False
    # The sign convention applied to this preview (True => charges shown positive).
    charges_positive: bool = False
    # Per-row reasons rows were skipped, so the user can see what went wrong.
    skipped_rows: list[SkippedRowOut] = []
    # Set when auto-detection failed and the user must map columns manually.
    mapping_required: bool = False
    available_columns: list[str] = []
    sample_rows: list[list[str]] = []
    detected_columns: dict[str, Optional[int]] = {}


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


class MerchantSpend(BaseModel):
    name: str
    amount_cents: int
    count: int


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
    unexpensed_work_cents: int = 0
    unexpensed_work_count: int = 0
    top_merchants: list[MerchantSpend] = []
