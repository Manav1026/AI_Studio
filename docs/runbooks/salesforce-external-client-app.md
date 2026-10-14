# Runbook — Create the Salesforce External Client App (live mode)

Use a **Developer Edition or sandbox** org first. Never start with production data.

## 1. Create the app in Salesforce
Reference: [Configure the External Client App OAuth Settings](https://help.salesforce.com/s/articleView?id=xcloud.configure_external_client_app_oauth_settings.htm&language=en_US&type=5)
and [OAuth 2.0 Web Server Flow](https://help.salesforce.com/s/articleView?id=xcloud.remoteaccess_oauth_web_server_flow.htm&language=en_US&type=5).

1. Setup → Quick Find: **External Client App Manager** → **New External Client App**.
2. Basic Information: name `SF AI Workspace (dev)`, contact email.
3. Expand **API (Enable OAuth Settings)** → check **Enable OAuth**.
4. **Callback URL** (one per line; must exactly match `SF_CALLBACK_URL`):
   - `http://localhost:8000/api/v1/salesforce/oauth/callback` (local)
   - `https://<staging-domain>/api/v1/salesforce/oauth/callback` (later; HTTPS required outside localhost)
5. **OAuth Scopes**: `Manage user data via APIs (api)`, `Perform requests at any time (refresh_token, offline_access)`,
   `Access unique user identifiers (openid)`. Do not add `full`.
6. **Security**: enable **Require Proof Key for Code Exchange (PKCE)** and **Require Secret for Web Server Flow**.
7. Create. Then open the app → Settings → OAuth Settings → **Consumer Key and Secret** (identity verification required).
8. Policies: set permitted users (e.g. admin-approved users via a permission set) and a refresh-token policy that
   fits your security posture. New apps can take a few minutes to become usable.

## 2. Configure this project
```
SALESFORCE_MODE=live
SF_CLIENT_ID=<consumer key>
SF_CLIENT_SECRET=<consumer secret>
SF_LOGIN_URL=https://login.salesforce.com      # sandbox: https://test.salesforce.com
SF_CALLBACK_URL=http://localhost:8000/api/v1/salesforce/oauth/callback
SF_SCOPES=api refresh_token openid
```
Restart `api` and `worker`. In the UI: Connections → **Connect Salesforce** → log in → approve.

## 3. Verify
- Connection shows `active`, org ID, instance URL; first sync `succeeded`.
- `GET /api/v1/salesforce/connections` contains no tokens.
- Audit log shows `salesforce.connect.started` / `salesforce.connect.succeeded`.

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| `redirect_uri_mismatch` | Callback URL in Salesforce differs from `SF_CALLBACK_URL` (scheme, port, trailing slash). |
| `invalid_client_id` | App not yet propagated (wait a few minutes) or wrong login URL (prod vs sandbox). |
| `OAUTH_APPROVAL_ERROR_GENERIC` / user not approved | User not in the app's permitted users / permission set. |
| `invalid_grant` on refresh | Refresh token revoked or expired by policy → connection is marked `error`; reconnect. |
| `invalid_state` on callback | State expired (10 min), already used, or Redis flushed — start the flow again. |
| 403 `API_DISABLED_FOR_ORG` | Edition without API access; use Developer Edition / Enterprise+. |

## Rotation
Rotate the consumer secret in Salesforce, update the secret store, restart. Existing refresh tokens keep working.
Per-connection tokens are revoked on **Disconnect**.
