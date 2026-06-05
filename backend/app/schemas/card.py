from datetime import date
from typing import Optional

from pydantic import BaseModel, field_validator


class CardOut(BaseModel):
    id: int
    name: str
    last4: Optional[str]
    statement_day: Optional[int]

    model_config = {"from_attributes": True}


class _CardFields(BaseModel):
    name: str
    last4: Optional[str] = None
    statement_day: Optional[int] = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Card name cannot be empty")
        if len(name) > 80:
            raise ValueError("Card name cannot exceed 80 characters")
        return name

    @field_validator("last4")
    @classmethod
    def _validate_last4(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        digits = value.strip()
        if not digits:
            return None
        if not digits.isdigit() or len(digits) > 4:
            raise ValueError("Last 4 must be up to 4 digits")
        return digits

    @field_validator("statement_day")
    @classmethod
    def _validate_statement_day(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        if value < 1 or value > 31:
            raise ValueError("Statement day must be between 1 and 31")
        return value


class CardCreate(_CardFields):
    pass


class CardUpdate(_CardFields):
    pass


class StatementSummary(BaseModel):
    card_id: int
    start_date: date
    end_date: date
    charges_cents: int
    payments_cents: int
    net_cents: int
    charge_count: int
    payment_count: int
