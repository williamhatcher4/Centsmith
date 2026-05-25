from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import ensure_local_user, get_db
from app.services.desktop_auth_service import consume_desktop_token

router = APIRouter(tags=["desktop"])


_BOOTSTRAP_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Credit Tracker</title>
<style>body{font-family:system-ui,sans-serif;margin:2rem;color:#444}</style></head>
<body><p id="status">Signing you in...</p></body></html>
"""


@router.get("/desktop-bootstrap", include_in_schema=False)
def desktop_bootstrap():
    if not settings.desktop_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return HTMLResponse(_BOOTSTRAP_HTML)


@router.post("/desktop-login", include_in_schema=False)
def desktop_login(
    request: Request,
    token: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if not consume_desktop_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid desktop login token")
    user = ensure_local_user(db)
    request.session["user_id"] = user.id
    return {"status": "ok"}
