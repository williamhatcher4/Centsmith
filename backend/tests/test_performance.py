"""Phase 2: large-ledger performance + index-usage checks.

Seeds a synthetic 50k-row ledger once per module and asserts the hot endpoints
stay within pragmatic local budgets and that core queries use indexes rather
than full scans. Marked ``perf`` so tight inner loops can skip via ``-m 'not perf'``.
"""

import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings as app_settings
from app.dependencies import get_db
from app.main import app
from app.migrations import run_migrations
from app.models.transaction import Transaction
from app.models.user import User
from app.services.auth_service import clear_all_login_failures, hash_password
from app.services.desktop_auth_service import reset_desktop_token_for_tests

pytestmark = pytest.mark.perf

ROW_COUNT = 50_000
CATEGORIES = ["Groceries", "Dining", "Transportation", "Home", "Shopping", "Travel"]

# Pragmatic local budgets on a 50k-row SQLite fixture (seconds).
LIST_BUDGET = 0.30
AGG_BUDGET = 0.80
LOOKUP_BUDGET = 0.30


def _seed(db) -> None:
    base = date(2020, 1, 1)
    objs = []
    for i in range(ROW_COUNT):
        classification = "personal" if i % 3 == 0 else ("work" if i % 3 == 1 else None)
        objs.append(
            Transaction(
                transaction_date=base + timedelta(days=i % 2000),
                description=f"Merchant {i % 500} #{i}",
                amount_cents=100 + (i % 9000),
                transaction_type="debit" if i % 4 else "credit",
                classification=classification,
                personal_category=CATEGORIES[i % len(CATEGORIES)] if classification == "personal" else None,
                expensed=(classification == "work" and i % 2 == 0),
                is_manual=False,
                statement_format="Generic CSV",
                source_hash=f"perf-{i}",
            )
        )
        if len(objs) >= 5000:
            db.bulk_save_objects(objs)
            objs = []
    if objs:
        db.bulk_save_objects(objs)
    db.commit()
    # Give the SQLite planner stats so it reliably chooses the new indexes.
    db.execute(text("ANALYZE"))
    db.commit()


@pytest.fixture(scope="module")
def perf_db(tmp_path_factory):
    clear_all_login_failures()
    reset_desktop_token_for_tests()
    db_path = tmp_path_factory.mktemp("perf") / "perf.db"
    db_url = f"sqlite:///{db_path}"
    original = app_settings.database_url
    app_settings.database_url = db_url
    run_migrations()
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    db.add(User(username="user1", display_name="User 1", hashed_password=hash_password("password")))
    db.commit()
    _seed(db)
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
        app_settings.database_url = original
        clear_all_login_failures()
        reset_desktop_token_for_tests()


@pytest.fixture()
def perf_client(perf_db):
    def override_get_db():
        yield perf_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as tc:
        tc.post("/api/v1/auth/login", data={"username": "user1", "password": "password"})
        yield tc
    app.dependency_overrides.clear()


def _timed_get(client, path, params=None):
    start = time.perf_counter()
    resp = client.get(path, params=params or {})
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    return resp, elapsed


def test_transaction_list_is_fast_and_paged(perf_client):
    resp, elapsed = _timed_get(perf_client, "/api/v1/transactions", {"classification": "personal", "limit": 200})
    body = resp.json()
    assert body["total"] > 0
    assert len(body["items"]) == 200
    assert body["has_more"] is True  # never silently truncates
    assert elapsed < LIST_BUDGET, f"list took {elapsed:.3f}s"


def test_dashboard_is_fast(perf_client):
    _, elapsed = _timed_get(perf_client, "/api/v1/transactions/dashboard")
    assert elapsed < AGG_BUDGET, f"dashboard took {elapsed:.3f}s"


def test_personal_spending_is_fast(perf_client):
    _, elapsed = _timed_get(perf_client, "/api/v1/transactions/spending/personal")
    assert elapsed < AGG_BUDGET, f"spending took {elapsed:.3f}s"


def test_export_is_fast(perf_client):
    start = time.perf_counter()
    resp = perf_client.get("/api/v1/transactions/export/personal")
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert elapsed < AGG_BUDGET, f"export took {elapsed:.3f}s"


def test_duplicate_hash_lookup_is_fast(perf_db):
    from app.services.transaction_import_service import _existing_hashes
    from app.services.statement_import_service import ParsedRow

    rows = [
        ParsedRow(
            row_number=i,
            transaction_date=date(2026, 1, 1),
            description="x",
            amount_cents=1,
            transaction_type="debit",
            source_hash=f"perf-{i}",
        )
        for i in range(0, 1000)
    ]
    start = time.perf_counter()
    existing = _existing_hashes(perf_db, rows)
    elapsed = time.perf_counter() - start
    assert len(existing) == 1000
    assert elapsed < LOOKUP_BUDGET, f"duplicate lookup took {elapsed:.3f}s"


def _query_plan(db, sql: str) -> str:
    rows = db.execute(text(f"EXPLAIN QUERY PLAN {sql}")).fetchall()
    return " ".join(str(r[-1]) for r in rows)


def test_core_filters_use_indexes(perf_db):
    # Date range + classification + category filters and the dup-hash lookup
    # should all resolve via an index, not a full table scan.
    date_plan = _query_plan(perf_db, "SELECT id FROM transactions WHERE transaction_date >= '2024-01-01' ORDER BY transaction_date DESC LIMIT 50")
    # An index plan reads "USING INDEX"/"USING COVERING INDEX"; a full scan would
    # read "SCAN transactions" with no INDEX. Assert the planner avoids the scan.
    date_plan = date_plan.upper()
    assert "INDEX" in date_plan and "SCAN" not in date_plan.replace("USING", "")

    class_plan = _query_plan(perf_db, "SELECT id FROM transactions WHERE classification = 'personal'").upper()
    assert "INDEX" in class_plan

    cat_plan = _query_plan(perf_db, "SELECT id FROM transactions WHERE personal_category = 'Groceries'").upper()
    assert "INDEX" in cat_plan

    hash_plan = _query_plan(perf_db, "SELECT id FROM transactions WHERE source_hash = 'perf-1'").upper()
    assert "INDEX" in hash_plan
