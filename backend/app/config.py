from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    secret_key: str = "dev-credit-tracker-change-me"
    session_max_age: int = 60 * 60 * 24 * 14
    database_url: str = f"sqlite:///{Path(__file__).resolve().parents[2] / 'credit_tracker.db'}"
    cors_origins: str = "http://localhost:5175,http://127.0.0.1:5175"

    # Seed-only — consumed by scripts/seed_db.py, not the running app.
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
