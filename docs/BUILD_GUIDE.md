# Step-by-Step Build Guide — Prototype that becomes the Product

This guide follows the blueprint's build sequence (Section 8) and turns it into concrete steps,
each mapped to the code in this repository. Everything here is the **production base**: the same
database, migrations, API contracts, services, connector interface, AI gateway, MCP adapter,
tests and containers continue after approval. Only scale, hardening, identity and infrastructure change.

---

## The build order (and why)

```
 Step 1  Repository + local environment
   │
 Step 2  PRIMARY DATABASE  (PostgreSQL)  ◄── system of record; everything persists here
   │
 Step 3  CACHE + QUEUE     (Redis)       ◄── OAuth state, rate limits, job queue, caches
   │
 Step 4  BACKEND foundation (FastAPI)    ◄── config, errors, correlation IDs, logs, health
 Step 5  Data model + migrations (SQLAlchemy 2 + Alembic)
 Step 6  App identity + tenant context
   │
 Step 7  FRONTEND shell    (Next.js)     ◄── consumes the API contracts from Steps 4–6
   │
 Step 8  Salesforce connection (External Client App OAuth)
 Step 9  Background worker + metadata sync
 Step 10 Catalog API + object explorer UI
 Step 11 AI gateway + query engine (plan → SOQL → validate)
 Step 12 Authorized execution + results viewer
 Step 13 Saved queries + history + AI cost
 Step 14 MCP server (same services, no new privileges)
 Step 15 Hardening: observability, audit, metrics, security + E2E tests
 Step 16 CI/CD + production transition
```

**Why database → cache → backend → frontend:**

| Order | Layer | Reason it comes here |
|---|---|---|
| 1st | PostgreSQL | It is the system of record. Your first real backend code (models + migrations) cannot exist without it, and the blueprint forbids a throwaway SQLite phase. Starting it takes minutes. |
| 2nd | Redis | The backend needs it from its first real feature: OAuth `state` (Step 8), rate limits and the job queue (Step 9). Starting it with Postgres keeps the environment identical to production from day one. |
| 3rd | Backend | Owns contracts, authorization and every Salesforce/AI call. The frontend must never hold secrets or make authorization decisions, so the API has to exist first. |
| 4th | Frontend | It is a client of `/api/v1`. Building it after identity (Step 6) means the very first screen is a real sign-in against the real API, not a mockup. |

After the foundation (Steps 1–7) you build **vertical features** (Steps 8–14). Each step adds a
backend capability *and* its UI together, so something demonstrable works at the end of every step.

Sprint mapping from the blueprint: **Sprint 1** = Steps 1–7 · **Sprint 2** = Steps 8–10 ·
**Sprint 3** = Step 11 · **Sprint 4** = Steps 12–14 · then Steps 15–16.

---

## Step 0 — Lock decisions before coding (blueprint §19)

| Decision | Choice made in this repo | Where it lives |
|---|---|---|
| Database | PostgreSQL from day one | `docker-compose.yml`, `services/api/migrations` |
| Migrations | Alembic, versioned, tested in CI | `services/api/migrations/versions` |
| API versioning | `/api/v1` | `app/main.py` |
| Tenant model | `tenant_id` on every tenant-owned row, server-derived | `app/db/models.py`, `app/auth` |
| Salesforce auth | External Client App + OAuth 2.0 web-server flow + PKCE | `app/integrations/salesforce/oauth.py` |
| Token boundary | Backend only, encrypted, referenced by `auth_ref` | `app/services/secret_store.py` |
| AI | One provider behind an internal gateway (mock / OpenAI / Anthropic) | `app/integrations/ai/gateway.py` |
| Query scope | Read-only SOQL subset | `app/domain/soql/parser.py` |
| MCP | Official Python SDK v2, adapter over shared services | `app/mcp/server.py` |
| Deployment | Docker images; one API image runs api / worker / mcp | `infra/docker` |
| Cloud | Pick one now (AWS is the default suggestion) | `infra/terraform/README.md` |

Record any change as an ADR in `docs/architecture/`.

---

## Step 1 — Repository and local environment

**Goal:** anyone can clone and start the same stack.

**Build**
- Monorepo layout from blueprint §9: `apps/web`, `services/api`, `workers/`, `packages/contracts`, `infra/`, `docs/`.
- `.env.example` (all settings, no real secrets) → copied to `.env` locally, never committed.
- `docker-compose.yml` with `postgres`, `redis`, `migrate`, `api`, `worker`, `mcp`, `web`.
- `Makefile` with the developer commands from blueprint §10.

**Run**
```bash
cp .env.example .env
make setup            # python venv + npm install
```

**Done when:** `docker compose config` is valid and `make setup` succeeds on a clean machine.

---

## Step 2 — Primary database: PostgreSQL

**Goal:** the system of record is running exactly as production will run it (same engine, migrations).

**Build**
- `postgres` service (16-alpine) with a named volume and health check in `docker-compose.yml`.
- `DATABASE_URL` in `.env` (`postgresql+psycopg://…`).
- Separate `sfai_test` database for automated tests.

**Run**
```bash
docker compose up -d --wait postgres
docker compose exec postgres psql -U sfai -c "select version();"
```

**Done when:** `pg_isready` passes and you can connect with the URL from `.env`.

**Production path:** managed PostgreSQL (RDS/Aurora/Cloud SQL) with Multi-AZ, encryption, PITR backups.
Only `DATABASE_URL` changes.

---

## Step 3 — Cache and queue: Redis

**Goal:** ephemeral state has a home that is *not* the database.

**Build**
- `redis` service (7-alpine, AOF on) in `docker-compose.yml`; `REDIS_URL` in `.env`.
- `app/cache/redis.py` — one client and the helpers every later step uses:

| Key pattern | Used for | Step |
|---|---|---|
| `oauth:state:{state}` | one-time OAuth state + PKCE verifier (10-min TTL, get-and-delete) | 8 |
| `rq:*` (queue `metadata-sync`) | background jobs | 9 |
| `catalog:{conn}:{version}:*` | catalog views / object detail (invalidated on sync) | 10 |
| `rl:{bucket}:{user}:{minute}` | AI + query rate limits | 11–12 |
| `qr:{conn}:{version}:{user}:{sha}` | per-user result cache (Salesforce permissions differ per user) | 12 |
| `idem:{tenant}:{user}:{key}` | `Idempotency-Key` replay | 12 |
| `sfapi:{conn}:{date}` | Salesforce API call counter | 12, 15 |

**Run**
```bash
docker compose up -d --wait redis
docker compose exec redis redis-cli ping     # PONG
```

**Done when:** `PONG`. Rule: Redis may be flushed at any time without losing business data.

---

## Step 4 — Backend foundation: FastAPI

**Goal:** an API skeleton that already behaves like production.

**Build** (`services/api/app/`)
- `core/config.py` — typed settings (pydantic-settings); same interface in every environment.
- `core/errors.py` — stable error contract `{"error": {code, message, correlation_id, details}}`.
- `core/middleware.py` + `core/context.py` — correlation ID in/out (`X-Correlation-ID`) on every request.
- `core/logging.py` — structured JSON logs with correlation ID and automatic secret redaction.
- `core/telemetry.py` — OpenTelemetry (no-op until `OTEL_ENABLED=true`).
- `api/v1/health.py` — `/healthz` (liveness) and `/readyz` (checks PostgreSQL + Redis).
- `main.py` — app factory, CORS, routers under `/api/v1`, OpenAPI at `/api/v1/openapi.json`, docs at `/api/docs`.

**Run**
```bash
make api
curl localhost:8000/readyz      # {"status":"ok","postgres":true,"redis":true}
```

**Done when:** readiness is green and every response carries `X-Correlation-ID`.

---

## Step 5 — Data model and migrations: SQLAlchemy 2 + Alembic

**Goal:** the relational schema from blueprint §5, created only through migrations.

**Build**
- `app/db/models.py` — all tables, typed SQLAlchemy 2 models, JSONB for variable Salesforce metadata.
- `migrations/versions/` — three migrations that match the build steps:

| Migration | Tables | Introduced in |
|---|---|---|
| `0001_identity_tenancy_connections_audit` | `tenants`, `users`, `tenant_users`, `credential_secrets`, `salesforce_connections`, `audit_events` | Steps 5–6, 8 |
| `0002_metadata_catalog` | `salesforce_objects`, `salesforce_fields`, `salesforce_relationships`, `sync_runs` | Step 9 |
| `0003_query_engine` | `saved_queries`, `query_executions`, `ai_usage` | Steps 11–13 |

**Run**
```bash
make migrate                         # alembic upgrade head
cd services/api && alembic check     # models and migrations agree
```

**Done when:** `upgrade head`, `downgrade base`, `upgrade head` all succeed and `alembic check` reports no drift.

**Rule from now on:** never change the schema by hand. New column → new migration → reviewed in PR.

---

## Step 6 — App identity and tenant context

**Goal:** a user signs in and the API derives tenant context from membership — never from client input.

**Build**
- `app/auth/provider.py` — auth abstraction. Prototype: `dev` sign-in (email, no password, controlled group).
  Production: OIDC provider behind the same function signatures.
- `app/core/security.py` — signed session JWT (httpOnly cookie for the browser, bearer for MCP/scripts).
- `app/auth/context.py` — `RequestContext(user_id, tenant_id, role, interface)` + `require_role()`.
- `app/auth/deps.py` — `get_ctx` dependency; `X-Tenant-Id` is honoured only after a membership check.
- Endpoints: `POST /auth/dev-login`, `POST /auth/logout`, `POST /auth/api-token`, `GET /me`.
- Roles: `owner` / `admin` (connect orgs, sync, audit, metrics) and `member` (query, save).

**Done when:** `GET /api/v1/me` returns your user + tenant; spoofed tenant headers return 401
(`tests/test_end_to_end.py::test_tenant_isolation`).

---

## Step 7 — Frontend shell: Next.js + React + TypeScript + Tailwind

**Goal:** the real product UI shell, signed in against the real API.

**Build** (`apps/web/`)
- `next.config.ts` — rewrites `/api/v1/*` to FastAPI so the browser talks to one origin; security headers.
- `src/lib/api.ts` — typed fetch client that understands the error contract and redirects on 401.
- `src/lib/types.ts` + `npm run gen:types` (OpenAPI → `src/lib/api-types.ts`).
- `src/components/ui.tsx` — small accessible component set (Button, Card, Badge, DataTable…) with no business logic.
- `src/components/AppShell.tsx` — authenticated layout, navigation, role-aware menu.
- Pages: `/login`, `/` (overview), `/connections`, `/catalog`, `/query`, `/saved`, `/history`, `/audit`.

**Run**
```bash
make web        # http://localhost:3000
```

**Done when:** you can sign in and navigate; no Salesforce or AI secret exists anywhere in `apps/web`.

---

## Step 8 — Salesforce connection (External Client App OAuth)

**Goal:** connect a real Salesforce Developer Edition / sandbox org without ever asking for a password.

**Build**
- `integrations/salesforce/base.py` — the connector **interface** (identity, describeGlobal, describe, query, limits).
- `integrations/salesforce/oauth.py` — authorization-code flow with **PKCE**, token exchange, refresh, revoke.
- `integrations/salesforce/rest.py` — live REST connector: bearer auth, auto-refresh on 401, backoff on 429/503,
  pagination, normalized errors, API-call counting, tracing spans.
- `integrations/salesforce/mock.py` + `mock_data.py` — built-in demo org (Account, Contact, Opportunity, Case, User,
  custom `Project__c`) that runs the **same** OAuth callback, sync and SOQL path.
- `services/secret_store.py` — `SecretStore` interface; prototype backend = Fernet-encrypted rows; `auth_ref` only.
- `services/connection_service.py` — state bound to user + tenant, one-time use (replay-safe), org identity check,
  connection upsert, audit events, disconnect + revoke.
- API: `POST /salesforce/connections`, `GET /salesforce/oauth/callback`, `GET /salesforce/connections`,
  `DELETE /salesforce/connections/{id}`, `GET /salesforce/connections/{id}/org-info`.
- UI: Connections page with **Connect Salesforce**.

**Run (mock org first, then real org)**
```bash
SALESFORCE_MODE=mock      # in .env — click Connect Salesforce, flow completes against the demo org
# then follow docs/runbooks/salesforce-external-client-app.md and set:
SALESFORCE_MODE=live  SF_CLIENT_ID=…  SF_CLIENT_SECRET=…  SF_LOGIN_URL=https://login.salesforce.com
```

**Done when:** the org appears as `active`; API responses never contain tokens or `auth_ref`;
replaying the OAuth callback fails (`test_oauth_state_replay_rejected`).

---

## Step 9 — Background worker and metadata sync

**Goal:** objects, fields and relationships land in PostgreSQL without blocking API requests.

**Build**
- `workers/main.py` + `workers/jobs.py` — RQ worker on Redis queue `metadata-sync` (same image as the API).
- `services/metadata_service.py` — blueprint Flow B: select objects (configured standard list + custom `__c`),
  describe, **normalize** into canonical records, upsert by API name, build relationship graph (parent + child,
  lookup vs master-detail), mark removed metadata inactive (never hard-delete), compute `catalog_version`,
  record `sync_runs` metrics, audit, invalidate Redis catalog keys.
- Callback queues the first sync automatically; `POST /salesforce/connections/{id}/sync` re-syncs.

**Run**
```bash
make worker
```

**Done when:** the Connections page shows a `succeeded` sync run with object/field/relationship counts.

---

## Step 10 — Catalog API and object explorer

**Goal:** users understand the discovered schema **without AI**.

**Build**
- `services/catalog_service.py` — list/search objects (paginated), object detail, relationships,
  `load_view()` (cached `CatalogView` used by the planner/validator), metadata search with business synonyms.
- API: `GET /catalog/objects`, `/catalog/objects/{object}`, `/catalog/objects/{object}/relationships`, `/catalog/search`.
- UI: `/catalog` (searchable list, standard vs custom) and `/catalog/[object]` (fields with type and
  filter/group/sort/aggregate capabilities, picklist values, parent/child relationships).

**Done when:** you can browse Opportunity → Account → Contacts entirely from the internal catalog.

---

## Step 11 — AI gateway and query engine (no execution yet)

**Goal:** a natural-language request produces a **validated** query — and nothing runs yet.

**Build**
- `integrations/ai/gateway.py` — the only place that knows AI vendors: provider selection, retries, tracing,
  token counting, cost estimation. Providers: `mock_provider.py` (deterministic, offline), `openai_provider.py`
  (strict JSON-schema output), `anthropic_provider.py`.
- `integrations/ai/prompts.py` — versioned system prompt (`nl2plan-v1`) + plan JSON schema.
- `domain/query_plan.py` — the **structured plan** contract from blueprint §7 and a deterministic
  `plan_to_soql()` compiler (values are typed + escaped from catalog types; model text is never concatenated).
- `domain/soql/parser.py` — strict parser for the allowed read-only subset (rejects DML, `FOR UPDATE`,
  subqueries, `TYPEOF`, `;`, unknown functions).
- `domain/soql/validator.py` — the 12-check pipeline: parse → read-only → object exists/queryable → policy →
  fields exist → relationship paths → operator/type compatibility → aggregate/group rules → sort rules →
  complexity → limit inject/cap.
- `domain/policy.py` — allow/deny rules (blocked objects/fields, limits, depth).
- `services/catalog_service.build_ai_context()` — sends the AI only the relevant objects/fields.
- `services/query_service.plan()` — blueprint Flow C, persists a `query_executions` row + `ai_usage`.
- API: `POST /query/plan`, `POST /query/validate`.

**Done when:** "Show me the top 10 customers by opportunity revenue this year" returns
`SELECT Account.Name, SUM(Amount) total FROM Opportunity WHERE CloseDate = THIS_YEAR AND IsWon = true
GROUP BY Account.Name ORDER BY SUM(Amount) DESC NULLS LAST LIMIT 10` with status `validated`, and
history shows it was **not** executed.

**Switch to a real model:** set `AI_PROVIDER=openai` + `OPENAI_API_KEY` (or `anthropic`). Nothing else changes.

---

## Step 12 — Authorized execution and results viewer

**Goal:** real read-only Salesforce data comes back correctly, under the user's Salesforce permissions.

**Build**
- `services/query_service.execute()` — explicit endpoint; **re-validates every time**; audit before and after;
  per-user Redis result cache; rate limit; timeout + row cap; normalized/flattened rows and stable columns;
  Salesforce errors mapped to `upstream_error`; auth failures mark the connection `error`.
- `POST /query/execute` with `Idempotency-Key` support.
- UI: Query workspace — plan card, editable SOQL (edits must re-validate), validation checks, **Execute**, results table.

**Done when:** results match Salesforce, invalid or write queries return 422 and are never sent to Salesforce.

---

## Step 13 — Saved queries, history, AI usage

**Goal:** repeated questions reuse governed query logic instead of calling the AI.

**Build**
- `services/saved_query_service.py` — templates with typed parameters (`{{limit}}`, `{{period}}`),
  auto-parameterization when saving, safe rendering (values become SOQL literals), versioning on change,
  private/tenant visibility, template matching + parameter extraction from the new question.
- `plan()` checks templates first → `source: "template"`, 0 tokens.
- API: `POST/GET /saved-queries`, `GET/PATCH /saved-queries/{id}`, `POST /saved-queries/{id}/execute`, `GET /query/history`.
- UI: Saved queries (parameter inputs + Run), History (source, interface, rows, latency, tokens).

**Done when:** after saving the top-customers query, "top 5 customers by opportunity revenue last year"
is answered from the template with `LAST_YEAR` and `LIMIT 5` and zero AI tokens.

---

## Step 14 — MCP server

**Goal:** an MCP client can discover and call governed read-only tools through the **same** services.

**Build** — `app/mcp/server.py` (official MCP Python SDK v2, `MCPServer`, Streamable HTTP + stdio)
- Tools: `list_objects`, `describe_object`, `search_metadata`, `get_relationships`, `execute_soql`,
  `get_records`, `aggregate_records` (allow-listed functions), `saved_query`, `get_org_info`.
- Auth: bearer token verified by `AppTokenVerifier` (same JWT + membership check as the API).
- Every tool → application service → validator/policy → connector → audit `mcp.tool_call`.

**Run**
```bash
make mcp                                                         # http://localhost:8001/mcp
TOKEN=$(curl -s -b cookies.txt -X POST localhost:8000/api/v1/auth/api-token | jq -r .token)
MCP_TOKEN=$TOKEN python services/api/scripts/mcp_smoke.py
```

**Done when:** the smoke script lists 9 tools, aggregates data, and `execute_soql("DELETE …")` is rejected.

---

## Step 15 — Hardening

**Goal:** the prototype is demonstrable and operationally diagnosable.

**Build**
- Audit view `GET /audit` (admin) + UI page; every event has a correlation ID that also appears in logs/traces.
- KPIs `GET /metrics/summary` — OAuth success/failure, sync duration/errors, catalog freshness, validation
  rejection rate, Salesforce latency (avg/p95), API calls today, AI tokens/cost by model, saved-query reuse rate,
  MCP calls by result (blueprint §14). Shown on the Overview page.
- Tests (blueprint §15): unit (parser, validator, plan compiler), integration (Postgres + Redis + mocked Salesforce
  HTTP), contract (OpenAPI drift), security (tenant isolation, token leakage, role checks, OAuth replay, read-only),
  MCP, and Playwright E2E for the full slice.

**Run**
```bash
make test        # 37 backend tests
make e2e         # Playwright: sign in → connect → sync → catalog → ask → execute → save → reuse → audit
```

---

## Step 16 — CI/CD and production transition

**Build**
- `.github/workflows/ci.yml` — lint, migrations + `alembic check`, pytest with real Postgres/Redis, OpenAPI drift,
  web typecheck + build, full-stack Playwright, image build.
- `infra/terraform/README.md` — target managed services and modules.

**Production checklist** (blueprint §18) — what changes, and where:

| Item | Change | Code touched |
|---|---|---|
| Identity | OIDC/SSO provider | `app/auth/provider.py` only |
| Secrets | Secrets Manager backend | new `SecretStore` implementation |
| Database / Redis | Managed, HA, backups | env vars only |
| Rate limits | Sliding window / gateway | `app/cache/redis.py` |
| AI | Budgets, fallback provider, eval suite | `app/integrations/ai/` |
| Observability | OTLP exporter → monitoring | `OTEL_ENABLED=true OTEL_EXPORTER=otlp` |
| Tenancy | Postgres RLS + adversarial isolation tests | new migration + tests |
| Environments | dev → staging → prod, same image | CI/CD |
| New capabilities | Feature flags, not branches | — |

Nothing in this list requires rewriting the domain services, data model, API contracts or MCP tools.
