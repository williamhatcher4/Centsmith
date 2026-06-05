from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.card import Card
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.card import CardCreate, CardOut, CardUpdate, StatementSummary

router = APIRouter(prefix="/cards", tags=["cards"])


def _get_card_or_404(db: Session, card_id: int) -> Card:
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return card


@router.get("", response_model=list[CardOut])
def list_cards(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Card).order_by(Card.name.asc(), Card.id.asc()).all()


@router.post("", response_model=CardOut, status_code=status.HTTP_201_CREATED)
def create_card(
    payload: CardCreate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = Card(name=payload.name, last4=payload.last4, statement_day=payload.statement_day)
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.put("/{card_id}", response_model=CardOut)
def update_card(
    card_id: int,
    payload: CardUpdate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = _get_card_or_404(db, card_id)
    card.name = payload.name
    card.last4 = payload.last4
    card.statement_day = payload.statement_day
    db.commit()
    db.refresh(card)
    return card


@router.delete("/{card_id}", response_model=CardOut)
def delete_card(
    card_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = _get_card_or_404(db, card_id)
    # SQLite can't rely on the ON DELETE SET NULL FK for pre-existing columns, so
    # clear the association in application code before removing the card (mirrors
    # the import-batch cleanup in transactions.delete_transaction).
    db.query(Transaction).filter(Transaction.card_id == card_id).update(
        {Transaction.card_id: None}, synchronize_session=False
    )
    db.delete(card)
    db.commit()
    return card


@router.get("/{card_id}/statement", response_model=StatementSummary)
def card_statement(
    card_id: int,
    start_date: date = Query(...),
    end_date: date = Query(...),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_card_or_404(db, card_id)
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be on or before end_date",
        )

    def _totals(transaction_type: str) -> tuple[int, int]:
        amount, count = (
            db.query(
                func.coalesce(func.sum(Transaction.amount_cents), 0),
                func.count(Transaction.id),
            )
            .filter(
                Transaction.card_id == card_id,
                Transaction.transaction_type == transaction_type,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
            )
            .one()
        )
        return int(amount or 0), int(count or 0)

    charges_cents, charge_count = _totals("debit")
    payments_cents, payment_count = _totals("credit")
    return StatementSummary(
        card_id=card_id,
        start_date=start_date,
        end_date=end_date,
        charges_cents=charges_cents,
        payments_cents=payments_cents,
        net_cents=charges_cents - payments_cents,
        charge_count=charge_count,
        payment_count=payment_count,
    )
