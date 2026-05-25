import os
import secrets
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


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    _CRYPTPROTECT_UI_FORBIDDEN = 0x1

    def _dpapi_protect(plaintext: bytes) -> bytes:
        in_blob = _DATA_BLOB(
            len(plaintext),
            ctypes.cast(ctypes.c_char_p(plaintext), ctypes.POINTER(ctypes.c_byte)),
        )
        out_blob = _DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            None, None, None, None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out_blob),
        )
        if not ok:
            raise OSError("CryptProtectData failed")
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    def _dpapi_unprotect(blob: bytes) -> bytes:
        in_blob = _DATA_BLOB(
            len(blob),
            ctypes.cast(ctypes.c_char_p(blob), ctypes.POINTER(ctypes.c_byte)),
        )
        out_blob = _DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None, None, None, None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out_blob),
        )
        if not ok:
            raise OSError("CryptUnprotectData failed")
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _write_exclusive(path: Path, data: bytes) -> bool:
    try:
        with open(path, "xb") as fh:
            fh.write(data)
        return True
    except FileExistsError:
        return False


def _default_secret_key() -> str:
    if not _is_frozen():
        return "dev-credit-tracker-change-me"

    data_dir = _user_data_dir()

    if sys.platform == "win32":
        encrypted_path = data_dir / "secret.key.dpapi"
        legacy_path = data_dir / "secret.key"

        try:
            encrypted = encrypted_path.read_bytes()
        except FileNotFoundError:
            encrypted = b""

        if encrypted:
            try:
                return _dpapi_unprotect(encrypted).decode("utf-8")
            except OSError:
                # Wrong user profile, restored from non-DPAPI backup, or
                # corrupted blob. Rotate rather than refusing to start;
                # any active sessions are invalidated.
                sys.stderr.write(
                    "credit-tracker: secret.key.dpapi could not be decrypted; rotating key\n"
                )
                try:
                    encrypted_path.unlink()
                except FileNotFoundError:
                    pass

        if legacy_path.exists() and not encrypted_path.exists():
            try:
                plaintext = legacy_path.read_text(encoding="utf-8").strip()
            except OSError:
                plaintext = ""
            if plaintext:
                blob = _dpapi_protect(plaintext.encode("utf-8"))
                if _write_exclusive(encrypted_path, blob):
                    try:
                        legacy_path.unlink()
                    except FileNotFoundError:
                        pass
                    return plaintext

        try:
            existing = _dpapi_unprotect(encrypted_path.read_bytes()).decode("utf-8")
            return existing
        except (OSError, FileNotFoundError):
            pass

        secret = secrets.token_urlsafe(48)
        blob = _dpapi_protect(secret.encode("utf-8"))
        if _write_exclusive(encrypted_path, blob):
            return secret
        # Lost the race; read whoever won.
        try:
            return _dpapi_unprotect(encrypted_path.read_bytes()).decode("utf-8")
        except OSError:
            return secret

    secret_path = data_dir / "secret.key"
    try:
        existing = secret_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except FileNotFoundError:
        pass

    secret = secrets.token_urlsafe(48)
    if _write_exclusive(secret_path, secret.encode("utf-8")):
        return secret
    return secret_path.read_text(encoding="utf-8").strip()


class Settings(BaseSettings):
    environment: str = _default_environment()
    secret_key: str = _default_secret_key()
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
