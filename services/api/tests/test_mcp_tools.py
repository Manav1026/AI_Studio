"""MCP tools go through the same services, validation and audit as the REST API."""
import os

import pytest


@pytest.fixture
def mcp_token(ready):
    client, _ = ready
    return client.post("/api/v1/auth/api-token").json()["token"]


def test_mcp_tools_share_governed_path(ready, mcp_token, monkeypatch):
    client, _ = ready
    monkeypatch.setenv("MCP_AUTH_TOKEN", mcp_token)
    from app.mcp import server

    objs = server.list_objects()
    assert any(o["api_name"] == "Account" for o in objs["items"])
    assert server.describe_object("Case")["api_name"] == "Case"
    assert server.search_metadata("revenue")["items"]
    agg = server.aggregate_records("Case", "COUNT", "Id", group_by="Priority")
    assert agg["status"] == "succeeded" and agg["row_count"] >= 1
    recs = server.get_records("Contact", ["Name", "Account.Name"], limit=3)
    assert recs["row_count"] == 3
    bad = server.execute_soql("SELECT Id FROM Account FOR UPDATE")
    assert bad["error"]["code"] == "validation_failed"
    info = server.get_org_info()
    assert info["read_only"] and "token" not in str(info).lower()

    audit = client.get("/api/v1/audit", params={"action": "mcp."}).json()["items"]
    assert len(audit) >= 6 and {"success", "failure"} <= {a["result"] for a in audit}
    hist = client.get("/api/v1/query/history").json()["items"]
    assert any(h["interface"] == "mcp" for h in hist)
    os.environ.pop("MCP_AUTH_TOKEN", None)


def test_mcp_rejects_missing_token(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    from app.mcp import server
    assert server.list_objects()["error"]["code"] == "unauthorized"
