from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

from app.models.import_profile import AMOUNT_CONVENTIONS, PROFILE_SOURCE_TYPES


class ColumnMappingIn(BaseModel):
    """An explicit column assignment supplied with an import request.

    Column references are zero-based indices into the headers/sample rows the
    preview returned. Either ``amount_column`` or at least one of
    ``debit_column``/``credit_column`` must be present.
    """

    date_column: int
    description_column: int
    amount_column: Optional[int] = None
    debit_column: Optional[int] = None
    credit_column: Optional[int] = None
    amount_convention: str = "signed"

    @field_validator("date_column", "description_column", "amount_column", "debit_column", "credit_column")
    @classmethod
    def non_negative(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 0:
            raise ValueError("column index cannot be negative")
        return value

    @field_validator("amount_convention")
    @classmethod
    def known_convention(cls, value: str) -> str:
        if value not in AMOUNT_CONVENTIONS:
            raise ValueError(f"amount_convention must be one of {sorted(AMOUNT_CONVENTIONS)}")
        return value

    @model_validator(mode="after")
    def has_amount_source(self) -> "ColumnMappingIn":
        if self.amount_column is None and self.debit_column is None and self.credit_column is None:
            raise ValueError("an amount column or a debit/credit column is required")
        return self


class ImportProfileBase(BaseModel):
    name: str
    source_type: str = "card"
    date_column: int
    description_column: int
    amount_column: Optional[int] = None
    debit_column: Optional[int] = None
    credit_column: Optional[int] = None
    amount_convention: str = "signed"
    ignored_payment_patterns: list[str] = []

    @field_validator("name")
    @classmethod
    def non_empty_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name cannot be empty")
        if len(cleaned) > 80:
            raise ValueError("name cannot exceed 80 characters")
        return cleaned

    @field_validator("source_type")
    @classmethod
    def known_source(cls, value: str) -> str:
        if value not in PROFILE_SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {sorted(PROFILE_SOURCE_TYPES)}")
        return value

    @field_validator("amount_convention")
    @classmethod
    def known_convention(cls, value: str) -> str:
        if value not in AMOUNT_CONVENTIONS:
            raise ValueError(f"amount_convention must be one of {sorted(AMOUNT_CONVENTIONS)}")
        return value

    @model_validator(mode="after")
    def has_amount_source(self) -> "ImportProfileBase":
        if self.amount_column is None and self.debit_column is None and self.credit_column is None:
            raise ValueError("an amount column or a debit/credit column is required")
        return self


class ImportProfileCreate(ImportProfileBase):
    pass


class ImportProfileUpdate(ImportProfileBase):
    pass


class ImportProfileOut(BaseModel):
    id: int
    name: str
    source_type: str
    date_column: int
    description_column: int
    amount_column: Optional[int]
    debit_column: Optional[int]
    credit_column: Optional[int]
    amount_convention: str
    ignored_payment_patterns: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
