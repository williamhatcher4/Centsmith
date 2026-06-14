"""Migration-lineage fixture generator (plan item P5.4).

Migrations run unconditionally at user startup against their only data copy — the
most dangerous code shipped per release. Existing tests cover fresh-create and a
*hand-built* synthetic old schema, but nothing migrates a database that actually
lived through the real revision chain. This module is the single source of truth
for a committed lineage fixture: a seeded SQLite DB plus a sidecar of expected
values that ``test_migration_lineage.py`` re-checks after upgrading the DB to
head.

It is named without a ``test_`` prefix so pytest does not collect it.

Regenerate (from ``backend/`` with the venv active)::

    python -m tests.lineage_fixture

**Release process rule** (also in ``AI-Context/Runbook.md``): immediately after
cutting release ``vX.Y.Z``, check out the tag, regenerate the fixture so it is
frozen at that release's schema, commit it to master, and delete fixtures older
than the previous release (keep at most two). Master thereafter always proves
"the previous release's database upgrades cleanly to current head" — exactly what
happens on every user's machine at auto-update time.

Seed data is **never** real user data: a fixed test-only user/password, and ~14
transactions covering every semantic corner (manual vs imported, personal
categorized/uncategorized, work expensed/unexpensed, Income/Reimbursement
credits, Transfer on both sides, an unclassified inbox row, card-linked rows, and
a custom category).
"""

import hashlib
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

# --- Test-only credentials (constants — never real user data) ------------------

TEST_USERNAME = "lineage-user"
TEST_DISPLAY_NAME = "Lineage Fixture User"
TEST_PASSWORD = "lineage-fixture-password"  # noqa: S105 — test-only, hashed into the fixture

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "lineage"

# A single import batch owns the imported rows below.
IMPORT_BATCH_ID = "00000000-0000-0000-0000-0000000000ba"
CARD_ID = 1


def _hashed(i: int) -> str:
    """A deterministic 64-char hex source_hash for an imported row."""
    return hashlib.sha256(f"lineage-import-{i}".encode()).hexdigest()


def _manual_hash(i: int) -> str:
    return f"manual:00000000-0000-0000-0000-{i:012d}"


# --- Seed transactions: every semantic corner ----------------------------------
# (date, description, amount_cents, transaction_type, classification,
#  personal_category, expensed, is_manual)
# Imported rows (is_manual=False) are stamped with the batch id; the three
# card-linked rows additionally carry CARD_ID.
_CARD_LINKED_DESCRIPTIONS = {"GROCERY ONE", "GROCERY TWO", "HOBBY SHOP"}

SEED_TRANSACTIONS = [
    # Imported (batch) -----------------------------------------------------------
    (date(2026, 5, 2), "GROCERY ONE", 5000, "debit", "personal", "Groceries", False, False),
    (date(2026, 5, 9), "GROCERY TWO", 3000, "debit", "personal", "Groceries", False, False),
    (date(2026, 5, 10), "UNSORTED CAFE", 1500, "debit", "personal", None, False, False),
    (date(2026, 5, 11), "WORK LUNCH EXPENSED", 8000, "debit", "work", None, True, False),
    (date(2026, 5, 12), "WORK SUPPLIES UNEXPENSED", 2000, "debit", "work", None, False, False),
    (date(2026, 5, 15), "PAYCHECK", 250000, "credit", "personal", "Income", False, False),
    (date(2026, 5, 16), "EXPENSE REIMBURSED", 4500, "credit", "personal", "Reimbursement", False, False),
    (date(2026, 5, 17), "CARD PAYMENT CREDIT", 30000, "credit", "personal", "Transfer", False, False),
    (date(2026, 5, 18), "HOBBY SHOP", 6000, "debit", "personal", "Hobbies", False, False),
    (date(2026, 5, 19), "INBOX UNCLASSIFIED", 999, "debit", None, None, False, False),
    # Manual ---------------------------------------------------------------------
    (date(2026, 5, 20), "MANUAL DINING", 2500, "debit", "personal", "Dining", False, True),
    (date(2026, 5, 21), "MANUAL WORK EXPENSED", 7000, "debit", "work", None, True, True),
    (date(2026, 5, 22), "MANUAL INCOME", 120000, "credit", "personal", "Income", False, True),
    (date(2026, 5, 23), "MANUAL TRANSFER", 15000, "debit", "personal", "Transfer", False, True),
]

# user_settings: defaults + one custom category ("Hobbies"), one hidden page.
CUSTOM_CATEGORY = "Hobbies"
HIDDEN_PAGE = "/exports"

# Tables whose row counts the sidecar pins.
COUNTED_TABLES = [
    "users",
    "user_settings",
    "import_profiles",
    "cards",
    "import_batches",
    "transactions",
]


def build_lineage_db(db_path: Path) -> None:
    """Create a DB at the current alembic head and seed it with the fixture rows."""
    # Importing inside the function keeps app import side effects out of module load
    # (and lets the caller set settings.database_url first if desired).
    from app.config import settings as app_settings
    from app.migrations import run_migrations
    from app.models.card import Card
    from app.models.import_batch import ImportBatch
    from app.models.import_profile import ImportProfile
    from app.models.transaction import Transaction
    from app.models.user import User
    from app.models.user_settings import UserSettings
    from app.services.auth_service import hash_password
    from app.services.transaction_rules import DEFAULT_CATEGORIES
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_url = f"sqlite:///{db_path}"
    app_settings.database_url = db_url
    run_migrations()

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        db.add(User(
            username=TEST_USERNAME,
            display_name=TEST_DISPLAY_NAME,
            hashed_password=hash_password(TEST_PASSWORD),
        ))
        # The user_settings migration already seeds a default id=1 row; update it
        # rather than insert (which would collide on the PK).
        settings_row = db.get(UserSettings, 1) or UserSettings(id=1)
        settings_row.personal_categories = list(DEFAULT_CATEGORIES) + [CUSTOM_CATEGORY]
        settings_row.hidden_pages = [HIDDEN_PAGE]
        db.add(settings_row)
        db.add(ImportProfile(
            name="Lineage Bank",
            source_type="checking",
            date_column=0,
            description_column=1,
            amount_column=2,
            amount_convention="signed",
            date_convention="dmy",
            ignored_payment_patterns=["AUTOPAY"],
        ))
        db.add(Card(id=CARD_ID, name="Lineage Card", last4="4242", statement_day=15))
        db.add(ImportBatch(
            id=IMPORT_BATCH_ID,
            filename="lineage-statement.csv",
            statement_format="Generic CSV",
            row_count=sum(1 for r in SEED_TRANSACTIONS if not r[7]),
            created_by_action="import",
        ))
        db.flush()  # ensure card/batch exist before FK references

        for i, (tx_date, desc, cents, ttype, classification, category, expensed, is_manual) in enumerate(
            SEED_TRANSACTIONS, start=1
        ):
            db.add(Transaction(
                transaction_date=tx_date,
                description=desc,
                amount_cents=cents,
                transaction_type=ttype,
                classification=classification,
                personal_category=category,
                expensed=expensed,
                is_manual=is_manual,
                statement_format=None if is_manual else "Generic CSV",
                source_hash=_manual_hash(i) if is_manual else _hashed(i),
                import_batch_id=None if is_manual else IMPORT_BATCH_ID,
                card_id=CARD_ID if desc in _CARD_LINKED_DESCRIPTIONS else None,
            ))
        db.commit()
    finally:
        db.close()
        engine.dispose()


def _signed_sum_key(ttype: str, classification) -> str:
    return f"{ttype}|{classification if classification is not None else 'None'}"


def collect_db_stats(conn: sqlite3.Connection) -> dict:
    """The frozen contract: stamped revision, per-table counts, signed sums.

    Used by both the generator (to write the sidecar) and the test (to re-check
    the migrated DB), so the two can never compute the contract differently.
    Signed amount = +amount_cents for credits, -amount_cents for debits.
    """
    revision_row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    table_counts = {
        table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in COUNTED_TABLES
    }
    signed_sums = {}
    for ttype, classification, total in conn.execute(
        "SELECT transaction_type, classification, "
        "SUM(CASE WHEN transaction_type = 'credit' THEN amount_cents ELSE -amount_cents END) "
        "FROM transactions GROUP BY transaction_type, classification"
    ):
        signed_sums[_signed_sum_key(ttype, classification)] = int(total)
    return {
        "head_revision": revision_row[0] if revision_row else None,
        "table_counts": table_counts,
        "signed_sums": signed_sums,
    }


def _app_version() -> str:
    from app.main import app

    return app.version


def _expected_path(db_path: Path) -> Path:
    return db_path.with_suffix(".expected.json")


def regenerate() -> Path:
    """Build the committed fixture + sidecar for the current app version & head."""
    from alembic.script import ScriptDirectory

    from app.migrations import _alembic_config

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    version = _app_version()
    db_path = FIXTURE_DIR / f"v{version}-{head}.db"
    if db_path.exists():
        db_path.unlink()
    build_lineage_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        stats = collect_db_stats(conn)
    finally:
        conn.close()
    payload = {"app_version": version, **stats}
    _expected_path(db_path).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return db_path


if __name__ == "__main__":
    path = regenerate()
    print(f"Wrote lineage fixture {path.name} (+ sidecar) at {datetime.now(timezone.utc).isoformat()}")
