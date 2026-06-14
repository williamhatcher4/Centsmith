from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel

from app.schemas.transaction import TransactionType


class ImportPreviewRow(BaseModel):
    row_number: int
    date: date
    description: str
    amount_cents: int
    transaction_type: TransactionType
    is_duplicate: bool
    # True for credit rows that are filtered out of the import (card payments or
    # user ignore patterns); shown in the preview so the user can see what's excluded.
    is_ignored_credit: bool = False


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
    # True when the file's numeric dates are MM/DD vs DD/MM ambiguous, so the
    # day-first convention can be toggled (mirrors amount_sign_adjustable).
    date_convention_adjustable: bool = False
    # The date convention applied to this preview (True => dates read day-first).
    day_first: bool = False
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
