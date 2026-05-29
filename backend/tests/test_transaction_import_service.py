import io
from datetime import date

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers

from app.config import settings
from app.migrations import run_migrations
from app.models.transaction import Transaction
from app.services.statement_import_service import ParsedRow
from app.services.transaction_import_service import (
    _existing_hashes,
    _is_card_payment,
    _rows_for_source,
    confirm_import,
    preview_import,
    read_limited_upload,
)


def _upload(content: bytes, filename: str = "statement.csv", content_type: str = "text/csv") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
        size=len(content),
    )


def _row(*, description: str, transaction_type: str, source_hash: str = "h") -> ParsedRow:
    return ParsedRow(
        row_number=1,
        transaction_date=date(2026, 5, 1),
        description=description,
        amount_cents=100,
        transaction_type=transaction_type,
        source_hash=source_hash,
    )


def _make_xlsx(headers: list[str], data_rows: list[list[object]]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in data_rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "imports.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setattr(settings, "database_url", db_url)
    run_migrations()
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return Session(), engine


@pytest.mark.asyncio
async def test_read_limited_upload_returns_full_content_under_limit():
    payload = b"hello world"
    assert await read_limited_upload(_upload(payload)) == payload


@pytest.mark.asyncio
async def test_read_limited_upload_rejects_oversized_via_advertised_size():
    payload = b"x" * (10 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="too large"):
        await read_limited_upload(_upload(payload))


@pytest.mark.asyncio
async def test_read_limited_upload_rejects_oversized_streamed_content():
    payload = b"x" * (10 * 1024 * 1024 + 1)
    upload = UploadFile(
        file=io.BytesIO(payload),
        filename="huge.csv",
        headers=Headers({"content-type": "text/csv"}),
        size=None,
    )
    with pytest.raises(ValueError, match="too large"):
        await read_limited_upload(upload)


def test_is_card_payment_matches_exact_descriptions_case_insensitively():
    assert _is_card_payment(_row(description="PAYMENT - THANK YOU", transaction_type="credit")) is True
    assert _is_card_payment(_row(description="  payment - thank you  ", transaction_type="credit")) is True
    assert _is_card_payment(_row(description="PAYMENT RECEIVED - THANK YOU", transaction_type="credit")) is True


def test_is_card_payment_ignores_substring_matches():
    assert _is_card_payment(_row(description="PAYMENT TO VENDOR - THANK YOU", transaction_type="credit")) is False


def test_is_card_payment_ignores_debits():
    assert _is_card_payment(_row(description="PAYMENT - THANK YOU", transaction_type="debit")) is False


def test_rows_for_source_card_drops_card_payment_credits():
    rows = [
        _row(description="Coffee", transaction_type="debit", source_hash="a"),
        _row(description="PAYMENT - THANK YOU", transaction_type="credit", source_hash="b"),
        _row(description="REFUND", transaction_type="credit", source_hash="c"),
    ]
    kept, ignored = _rows_for_source(rows, "card")
    assert [r.source_hash for r in kept] == ["a", "c"]
    assert ignored == 1


def test_rows_for_source_checking_keeps_all_rows():
    rows = [
        _row(description="Paycheck", transaction_type="credit", source_hash="a"),
        _row(description="Rent", transaction_type="debit", source_hash="b"),
    ]
    kept, ignored = _rows_for_source(rows, "checking")
    assert [r.source_hash for r in kept] == ["a", "b"]
    assert ignored == 0


def test_existing_hashes_returns_intersection(tmp_path, monkeypatch):
    db, engine = _db_session(tmp_path, monkeypatch)
    try:
        db.add(Transaction(
            transaction_date=date(2026, 5, 1),
            description="Coffee",
            amount_cents=425,
            transaction_type="debit",
            statement_format="test",
            source_hash="existing-hash",
        ))
        db.commit()

        rows = [
            _row(description="Coffee", transaction_type="debit", source_hash="existing-hash"),
            _row(description="New", transaction_type="debit", source_hash="new-hash"),
        ]
        assert _existing_hashes(db, rows) == {"existing-hash"}
        assert _existing_hashes(db, []) == set()
    finally:
        db.close()
        engine.dispose()


def test_preview_checking_xlsx_signed_amount_preserves_transaction_types(tmp_path, monkeypatch):
    db, engine = _db_session(tmp_path, monkeypatch)
    try:
        raw = _make_xlsx(
            ["Date", "Description", "Amount"],
            [
                ["05/01/2026", "Paycheck", 1000.00],
                ["05/02/2026", "Rent", -1200.00],
            ],
        )

        preview = preview_import(db, raw, "checking.xlsx", "checking")

        assert preview.statement_format == "Checking CSV"
        assert preview.ignored_credits == 0
        assert preview.to_import == 2
        assert [(row.description, row.transaction_type, row.amount_cents) for row in preview.rows] == [
            ("Paycheck", "credit", 100000),
            ("Rent", "debit", 120000),
        ]
    finally:
        db.close()
        engine.dispose()


def test_confirm_checking_xlsx_withdrawal_deposit_columns_persists_personal_rows(tmp_path, monkeypatch):
    db, engine = _db_session(tmp_path, monkeypatch)
    try:
        raw = _make_xlsx(
            ["Date", "Description", "Withdrawal", "Deposit"],
            [
                ["05/01/2026", "Paycheck", "", 1000.00],
                ["05/02/2026", "Rent", 1200.00, ""],
            ],
        )

        result = confirm_import(db, raw, "checking.xlsx", "checking")

        assert result.imported == 2
        assert result.ignored_credits == 0
        stored = db.query(Transaction).order_by(Transaction.transaction_date).all()
        assert [(tx.description, tx.transaction_type, tx.amount_cents, tx.classification) for tx in stored] == [
            ("Paycheck", "credit", 100000, "personal"),
            ("Rent", "debit", 120000, "personal"),
        ]
        assert all(tx.import_batch_id == result.batch_id for tx in stored)
    finally:
        db.close()
        engine.dispose()


def test_preview_qfx_card_import_ignores_payment_credit(tmp_path, monkeypatch):
    db, engine = _db_session(tmp_path, monkeypatch)
    try:
        raw = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<OFX xmlns="http://ofx.net/types/2003/04">
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STMTRS>
        <BANKTRNLIST>
          <STMTTRN>
            <DTPOSTED>20260501</DTPOSTED>
            <TRNAMT>-4.25</TRNAMT>
            <NAME>Coffee shop</NAME>
          </STMTTRN>
          <STMTTRN>
            <DTPOSTED>20260502</DTPOSTED>
            <TRNAMT>100.00</TRNAMT>
            <NAME>PAYMENT - THANK YOU</NAME>
          </STMTTRN>
        </BANKTRNLIST>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>
"""

        preview = preview_import(db, raw, "statement.qfx", "card")

        assert preview.statement_format == "OFX/QFX Bank Export"
        assert preview.total == 2
        assert preview.ignored_credits == 1
        assert preview.to_import == 1
        assert [(row.description, row.transaction_type, row.amount_cents) for row in preview.rows] == [
            ("Coffee shop", "debit", 425),
        ]
    finally:
        db.close()
        engine.dispose()


def test_confirm_checking_qfx_keeps_debits_and_credits_as_personal(tmp_path, monkeypatch):
    db, engine = _db_session(tmp_path, monkeypatch)
    try:
        raw = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<OFX>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STMTRS>
        <BANKTRNLIST>
          <STMTTRN>
            <DTPOSTED>20260501</DTPOSTED>
            <TRNAMT>1000.00</TRNAMT>
            <NAME>Paycheck</NAME>
          </STMTTRN>
          <STMTTRN>
            <DTPOSTED>20260502</DTPOSTED>
            <TRNAMT>-1200.00</TRNAMT>
            <NAME>Rent</NAME>
          </STMTTRN>
        </BANKTRNLIST>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>
"""

        result = confirm_import(db, raw, "checking.qfx", "checking")

        assert result.imported == 2
        assert result.ignored_credits == 0
        assert result.batch_id is not None
        stored = db.query(Transaction).order_by(Transaction.transaction_date).all()
        assert [(tx.description, tx.transaction_type, tx.amount_cents, tx.classification, tx.statement_format) for tx in stored] == [
            ("Paycheck", "credit", 100000, "personal", "OFX/QFX Bank Export"),
            ("Rent", "debit", 120000, "personal", "OFX/QFX Bank Export"),
        ]
    finally:
        db.close()
        engine.dispose()
