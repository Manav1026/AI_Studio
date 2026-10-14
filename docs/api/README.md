# API

- Interactive docs: http://localhost:8000/api/docs
- Contract: `packages/contracts/openapi.json` (regenerate with `make contracts`)
- Versioning: all endpoints under `/api/v1`; breaking changes go to `/api/v2`.
- Auth: `sfai_session` httpOnly cookie (browser) or `Authorization: Bearer <token>` (scripts, MCP).
- Errors: `{"error": {"code", "message", "correlation_id", "details"}}` with stable `code` values
  (`unauthorized`, `forbidden`, `not_found`, `validation_failed`, `rate_limited`, `upstream_error`, …).
- Every response has `X-Correlation-ID`; send your own to trace a request end to end.
- `POST /query/execute` accepts `Idempotency-Key`.

| Area | Endpoints |
|---|---|
| Identity | `POST /auth/dev-login`, `POST /auth/logout`, `POST /auth/api-token`, `GET /me` |
| Salesforce | `GET/POST /salesforce/connections`, `GET /salesforce/oauth/callback`, `DELETE /salesforce/connections/{id}`, `GET …/{id}/org-info`, `POST …/{id}/sync`, `GET …/{id}/sync-runs` |
| Catalog | `GET /catalog/objects`, `GET /catalog/objects/{object}`, `GET …/{object}/relationships`, `GET /catalog/search` |
| Query | `POST /query/plan`, `POST /query/validate`, `POST /query/execute`, `GET /query/history` |
| Saved queries | `GET/POST /saved-queries`, `GET/PATCH /saved-queries/{id}`, `POST /saved-queries/{id}/execute` |
| Admin | `GET /audit`, `GET /metrics/summary` |
| Health | `GET /healthz`, `GET /readyz` |
