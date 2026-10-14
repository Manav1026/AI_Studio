# Developer commands (Section 10 of the blueprint). Assumes Python 3.12+, Node 20+, Docker.
API=services/api
WEB=apps/web
PY=cd $(API) && . .venv/bin/activate &&

.PHONY: setup infra migrate api worker mcp web test e2e lint contracts up down reset-db

setup:            ## one-time: env file, python venv, node modules
	@test -f .env || cp .env.example .env
	cd $(API) && python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
	cd $(WEB) && npm install

infra:            ## step 2+3: start PostgreSQL + Redis only
	docker compose up -d --wait postgres redis

migrate:          ## apply database migrations
	$(PY) alembic upgrade head

api:              ## FastAPI on :8000 (docs at /api/docs)
	$(PY) uvicorn app.main:app --reload --port 8000

worker:           ## background worker (metadata sync) on the Redis queue
	$(PY) python -m app.workers.main

mcp:              ## MCP server (Streamable HTTP) on :8001/mcp
	$(PY) python -m app.mcp.server

web:              ## Next.js on :3000
	cd $(WEB) && npm run dev

test:             ## backend unit/integration/contract/security tests
	$(PY) pytest

e2e:              ## browser test of the full vertical slice (stack must be running)
	cd $(WEB) && npx playwright test

lint:
	$(PY) ruff check app tests scripts
	cd $(WEB) && npm run typecheck

contracts:        ## regenerate OpenAPI + TS types
	$(PY) python scripts/export_openapi.py
	cd $(WEB) && npm run gen:types

up:               ## everything in containers
	docker compose up -d --build

down:
	docker compose down

reset-db:         ## drop and recreate local schema
	$(PY) alembic downgrade base && alembic upgrade head
