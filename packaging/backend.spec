# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Centsmith backend sidecar.

Build from the repo root with the backend venv active:

    pyinstaller packaging/backend.spec

Output: packaging/dist/centsmith-backend/centsmith-backend.exe
Bundles app/ + frontend/dist/ so the running exe self-serves the static UI.
"""
import sys
from pathlib import Path

# When PyInstaller invokes a spec, __file__ is not defined the same way as a
# normal script — fall back to the current working directory (the repo root).
HERE = Path(SPECPATH).resolve()
REPO = HERE.parent
BACKEND = REPO / "backend"
FRONTEND_DIST = REPO / "frontend" / "dist"

if not FRONTEND_DIST.is_dir():
    raise SystemExit(
        f"frontend/dist not found at {FRONTEND_DIST}. "
        "Run `npm run build` in frontend/ before packaging."
    )

sys.path.insert(0, str(BACKEND))

datas = [
    (str(FRONTEND_DIST), "frontend/dist"),
    (str(BACKEND / "alembic.ini"), "."),
    (str(BACKEND / "alembic"), "alembic"),
]

hiddenimports = [
    "app.main",
    "app.config",
    "app.database",
    "app.dependencies",
    "app.migrations",
    "app.routers.desktop",
    "app.routers.auth",
    "app.routers.transactions",
    "app.models.user",
    "app.models.transaction",
    "app.schemas.transaction",
    "app.services.auth_service",
    "app.services.desktop_auth_service",
    "app.services.statement_import_service",
    "app.services.transaction_import_service",
    "alembic",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "bcrypt",
    "xlrd",
    "openpyxl",
]

a = Analysis(
    [str(HERE / "backend_entry.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PIL", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="centsmith-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="centsmith-backend",
)
