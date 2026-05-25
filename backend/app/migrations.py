from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def run_migrations() -> None:
    # Assumes a single backend process owns the database — there is no
    # cross-process lock around Alembic's `upgrade`. Safe in desktop mode
    # because only the Tauri-spawned backend touches the SQLite file.
    backend_dir = _backend_dir()
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")
