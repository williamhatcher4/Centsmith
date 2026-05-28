import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.import_batch import ImportBatch
from app.models.transaction import Transaction
from app.schemas.transaction import ImportPreview, ImportPreviewRow, ImportResult
from app.services.statement_import_service import ParsedRow, parse_statement

ImportSource = Literal["card", "checking"]

MAX_IMPORT_BYTES = 10 * 1024 * 1024
CARD_PAYMENT_DESCRIPTIONS = frozenset({"PAYMENT - THANK YOU", "PAYMENT RECEIVED - THANK YOU"})


async def read_limited_upload(file: UploadFile, max_bytes: int = MAX_IMPORT_BYTES) -> bytes:
    if file.size and file.size > max_bytes:
        raise ValueError("File too large (max 10 MB)")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("File too large (max 10 MB)")
        chunks.append(chunk)
    return b"".join(chunks)


def _is_card_payment(row: ParsedRow) -> bool:
    return (
        row.transaction_type == "credit"
        and row.description.strip().upper() in CARD_PAYMENT_DESCRIPTIONS
    )


def _rows_for_source(rows: list[ParsedRow], source: ImportSource) -> tuple[list[ParsedRow], int]:
    if source == "checking":
        return rows, 0
    spending_rows = [row for row in rows if not _is_card_payment(row)]
    return spending_rows, len(rows) - len(spending_rows)


def _existing_hashes(db: Session, rows: list[ParsedRow]) -> set[str]:
    hashes = [row.source_hash for row in rows]
    if not hashes:
        return set()
    return {h for (h,) in db.query(Transaction.source_hash).filter(Transaction.source_hash.in_(hashes)).all()}


def _parse(raw: bytes, filename: str, source: ImportSource) -> tuple[list[ParsedRow], str, int]:
    if source == "checking":
        return parse_statement(filename or "checking.csv", raw, source="checking")
    return parse_statement(filename or "statement.csv", raw)


def preview_import(db: Session, raw: bytes, filename: str, source: ImportSource) -> ImportPreview:
    rows, fmt, skipped_errors = _parse(raw, filename, source)
    import_rows, ignored_credits = _rows_for_source(rows, source)
    existing = _existing_hashes(db, import_rows)
    preview_rows = [
        ImportPreviewRow(
            row_number=row.row_number,
            date=row.transaction_date,
            description=row.description,
            amount_cents=row.amount_cents,
            transaction_type=row.transaction_type,
            is_duplicate=row.source_hash in existing,
        )
        for row in import_rows
    ]
    duplicates = sum(1 for row in preview_rows if row.is_duplicate)
    return ImportPreview(
        rows=preview_rows,
        total=len(rows),
        duplicates=duplicates,
        ignored_credits=ignored_credits,
        to_import=len(preview_rows) - duplicates,
        statement_format=fmt,
        skipped_errors=skipped_errors,
    )


def confirm_import(db: Session, raw: bytes, filename: str, source: ImportSource) -> ImportResult:
    rows, fmt, skipped_errors = _parse(raw, filename, source)
    import_rows, ignored_credits = _rows_for_source(rows, source)
    existing = _existing_hashes(db, import_rows)
    imported = skipped = 0

    batch_id = str(uuid.uuid4())
    batch = ImportBatch(
        id=batch_id,
        filename=filename or ("checking.csv" if source == "checking" else "statement.csv"),
        statement_format=fmt,
        imported_at=datetime.now(timezone.utc),
        row_count=0,
        created_by_action="import",
    )
    db.add(batch)
    db.flush()

    for row in import_rows:
        if row.source_hash in existing:
            skipped += 1
            continue
        db.add(Transaction(
            transaction_date=row.transaction_date,
            description=row.description,
            amount_cents=row.amount_cents,
            transaction_type=row.transaction_type,
            classification="personal" if source == "checking" else None,
            expensed=False,
            statement_format=fmt,
            source_hash=row.source_hash,
            import_batch_id=batch_id,
        ))
        existing.add(row.source_hash)
        imported += 1

    if imported == 0:
        db.delete(batch)
        db.commit()
        return ImportResult(
            imported=imported,
            skipped=skipped,
            ignored_credits=ignored_credits,
            skipped_errors=skipped_errors,
            batch_id=None,
        )

    batch.row_count = imported
    db.commit()
    return ImportResult(
        imported=imported,
        skipped=skipped,
        ignored_credits=ignored_credits,
        skipped_errors=skipped_errors,
        batch_id=batch_id,
    )
