"""Metadata discovery -> normalisation -> catalog upsert. Runs in the background worker."""
import hashlib
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.cache.redis import cache_delete_prefix
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.models import (
    SalesforceConnection,
    SalesforceField,
    SalesforceObject,
    SalesforceRelationship,
    SyncRun,
)
from app.integrations.salesforce.base import SalesforceError
from app.integrations.salesforce.factory import get_connector
from app.services import audit_service

log = get_logger("metadata_sync")


def select_objects(global_list: list[dict]) -> list[dict]:
    s = get_settings()
    wanted = {n.lower() for n in s.sync_object_list}
    chosen = [o for o in global_list if o.get("queryable") and not o.get("deprecatedAndHidden")
              and (o["name"].lower() in wanted or (s.sf_sync_include_custom and o["name"].endswith("__c")))]
    return chosen[: s.sf_sync_max_objects]


def normalize_field(f: dict) -> dict:
    """Canonical field record — the query engine depends on this shape, not Salesforce's."""
    return {
        "field_api_name": f["name"], "label": f.get("label") or f["name"], "data_type": f.get("type", "string"),
        "reference_to": f.get("referenceTo") or [], "relationship_name": f.get("relationshipName"),
        "is_custom": bool(f.get("custom")), "is_queryable": True,
        "is_filterable": bool(f.get("filterable", True)), "is_groupable": bool(f.get("groupable", False)),
        "is_sortable": bool(f.get("sortable", True)), "is_aggregatable": bool(f.get("aggregatable", False)),
        "metadata_json": {
            "nillable": f.get("nillable"), "length": f.get("length"),
            "picklist_values": [p["value"] for p in (f.get("picklistValues") or []) if p.get("active", True)][:100],
            "master_detail": f.get("relationshipOrder") is not None or bool(f.get("cascadeDelete")),
        },
    }


def queue_sync(db: Session, conn: SalesforceConnection, user_id=None) -> SyncRun:
    run = SyncRun(tenant_id=conn.tenant_id, connection_id=conn.id, status="queued")
    db.add(run)
    db.flush()
    audit_service.record(db, "metadata.sync.queued", tenant_id=conn.tenant_id, user_id=user_id,
                         resource_type="sync_run", resource_id=run.id)
    db.commit()
    s = get_settings()
    if s.sync_mode == "inline":
        run_sync(db, run.id)
    else:
        from rq import Queue

        from app.workers.queue import get_queue_connection
        Queue(s.rq_queue_name, connection=get_queue_connection()).enqueue(
            "app.workers.jobs.metadata_sync_job", str(run.id), job_timeout=1800)
    return run


def run_sync(db: Session, sync_run_id) -> SyncRun:
    run = db.get(SyncRun, uuid.UUID(str(sync_run_id)))
    conn = db.get(SalesforceConnection, run.connection_id)
    run.status, run.started_at = "running", utcnow()
    db.commit()
    errors: list[str] = []
    try:
        connector = get_connector(db, conn)
        chosen = select_objects(connector.describe_global())
        chosen_names = {o["name"].lower() for o in chosen}
        existing = {o.object_api_name.lower(): o for o in db.scalars(
            select(SalesforceObject).where(SalesforceObject.connection_id == conn.id))}
        signature = hashlib.sha256()
        seen_objects: set[str] = set()
        describes: dict[str, dict] = {}
        for entry in chosen:
            try:
                d = connector.describe_object(entry["name"])
            except SalesforceError as exc:
                errors.append(f"{entry['name']}: {exc}")
                continue
            describes[d["name"]] = d
            obj = existing.get(d["name"].lower())
            if obj is None:
                obj = SalesforceObject(tenant_id=conn.tenant_id, connection_id=conn.id, object_api_name=d["name"],
                                       label=d.get("label") or d["name"])
                db.add(obj)
                db.flush()
                existing[d["name"].lower()] = obj
            obj.label, obj.label_plural = d.get("label") or d["name"], d.get("labelPlural")
            obj.key_prefix, obj.is_custom = d.get("keyPrefix"), bool(d.get("custom"))
            obj.is_queryable, obj.is_active = bool(d.get("queryable", True)), True
            obj.metadata_json = {"child_relationship_count": len(d.get("childRelationships") or [])}
            seen_objects.add(d["name"].lower())

            fields = {f.field_api_name.lower(): f for f in db.scalars(
                select(SalesforceField).where(SalesforceField.object_id == obj.id))}
            seen_fields = set()
            for raw in d.get("fields", []):
                nf = normalize_field(raw)
                signature.update(f"{d['name']}.{nf['field_api_name']}:{nf['data_type']}".encode())
                row = fields.get(nf["field_api_name"].lower())
                if row is None:
                    row = SalesforceField(tenant_id=conn.tenant_id, object_id=obj.id, **nf)
                    db.add(row)
                else:
                    for k, v in nf.items():
                        setattr(row, k, v)
                row.is_active = True
                seen_fields.add(nf["field_api_name"].lower())
                run.fields_seen += 1
            for key, row in fields.items():  # mark removed metadata, keep history
                if key not in seen_fields:
                    row.is_active = False
            run.objects_seen += 1
        db.flush()

        # relationships (need all objects first so related_object_id can resolve)
        for name, d in describes.items():
            obj = existing[name.lower()]
            rels = {(r.relationship_name.lower(), r.direction): r for r in db.scalars(
                select(SalesforceRelationship).where(SalesforceRelationship.object_id == obj.id))}
            seen_rels = set()
            items = []
            for f in d.get("fields", []):
                if f.get("type") == "reference" and f.get("relationshipName"):
                    target = next((t for t in f.get("referenceTo") or [] if t.lower() in chosen_names),
                                  (f.get("referenceTo") or ["?"])[0])
                    md = f.get("relationshipOrder") is not None or bool(f.get("cascadeDelete"))
                    items.append(("parent", f["relationshipName"], target, f["name"],
                                  "master_detail" if md else "lookup", {"polymorphic": len(f.get("referenceTo") or []) > 1}))
            for c in d.get("childRelationships") or []:
                if c.get("relationshipName") and c["childSObject"].lower() in chosen_names:
                    items.append(("child", c["relationshipName"], c["childSObject"], c.get("field"),
                                  "master_detail" if c.get("cascadeDelete") else "lookup", {}))
            for direction, rel_name, target, field_name, rtype, meta in items:
                key = (rel_name.lower(), direction)
                if key in seen_rels:
                    continue
                seen_rels.add(key)
                related = existing.get(target.lower())
                row = rels.get(key)
                if row is None:
                    row = SalesforceRelationship(tenant_id=conn.tenant_id, object_id=obj.id,
                                                 relationship_name=rel_name, direction=direction,
                                                 related_object_api_name=target, relationship_type=rtype)
                    db.add(row)
                row.related_object_api_name, row.related_object_id = target, related.id if related else None
                row.field_api_name, row.relationship_type, row.is_active = field_name, rtype, True
                row.metadata_json = meta
                run.relationships_seen += 1
            for key, row in rels.items():
                if key not in seen_rels:
                    row.is_active = False

        for key, obj in existing.items():
            if key not in seen_objects:
                obj.is_active = False
        version = signature.hexdigest()[:16]
        db.execute(update(SalesforceObject).where(SalesforceObject.connection_id == conn.id,
                                                  SalesforceObject.is_active.is_(True))
                   .values(metadata_version=version))
        conn.catalog_version, conn.last_sync_at = version, utcnow()
        run.status = "succeeded" if not errors else "partial"
    except Exception as exc:  # noqa: BLE001
        log.exception("metadata_sync_failed")
        db.rollback()
        run = db.get(SyncRun, run.id)
        run.status = "failed"
        errors.append(str(exc)[:500])
    run.error_count = len(errors)
    run.error_detail = "\n".join(errors)[:4000] or None
    run.completed_at = utcnow()
    audit_service.record(db, "metadata.sync.completed", tenant_id=run.tenant_id, resource_type="sync_run",
                         resource_id=run.id, result="success" if run.status in ("succeeded", "partial") else "failure",
                         metadata={"objects": run.objects_seen, "fields": run.fields_seen,
                                   "errors": run.error_count,
                                   "duration_ms": int((run.completed_at - run.started_at).total_seconds() * 1000)})
    db.commit()
    cache_delete_prefix(f"catalog:{run.connection_id}:")
    log.info("metadata_sync_done", status=run.status, objects=run.objects_seen, fields=run.fields_seen)
    return run
