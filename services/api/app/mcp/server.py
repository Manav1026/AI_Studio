"""MCP protocol adapter (official MCP Python SDK v2).

Rule: every tool calls the SAME application services as the REST API — same tenant scoping,
same validator, same policy, same Salesforce authorization, same audit trail. MCP gets no
privileged path.

Run (Streamable HTTP):  python -m app.mcp.server            -> http://localhost:8001/mcp
Run (stdio):            MCP_AUTH_TOKEN=<token> python -m app.mcp.server --stdio
Clients authenticate with a bearer token from POST /api/v1/auth/api-token."""
import os
import sys
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer

from app.auth.context import RequestContext
from app.auth.provider import context_from_token
from app.core.config import get_settings
from app.core.context import correlation_id_var, new_correlation_id
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.domain.query_plan import PlanAggregation, PlanFilter, QueryPlan, plan_to_soql
from app.integrations.salesforce.factory import get_connector
from app.services import (
    audit_service,
    catalog_service,
    connection_service,
    query_service,
    saved_query_service,
)

log = get_logger("mcp")
settings = get_settings()


class AppTokenVerifier:
    """Validates the application's own signed tokens and confirms tenant membership."""

    async def verify_token(self, token: str) -> AccessToken | None:
        db = SessionLocal()
        try:
            ctx = context_from_token(db, token, interface="mcp")
        except AppError:
            return None
        finally:
            db.close()
        return AccessToken(token=token, client_id="sfai-mcp", scopes=["sfai.read"], subject=str(ctx.user_id),
                           claims={"tid": str(ctx.tenant_id)}, resource=settings.mcp_public_url)


_stdio = "--stdio" in sys.argv
mcp = MCPServer(
    name="salesforce-ai-workspace",
    instructions=("Governed, read-only access to a connected Salesforce org. Discover metadata first "
                  "(list_objects, describe_object, search_metadata), then query with execute_soql, get_records "
                  "or aggregate_records. All queries are validated and run with the user's Salesforce permissions."),
    **({} if _stdio else {
        "token_verifier": AppTokenVerifier(),
        "auth": AuthSettings(issuer_url=settings.api_base_url, resource_server_url=settings.mcp_public_url,
                             required_scopes=["sfai.read"], validate_token_resource=False),
    }),
)


def _ctx(db) -> RequestContext:
    tok = get_access_token()
    raw = tok.token if tok else os.environ.get("MCP_AUTH_TOKEN")
    if not raw:
        raise AppError("Missing MCP credentials", code="unauthorized", status_code=401)
    return context_from_token(db, raw, interface="mcp")


def _run(tool: str, fn, **args) -> Any:
    correlation_id_var.set(new_correlation_id())
    db = SessionLocal()
    ctx = None
    try:
        ctx = _ctx(db)
        out = fn(db, ctx)
        audit_service.record(db, "mcp.tool_call", ctx=ctx, resource_type="mcp_tool", resource_id=tool,
                             metadata={"args": {k: v for k, v in args.items() if k != "soql"}})
        db.commit()
        return out
    except AppError as exc:
        db.rollback()
        if ctx:
            audit_service.record(db, "mcp.tool_call", ctx=ctx, resource_type="mcp_tool", resource_id=tool,
                                 result="failure", metadata={"error": exc.code})
            db.commit()
        return {"error": {"code": exc.code, "message": exc.message, "details": exc.details}}
    finally:
        db.close()


@mcp.tool(description="List cataloged Salesforce objects (tenant/org scoped). Optional text filter.")
def list_objects(query: str | None = None, limit: int = 50) -> dict:
    def fn(db, ctx):
        conn = connection_service.resolve_connection(db, ctx)
        items, total = catalog_service.list_objects(db, conn, query, min(limit, 200), 0)
        return {"items": items, "total": total}
    return _run("list_objects", fn, query=query, limit=limit)


@mcp.tool(description="Describe one object: fields (type, filterable, groupable) and relationships.")
def describe_object(object_name: str) -> dict:
    return _run("describe_object", lambda db, ctx: catalog_service.object_detail(
        db, connection_service.resolve_connection(db, ctx), object_name), object_name=object_name)


@mcp.tool(description="Search the metadata catalog for objects/fields matching business terms.")
def search_metadata(query: str, limit: int = 20) -> dict:
    def fn(db, ctx):
        conn = connection_service.resolve_connection(db, ctx)
        return {"items": catalog_service.search_metadata(catalog_service.load_view(db, conn), query, min(limit, 100))}
    return _run("search_metadata", fn, query=query)


@mcp.tool(description="Return known parent/child relationship paths for an object.")
def get_relationships(object_name: str) -> dict:
    return _run("get_relationships", lambda db, ctx: {"items": catalog_service.relationships(
        db, connection_service.resolve_connection(db, ctx), object_name)}, object_name=object_name)


@mcp.tool(description="Validate and execute a READ-ONLY SOQL query. Rejected queries are never sent to Salesforce.")
def execute_soql(soql: str) -> dict:
    return _run("execute_soql", lambda db, ctx: query_service.execute(
        db, ctx, connection_service.resolve_connection(db, ctx), soql=soql, source="manual"), soql=soql)


@mcp.tool(description="Retrieve records: object, fields (paths like Account.Name), optional filters "
                      "[{field, operator, value}], order_by field, descending, limit.")
def get_records(object_name: str, fields: list[str], filters: list[dict] | None = None,
                order_by: str | None = None, descending: bool = False, limit: int = 25) -> dict:
    def fn(db, ctx):
        conn = connection_service.resolve_connection(db, ctx)
        view = catalog_service.load_view(db, conn)
        plan = QueryPlan(intent="mcp:get_records", root_object=object_name, fields=fields,
                         filters=[PlanFilter(**f) for f in (filters or [])],
                         order_by=[{"field": order_by, "direction": "DESC" if descending else "ASC"}] if order_by else [],
                         limit=min(limit, settings.query_max_limit))
        return query_service.execute(db, ctx, conn, soql=plan_to_soql(plan, view), source="manual")
    return _run("get_records", fn, object_name=object_name, fields=fields)


@mcp.tool(description="Supported aggregation (COUNT|SUM|AVG|MIN|MAX) on an object, optionally grouped by one field.")
def aggregate_records(object_name: str, function: str, field: str | None = None, group_by: str | None = None,
                      filters: list[dict] | None = None, limit: int = 50) -> dict:
    def fn(db, ctx):
        if function.upper() not in {"COUNT", "SUM", "AVG", "MIN", "MAX"}:  # allow-listed patterns only
            raise AppError("Unsupported aggregate function", code="unsupported_aggregate")
        conn = connection_service.resolve_connection(db, ctx)
        view = catalog_service.load_view(db, conn)
        plan = QueryPlan(intent="mcp:aggregate", root_object=object_name,
                         aggregations=[PlanAggregation(function=function, field=field, alias="value")],
                         group_by=[group_by] if group_by else [], filters=[PlanFilter(**f) for f in (filters or [])],
                         order_by=[{"field": "value", "direction": "DESC"}] if group_by else [],
                         limit=min(limit, settings.query_max_limit) if group_by else None)
        return query_service.execute(db, ctx, conn, soql=plan_to_soql(plan, view), source="manual")
    return _run("aggregate_records", fn, object_name=object_name, function=function, field=field, group_by=group_by)


@mcp.tool(description="List saved queries visible to you, or run one by id with optional parameters.")
def saved_query(saved_query_id: str | None = None, parameters: dict | None = None) -> dict:
    def fn(db, ctx):
        conn = connection_service.resolve_connection(db, ctx)
        if not saved_query_id:
            items, total = saved_query_service.list_saved(db, ctx, conn, 50, 0)
            return {"items": [saved_query_service.to_dict(s) for s in items], "total": total}
        sq = saved_query_service.get_saved(db, ctx, saved_query_id)
        sq.use_count += 1
        return query_service.execute(db, ctx, conn, soql=saved_query_service.render(sq, parameters or {}),
                                     saved_query_id=sq.id, question=f"[saved] {sq.name}", source="template")
    return _run("saved_query", fn, saved_query_id=saved_query_id)


@mcp.tool(description="Non-secret org and capability information for the active connection.")
def get_org_info() -> dict:
    def fn(db, ctx):
        conn = connection_service.resolve_connection(db, ctx)
        limits = get_connector(db, conn).get_limits()
        return {"org_id": conn.org_id, "org_name": conn.org_name, "instance_url": conn.instance_url,
                "mode": conn.mode, "api_version": conn.api_version, "catalog_version": conn.catalog_version,
                "last_sync_at": conn.last_sync_at.isoformat() if conn.last_sync_at else None,
                "daily_api_requests": limits.get("DailyApiRequests"), "read_only": True}
    return _run("get_org_info", fn)


def main() -> None:
    configure_logging(settings.log_level, settings.log_json, stream=sys.stderr if _stdio else None)
    if _stdio:
        mcp.run("stdio")
    else:
        import anyio
        anyio.run(lambda: mcp.run_streamable_http_async(host=settings.mcp_host, port=settings.mcp_port))


if __name__ == "__main__":
    main()
