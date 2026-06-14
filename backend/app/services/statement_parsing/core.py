"""Shared parsing primitives: result dataclasses, date/amount/hash helpers,
and the sanitized skipped-row diagnostics.

This module sits at the bottom of the package's dependency graph — every
format parser imports from here, never the other way around.
"""
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .columns import StatementColumnInfo

FORMAT_NAMES = {
    "accountactivity": "Account Activity CSV",
    "amex_xls": "American Express XLS",
    "generic": "Generic CSV",
    "checking": "Checking CSV",
    "xlsx": "Spreadsheet (XLSX)",
    "ofx": "OFX/QFX Bank Export",
}


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
    # True when every slash/dash-numeric date in the file has both leading fields
    # <= 12, so MM/DD vs DD/MM is genuinely ambiguous and the user can override
    # the convention from the import preview (mirrors amount_sign_adjustable).
    date_convention_adjustable: bool = False
    # The convention actually applied: True => dates read day-first (DD/MM).
    # Defaults to US month-first so existing imports and hashes are unchanged.
    day_first: bool = False
    # Per-row diagnostics for rows that could not be parsed. ``skipped_errors``
    # stays as the count for back-compat; ``skipped_rows`` carries the detail.
    skipped_rows: list[SkippedRow] = field(default_factory=list)
    # Populated when auto-detection failed and the caller should offer manual
    # column mapping instead of treating an empty result as "unsupported bank".
    columns: Optional["StatementColumnInfo"] = None


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


# Numeric slash/dash formats whose field order depends on the file's convention.
_MONTH_FIRST_NUMERIC_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d/%m/%y")
_DAY_FIRST_NUMERIC_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%m/%d/%y")
# Unambiguous formats (ISO, month names) tried around the numeric family.
_UNAMBIGUOUS_DATE_FORMATS = ("%b %d, %Y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y")


def _parse_date(raw: object, day_first: Optional[bool] = None) -> date:
    """Parse a statement date; ``day_first`` picks the DD/MM family first for
    ambiguous numeric dates (default stays US month-first)."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    s = re.sub(r"([A-Za-z]+)\.", r"\1", s)
    numeric = _DAY_FIRST_NUMERIC_FORMATS if day_first else _MONTH_FIRST_NUMERIC_FORMATS
    for fmt in ("%Y-%m-%d",) + numeric + _UNAMBIGUOUS_DATE_FORMATS:
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
        first, second = (b, a) if day_first else (a, b)
        try:
            return date(year, first, second)
        except ValueError:
            return date(year, second, first)
    raise ValueError(f"Cannot parse date: {raw!r}")


_AMBIGUOUS_NUMERIC_DATE_RE = re.compile(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$")


def _dates_ambiguous(raw_dates: list) -> bool:
    """True when a date column's MM/DD vs DD/MM order cannot be inferred.

    Ambiguous iff the column contains at least one slash/dash-numeric date and
    every such date has both leading fields <= 12 — a single day > 12 anywhere
    disambiguates the whole column (the strptime fallback already reads those
    rows correctly whichever family is tried first). Native date/datetime cells
    (e.g. real spreadsheet dates) and non-numeric formats are never ambiguous.
    """
    found = False
    for raw in raw_dates:
        if raw is None or isinstance(raw, (datetime, date, float, int)):
            continue
        m = _AMBIGUOUS_NUMERIC_DATE_RE.match(str(raw).strip())
        if not m:
            continue
        if int(m.group(1)) > 12 or int(m.group(2)) > 12:
            return False
        found = True
    return found


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


def _cell(cells: list, col: Optional[int]) -> object:
    if col is None or col >= len(cells):
        return None
    return cells[col]


def _populated_cell(cells: list, col: Optional[int]) -> bool:
    return not _is_blank(_cell(cells, col))
