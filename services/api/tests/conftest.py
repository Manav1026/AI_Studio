import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://admin:admin123@localhost:5432/admin")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ["SYNC_MODE"] = "inline"
os.environ["SALESFORCE_MODE"] = "mock"
os.environ["AI_PROVIDER"] = "mock"
os.environ["LOG_JSON"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["APP_SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.cache.redis import get_redis  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

HERE = os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(scope="session", autouse=True)
def _schema():
    with get_engine().begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(os.path.join(HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "migrations"))
    command.upgrade(cfg, "head")  # tests run against the real migrations
    yield


@pytest.fixture(autouse=True)
def _clean():
    get_redis().flushdb()
    with get_engine().begin() as c:
        c.execute(text("TRUNCATE tenants, users CASCADE"))
    yield


@pytest.fixture
def client():
    from app.main import create_app
    return TestClient(create_app(), base_url="http://localhost:8000")


def login(client, email="owner@acme.example.com"):
    r = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    return r.json()


def connect_mock_org(client):
    r = client.post("/api/v1/salesforce/connections")
    assert r.status_code == 200, r.text
    url = r.json()["authorization_url"]
    path = url.split("localhost:8000")[1]
    cb = client.get(path, follow_redirects=False)
    assert cb.status_code == 302, cb.text
    assert "connected=" in cb.headers["location"], cb.headers["location"]
    conns = client.get("/api/v1/salesforce/connections").json()
    return conns[0]


@pytest.fixture
def ready(client):
    """Signed-in owner with a connected + synchronised mock org."""
    login(client)
    conn = connect_mock_org(client)
    return client, conn
