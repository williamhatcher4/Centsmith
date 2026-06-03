import csv
import hashlib
import io
import re
import xml.etree.ElementTree as ET
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

FORMAT_NAMES = {
    "accountactivity": "Account Activity CSV",
    "amex_xls": "American Express XLS",
    "generic": "Generic CSV",
    "checking": "Checking CSV",
    "xlsx": "Spreadsheet (XLSX)",
    "ofx": "OFX/QFX Bank Export",
}

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
class ParsedRow:
    row_number: int
    transaction_date: date
    description: str
    amount_cents: int
    transaction_type: str
    source_hash: str


# Max length for any raw field echoed back in a skipped-row diagnostic. Keeps the
# payload small and avoids dumping pathological rows verbatim into the UI/logs.
MAX_DIAG_FIELD_LEN = 80


@dataclass
class SkippedRow:
    """A sanitized reason a single source row could not be imported.

    Raw fields are the user's own date/amount/description cell values (truncated);
    ``message`` is a fixed user-facing string — never an exception string or
    traceback — so no library paths or internals leak into the preview/logs.
    """
    row_number: int
    raw_date: str
    raw_amount: str
    raw_description: str
    reason_code: str
    message: str


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


@dataclass
class ColumnMapping:
    """An explicit user/profile-supplied column assignment for an import.

    ``amount_convention`` is one of ``signed`` (the Amount column is already
    signed), ``charges_positive`` (purchases are positive → invert), or
    ``charges_negative`` (purchases are negative → keep as-is). Either
    ``amount_column`` or at least one of ``debit_column``/``credit_column`` must
    be set.
    """
    date_column: int
    description_column: int
    amount_column: Optional[int] = None
    debit_column: Optional[int] = None
    credit_column: Optional[int] = None
    amount_convention: str = "signed"


@dataclass
class StatementParseResult:
    rows: list[ParsedRow]
    statement_format: str
    skipped_errors: int
    # True when the file was read through a single signed "Amount" column on a
    # card statement, where charges-positive vs charges-negative is ambiguous and
    # the user can override the convention from the import preview.
    amount_sign_adjustable: bool = False
    # The convention actually applied: True => charges shown as positive (inverted
    # so charges become debits); False => charges shown as negative (kept as-is).
    charges_positive: bool = False
    # Per-row diagnostics for rows that could not be parsed. ``skipped_errors``
    # stays as the count for back-compat; ``skipped_rows`` carries the detail.
    skipped_rows: list[SkippedRow] = field(default_factory=list)
    # Populated when auto-detection failed and the caller should offer manual
    # column mapping instead of treating an empty result as "unsupported bank".
    columns: Optional[StatementColumnInfo] = None


def _trunc_diag(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.strip()
    if len(text) <= MAX_DIAG_FIELD_LEN:
        return text
    return text[: MAX_DIAG_FIELD_LEN - 1] + "…"


def _classify_skip(exc: Exception) -> tuple[str, str]:
    """Map a parse exception to a (reason_code, user-facing message).

    The message is a fixed string, never ``str(exc)``, so internal paths and
    library details never reach the UI or a support bundle.
    """
    low = str(exc).lower()
    if "no amount" in low or "missing required trnamt" in low or "no amount, debit" in low:
        return "missing_amount", "This row has no amount, debit, or credit value."
    if "date" in low:
        return "unparseable_date", "Could not read the date in this row."
    if "amount" in low:
        return "unparseable_amount", "Could not read the amount in this row."
    return "row_error", "This row could not be read and was skipped."


def _record_skip(
    skipped: list[SkippedRow],
    row_number: int,
    raw_date: object,
    raw_amount: object,
    raw_description: object,
    exc: Exception,
) -> None:
    reason_code, message = _classify_skip(exc)
    skipped.append(
        SkippedRow(
            row_number=row_number,
            raw_date=_trunc_diag(raw_date),
            raw_amount=_trunc_diag(raw_amount),
            raw_description=_trunc_diag(raw_description),
            reason_code=reason_code,
            message=message,
        )
    )


def _resolve_charges_positive(
    amounts: list[Decimal],
    explicit: Optional[bool],
    legacy_default: bool,
) -> bool:
    """Decide whether a single Amount column lists charges as positive.

    An explicit user choice always wins. Otherwise auto-detect from the file's
    dominant sign (cards are overwhelmingly charges): more positives than
    negatives => charges-positive; more negatives => charges-negative. On a tie
    fall back to the path's historical default so existing imports/tests are
    unchanged.
    """
    if explicit is not None:
        return explicit
    positives = sum(1 for amount in amounts if amount > 0)
    negatives = sum(1 for amount in amounts if amount < 0)
    if positives > negatives:
        return True
    if negatives > positives:
        return False
    return legacy_default


def _parse_date(raw: object) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    s = re.sub(r"([A-Za-z]+)\.", r"\1", s)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d/%m/%y", "%b %d, %Y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    m = re.match(r"^(\d{1,4})[/\-](\d{1,2})[/\-](\d{1,4})$", s)
    if m:
        a, b, c = [int(x) for x in m.groups()]
        if a > 31:
            return date(a, b, c)
        year = c if c > 99 else 2000 + c
        try:
            return date(year, a, b)
        except ValueError:
            return date(year, b, a)
    raise ValueError(f"Cannot parse date: {raw!r}")


def _parse_amount(raw: object) -> Decimal:
    s = str(raw or "").strip()
    s = s.replace("−", "-")
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[$,]", "", s).strip("() ")
    if not s:
        return Decimal("0")
    try:
        value = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse amount: {raw!r}") from exc
    return -value if neg else value


def _to_cents(amount: Decimal) -> int:
    return int((abs(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _source_hash(tx_date: date, description: str, amount_cents: int, tx_type: str, source: str = "card", occurrence: int = 0) -> str:
    raw = f"{source}|{tx_date.isoformat()}|{description.strip().lower()}|{amount_cents}|{tx_type}"
    if occurrence > 0:
        raw = f"{raw}|{occurrence}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _assign_occurrences(rows: list[ParsedRow], source: str = "card") -> None:
    counts: dict[tuple[date, str, int, str], int] = {}
    for row in rows:
        key = (row.transaction_date, row.description.strip().lower(), row.amount_cents, row.transaction_type)
        occurrence = counts.get(key, 0)
        if occurrence > 0:
            row.source_hash = _source_hash(
                row.transaction_date,
                row.description,
                row.amount_cents,
                row.transaction_type,
                source,
                occurrence,
            )
        counts[key] = occurrence + 1


def _row(tx_date: date, description: str, signed_amount: Decimal, row_number: int, source: str = "card") -> Optional[ParsedRow]:
    if signed_amount == 0:
        return None
    tx_type = "credit" if signed_amount > 0 else "debit"
    amount_cents = _to_cents(signed_amount)
    desc = description.strip() or "Imported transaction"
    return ParsedRow(
        row_number=row_number,
        transaction_date=tx_date,
        description=desc,
        amount_cents=amount_cents,
        transaction_type=tx_type,
        source_hash=_source_hash(tx_date, desc, amount_cents, tx_type, source),
    )


def _looks_like_date(value: str) -> bool:
    try:
        _parse_date(value)
        return True
    except Exception:
        return False


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (int, float)):
        return False
    return not str(value).strip()


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


def _cell(cells: list, col: Optional[int]) -> object:
    if col is None or col >= len(cells):
        return None
    return cells[col]


def _populated_cell(cells: list, col: Optional[int]) -> bool:
    return not _is_blank(_cell(cells, col))


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
    raw: bytes, source: str = "card", charges_positive: Optional[bool] = None
) -> StatementParseResult:
    text = raw.decode("utf-8-sig", errors="replace")

    delimiter = _detect_delimiter(text)

    first = next(csv.reader(io.StringIO(text), delimiter=delimiter), [])
    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []

    if first and _looks_like_date(first[0]):
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        for i, cells in enumerate(reader, start=1):
            if len(cells) < 3 or not _looks_like_date(cells[0]):
                continue
            try:
                debit = _parse_amount(cells[2]) if len(cells) > 2 and cells[2].strip() else Decimal("0")
                credit = _parse_amount(cells[3]) if len(cells) > 3 and cells[3].strip() else Decimal("0")
                signed = credit if credit else -abs(debit)
                parsed = _row(_parse_date(cells[0]), cells[1] if len(cells) > 1 else "", signed, i, source)
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
        return StatementParseResult(rows, fmt, len(skipped), skipped_rows=skipped)

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
            parsed = _row(_parse_date(raw_date), desc, signed, i, source)
            if parsed:
                rows.append(parsed)
        except Exception as exc:
            _record_skip(skipped, i, raw_date, amount if amount else (debit or credit), desc, exc)
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["generic"]
    return StatementParseResult(rows, fmt, len(skipped), adjustable, resolved_cp, skipped_rows=skipped)


def _parse_xls(
    raw: bytes, source: str = "card", charges_positive: Optional[bool] = None
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
                tx_date = _parse_date(raw_date)
            amount = _spreadsheet_signed_amount(
                cells, amount_col, debit_col, credit_col, source, invert_amount=resolved_cp
            )
            parsed = _row(tx_date, str(cells[desc_col]), amount, row_number, source)
            if parsed:
                rows.append(parsed)
        except Exception as exc:
            _record_skip(skipped, row_number, _cell(cells, date_col), _cell(cells, amount_col if amount_col is not None else debit_col), _cell(cells, desc_col), exc)
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["amex_xls"]
    return StatementParseResult(rows, fmt, len(skipped), adjustable, resolved_cp, skipped_rows=skipped)


def _parse_xlsx(
    raw: bytes, source: str = "card", charges_positive: Optional[bool] = None
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
            tx_date = _parse_date(cells[date_col])
            amount = _spreadsheet_signed_amount(
                cells, amount_col, debit_col, credit_col, source, invert_amount=resolved_cp
            )
            parsed = _row(tx_date, str(cells[desc_col]) if cells[desc_col] is not None else "", amount, row_number, source)
            if parsed:
                rows.append(parsed)
        except Exception as exc:
            _record_skip(skipped, row_number, _cell(cells, date_col), _cell(cells, amount_col if amount_col is not None else debit_col), _cell(cells, desc_col), exc)
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["xlsx"]
    return StatementParseResult(rows, fmt, len(skipped), adjustable, resolved_cp, skipped_rows=skipped)


def _parse_ofx_date(raw: str) -> date:
    m = re.match(r"^(\d{8})", raw.strip())
    if m:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    raise ValueError(f"Cannot parse OFX date: {raw!r}")


def _parse_ofx(raw: bytes, source: str = "card") -> StatementParseResult:
    text = raw.decode("utf-8-sig", errors="replace").strip()
    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []

    def parse_sgml_transactions() -> tuple[list[ParsedRow], list[SkippedRow]]:
        parsed_rows: list[ParsedRow] = []
        parsed_skipped: list[SkippedRow] = []
        # OFX 1.x SGML — extract STMTTRN blocks; closing tags are optional. The
        # block-level lookaheads stop a missing-</STMTTRN> final block from
        # absorbing a following balance section (LEDGERBAL/AVAILBAL) and picking
        # up its DTASOF date.
        blocks = re.findall(
            r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRNLIST>)|(?=</STMTRS>)|$)",
            text,
            re.S | re.I,
        )
        for row_number, block in enumerate(blocks, start=1):
            if not block.strip():
                continue
            dm = re.search(r"<DTPOSTED>\s*([\d\[\]:+\-A-Z]+)", block, re.I)
            am = re.search(r"<TRNAMT>\s*([+$,\-\d.()]+)", block, re.I)
            # Prefer NAME over MEMO to match the XML path (_child_text NAME, MEMO),
            # so the same statement hashes identically across OFX 1.x and 2.x.
            nm = re.search(r"<NAME>\s*([^\n<]+)", block, re.I) or re.search(
                r"<MEMO>\s*([^\n<]+)", block, re.I
            )
            date_str = dm.group(1).strip() if dm else ""
            desc = nm.group(1).strip() if nm else ""
            try:
                if am is None:
                    raise ValueError("STMTTRN is missing required TRNAMT field")
                tx_date = _parse_ofx_date(date_str)
                signed = _parse_amount(am.group(1).strip())
                parsed = _row(tx_date, desc, signed, row_number, source)
                if parsed:
                    parsed_rows.append(parsed)
            except Exception as exc:
                _record_skip(parsed_skipped, row_number, date_str, am.group(1).strip() if am else "", desc, exc)
        return parsed_rows, parsed_skipped

    # OFX 2.x (XML) has closing tags on leaf elements like </DTPOSTED>.
    # OFX 1.x (SGML) has closing tags only on block elements like </STMTTRN>.
    is_xml = text.startswith("<?xml") or bool(re.search(r"</(?:DTPOSTED|TRNAMT|FITID|NAME|MEMO)>", text, re.I))

    if is_xml:
        # Strip any leading SGML-style header lines before the XML root.
        # Search for "<OFX" rather than "<OFX>" so that <OFX xmlns="..."> still matches.
        xml_start = text.find("<OFX")
        if xml_start == -1:
            xml_start = text.find("<?xml")
        xml_text = text[xml_start:] if xml_start >= 0 else text
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            if not text.startswith("<?xml"):
                rows, skipped = parse_sgml_transactions()
                return StatementParseResult(rows, FORMAT_NAMES["ofx"], len(skipped), skipped_rows=skipped)
            raise ValueError(f"Could not parse OFX file as XML: {exc}") from exc

        def _local(tag: str) -> str:
            return tag.rpartition("}")[2]

        def _child_text(parent: ET.Element, *names: str) -> str:
            for name in names:
                for child in parent:
                    if _local(child.tag) == name and child.text:
                        return child.text.strip()
            return ""

        trn_elements = [el for el in root.iter() if _local(el.tag) == "STMTTRN"]
        if not trn_elements and not text.startswith("<?xml"):
            # The file happened to parse as a sparse XML tree (closing leaf tags
            # tripped is_xml), but the real transactions are SGML-style elsewhere
            # in the buffer. Recover them via SGML parsing instead of reporting 0.
            rows, skipped = parse_sgml_transactions()
            return StatementParseResult(rows, FORMAT_NAMES["ofx"], len(skipped), skipped_rows=skipped)
        for row_number, trn in enumerate(trn_elements, start=1):
            date_str = _child_text(trn, "DTPOSTED", "DTUSER")
            amount_str = _child_text(trn, "TRNAMT")
            desc = _child_text(trn, "NAME", "MEMO")
            try:
                if not amount_str:
                    raise ValueError("STMTTRN is missing required TRNAMT field")
                tx_date = _parse_ofx_date(date_str)
                signed = _parse_amount(amount_str)
                parsed = _row(tx_date, desc, signed, row_number, source)
                if parsed:
                    rows.append(parsed)
            except Exception as exc:
                _record_skip(skipped, row_number, date_str, amount_str, desc, exc)
    else:
        rows, skipped = parse_sgml_transactions()

    return StatementParseResult(rows, FORMAT_NAMES["ofx"], len(skipped), skipped_rows=skipped)


def parse_statement_ex(
    filename: str, content: bytes, source: str = "card", charges_positive: Optional[bool] = None
) -> StatementParseResult:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "xls":
        result = _parse_xls(content, source, charges_positive)
    elif suffix == "xlsx":
        result = _parse_xlsx(content, source, charges_positive)
    elif suffix in ("ofx", "qfx"):
        result = _parse_ofx(content, source)
    else:
        result = _parse_csv(content, source, charges_positive)
    _assign_occurrences(result.rows, source)
    return result


def parse_statement(
    filename: str, content: bytes, source: str = "card", charges_positive: Optional[bool] = None
) -> tuple[list[ParsedRow], str, int]:
    result = parse_statement_ex(filename, content, source, charges_positive)
    return result.rows, result.statement_format, result.skipped_errors


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


def _coerce_mapping_date(cell: object) -> date:
    """Parse a date from a mapped cell, handling raw Excel serial-date floats."""
    if isinstance(cell, float):
        try:
            import xlrd

            return xlrd.xldate_as_datetime(cell, 0).date()
        except Exception:
            pass
    return _parse_date(cell)


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
    filename: str, content: bytes, source: str, mapping: ColumnMapping
) -> StatementParseResult:
    """Parse a statement using an explicit, user/profile-supplied column mapping.

    Used when auto-detection can't identify the columns (unfamiliar bank export)
    or when a saved import profile pins the layout for a known bank.
    """
    headers, data_rows = _extract_grid(filename, content)
    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []
    for i, cells in enumerate(data_rows, start=2):
        raw_date = _cell(cells, mapping.date_column)
        raw_desc = _cell(cells, mapping.description_column)
        amount_hint_col = mapping.amount_column if mapping.amount_column is not None else mapping.debit_column
        if _is_blank(raw_date) and _is_blank(raw_desc):
            continue
        try:
            tx_date = _coerce_mapping_date(raw_date)
            signed = _mapping_signed_amount(cells, mapping)
            parsed = _row(tx_date, str(raw_desc) if raw_desc is not None else "", signed, i, source)
            if parsed:
                rows.append(parsed)
        except Exception as exc:
            _record_skip(skipped, i, raw_date, _cell(cells, amount_hint_col), raw_desc, exc)
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["generic"]
    result = StatementParseResult(rows, fmt, len(skipped), skipped_rows=skipped)
    _assign_occurrences(result.rows, source)
    return result
