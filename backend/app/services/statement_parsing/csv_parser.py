"""CSV statement parsing: delimiter detection, the headerless Account Activity
shape, and header-driven generic/checking CSVs."""
import csv
import io
from decimal import Decimal
from typing import Optional

from .columns import (
    AMOUNT_ALIASES,
    CREDIT_ALIASES,
    DATE_ALIASES,
    DEBIT_ALIASES,
    DESCRIPTION_ALIASES,
    _column_info_from_csv,
    _has_required_statement_columns,
    _normalize_hdr,
    _statement_columns,
)
from .core import (
    FORMAT_NAMES,
    ParsedRow,
    SkippedRow,
    StatementParseResult,
    _dates_ambiguous,
    _looks_like_date,
    _parse_amount,
    _parse_date,
    _record_skip,
    _resolve_charges_positive,
    _row,
)


def _col(row: dict, *names: str) -> Optional[str]:
    normalized = {_normalize_hdr(k): v for k, v in row.items()}
    for name in names:
        value = normalized.get(_normalize_hdr(name))
        if value is not None:
            return value
    return None


# Candidates ordered by tie-break preference: comma wins ties, then tab, etc.
_CSV_DELIMITERS = (",", "\t", ";", "|")


def _detect_delimiter(text: str) -> str:
    """Pick the delimiter that most consistently yields multi-column rows.

    csv.Sniffer can be fooled into choosing ';' or '|' when those characters
    appear inside description text of a comma-separated file, silently producing
    zero usable rows. Instead, score each candidate by how many of the first
    sample lines agree on a column count > 1, breaking ties toward comma.
    """
    sample_lines = [ln for ln in text.splitlines()[:10] if ln.strip()]
    if not sample_lines:
        return ","
    best_delim = ","
    best_score = (0, 0)  # (agreement on a >1 column count, that column count)
    for delim in _CSV_DELIMITERS:
        counts = [len(row) for row in csv.reader(sample_lines, delimiter=delim)]
        multi = [c for c in counts if c > 1]
        if not multi:
            continue
        common = max(set(multi), key=multi.count)
        score = (multi.count(common), common)
        if score > best_score:
            best_score = score
            best_delim = delim
    return best_delim


def _parse_csv(
    raw: bytes,
    source: str = "card",
    charges_positive: Optional[bool] = None,
    day_first: Optional[bool] = None,
) -> StatementParseResult:
    text = raw.decode("utf-8-sig", errors="replace")

    delimiter = _detect_delimiter(text)

    first = next(csv.reader(io.StringIO(text), delimiter=delimiter), [])
    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []
    resolved_df = bool(day_first)

    if first and _looks_like_date(first[0]):
        date_values: list[str] = []
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        for i, cells in enumerate(reader, start=1):
            if len(cells) < 3 or not _looks_like_date(cells[0]):
                continue
            date_values.append(cells[0])
            try:
                debit = _parse_amount(cells[2]) if len(cells) > 2 and cells[2].strip() else Decimal("0")
                credit = _parse_amount(cells[3]) if len(cells) > 3 and cells[3].strip() else Decimal("0")
                signed = credit if credit else -abs(debit)
                parsed = _row(_parse_date(cells[0], resolved_df), cells[1] if len(cells) > 1 else "", signed, i, source)
                if parsed:
                    rows.append(parsed)
            except Exception as exc:
                _record_skip(
                    skipped, i,
                    cells[0] if cells else "",
                    cells[2] if len(cells) > 2 else "",
                    cells[1] if len(cells) > 1 else "",
                    exc,
                )
        fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["accountactivity"]
        return StatementParseResult(
            rows, fmt, len(skipped), skipped_rows=skipped,
            date_convention_adjustable=_dates_ambiguous(date_values), day_first=resolved_df,
        )

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        return StatementParseResult([], "Unknown", 0)

    # A single signed Amount column (no split debit/credit) on a card statement is
    # the ambiguous case: AmEx-style exports list charges as positive, most banks
    # list them as negative. Resolve the convention from the dominant sign (or an
    # explicit user override) and expose it so the import preview can offer a toggle.
    normalized_fields = [_normalize_hdr(name) for name in reader.fieldnames]
    detected_cols = _statement_columns(normalized_fields)
    date_col, desc_col, amount_col, debit_col, credit_col = detected_cols
    records = list(reader)

    # Auto-detection could not find the columns it needs (unfamiliar bank export).
    # Surface header + sample metadata so the caller can offer a manual mapping
    # step instead of dead-ending with an empty/garbage import.
    if not _has_required_statement_columns(detected_cols):
        return StatementParseResult(
            [], FORMAT_NAMES["generic"], 0,
            columns=_column_info_from_csv(list(reader.fieldnames), records, detected_cols),
        )

    amount_only = amount_col is not None and debit_col is None and credit_col is None
    adjustable = amount_only and source != "checking"

    resolved_cp = False
    if adjustable:
        amounts: list[Decimal] = []
        for record in records:
            raw_amount = _col(record, *AMOUNT_ALIASES)
            if not _col(record, *DATE_ALIASES) or not raw_amount:
                continue
            try:
                amounts.append(_parse_amount(raw_amount))
            except Exception:
                continue
        resolved_cp = _resolve_charges_positive(amounts, charges_positive, legacy_default=False)

    date_adjustable = _dates_ambiguous([_col(record, *DATE_ALIASES) for record in records])

    for i, record in enumerate(records, start=2):
        raw_date = _col(record, *DATE_ALIASES)
        desc = _col(record, *DESCRIPTION_ALIASES) or ""
        debit = _col(record, *DEBIT_ALIASES)
        credit = _col(record, *CREDIT_ALIASES)
        amount = _col(record, *AMOUNT_ALIASES)
        if not raw_date:
            continue
        try:
            if debit or credit:
                d = _parse_amount(debit) if debit else Decimal("0")
                c = _parse_amount(credit) if credit else Decimal("0")
                signed = c if c else -abs(d)
            elif amount:
                signed = _parse_amount(amount)
                if adjustable and resolved_cp:
                    signed = -signed
            else:
                raise ValueError("row has no amount, debit, or credit value")
            parsed = _row(_parse_date(raw_date, resolved_df), desc, signed, i, source)
            if parsed:
                rows.append(parsed)
        except Exception as exc:
            _record_skip(skipped, i, raw_date, amount if amount else (debit or credit), desc, exc)
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["generic"]
    return StatementParseResult(
        rows, fmt, len(skipped), adjustable, resolved_cp, skipped_rows=skipped,
        date_convention_adjustable=date_adjustable, day_first=resolved_df,
    )
