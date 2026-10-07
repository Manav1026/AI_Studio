from typing import Any

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.core.context import get_correlation_id
from app.core.logging import get_logger
from app.db.models import AuditEvent

log = get_logger("audit")


def record(db: Session, action: str, *, ctx: RequestContext | None = None, tenant_id=None, user_id=None,
           resource_type: str | None = None, resource_id: Any = None, result: str = "success",
           metadata: dict | None = None) -> AuditEvent:
    ev = AuditEvent(
        tenant_id=ctx.tenant_id if ctx else tenant_id,
        user_id=ctx.user_id if ctx else user_id,
        action=action, resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        result=result, correlation_id=get_correlation_id(),
        metadata_json={**(metadata or {}), **({"interface": ctx.interface} if ctx else {})},
    )
    db.add(ev)
    db.flush()
    log.info("audit_event", action=action, result=result, resource_type=resource_type,
             resource_id=ev.resource_id)
    return ev
