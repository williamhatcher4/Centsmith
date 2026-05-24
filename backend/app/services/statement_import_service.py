import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

FORMAT_NAMES = {
    "accountactivity": "Account Activity CSV",
    "amex_xls": "American Express XLS",
    "generic": "Generic CSV",
    "checking": "Checking CSV",
}


@dataclass
class ParsedRow:
    row_number: int
    transaction_date: date
    description: str
    amount_cents: int
    transaction_type: str
    source_hash: str


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


def _source_hash(tx_date: date, description: str, amount_cents: int, tx_type: str, source: str = "card") -> str:
    raw = f"{source}|{tx_date.isoformat()}|{description.strip().lower()}|{amount_cents}|{tx_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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


def _col(row: dict, *names: str) -> Optional[str]:
    lower = {str(k).lower().strip(): v for k, v in row.items()}
    for name in names:
        value = lower.get(name.lower())
        if value is not None:
            return value
    return None


def _parse_csv(raw: bytes, source: str = "card") -> tuple[list[ParsedRow], str, int]:
    text = raw.decode("utf-8-sig", errors="replace")
    first = next(csv.reader(io.StringIO(text)), [])
    rows: list[ParsedRow] = []
    errors = 0

    if first and _looks_like_date(first[0]):
        reader = csv.reader(io.StringIO(text))
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
            except Exception:
                errors += 1
        fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["accountactivity"]
        return rows, fmt, errors

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], "Unknown", 0
    for i, record in enumerate(reader, start=2):
        raw_date = _col(record, "Date", "Transaction Date", "Trans Date", "Posted Date")
        desc = _col(record, "Description", "Merchant", "Payee", "Details", "Narrative") or ""
        debit = _col(record, "Debit", "Withdrawal", "Withdrawals")
        credit = _col(record, "Credit", "Deposit", "Deposits")
        amount = _col(record, "Amount", "Transaction Amount", "Value")
        if not raw_date:
            continue
        try:
            if debit or credit:
                d = _parse_amount(debit) if debit else Decimal("0")
                c = _parse_amount(credit) if credit else Decimal("0")
                signed = c if c else -abs(d)
            elif amount:
                signed = _parse_amount(amount)
            else:
                continue
            parsed = _row(_parse_date(raw_date), desc, signed, i, source)
            if parsed:
                rows.append(parsed)
        except Exception:
            errors += 1
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["generic"]
    return rows, fmt, errors


def _parse_xls(raw: bytes, source: str = "card") -> tuple[list[ParsedRow], str, int]:
    try:
        import xlrd
    except ImportError as exc:
        raise ValueError("XLS imports require the xlrd package. Run pip install -e . in backend.") from exc

    book = xlrd.open_workbook(file_contents=raw)
    sheet = book.sheet_by_index(0)
    data = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]

    header_index = None
    headers: list[str] = []
    for idx, cells in enumerate(data[:25]):
        normalized = [str(c).strip().lower() for c in cells]
        if any("date" in c for c in normalized) and any("description" in c or "merchant" in c for c in normalized):
            header_index = idx
            headers = normalized
            break
    if header_index is None:
        raise ValueError("Could not find a transaction header row in the XLS file")

    def find_col(*needles: str) -> Optional[int]:
        for needle in needles:
            for idx, header in enumerate(headers):
                if needle in header:
                    return idx
        return None

    date_col = find_col("date")
    desc_col = find_col("description", "merchant", "name")
    amount_col = find_col("amount", "charge", "debit")
    credit_col = find_col("credit", "payment")
    if date_col is None or desc_col is None or amount_col is None:
        raise ValueError("XLS format must include date, description, and amount columns")

    rows: list[ParsedRow] = []
    errors = 0
    for row_number, cells in enumerate(data[header_index + 1 :], start=header_index + 2):
        if date_col >= len(cells) or desc_col >= len(cells) or amount_col >= len(cells):
            continue
        if _is_blank(cells[date_col]) and _is_blank(cells[desc_col]) and _is_blank(cells[amount_col]):
            continue
        try:
            raw_date = cells[date_col]
            if isinstance(raw_date, float):
                tx_date = xlrd.xldate_as_datetime(raw_date, book.datemode).date()
            else:
                tx_date = _parse_date(raw_date)
            amount = _parse_amount(cells[amount_col])
            if credit_col is not None and credit_col < len(cells) and str(cells[credit_col]).strip():
                credit_amount = _parse_amount(cells[credit_col])
                if credit_amount:
                    amount = abs(credit_amount)
            if credit_col is None:
                amount = -amount
            parsed = _row(tx_date, str(cells[desc_col]), amount, row_number, source)
            if parsed:
                rows.append(parsed)
        except Exception:
            errors += 1
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["amex_xls"]
    return rows, fmt, errors


def parse_statement(filename: str, content: bytes, source: str = "card") -> tuple[list[ParsedRow], str, int]:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "xls":
        return _parse_xls(content, source)
    return _parse_csv(content, source)

