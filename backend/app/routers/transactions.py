import uuid
from datetime import datetime, timezone, date
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models.card import Card
from app.models.import_batch import ImportBatch
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import (
    BulkAssignCardRequest,
    BulkAssignCardResult,
    BulkCategorizeRequest,
    BulkCategorizeResult,
    BulkClassifyRequest,
    BulkClassifyResult,
    TransactionCreate,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
)
from app.services.transaction_rules import (
    apply_classification_side_effects,
    ensure_category_registered,
    validate_category_for_type,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/manual", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_manual_transaction(
    payload: TransactionCreate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.personal_category is not None:
        payload.personal_category = payload.personal_category.strip() or None
    if payload.personal_category:
        validate_category_for_type(payload.personal_category, payload.transaction_type)
    if payload.expensed and payload.classification != "work":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only work transactions can be marked as expensed")
    if payload.personal_category and payload.classification != "personal":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only personal transactions can have a personal category")
    ensure_category_registered(db, payload.personal_category)
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


@router.get("", response_model=TransactionPage)
def list_transactions(
    classification: Optional[Literal["personal", "work", "unsorted"]] = Query(None),
    transaction_type: Optional[Literal["debit", "credit"]] = Query(None),
    personal_category: Optional[str] = Query(None, max_length=80),
    expensed: Optional[bool] = Query(None),
    card_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # The unfiltered view shows everything — debits and credits (maintainer
    # decision 2026-06-09); narrowing to one type is an explicit filter.
    q = db.query(Transaction)
    if transaction_type is not None:
        q = q.filter(Transaction.transaction_type == transaction_type)
    if card_id is not None:
        q = q.filter(Transaction.card_id == card_id)
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
    # total over the full filtered set, before windowing — so the UI can tell the
    # user when more rows exist instead of silently truncating at the limit.
    total = q.count()
    if classification == "work":
        q = q.order_by(Transaction.expensed.asc())
    items = q.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).offset(skip).limit(limit).all()
    has_more = skip + len(items) < total
    return TransactionPage(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
        next_skip=(skip + limit) if has_more else None,
    )


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
        updates = apply_classification_side_effects(
            {"classification": payload.classification}, tx.classification
        )
        for field, value in updates.items():
            setattr(tx, field, value)
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
    for tx in txs:
        validate_category_for_type(payload.personal_category, tx.transaction_type)
    ensure_category_registered(db, payload.personal_category)
    for tx in txs:
        tx.personal_category = payload.personal_category
        tx.updated_at = datetime.now(timezone.utc)
    db.commit()
    return BulkCategorizeResult(updated=len(txs))


@router.post("/bulk-assign-card", response_model=BulkAssignCardResult)
def bulk_assign_card(
    payload: BulkAssignCardRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.card_id is not None and not db.query(Card).filter(Card.id == payload.card_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    txs = db.query(Transaction).filter(Transaction.id.in_(payload.transaction_ids)).all()
    if len(txs) != len(set(payload.transaction_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more transactions were not found")
    for tx in txs:
        tx.card_id = payload.card_id
        tx.updated_at = datetime.now(timezone.utc)
    db.commit()
    return BulkAssignCardResult(updated=len(txs))


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
    if ("amount_cents" in updates or "transaction_type" in updates) and not tx.is_manual:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount and type can only be edited on manually added transactions",
        )
    if updates.get("card_id") is not None and not db.query(Card).filter(Card.id == updates["card_id"]).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    if updates.get("expensed") and updates.get("classification", tx.classification) != "work":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only work transactions can be marked as expensed")
    next_classification = updates.get("classification", tx.classification)
    next_type = updates.get("transaction_type", tx.transaction_type)
    if updates.get("personal_category") and next_classification != "personal":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only personal transactions can have a personal category")
    if "personal_category" in updates and updates["personal_category"] is not None:
        updates["personal_category"] = updates["personal_category"].strip()
        if not updates["personal_category"]:
            updates["personal_category"] = None
        else:
            validate_category_for_type(updates["personal_category"], next_type)
            ensure_category_registered(db, updates["personal_category"])
    elif "transaction_type" in updates and next_classification == "personal":
        # A type flip must not leave a credit-only category on a debit row.
        validate_category_for_type(tx.personal_category, next_type)
    apply_classification_side_effects(updates, tx.classification)
    for field, value in updates.items():
        setattr(tx, field, value)
    tx.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tx)
    return tx
