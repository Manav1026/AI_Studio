from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.provider import context_from_token
from app.core.errors import Unauthorized
from app.db.session import get_db

SESSION_COOKIE = "sfai_session"


def get_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return cookie
    raise Unauthorized("Not signed in")


def get_ctx(request: Request, db: Session = Depends(get_db)) -> RequestContext:
    token = get_token(request)
    return context_from_token(db, token, request.headers.get("X-Tenant-Id"),
                              interface="api" if request.headers.get("Authorization") else "web")
