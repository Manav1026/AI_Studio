"""Operational KPIs from the blueprint (Section 14), computed from the system of record."""
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.cache.redis import get_redis
from app.db.base import utcnow
from app.db.models import AIUsage, AuditEvent, QueryExecution, SalesforceConnection, SyncRun


def summary(db: Session, ctx: RequestContext, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)
    t = ctx.tenant_id

    def count(stmt):
        return db.scalar(stmt) or 0

    oauth = dict(db.execute(select(AuditEvent.result, func.count()).where(
        AuditEvent.tenant_id == t, AuditEvent.action == "salesforce.oauth.callback", AuditEvent.created_at >= since)
        .group_by(AuditEvent.result)).all())
    status = dict(db.execute(select(QueryExecution.status, func.count()).where(
        QueryExecution.tenant_id == t, QueryExecution.created_at >= since).group_by(QueryExecution.status)).all())
    source = dict(db.execute(select(QueryExecution.source, func.count()).where(
        QueryExecution.tenant_id == t, QueryExecution.created_at >= since).group_by(QueryExecution.source)).all())
    planned = sum(status.values())
    ai = db.execute(select(func.coalesce(func.sum(AIUsage.input_tokens), 0),
                           func.coalesce(func.sum(AIUsage.output_tokens), 0),
                           func.coalesce(func.sum(AIUsage.estimated_cost), 0),
                           func.coalesce(func.avg(AIUsage.latency_ms), 0), func.count())
                    .where(AIUsage.tenant_id == t, AIUsage.created_at >= since)).one()
    by_model = [{"provider": p, "model": m, "requests": n, "tokens": int(tok or 0), "cost": float(c or 0)}
                for p, m, n, tok, c in db.execute(
                    select(AIUsage.provider, AIUsage.model, func.count(),
                           func.sum(AIUsage.input_tokens + AIUsage.output_tokens), func.sum(AIUsage.estimated_cost))
                    .where(AIUsage.tenant_id == t, AIUsage.created_at >= since)
                    .group_by(AIUsage.provider, AIUsage.model)).all()]
    exec_lat = db.execute(select(func.avg(QueryExecution.duration_ms),
                                 func.percentile_cont(0.95).within_group(QueryExecution.duration_ms))
                          .where(QueryExecution.tenant_id == t, QueryExecution.status == "succeeded",
                                 QueryExecution.created_at >= since)).one()
    syncs = db.execute(select(func.count(), func.avg(func.extract("epoch", SyncRun.completed_at - SyncRun.started_at)),
                              func.sum(SyncRun.error_count))
                       .where(SyncRun.tenant_id == t, SyncRun.created_at >= since)).one()
    mcp_calls = dict(db.execute(select(AuditEvent.result, func.count()).where(
        AuditEvent.tenant_id == t, AuditEvent.action == "mcp.tool_call", AuditEvent.created_at >= since)
        .group_by(AuditEvent.result)).all())
    conns = list(db.scalars(select(SalesforceConnection).where(SalesforceConnection.tenant_id == t)))
    r = get_redis()
    api_today = {str(c.id): int(r.get(f"sfapi:{c.id}:{date.today().isoformat()}") or 0) for c in conns}
    freshness = {str(c.id): c.last_sync_at.isoformat() if c.last_sync_at else None for c in conns}
    rejected = status.get("rejected", 0)
    return {
        "window_days": days,
        "oauth": {"success": oauth.get("success", 0), "failure": oauth.get("failure", 0)},
        "metadata_sync": {"runs": syncs[0] or 0, "avg_duration_s": round(float(syncs[1] or 0), 2),
                          "errors": int(syncs[2] or 0), "catalog_freshness": freshness},
        "queries": {"by_status": status, "by_source": source, "total": planned,
                    "validation_rejection_rate": round(rejected / planned, 3) if planned else 0.0,
                    "avg_execution_ms": round(float(exec_lat[0] or 0), 1),
                    "p95_execution_ms": round(float(exec_lat[1] or 0), 1)},
        "ai": {"requests": ai[4], "input_tokens": int(ai[0]), "output_tokens": int(ai[1]),
               "estimated_cost_usd": float(ai[2]), "avg_latency_ms": round(float(ai[3]), 1), "by_model": by_model},
        "saved_query_reuse_rate": round(source.get("template", 0) / planned, 3) if planned else 0.0,
        "salesforce_api_calls_today": api_today,
        "mcp_tool_calls": mcp_calls,
    }
