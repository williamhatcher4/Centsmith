"""Explicit column-mapped parsing for unfamiliar bank exports and saved
import profiles."""
import csv
import io
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from .columns import _pick_spreadsheet_header_idx
from .core import (
    FORMAT_NAMES,
    ParsedRow,
    SkippedRow,
    StatementParseResult,
    _assign_occurrences,
    _cell,
    _dates_ambiguous,
    _is_blank,
    _parse_amount,
    _parse_date,
    _record_skip,
    _row,
)
from .csv_parser import _detect_delimiter


@dataclass
class ColumnMapping:
    """An explicit user/profile-supplied column assignment for an import.

    ``amount_convention`` is one of ``signed`` (the Amount column is already
    signed), ``charges_positive`` (purchases are positive → invert), or
    ``charges_negative`` (purchases are negative → keep as-is). Either
    ``amount_column`` or at least one of ``debit_column``/``credit_column`` must
    be set. ``date_convention`` is ``"mdy"``, ``"dmy"``, or None (default
    month-first) for ambiguous numeric dates.
    """
    date_column: int
    description_column: int
    amount_column: Optional[int] = None
    debit_column: Optional[int] = None
    credit_column: Optional[int] = None
    amount_convention: str = "signed"
    date_convention: Optional[str] = None


def _extract_grid(filename: str, content: bytes) -> tuple[list[str], list[list]]:
    """Return (headers, data_rows) aligned with the column info shown for mapping.

    CSV uses the same DictReader/delimiter logic as ``_column_info_from_csv``;
    spreadsheets use the same header-row pick as ``_spreadsheet_column_info`` so a
    user-supplied column index refers to the column they actually saw.
    """
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "xls":
        import xlrd

        try:
            book = xlrd.open_workbook(file_contents=content)
            sheet = book.sheet_by_index(0)
            data = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
        except Exception as exc:
            raise ValueError("Could not parse XLS file") from exc
        idx = _pick_spreadsheet_header_idx(data)
        headers = [str(c) for c in data[idx]] if data else []
        return headers, data[idx + 1 :]
    if suffix == "xlsx":
        import openpyxl

        try:
            with closing(openpyxl.load_workbook(io.BytesIO(content), data_only=True)) as wb:
                ws = wb.active
                data = [list(row) for row in ws.iter_rows(values_only=True)]
        except Exception as exc:
            raise ValueError("Could not parse XLSX file") from exc
        idx = _pick_spreadsheet_header_idx(data)
        headers = [str(c) if c is not None else "" for c in data[idx]] if data else []
        return headers, data[idx + 1 :]

    text = content.decode("utf-8-sig", errors="replace")
    delimiter = _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fieldnames = list(reader.fieldnames or [])
    records = list(reader)
    data_rows = [[record.get(name, "") for name in fieldnames] for record in records]
    return fieldnames, data_rows


def _coerce_mapping_date(cell: object, day_first: Optional[bool] = None) -> date:
    """Parse a date from a mapped cell, handling raw Excel serial-date floats."""
    if isinstance(cell, float):
        try:
            import xlrd

            return xlrd.xldate_as_datetime(cell, 0).date()
        except Exception:
            pass
    return _parse_date(cell, day_first)


def _mapping_signed_amount(cells: list, mapping: ColumnMapping) -> Decimal:
    if mapping.debit_column is not None or mapping.credit_column is not None:
        credit = _cell(cells, mapping.credit_column)
        debit = _cell(cells, mapping.debit_column)
        if _is_blank(credit) and _is_blank(debit):
            raise ValueError("row has no amount, debit, or credit value")
        c = _parse_amount(credit) if not _is_blank(credit) else Decimal("0")
        d = _parse_amount(debit) if not _is_blank(debit) else Decimal("0")
        return c if c else -abs(d)
    raw = _cell(cells, mapping.amount_column)
    if _is_blank(raw):
        raise ValueError("row has no amount, debit, or credit value")
    amount = _parse_amount(raw)
    # charges_positive: purchases listed as positive → invert so they become debits.
    # signed / charges_negative: the column is already correctly signed → keep.
    if mapping.amount_convention == "charges_positive":
        return -amount
    return amount


def parse_statement_with_mapping(
    filename: str,
    content: bytes,
    source: str,
    mapping: ColumnMapping,
    day_first: Optional[bool] = None,
) -> StatementParseResult:
    """Parse a statement using an explicit, user/profile-supplied column mapping.

    Used when auto-detection can't identify the columns (unfamiliar bank export)
    or when a saved import profile pins the layout for a known bank. An explicit
    ``day_first`` (the preview toggle) wins over the mapping's saved
    ``date_convention``; both default to month-first.
    """
    if day_first is None and mapping.date_convention is not None:
        day_first = mapping.date_convention == "dmy"
    resolved_df = bool(day_first)
    headers, data_rows = _extract_grid(filename, content)
    date_adjustable = _dates_ambiguous([_cell(cells, mapping.date_column) for cells in data_rows])
    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []
    for i, cells in enumerate(data_rows, start=2):
        raw_date = _cell(cells, mapping.date_column)
        raw_desc = _cell(cells, mapping.description_column)
        amount_hint_col = mapping.amount_column if mapping.amount_column is not None else mapping.debit_column
        if _is_blank(raw_date) and _is_blank(raw_desc):
            continue
        try:
            tx_date = _coerce_mapping_date(raw_date, resolved_df)
            signed = _mapping_signed_amount(cells, mapping)
            parsed = _row(tx_date, str(raw_desc) if raw_desc is not None else "", signed, i, source)
            if parsed:
                rows.append(parsed)
        except Exception as exc:
            _record_skip(skipped, i, raw_date, _cell(cells, amount_hint_col), raw_desc, exc)
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["generic"]
    result = StatementParseResult(
        rows, fmt, len(skipped), skipped_rows=skipped,
        date_convention_adjustable=date_adjustable, day_first=resolved_df,
    )
    _assign_occurrences(result.rows, source)
    return result
