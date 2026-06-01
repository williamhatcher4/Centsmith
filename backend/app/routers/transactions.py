import csv
import io
import re
import uuid
from datetime import datetime, timezone, date
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models.import_batch import ImportBatch
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import (
    BulkCategorizeRequest,
    BulkCategorizeResult,
    BulkClassifyRequest,
    BulkClassifyResult,
    DashboardMonth,
    DashboardSummary,
    ImportPreview,
    ImportResult,
    MerchantSpend,
    SpendingByCategory,
    SpendingPoint,
    SpendingSummary,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.services.transaction_import_service import (
    confirm_import as confirm_statement_import,
    preview_import as preview_statement_import,
    read_limited_upload,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

INCOME_CATEGORIES = {"Income", "Reimbursement"}
TRANSFER_CATEGORY = "Transfer"


def _base_query(db: Session):
    return db.query(Transaction).filter(Transaction.transaction_type == "debit")


def _personal_signed_amount():
    return case(
        (Transaction.transaction_type == "debit", Transaction.amount_cents),
        else_=-Transaction.amount_cents,
    )


def _personal_spending_filters():
    return [
        Transaction.classification == "personal",
        func.coalesce(Transaction.personal_category, "") != TRANSFER_CATEGORY,
        ~(
            (Transaction.transaction_type == "credit")
            & (Transaction.personal_category.in_(list(INCOME_CATEGORIES)))
        ),
    ]


# Merchant-name normalization for the dashboard "Top merchants" rollup.
# SQLite string munging is brittle, so this is done in Python after fetching rows.
_STORE_NUM_RE = re.compile(r"#\s*\d+")
_MASKED_REF_RE = re.compile(r"\bX{2,}\d*\b", re.IGNORECASE)
_DATE_FRAG_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_TRAILING_REF_RE = re.compile(r"\d{3,}$")


def _normalize_merchant(description: Optional[str]) -> str:
    """Collapse a raw bank description into a stable merchant key.

    Uppercases, strips store numbers (``#1234``), masked card refs (``XXXX1234``),
    embedded date fragments, and a trailing all-numeric auth/store code so that
    e.g. ``STARBUCKS #1234`` and ``STARBUCKS #5678`` group together.
    """
    if not description:
        return ""
    text = description.upper()
    text = _STORE_NUM_RE.sub(" ", text)
    text = _MASKED_REF_RE.sub(" ", text)
    text = _DATE_FRAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = text.split(" ")
    # Drop a trailing reference/auth number left on the tail (e.g. "AMAZON 1234567").
    while len(parts) > 1 and _TRAILING_REF_RE.search(parts[-1]) and not any(c.isalpha() for c in parts[-1]):
        parts.pop()
    return " ".join(parts).strip()


def _validate_personal_category(category: Optional[str], tx_type: str) -> None:
    if category is None or category == TRANSFER_CATEGORY:
        return
    if category in INCOME_CATEGORIES and tx_type != "credit":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Income/Reimbursement categories only apply to credit transactions",
        )


@router.post("/manual", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_manual_transaction(
    payload: TransactionCreate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.personal_category is not None:
        payload.personal_category = payload.personal_category.strip() or None
    if payload.personal_category:
        _validate_personal_category(payload.personal_category, payload.transaction_type)
    if payload.expensed and payload.classification != "work":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only work transactions can be marked as expensed")
    if payload.personal_category and payload.classification != "personal":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only personal transactions can have a personal category")
    tx = Transaction(
        transaction_date=payload.transaction_date,
        description=payload.description,
        amount_cents=payload.amount_cents,
        transaction_type=payload.transaction_type,
        classification=payload.classification,
        personal_category=payload.personal_category,
        expensed=payload.expensed,
        is_manual=True,
        statement_format=None,
        source_hash=f"manual:{uuid.uuid4()}",
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.delete("/{tx_id}", response_model=TransactionOut)
def delete_transaction(
    tx_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    batch_id = tx.import_batch_id
    db.delete(tx)
    db.flush()
    if batch_id:
        remaining = db.query(Transaction).filter(Transaction.import_batch_id == batch_id).count()
        batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
        if batch:
            if remaining:
                batch.row_count = remaining
            else:
                db.delete(batch)
    db.commit()
    return tx


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    classification: Optional[Literal["personal", "work", "unsorted"]] = Query(None),
    personal_category: Optional[str] = Query(None, max_length=80),
    expensed: Optional[bool] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if personal_category or classification in {"unsorted", "personal", "work"}:
        q = db.query(Transaction)
    else:
        q = _base_query(db)
    if classification == "unsorted":
        q = q.filter(Transaction.classification.is_(None))
    elif classification in {"personal", "work"}:
        q = q.filter(Transaction.classification == classification)
    if personal_category == "uncategorized":
        q = q.filter(Transaction.classification == "personal", Transaction.personal_category.is_(None))
    elif personal_category:
        q = q.filter(Transaction.classification == "personal", Transaction.personal_category == personal_category)
    if expensed is not None:
        q = q.filter(Transaction.classification == "work", Transaction.expensed.is_(expensed))
    if start_date:
        q = q.filter(Transaction.transaction_date >= start_date)
    if end_date:
        q = q.filter(Transaction.transaction_date <= end_date)
    if classification == "work":
        q = q.order_by(Transaction.expensed.asc())
    return q.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).offset(skip).limit(limit).all()


@router.post("/import/preview", response_model=ImportPreview)
async def preview_import(
    file: UploadFile = File(...),
    charges_positive: Optional[bool] = Form(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        raw = await read_limited_upload(file)
        return preview_statement_import(db, raw, file.filename or "statement.csv", "card", charges_positive)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import/confirm", response_model=ImportResult)
async def confirm_import(
    file: UploadFile = File(...),
    charges_positive: Optional[bool] = Form(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        raw = await read_limited_upload(file)
        return confirm_statement_import(db, raw, file.filename or "statement.csv", "card", charges_positive)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import/checking/preview", response_model=ImportPreview)
async def preview_checking_import(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        raw = await read_limited_upload(file)
        return preview_statement_import(db, raw, file.filename or "checking.csv", "checking")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import/checking/confirm", response_model=ImportResult)
async def confirm_checking_import(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        raw = await read_limited_upload(file)
        return confirm_statement_import(db, raw, file.filename or "checking.csv", "checking")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/bulk-classify", response_model=BulkClassifyResult)
def bulk_classify(
    payload: BulkClassifyRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txs = db.query(Transaction).filter(Transaction.id.in_(payload.transaction_ids)).all()
    if len(txs) != len(set(payload.transaction_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more transactions were not found")
    for tx in txs:
        tx.classification = payload.classification
        if payload.classification != "work":
            tx.expensed = False
        if payload.classification != "personal":
            tx.personal_category = None
        tx.updated_at = datetime.now(timezone.utc)
    db.commit()
    return BulkClassifyResult(updated=len(txs))


@router.post("/bulk-categorize-personal", response_model=BulkCategorizeResult)
def bulk_categorize_personal(
    payload: BulkCategorizeRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txs = db.query(Transaction).filter(Transaction.id.in_(payload.transaction_ids)).all()
    if len(txs) != len(set(payload.transaction_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more transactions were not found")
    not_personal = [tx.id for tx in txs if tx.classification != "personal"]
    if not_personal:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only personal transactions can be categorized")
    if payload.personal_category in INCOME_CATEGORIES:
        mismatched = [tx.id for tx in txs if tx.transaction_type != "credit"]
        if mismatched:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Income/Reimbursement categories only apply to credit transactions",
            )
    for tx in txs:
        tx.personal_category = payload.personal_category
        tx.updated_at = datetime.now(timezone.utc)
    db.commit()
    return BulkCategorizeResult(updated=len(txs))


@router.put("/{tx_id}", response_model=TransactionOut)
def update_transaction(
    tx_id: int,
    payload: TransactionUpdate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("expensed") and updates.get("classification", tx.classification) != "work":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only work transactions can be marked as expensed")
    next_classification = updates.get("classification", tx.classification)
    if updates.get("personal_category") and next_classification != "personal":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only personal transactions can have a personal category")
    if "personal_category" in updates and updates["personal_category"] is not None:
        updates["personal_category"] = updates["personal_category"].strip()
        if not updates["personal_category"]:
            updates["personal_category"] = None
        else:
            _validate_personal_category(updates["personal_category"], tx.transaction_type)
    if updates.get("classification") != "work" and (updates.get("classification") is not None or tx.classification != "work"):
        updates["expensed"] = False
    if next_classification != "personal":
        updates["personal_category"] = None
    for field, value in updates.items():
        setattr(tx, field, value)
    tx.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tx)
    return tx


def _export_rows(db: Session, classification: Literal["personal", "work"], start_date: Optional[date], end_date: Optional[date]):
    q = db.query(Transaction).filter(
        Transaction.classification == classification,
        Transaction.transaction_type == "debit",
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
        writer.writerow(row)
    output.seek(0)
    filename = f"{classification}_transactions_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/spending/personal", response_model=SpendingSummary)
def personal_spending(
    months: int = Query(12, ge=1, le=36),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    signed = _personal_signed_amount()
    common_filters = _personal_spending_filters()
    month_rows = db.query(
        func.strftime("%Y-%m", Transaction.transaction_date).label("month"),
        func.sum(signed).label("amount"),
    ).filter(*common_filters).group_by("month").order_by("month").all()
    selected_months = [month for month, _ in month_rows][-months:]

    category_rows = []
    if selected_months:
        category_rows = db.query(
            func.strftime("%Y-%m", Transaction.transaction_date).label("month"),
            func.coalesce(Transaction.personal_category, "Uncategorized").label("category"),
            func.sum(signed).label("amount"),
        ).filter(
            *common_filters,
            func.strftime("%Y-%m", Transaction.transaction_date).in_(selected_months),
        ).group_by("month", "category").order_by("month", "category").all()

    category_by_month: dict[str, list[tuple[str, int]]] = {}
    category_totals: dict[str, int] = {}
    for month, category, amount in category_rows:
        cents = int(amount or 0)
        category_by_month.setdefault(month, []).append((category, cents))
        category_totals[category] = category_totals.get(category, 0) + cents

    points = []
    for month, amount in month_rows[-months:]:
        amount_cents = int(amount or 0)
        rows = category_by_month.get(month, [])
        points.append(SpendingPoint(
            label=month,
            amount_cents=amount_cents,
            by_category=[
                SpendingByCategory(category_name=category, amount_cents=cents, percent=(cents / amount_cents * 100) if amount_cents else 0)
                for category, cents in sorted(rows, key=lambda row: row[1], reverse=True)
            ],
        ))
    total = sum(point.amount_cents for point in points)
    avg = round(total / len(points)) if points else 0
    by_category = [
        SpendingByCategory(category_name=category, amount_cents=cents, percent=(cents / total * 100) if total else 0)
        for category, cents in sorted(category_totals.items(), key=lambda row: row[1], reverse=True)
    ]
    return SpendingSummary(total_cents=total, average_per_month_cents=avg, points=points, by_category=by_category)


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    months: int = Query(12, ge=1, le=36),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    personal_spend_rows = db.query(
        func.strftime("%Y-%m", Transaction.transaction_date).label("month"),
        func.sum(_personal_signed_amount()).label("amount"),
    ).filter(*_personal_spending_filters()).group_by("month").order_by("month").all()
    work_spend_rows = db.query(
        func.strftime("%Y-%m", Transaction.transaction_date).label("month"),
        func.sum(Transaction.amount_cents).label("amount"),
    ).filter(
        Transaction.transaction_type == "debit",
        Transaction.classification == "work",
        func.coalesce(Transaction.personal_category, "") != TRANSFER_CATEGORY,
    ).group_by("month").order_by("month").all()
    spend_rows = [(month, "personal", amount) for month, amount in personal_spend_rows] + [
        (month, "work", amount) for month, amount in work_spend_rows
    ]

    income_rows = db.query(
        func.strftime("%Y-%m", Transaction.transaction_date).label("month"),
        Transaction.personal_category,
        func.sum(Transaction.amount_cents).label("amount"),
    ).filter(
        Transaction.transaction_type == "credit",
        Transaction.classification == "personal",
        Transaction.personal_category.in_(list(INCOME_CATEGORIES)),
    ).group_by("month", Transaction.personal_category).order_by("month").all()

    month_map: dict[str, dict[str, int]] = {}
    for month, classification, amount in spend_rows:
        bucket = month_map.setdefault(month, {"personal": 0, "work": 0, "Income": 0, "Reimbursement": 0})
        bucket[classification] = int(amount or 0)
    for month, category, amount in income_rows:
        bucket = month_map.setdefault(month, {"personal": 0, "work": 0, "Income": 0, "Reimbursement": 0})
        bucket[category] = int(amount or 0)

    selected = sorted(month_map.items())[-months:]
    summary_months = [
        DashboardMonth(
            month=m,
            personal_cents=v.get("personal", 0),
            work_cents=v.get("work", 0),
            income_cents=v.get("Income", 0),
            reimbursement_cents=v.get("Reimbursement", 0),
        )
        for m, v in selected
    ]
    personal_total = sum(m.personal_cents for m in summary_months)
    work_total = sum(m.work_cents for m in summary_months)
    income_total = sum(m.income_cents for m in summary_months)
    reimbursement_total = sum(m.reimbursement_cents for m in summary_months)

    uncategorized_income_cents, uncategorized_income_count = db.query(
        func.coalesce(func.sum(Transaction.amount_cents), 0),
        func.count(Transaction.id),
    ).filter(
        Transaction.transaction_type == "credit",
        Transaction.classification == "personal",
        Transaction.personal_category.is_(None),
    ).one()

    # Work money still owed back: debit work rows not yet marked expensed.
    unexpensed_work_cents, unexpensed_work_count = db.query(
        func.coalesce(func.sum(Transaction.amount_cents), 0),
        func.count(Transaction.id),
    ).filter(
        Transaction.transaction_type == "debit",
        Transaction.classification == "work",
        Transaction.expensed.is_(False),
        func.coalesce(Transaction.personal_category, "") != TRANSFER_CATEGORY,
    ).one()

    # Top merchants by personal spend over the selected window.
    selected_month_keys = [m for m, _ in selected]
    top_merchants: list[MerchantSpend] = []
    if selected_month_keys:
        merchant_rows = db.query(
            Transaction.description,
            Transaction.amount_cents,
        ).filter(
            Transaction.classification == "personal",
            Transaction.transaction_type == "debit",
            func.coalesce(Transaction.personal_category, "") != TRANSFER_CATEGORY,
            func.strftime("%Y-%m", Transaction.transaction_date).in_(selected_month_keys),
        ).all()
        merchant_totals: dict[str, list[int]] = {}
        for description, amount in merchant_rows:
            name = _normalize_merchant(description)
            if not name:
                continue
            bucket = merchant_totals.setdefault(name, [0, 0])
            bucket[0] += int(amount or 0)
            bucket[1] += 1
        top_merchants = [
            MerchantSpend(name=name, amount_cents=cents, count=count)
            for name, (cents, count) in sorted(
                merchant_totals.items(), key=lambda kv: kv[1][0], reverse=True
            )
            if cents > 0
        ][:5]

    unsorted_count = db.query(Transaction).filter(Transaction.classification.is_(None)).count()
    latest_month = summary_months[-1].month if summary_months else None
    return DashboardSummary(
        personal_total_cents=personal_total,
        work_total_cents=work_total,
        unsorted_count=unsorted_count,
        latest_month=latest_month,
        months=summary_months,
        income_total_cents=income_total,
        reimbursement_total_cents=reimbursement_total,
        uncategorized_income_cents=int(uncategorized_income_cents or 0),
        uncategorized_income_count=int(uncategorized_income_count or 0),
        unexpensed_work_cents=int(unexpensed_work_cents or 0),
        unexpensed_work_count=int(unexpensed_work_count or 0),
        top_merchants=top_merchants,
    )


@router.get("/income/personal", response_model=SpendingSummary)
def personal_income(
    months: int = Query(12, ge=1, le=36),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month_rows = db.query(
        func.strftime("%Y-%m", Transaction.transaction_date).label("month"),
        func.sum(Transaction.amount_cents).label("amount"),
    ).filter(
        Transaction.classification == "personal",
        Transaction.transaction_type == "credit",
        Transaction.personal_category.in_(list(INCOME_CATEGORIES)),
    ).group_by("month").order_by("month").all()
    selected_months = [month for month, _ in month_rows][-months:]

    category_rows = []
    if selected_months:
        category_rows = db.query(
            func.strftime("%Y-%m", Transaction.transaction_date).label("month"),
            Transaction.personal_category.label("category"),
            func.sum(Transaction.amount_cents).label("amount"),
        ).filter(
            Transaction.classification == "personal",
            Transaction.transaction_type == "credit",
            Transaction.personal_category.in_(list(INCOME_CATEGORIES)),
            func.strftime("%Y-%m", Transaction.transaction_date).in_(selected_months),
        ).group_by("month", "category").order_by("month", "category").all()

    category_by_month: dict[str, list[tuple[str, int]]] = {}
    category_totals: dict[str, int] = {}
    for month, category, amount in category_rows:
        cents = int(amount or 0)
        category_by_month.setdefault(month, []).append((category, cents))
        category_totals[category] = category_totals.get(category, 0) + cents

    points = []
    for month, amount in month_rows[-months:]:
        amount_cents = int(amount or 0)
        rows = category_by_month.get(month, [])
        points.append(SpendingPoint(
            label=month,
            amount_cents=amount_cents,
            by_category=[
                SpendingByCategory(category_name=category, amount_cents=cents, percent=(cents / amount_cents * 100) if amount_cents else 0)
                for category, cents in sorted(rows, key=lambda row: row[1], reverse=True)
            ],
        ))
    total = sum(point.amount_cents for point in points)
    avg = round(total / len(points)) if points else 0
    by_category = [
        SpendingByCategory(category_name=category, amount_cents=cents, percent=(cents / total * 100) if total else 0)
        for category, cents in sorted(category_totals.items(), key=lambda row: row[1], reverse=True)
    ]
    return SpendingSummary(total_cents=total, average_per_month_cents=avg, points=points, by_category=by_category)
