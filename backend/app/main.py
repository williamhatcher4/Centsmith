from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.database import Base, engine
from app.routers import auth, transactions

Base.metadata.create_all(bind=engine)

if engine.dialect.name == "sqlite":
    with engine.begin() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(transactions)").all()}
        if "expensed" not in columns:
            conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN expensed BOOLEAN NOT NULL DEFAULT 0")
        if "personal_category" not in columns:
            conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN personal_category VARCHAR(80)")

app = FastAPI(title="Credit Tracker", version="0.1.0")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=settings.session_max_age, https_only=not settings.is_development, same_site="lax")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router, prefix="/api/v1")
app.include_router(transactions.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}


_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
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
