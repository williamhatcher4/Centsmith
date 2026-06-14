import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.import_batch import ImportBatch
from app.models.transaction import Transaction
from app.schemas.imports import ImportPreview, ImportPreviewRow, ImportResult, SkippedRowOut
from app.services.statement_import_service import (
    ColumnMapping,
    ParsedRow,
    StatementParseResult,
    parse_statement_ex,
    parse_statement_with_mapping,
)

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


def _matches_ignore_pattern(row: ParsedRow, patterns: Optional[list[str]]) -> bool:
    if not patterns:
        return False
    desc = row.description.strip().upper()
    return any(p.strip().upper() in desc for p in patterns if p.strip())


def _rows_for_source(
    rows: list[ParsedRow], source: ImportSource, ignored_patterns: Optional[list[str]] = None
) -> tuple[list[ParsedRow], list[ParsedRow]]:
    def ignored(row: ParsedRow) -> bool:
        if source != "checking" and _is_card_payment(row):
            return True
        return _matches_ignore_pattern(row, ignored_patterns)

    kept: list[ParsedRow] = []
    ignored_rows: list[ParsedRow] = []
    for row in rows:
        (ignored_rows if ignored(row) else kept).append(row)
    return kept, ignored_rows


def _skipped_out(result: StatementParseResult) -> list[SkippedRowOut]:
    return [
        SkippedRowOut(
            row_number=s.row_number,
            raw_date=s.raw_date,
            raw_amount=s.raw_amount,
            raw_description=s.raw_description,
            reason_code=s.reason_code,
            message=s.message,
        )
        for s in result.skipped_rows
    ]


def _mapping_required_preview(result: StatementParseResult) -> ImportPreview:
    info = result.columns
    assert info is not None
    return ImportPreview(
        rows=[],
        total=0,
        duplicates=0,
        ignored_credits=0,
        to_import=0,
        statement_format=result.statement_format,
        skipped_errors=result.skipped_errors,
        skipped_rows=_skipped_out(result),
        mapping_required=True,
        available_columns=info.headers,
        sample_rows=info.sample_rows,
        detected_columns=info.detected,
    )


def _existing_hashes(db: Session, rows: list[ParsedRow]) -> set[str]:
    hashes = [row.source_hash for row in rows]
    if not hashes:
        return set()
    return {h for (h,) in db.query(Transaction.source_hash).filter(Transaction.source_hash.in_(hashes)).all()}


def _parse(
    raw: bytes,
    filename: str,
    source: ImportSource,
    charges_positive: Optional[bool] = None,
    mapping: Optional[ColumnMapping] = None,
    day_first: Optional[bool] = None,
) -> StatementParseResult:
    default_name = "checking.csv" if source == "checking" else "statement.csv"
    if mapping is not None:
        return parse_statement_with_mapping(filename or default_name, raw, source, mapping, day_first)
    if source == "checking":
        return parse_statement_ex(
            filename or default_name, raw, source="checking", charges_positive=charges_positive, day_first=day_first
        )
    return parse_statement_ex(filename or default_name, raw, charges_positive=charges_positive, day_first=day_first)


def preview_import(
    db: Session,
    raw: bytes,
    filename: str,
    source: ImportSource,
    charges_positive: Optional[bool] = None,
    mapping: Optional[ColumnMapping] = None,
    ignored_patterns: Optional[list[str]] = None,
    day_first: Optional[bool] = None,
) -> ImportPreview:
    result = _parse(raw, filename, source, charges_positive, mapping, day_first)
    if result.columns is not None and result.columns.mapping_required:
        return _mapping_required_preview(result)
    rows = result.rows
    import_rows, ignored_rows = _rows_for_source(rows, source, ignored_patterns)
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
    ignored_preview_rows = [
        ImportPreviewRow(
            row_number=row.row_number,
            date=row.transaction_date,
            description=row.description,
            amount_cents=row.amount_cents,
            transaction_type=row.transaction_type,
            is_duplicate=False,
            is_ignored_credit=True,
        )
        for row in ignored_rows
    ]
    duplicates = sum(1 for row in preview_rows if row.is_duplicate)
    all_rows = sorted(preview_rows + ignored_preview_rows, key=lambda r: r.row_number)
    return ImportPreview(
        rows=all_rows,
        total=len(rows),
        duplicates=duplicates,
        ignored_credits=len(ignored_rows),
        to_import=len(preview_rows) - duplicates,
        statement_format=result.statement_format,
        skipped_errors=result.skipped_errors,
        amount_sign_adjustable=result.amount_sign_adjustable,
        charges_positive=result.charges_positive,
        date_convention_adjustable=result.date_convention_adjustable,
        day_first=result.day_first,
        skipped_rows=_skipped_out(result),
    )


def confirm_import(
    db: Session,
    raw: bytes,
    filename: str,
    source: ImportSource,
    charges_positive: Optional[bool] = None,
    mapping: Optional[ColumnMapping] = None,
    ignored_patterns: Optional[list[str]] = None,
    card_id: Optional[int] = None,
    day_first: Optional[bool] = None,
) -> ImportResult:
    result = _parse(raw, filename, source, charges_positive, mapping, day_first)
    if result.columns is not None and result.columns.mapping_required:
        raise ValueError("This file needs a column mapping before it can be imported.")
    rows = result.rows
    fmt = result.statement_format
    skipped_errors = result.skipped_errors
    import_rows, ignored_rows = _rows_for_source(rows, source, ignored_patterns)
    ignored_credits = len(ignored_rows)
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
            card_id=card_id,
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
