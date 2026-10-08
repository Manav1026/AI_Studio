"""Live Salesforce REST connector. Uses the *user's* OAuth identity, so Salesforce enforces object
permissions, field-level security and sharing on every call — the product never bypasses it."""
import time
from collections.abc import Callable
from urllib.parse import quote

import httpx

from app.core.logging import get_logger
from app.core.telemetry import tracer
from app.integrations.salesforce.base import (
    OrgIdentity,
    QueryResult,
    SalesforceAuthError,
    SalesforceConnector,
    SalesforceError,
)
from app.integrations.salesforce.oauth import SalesforceOAuthClient, TokenSet

log = get_logger("salesforce")


class RestSalesforceConnector(SalesforceConnector):
    def __init__(self, tokens: dict, api_version: str, *, timeout: float = 30.0,
                 on_token_refresh: Callable[[TokenSet], None] | None = None,
                 on_api_call: Callable[[str], None] | None = None, http: httpx.Client | None = None):
        self.tokens = tokens
        self.api_version = api_version
        self.on_token_refresh = on_token_refresh
        self.on_api_call = on_api_call
        self.http = http or httpx.Client(timeout=timeout)

    @property
    def base(self) -> str:
        return f"{self.tokens['instance_url']}/services/data/{self.api_version}"

    def _request(self, method: str, url: str, *, retried: bool = False, attempt: int = 0, **kw) -> dict:
        headers = {"Authorization": f"Bearer {self.tokens['access_token']}", "Accept": "application/json"}
        with tracer.start_as_current_span("salesforce.request") as span:
            span.set_attribute("http.method", method)
            span.set_attribute("sf.path", url.split("/services/")[-1][:120])
            start = time.perf_counter()
            r = self.http.request(method, url, headers=headers, **kw)
            log.info("salesforce_call", method=method, path=url.split("/services/")[-1][:120],
                     status=r.status_code, duration_ms=int((time.perf_counter() - start) * 1000))
        if self.on_api_call:
            self.on_api_call(url)
        if r.status_code == 401 and not retried and self.tokens.get("refresh_token"):
            new = SalesforceOAuthClient().refresh(self.tokens["refresh_token"])
            self.tokens.update(new.to_secret())
            if self.on_token_refresh:
                self.on_token_refresh(new)
            return self._request(method, url, retried=True, **kw)
        if r.status_code == 401:
            raise SalesforceAuthError("Salesforce session expired or revoked", status=401)
        if r.status_code in (429, 503) and attempt < 3:
            time.sleep(min(2 ** attempt, 8))  # Salesforce-aware backoff
            return self._request(method, url, retried=retried, attempt=attempt + 1, **kw)
        if r.status_code >= 400:
            try:
                body = r.json()
                err = body[0] if isinstance(body, list) and body else body
                raise SalesforceError(err.get("message", r.text[:300]), status=r.status_code,
                                      error_code=err.get("errorCode"))
            except ValueError:
                raise SalesforceError(r.text[:300], status=r.status_code) from None
        return r.json()

    def get_identity(self) -> OrgIdentity:
        info = self._request("GET", f"{self.tokens['instance_url']}/services/oauth2/userinfo")
        org_name = None
        try:
            org = self._request("GET", f"{self.base}/query?q=" + quote("SELECT Name FROM Organization LIMIT 1"))
            org_name = (org.get("records") or [{}])[0].get("Name")
        except SalesforceError:
            pass
        return OrgIdentity(org_id=info["organization_id"], user_id=info["user_id"],
                           username=info.get("preferred_username") or info.get("email", ""),
                           instance_url=self.tokens["instance_url"], org_name=org_name)

    def describe_global(self) -> list[dict]:
        return self._request("GET", f"{self.base}/sobjects/")["sobjects"]

    def describe_object(self, name: str) -> dict:
        return self._request("GET", f"{self.base}/sobjects/{quote(name)}/describe/")

    def query(self, soql: str, *, max_records: int = 2000) -> QueryResult:
        body = self._request("GET", f"{self.base}/query", params={"q": soql})
        records = list(body.get("records", []))
        while not body.get("done", True) and len(records) < max_records:
            body = self._request("GET", f"{self.tokens['instance_url']}{body['nextRecordsUrl']}")
            records.extend(body.get("records", []))
        return QueryResult(records=records[:max_records], total_size=body.get("totalSize", len(records)),
                           done=body.get("done", True))

    def get_limits(self) -> dict:
        return self._request("GET", f"{self.base}/limits/")
