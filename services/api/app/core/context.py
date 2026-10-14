"""Request-scoped context (correlation id) shared by API, worker, AI gateway and MCP."""
import uuid
from contextvars import ContextVar

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def get_correlation_id() -> str:
    cid = correlation_id_var.get()
    if cid == "-":
        cid = new_correlation_id()
        correlation_id_var.set(cid)
    return cid
