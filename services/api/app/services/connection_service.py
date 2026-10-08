"""Salesforce connection lifecycle: OAuth start/callback, identity check, credential storage."""
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.cache.redis import cache_set_json, pop_json
from app.core.config import get_settings
from app.core.errors import AppError, Forbidden, NotFound
from app.core.security import pkce_pair
from app.db.models import SalesforceConnection
from app.integrations.salesforce.base import SalesforceError
from app.integrations.salesforce.mock import MockSalesforceConnector
from app.integrations.salesforce.oauth import SalesforceOAuthClient
from app.integrations.salesforce.rest import RestSalesforceConnector
from app.services import audit_service
from app.services.secret_store import get_secret_store

STATE_TTL = 600


def start_connection(db: Session, ctx: RequestContext) -> dict:
    ctx.require_role("owner", "admin")
    s = get_settings()
    state = secrets.token_urlsafe(32)
    verifier, challenge = pkce_pair()
    cache_set_json(f"oauth:state:{state}", {"user_id": str(ctx.user_id), "tenant_id": str(ctx.tenant_id),
                                             "verifier": verifier, "mode": s.salesforce_mode}, STATE_TTL)
    if s.salesforce_mode == "mock":
        url = f"{s.sf_callback_url}?code=mock-code&state={state}"  # same callback route as live
    else:
        if not s.sf_client_id:
            raise AppError("Salesforce External Client App is not configured (SF_CLIENT_ID)",
                           code="salesforce_not_configured")
        url = SalesforceOAuthClient().authorize_url(state, challenge)
    audit_service.record(db, "salesforce.oauth.start", ctx=ctx, resource_type="salesforce_connection",
                         metadata={"mode": s.salesforce_mode})
    db.commit()
    return {"authorization_url": url, "state_expires_in": STATE_TTL}


def complete_callback(db: Session, ctx: RequestContext, code: str | None, state: str | None,
                      error: str | None = None) -> SalesforceConnection:
    if error:
        audit_service.record(db, "salesforce.oauth.callback", ctx=ctx, result="failure", metadata={"error": error})
        db.commit()
        raise AppError(f"Salesforce authorization was not granted: {error}", code="oauth_denied")
    payload = pop_json(f"oauth:state:{state}") if state else None  # one-time use => replay protection
    if not payload:
        raise AppError("OAuth state is invalid or expired", code="oauth_state_invalid")
    if payload["user_id"] != str(ctx.user_id) or payload["tenant_id"] != str(ctx.tenant_id):
        audit_service.record(db, "salesforce.oauth.callback", ctx=ctx, result="failure",
                             metadata={"reason": "state_user_mismatch"})
        db.commit()
        raise Forbidden("OAuth state does not belong to this session")
    s = get_settings()
    store = get_secret_store(db)
    try:
        if payload["mode"] == "mock":
            identity = MockSalesforceConnector().get_identity()
            secret = {"access_token": "mock", "refresh_token": None, "instance_url": identity.instance_url}
            scopes, mode = ["api", "refresh_token"], "mock"
        else:
            tokens = SalesforceOAuthClient().exchange_code(code or "", payload["verifier"])
            identity = RestSalesforceConnector(tokens.to_secret(), s.sf_api_version).get_identity()
            secret = tokens.to_secret()
            scopes, mode = (tokens.scope or s.sf_scopes).split(), "live"
    except SalesforceError as exc:
        audit_service.record(db, "salesforce.oauth.callback", ctx=ctx, result="failure",
                             metadata={"error": str(exc)[:300]})
        db.commit()
        raise AppError(f"Salesforce connection failed: {exc}", code="salesforce_oauth_failed", status_code=502) from exc

    conn = db.scalar(select(SalesforceConnection).where(SalesforceConnection.tenant_id == ctx.tenant_id,
                                                        SalesforceConnection.org_id == identity.org_id))
    if conn is None:
        conn = SalesforceConnection(tenant_id=ctx.tenant_id, created_by=ctx.user_id, org_id=identity.org_id,
                                    instance_url=identity.instance_url, api_version=s.sf_api_version, mode=mode)
        db.add(conn)
    if conn.auth_ref:
        store.update(ctx.tenant_id, conn.auth_ref, secret)
    else:
        conn.auth_ref = store.put(ctx.tenant_id, "salesforce_oauth", secret)
    conn.org_name, conn.sf_username, conn.sf_user_id = identity.org_name, identity.username, identity.user_id
    conn.instance_url, conn.scopes, conn.status, conn.mode = identity.instance_url, scopes, "active", mode
    db.flush()
    audit_service.record(db, "salesforce.oauth.callback", ctx=ctx, resource_type="salesforce_connection",
                         resource_id=conn.id, metadata={"org_id": identity.org_id, "mode": mode})
    db.commit()
    return conn


def list_connections(db: Session, ctx: RequestContext) -> list[SalesforceConnection]:
    return list(db.scalars(select(SalesforceConnection).where(SalesforceConnection.tenant_id == ctx.tenant_id)
                           .order_by(SalesforceConnection.created_at.desc())))


def resolve_connection(db: Session, ctx: RequestContext, connection_id: uuid.UUID | str | None = None
                       ) -> SalesforceConnection:
    """Tenant-scoped lookup. Defaults to the most recent active connection (one-org prototype)."""
    stmt = select(SalesforceConnection).where(SalesforceConnection.tenant_id == ctx.tenant_id)
    if connection_id:
        try:
            cid = uuid.UUID(str(connection_id))
        except ValueError as exc:
            raise NotFound("Salesforce connection not found") from exc
        conn = db.scalar(stmt.where(SalesforceConnection.id == cid))
    else:
        conn = db.scalar(stmt.where(SalesforceConnection.status == "active")
                         .order_by(SalesforceConnection.created_at.desc()))
    if conn is None:
        raise NotFound("Salesforce connection not found — connect an org first")
    return conn


def disconnect(db: Session, ctx: RequestContext, connection_id) -> None:
    ctx.require_role("owner", "admin")
    conn = resolve_connection(db, ctx, connection_id)
    store = get_secret_store(db)
    if conn.auth_ref:
        try:
            if conn.mode == "live":
                tokens = store.get(ctx.tenant_id, conn.auth_ref)
                SalesforceOAuthClient().revoke(tokens.get("refresh_token") or tokens["access_token"])
        except Exception:  # noqa: BLE001 - best effort revoke
            pass
        ref = conn.auth_ref
        conn.auth_ref = None
        db.flush()
        store.delete(ctx.tenant_id, ref)
    conn.status = "revoked"
    audit_service.record(db, "salesforce.connection.revoke", ctx=ctx, resource_type="salesforce_connection",
                         resource_id=conn.id)
    db.commit()
