"""Phase 1: skipped-row diagnostics + manual column mapping (parser level)."""

import pytest

from app.services.statement_import_service import (
    MAX_DIAG_FIELD_LEN,
    ColumnMapping,
    parse_statement_ex,
    parse_statement_with_mapping,
)

# Fixed user-facing messages — diagnostics must never leak exception text/paths.
ALLOWED_MESSAGES = {
    "Could not read the date in this row.",
    "Could not read the amount in this row.",
    "This row has no amount, debit, or credit value.",
    "This row could not be read and was skipped.",
}


def test_skipped_rows_capture_reason_and_are_sanitized():
    csv_bytes = (
        b"Date,Description,Amount\n"
        b"2026-05-01,Coffee,4.25\n"
        b"not-a-date,Bad row,9.99\n"
    )
    result = parse_statement_ex("statement.csv", csv_bytes)
    assert len(result.rows) == 1
    assert result.skipped_errors == 1
    assert len(result.skipped_rows) == 1
    skip = result.skipped_rows[0]
    assert skip.reason_code == "unparseable_date"
    assert skip.message in ALLOWED_MESSAGES
    # Raw fields are echoed back (user's own data) but no internal path leaks.
    assert skip.raw_date == "not-a-date"
    assert skip.raw_description == "Bad row"
    assert "\\" not in skip.message and "/" not in skip.message
    assert "Traceback" not in skip.message


def test_skipped_row_fields_are_truncated():
    long_desc = "X" * 500
    csv_bytes = (
        b"Date,Description,Amount\n"
        + f"bad-date,{long_desc},1.00\n".encode()
    )
    result = parse_statement_ex("statement.csv", csv_bytes)
    assert len(result.skipped_rows) == 1
    assert len(result.skipped_rows[0].raw_description) <= MAX_DIAG_FIELD_LEN


def test_unknown_headers_trigger_mapping_required():
    csv_bytes = (
        b"Col A,Col B,Col C\n"
        b"2026-05-01,Coffee,4.25\n"
        b"2026-05-02,Lunch,12.50\n"
    )
    result = parse_statement_ex("statement.csv", csv_bytes)
    assert result.rows == []
    assert result.columns is not None
    assert result.columns.mapping_required is True
    assert result.columns.headers == ["Col A", "Col B", "Col C"]
    assert result.columns.sample_rows[0] == ["2026-05-01", "Coffee", "4.25"]


def test_parse_with_mapping_imports_unknown_csv():
    csv_bytes = (
        b"Col A,Col B,Col C\n"
        b"2026-05-01,Coffee,-4.25\n"
        b"2026-05-02,Refund,10.00\n"
    )
    mapping = ColumnMapping(
        date_column=0, description_column=1, amount_column=2, amount_convention="signed"
    )
    result = parse_statement_with_mapping("statement.csv", csv_bytes, "card", mapping)
    assert len(result.rows) == 2
    coffee = next(r for r in result.rows if r.description == "Coffee")
    refund = next(r for r in result.rows if r.description == "Refund")
    assert coffee.transaction_type == "debit"
    assert coffee.amount_cents == 425
    assert refund.transaction_type == "credit"
    assert refund.amount_cents == 1000


def test_mapping_charges_positive_inverts_sign():
    csv_bytes = b"Col A,Col B,Col C\n2026-05-01,Coffee,4.25\n"
    mapping = ColumnMapping(
        date_column=0, description_column=1, amount_column=2, amount_convention="charges_positive"
    )
    result = parse_statement_with_mapping("statement.csv", csv_bytes, "card", mapping)
    assert len(result.rows) == 1
    # Positive charge becomes a debit when charges are listed as positive.
    assert result.rows[0].transaction_type == "debit"


def test_mapping_debit_credit_columns():
    csv_bytes = (
        b"When,What,Out,In\n"
        b"2026-05-01,Coffee,4.25,\n"
        b"2026-05-02,Paycheck,,1500.00\n"
    )
    mapping = ColumnMapping(date_column=0, description_column=1, debit_column=2, credit_column=3)
    result = parse_statement_with_mapping("statement.csv", csv_bytes, "checking", mapping)
    assert len(result.rows) == 2
    coffee = next(r for r in result.rows if r.description == "Coffee")
    pay = next(r for r in result.rows if r.description == "Paycheck")
    assert coffee.transaction_type == "debit" and coffee.amount_cents == 425
    assert pay.transaction_type == "credit" and pay.amount_cents == 150000


def test_mapping_blank_debit_and_credit_is_skipped_not_dropped():
    # A row with a date + description but blank in both debit and credit columns
    # must surface as a skipped row with a missing-amount diagnostic, never vanish.
    csv_bytes = (
        b"When,What,Out,In\n"
        b"2026-05-01,Coffee,4.25,\n"
        b"2026-05-02,Mystery,,\n"
    )
    mapping = ColumnMapping(date_column=0, description_column=1, debit_column=2, credit_column=3)
    result = parse_statement_with_mapping("statement.csv", csv_bytes, "checking", mapping)
    assert len(result.rows) == 1
    assert result.skipped_errors == 1
    assert len(result.skipped_rows) == 1
    skip = result.skipped_rows[0]
    assert skip.reason_code == "missing_amount"
    assert skip.message in ALLOWED_MESSAGES
    assert skip.raw_description == "Mystery"


def test_generic_csv_blank_amount_is_skipped_not_dropped():
    # Auto-detected generic CSV: a row with a date + description but a blank
    # amount must be recorded as a skipped row, never silently dropped.
    csv_bytes = (
        b"Date,Description,Amount\n"
        b"2026-05-01,Coffee,\n"
        b"2026-05-02,Lunch,12.50\n"
    )
    result = parse_statement_ex("statement.csv", csv_bytes)
    assert len(result.rows) == 1
    assert result.rows[0].description == "Lunch"
    assert result.skipped_errors == 1
    assert len(result.skipped_rows) == 1
    skip = result.skipped_rows[0]
    assert skip.reason_code == "missing_amount"
    assert skip.message in ALLOWED_MESSAGES
    assert skip.raw_description == "Coffee"


def test_mapping_corrupt_xlsx_raises_clean_value_error():
    # A file that claims to be .xlsx but is not a valid Excel workbook must
    # surface a clean ValueError (-> 400) instead of a raw library exception
    # (-> 500) leaking out of the mapped/profile import path.
    mapping = ColumnMapping(date_column=0, description_column=1, amount_column=2)
    with pytest.raises(ValueError, match="Could not parse XLSX file"):
        parse_statement_with_mapping("statement.xlsx", b"not a real workbook", "card", mapping)
