from datetime import datetime, date
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

Classification = Literal["personal", "work"]
TransactionType = Literal["debit", "credit"]

MAX_DESCRIPTION_LENGTH = 255


def _clean_description(value: str) -> str:
    """Trim a description and enforce the 1..255 length the DB column declares.

    SQLite ignores ``String(255)``, so the cap has to be enforced here — the
    React form validates too, but the API is the real boundary.
    """
    description = value.strip()
    if not description:
        raise ValueError("description cannot be empty")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(f"description cannot exceed {MAX_DESCRIPTION_LENGTH} characters")
    return description


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
    card_id: Optional[int]
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
    # Mirrors transaction_rules.validate_amount as a Field constraint so the
    # bound shows up in the OpenAPI schema (exclusiveMinimum).
    amount_cents: int = Field(gt=0)
    transaction_type: TransactionType
    classification: Optional[Classification] = None
    personal_category: Optional[str] = None
    expensed: bool = False

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return _clean_description(value)


class TransactionUpdate(BaseModel):
    classification: Optional[Classification] = None
    personal_category: Optional[str] = None
    description: Optional[str] = None
    transaction_date: Optional[date] = None
    expensed: Optional[bool] = None
    card_id: Optional[int] = None
    # Editable only on manual rows (the router enforces is_manual); imported
    # rows stay immutable to protect source_hash dedup and statement fidelity.
    amount_cents: Optional[int] = Field(None, gt=0)
    transaction_type: Optional[TransactionType] = None

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _clean_description(value)


class BulkAssignCardRequest(BaseModel):
    transaction_ids: list[int]
    card_id: Optional[int] = None

    @field_validator("transaction_ids")
    @classmethod
    def validate_ids(cls, value: list[int]) -> list[int]:
        ids = sorted(set(value))
        if not ids:
            raise ValueError("transaction_ids cannot be empty")
        if len(ids) > 500:
            raise ValueError("cannot update more than 500 transactions at once")
        return ids


class BulkAssignCardResult(BaseModel):
    updated: int


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
