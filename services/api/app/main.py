from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, auth, catalog, health, query, salesforce, saved_queries
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware
from app.core.telemetry import setup_telemetry


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    app = FastAPI(title="Salesforce AI Workspace API", version="0.1.0",
                  openapi_url="/api/v1/openapi.json", docs_url="/api/docs")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Correlation-ID"])
    app.add_middleware(CorrelationIdMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    for r in (auth.router, salesforce.router, catalog.router, query.router, saved_queries.router, admin.router):
        app.include_router(r, prefix="/api/v1")
    setup_telemetry(app)
    return app


app = create_app()
