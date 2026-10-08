"""Query engine orchestration — Flow C of the blueprint:
question -> context retrieval -> template match -> plan (AI) -> SOQL -> validate -> (explicit) execute."""
import hashlib
import json
import time
import uuid
from datetime import date

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.cache.redis import cache_get_json, cache_set_json, enforce_rate_limit
from app.core.config import get_settings
from app.core.context import get_correlation_id
from app.core.errors import AppError, NotFound, UpstreamError
from app.core.logging import get_logger
from app.core.telemetry import tracer
from app.db.base import utcnow
from app.db.models import AIUsage, QueryExecution, SalesforceConnection
from app.domain.policy import QueryPolicy
from app.domain.query_plan import PlanBuildError, QueryPlan, plan_to_soql
from app.domain.soql.ast import FieldRef
from app.domain.soql.parser import parse_soql
from app.domain.soql.validator import ValidationResult, validate_soql
from app.integrations.ai.base import AIRequest
from app.integrations.ai.gateway import AIGateway, estimate_cost
from app.integrations.ai.prompts import PLAN_JSON_SCHEMA, PROMPT_VERSION, SYSTEM_PROMPT, render_user_prompt
from app.integrations.salesforce.base import SalesforceAuthError, SalesforceError
from app.integrations.salesforce.factory import get_connector
from app.services import audit_service, catalog_service, saved_query_service

log = get_logger("query")


def _policy() -> QueryPolicy:
    return QueryPolicy.from_settings(get_settings())


def _require_catalog(conn: SalesforceConnection) -> None:
    if not conn.catalog_version:
        raise AppError("Metadata has not been synchronised yet for this connection", code="catalog_not_ready",
                       status_code=409)


def validate(db: Session, ctx: RequestContext, conn: SalesforceConnection, soql: str) -> ValidationResult:
    _require_catalog(conn)
    view = catalog_service.load_view(db, conn)
    with tracer.start_as_current_span("query.validate"):
        return validate_soql(soql, view, _policy())


def plan(db: Session, ctx: RequestContext, conn: SalesforceConnection, question: str,
         use_templates: bool = True) -> dict:
    _require_catalog(conn)
    s = get_settings()
    view = catalog_service.load_view(db, conn)
    execution = QueryExecution(tenant_id=ctx.tenant_id, connection_id=conn.id, user_id=ctx.user_id,
                               question=question, interface=ctx.interface, correlation_id=get_correlation_id())
    db.add(execution)

    # 1. Saved-query template match => zero AI tokens
    if use_templates:
        match = saved_query_service.match_template(db, ctx, conn, question, s.template_match_threshold)
        if match:
            sq, params, score = match
            soql = saved_query_service.render(sq, params)
            result = validate_soql(soql, view, _policy())
            if result.valid:
                execution.saved_query_id, execution.source = sq.id, "template"
                execution.plan_json = sq.plan_json
                execution.generated_soql = result.normalized_soql
                execution.validation_json = result.to_dict()
                execution.status = "validated"
                execution.explanation = (f"Reused saved query “{sq.name}” (v{sq.version}, match {score:.0%}) "
                                         f"with parameters {json.dumps(params)} — no AI call was needed.")
                execution.token_usage = {"input_tokens": 0, "output_tokens": 0, "saved_by_template": True}
                db.flush()
                audit_service.record(db, "query.plan", ctx=ctx, resource_type="query_execution",
                                     resource_id=execution.id, metadata={"source": "template",
                                                                         "saved_query_id": str(sq.id)})
                db.commit()
                return _plan_response(execution, result, context_objects=[], template={"id": str(sq.id),
                                      "name": sq.name, "score": round(score, 3), "parameters": params})

    # 2. Retrieve only the relevant catalog context
    enforce_rate_limit("ai", str(ctx.user_id), s.rate_limit_ai_per_minute)
    context = catalog_service.build_ai_context(view, question)
    context["today"] = date.today().isoformat()
    req = AIRequest(task="nl_to_plan", system=SYSTEM_PROMPT, user=render_user_prompt(question, context),
                    json_schema=PLAN_JSON_SCHEMA, context={**context, "question": question})
    gateway = AIGateway()
    resp = gateway.complete(req)
    execution.model = f"{resp.provider}:{resp.model}"
    execution.token_usage = {"input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens}
    db.flush()
    db.add(AIUsage(tenant_id=ctx.tenant_id, execution_id=execution.id, provider=resp.provider, model=resp.model,
                   prompt_version=PROMPT_VERSION, input_tokens=resp.input_tokens,
                   output_tokens=resp.output_tokens,
                   estimated_cost=estimate_cost(resp.model, resp.input_tokens, resp.output_tokens),
                   latency_ms=resp.latency_ms))

    # 3. Treat model output as untrusted: schema-validate, compile deterministically, validate
    try:
        raw = gateway.parse_json(resp.content)
        qp = QueryPlan.model_validate(raw)
        execution.plan_json = qp.model_dump()
        execution.explanation = qp.explanation
        soql = plan_to_soql(qp, view, _policy().default_limit)
    except (ValueError, ValidationError, PlanBuildError) as exc:
        execution.status, execution.error = "rejected", f"Invalid plan from model: {str(exc)[:400]}"
        execution.validation_json = {"valid": False, "issues": [{"code": "invalid_plan", "message": str(exc)[:400],
                                                                 "severity": "error", "path": None}]}
        audit_service.record(db, "query.plan", ctx=ctx, resource_type="query_execution", resource_id=execution.id,
                             result="rejected", metadata={"reason": "invalid_plan"})
        db.commit()
        return _plan_response(execution, None, context["selected_objects"])
    result = validate_soql(soql, view, _policy())
    execution.generated_soql = result.normalized_soql or soql
    execution.validation_json = result.to_dict()
    execution.status = "validated" if result.valid else "rejected"
    audit_service.record(db, "query.plan", ctx=ctx, resource_type="query_execution", resource_id=execution.id,
                         result="success" if result.valid else "rejected",
                         metadata={"source": "ai", "model": execution.model})
    db.commit()
    return _plan_response(execution, result, context["selected_objects"])


def _plan_response(ex: QueryExecution, result: ValidationResult | None, context_objects, template=None) -> dict:
    return {"execution_id": str(ex.id), "status": ex.status, "source": ex.source if template is None else "template",
            "question": ex.question, "plan": ex.plan_json, "soql": ex.generated_soql,
            "explanation": ex.explanation, "validation": ex.validation_json if result is None else result.to_dict(),
            "context_objects": context_objects, "template": template, "model": ex.model,
            "token_usage": ex.token_usage, "correlation_id": ex.correlation_id}


# ---- execution ---------------------------------------------------------------------------
def _columns(soql: str) -> list[str]:
    q = parse_soql(soql)
    cols, expr_i = [], 0
    agg = q.has_aggregates or bool(q.group_by)
    for item in q.select:
        if isinstance(item.expr, FieldRef):
            cols.append(item.expr.path[-1] if agg else item.expr.dotted)
        else:
            cols.append(item.alias or f"expr{expr_i}")
            expr_i += 0 if item.alias else 1
    return cols


def _flatten(rec: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in rec.items():
        if k == "attributes":
            continue
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def execute(db: Session, ctx: RequestContext, conn: SalesforceConnection, *, execution_id: str | None = None,
            soql: str | None = None, saved_query_id=None, question: str | None = None,
            source: str = "manual") -> dict:
    """Explicit execution. ALWAYS re-validates — a stored plan is never trusted blindly."""
    s = get_settings()
    _require_catalog(conn)
    enforce_rate_limit("query", str(ctx.user_id), s.rate_limit_query_per_minute)
    if execution_id:
        try:
            ex = db.get(QueryExecution, uuid.UUID(str(execution_id)))
        except ValueError:
            ex = None
        if ex is None or ex.tenant_id != ctx.tenant_id or ex.connection_id != conn.id:
            raise NotFound("Query execution not found")
        if not ex.generated_soql:
            raise AppError("This plan has no executable SOQL", code="not_executable")
        if ex.status == "succeeded":  # re-run as a new execution, preserving lineage
            ex = QueryExecution(tenant_id=ctx.tenant_id, connection_id=conn.id, user_id=ctx.user_id,
                                question=ex.question, plan_json=ex.plan_json, generated_soql=ex.generated_soql,
                                explanation=ex.explanation, source=ex.source, saved_query_id=ex.saved_query_id,
                                interface=ctx.interface, correlation_id=get_correlation_id())
            db.add(ex)
        soql_to_run = ex.generated_soql
    else:
        if not soql:
            raise AppError("Provide execution_id or soql", code="bad_request")
        ex = QueryExecution(tenant_id=ctx.tenant_id, connection_id=conn.id, user_id=ctx.user_id, question=question,
                            generated_soql=soql, source=source, saved_query_id=saved_query_id,
                            interface=ctx.interface, correlation_id=get_correlation_id())
        db.add(ex)
        soql_to_run = soql
    ex.interface = ctx.interface
    ex.correlation_id = get_correlation_id()
    db.flush()

    view = catalog_service.load_view(db, conn)
    result = validate_soql(soql_to_run, view, _policy())
    ex.validation_json = result.to_dict()
    if not result.valid:
        ex.status = "rejected"
        audit_service.record(db, "query.execute", ctx=ctx, resource_type="query_execution", resource_id=ex.id,
                             result="rejected", metadata={"issues": [i.code for i in result.issues]})
        db.commit()
        raise AppError("Query failed validation and was not executed", code="validation_failed",
                       status_code=422, details={"execution_id": str(ex.id), **result.to_dict()})
    final_soql = result.normalized_soql
    ex.generated_soql = final_soql
    audit_service.record(db, "query.execute.start", ctx=ctx, resource_type="query_execution", resource_id=ex.id,
                         metadata={"soql_sha": hashlib.sha256(final_soql.encode()).hexdigest()[:16]})
    db.commit()

    # Result cache is per *user* because Salesforce sharing/FLS differ per user.
    cache_key = (f"qr:{conn.id}:{conn.catalog_version}:{ctx.user_id}:"
                 f"{hashlib.sha256(final_soql.encode()).hexdigest()}")
    cached = cache_get_json(cache_key)
    start = time.perf_counter()
    if cached:
        rows, total = cached["rows"], cached["total"]
    else:
        try:
            with tracer.start_as_current_span("salesforce.query"):
                qr = get_connector(db, conn).query(final_soql, max_records=s.query_max_limit)
        except (SalesforceAuthError, SalesforceError) as exc:
            ex.status, ex.error = "failed", str(exc)[:500]
            ex.duration_ms = int((time.perf_counter() - start) * 1000)
            if isinstance(exc, SalesforceAuthError):
                conn.status = "error"
            audit_service.record(db, "query.execute", ctx=ctx, resource_type="query_execution", resource_id=ex.id,
                                 result="failure", metadata={"error": str(exc)[:300]})
            db.commit()
            raise UpstreamError(f"Salesforce rejected the query: {exc}",
                                details={"execution_id": str(ex.id), "salesforce_error": getattr(exc, "error_code", None)}
                                ) from exc
        rows, total = [_flatten(r) for r in qr.records], qr.total_size
        cache_set_json(cache_key, {"rows": rows, "total": total}, s.result_cache_ttl_seconds)
    duration = int((time.perf_counter() - start) * 1000)
    columns = _columns(final_soql)
    extra = [k for r in rows[:1] for k in r if k not in columns]
    ex.status, ex.row_count, ex.duration_ms, ex.executed_at = "succeeded", len(rows), duration, utcnow()
    audit_service.record(db, "query.execute", ctx=ctx, resource_type="query_execution", resource_id=ex.id,
                         metadata={"rows": len(rows), "duration_ms": duration, "cached": bool(cached)})
    db.commit()
    return {"execution_id": str(ex.id), "status": ex.status, "soql": final_soql, "columns": columns + extra,
            "rows": rows, "row_count": len(rows), "total_size": total, "duration_ms": duration,
            "cached": bool(cached), "explanation": ex.explanation, "source": ex.source,
            "warnings": [i.to_dict() for i in result.issues if i.severity == "warning"],
            "correlation_id": ex.correlation_id}


def history(db: Session, ctx: RequestContext, limit: int, offset: int, mine_only: bool = True):
    from sqlalchemy import func
    stmt = select(QueryExecution).where(QueryExecution.tenant_id == ctx.tenant_id)
    if mine_only:
        stmt = stmt.where(QueryExecution.user_id == ctx.user_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(QueryExecution.created_at.desc()).limit(limit).offset(offset))
    return [{"id": str(r.id), "question": r.question, "soql": r.generated_soql, "status": r.status,
             "source": r.source, "interface": r.interface, "row_count": r.row_count, "duration_ms": r.duration_ms,
             "model": r.model, "token_usage": r.token_usage, "saved_query_id": str(r.saved_query_id) if r.saved_query_id else None,
             "created_at": r.created_at.isoformat(), "correlation_id": r.correlation_id} for r in rows], total
