from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.deps import get_ctx
from app.db.models import AuditEvent
from app.db.session import get_db
from app.services import metrics_service

router = APIRouter(tags=["governance"])


@router.get("/audit")
def audit(action: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
          correlation_id: str | None = None, ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    ctx.require_role("owner", "admin")
    stmt = select(AuditEvent).where(AuditEvent.tenant_id == ctx.tenant_id)
    if action:
        stmt = stmt.where(AuditEvent.action.startswith(action))
    if correlation_id:
        stmt = stmt.where(AuditEvent.correlation_id == correlation_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset))
    return {"items": [{"id": str(e.id), "action": e.action, "result": e.result, "resource_type": e.resource_type,
                       "resource_id": e.resource_id, "user_id": str(e.user_id) if e.user_id else None,
                       "correlation_id": e.correlation_id, "created_at": e.created_at.isoformat(),
                       "metadata": e.metadata_json} for e in rows],
            "total": total, "limit": limit, "offset": offset}


@router.get("/metrics/summary")
def metrics(days: int = Query(30, ge=1, le=365), ctx: RequestContext = Depends(get_ctx),
            db: Session = Depends(get_db)):
    ctx.require_role("owner", "admin")
    return metrics_service.summary(db, ctx, days)
