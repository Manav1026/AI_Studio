from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.deps import SESSION_COOKIE, get_ctx
from app.auth.provider import dev_sign_in
from app.core.config import get_settings
from app.core.security import create_session_token
from app.db.models import Tenant, User
from app.db.session import get_db
from app.schemas.api import DevLoginIn, MeOut
from app.services import audit_service

router = APIRouter(tags=["identity"])


@router.post("/auth/dev-login")
def dev_login(body: DevLoginIn, response: Response, db: Session = Depends(get_db)):
    """Prototype sign-in for a small, controlled user group. Replaced by OIDC in production."""
    user, membership = dev_sign_in(db, body.email, body.display_name)
    token = create_session_token(str(user.id), str(membership.tenant_id), membership.role)
    s = get_settings()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax",
                        secure=s.app_env in ("staging", "production"), max_age=s.session_ttl_minutes * 60, path="/")
    audit_service.record(db, "auth.login", tenant_id=membership.tenant_id, user_id=user.id, resource_type="user",
                         resource_id=user.id, metadata={"mode": "dev"})
    db.commit()
    return {"user_id": str(user.id), "tenant_id": str(membership.tenant_id), "role": membership.role}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/auth/api-token")
def api_token(ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    """Short-lived bearer token for MCP clients / scripts. Same identity, same tenant scope."""
    token = create_session_token(str(ctx.user_id), str(ctx.tenant_id), ctx.role, ttl_minutes=60 * 8, scope="mcp")
    audit_service.record(db, "auth.api_token.issue", ctx=ctx, resource_type="user", resource_id=ctx.user_id)
    db.commit()
    return {"token": token, "expires_in": 8 * 3600, "token_type": "Bearer"}


@router.get("/me", response_model=MeOut)
def me(ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    s = get_settings()
    user, tenant = db.get(User, ctx.user_id), db.get(Tenant, ctx.tenant_id)
    return MeOut(user_id=str(user.id), email=user.email, display_name=user.display_name,
                 tenant_id=str(tenant.id), tenant_name=tenant.name, role=ctx.role, auth_mode=s.auth_mode,
                 salesforce_mode=s.salesforce_mode, ai_provider=s.ai_provider)
