"""OAuth 2.0 web-server flow (authorization code + PKCE) for a Salesforce External Client App."""
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.integrations.salesforce.base import SalesforceAuthError


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str | None
    instance_url: str
    id_url: str | None
    issued_at: str | None
    scope: str | None

    def to_secret(self) -> dict:
        return {"access_token": self.access_token, "refresh_token": self.refresh_token,
                "instance_url": self.instance_url, "id_url": self.id_url, "issued_at": self.issued_at}


class SalesforceOAuthClient:
    def __init__(self, http: httpx.Client | None = None):
        self.s = get_settings()
        self.http = http or httpx.Client(timeout=20)

    def authorize_url(self, state: str, code_challenge: str) -> str:
        params = {
            "response_type": "code", "client_id": self.s.sf_client_id, "redirect_uri": self.s.sf_callback_url,
            "scope": self.s.sf_scopes, "state": state, "code_challenge": code_challenge,
            "code_challenge_method": "S256", "prompt": "login consent",
        }
        return f"{self.s.sf_login_url}/services/oauth2/authorize?{urlencode(params)}"

    def _token_request(self, data: dict) -> dict:
        r = self.http.post(f"{self.s.sf_login_url}/services/oauth2/token", data=data,
                           headers={"Accept": "application/json"})
        if r.status_code != 200:
            try:
                err = r.json()
            except ValueError:
                err = {"error": r.text[:200]}
            raise SalesforceAuthError(f"Token request failed: {err.get('error')} {err.get('error_description', '')}",
                                      status=r.status_code, error_code=err.get("error"))
        return r.json()

    def exchange_code(self, code: str, code_verifier: str) -> TokenSet:
        body = self._token_request({
            "grant_type": "authorization_code", "code": code, "client_id": self.s.sf_client_id,
            "client_secret": self.s.sf_client_secret, "redirect_uri": self.s.sf_callback_url,
            "code_verifier": code_verifier,
        })
        return TokenSet(body["access_token"], body.get("refresh_token"), body["instance_url"], body.get("id"),
                        body.get("issued_at"), body.get("scope"))

    def refresh(self, refresh_token: str) -> TokenSet:
        body = self._token_request({
            "grant_type": "refresh_token", "refresh_token": refresh_token,
            "client_id": self.s.sf_client_id, "client_secret": self.s.sf_client_secret,
        })
        return TokenSet(body["access_token"], refresh_token, body["instance_url"], body.get("id"),
                        body.get("issued_at"), body.get("scope"))

    def revoke(self, token: str) -> None:
        self.http.post(f"{self.s.sf_login_url}/services/oauth2/revoke", data={"token": token})
