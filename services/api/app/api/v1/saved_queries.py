from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.deps import get_ctx
from app.db.session import get_db
from app.schemas.api import SavedExecuteIn, SavedQueryIn, SavedQueryUpdate
from app.services import connection_service, query_service, saved_query_service

router = APIRouter(prefix="/saved-queries", tags=["saved-queries"])


@router.post("")
def create(body: SavedQueryIn, ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    conn = connection_service.resolve_connection(db, ctx, body.connection_id)
    sq = saved_query_service.create(db, ctx, conn, name=body.name, description=body.description, soql=body.soql,
                                    execution_id=body.execution_id, parameters_schema=body.parameters_schema,
                                    visibility=body.visibility, question_examples=body.question_examples,
                                    auto_parameterize=body.auto_parameterize)
    return saved_query_service.to_dict(sq)


@router.get("")
def list_saved(connection_id: str | None = None, limit: int = Query(50, le=200), offset: int = Query(0, ge=0),
               ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    conn = connection_service.resolve_connection(db, ctx, connection_id)
    items, total = saved_query_service.list_saved(db, ctx, conn, limit, offset)
    return {"items": [saved_query_service.to_dict(s) for s in items], "total": total, "limit": limit,
            "offset": offset}


@router.get("/{saved_id}")
def get_one(saved_id: str, ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    return saved_query_service.to_dict(saved_query_service.get_saved(db, ctx, saved_id))


@router.patch("/{saved_id}")
def update(saved_id: str, body: SavedQueryUpdate, ctx: RequestContext = Depends(get_ctx),
           db: Session = Depends(get_db)):
    return saved_query_service.to_dict(saved_query_service.update(db, ctx, saved_id, **body.model_dump()))


@router.post("/{saved_id}/execute")
def execute_saved(saved_id: str, body: SavedExecuteIn, ctx: RequestContext = Depends(get_ctx),
                  db: Session = Depends(get_db)):
    sq = saved_query_service.get_saved(db, ctx, saved_id)
    conn = connection_service.resolve_connection(db, ctx, sq.connection_id)
    soql = saved_query_service.render(sq, body.parameters)
    sq.use_count += 1
    out = query_service.execute(db, ctx, conn, soql=soql, saved_query_id=sq.id, question=f"[saved] {sq.name}",
                                source="template")
    return {**out, "saved_query": {"id": str(sq.id), "name": sq.name, "version": sq.version,
                                   "parameters": body.parameters}}
