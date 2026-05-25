import secrets
from threading import Lock

from app.config import settings

_token_lock = Lock()
_token_consumed = False


def consume_desktop_token(token: str | None) -> bool:
    global _token_consumed
    expected = settings.desktop_auth_token
    if not settings.desktop_mode or not expected or not token:
        return False
    with _token_lock:
        if _token_consumed:
            return False
        if not secrets.compare_digest(token, expected):
            return False
        _token_consumed = True
        return True


def reset_desktop_token_for_tests() -> None:
    global _token_consumed
    with _token_lock:
        _token_consumed = False
