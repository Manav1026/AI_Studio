"""Application auth abstraction. The prototype ships a 'dev' provider (email sign-in, no password)
for controlled demo users; production swaps in an OIDC provider behind the same interface."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.core.config import get_settings
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_session_token
from app.db.models import Tenant, TenantUser, User


def dev_sign_in(db: Session, email: str, display_name: str | None = None) -> tuple[User, TenantUser]:
    if get_settings().auth_mode != "dev":
        raise Forbidden("Dev user sign-in is disabled")
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, display_name=display_name or email.split("@")[0])
        db.add(user)
        db.flush()
    membership = db.scalar(select(TenantUser).where(TenantUser.user_id == user.id).order_by(TenantUser.created_at))
    if membership is None:
        domain = email.split("@")[-1]
        tenant = db.scalar(select(Tenant).where(Tenant.name == domain))
        role = "member"
        if tenant is None:
            tenant = Tenant(name=domain)
            db.add(tenant)
            db.flush()
            role = "owner"
        membership = TenantUser(tenant_id=tenant.id, user_id=user.id, role=role)
        db.add(membership)
        db.flush()
    return user, membership


def context_from_token(db: Session, token: str, requested_tenant: str | None = None,
                       interface: str = "web") -> RequestContext:
    claims = decode_session_token(token)
    user_id = uuid.UUID(claims["sub"])
    tenant_id = uuid.UUID(requested_tenant) if requested_tenant else uuid.UUID(claims["tid"])
    row = db.execute(
        select(User, TenantUser).join(TenantUser, TenantUser.user_id == User.id)
        .where(User.id == user_id, TenantUser.tenant_id == tenant_id)
    ).first()
    if row is None:
        raise Unauthorized("No membership for this tenant")
    user, membership = row
    if user.status != "active":
        raise Unauthorized("User is not active")
    return RequestContext(user_id=user.id, tenant_id=tenant_id, role=membership.role, email=user.email,
                          interface=interface)
