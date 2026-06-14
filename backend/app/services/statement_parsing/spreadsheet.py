"""XLS/XLSX statement parsing, including the AmEx preamble/Summary-block shape
and the shared signed-amount resolution for split debit/credit columns."""
import io
from contextlib import closing
from decimal import Decimal
from typing import Optional

from .columns import (
    _has_required_statement_columns,
    _normalize_hdr,
    _spreadsheet_column_info,
    _statement_columns,
)
from .core import (
    FORMAT_NAMES,
    ParsedRow,
    SkippedRow,
    StatementParseResult,
    _cell,
    _dates_ambiguous,
    _is_blank,
    _parse_amount,
    _parse_date,
    _populated_cell,
    _record_skip,
    _resolve_charges_positive,
    _row,
)


def _spreadsheet_signed_amount(
    cells: list,
    amount_col: Optional[int],
    debit_col: Optional[int],
    credit_col: Optional[int],
    source: str,
    invert_amount: bool = True,
) -> Decimal:
    if _populated_cell(cells, credit_col):
        credit_amount = _parse_amount(_cell(cells, credit_col))
        if credit_amount:
            return abs(credit_amount)

    if _populated_cell(cells, debit_col):
        return -abs(_parse_amount(_cell(cells, debit_col)))

    if _populated_cell(cells, amount_col):
        amount = _parse_amount(_cell(cells, amount_col))
        # When the file also has split debit/credit columns the Amount column is
        # already signed — never invert it.
        if source == "checking" or debit_col is not None or credit_col is not None:
            return amount
        # Single Amount column on a card statement: invert only when charges are
        # listed as positive (the resolved convention). Defaults to inverting to
        # preserve the historical AmEx-style behavior for callers that don't pass
        # an explicit decision.
        return -amount if invert_amount else amount

    raise ValueError("row has no amount, debit, or credit value")


def _resolve_spreadsheet_amount_sign(
    data_rows: list,
    amount_col: Optional[int],
    debit_col: Optional[int],
    credit_col: Optional[int],
    source: str,
    charges_positive: Optional[bool],
) -> tuple[bool, bool]:
    """Return (amount_sign_adjustable, charges_positive) for spreadsheet rows.

    Only a single signed Amount column on a card statement is adjustable; split
    debit/credit columns and checking imports carry an unambiguous sign. The
    historical default for card spreadsheets is charges-positive (invert).
    """
    amount_only = (
        amount_col is not None and debit_col is None and credit_col is None and source != "checking"
    )
    if not amount_only:
        return False, False
    amounts: list[Decimal] = []
    for cells in data_rows:
        if not _populated_cell(cells, amount_col):
            continue
        try:
            amounts.append(_parse_amount(_cell(cells, amount_col)))
        except Exception:
            continue
    return True, _resolve_charges_positive(amounts, charges_positive, legacy_default=True)


def _parse_xls(
    raw: bytes,
    source: str = "card",
    charges_positive: Optional[bool] = None,
    day_first: Optional[bool] = None,
) -> StatementParseResult:
    try:
        import xlrd
    except ImportError as exc:
        raise ValueError("XLS imports require the xlrd package. Run pip install -e . in backend.") from exc

    book = xlrd.open_workbook(file_contents=raw)
    sheet = book.sheet_by_index(0)
    data = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]

    header_index = None
    columns: tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]] | None = None
    for idx, cells in enumerate(data[:25]):
        normalized = [_normalize_hdr(c) for c in cells]
        candidate = _statement_columns(normalized)
        if _has_required_statement_columns(candidate):
            header_index = idx
            columns = candidate
            break
    if header_index is None or columns is None:
        fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["amex_xls"]
        return StatementParseResult([], fmt, 0, columns=_spreadsheet_column_info(data))

    date_col, desc_col, amount_col, debit_col, credit_col = columns
    adjustable, resolved_cp = _resolve_spreadsheet_amount_sign(
        data[header_index + 1 :], amount_col, debit_col, credit_col, source, charges_positive
    )
    resolved_df = bool(day_first)
    date_adjustable = _dates_ambiguous([_cell(cells, date_col) for cells in data[header_index + 1 :]])

    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []
    for row_number, cells in enumerate(data[header_index + 1 :], start=header_index + 2):
        if date_col >= len(cells) or desc_col >= len(cells):
            continue
        if (
            _is_blank(cells[date_col])
            and _is_blank(cells[desc_col])
            and not any(_populated_cell(cells, col) for col in (amount_col, debit_col, credit_col))
        ):
            continue
        try:
            raw_date = cells[date_col]
            if isinstance(raw_date, float):
                tx_date = xlrd.xldate_as_datetime(raw_date, book.datemode).date()
            else:
                tx_date = _parse_date(raw_date, resolved_df)
            amount = _spreadsheet_signed_amount(
                cells, amount_col, debit_col, credit_col, source, invert_amount=resolved_cp
            )
            parsed = _row(tx_date, str(cells[desc_col]), amount, row_number, source)
            if parsed:
                rows.append(parsed)
        except Exception as exc:
            _record_skip(skipped, row_number, _cell(cells, date_col), _cell(cells, amount_col if amount_col is not None else debit_col), _cell(cells, desc_col), exc)
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["amex_xls"]
    return StatementParseResult(
        rows, fmt, len(skipped), adjustable, resolved_cp, skipped_rows=skipped,
        date_convention_adjustable=date_adjustable, day_first=resolved_df,
    )


def _parse_xlsx(
    raw: bytes,
    source: str = "card",
    charges_positive: Optional[bool] = None,
    day_first: Optional[bool] = None,
) -> StatementParseResult:
    try:
        import openpyxl
    except ImportError as exc:
        raise ValueError("XLSX imports require the openpyxl package. Run pip install -e . in backend.") from exc

    try:
        with closing(openpyxl.load_workbook(io.BytesIO(raw), data_only=True)) as wb:
            ws = wb.active
            data = [list(row) for row in ws.iter_rows(values_only=True)]
    except Exception as exc:
        raise ValueError("Could not parse XLSX file") from exc

    header_index = None
    columns: tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]] | None = None
    for idx, cells in enumerate(data[:25]):
        normalized = [_normalize_hdr(c) if c is not None else "" for c in cells]
        candidate = _statement_columns(normalized)
        if _has_required_statement_columns(candidate):
            header_index = idx
            columns = candidate
            break
    if header_index is None or columns is None:
        fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["xlsx"]
        return StatementParseResult([], fmt, 0, columns=_spreadsheet_column_info(data))

    date_col, desc_col, amount_col, debit_col, credit_col = columns
    adjustable, resolved_cp = _resolve_spreadsheet_amount_sign(
        data[header_index + 1 :], amount_col, debit_col, credit_col, source, charges_positive
    )
    resolved_df = bool(day_first)
    date_adjustable = _dates_ambiguous([_cell(cells, date_col) for cells in data[header_index + 1 :]])

    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []
    for row_number, cells in enumerate(data[header_index + 1 :], start=header_index + 2):
        if date_col >= len(cells) or desc_col >= len(cells):
            continue
        if (
            _is_blank(cells[date_col])
            and _is_blank(cells[desc_col])
            and not any(_populated_cell(cells, col) for col in (amount_col, debit_col, credit_col))
        ):
            continue
        try:
            tx_date = _parse_date(cells[date_col], resolved_df)
            amount = _spreadsheet_signed_amount(
                cells, amount_col, debit_col, credit_col, source, invert_amount=resolved_cp
            )
            parsed = _row(tx_date, str(cells[desc_col]) if cells[desc_col] is not None else "", amount, row_number, source)
            if parsed:
                rows.append(parsed)
        except Exception as exc:
            _record_skip(skipped, row_number, _cell(cells, date_col), _cell(cells, amount_col if amount_col is not None else debit_col), _cell(cells, desc_col), exc)
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["xlsx"]
    return StatementParseResult(
        rows, fmt, len(skipped), adjustable, resolved_cp, skipped_rows=skipped,
        date_convention_adjustable=date_adjustable, day_first=resolved_df,
    )
