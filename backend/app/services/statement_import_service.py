import csv
import hashlib
import io
import re
import xml.etree.ElementTree as ET
from contextlib import closing
from dataclasses import dataclass
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
) -> Decimal:
    if _populated_cell(cells, credit_col):
        credit_amount = _parse_amount(_cell(cells, credit_col))
        if credit_amount:
            return abs(credit_amount)

    if _populated_cell(cells, debit_col):
        return -abs(_parse_amount(_cell(cells, debit_col)))

    if _populated_cell(cells, amount_col):
        amount = _parse_amount(_cell(cells, amount_col))
        # Card statements use a magnitude-only Amount column (charges positive),
        # so invert. But when the file also has split debit/credit columns, the
        # Amount column is already signed — never invert it.
        if source == "checking" or debit_col is not None or credit_col is not None:
            return amount
        return -amount

    raise ValueError("row has no amount, debit, or credit value")


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


def _parse_csv(raw: bytes, source: str = "card") -> tuple[list[ParsedRow], str, int]:
    text = raw.decode("utf-8-sig", errors="replace")

    delimiter = _detect_delimiter(text)

    first = next(csv.reader(io.StringIO(text), delimiter=delimiter), [])
    rows: list[ParsedRow] = []
    errors = 0

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
            except Exception:
                errors += 1
        fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["accountactivity"]
        return rows, fmt, errors

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        return [], "Unknown", 0
    for i, record in enumerate(reader, start=2):
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
    columns: tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]] | None = None
    for idx, cells in enumerate(data[:25]):
        normalized = [_normalize_hdr(c) for c in cells]
        candidate = _statement_columns(normalized)
        if _has_required_statement_columns(candidate):
            header_index = idx
            columns = candidate
            break
    if header_index is None or columns is None:
        raise ValueError("Could not find a transaction header row in the XLS file")

    date_col, desc_col, amount_col, debit_col, credit_col = columns

    rows: list[ParsedRow] = []
    errors = 0
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
            amount = _spreadsheet_signed_amount(cells, amount_col, debit_col, credit_col, source)
            parsed = _row(tx_date, str(cells[desc_col]), amount, row_number, source)
            if parsed:
                rows.append(parsed)
        except Exception:
            errors += 1
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["amex_xls"]
    return rows, fmt, errors


def _parse_xlsx(raw: bytes, source: str = "card") -> tuple[list[ParsedRow], str, int]:
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
        raise ValueError("Could not find a transaction header row in the XLSX file")

    date_col, desc_col, amount_col, debit_col, credit_col = columns

    rows: list[ParsedRow] = []
    errors = 0
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
            amount = _spreadsheet_signed_amount(cells, amount_col, debit_col, credit_col, source)
            parsed = _row(tx_date, str(cells[desc_col]) if cells[desc_col] is not None else "", amount, row_number, source)
            if parsed:
                rows.append(parsed)
        except Exception:
            errors += 1
    fmt = FORMAT_NAMES["checking"] if source == "checking" else FORMAT_NAMES["xlsx"]
    return rows, fmt, errors


def _parse_ofx_date(raw: str) -> date:
    m = re.match(r"^(\d{8})", raw.strip())
    if m:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    raise ValueError(f"Cannot parse OFX date: {raw!r}")


def _parse_ofx(raw: bytes, source: str = "card") -> tuple[list[ParsedRow], str, int]:
    text = raw.decode("utf-8-sig", errors="replace").strip()
    rows: list[ParsedRow] = []
    errors = 0

    def parse_sgml_transactions() -> tuple[list[ParsedRow], int]:
        parsed_rows: list[ParsedRow] = []
        parsed_errors = 0
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
            except Exception:
                parsed_errors += 1
        return parsed_rows, parsed_errors

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
                rows, errors = parse_sgml_transactions()
                return rows, FORMAT_NAMES["ofx"], errors
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
            rows, errors = parse_sgml_transactions()
            return rows, FORMAT_NAMES["ofx"], errors
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
            except Exception:
                errors += 1
    else:
        rows, errors = parse_sgml_transactions()

    return rows, FORMAT_NAMES["ofx"], errors


def parse_statement(filename: str, content: bytes, source: str = "card") -> tuple[list[ParsedRow], str, int]:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "xls":
        rows, fmt, errors = _parse_xls(content, source)
    elif suffix == "xlsx":
        rows, fmt, errors = _parse_xlsx(content, source)
    elif suffix in ("ofx", "qfx"):
        rows, fmt, errors = _parse_ofx(content, source)
    else:
        rows, fmt, errors = _parse_csv(content, source)
    _assign_occurrences(rows, source)
    return rows, fmt, errors
