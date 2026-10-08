"""Catalog reads + relevance retrieval. The AI never receives the whole schema — only the
objects/fields most relevant to the question."""
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.cache.redis import cache_get_json, cache_set_json
from app.core.config import get_settings
from app.core.errors import NotFound
from app.db.models import SalesforceConnection, SalesforceField, SalesforceObject, SalesforceRelationship
from app.domain.catalog_view import CatalogView, FieldInfo, ObjectInfo


def _key(conn: SalesforceConnection, suffix: str) -> str:
    return f"catalog:{conn.id}:{conn.catalog_version or 'none'}:{suffix}"


def load_view(db: Session, conn: SalesforceConnection) -> CatalogView:
    key = _key(conn, "view")
    cached = cache_get_json(key)
    if cached:
        return CatalogView.from_dict(cached)
    view = CatalogView(connection_id=str(conn.id), version=conn.catalog_version or "none")
    objs = list(db.scalars(select(SalesforceObject).where(SalesforceObject.connection_id == conn.id,
                                                          SalesforceObject.is_active.is_(True))))
    by_id = {o.id: o for o in objs}
    for o in objs:
        view.objects[o.object_api_name.lower()] = ObjectInfo(
            name=o.object_api_name, label=o.label, label_plural=o.label_plural, is_custom=o.is_custom,
            queryable=o.is_queryable)
    if by_id:
        for f in db.scalars(select(SalesforceField).where(SalesforceField.object_id.in_(by_id.keys()),
                                                          SalesforceField.is_active.is_(True))):
            view.objects[by_id[f.object_id].object_api_name.lower()].fields[f.field_api_name.lower()] = FieldInfo(
                name=f.field_api_name, label=f.label, type=f.data_type, reference_to=list(f.reference_to or []),
                relationship_name=f.relationship_name, queryable=f.is_queryable, filterable=f.is_filterable,
                groupable=f.is_groupable, sortable=f.is_sortable, aggregatable=f.is_aggregatable,
                picklist_values=(f.metadata_json or {}).get("picklist_values", [])[:25])
        for r in db.scalars(select(SalesforceRelationship).where(
                SalesforceRelationship.object_id.in_(by_id.keys()), SalesforceRelationship.direction == "child",
                SalesforceRelationship.is_active.is_(True))):
            view.objects[by_id[r.object_id].object_api_name.lower()].children.append(
                {"relationship_name": r.relationship_name, "child_object": r.related_object_api_name,
                 "field": r.field_api_name})
    cache_set_json(key, view.to_dict(), get_settings().catalog_cache_ttl_seconds)
    return view


def list_objects(db: Session, conn: SalesforceConnection, q: str | None, limit: int, offset: int,
                 include_inactive: bool = False) -> tuple[list[dict], int]:
    stmt = select(SalesforceObject).where(SalesforceObject.connection_id == conn.id)
    if not include_inactive:
        stmt = stmt.where(SalesforceObject.is_active.is_(True))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(SalesforceObject.object_api_name).like(like),
                              func.lower(SalesforceObject.label).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    field_counts = dict(db.execute(
        select(SalesforceField.object_id, func.count()).join(SalesforceObject)
        .where(SalesforceObject.connection_id == conn.id, SalesforceField.is_active.is_(True))
        .group_by(SalesforceField.object_id)).all())
    rows = db.scalars(stmt.order_by(SalesforceObject.is_custom, SalesforceObject.object_api_name)
                      .limit(limit).offset(offset))
    return [{"api_name": o.object_api_name, "label": o.label, "label_plural": o.label_plural,
             "is_custom": o.is_custom, "is_queryable": o.is_queryable, "is_active": o.is_active,
             "field_count": field_counts.get(o.id, 0), "metadata_version": o.metadata_version} for o in rows], total


def _get_obj(db: Session, conn: SalesforceConnection, name: str) -> SalesforceObject:
    obj = db.scalar(select(SalesforceObject).where(SalesforceObject.connection_id == conn.id,
                                                   func.lower(SalesforceObject.object_api_name) == name.lower()))
    if obj is None:
        raise NotFound(f"Object {name} is not in the catalog")
    return obj


def object_detail(db: Session, conn: SalesforceConnection, name: str) -> dict:
    key = _key(conn, f"obj:{name.lower()}")
    cached = cache_get_json(key)
    if cached:
        return cached
    obj = _get_obj(db, conn, name)
    fields = db.scalars(select(SalesforceField).where(SalesforceField.object_id == obj.id)
                        .order_by(SalesforceField.is_custom, SalesforceField.field_api_name))
    out = {
        "api_name": obj.object_api_name, "label": obj.label, "label_plural": obj.label_plural,
        "is_custom": obj.is_custom, "is_queryable": obj.is_queryable, "is_active": obj.is_active,
        "key_prefix": obj.key_prefix, "metadata_version": obj.metadata_version,
        "fields": [{"api_name": f.field_api_name, "label": f.label, "data_type": f.data_type,
                    "reference_to": f.reference_to, "relationship_name": f.relationship_name,
                    "is_custom": f.is_custom, "is_filterable": f.is_filterable, "is_groupable": f.is_groupable,
                    "is_sortable": f.is_sortable, "is_aggregatable": f.is_aggregatable, "is_active": f.is_active,
                    "picklist_values": (f.metadata_json or {}).get("picklist_values", [])} for f in fields],
        "relationships": relationships(db, conn, name),
    }
    cache_set_json(key, out, get_settings().catalog_cache_ttl_seconds)
    return out


def relationships(db: Session, conn: SalesforceConnection, name: str) -> list[dict]:
    obj = _get_obj(db, conn, name)
    rows = db.scalars(select(SalesforceRelationship).where(SalesforceRelationship.object_id == obj.id,
                                                           SalesforceRelationship.is_active.is_(True))
                      .order_by(SalesforceRelationship.direction, SalesforceRelationship.relationship_name))
    return [{"relationship_name": r.relationship_name, "direction": r.direction,
             "related_object": r.related_object_api_name, "relationship_type": r.relationship_type,
             "field": r.field_api_name, "in_catalog": r.related_object_id is not None,
             "soql_hint": (f"SELECT {r.relationship_name}.Name FROM {obj.object_api_name}" if r.direction == "parent"
                           else f"(SELECT Id FROM {r.relationship_name}) — child subqueries arrive after prototype")}
            for r in rows]


# ---- retrieval ---------------------------------------------------------------------------
_SYNONYMS = {
    "customer": ["account"], "customers": ["account"], "client": ["account"], "company": ["account"],
    "companies": ["account"], "deal": ["opportunity"], "deals": ["opportunity"], "revenue": ["opportunity", "amount"],
    "pipeline": ["opportunity"], "bookings": ["opportunity"], "sales": ["opportunity"], "ticket": ["case"],
    "tickets": ["case"], "support": ["case"], "people": ["contact"], "rep": ["user", "owner"],
    "reps": ["user", "owner"], "owner": ["user"],
}


def _terms(text: str) -> set[str]:
    words = {w for w in re.findall(r"[a-z0-9_]+", text.lower()) if len(w) > 2}
    out = set(words)
    for w in words:
        out.update(_SYNONYMS.get(w, []))
        if w.endswith("ies"):
            out.add(w[:-3] + "y")
        elif w.endswith("s"):
            out.add(w[:-1])
    return out


def search_metadata(view: CatalogView, query: str, limit: int = 20) -> list[dict]:
    terms = _terms(query)
    hits = []
    for o in view.objects.values():
        oname = o.name.lower().replace("__c", "")
        score = sum(3 for t in terms if t == oname or t in o.label.lower().split())
        if score:
            hits.append({"type": "object", "object": o.name, "label": o.label, "score": score})
        for f in o.fields.values():
            fs = sum(1 for t in terms if t in f.name.lower() or t in f.label.lower().split())
            if fs:
                hits.append({"type": "field", "object": o.name, "field": f.name, "label": f.label,
                             "data_type": f.type, "score": fs})
    hits.sort(key=lambda h: (-h["score"], h["object"]))
    return hits[:limit]


def build_ai_context(view: CatalogView, question: str, max_objects: int = 4, max_fields: int = 40) -> dict:
    """Pick the most relevant objects (+ their direct parents) and a bounded field list."""
    scores: dict[str, int] = {}
    for h in search_metadata(view, question, limit=200):
        scores[h["object"]] = scores.get(h["object"], 0) + h["score"]
    ranked = [n for n, _ in sorted(scores.items(), key=lambda kv: -kv[1])][:max_objects]
    if not ranked:
        ranked = [o.name for o in list(view.objects.values())[:max_objects]]
    selected = list(ranked)
    for name in ranked:  # include parent objects so relationship paths are resolvable
        o = view.obj(name)
        for f in o.fields.values():
            for t in f.reference_to:
                if view.obj(t) and view.obj(t).name not in selected and len(selected) < max_objects + 2:
                    selected.append(view.obj(t).name)
    terms = _terms(question)
    ctx_objects = []
    for name in selected:
        o = view.obj(name)
        fields = sorted(o.fields.values(), key=lambda f: (
            -(sum(1 for t in terms if t in f.name.lower() or t in f.label.lower())),
            f.type == "reference" and not f.relationship_name, f.name))[:max_fields]
        ctx_objects.append({
            "name": o.name, "label": o.label, "label_plural": o.label_plural,
            "fields": [{"name": f.name, "label": f.label, "type": f.type, "groupable": f.groupable,
                        "filterable": f.filterable,
                        **({"relationship_name": f.relationship_name, "reference_to": f.reference_to}
                           if f.relationship_name else {}),
                        **({"picklist_values": f.picklist_values[:15]} if f.picklist_values else {})}
                       for f in fields],
        })
    return {"objects": ctx_objects, "selected_objects": selected}
