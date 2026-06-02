"""Sanitized AmEx XLS fixture: structure of a real American Express export.

The real export (``statements/Dan AMex Transactions.xls``) is gitignored because
it contains real PII. This module recreates its *structure* with fake data so
the parser and the full import -> spending/income chain can be tested against a
realistic file:

- a preamble (title, account number, date range) before the table,
- a "Summary" block whose ``Total`` column holds ``$``-formatted amounts,
- the real transaction header at row 11 (0-based),
- a 10-column header with competing aliases (``Date`` vs ``Date Processed``,
  ``Description`` vs ``Merchant``, ``Amount`` next to ``Foreign Spend`` etc.),
- charges-positive amounts with ``$``/comma formatting and period-in-month dates.

It is named without a ``test_`` prefix so pytest does not collect it. Both
``test_statement_parsers.py`` and ``test_backend_flows.py`` import from it, and
``build_sanitized_amex_xls`` generates the committed
``tests/fixtures/amex_sanitized.xls`` artifact.
"""

import io
from datetime import date
from pathlib import Path

from xlwt import Workbook

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "amex_sanitized.xls"

# The 10-column transaction header, mirroring the real export. Multiple columns
# look like date/description/amount aliases; the parser must pick Date(0),
# Description(2) and Amount(3) and ignore the rest.
HEADER = [
    "Date",
    "Date Processed",
    "Description",
    "Amount",
    "Foreign Spend Amount",
    "Commission",
    "Exchange Rate",
    "Merchant",
    "Merchant Address",
    "Additional Information",
]

# Fake transactions in AmEx "formal" shape: charges positive, payments/refunds
# negative. Descriptions are padded (the parser must strip them) and amounts are
# ``$``-strings (one with a thousands comma) just like the real file.
# (date_string, description, amount_string)
SANITIZED_ROWS = [
    ("01 May 2026", "GROCERY MART        ", "$100.00"),
    ("02 May 2026", "CAFE EXAMPLE", "$25.00"),
    ("03 May 2026", "BIG BOX STORE", "$1,000.00"),
    ("15 Apr. 2026", "GROCERY MART        ", "$60.00"),
    ("04 May 2026", "CAFE EXAMPLE REFUND", "-$5.00"),
    ("10 May 2026", "PAYMENT RECEIVED - THANK YOU", "-$200.00"),
]


def build_sanitized_amex_xls() -> bytes:
    """Build the sanitized ``.xls`` bytes (all cells written as strings)."""
    book = Workbook()
    sheet = book.add_sheet("Transaction Details")

    # Preamble (rows 0-5).
    sheet.write(0, 1, "Transaction Detail")
    sheet.write(0, 2, "American Express")
    sheet.write(1, 2, "01 Jan. 2026 - 22 May 2026")
    sheet.write(2, 1, "Account Number: XXXX-XXXXXX-X1234")

    # Summary block (rows 6-9): a ``Total`` column with ``$``-amounts that must
    # not be mistaken for the transaction header.
    sheet.write(6, 0, "Summary")
    sheet.write(6, 3, "Total")
    sheet.write(7, 0, "Charges & Adjustments")
    sheet.write(7, 3, "$1,185.00")
    sheet.write(8, 0, "Payments & Credits")
    sheet.write(8, 3, "$205.00")
    sheet.write(9, 0, "Total")
    sheet.write(9, 3, "$980.00")

    # Row 10 intentionally blank. Header at row 11.
    for col, label in enumerate(HEADER):
        sheet.write(11, col, label)

    # Transaction rows start at row 12. Date(0), Date Processed(1),
    # Description(2), Amount(3); remaining columns left blank.
    row_idx = 12
    for date_str, description, amount_str in SANITIZED_ROWS:
        sheet.write(row_idx, 0, date_str)
        sheet.write(row_idx, 1, date_str)
        sheet.write(row_idx, 2, description)
        sheet.write(row_idx, 3, amount_str)
        sheet.write(row_idx, 7, description.strip())
        row_idx += 1

    # One trailing fully-blank row (the parser must skip it without erroring).
    sheet.write(row_idx, 0, "")

    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Expected results (single source of truth for both tests).
#
# Single Amount column on a card statement -> amount_sign_adjustable; 4 positives
# vs 2 negatives -> charges_positive=True -> charges become debits, negatives
# become credits.
# ---------------------------------------------------------------------------

# (description, transaction_type, amount_cents, transaction_date)
EXPECTED_PARSED = [
    ("GROCERY MART", "debit", 10000, date(2026, 5, 1)),
    ("CAFE EXAMPLE", "debit", 2500, date(2026, 5, 2)),
    ("BIG BOX STORE", "debit", 100000, date(2026, 5, 3)),
    ("GROCERY MART", "debit", 6000, date(2026, 4, 15)),
    ("CAFE EXAMPLE REFUND", "credit", 500, date(2026, 5, 4)),
    ("PAYMENT RECEIVED - THANK YOU", "credit", 20000, date(2026, 5, 10)),
]

# After a card import: the payment credit is dropped, the rest are stored.
EXPECTED_IMPORTED = 5
EXPECTED_IGNORED_CREDITS = 1

# How the imported rows are categorized in the end-to-end test (by description).
CATEGORY_ASSIGNMENTS = {
    "Groceries": ["GROCERY MART"],  # both grocery debits share this description
    "Dining": ["CAFE EXAMPLE", "CAFE EXAMPLE REFUND"],
    "Shopping": ["BIG BOX STORE"],
}

# Spending = 100 + 25 + 1000 + 60 charges (118500c) minus the 5.00 refund
# credit = 118000c. Income = 0 (no Income/Reimbursement category).
EXPECTED_SPENDING_CENTS = 118000
EXPECTED_SPENDING_BY_CATEGORY = {
    "Shopping": 100000,
    "Groceries": 16000,
    "Dining": 2000,
}
EXPECTED_INCOME_CENTS = 0
