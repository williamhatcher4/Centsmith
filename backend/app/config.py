import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    target = base / "CreditTracker"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _default_database_url() -> str:
    if _is_frozen():
        return f"sqlite:///{_user_data_dir() / 'credit_tracker.db'}"
    return f"sqlite:///{Path(__file__).resolve().parents[2] / 'credit_tracker.db'}"


def _default_environment() -> str:
    return "production" if _is_frozen() else "development"


def _default_desktop_mode() -> bool:
    return _is_frozen()


class Settings(BaseSettings):
    environment: str = _default_environment()
    secret_key: str = "dev-credit-tracker-change-me"
    session_max_age: int = 60 * 60 * 24 * 14
    database_url: str = _default_database_url()
    cors_origins: str = "http://localhost:5175,http://127.0.0.1:5175"
    desktop_mode: bool = _default_desktop_mode()
    desktop_auth_token: str | None = None
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 15 * 60

    # Seed-only - consumed by scripts/seed_db.py, not the running app.
    admin_username: str | None = None
    admin_password: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
