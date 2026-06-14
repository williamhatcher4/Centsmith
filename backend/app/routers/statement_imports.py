import json
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models.card import Card
from app.models.import_profile import ImportProfile
from app.models.user import User
from app.schemas.import_profile import ColumnMappingIn
from app.schemas.imports import ImportPreview, ImportResult
from app.services.statement_import_service import ColumnMapping
from app.services.transaction_import_service import (
    confirm_import as confirm_statement_import,
    preview_import as preview_statement_import,
    read_limited_upload,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _resolve_import_mapping(
    db: Session, column_mapping: Optional[str], profile_id: Optional[int]
) -> tuple[Optional[ColumnMapping], Optional[list[str]]]:
    """Resolve an explicit column mapping + ignore patterns from request fields.

    A ``profile_id`` loads a saved per-bank profile; otherwise ``column_mapping``
    is a JSON string of an ad-hoc mapping. Returns ``(None, None)`` for ordinary
    auto-detected imports.
    """
    if profile_id is not None:
        profile = db.get(ImportProfile, profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Import profile not found")
        mapping = ColumnMapping(
            date_column=profile.date_column,
            description_column=profile.description_column,
            amount_column=profile.amount_column,
            debit_column=profile.debit_column,
            credit_column=profile.credit_column,
            amount_convention=profile.amount_convention,
            date_convention=profile.date_convention,
        )
        return mapping, list(profile.ignored_payment_patterns or [])
    if column_mapping:
        try:
            parsed = ColumnMappingIn(**json.loads(column_mapping))
        except (json.JSONDecodeError, TypeError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail="Invalid column mapping") from exc
        mapping = ColumnMapping(
            date_column=parsed.date_column,
            description_column=parsed.description_column,
            amount_column=parsed.amount_column,
            debit_column=parsed.debit_column,
            credit_column=parsed.credit_column,
            amount_convention=parsed.amount_convention,
            date_convention=parsed.date_convention,
        )
        return mapping, None
    return None, None


@router.post("/import/preview", response_model=ImportPreview)
async def preview_import(
    file: UploadFile = File(...),
    charges_positive: Optional[bool] = Form(None),
    day_first: Optional[bool] = Form(None),
    column_mapping: Optional[str] = Form(None),
    profile_id: Optional[int] = Form(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        mapping, ignored_patterns = _resolve_import_mapping(db, column_mapping, profile_id)
        raw = await read_limited_upload(file)
        return preview_statement_import(
            db, raw, file.filename or "statement.csv", "card", charges_positive, mapping, ignored_patterns,
            day_first=day_first,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import/confirm", response_model=ImportResult)
async def confirm_import(
    file: UploadFile = File(...),
    charges_positive: Optional[bool] = Form(None),
    day_first: Optional[bool] = Form(None),
    column_mapping: Optional[str] = Form(None),
    profile_id: Optional[int] = Form(None),
    card_id: Optional[int] = Form(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if card_id is not None and not db.query(Card).filter(Card.id == card_id).first():
        raise HTTPException(status_code=404, detail="Card not found")
    try:
        mapping, ignored_patterns = _resolve_import_mapping(db, column_mapping, profile_id)
        raw = await read_limited_upload(file)
        return confirm_statement_import(
            db, raw, file.filename or "statement.csv", "card", charges_positive, mapping, ignored_patterns, card_id,
            day_first=day_first,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import/checking/preview", response_model=ImportPreview)
async def preview_checking_import(
    file: UploadFile = File(...),
    day_first: Optional[bool] = Form(None),
    column_mapping: Optional[str] = Form(None),
    profile_id: Optional[int] = Form(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        mapping, ignored_patterns = _resolve_import_mapping(db, column_mapping, profile_id)
        raw = await read_limited_upload(file)
        return preview_statement_import(
            db, raw, file.filename or "checking.csv", "checking", None, mapping, ignored_patterns,
            day_first=day_first,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import/checking/confirm", response_model=ImportResult)
async def confirm_checking_import(
    file: UploadFile = File(...),
    day_first: Optional[bool] = Form(None),
    column_mapping: Optional[str] = Form(None),
    profile_id: Optional[int] = Form(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        mapping, ignored_patterns = _resolve_import_mapping(db, column_mapping, profile_id)
        raw = await read_limited_upload(file)
        return confirm_statement_import(
            db, raw, file.filename or "checking.csv", "checking", None, mapping, ignored_patterns,
            day_first=day_first,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
