from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.schemas.reports import (
    DashboardMonth,
    DashboardSummary,
    MerchantSpend,
    SpendingByCategory,
    SpendingPoint,
    SpendingSummary,
)
from app.services import reporting_service
from app.services.transaction_rules import INCOME_CATEGORY, REIMBURSEMENT_CATEGORY

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _spending_summary(rows: list[tuple[str, str, int]], window: list[str]) -> SpendingSummary:
    """Map (month, category, cents) rows onto the SpendingSummary shape.

    Every month in the window gets a point — months with no rows contribute a
    $0 point rather than being skipped, and the per-month average divides by
    the full window length.
    """
    category_by_month: dict[str, list[tuple[str, int]]] = {}
    month_amounts: dict[str, int] = {}
    category_totals: dict[str, int] = {}
    for month, category, cents in rows:
        category_by_month.setdefault(month, []).append((category, cents))
        month_amounts[month] = month_amounts.get(month, 0) + cents
        category_totals[category] = category_totals.get(category, 0) + cents

    points = []
    for month in window:
        amount_cents = month_amounts.get(month, 0)
        month_rows = category_by_month.get(month, [])
        points.append(SpendingPoint(
            label=month,
            amount_cents=amount_cents,
            by_category=[
                SpendingByCategory(category_name=category, amount_cents=cents, percent=(cents / amount_cents * 100) if amount_cents else 0)
                for category, cents in sorted(month_rows, key=lambda row: row[1], reverse=True)
            ],
        ))
    total = sum(point.amount_cents for point in points)
    avg = round(total / len(points)) if points else 0
    by_category = [
        SpendingByCategory(category_name=category, amount_cents=cents, percent=(cents / total * 100) if total else 0)
        for category, cents in sorted(category_totals.items(), key=lambda row: row[1], reverse=True)
    ]
    return SpendingSummary(total_cents=total, average_per_month_cents=avg, points=points, by_category=by_category)


@router.get("/spending/personal", response_model=SpendingSummary)
def personal_spending(
    months: int = Query(12, ge=1, le=36),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Same calendar-month window as the dashboard, so the two "personal
    # spending, last N months" figures always cover the same months.
    window = reporting_service.activity_window(db, months)
    rows = reporting_service.category_breakdown(db, window)
    return _spending_summary(rows, window)


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    months: int = Query(12, ge=1, le=36),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    window = reporting_service.activity_window(db, months)
    personal_spend = reporting_service.monthly_personal_spend(db, window)
    work_spend = reporting_service.monthly_work_spend(db, window)
    income_by_month: dict[str, dict[str, int]] = {}
    for month, category, cents in reporting_service.monthly_income(db, window):
        income_by_month.setdefault(month, {})[category] = cents

    summary_months = [
        DashboardMonth(
            month=month,
            personal_cents=personal_spend.get(month, 0),
            work_cents=work_spend.get(month, 0),
            income_cents=income_by_month.get(month, {}).get(INCOME_CATEGORY, 0),
            reimbursement_cents=income_by_month.get(month, {}).get(REIMBURSEMENT_CATEGORY, 0),
        )
        for month in window
    ]
    personal_total = sum(m.personal_cents for m in summary_months)
    work_total = sum(m.work_cents for m in summary_months)
    income_total = sum(m.income_cents for m in summary_months)
    reimbursement_total = sum(m.reimbursement_cents for m in summary_months)

    uncategorized_income_cents, uncategorized_income_count = reporting_service.uncategorized_income(db)
    unexpensed_work_cents, unexpensed_work_count = reporting_service.unexpensed_work(db)
    top_merchants = [
        MerchantSpend(name=name, amount_cents=cents, count=count)
        for name, cents, count in reporting_service.top_merchants(db, window)
    ]

    latest_month = summary_months[-1].month if summary_months else None
    return DashboardSummary(
        personal_total_cents=personal_total,
        work_total_cents=work_total,
        unsorted_count=reporting_service.unsorted_count(db),
        latest_month=latest_month,
        months=summary_months,
        income_total_cents=income_total,
        reimbursement_total_cents=reimbursement_total,
        uncategorized_income_cents=uncategorized_income_cents,
        uncategorized_income_count=uncategorized_income_count,
        unexpensed_work_cents=unexpensed_work_cents,
        unexpensed_work_count=unexpensed_work_count,
        top_merchants=top_merchants,
    )


@router.get("/income/personal", response_model=SpendingSummary)
def personal_income(
    months: int = Query(12, ge=1, le=36),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Same calendar-month window as the dashboard; months in the window with
    # no income contribute a $0 point rather than being skipped.
    window = reporting_service.activity_window(db, months)
    rows = reporting_service.monthly_income(db, window, categories={INCOME_CATEGORY})
    return _spending_summary(rows, window)
