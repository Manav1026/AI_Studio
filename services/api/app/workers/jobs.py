from app.core.context import correlation_id_var, new_correlation_id
from app.core.logging import get_logger
from app.db.session import session_scope
from app.services.metadata_service import run_sync

log = get_logger("worker")


def metadata_sync_job(sync_run_id: str) -> dict:
    correlation_id_var.set(new_correlation_id())
    with session_scope() as db:
        run = run_sync(db, sync_run_id)
        return {"status": run.status, "objects": run.objects_seen, "fields": run.fields_seen}
