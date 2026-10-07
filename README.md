# AI Studio — Salesforce + AI + MCP

Ask Salesforce questions in plain English. The system reads your org's metadata, builds a structured plan with AI,
compiles **read-only SOQL**, validates it against the catalog and policy, executes it under your Salesforce
permissions, saves reusable queries, and exposes the same governed capabilities to AI assistants through **MCP**.

This is built as the product's **production base**, not a throwaway demo. Start with
**[docs/BUILD_GUIDE.md](docs/BUILD_GUIDE.md)**: 16 steps in build order (database → cache → backend → frontend →
features), each with the files, commands, a definition of done and its production path.

## Stack
| Layer | Technology |
|---|---|
| Frontend | Next.js 16 · React 19 · TypeScript · Tailwind CSS 4 · Playwright |
| Backend | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic |
| Primary DB | PostgreSQL 16 |
| Cache / queue | Redis 7 · RQ worker |
| Salesforce | REST API · External Client App · OAuth 2.0 web-server flow + PKCE |
| AI | Internal AI gateway — `mock` (offline), `openai`, `anthropic` |
| MCP | Official MCP Python SDK v2 · Streamable HTTP + stdio |
| Ops | Docker + Compose · GitHub Actions · OpenTelemetry · structured JSON logs |

## Quick start (Docker)
```bash
cp .env.example .env                  # then set APP_SECRET_KEY / ENCRYPTION_KEY (commands in the file)
docker compose up -d --build
open http://localhost:3000            # sign in with any email → Connections → Connect Salesforce
```
Runs fully offline: `SALESFORCE_MODE=mock` uses a built-in demo org and `AI_PROVIDER=mock` a deterministic planner.
For a real org follow [the External Client App runbook](docs/runbooks/salesforce-external-client-app.md); for a real
model set `AI_PROVIDER=openai` + `OPENAI_API_KEY` (or `anthropic`).

| Service | URL |
|---|---|
| Web app | http://localhost:3000 |
| API docs | http://localhost:8000/api/docs |
| MCP endpoint | http://localhost:8001/mcp |
| Postgres / Redis | localhost:5432 / localhost:6379 |

## Quick start (without Docker)
Needs Python 3.12+, Node 20+, a local PostgreSQL and Redis.
```bash
cp .env.example .env && make setup
make infra          # or point DATABASE_URL / REDIS_URL at your own instances
make migrate
make api            # terminal 1
make worker         # terminal 2
make web            # terminal 3
make mcp            # terminal 4 (optional)
```

## Try it
1. Connections → **Connect Salesforce** → first metadata sync runs in the worker.
2. Metadata catalog → browse Opportunity → Account relationships.
3. Query workspace → "Show me the top 10 customers by opportunity revenue this year" → **Generate** → **Execute**.
4. **Save as reusable query**, then ask "top 5 customers by opportunity revenue last year" — answered from the
   template with no AI call.
5. History, Audit log and Overview KPIs show what happened.
6. MCP: create a token (`POST /api/v1/auth/api-token`) and run `services/api/scripts/mcp_smoke.py`.

## Tests
```bash
make test     # 37 backend tests: parser, validator, plan compiler, mocked Salesforce HTTP,
              # end-to-end API flow, tenant isolation, roles, OAuth replay, MCP tools
make e2e      # Playwright browser test of the whole slice
make lint
```

## Repository layout
```
apps/web/                     Next.js frontend
services/api/app/
  api/v1/                     HTTP routes (thin)
  domain/                     query plan, SOQL parser/validator, policy (pure logic)
  services/                   application services shared by API, worker and MCP
  integrations/salesforce/    OAuth, REST connector, mock org
  integrations/ai/            AI gateway + providers + versioned prompts
  mcp/                        MCP server (adapter over services)
  auth/  db/  cache/  core/   identity, models, Redis, config/logging/errors/telemetry
  workers/                    RQ worker + jobs
services/api/migrations/      Alembic migrations 0001–0003
workers/metadata-sync/        worker notes (code shares the API image)
packages/contracts/           OpenAPI contract (→ generated TS types)
infra/docker/  infra/terraform/
docs/  BUILD_GUIDE · architecture (ADRs) · api · security · runbooks
.github/workflows/ci.yml
```
