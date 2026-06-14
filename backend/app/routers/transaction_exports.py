import csv
import io
from datetime import datetime, timezone, date
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models.transaction import Transaction
from app.models.user import User
from app.services.transaction_rules import TRANSFER_CATEGORY

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _export_rows(db: Session, classification: Literal["personal", "work"], start_date: Optional[date], end_date: Optional[date]):
    # Select only the columns the CSV needs instead of hydrating full ORM
    # Transaction objects — on large ledgers (tens of thousands of rows) ORM
    # instance construction dominates the export time.
    # Credits (income, refunds, reimbursements) are included — an export is the
    # complete record for taxes/accountants (maintainer decision 2026-06-09).
    # The signed Amount column and the Type column keep them distinguishable.
    q = db.query(
        Transaction.transaction_date,
        Transaction.description,
        Transaction.classification,
        Transaction.transaction_type,
        Transaction.amount_cents,
        Transaction.expensed,
        Transaction.personal_category,
    ).filter(
        Transaction.classification == classification,
    )
    if classification == "personal":
        q = q.filter(func.coalesce(Transaction.personal_category, "") != TRANSFER_CATEGORY)
    if start_date:
        q = q.filter(Transaction.transaction_date >= start_date)
    if end_date:
        q = q.filter(Transaction.transaction_date <= end_date)
    return q.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).all()


@router.get("/export/{classification}")
def export_transactions(
    classification: Literal["personal", "work"],
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    output = io.StringIO()
    writer = csv.writer(output)
    header = ["Date", "Description", "Classification", "Type", "Amount"]
    if classification == "work":
        header.append("Expensed")
    else:
        header.append("Category")
    writer.writerow(header)
    for tx in _export_rows(db, classification, start_date, end_date):
        sign = 1 if tx.transaction_type == "credit" else -1
        row = [
            tx.transaction_date.isoformat(),
            tx.description,
            tx.classification,
            tx.transaction_type,
            f"{sign * tx.amount_cents / 100:.2f}",
        ]
        if classification == "work":
            row.append("yes" if tx.expensed else "no")
        else:
            row.append(tx.personal_category or "")
        writer.writerow(row)
    output.seek(0)
    filename = f"{classification}_transactions_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})
