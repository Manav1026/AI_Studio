import uuid
from dataclasses import dataclass

from app.core.errors import Forbidden


@dataclass(frozen=True)
class RequestContext:
    """Server-derived identity. tenant_id is NEVER taken from client input without a membership check."""
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    email: str
    interface: str = "web" 

    def require_role(self, *roles: str) -> None:
        if self.role not in roles:
            raise Forbidden(f"Requires role: {', '.join(roles)}")
