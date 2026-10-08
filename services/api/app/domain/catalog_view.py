"""Immutable in-memory view of a connection's metadata catalog, used by the planner and validator.
Built from PostgreSQL and cached in Redis keyed by catalog_version."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

NUMERIC_TYPES = {"int", "double", "currency", "percent", "long"}
DATE_TYPES = {"date"}
DATETIME_TYPES = {"datetime"}
TEXT_TYPES = {"string", "textarea", "picklist", "multipicklist", "email", "phone", "url", "combobox",
              "id", "reference", "encryptedstring"}


@dataclass
class FieldInfo:
    name: str
    label: str
    type: str
    reference_to: list[str] = field(default_factory=list)
    relationship_name: str | None = None
    queryable: bool = True
    filterable: bool = True
    groupable: bool = False
    sortable: bool = True
    aggregatable: bool = False
    picklist_values: list[str] = field(default_factory=list)


@dataclass
class ObjectInfo:
    name: str
    label: str
    label_plural: str | None = None
    is_custom: bool = False
    queryable: bool = True
    fields: dict[str, FieldInfo] = field(default_factory=dict)
    children: list[dict] = field(default_factory=list)  

    def field(self, name: str) -> FieldInfo | None:
        return self.fields.get(name.lower())

    def parent_rel(self, rel_name: str) -> FieldInfo | None:
        rl = rel_name.lower()
        for f in self.fields.values():
            if f.relationship_name and f.relationship_name.lower() == rl:
                return f
        return None


@dataclass
class CatalogView:
    connection_id: str
    version: str
    objects: dict[str, ObjectInfo] = field(default_factory=dict) 

    def obj(self, name: str) -> ObjectInfo | None:
        return self.objects.get(name.lower())

    def resolve_path(self, root: str, path: tuple[str, ...]) -> tuple[FieldInfo | None, list[str], str | None]:
        """Resolve e.g. ('Account','Owner','Name') from Opportunity.
        Returns (field, traversed_objects, error)."""
        current = self.obj(root)
        if current is None:
            return None, [], f"Unknown object {root}"
        traversed = [current.name]
        for i, part in enumerate(path):
            last = i == len(path) - 1
            if last:
                f = current.field(part)
                if f is None:
                    return None, traversed, f"Field {part} does not exist on {current.name}"
                return f, traversed, None
            ref = current.parent_rel(part)
            if ref is None:
                return None, traversed, f"{part} is not a parent relationship on {current.name}"
            target = next((self.obj(t) for t in ref.reference_to if self.obj(t)), None)
            if target is None:
                return None, traversed, (f"Relationship {current.name}.{part} points to "
                                         f"{'/'.join(ref.reference_to)} which is not in the catalog")
            current = target
            traversed.append(current.name)
        return None, traversed, "Empty field path"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> CatalogView:
        objs = {}
        for k, o in d["objects"].items():
            fields = {fk: FieldInfo(**fv) for fk, fv in o.pop("fields").items()}
            objs[k] = ObjectInfo(**o, fields=fields)
        return cls(connection_id=d["connection_id"], version=d["version"], objects=objs)
