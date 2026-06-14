"""Statement parsing package — CSV/XLS/XLSX/OFX/QFX bank statement parsers.

Split out of the former single-module ``statement_import_service`` (plan item
P4.2) with zero logic changes:

- ``core``        — result dataclasses, date/amount/hash/occurrence helpers,
                    sanitized skipped-row diagnostics
- ``columns``     — header alias tables, header matching, detected-column info
- ``csv_parser``  — Account Activity / generic / checking CSV parsing
- ``spreadsheet`` — XLS/XLSX parsing (AmEx preamble shape, split debit/credit)
- ``ofx``         — OFX/QFX (XML, SGML, hybrids)
- ``mapping``     — explicit column-mapped parsing for unfamiliar exports/profiles

This ``__init__`` owns the file-extension dispatch and re-exports the public
surface (plus the helpers the test suite exercises directly) so existing
imports keep working.
"""
from typing import Optional

from .columns import (
    AMOUNT_ALIASES,
    CREDIT_ALIASES,
    DATE_ALIASES,
    DEBIT_ALIASES,
    DESCRIPTION_ALIASES,
    NON_AMOUNT_HEADER_TOKENS,
    StatementColumnInfo,
)
from .core import (
    FORMAT_NAMES,
    MAX_DIAG_FIELD_LEN,
    ParsedRow,
    SkippedRow,
    StatementParseResult,
    _assign_occurrences,
    _dates_ambiguous,
    _is_blank,
    _looks_like_date,
    _parse_amount,
    _parse_date,
    _source_hash,
    _to_cents,
)
from .csv_parser import _parse_csv
from .mapping import ColumnMapping, parse_statement_with_mapping
from .ofx import _parse_ofx
from .spreadsheet import _parse_xls, _parse_xlsx

__all__ = [
    # Public surface
    "AMOUNT_ALIASES",
    "CREDIT_ALIASES",
    "ColumnMapping",
    "DATE_ALIASES",
    "DEBIT_ALIASES",
    "DESCRIPTION_ALIASES",
    "FORMAT_NAMES",
    "MAX_DIAG_FIELD_LEN",
    "NON_AMOUNT_HEADER_TOKENS",
    "ParsedRow",
    "SkippedRow",
    "StatementColumnInfo",
    "StatementParseResult",
    "parse_statement",
    "parse_statement_ex",
    "parse_statement_with_mapping",
    # Helpers exercised directly by the test suite
    "_assign_occurrences",
    "_dates_ambiguous",
    "_is_blank",
    "_looks_like_date",
    "_parse_amount",
    "_parse_date",
    "_source_hash",
    "_to_cents",
]


def parse_statement_ex(
    filename: str,
    content: bytes,
    source: str = "card",
    charges_positive: Optional[bool] = None,
    day_first: Optional[bool] = None,
) -> StatementParseResult:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "xls":
        result = _parse_xls(content, source, charges_positive, day_first)
    elif suffix == "xlsx":
        result = _parse_xlsx(content, source, charges_positive, day_first)
    elif suffix in ("ofx", "qfx"):
        # OFX dates are YYYYMMDD — never MM/DD vs DD/MM ambiguous.
        result = _parse_ofx(content, source)
    else:
        result = _parse_csv(content, source, charges_positive, day_first)
    _assign_occurrences(result.rows, source)
    return result


def parse_statement(
    filename: str,
    content: bytes,
    source: str = "card",
    charges_positive: Optional[bool] = None,
    day_first: Optional[bool] = None,
) -> tuple[list[ParsedRow], str, int]:
    result = parse_statement_ex(filename, content, source, charges_positive, day_first)
    return result.rows, result.statement_format, result.skipped_errors
