---
title: "Component design: Orchestrator"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: orchestrator
related:
  - docs/architecture/overview.md
  - docs/architecture/data-model.md
  - docs/architecture/decisions/0001-workflow-orchestration.md
---

## Purpose

The orchestrator is the API gateway and coordination layer for the platform. It owns user registration, the app registry, intent routing, and build dispatch. All external-facing HTTP requests from the Telegram bot pass through it.

## Responsibilities

**Owns:**
- User registration and verification flow
- App registry CRUD (`apps` table)
- Routing all chat messages to the designer agent
- Dispatching background build tasks (designer → coder)
- Agent run logging (`agent_runs` table)
- Monitor issue intake (`POST /apps/{name}/report-issue`)

**Does not own:**
- Conversation state (owned by the designer agent)
- Code scaffolding (owned by the coder agent)
- Test generation (owned by the tester agent)
- Container log monitoring (owned by the monitor agent)
- Telegram message handling (owned by the telegram bot)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, all HTTP endpoints, lifespan (DB pool, standards loading) |
| `workflow.py` | LangGraph graph for intent classification + designer routing; `run_build()` background task |
| `db.py` | asyncpg connection pool, schema auto-migration, query helpers |

## Key flows

### Chat message routing

1. Telegram bot sends `POST /chat` with `{user_id, message}`
2. `main.py` looks up user in `users`; returns 403 if not registered
3. Delegates to designer agent `POST /design` with message history from `messages`
4. Saves assistant reply to `messages`
5. Returns `{reply, build_triggered: bool}` to the Telegram bot
6. If `build_triggered`, orchestrator launches `run_build()` as a background task

### Build dispatch (`run_build`)

1. Updates `apps.status` to `provisioning`
2. Calls coder agent `POST /build` with the spec
3. On success: saves `repo_url`, `app_url`, sets `apps.status = building`
4. On failure: sets `apps.status = failed`, writes `error_detail`
5. Logs each step to `agent_runs`

### User registration

1. `POST /register` — validates invite code (if `INVITE_CODE` set), creates `users` row, calls Gitea API to create org
2. `POST /verify` — not currently used in the Telegram flow (registration is immediate)

### Monitor issue intake

1. Monitor agent calls `POST /apps/{name}/report-issue` with `{error_hash, summary, is_breaking}`
2. Orchestrator checks `app_issues` for duplicate hash
3. On new error: creates Gitea issue, inserts `app_issues` row, updates `apps.status` if breaking, sends Telegram notification

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /chat` | Telegram bot | Route message through designer |
| `POST /register` | Telegram bot | Register new user |
| `GET /apps` | Telegram bot | List user's apps |
| `POST /delete-app` | Telegram bot | Archive app |
| `POST /apps/{name}/report-issue` | Monitor agent | Ingest error report |
| `POST /runs/log` | Agents | Append agent run event |
| `GET /runs` | Admin | Query agent run history |
| `GET /health` | Traefik | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| `designer:8003 POST /design` | Delegate chat messages |
| `coder:8001 POST /build` | Dispatch build |
| Gitea HTTP API | Create orgs, repos, issues |
| Telegram Bot API | Send notifications (via bot token) |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | — | asyncpg DSN |
| `OLLAMA_MODEL` | `llama3.1:8b` | Model for LangGraph classification nodes |
| `GITEA_URL` | — | Internal Gitea base URL |
| `GITEA_ADMIN_USER` / `GITEA_ADMIN_PASS` | — | Gitea API credentials |
| `TELEGRAM_BOT_TOKEN` | — | For outbound Telegram notifications |
| `INVITE_CODE` | unset | If set, required during registration |

## Known limitations

- `run_build()` uses bare `asyncio.create_task()` — fire-and-forget with no retry or concurrency limit. ADR-0001 proposes replacing this with Temporal.
- Intent classification (LangGraph) runs in-process with the API server; a slow Ollama response blocks the HTTP worker.
- Woodpecker activation (direct Postgres insert) couples the orchestrator to Woodpecker's internal schema.
