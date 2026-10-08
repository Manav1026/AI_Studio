from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.deps import get_ctx
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import SalesforceConnection, SyncRun
from app.db.session import get_db
from app.integrations.salesforce.factory import get_connector
from app.schemas.api import ConnectionOut, StartConnectionOut
from app.services import connection_service, metadata_service

router = APIRouter(prefix="/salesforce", tags=["salesforce"])


def _latest_sync(db: Session, conn_id) -> dict | None:
    run = db.scalar(select(SyncRun).where(SyncRun.connection_id == conn_id).order_by(SyncRun.created_at.desc()))
    if run is None:
        return None
    return {"id": str(run.id), "status": run.status, "objects_seen": run.objects_seen, "fields_seen": run.fields_seen,
            "relationships_seen": run.relationships_seen, "error_count": run.error_count,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None}


def _out(db: Session, c: SalesforceConnection) -> ConnectionOut:
    return ConnectionOut(id=str(c.id), org_id=c.org_id, org_name=c.org_name, instance_url=c.instance_url,
                         sf_username=c.sf_username, mode=c.mode, status=c.status, scopes=c.scopes or [],
                         api_version=c.api_version, last_sync_at=c.last_sync_at.isoformat() if c.last_sync_at else None,
                         catalog_version=c.catalog_version, latest_sync=_latest_sync(db, c.id))


@router.post("/connections", response_model=StartConnectionOut)
def start_connection(ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    return connection_service.start_connection(db, ctx)


@router.get("/oauth/callback")
def oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None,
                   error_description: str | None = None, ctx: RequestContext = Depends(get_ctx),
                   db: Session = Depends(get_db)):
    web = get_settings().web_base_url
    try:
        conn = connection_service.complete_callback(db, ctx, code, state, error)
    except AppError as exc:
        return RedirectResponse(f"{web}/connections?error={exc.code}", status_code=302)
    metadata_service.queue_sync(db, conn, ctx.user_id)
    return RedirectResponse(f"{web}/connections?connected={conn.id}", status_code=302)


@router.get("/connections", response_model=list[ConnectionOut])
def list_connections(ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    return [_out(db, c) for c in connection_service.list_connections(db, ctx)]


@router.post("/connections/{connection_id}/sync")
def start_sync(connection_id: str, ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_role("owner", "admin")
    conn = connection_service.resolve_connection(db, ctx, connection_id)
    if conn.status != "active":
        raise AppError("Connection is not active", code="connection_inactive", status_code=409)
    run = metadata_service.queue_sync(db, conn, ctx.user_id)
    db.refresh(run)
    return {"sync_run_id": str(run.id), "status": run.status}


@router.get("/connections/{connection_id}/org-info")
def org_info(connection_id: str, ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    conn = connection_service.resolve_connection(db, ctx, connection_id)
    limits = get_connector(db, conn).get_limits()
    daily = limits.get("DailyApiRequests", {})
    return {"org_id": conn.org_id, "org_name": conn.org_name, "instance_url": conn.instance_url, "mode": conn.mode,
            "api_version": conn.api_version, "daily_api_requests": daily}


@router.delete("/connections/{connection_id}")
def disconnect(connection_id: str, ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    connection_service.disconnect(db, ctx, connection_id)
    return {"ok": True}


@router.get("/connections/{connection_id}/sync-runs")
def sync_runs(connection_id: str, limit: int = Query(10, le=100), ctx: RequestContext = Depends(get_ctx),
              db: Session = Depends(get_db)):
    conn = connection_service.resolve_connection(db, ctx, connection_id)
    runs = db.scalars(select(SyncRun).where(SyncRun.connection_id == conn.id).order_by(SyncRun.created_at.desc())
                      .limit(limit))
    return [{"id": str(r.id), "status": r.status, "objects_seen": r.objects_seen, "fields_seen": r.fields_seen,
             "relationships_seen": r.relationships_seen, "error_count": r.error_count, "error_detail": r.error_detail,
             "started_at": r.started_at.isoformat() if r.started_at else None,
             "completed_at": r.completed_at.isoformat() if r.completed_at else None} for r in runs]
