from datetime import datetime, timezone
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models.transaction import Transaction
from app.models.user import User
from app.models.user_settings import UserSettings
from app.schemas.settings import UserSettingsOut, UserSettingsUpdate
from app.services.maintenance_service import validate_backup_folder
from app.services.transaction_rules import DEFAULT_CATEGORIES, INCOME_CATEGORIES

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_or_create(db: Session) -> UserSettings:
    obj = db.get(UserSettings, 1)
    if not obj:
        obj = UserSettings(id=1, personal_categories=list(DEFAULT_CATEGORIES), hidden_pages=[])
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj


@router.get("", response_model=UserSettingsOut)
def get_settings(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _get_or_create(db)


@router.get("/category-usage", response_model=dict[str, int])
def get_category_usage(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Transaction.personal_category, func.count(Transaction.id))
        .filter(Transaction.personal_category.isnot(None))
        .group_by(Transaction.personal_category)
        .all()
    )
    return {cat: int(count) for cat, count in rows if cat}


@router.put("", response_model=UserSettingsOut)
def update_settings(
    payload: UserSettingsUpdate,
    on_delete: Literal["reject", "relabel"] = Query("reject"),
    relabel_target: Optional[str] = Query(None, max_length=80),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    obj = _get_or_create(db)
    old_categories = set(obj.personal_categories or [])
    new_categories_list = payload.personal_categories
    new_categories = set(new_categories_list)
    removed = old_categories - new_categories

    if removed:
        usage_rows = (
            db.query(Transaction.personal_category, func.count(Transaction.id))
            .filter(Transaction.personal_category.in_(list(removed)))
            .group_by(Transaction.personal_category)
            .all()
        )
        in_use = {cat: int(count) for cat, count in usage_rows if count}
        if in_use:
            if on_delete == "relabel":
                if not relabel_target:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="relabel_target is required when on_delete=relabel",
                    )
                if relabel_target not in new_categories:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="relabel_target must be one of the saved categories",
                    )
                if relabel_target in INCOME_CATEGORIES:
                    non_credit_count = db.query(Transaction).filter(
                        Transaction.personal_category.in_(list(in_use.keys())),
                        Transaction.transaction_type != "credit",
                    ).count()
                    if non_credit_count:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Income/Reimbursement categories only apply to credit transactions",
                        )
                db.query(Transaction).filter(
                    Transaction.personal_category.in_(list(in_use.keys()))
                ).update(
                    {Transaction.personal_category: relabel_target},
                    synchronize_session=False,
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "Cannot remove categories that are still in use",
                        "in_use": in_use,
                    },
                )

    # Only touch backup_folder when the client actually sent the field, so the
    # categories/pages PUT flows can't silently clear a configured folder.
    if "backup_folder" in payload.model_fields_set:
        if payload.backup_folder is None or not payload.backup_folder.strip():
            obj.backup_folder = None
        else:
            try:
                obj.backup_folder = validate_backup_folder(payload.backup_folder)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    obj.personal_categories = new_categories_list
    obj.hidden_pages = payload.hidden_pages
    obj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj
