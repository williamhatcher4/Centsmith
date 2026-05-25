"""PyInstaller entry point for the Credit Tracker backend sidecar.

Picks a free port, writes it to %APPDATA%\\CreditTracker\\port.txt so the Tauri
shell can discover it, then launches uvicorn against ``app.main:app``.

This module is the value of ``backend.spec``'s ``Analysis(...)`` first arg, so
it must be importable standalone — no relative imports from ``app``.
"""
from __future__ import annotations

import os
import socket
import sys
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


def main() -> None:
    os.environ.setdefault("DESKTOP_MODE", "1")
    os.environ.setdefault("ENVIRONMENT", "production")

    port_override = os.environ.get("CREDIT_TRACKER_PORT")
    port = int(port_override) if port_override else _pick_free_port()

    data_dir = _user_data_dir()
    port_file = data_dir / "port.txt"
    pid_file = data_dir / "backend.pid"

    port_file.write_text(str(port), encoding="utf-8")
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    import uvicorn
    from app.main import app

    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        for path in (port_file, pid_file):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
