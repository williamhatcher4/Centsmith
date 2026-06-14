from typing import Optional
from pydantic import BaseModel


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
