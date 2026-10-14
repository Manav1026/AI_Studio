# Security controls (prototype baseline)

| Threat | Control | Verified by |
|---|---|---|
| Token theft / leakage | Backend-only OAuth, encrypted secret store, `auth_ref` indirection, log redaction | `test_connect_sync_catalog` (no tokens in responses) |
| Cross-tenant access | Tenant from membership; tenant-scoped queries; header spoofing rejected | `test_tenant_isolation` |
| Privilege escalation | Roles (`owner`/`admin`/`member`) on connect, sync, audit, metrics | `test_member_cannot_connect` |
| OAuth CSRF / replay | Random state bound to user+tenant, 10-min TTL, single use; PKCE S256 | `test_oauth_state_replay_rejected` |
| Write / unsafe SOQL | Strict read-only parser; no DML, subqueries, `FOR UPDATE`, `;` | `test_rejects_unsafe_or_unsupported`, `test_execute_rejects_invalid_and_write` |
| Prompt injection | AI returns a plan only; deterministic compiler + validator + policy | `test_plan_values_are_escaped` |
| Sensitive fields | Policy deny-lists for objects/fields | `test_policy_blocks_field_and_object` |
| MCP abuse | Bearer auth, same services + validator, audited `mcp.tool_call` | `test_mcp_*` |
| Abuse / cost | Redis rate limits on AI and execution, row caps, timeouts, cost tracking | metrics summary |
| Browser attacks | httpOnly SameSite session cookie, security headers, single origin via proxy | `next.config.ts` |

Before production: OIDC SSO, Secrets Manager + KMS, Postgres row-level security, WAF, dependency and
container scanning in CI, penetration test, data-retention policy for audit and result data.
