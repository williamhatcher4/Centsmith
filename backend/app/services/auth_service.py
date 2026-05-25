import time
from collections import deque
from threading import Lock

import bcrypt

from app.config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


_login_failures: dict[str, deque[float]] = {}
_login_failures_lock = Lock()


def _prune(attempts: deque[float], now: float) -> None:
    cutoff = now - settings.login_rate_limit_window_seconds
    while attempts and attempts[0] < cutoff:
        attempts.popleft()


def is_login_locked(username: str) -> bool:
    now = time.monotonic()
    with _login_failures_lock:
        attempts = _login_failures.get(username)
        if not attempts:
            return False
        _prune(attempts, now)
        return len(attempts) >= settings.login_rate_limit_attempts


def record_login_failure(username: str) -> None:
    now = time.monotonic()
    with _login_failures_lock:
        attempts = _login_failures.setdefault(username, deque())
        _prune(attempts, now)
        attempts.append(now)


def clear_login_failures(username: str) -> None:
    with _login_failures_lock:
        _login_failures.pop(username, None)


def clear_all_login_failures() -> None:
    with _login_failures_lock:
        _login_failures.clear()
