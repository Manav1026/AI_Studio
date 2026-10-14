from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.deps import get_ctx
from app.db.session import get_db
from app.services import catalog_service, connection_service

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/objects")
def list_objects(q: str | None = None, connection_id: str | None = None, limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0), include_inactive: bool = False,
                 ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    conn = connection_service.resolve_connection(db, ctx, connection_id)
    items, total = catalog_service.list_objects(db, conn, q, limit, offset, include_inactive)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/search")
def search(q: str = Query(min_length=2), connection_id: str | None = None, limit: int = Query(20, le=100),
           ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    conn = connection_service.resolve_connection(db, ctx, connection_id)
    return {"items": catalog_service.search_metadata(catalog_service.load_view(db, conn), q, limit)}


@router.get("/objects/{object_name}")
def object_detail(object_name: str, connection_id: str | None = None, ctx: RequestContext = Depends(get_ctx),
                  db: Session = Depends(get_db)):
    conn = connection_service.resolve_connection(db, ctx, connection_id)
    return catalog_service.object_detail(db, conn, object_name)


@router.get("/objects/{object_name}/relationships")
def object_relationships(object_name: str, connection_id: str | None = None,
                         ctx: RequestContext = Depends(get_ctx), db: Session = Depends(get_db)):
    conn = connection_service.resolve_connection(db, ctx, connection_id)
    return {"object": object_name, "items": catalog_service.relationships(db, conn, object_name)}
