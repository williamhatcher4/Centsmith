from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.import_batch import ImportBatch
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import ImportBatchDeleteResult, ImportBatchOut

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("", response_model=list[ImportBatchOut])
def list_import_batches(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(ImportBatch)
        .order_by(ImportBatch.imported_at.desc(), ImportBatch.id.desc())
        .all()
    )


@router.delete("/{batch_id}", response_model=ImportBatchDeleteResult)
def delete_import_batch(
    batch_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")

    classified_expr = func.sum(case((Transaction.classification.is_not(None), 1), else_=0))
    categorized_expr = func.sum(case((Transaction.personal_category.is_not(None), 1), else_=0))
    classified_rows, categorized_rows, removed_rows = db.query(
        func.coalesce(classified_expr, 0),
        func.coalesce(categorized_expr, 0),
        func.count(Transaction.id),
    ).filter(Transaction.import_batch_id == batch_id).one()

    db.query(Transaction).filter(Transaction.import_batch_id == batch_id).delete(synchronize_session=False)
    db.delete(batch)
    db.commit()

    return ImportBatchDeleteResult(
        removed_rows=int(removed_rows or 0),
        classified_rows=int(classified_rows or 0),
        categorized_rows=int(categorized_rows or 0),
    )
