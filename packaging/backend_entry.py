"""PyInstaller entry point for the Credit Tracker backend sidecar.

Picks a free port, writes runtime metadata to %APPDATA%\\CreditTracker so the
Tauri shell can discover it, then launches uvicorn against ``app.main:app``.

This module is the value of ``backend.spec``'s ``Analysis(...)`` first arg, so
it must be importable standalone; no relative imports from ``app``.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import traceback
from pathlib import Path


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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


def _debug_log(data_dir: Path, message: str) -> None:
    try:
        with (data_dir / "backend-sidecar.log").open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


def main() -> None:
    os.environ.setdefault("DESKTOP_MODE", "1")
    os.environ.setdefault("ENVIRONMENT", "production")

    port_override = os.environ.get("CREDIT_TRACKER_PORT")
    port = int(port_override) if port_override else _pick_free_port()
    token = secrets.token_urlsafe(32)
    os.environ["DESKTOP_AUTH_TOKEN"] = token

    data_dir = _user_data_dir()
    runtime_file = data_dir / "runtime.json"
    pid_file = data_dir / "backend.pid"

    runtime_file.write_text(json.dumps({"port": port, "token": token}), encoding="utf-8")
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    try:
        _debug_log(data_dir, "importing uvicorn")
        import uvicorn

        _debug_log(data_dir, "importing app.main")
        from app.main import app

        _debug_log(data_dir, f"starting uvicorn on port {port}")
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    except Exception:
        _debug_log(data_dir, traceback.format_exc())
        raise
    finally:
        for path in (runtime_file, pid_file):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
