import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.migrations import run_migrations
from app.routers import auth, desktop, transactions
from app.routers import imports as imports_router
from app.routers import settings as settings_router


def _frontend_dist_dir() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return bundle_root / "frontend" / "dist"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_migrations()
    yield


app = FastAPI(title="Centsmith", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_max_age,
    https_only=not settings.is_development and not settings.desktop_mode,
    same_site="lax",
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(desktop.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(settings_router.router, prefix="/api/v1")
app.include_router(imports_router.router, prefix="/api/v1")
app.include_router(transactions.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}


_dist = _frontend_dist_dir()
if _dist.is_dir():
    assets_dir = _dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path == "health":
            raise StarletteHTTPException(status_code=404)
        target = (_dist / full_path).resolve()
        if target.is_file() and _dist.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(_dist / "index.html")
