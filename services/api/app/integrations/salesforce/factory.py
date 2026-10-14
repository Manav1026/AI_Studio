from datetime import date

from sqlalchemy.orm import Session

from app.cache.redis import get_redis
from app.core.config import get_settings
from app.db.models import SalesforceConnection
from app.integrations.salesforce.base import SalesforceConnector
from app.integrations.salesforce.mock import MockSalesforceConnector
from app.integrations.salesforce.rest import RestSalesforceConnector
from app.services.secret_store import get_secret_store

_mock_singleton: MockSalesforceConnector | None = None


def _count_api_call(connection_id: str):
    def _inc(_url: str) -> None:
        key = f"sfapi:{connection_id}:{date.today().isoformat()}"
        r = get_redis()
        r.incr(key)
        r.expire(key, 3 * 86400)
    return _inc


def get_connector(db: Session, conn: SalesforceConnection) -> SalesforceConnector:
    global _mock_singleton
    if conn.mode == "mock":
        if _mock_singleton is None or _mock_singleton.today != date.today():
            _mock_singleton = MockSalesforceConnector()
        _count_api_call(str(conn.id))("mock")
        return _mock_singleton
    store = get_secret_store(db)
    tokens = store.get(conn.tenant_id, conn.auth_ref)

    def persist(new_tokens) -> None:
        store.update(conn.tenant_id, conn.auth_ref, {**tokens, **new_tokens.to_secret()})
        db.commit()

    return RestSalesforceConnector(tokens, conn.api_version, timeout=get_settings().sf_query_timeout_seconds,
                                   on_token_refresh=persist, on_api_call=_count_api_call(str(conn.id)))
