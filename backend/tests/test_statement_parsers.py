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
    parse_statement_ex,
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


def _make_xls(headers: list, data_rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.add_sheet("Activity")
    for col, header in enumerate(headers):
        sheet.write(0, col, header)
    for row_idx, row in enumerate(data_rows, start=1):
        for col, value in enumerate(row):
            sheet.write(row_idx, col, value)
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


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


def test_parse_statement_xls_checking_signed_amount_preserves_sign():
    # Regression: checking XLS with a single signed Amount column should NOT
    # apply the AmEx-style inversion. Positive = deposit (credit), negative = withdrawal (debit).
    book = Workbook()
    sheet = book.add_sheet("Activity")
    sheet.write(0, 0, "Date")
    sheet.write(0, 1, "Description")
    sheet.write(0, 2, "Amount")
    sheet.write(1, 0, "05/01/2026")
    sheet.write(1, 1, "Paycheck")
    sheet.write(1, 2, 1000.00)
    sheet.write(2, 0, "05/02/2026")
    sheet.write(2, 1, "Rent")
    sheet.write(2, 2, -1200.00)
    buf = io.BytesIO()
    book.save(buf)

    rows, fmt, errors = parse_statement("statement.xls", buf.getvalue(), source="checking")
    assert errors == 0
    assert fmt == FORMAT_NAMES["checking"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Paycheck", "credit", 100000),
        ("Rent", "debit", 120000),
    ]


def test_parse_statement_xls_withdrawal_deposit_columns():
    # Regression: XLS checking files with Withdrawal/Deposit headers were rejected.
    book = Workbook()
    sheet = book.add_sheet("Activity")
    sheet.write(0, 0, "Date")
    sheet.write(0, 1, "Description")
    sheet.write(0, 2, "Withdrawal")
    sheet.write(0, 3, "Deposit")
    sheet.write(1, 0, "05/01/2026")
    sheet.write(1, 1, "Paycheck")
    sheet.write(1, 2, "")
    sheet.write(1, 3, 1000.00)
    sheet.write(2, 0, "05/02/2026")
    sheet.write(2, 1, "Rent")
    sheet.write(2, 2, 1200.00)
    sheet.write(2, 3, "")
    buf = io.BytesIO()
    book.save(buf)

    rows, fmt, errors = parse_statement("statement.xls", buf.getvalue(), source="checking")
    assert errors == 0
    assert fmt == FORMAT_NAMES["checking"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Paycheck", "credit", 100000),
        ("Rent", "debit", 120000),
    ]


def test_parse_statement_xls_credit_amount_before_debit_amount():
    # Regression: "Credit Amount" must not also be chosen as the debit/amount column.
    content = _make_xls(
        ["Date", "Description", "Credit Amount", "Debit Amount"],
        [
            ["05/01/2026", "Paycheck", 1000.00, ""],
            ["05/02/2026", "Rent", "", 1200.00],
        ],
    )

    rows, _, errors = parse_statement("statement.xls", content, source="checking")
    assert errors == 0
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Paycheck", "credit", 100000),
        ("Rent", "debit", 120000),
    ]


def test_parse_statement_xls_payee_withdrawal_deposit_columns():
    content = _make_xls(
        ["Date", "Payee", "Withdrawal", "Deposit"],
        [
            ["05/01/2026", "Employer", "", 1000.00],
            ["05/02/2026", "Landlord", 1200.00, ""],
        ],
    )

    rows, fmt, errors = parse_statement("statement.xls", content, source="checking")
    assert errors == 0
    assert fmt == FORMAT_NAMES["checking"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Employer", "credit", 100000),
        ("Landlord", "debit", 120000),
    ]


def test_parse_statement_xls_payment_date_does_not_shadow_amount():
    content = _make_xls(
        ["Date", "Description", "Payment Date", "Amount"],
        [["05/01/2026", "Coffee", "05/03/2026", 4.25]],
    )

    rows, _, errors = parse_statement("statement.xls", content)
    assert errors == 0
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 425),
    ]


def test_parse_statement_xls_payment_method_does_not_shadow_amount():
    content = _make_xls(
        ["Date", "Description", "Payment Method", "Amount"],
        [["05/01/2026", "Coffee", "ACH", 4.25]],
    )

    rows, _, errors = parse_statement("statement.xls", content)
    assert errors == 0
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 425),
    ]


def test_parse_statement_xls_debit_credit_columns_blank_credit_is_debit():
    # Regression: when a credit column exists but is blank on a debit row, the
    # debit value must be treated as a debit, not flipped into a credit.
    book = Workbook()
    sheet = book.add_sheet("Activity")
    sheet.write(0, 0, "Date")
    sheet.write(0, 1, "Description")
    sheet.write(0, 2, "Debit")
    sheet.write(0, 3, "Credit")
    sheet.write(1, 0, "05/01/2026")
    sheet.write(1, 1, "Coffee")
    sheet.write(1, 2, 4.25)
    sheet.write(1, 3, "")
    sheet.write(2, 0, "05/02/2026")
    sheet.write(2, 1, "Refund")
    sheet.write(2, 2, "")
    sheet.write(2, 3, 4.25)
    buf = io.BytesIO()
    book.save(buf)

    rows, _, errors = parse_statement("statement.xls", buf.getvalue())
    assert errors == 0
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 425),
        ("Refund", "credit", 425),
    ]


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


# ---------------------------------------------------------------------------
# XLSX format
# ---------------------------------------------------------------------------

def _make_xlsx(headers: list, data_rows: list[list]) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in data_rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_statement_xlsx_basic():
    content = _make_xlsx(
        ["Date", "Description", "Amount"],
        [["05/01/2026", "Coffee", 4.25], ["05/02/2026", "Refund", -4.25]],
    )
    rows, fmt, errors = parse_statement("statement.xlsx", content)
    assert errors == 0
    assert fmt == FORMAT_NAMES["xlsx"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 425),
        ("Refund", "credit", 425),
    ]


def test_parse_statement_xlsx_checking_source_label():
    content = _make_xlsx(["Date", "Description", "Amount"], [["05/01/2026", "Coffee", 4.25]])
    _, fmt, _ = parse_statement("statement.xlsx", content, source="checking")
    assert fmt == FORMAT_NAMES["checking"]


def test_parse_statement_xlsx_rejects_missing_header_row():
    content = _make_xlsx(["Foo", "Bar"], [["x", "y"]])
    with pytest.raises(ValueError):
        parse_statement("statement.xlsx", content)


def test_parse_statement_xlsx_rejects_malformed_workbook_as_value_error():
    with pytest.raises(ValueError, match="Could not parse XLSX file"):
        parse_statement("statement.xlsx", b"not a workbook")


def test_parse_statement_xlsx_native_date_cell():
    import openpyxl
    from datetime import date as dt
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Date", "Description", "Amount"])
    ws.cell(row=2, column=1, value=dt(2026, 5, 1))
    ws.cell(row=2, column=2, value="Coffee")
    ws.cell(row=2, column=3, value=4.25)
    buf = io.BytesIO()
    wb.save(buf)
    rows, _, errors = parse_statement("statement.xlsx", buf.getvalue())
    assert errors == 0
    assert len(rows) == 1
    assert rows[0].transaction_date == date(2026, 5, 1)


def test_parse_statement_xlsx_credit_column():
    content = _make_xlsx(
        ["Date", "Description", "Amount", "Credit"],
        [["05/01/2026", "Refund", 0.0, 4.25]],
    )
    rows, _, errors = parse_statement("statement.xlsx", content)
    assert errors == 0
    assert rows[0].transaction_type == "credit"
    assert rows[0].amount_cents == 425


def test_parse_statement_xlsx_checking_signed_amount_preserves_sign():
    # Regression: checking XLSX with a single signed Amount column should NOT
    # apply the AmEx-style inversion. Positive = deposit (credit), negative = withdrawal (debit).
    content = _make_xlsx(
        ["Date", "Description", "Amount"],
        [
            ["05/01/2026", "Paycheck", 1000.00],
            ["05/02/2026", "Rent", -1200.00],
        ],
    )
    rows, fmt, errors = parse_statement("statement.xlsx", content, source="checking")
    assert errors == 0
    assert fmt == FORMAT_NAMES["checking"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Paycheck", "credit", 100000),
        ("Rent", "debit", 120000),
    ]


def test_parse_statement_xlsx_withdrawal_deposit_columns():
    # Regression: XLSX checking files with Withdrawal/Deposit headers were rejected.
    content = _make_xlsx(
        ["Date", "Description", "Withdrawal", "Deposit"],
        [
            ["05/01/2026", "Paycheck", "", 1000.00],
            ["05/02/2026", "Rent", 1200.00, ""],
        ],
    )
    rows, fmt, errors = parse_statement("statement.xlsx", content, source="checking")
    assert errors == 0
    assert fmt == FORMAT_NAMES["checking"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Paycheck", "credit", 100000),
        ("Rent", "debit", 120000),
    ]


def test_parse_statement_xlsx_credit_amount_before_debit_amount():
    # Regression: "Credit Amount" must not also be chosen as the debit/amount column.
    content = _make_xlsx(
        ["Date", "Description", "Credit Amount", "Debit Amount"],
        [
            ["05/01/2026", "Paycheck", 1000.00, ""],
            ["05/02/2026", "Rent", "", 1200.00],
        ],
    )

    rows, _, errors = parse_statement("statement.xlsx", content, source="checking")
    assert errors == 0
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Paycheck", "credit", 100000),
        ("Rent", "debit", 120000),
    ]


def test_parse_statement_xlsx_payee_withdrawal_deposit_columns():
    content = _make_xlsx(
        ["Date", "Payee", "Withdrawal", "Deposit"],
        [
            ["05/01/2026", "Employer", "", 1000.00],
            ["05/02/2026", "Landlord", 1200.00, ""],
        ],
    )

    rows, fmt, errors = parse_statement("statement.xlsx", content, source="checking")
    assert errors == 0
    assert fmt == FORMAT_NAMES["checking"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Employer", "credit", 100000),
        ("Landlord", "debit", 120000),
    ]


def test_parse_statement_xlsx_payment_date_does_not_shadow_amount():
    content = _make_xlsx(
        ["Date", "Description", "Payment Date", "Amount"],
        [["05/01/2026", "Coffee", "05/03/2026", 4.25]],
    )

    rows, _, errors = parse_statement("statement.xlsx", content)
    assert errors == 0
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 425),
    ]


def test_parse_statement_xlsx_payment_method_does_not_shadow_amount():
    content = _make_xlsx(
        ["Date", "Description", "Payment Method", "Amount"],
        [["05/01/2026", "Coffee", "ACH", 4.25]],
    )

    rows, _, errors = parse_statement("statement.xlsx", content)
    assert errors == 0
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 425),
    ]


def test_parse_statement_xlsx_debit_credit_columns_blank_credit_is_debit():
    # Regression: when a credit column exists but is blank on a debit row, the
    # debit value must be treated as a debit, not flipped into a credit.
    content = _make_xlsx(
        ["Date", "Description", "Debit", "Credit"],
        [
            ["05/01/2026", "Coffee", 4.25, ""],
            ["05/02/2026", "Refund", "", 4.25],
        ],
    )
    rows, _, errors = parse_statement("statement.xlsx", content)
    assert errors == 0
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 425),
        ("Refund", "credit", 425),
    ]


def test_parse_statement_xlsx_malformed_amount_counted_as_error():
    content = _make_xlsx(
        ["Date", "Description", "Amount"],
        [["05/01/2026", "Good", 4.25], ["05/02/2026", "Bad", "not-a-number"]],
    )
    rows, _, errors = parse_statement("statement.xlsx", content)
    assert len(rows) == 1
    assert errors == 1


# ---------------------------------------------------------------------------
# OFX / QFX format
# ---------------------------------------------------------------------------

_OFX_SGML = b"""\
OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<BANKTRNLIST>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260501
<TRNAMT>-4.25
<FITID>001
<NAME>Coffee shop
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260502
<TRNAMT>4.25
<FITID>002
<NAME>Refund
</STMTTRN>
</BANKTRNLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""

_OFX_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<OFX>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STMTRS>
        <BANKTRNLIST>
          <STMTTRN>
            <TRNTYPE>DEBIT</TRNTYPE>
            <DTPOSTED>20260501</DTPOSTED>
            <TRNAMT>-4.25</TRNAMT>
            <FITID>001</FITID>
            <NAME>Coffee shop</NAME>
          </STMTTRN>
          <STMTTRN>
            <TRNTYPE>CREDIT</TRNTYPE>
            <DTPOSTED>20260502</DTPOSTED>
            <TRNAMT>4.25</TRNAMT>
            <FITID>002</FITID>
            <NAME>Refund</NAME>
          </STMTTRN>
        </BANKTRNLIST>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>
"""


_OFX_SGML_HYBRID = b"""\
OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<BANKTRNLIST>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260501
<TRNAMT>-4.25
<FITID>001</FITID>
<NAME>Coffee shop</NAME>
</STMTTRN>
</BANKTRNLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""


def test_parse_statement_ofx_sgml():
    rows, fmt, errors = parse_statement("statement.ofx", _OFX_SGML)
    assert errors == 0
    assert fmt == FORMAT_NAMES["ofx"]
    assert len(rows) == 2
    assert rows[0].transaction_date == date(2026, 5, 1)
    assert rows[0].transaction_type == "debit"
    assert rows[0].amount_cents == 425
    assert rows[0].description == "Coffee shop"
    assert rows[1].transaction_type == "credit"


def test_parse_statement_ofx_xml():
    rows, fmt, errors = parse_statement("statement.ofx", _OFX_XML)
    assert errors == 0
    assert fmt == FORMAT_NAMES["ofx"]
    assert [(r.transaction_type, r.amount_cents) for r in rows] == [("debit", 425), ("credit", 425)]


def test_parse_statement_ofx_sgml_hybrid_falls_back_from_xml_detection():
    # Some OFX 1.x exports close a few leaf tags, but are still SGML because
    # most tags are unclosed. These should fall back instead of failing XML parse.
    rows, fmt, errors = parse_statement("statement.ofx", _OFX_SGML_HYBRID)
    assert errors == 0
    assert fmt == FORMAT_NAMES["ofx"]
    assert len(rows) == 1
    assert rows[0].description == "Coffee shop"
    assert rows[0].transaction_type == "debit"
    assert rows[0].amount_cents == 425


_OFX_XML_NAMESPACED = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<OFX xmlns="http://ofx.net/types/2003/04">
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STMTRS>
        <BANKTRNLIST>
          <STMTTRN>
            <TRNTYPE>DEBIT</TRNTYPE>
            <DTPOSTED>20260501</DTPOSTED>
            <TRNAMT>-4.25</TRNAMT>
            <FITID>001</FITID>
            <NAME>Coffee shop</NAME>
          </STMTTRN>
          <STMTTRN>
            <TRNTYPE>CREDIT</TRNTYPE>
            <DTPOSTED>20260502</DTPOSTED>
            <TRNAMT>4.25</TRNAMT>
            <FITID>002</FITID>
            <NAME>Refund</NAME>
          </STMTTRN>
        </BANKTRNLIST>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>
"""


def test_parse_statement_ofx_xml_with_default_namespace():
    # Regression: OFX 2.x documents declare a default namespace on <OFX>.
    # ElementTree expands child tags to {ns}STMTTRN; iteration must match by local name.
    rows, fmt, errors = parse_statement("statement.ofx", _OFX_XML_NAMESPACED)
    assert errors == 0
    assert fmt == FORMAT_NAMES["ofx"]
    assert len(rows) == 2
    assert rows[0].description == "Coffee shop"
    assert rows[0].transaction_type == "debit"
    assert rows[0].amount_cents == 425
    assert rows[1].description == "Refund"
    assert rows[1].transaction_type == "credit"


def test_parse_statement_qfx_extension_uses_ofx_label():
    rows, fmt, errors = parse_statement("statement.qfx", _OFX_SGML)
    assert fmt == FORMAT_NAMES["ofx"]
    assert len(rows) == 2


def test_parse_statement_ofx_missing_amount_counted_as_error():
    body = b"""\
OFXHEADER:100
<OFX>
<BANKTRNLIST>
<STMTTRN>
<DTPOSTED>20260501
<NAME>No amount
</STMTTRN>
</BANKTRNLIST>
</OFX>
"""
    rows, _, errors = parse_statement("statement.ofx", body)
    assert len(rows) == 0
    assert errors == 1


def test_parse_statement_ofx_sgml_explicit_plus_amount():
    body = b"""\
OFXHEADER:100
DATA:OFXSGML
VERSION:102
<OFX>
<BANKTRNLIST>
<STMTTRN>
<DTPOSTED>20260501
<TRNAMT>+100.00
<NAME>Refund
</STMTTRN>
</BANKTRNLIST>
</OFX>
"""
    rows, fmt, errors = parse_statement("statement.ofx", body)
    assert errors == 0
    assert fmt == FORMAT_NAMES["ofx"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Refund", "credit", 10000),
    ]


def test_parse_statement_ofx_checking_source_label():
    _, fmt, _ = parse_statement("statement.ofx", _OFX_SGML, source="checking")
    assert fmt == FORMAT_NAMES["ofx"]


# ---------------------------------------------------------------------------
# Expanded CSV aliases and delimiter detection
# ---------------------------------------------------------------------------

def test_parse_statement_csv_post_date_column():
    body = b"Post Date,Description,Amount\n05/01/2026,Coffee,-4.25\n"
    rows, _, errors = parse_statement("statement.csv", body)
    assert errors == 0
    assert len(rows) == 1
    assert rows[0].transaction_date == date(2026, 5, 1)


def test_parse_statement_csv_memo_as_description():
    body = b"Date,Memo,Amount\n2026-05-01,Grocery store,-42.50\n"
    rows, _, errors = parse_statement("statement.csv", body)
    assert errors == 0
    assert rows[0].description == "Grocery store"


def test_parse_statement_csv_period_in_header_normalized():
    # "Trans. Date" should match the "Trans Date" alias after period normalization
    body = b"Trans. Date,Description,Amount\n05/01/2026,Coffee,-4.25\n"
    rows, _, errors = parse_statement("statement.csv", body)
    assert errors == 0
    assert len(rows) == 1
    assert rows[0].transaction_date == date(2026, 5, 1)


def test_parse_statement_csv_tab_delimited():
    body = b"Date\tDescription\tAmount\n2026-05-01\tCoffee\t-4.25\n2026-05-02\tRefund\t4.25\n"
    rows, fmt, errors = parse_statement("statement.csv", body)
    assert errors == 0
    assert fmt == FORMAT_NAMES["generic"]
    assert len(rows) == 2
    assert rows[0].transaction_type == "debit"
    assert rows[1].transaction_type == "credit"


def test_parse_statement_csv_semicolon_delimited():
    body = b"Date;Description;Amount\n2026-05-01;Coffee;-4.25\n2026-05-02;Refund;4.25\n"
    rows, fmt, errors = parse_statement("statement.csv", body)
    assert errors == 0
    assert fmt == FORMAT_NAMES["generic"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 425),
        ("Refund", "credit", 425),
    ]


def test_parse_statement_csv_pipe_delimited():
    body = b"Date|Description|Amount\n2026-05-01|Coffee|-4.25\n2026-05-02|Refund|4.25\n"
    rows, fmt, errors = parse_statement("statement.csv", body)
    assert errors == 0
    assert fmt == FORMAT_NAMES["generic"]
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 425),
        ("Refund", "credit", 425),
    ]


# ---------------------------------------------------------------------------
# Review regression fixes
# ---------------------------------------------------------------------------

def test_parse_statement_csv_comma_with_semicolons_and_pipes_in_descriptions():
    # Regression (#2): a comma-separated file whose descriptions contain ';' and
    # '|' must not be mis-detected as semicolon/pipe-delimited (which yielded 0 rows).
    body = (
        b"Date,Description,Amount\n"
        b"2026-05-01,Amazon.com*ABC; ref:123|456,-4.25\n"
        b"2026-05-02,Store; aisle|7,-9.50\n"
    )
    rows, fmt, errors = parse_statement("statement.csv", body)
    assert errors == 0
    assert fmt == FORMAT_NAMES["generic"]
    assert len(rows) == 2
    assert rows[0].description == "Amazon.com*ABC; ref:123|456"
    assert rows[0].transaction_type == "debit"
    assert rows[0].amount_cents == 425


def test_parse_statement_csv_colon_and_paren_headers():
    # Regression (#8): headers like "Date:" and "(Amount)" must normalize and match.
    body = b"Date:,Description,(Amount)\n2026-05-01,Coffee,-4.25\n"
    rows, _, errors = parse_statement("statement.csv", body)
    assert errors == 0
    assert len(rows) == 1
    assert rows[0].description == "Coffee"
    assert rows[0].transaction_type == "debit"
    assert rows[0].amount_cents == 425


def test_parse_statement_xls_card_signed_amount_with_credit_column_not_inverted():
    # Regression (#3): when split debit/credit columns exist, the Amount column is
    # already signed — a charge (negative Amount, blank Credit) must stay a debit.
    content = _make_xls(
        ["Date", "Description", "Amount", "Credit"],
        [
            ["05/01/2026", "Coffee", -50.00, ""],
            ["05/02/2026", "Payment", 50.00, 50.00],
        ],
    )
    rows, _, errors = parse_statement("statement.xls", content)
    assert errors == 0
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 5000),
        ("Payment", "credit", 5000),
    ]


def test_parse_statement_xlsx_card_signed_amount_with_credit_column_not_inverted():
    # Regression (#3): XLSX mirror of the signed-amount-with-credit-column case.
    content = _make_xlsx(
        ["Date", "Description", "Amount", "Credit"],
        [
            ["05/01/2026", "Coffee", -50.00, ""],
            ["05/02/2026", "Payment", 50.00, 50.00],
        ],
    )
    rows, _, errors = parse_statement("statement.xlsx", content)
    assert errors == 0
    assert [(r.description, r.transaction_type, r.amount_cents) for r in rows] == [
        ("Coffee", "debit", 5000),
        ("Payment", "credit", 5000),
    ]


def test_parse_statement_xls_row_without_amount_counts_as_error():
    # Regression (#14): a row with date+description but no amount cell is surfaced
    # as a skipped error, not silently dropped.
    content = _make_xls(
        ["Date", "Description", "Amount"],
        [["05/01/2026", "Good", 4.25], ["05/02/2026", "No amount", ""]],
    )
    rows, _, errors = parse_statement("statement.xls", content)
    assert len(rows) == 1
    assert errors == 1


def test_parse_statement_xlsx_row_without_amount_counts_as_error():
    # Regression (#14): XLSX mirror of the no-amount-row case.
    content = _make_xlsx(
        ["Date", "Description", "Amount"],
        [["05/01/2026", "Good", 4.25], ["05/02/2026", "No amount", ""]],
    )
    rows, _, errors = parse_statement("statement.xlsx", content)
    assert len(rows) == 1
    assert errors == 1


def test_parse_statement_xlsx_error_message_has_no_internal_detail():
    # Regression (#13): the 400 detail must not leak openpyxl/library internals.
    with pytest.raises(ValueError) as exc_info:
        parse_statement("statement.xlsx", b"not a workbook")
    assert str(exc_info.value) == "Could not parse XLSX file"


def test_parse_statement_ofx_sgml_prefers_name_over_memo():
    # Regression (#1): SGML must prefer NAME over MEMO (matching the XML path) so
    # the same statement hashes/displays identically across OFX 1.x and 2.x.
    body = b"""\
OFXHEADER:100
DATA:OFXSGML
<OFX>
<BANKTRNLIST>
<STMTTRN>
<DTPOSTED>20260501
<TRNAMT>-4.25
<MEMO>Card purchase 1234
<NAME>Starbucks
</STMTTRN>
</BANKTRNLIST>
</OFX>
"""
    rows, _, errors = parse_statement("statement.ofx", body)
    assert errors == 0
    assert len(rows) == 1
    assert rows[0].description == "Starbucks"


def test_parse_statement_ofx_sgml_unterminated_last_txn_does_not_absorb_following_section():
    # Regression (#7): a final STMTTRN missing its closing tag must not absorb a
    # following balance section and borrow its date.
    body = b"""\
OFXHEADER:100
DATA:OFXSGML
<OFX>
<BANKTRNLIST>
<STMTTRN>
<TRNAMT>-4.25
<NAME>Coffee shop
</BANKTRNLIST>
<LEDGERBAL>
<DTPOSTED>20260601
<BALAMT>1234.56
</LEDGERBAL>
</OFX>
"""
    rows, _, errors = parse_statement("statement.ofx", body)
    # Transaction has no DTPOSTED of its own → counted as an error, not silently
    # dated from the trailing balance section.
    assert rows == []
    assert errors == 1


def test_parse_statement_ofx_valid_xml_without_transactions_falls_back_to_sgml():
    # Regression (#5): a buffer that parses as a valid but transaction-less XML
    # tree (closing leaf tags tripped XML detection) must recover SGML-style
    # transactions instead of silently returning zero.
    body = (
        b"OFXHEADER:100\nDATA:OFXSGML\n"
        b"<OFX><![CDATA[\n"
        b"<STMTTRN>\n<DTPOSTED>20260501\n<TRNAMT>-4.25\n<NAME>Coffee shop</NAME>\n</STMTTRN>\n"
        b"]]></OFX>\n"
    )
    rows, fmt, errors = parse_statement("statement.ofx", body)
    assert fmt == FORMAT_NAMES["ofx"]
    assert errors == 0
    assert len(rows) == 1
    assert rows[0].description == "Coffee shop"
    assert rows[0].transaction_date == date(2026, 5, 1)


# ---------------------------------------------------------------------------
# Single Amount-column sign convention (charges-positive toggle)
# ---------------------------------------------------------------------------

def test_parse_statement_amex_csv_charges_positive_auto_detected():
    # AmEx "formal" CSV lists charges as positive and payments as negative. The
    # dominant positive sign auto-detects the charges-positive convention, so
    # charges become debits and the payment becomes a credit.
    body = (
        b"Date,Date Processed,Description,Amount,Flexible\n"
        b"20 Dec 2025,20 Dec 2025,Airalo,42.09,FS\n"
        b"19 Dec 2025,19 Dec 2025,Uber,10.67,FS\n"
        b"11 Dec 2025,11 Dec 2025,PAYMENT RECEIVED - THANK YOU,-19275.99,\n"
    )
    result = parse_statement_ex("amex.csv", body)
    assert result.skipped_errors == 0
    assert result.statement_format == FORMAT_NAMES["generic"]
    assert result.amount_sign_adjustable is True
    assert result.charges_positive is True
    assert [(r.description, r.transaction_type) for r in result.rows] == [
        ("Airalo", "debit"),
        ("Uber", "debit"),
        ("PAYMENT RECEIVED - THANK YOU", "credit"),
    ]


def test_parse_statement_amount_csv_explicit_charges_positive_overrides():
    body = (
        b"Date,Description,Amount\n"
        b"2026-05-01,Coffee,4.25\n"
        b"2026-05-02,Lunch,8.00\n"
        b"2026-05-03,Refund,-1.00\n"
    )
    # Auto: dominant positive (2 charges vs 1 refund) -> charges-positive -> Coffee is a debit.
    auto = parse_statement_ex("s.csv", body)
    assert auto.charges_positive is True
    assert auto.rows[0].transaction_type == "debit"
    # Forcing charges-negative keeps a positive Amount as a credit.
    forced = parse_statement_ex("s.csv", body, charges_positive=False)
    assert forced.charges_positive is False
    assert forced.rows[0].transaction_type == "credit"


def test_parse_statement_amount_csv_charges_negative_default_preserved():
    # Standard bank CSV (charges-negative dominant) is unchanged.
    body = (
        b"Date,Description,Amount\n"
        b"2026-05-01,Coffee,-5.50\n"
        b"2026-05-02,Salary,2500.00\n"
        b"2026-05-03,Groceries,-85.20\n"
    )
    result = parse_statement_ex("s.csv", body)
    assert result.amount_sign_adjustable is True
    assert result.charges_positive is False
    assert [(r.description, r.transaction_type) for r in result.rows] == [
        ("Coffee", "debit"),
        ("Salary", "credit"),
        ("Groceries", "debit"),
    ]


def test_amount_sign_not_adjustable_for_debit_credit_columns():
    body = b"Date,Description,Debit,Credit\n2026-05-01,Coffee,4.25,\n"
    result = parse_statement_ex("s.csv", body)
    assert result.amount_sign_adjustable is False


def test_amount_sign_not_adjustable_for_headerless_csv():
    body = b"2026-05-01,Coffee,4.25,\n"
    result = parse_statement_ex("s.csv", body)
    assert result.amount_sign_adjustable is False


def test_amount_sign_not_adjustable_for_ofx():
    result = parse_statement_ex("statement.ofx", _OFX_SGML)
    assert result.amount_sign_adjustable is False


def test_amount_sign_not_adjustable_for_checking_csv():
    body = (
        b"Date,Description,Amount\n"
        b"2026-05-01,Paycheck,1000.00\n"
        b"2026-05-02,Rent,-1200.00\n"
    )
    result = parse_statement_ex("s.csv", body, source="checking")
    assert result.amount_sign_adjustable is False
    # Checking preserves the signed amount regardless of dominant sign.
    assert [(r.description, r.transaction_type) for r in result.rows] == [
        ("Paycheck", "credit"),
        ("Rent", "debit"),
    ]


def test_amount_sign_adjustable_for_amex_xlsx():
    content = _make_xlsx(
        ["Date", "Description", "Amount"],
        [["05/01/2026", "Coffee", 4.25], ["05/02/2026", "Uber", 9.50]],
    )
    result = parse_statement_ex("statement.xlsx", content)
    assert result.amount_sign_adjustable is True
    assert result.charges_positive is True
    assert [r.transaction_type for r in result.rows] == ["debit", "debit"]
