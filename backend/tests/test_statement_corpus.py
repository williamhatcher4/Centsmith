"""Statement fixture corpus harness (plan item P5.5).

Parses every fixture under ``fixtures/corpus/`` and asserts the frozen
``manifest.json`` ``expected`` block field-by-field, plus corpus-wide invariants
applied to every file. See ``tests/corpus_fixtures.py`` for the builder and the
**mandatory sanitization rule** (every fixture is builder-generated or scrubbed —
committing an unscrubbed real statement is forbidden) and the **ongoing rule**
(every user-reported import bug lands with a sanitized fixture + manifest entry in
the same change).

Regenerate the corpus + manifest from ``backend/``::

    python -m tests.corpus_fixtures
"""

import json
from datetime import date
from pathlib import Path

import pytest

from app.services.statement_import_service import (
    ColumnMapping,
    parse_statement_ex,
    parse_statement_with_mapping,
)
from app.services.transaction_import_service import _rows_for_source

CORPUS_DIR = Path(__file__).parent / "fixtures" / "corpus"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"

_MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {"fixtures": []}
_FIXTURES = _MANIFEST.get("fixtures", [])


def _parse(entry: dict):
    """Parse a corpus entry via the auto path, or the mapping path when the
    manifest pins a ``column_mapping`` (mirrors the import service's dispatch)."""
    content = (CORPUS_DIR / entry["filename"]).read_bytes()
    source = entry["source"]
    kwargs = dict(entry.get("parse_kwargs", {}))
    mapping_dict = kwargs.pop("column_mapping", None)
    if mapping_dict is not None:
        mapping = ColumnMapping(**mapping_dict)
        return parse_statement_with_mapping(
            entry["filename"], content, source, mapping, kwargs.get("day_first")
        )
    return parse_statement_ex(entry["filename"], content, source=source, **kwargs)


def _signed_total(rows) -> int:
    return sum(r.amount_cents if r.transaction_type == "credit" else -r.amount_cents for r in rows)


def test_manifest_has_fixtures():
    # Guard: an empty corpus dir must not silently pass the parameterized tests
    # below (pytest treats zero params as a pass).
    assert _FIXTURES, (
        "No corpus fixtures found. Generate them from backend/ with:\n"
        "    python -m tests.corpus_fixtures"
    )


@pytest.mark.parametrize("entry", _FIXTURES, ids=lambda e: e["filename"])
def test_corpus_entry_matches_expected(entry):
    result = _parse(entry)
    expected = entry["expected"]
    filename = entry["filename"]

    assert result.statement_format == expected["format"], (
        f"{filename}: format {result.statement_format!r} != expected {expected['format']!r}"
    )
    assert len(result.rows) == expected["rows"], (
        f"{filename}: parsed {len(result.rows)} rows, expected {expected['rows']}"
    )
    assert result.skipped_errors == expected["skipped"], (
        f"{filename}: {result.skipped_errors} skipped, expected {expected['skipped']}"
    )

    kept, ignored = _rows_for_source(
        result.rows, entry["source"], entry.get("ignored_patterns")
    )
    assert len(ignored) == expected["ignored_credits"], (
        f"{filename}: {len(ignored)} ignored credits, expected {expected['ignored_credits']}"
    )
    assert _signed_total(kept) == expected["signed_total_cents"], (
        f"{filename}: signed total {_signed_total(kept)}c, expected {expected['signed_total_cents']}c"
    )


@pytest.mark.parametrize("entry", _FIXTURES, ids=lambda e: e["filename"])
def test_corpus_entry_invariants(entry):
    # Corpus-wide invariants applied to every file regardless of manifest.
    try:
        result = _parse(entry)
    except ValueError as exc:
        # The only acceptable parse failure is a sanitized user-facing ValueError
        # — never a path or library traceback in the message.
        message = str(exc)
        assert ":\\" not in message and "/site-packages/" not in message and "Traceback" not in message
        return
    except Exception as exc:  # pragma: no cover - corpus fixtures should never hit this
        pytest.fail(f"{entry['filename']}: parsing raised {type(exc).__name__}, not a sanitized ValueError: {exc}")

    for row in result.rows:
        assert row.description.strip(), f"{entry['filename']}: a kept row has an empty description"
        assert date(1990, 1, 1) <= row.transaction_date <= date(2100, 1, 1), (
            f"{entry['filename']}: row date {row.transaction_date} outside 1990-2100"
        )

    # Determinism: parsing the same bytes twice yields identical source hashes.
    again = _parse(entry)
    assert [r.source_hash for r in result.rows] == [r.source_hash for r in again.rows]
