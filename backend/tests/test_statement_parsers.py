import io
from datetime import date
from decimal import Decimal

import pytest
import xlrd
from xlwt import Workbook

from app.services.statement_import_service import (
    FORMAT_NAMES,
    _assign_occurrences,
    _is_blank,
    _looks_like_date,
    _parse_amount,
    _parse_date,
    _source_hash,
    _to_cents,
    parse_statement,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-05-01", date(2026, 5, 1)),
        ("05/01/2026", date(2026, 5, 1)),
        ("5/1/26", date(2026, 5, 1)),
        ("May 1, 2026", date(2026, 5, 1)),
        ("01-May-2026", date(2026, 5, 1)),
        ("1 May 2026", date(2026, 5, 1)),
        ("1 May. 2026", date(2026, 5, 1)),
    ],
)
def test_parse_date_accepts_supported_formats(raw, expected):
    assert _parse_date(raw) == expected


def test_parse_date_ambiguous_us_format_picks_month_first():
    assert _parse_date("01/05/2026") == date(2026, 1, 5)


def test_parse_date_regex_fallback_handles_four_digit_year_first():
    assert _parse_date("2026-5-1") == date(2026, 5, 1)


def test_parse_date_regex_fallback_handles_two_digit_year():
    assert _parse_date("05-01-26") == date(2026, 5, 1)


def test_parse_date_rejects_garbage():
    with pytest.raises(ValueError):
        _parse_date("not a date")


def test_parse_date_accepts_native_date_and_datetime():
    from datetime import datetime

    assert _parse_date(date(2026, 5, 1)) == date(2026, 5, 1)
    assert _parse_date(datetime(2026, 5, 1, 13, 30)) == date(2026, 5, 1)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("4.25", Decimal("4.25")),
        ("$4.25", Decimal("4.25")),
        ("1,234.56", Decimal("1234.56")),
        ("$1,234.56", Decimal("1234.56")),
        ("(50.00)", Decimal("-50.00")),
        ("−50.00", Decimal("-50.00")),
        ("-50.00", Decimal("-50.00")),
        ("", Decimal("0")),
        (None, Decimal("0")),
    ],
)
def test_parse_amount_handles_currency_and_signs(raw, expected):
    assert _parse_amount(raw) == expected


def test_parse_amount_rejects_garbage():
    with pytest.raises(ValueError):
        _parse_amount("not-a-number")


def test_to_cents_uses_half_up_rounding():
    assert _to_cents(Decimal("1.005")) == 101
    assert _to_cents(Decimal("-1.005")) == 101
    assert _to_cents(Decimal("0.004")) == 0
    assert _to_cents(Decimal("0.006")) == 1


def test_source_hash_is_stable_and_distinct_per_occurrence():
    base = _source_hash(date(2026, 5, 1), "Coffee", 425, "debit")
    again = _source_hash(date(2026, 5, 1), "Coffee", 425, "debit")
    later = _source_hash(date(2026, 5, 1), "Coffee", 425, "debit", occurrence=1)
    assert base == again
    assert base != later


def test_source_hash_strips_and_lowercases_description():
    a = _source_hash(date(2026, 5, 1), "  Coffee  ", 425, "debit")
    b = _source_hash(date(2026, 5, 1), "coffee", 425, "debit")
    assert a == b


def test_assign_occurrences_makes_duplicate_rows_unique():
    rows, _, _ = parse_statement(
        "statement.csv",
        b"2026-05-01,Coffee,4.25,\n2026-05-01,Coffee,4.25,\n",
    )
    assert len(rows) == 2
    assert rows[0].source_hash != rows[1].source_hash


def test_assign_occurrences_leaves_distinct_rows_alone():
    rows = [
        type("R", (), {
            "transaction_date": date(2026, 5, 1),
            "description": "Coffee",
            "amount_cents": 425,
            "transaction_type": "debit",
            "source_hash": "original",
            "row_number": 1,
        })(),
        type("R", (), {
            "transaction_date": date(2026, 5, 2),
            "description": "Coffee",
            "amount_cents": 425,
            "transaction_type": "debit",
            "source_hash": "original2",
            "row_number": 2,
        })(),
    ]
    _assign_occurrences(rows)
    assert rows[0].source_hash == "original"
    assert rows[1].source_hash == "original2"


def test_looks_like_date_handles_known_and_unknown():
    assert _looks_like_date("2026-05-01") is True
    assert _looks_like_date("garbage") is False


def test_is_blank_distinguishes_none_empty_and_zero():
    assert _is_blank(None) is True
    assert _is_blank("") is True
    assert _is_blank("   ") is True
    assert _is_blank(0) is False
    assert _is_blank("x") is False


def test_parse_statement_headerless_csv_is_account_activity():
    body = b"2026-05-01,Coffee,4.25,\n2026-05-02,Refund,,4.25\n"
    rows, fmt, errors = parse_statement("statement.csv", body)
    assert errors == 0
    assert fmt == FORMAT_NAMES["accountactivity"]
    assert [(r.transaction_type, r.amount_cents) for r in rows] == [("debit", 425), ("credit", 425)]


def test_parse_statement_headerless_csv_as_checking_uses_checking_label():
    body = b"2026-05-01,Coffee,4.25,\n"
    _, fmt, _ = parse_statement("statement.csv", body, source="checking")
    assert fmt == FORMAT_NAMES["checking"]


def test_parse_statement_generic_csv_with_amount_column():
    body = b"Date,Description,Amount\n2026-05-01,Coffee,-4.25\n2026-05-02,Refund,4.25\n"
    rows, fmt, errors = parse_statement("statement.csv", body)
    assert errors == 0
    assert fmt == FORMAT_NAMES["generic"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 425),
        ("Refund", "credit", 425),
    ]


def test_parse_statement_generic_csv_with_debit_credit_columns():
    body = b"Date,Description,Debit,Credit\n2026-05-01,Coffee,4.25,\n2026-05-02,Refund,,4.25\n"
    rows, fmt, errors = parse_statement("statement.csv", body)
    assert errors == 0
    assert fmt == FORMAT_NAMES["generic"]
    assert [(r.transaction_type, r.amount_cents) for r in rows] == [("debit", 425), ("credit", 425)]


def test_parse_statement_generic_csv_falls_through_for_unknown_headers():
    body = b"Foo,Bar\nx,y\n"
    rows, _, _ = parse_statement("statement.csv", body)
    assert rows == []


def test_parse_statement_xls_amex_format():
    book = Workbook()
    sheet = book.add_sheet("Activity")
    sheet.write(0, 0, "Date")
    sheet.write(0, 1, "Description")
    sheet.write(0, 2, "Amount")
    sheet.write(1, 0, "05/01/2026")
    sheet.write(1, 1, "Coffee")
    sheet.write(1, 2, 4.25)
    sheet.write(2, 0, "05/02/2026")
    sheet.write(2, 1, "Refund")
    sheet.write(2, 2, -4.25)
    buf = io.BytesIO()
    book.save(buf)

    rows, fmt, errors = parse_statement("statement.xls", buf.getvalue())
    assert errors == 0
    assert fmt == FORMAT_NAMES["amex_xls"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 425),
        ("Refund", "credit", 425),
    ]


def test_parse_statement_xls_rejects_missing_header_row():
    book = Workbook()
    sheet = book.add_sheet("Activity")
    sheet.write(0, 0, "Foo")
    sheet.write(0, 1, "Bar")
    sheet.write(1, 0, "1")
    sheet.write(1, 1, "2")
    buf = io.BytesIO()
    book.save(buf)

    with pytest.raises(ValueError):
        parse_statement("statement.xls", buf.getvalue())


def test_parse_statement_xls_uses_xldate_for_numeric_dates():
    book = Workbook()
    sheet = book.add_sheet("Activity")
    sheet.write(0, 0, "Date")
    sheet.write(0, 1, "Description")
    sheet.write(0, 2, "Amount")
    sheet.write(1, 0, 46143.0)  # 2026-05-01 as Excel serial in 1900 datemode
    sheet.write(1, 1, "Coffee")
    sheet.write(1, 2, 4.25)
    buf = io.BytesIO()
    book.save(buf)

    book_check = xlrd.open_workbook(file_contents=buf.getvalue())
    parsed_date = xlrd.xldate_as_datetime(46143.0, book_check.datemode).date()

    rows, _, _ = parse_statement("statement.xls", buf.getvalue())
    assert len(rows) == 1
    assert rows[0].transaction_date == parsed_date


def test_parse_statement_skips_rows_with_missing_date_silently():
    body = b"Date,Description,Amount\n2026-05-01,Good,4.25\n,Missing date,4.25\n"
    rows, _, errors = parse_statement("statement.csv", body)
    assert len(rows) == 1
    assert errors == 0


def test_parse_statement_counts_malformed_amounts_as_errors():
    body = b"Date,Description,Amount\n2026-05-01,Good,4.25\n2026-05-02,Bad,not-a-number\n"
    rows, _, errors = parse_statement("statement.csv", body)
    assert len(rows) == 1
    assert errors == 1
