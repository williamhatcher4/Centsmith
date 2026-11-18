# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Centsmith backend sidecar.

Build from the repo root with the backend venv active:

    pyinstaller packaging/backend.spec

Output: packaging/dist/centsmith-backend/centsmith-backend.exe
Bundles app/ + frontend/dist/ so the running exe self-serves the static UI.
"""
import json
import re
import sys
from pathlib import Path

# When PyInstaller invokes a spec, __file__ is not defined the same way as a
# normal script — fall back to the current working directory (the repo root).
HERE = Path(SPECPATH).resolve()
REPO = HERE.parent
BACKEND = REPO / "backend"
FRONTEND_DIST = REPO / "frontend" / "dist"
TAURI_CONF = REPO / "desktop" / "src-tauri" / "tauri.conf.json"

if not FRONTEND_DIST.is_dir():
    raise SystemExit(
        f"frontend/dist not found at {FRONTEND_DIST}. "
        "Run `npm run build` in frontend/ before packaging."
    )


def _write_version_info(dest: Path) -> Path:
    """Write a Windows version resource for centsmith-backend.exe.

    Release signing (SignPath) only signs files whose ProductName and
    ProductVersion match the release, the same metadata Tauri embeds in the
    shell exe and installer. Values come from tauri.conf.json, whose version CI
    syncs from the release tag before this spec runs (locally it stays 0.1.0).
    """
    conf = json.loads(TAURI_CONF.read_text(encoding="utf-8-sig"))
    product = conf["productName"]
    version = conf["version"]
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise SystemExit(f"tauri.conf.json version {version!r} is not x.y.z")
    numeric = tuple(int(part) for part in match.groups()) + (0,)
    bundle = conf.get("bundle", {})
    strings = {
        "CompanyName": bundle.get("publisher", product),
        "FileDescription": f"{product} backend",
        "FileVersion": version,
        "InternalName": "centsmith-backend",
        "LegalCopyright": bundle.get("copyright", ""),
        "OriginalFilename": "centsmith-backend.exe",
        "ProductName": product,
        "ProductVersion": version,
    }
    entries = ",\n          ".join(
        f"StringStruct({key!r}, {value!r})" for key, value in strings.items()
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric!r},
    prodvers={numeric!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
          {entries}
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    return dest


VERSION_FILE = _write_version_info(Path(workpath) / "centsmith-backend-version.txt")

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
    version=str(VERSION_FILE),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="centsmith-backend",
)
