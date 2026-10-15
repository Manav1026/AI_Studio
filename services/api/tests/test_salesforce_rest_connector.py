"""Live connector against mocked Salesforce HTTP responses (no network)."""
import httpx
import pytest
from app.integrations.salesforce.base import SalesforceError
from app.integrations.salesforce.rest import RestSalesforceConnector

INSTANCE = "https://example.my.salesforce.com"


def make(handler, **kw):
    tokens = {"access_token": "AT1", "refresh_token": "RT", "instance_url": INSTANCE}
    return RestSalesforceConnector(tokens, "v62.0", http=httpx.Client(transport=httpx.MockTransport(handler)), **kw), tokens


def test_query_paginates_and_sends_bearer():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        assert req.headers["Authorization"] == "Bearer AT1"
        if "nextRecords" in req.url.path:
            return httpx.Response(200, json={"done": True, "totalSize": 3, "records": [{"Id": "3"}]})
        return httpx.Response(200, json={"done": False, "totalSize": 3, "records": [{"Id": "1"}, {"Id": "2"}],
                                         "nextRecordsUrl": "/services/data/v62.0/query/01g-nextRecords"})

    conn, _ = make(handler)
    res = conn.query("SELECT Id FROM Account LIMIT 3")
    assert [r["Id"] for r in res.records] == ["1", "2", "3"]
    assert seen[0].url.params["q"] == "SELECT Id FROM Account LIMIT 3"


def test_refreshes_token_on_401(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if req.headers["Authorization"] == "Bearer AT1":
            return httpx.Response(401, json=[{"errorCode": "INVALID_SESSION_ID", "message": "expired"}])
        return httpx.Response(200, json={"sobjects": [{"name": "Account"}]})

    from app.integrations.salesforce import oauth, rest

    class FakeOAuth:
        def refresh(self, rt):
            assert rt == "RT"
            return oauth.TokenSet("AT2", rt, INSTANCE, None, None, None)

    monkeypatch.setattr(rest, "SalesforceOAuthClient", FakeOAuth)
    persisted = []
    conn, tokens = make(handler, on_token_refresh=persisted.append)
    assert conn.describe_global() == [{"name": "Account"}]
    assert tokens["access_token"] == "AT2" and persisted and calls["n"] == 2


def test_salesforce_error_is_normalised():
    def handler(req):
        return httpx.Response(400, json=[{"errorCode": "MALFORMED_QUERY", "message": "unexpected token"}])

    conn, _ = make(handler)
    with pytest.raises(SalesforceError) as e:
        conn.query("SELECT")
    assert e.value.error_code == "MALFORMED_QUERY" and e.value.status == 400
