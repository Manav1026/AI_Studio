# ADR-0001 — Salesforce access via External Client App + OAuth 2.0 web-server flow with PKCE

Status: Accepted · Date: 2026-10-01

## Context
The product reads customer Salesforce data on behalf of named users. Passwords and security tokens
must never be collected. Salesforce recommends External Client Apps for new integrations.

## Decision
- One External Client App per environment (dev / staging / prod).
- Authorization-code (web-server) flow with PKCE and client secret, performed **only by the backend**.
- `state` is random, bound to user + tenant, stored in Redis for 10 minutes and deleted on first use.
- Access + refresh tokens are encrypted and stored behind the `SecretStore` interface; database rows hold
  only an `auth_ref`. Tokens never reach the browser, logs, AI prompts or MCP clients.
- Queries run with the **connecting user's** Salesforce permissions (FLS, sharing are enforced by Salesforce);
  results are cached per user, never shared across users.
- Scopes: `api refresh_token openid` (least privilege for read-only REST).

## Consequences
- A Salesforce admin must create and approve the app per customer org (documented in the runbook).
- Prototype secret backend = Fernet-encrypted rows; production swaps to AWS Secrets Manager / KMS with no
  change to callers.
- Integration-user (JWT bearer / client-credentials) access can be added later as a second connection type
  behind the same connector interface.
