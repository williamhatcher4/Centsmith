"""Migration-lineage test (plan item P5.4).

For each committed fixture under ``fixtures/lineage/*.db`` — a database seeded
through the real revision chain (see ``lineage_fixture.py``) — copy it to a temp
dir, run ``run_migrations()`` to head, then prove:

  (a) the DB reaches the current alembic head,
  (b) every frozen sidecar count and signed-amount sum still holds, and
  (c) the app actually *boots and serves* the upgraded data — login with the
      fixture password and ``GET /transactions`` returns the expected total.

This is the class of bug where revision N+1 assumes something only true of real
lineage. The committed fixture file (at the previous release's head) is migrated
to the current head on every test run, so a new migration that mangles real
lineage fails here even when fresh-create tests stay green.
"""

import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings as app_settings
from app.dependencies import get_db
from app.main import app
from app.migrations import _alembic_config, run_migrations
from app.services.auth_service import clear_all_login_failures
from app.services.desktop_auth_service import reset_desktop_token_for_tests
from tests.lineage_fixture import TEST_PASSWORD, TEST_USERNAME, collect_db_stats

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "lineage"
LINEAGE_DBS = sorted(FIXTURE_DIR.glob("*.db"))


@pytest.fixture(autouse=True)
def reset_auth_state():
    clear_all_login_failures()
    reset_desktop_token_for_tests()
    yield
    clear_all_login_failures()
    reset_desktop_token_for_tests()


def test_lineage_fixtures_exist():
    # A guard so an empty fixture dir doesn't silently pass the parameterized
    # test below (pytest skips a test with zero params).
    assert LINEAGE_DBS, (
        "No lineage fixtures found. Generate one from backend/ with:\n"
        "    python -m tests.lineage_fixture"
    )


@pytest.mark.parametrize("fixture_db", LINEAGE_DBS, ids=lambda p: p.name)
def test_lineage_db_upgrades_and_serves(fixture_db, tmp_path, monkeypatch):
    sidecar = json.loads(fixture_db.with_suffix(".expected.json").read_text(encoding="utf-8"))

    # Never mutate the committed fixture — work on a copy.
    live = tmp_path / "lineage.db"
    shutil.copyfile(fixture_db, live)
    monkeypatch.setattr(app_settings, "database_url", f"sqlite:///{live}")

    run_migrations()

    # (a) Reached the current head.
    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    conn = sqlite3.connect(str(live))
    try:
        stats = collect_db_stats(conn)
    finally:
        conn.close()
    assert stats["head_revision"] == head

    # (b) Every frozen count and signed sum still holds after the upgrade.
    assert stats["table_counts"] == sidecar["table_counts"]
    assert stats["signed_sums"] == sidecar["signed_sums"]

    # (c) The app boots and serves the upgraded data.
    engine = create_engine(f"sqlite:///{live}", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        login = client.post(
            "/api/v1/auth/login",
            data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        )
        assert login.status_code == 200, login.text
        resp = client.get("/api/v1/transactions")
        assert resp.status_code == 200
        assert resp.json()["total"] == sidecar["table_counts"]["transactions"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
