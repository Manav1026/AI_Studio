"""Governed, versioned, parameterised query templates (token-optimisation path)."""
import re
import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.core.errors import AppError, Forbidden, NotFound
from app.db.models import QueryExecution, SalesforceConnection, SavedQuery
from app.domain.soql.ast import Literal
from app.domain.soql.parser import DATE_LITERALS, SoqlParseError, parse_soql
from app.services import audit_service

_PARAM = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_TIME_PHRASES = [
    (r"\bthis year\b|\bytd\b", "THIS_YEAR"), (r"\blast year\b", "LAST_YEAR"), (r"\bthis quarter\b", "THIS_QUARTER"),
    (r"\blast quarter\b", "LAST_QUARTER"), (r"\bthis month\b", "THIS_MONTH"), (r"\blast month\b", "LAST_MONTH"),
    (r"\bnext month\b", "NEXT_MONTH"), (r"\bthis week\b", "THIS_WEEK"), (r"\btoday\b", "TODAY"),
]
_STOP = {"the", "me", "show", "what", "are", "is", "of", "by", "for", "in", "a", "an", "and", "to", "list", "give",
         "get", "my", "all", "with", "from", "which", "who", "top", "this", "last", "next", "year", "month",
         "quarter", "week"}


def _visible(ctx: RequestContext):
    return or_(SavedQuery.owner_id == ctx.user_id, SavedQuery.visibility == "tenant")


def get_saved(db: Session, ctx: RequestContext, saved_id) -> SavedQuery:
    try:
        sq = db.get(SavedQuery, uuid.UUID(str(saved_id)))
    except ValueError:
        sq = None
    if sq is None or sq.tenant_id != ctx.tenant_id or (sq.owner_id != ctx.user_id and sq.visibility != "tenant"):
        raise NotFound("Saved query not found")
    return sq


def parameterize(soql: str) -> tuple[str, dict]:
    """Turn a concrete SOQL statement into a template: LIMIT n -> {{limit}}, date literal -> {{period}}."""
    schema: dict = {}
    m = re.search(r"\bLIMIT\s+(\d+)\b", soql, re.I)
    if m:
        schema["limit"] = {"type": "integer", "default": int(m.group(1)), "minimum": 1, "maximum": 200}
        soql = soql[:m.start()] + "LIMIT {{limit}}" + soql[m.end():]
    for lit in sorted(DATE_LITERALS, key=len, reverse=True):
        pat = re.compile(r"([=<>]\s*)" + lit + r"\b")
        if pat.search(soql) and "period" not in schema:
            schema["period"] = {"type": "date_literal", "default": lit,
                                "enum": ["TODAY", "THIS_WEEK", "THIS_MONTH", "LAST_MONTH", "THIS_QUARTER",
                                         "LAST_QUARTER", "THIS_YEAR", "LAST_YEAR"]}
            soql = pat.sub(r"\1{{period}}", soql, count=1)
    return soql, schema


def render(sq: SavedQuery, params: dict | None) -> str:
    """Typed parameter injection — values become SOQL literals, never raw text."""
    params = params or {}
    schema = sq.parameters_schema or {}
    unknown = set(params) - set(schema)
    if unknown:
        raise AppError(f"Unknown parameters: {', '.join(sorted(unknown))}", code="invalid_parameters")

    def lit(name: str) -> str:
        spec = schema.get(name)
        if spec is None:
            raise AppError(f"Template references undefined parameter {name}", code="invalid_template")
        value = params.get(name, spec.get("default"))
        if value is None:
            raise AppError(f"Missing parameter {name}", code="invalid_parameters")
        t = spec.get("type", "string")
        if "enum" in spec and value not in spec["enum"]:
            raise AppError(f"{name} must be one of {spec['enum']}", code="invalid_parameters")
        if t == "integer":
            try:
                v = int(value)
            except (TypeError, ValueError) as exc:
                raise AppError(f"{name} must be an integer", code="invalid_parameters") from exc
            if v < spec.get("minimum", -10**12) or v > spec.get("maximum", 10**12):
                raise AppError(f"{name} out of range", code="invalid_parameters")
            return str(v)
        if t == "number":
            return str(float(value))
        if t == "boolean":
            return "true" if value in (True, "true", "True", 1) else "false"
        if t == "date_literal":
            if str(value).upper() not in DATE_LITERALS:
                raise AppError(f"{name} must be a SOQL date literal", code="invalid_parameters")
            return str(value).upper()
        if t == "date":
            date.fromisoformat(str(value))
            return str(value)
        return Literal("string", str(value)).to_soql()

    return _PARAM.sub(lambda m: lit(m.group(1)), sq.template)


def create(db: Session, ctx: RequestContext, conn: SalesforceConnection, *, name: str, description: str | None,
           soql: str | None, execution_id: str | None, parameters_schema: dict | None, visibility: str,
           question_examples: list[str] | None, auto_parameterize: bool = True) -> SavedQuery:
    plan_json, question = None, None
    if execution_id:
        ex = db.get(QueryExecution, uuid.UUID(str(execution_id)))
        if ex is None or ex.tenant_id != ctx.tenant_id:
            raise NotFound("Execution not found")
        if ex.status not in ("validated", "succeeded"):
            raise AppError("Only validated queries can be saved", code="not_validated")
        soql, plan_json, question = ex.generated_soql, ex.plan_json, ex.question
    if not soql:
        raise AppError("Provide soql or execution_id", code="bad_request")
    template, schema = (parameterize(soql) if auto_parameterize and not parameters_schema
                        else (soql, parameters_schema or {}))
    sq = SavedQuery(tenant_id=ctx.tenant_id, connection_id=conn.id, owner_id=ctx.user_id, name=name,
                    description=description, template=template, parameters_schema=schema, plan_json=plan_json,
                    visibility=visibility,
                    question_examples=list(dict.fromkeys([*(question_examples or []), *([question] if question else [])])))
    try:  # template must render + parse with defaults before it is accepted
        parse_soql(render(sq, {}))
    except SoqlParseError as exc:
        raise AppError(f"Template is not valid SOQL: {exc}", code="invalid_template") from exc
    db.add(sq)
    db.flush()
    audit_service.record(db, "saved_query.create", ctx=ctx, resource_type="saved_query", resource_id=sq.id,
                         metadata={"visibility": visibility})
    db.commit()
    return sq


def update(db: Session, ctx: RequestContext, saved_id, **changes) -> SavedQuery:
    sq = get_saved(db, ctx, saved_id)
    if sq.owner_id != ctx.user_id and ctx.role not in ("owner", "admin"):
        raise Forbidden("Only the owner or an admin can modify this saved query")
    for k, v in changes.items():
        if v is not None:
            setattr(sq, k, v)
    if changes.get("template") or changes.get("parameters_schema"):
        sq.version += 1
        parse_soql(render(sq, {}))
    audit_service.record(db, "saved_query.update", ctx=ctx, resource_type="saved_query", resource_id=sq.id,
                         metadata={"version": sq.version})
    db.commit()
    return sq


def list_saved(db: Session, ctx: RequestContext, conn: SalesforceConnection, limit: int, offset: int):
    from sqlalchemy import func
    stmt = select(SavedQuery).where(SavedQuery.tenant_id == ctx.tenant_id, SavedQuery.connection_id == conn.id,
                                    _visible(ctx))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return list(db.scalars(stmt.order_by(SavedQuery.updated_at.desc()).limit(limit).offset(offset))), total


def _terms(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 2}


def extract_params(sq: SavedQuery, question: str) -> dict:
    params = {}
    schema = sq.parameters_schema or {}
    ql = question.lower()
    for name, spec in schema.items():
        if spec.get("type") == "date_literal":
            for pat, lit in _TIME_PHRASES:
                if re.search(pat, ql) and lit in spec.get("enum", [lit]):
                    params[name] = lit
                    break
        elif spec.get("type") == "integer" and name == "limit":
            m = re.search(r"\b(?:top|first)\s+(\d+)\b", ql)
            if m:
                params[name] = int(m.group(1))
    return params


def match_template(db: Session, ctx: RequestContext, conn: SalesforceConnection, question: str,
                   threshold: float):
    q_terms = _terms(question)
    if not q_terms:
        return None
    best = None
    for sq in db.scalars(select(SavedQuery).where(SavedQuery.tenant_id == ctx.tenant_id,
                                                  SavedQuery.connection_id == conn.id, _visible(ctx))):
        for text in [sq.name, *(sq.question_examples or [])]:
            t = _terms(text)
            if not t:
                continue
            score = len(q_terms & t) / len(q_terms | t)
            if best is None or score > best[1]:
                best = (sq, score)
    if best and best[1] >= threshold:
        sq = best[0]
        sq.use_count += 1
        return sq, extract_params(sq, question), best[1]
    return None


def to_dict(sq: SavedQuery) -> dict:
    return {"id": str(sq.id), "name": sq.name, "description": sq.description, "template": sq.template,
            "parameters_schema": sq.parameters_schema, "question_examples": sq.question_examples,
            "version": sq.version, "visibility": sq.visibility, "owner_id": str(sq.owner_id),
            "use_count": sq.use_count, "connection_id": str(sq.connection_id),
            "created_at": sq.created_at.isoformat(), "updated_at": sq.updated_at.isoformat()}
