"""Application policy: allow/deny rules evaluated before execution (separate from SOQL generation)."""
from dataclasses import dataclass, field


@dataclass
class QueryPolicy:
    read_only: bool = True
    blocked_objects: set[str] = field(default_factory=set)
    blocked_fields: set[str] = field(default_factory=set)  
    default_limit: int = 50
    max_limit: int = 200
    max_fields: int = 50
    max_conditions: int = 20
    max_relationship_depth: int = 3

    def object_allowed(self, obj: str) -> bool:
        return obj.lower() not in self.blocked_objects

    def field_allowed(self, obj: str, fld: str) -> bool:
        o, f = obj.lower(), fld.lower()
        return f"{o}.{f}" not in self.blocked_fields and f"*.{f}" not in self.blocked_fields

    @classmethod
    def from_settings(cls, s) -> "QueryPolicy":
        return cls(blocked_objects=s.blocked_objects, blocked_fields=s.blocked_fields,
                   default_limit=s.query_default_limit, max_limit=s.query_max_limit,
                   max_fields=s.query_max_fields, max_conditions=s.query_max_conditions,
                   max_relationship_depth=s.query_max_relationship_depth)
