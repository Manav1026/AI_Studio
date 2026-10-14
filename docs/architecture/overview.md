# Architecture overview

```
Browser (Next.js) ──/api/v1──► FastAPI ──► application services ──► domain (plan, SOQL parser, validator, policy)
                                  │               │                        │
MCP client ──Streamable HTTP──► MCP server ───────┘                        ▼
                                                              integrations: Salesforce connector, AI gateway
Worker (RQ) ◄── Redis queue ◄── API                                         │
   └── metadata sync ──► PostgreSQL (system of record) ◄────────────────────┘
                          Redis (state, rate limits, caches, queue)
```

Rules
1. Routes/tools are thin; business logic lives in `app/services` and `app/domain`.
2. Only `app/integrations/*` talks to external vendors.
3. Tenant context comes from the authenticated session, never from request bodies.
4. API, worker and MCP run from one image with different commands — one codebase, no duplicated logic.
