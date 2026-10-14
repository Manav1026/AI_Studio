"""Acceptance criteria (Section 16) exercised through the public API against PostgreSQL + Redis."""
from tests.conftest import connect_mock_org, login


def test_health(client):
    assert client.get("/readyz").json() == {"status": "ok", "postgres": True, "redis": True}


def test_requires_auth_and_error_contract(client):
    r = client.get("/api/v1/me")
    assert r.status_code == 401
    body = r.json()["error"]
    assert body["code"] == "unauthorized" and body["correlation_id"]
    assert r.headers["X-Correlation-ID"] == body["correlation_id"]


def test_connect_sync_catalog(ready):
    client, conn = ready
    assert conn["status"] == "active" and conn["catalog_version"]
    assert conn["latest_sync"]["status"] == "succeeded"
    objs = client.get("/api/v1/catalog/objects").json()
    names = {o["api_name"] for o in objs["items"]}
    assert {"Account", "Opportunity", "Contact", "Case", "Project__c"} <= names  # standard + custom
    detail = client.get("/api/v1/catalog/objects/Opportunity").json()
    assert any(f["api_name"] == "Amount" for f in detail["fields"])
    rels = client.get("/api/v1/catalog/objects/Account/relationships").json()["items"]
    assert {"Opportunities", "Contacts"} <= {r["relationship_name"] for r in rels if r["direction"] == "child"}
    # tokens never leave the backend
    assert "access_token" not in str(conn) and "auth_ref" not in conn


def test_nl_question_plan_validate_execute_save_reuse(ready):
    client, _ = ready
    q = "Show me the top 10 customers by opportunity revenue this year"
    plan = client.post("/api/v1/query/plan", json={"question": q}).json()
    assert plan["status"] == "validated", plan
    assert plan["source"] == "ai"
    assert "FROM Opportunity" in plan["soql"] and "GROUP BY Account.Name" in plan["soql"]
    assert "Opportunity" in plan["context_objects"]  # only relevant context sent to AI
    assert plan["token_usage"]["input_tokens"] > 0

    # generation never executes implicitly
    hist = client.get("/api/v1/query/history").json()["items"]
    assert hist[0]["status"] == "validated" and hist[0]["row_count"] is None

    res = client.post("/api/v1/query/execute", json={"execution_id": plan["execution_id"]}).json()
    assert res["status"] == "succeeded" and 0 < res["row_count"] <= 10
    assert res["columns"][:2] == ["Name", "total"]
    totals = [r["total"] for r in res["rows"]]
    assert totals == sorted(totals, reverse=True)

    saved = client.post("/api/v1/saved-queries", json={"name": "Top customers by revenue",
                                                       "execution_id": plan["execution_id"]}).json()
    assert "{{limit}}" in saved["template"] and "{{period}}" in saved["template"]

    again = client.post("/api/v1/query/plan", json={"question": "top 5 customers by opportunity revenue last year"}).json()
    assert again["source"] == "template", again
    assert again["token_usage"]["input_tokens"] == 0
    assert "LAST_YEAR" in again["soql"] and "LIMIT 5" in again["soql"]

    run = client.post(f"/api/v1/saved-queries/{saved['id']}/execute", json={"parameters": {"limit": 3}}).json()
    assert run["row_count"] <= 3 and run["source"] == "template"


def test_execute_rejects_invalid_and_write(ready):
    client, _ = ready
    r = client.post("/api/v1/query/execute", json={"soql": "DELETE FROM Account"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"
    r = client.post("/api/v1/query/execute", json={"soql": "SELECT Nope FROM Account"})
    assert r.status_code == 422


def test_idempotency_and_result_cache(ready):
    client, _ = ready
    body = {"soql": "SELECT Name, Industry FROM Account WHERE Industry = 'Technology' ORDER BY Name LIMIT 5"}
    a = client.post("/api/v1/query/execute", json=body, headers={"Idempotency-Key": "abc12345"}).json()
    b = client.post("/api/v1/query/execute", json=body, headers={"Idempotency-Key": "abc12345"}).json()
    assert b["idempotent_replay"] and a["execution_id"] == b["execution_id"]
    c = client.post("/api/v1/query/execute", json=body).json()
    assert c["cached"] is True
    assert all(r["Industry"] == "Technology" for r in a["rows"])


def test_audit_and_metrics(ready):
    client, _ = ready
    client.post("/api/v1/query/plan", json={"question": "How many open cases by priority"})
    audit = client.get("/api/v1/audit").json()["items"]
    actions = {a["action"] for a in audit}
    assert {"salesforce.oauth.callback", "metadata.sync.completed", "query.plan"} <= actions
    assert all(a["correlation_id"] for a in audit)
    m = client.get("/api/v1/metrics/summary").json()
    assert m["oauth"]["success"] == 1 and m["ai"]["requests"] >= 1


def test_tenant_isolation(client):
    login(client, "owner@acme.example.com")
    connect_mock_org(client)
    plan = client.post("/api/v1/query/plan", json={"question": "list accounts"}).json()
    client.cookies.clear()
    login(client, "intruder@evil.example.org")
    # other tenant cannot see the connection, catalog, executions or audit
    assert client.get("/api/v1/salesforce/connections").json() == []
    assert client.get("/api/v1/catalog/objects").status_code == 404
    r = client.post("/api/v1/query/execute", json={"execution_id": plan["execution_id"]})
    assert r.status_code == 404
    assert client.get("/api/v1/audit").json()["total"] >= 1  # only their own login event
    assert all(e["action"] == "auth.login" for e in client.get("/api/v1/audit").json()["items"])
    # spoofed tenant header is rejected
    acme_tid = plan and client.get("/api/v1/me").json()["tenant_id"]
    r = client.get("/api/v1/me", headers={"X-Tenant-Id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 401 and acme_tid


def test_member_cannot_connect(client):
    login(client, "owner@acme.example.com")
    client.cookies.clear()
    login(client, "member@acme.example.com")
    assert client.post("/api/v1/salesforce/connections").status_code == 403


def test_oauth_state_replay_rejected(client):
    login(client)
    url = client.post("/api/v1/salesforce/connections").json()["authorization_url"].split("localhost:8000")[1]
    assert "connected=" in client.get(url, follow_redirects=False).headers["location"]
    assert "oauth_state_invalid" in client.get(url, follow_redirects=False).headers["location"]
