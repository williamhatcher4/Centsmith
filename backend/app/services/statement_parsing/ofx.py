"""OFX/QFX parsing: XML (OFX 2.x), SGML (OFX 1.x), and the SGML-ish hybrids."""
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

from .core import (
    FORMAT_NAMES,
    ParsedRow,
    SkippedRow,
    StatementParseResult,
    _parse_amount,
    _record_skip,
    _row,
)


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
