from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.deps import get_ctx
from app.cache.redis import cache_get_json, cache_set_json
from app.db.session import get_db
from app.schemas.api import ExecuteIn, PlanIn, ValidateIn
from app.services import audit_service, connection_service, query_service

router = APIRouter(prefix="/query", tags=["query"])


@router.post("/plan")
def plan(body: PlanIn, ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    """Generate a structured plan + SOQL and validate it. Never executes."""
    conn = connection_service.resolve_connection(db, ctx, body.connection_id)
    return query_service.plan(db, ctx, conn, body.question, body.use_templates)


@router.post("/validate")
def validate(body: ValidateIn, ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    conn = connection_service.resolve_connection(db, ctx, body.connection_id)
    result = query_service.validate(db, ctx, conn, body.soql)
    audit_service.record(db, "query.validate", ctx=ctx, result="success" if result.valid else "rejected")
    db.commit()
    return result.to_dict()


@router.post("/execute")
def execute(body: ExecuteIn, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
            ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    """Explicit, authorised, read-only execution. Supports Idempotency-Key for safe client retries."""
    idem = f"idem:{ctx.tenant_id}:{ctx.user_id}:{idempotency_key}" if idempotency_key else None
    if idem and (prior := cache_get_json(idem)):
        return {**prior, "idempotent_replay": True}
    conn = connection_service.resolve_connection(db, ctx, body.connection_id)
    out = query_service.execute(db, ctx, conn, execution_id=body.execution_id, soql=body.soql)
    if idem:
        cache_set_json(idem, out, 86400)
    return out


@router.get("/history")
def history(limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), scope: str = "mine",
            ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    mine = scope != "tenant" or ctx.role not in ("owner", "admin")
    items, total = query_service.history(db, ctx, limit, offset, mine_only=mine)
    return {"items": items, "total": total, "limit": limit, "offset": offset}
