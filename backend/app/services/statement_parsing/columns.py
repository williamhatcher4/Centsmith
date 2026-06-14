"""Header alias tables, header matching, and detected-column metadata.

Owns everything about *finding* the date/description/amount columns in a file;
the format parsers consume the detected tuple and never re-implement matching.
"""
import re
from dataclasses import dataclass
from typing import Optional

from .core import _is_blank, _trunc_diag

DATE_ALIASES = (
    "Date", "Transaction Date", "Trans Date", "Posted Date",
    "Post Date", "Posting Date", "Value Date", "Settlement Date",
)
DESCRIPTION_ALIASES = (
    "Description", "Merchant", "Payee", "Details", "Narrative",
    "Memo", "Transaction Description", "Transaction Details",
    "Reference", "Payee Name", "Name",
)
DEBIT_ALIASES = ("Debit", "Withdrawal", "Withdrawals", "Debit Amount", "Withdrawal Amount")
CREDIT_ALIASES = ("Credit", "Deposit", "Deposits", "Payment", "Payments", "Credit Amount", "Deposit Amount", "Payment Amount")
AMOUNT_ALIASES = ("Amount", "Transaction Amount", "Value", "Net Amount", "Charge", "Charges", "Charge Amount")
NON_AMOUNT_HEADER_TOKENS = ("date", "time", "status", "reference", "ref", "id", "number", "memo", "description", "details")


@dataclass
class StatementColumnInfo:
    """Detected-column metadata surfaced when auto-detection can't map a file.

    Lets the import preview offer a manual column-mapping step instead of failing.
    Columns are referenced by zero-based index into ``headers``/each sample row.
    """
    headers: list[str]
    sample_rows: list[list[str]]
    detected: dict[str, Optional[int]]
    mapping_required: bool


def _normalize_hdr(k: object) -> str:
    return re.sub(r"[.\s:*#()]+", " ", str(k).lower()).strip()


def _header_matches(header: str, alias: str, exact_single_word: bool = False) -> bool:
    normalized_alias = _normalize_hdr(alias)
    if exact_single_word and " " not in normalized_alias:
        return header == normalized_alias
    return header == normalized_alias or header.startswith(f"{normalized_alias} ") or header.endswith(f" {normalized_alias}")


def _looks_like_non_amount_header(header: str) -> bool:
    tokens = set(header.split())
    return any(token in tokens for token in NON_AMOUNT_HEADER_TOKENS)


def _find_header_col(
    headers: list[str],
    aliases: tuple[str, ...],
    exclude: tuple[str, ...] = (),
    allow_non_amount: bool = False,
    exact_single_word: bool = False,
) -> Optional[int]:
    for alias in aliases:
        for idx, header in enumerate(headers):
            if (
                header
                and (allow_non_amount or not _looks_like_non_amount_header(header))
                and _header_matches(header, alias, exact_single_word=exact_single_word)
                and not any(_header_matches(header, blocked, exact_single_word=exact_single_word) for blocked in exclude)
            ):
                return idx
    return None


def _statement_columns(headers: list[str]) -> tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]]:
    date_col = _find_header_col(headers, DATE_ALIASES, allow_non_amount=True)
    desc_col = _find_header_col(headers, DESCRIPTION_ALIASES, allow_non_amount=True)
    debit_col = _find_header_col(headers, DEBIT_ALIASES, exact_single_word=True)
    credit_col = _find_header_col(headers, CREDIT_ALIASES, exact_single_word=True)
    amount_col = _find_header_col(headers, AMOUNT_ALIASES, exclude=DEBIT_ALIASES + CREDIT_ALIASES, exact_single_word=True)
    return date_col, desc_col, amount_col, debit_col, credit_col


def _has_required_statement_columns(columns: tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]]) -> bool:
    date_col, desc_col, amount_col, debit_col, credit_col = columns
    return date_col is not None and desc_col is not None and (amount_col is not None or debit_col is not None or credit_col is not None)


def _detected_dict(columns: tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]]) -> dict[str, Optional[int]]:
    date_col, desc_col, amount_col, debit_col, credit_col = columns
    return {
        "date": date_col,
        "description": desc_col,
        "amount": amount_col,
        "debit": debit_col,
        "credit": credit_col,
    }


def _make_column_info(
    headers: list[str],
    data_rows: list[list],
    columns: tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]],
    mapping_required: bool,
) -> StatementColumnInfo:
    sample = [[_trunc_diag(cell) for cell in row] for row in data_rows[:10]]
    return StatementColumnInfo(
        headers=[_trunc_diag(h) for h in headers],
        sample_rows=sample,
        detected=_detected_dict(columns),
        mapping_required=mapping_required,
    )


def _column_info_from_csv(
    fieldnames: list[str],
    records: list[dict],
    columns: tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]],
) -> StatementColumnInfo:
    data_rows = [[record.get(name, "") for name in fieldnames] for record in records]
    return _make_column_info(list(fieldnames), data_rows, columns, mapping_required=True)


def _pick_spreadsheet_header_idx(data: list[list]) -> int:
    """First row (within the first 25) with at least two populated cells."""
    for idx, cells in enumerate(data[:25]):
        if sum(1 for c in cells if not _is_blank(c)) >= 2:
            return idx
    return 0


def _spreadsheet_column_info(data: list[list]) -> StatementColumnInfo:
    """Build manual-mapping metadata for a spreadsheet whose header wasn't found.

    Picks the first row with at least two populated cells as the header guess and
    presents the rows below it as samples; the user maps columns by position.
    """
    if not data:
        return StatementColumnInfo(headers=[], sample_rows=[], detected=_detected_dict((None,) * 5), mapping_required=True)
    header_idx = _pick_spreadsheet_header_idx(data)
    header_cells = data[header_idx]
    headers = [_trunc_diag(c) for c in header_cells]
    columns = _statement_columns([_normalize_hdr(c) if c is not None else "" for c in header_cells])
    return _make_column_info(headers, data[header_idx + 1 :], columns, mapping_required=True)
