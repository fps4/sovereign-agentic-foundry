---
title: "Component design: Gateway"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: gateway
related:
  - docs/architecture/overview.md
  - docs/architecture/data-model.md
  - docs/architecture/decisions/0001-workflow-orchestration.md
  - docs/architecture/decisions/0002-kanban-board-integration.md
---

## Purpose

The gateway is the API facade and coordination layer for the platform. It owns user registration, the app registry, build pipeline dispatch, board card state, and agent run logging. All HTTP requests from the portal and Telegram bot pass through it. It contains no LLM calls — all reasoning is delegated to agents.

## Responsibilities

**Owns:**
- User registration and the app registry (`users`, `apps` tables)
- Web authentication (`POST /auth/login`, JWT issuance)
- Routing all chat messages to the intake agent
- Driving the build pipeline: sequencing intake → infra → planner → builder → ui-designer → reviewer → publisher → acceptance
- Board card lifecycle (`board_cards` table): creating and moving cards at each pipeline stage
- Agent run logging (`agent_runs` table)
- Watchdog issue intake (`POST /apps/{name}/report-issue`) and remediation dispatch
- App status lifecycle updates

**Does not own:**
- Conversation state (owned by the intake agent)
- Planning and code generation (owned by the planner and builder agents)
- UI template generation (owned by the ui-designer agent)
- Standards review (owned by the reviewer agent)
- Git operations (owned by the publisher)
- Infrastructure provisioning (owned by the infra agent)
- Container monitoring (owned by the watchdog)
- Telegram message handling (owned by the Telegram bot)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, all HTTP endpoints, lifespan (DB pool) |
| `pipeline.py` | `run_build()` background task; sequences agents in order; writes board cards at each stage; handles failures |
| `db.py` | asyncpg connection pool, schema auto-migration, query helpers |
| `auth.py` | JWT issuance and validation; bcrypt password check |

## Key flows

### Chat message routing

1. Portal or Telegram bot sends `POST /chat` with `{user_id, message}`
2. Gateway looks up user in `users`; returns 403 if not registered
3. Delegates to intake agent `POST /intake` with message history from `messages`
4. Saves assistant reply to `messages`
5. Returns `{reply, spec_locked: bool}` to the caller
6. If `spec_locked`, gateway launches `run_build()` as a background task

### Build pipeline (`run_build`)

1. Sets `apps.status = provisioning`; creates `board_cards` entry in `in_progress`
2. If spec requires external resources: calls infra agent `POST /provision`
3. Calls planner agent `POST /plan` with spec (and provisioned resource context)
4. Calls builder agent `POST /build` with the build plan; moves board card to `review`
5. Calls ui-designer agent `POST /design-ui` with spec and route manifest
6. Calls reviewer agent `POST /review`; on fix-required: loops back to builder (bounded retries)
7. Calls publisher `POST /publish`; sets `apps.status = building`
8. After Woodpecker deploys: calls acceptance agent `POST /accept`
9. On acceptance pass: sets `apps.status = active`; moves board card to `done`; sends notification with app URL
10. On acceptance fail: calls remediation agent `POST /remediate`
11. On any unrecoverable failure: sets `apps.status = failed`; moves board card to `failed`; writes `error_detail`; logs to `agent_runs`

### Web authentication

1. Portal sends `POST /auth/login` with `{email, password}`
2. Gateway looks up `users` by email; bcrypt-checks password
3. Issues a JWT (signed with `JWT_SECRET`); returns `{token, user_id}`
4. Subsequent requests carry `Authorization: Bearer <token>`

### User registration

1. `POST /register` — validates invite code (if `INVITE_CODE` set), creates `users` row, calls Gitea API to create org

### App documentation fetch

The gateway proxies doc file content from the app's Gitea repository, so the portal can display app docs without exposing Gitea credentials to the browser.

1. Portal calls `GET /apps/{id}/docs` (fetches `README.md`) or `GET /apps/{id}/docs?path={filepath}` (fetches a specific file from `docs/`)
2. Gateway resolves the app's Gitea repo from `apps.repo_url`
3. Calls Gitea API: `GET /repos/{org}/{repo}/contents/{path}`
4. Decodes base64 content; returns `{path, content, last_updated}`
5. Portal renders the markdown

### Watchdog issue intake

1. Watchdog calls `POST /apps/{name}/report-issue` with `{error_hash, summary, is_breaking, logs}`
2. Gateway checks `app_issues` for duplicate hash; skips if already recorded
3. On new breaking error: calls remediation agent; updates `apps.status = degraded`; moves board card to `failed`
4. On new non-breaking error: creates Gitea issue; sends notification

## Data owned

**Writes:**
- `users` — registration, password hash, email, Gitea org
- `apps` — status lifecycle, repo URL, app URL, error detail
- `messages` — conversation history per user
- `agent_runs` — append-only audit trail per pipeline step
- `app_issues` — deduplication log for monitor-detected errors
- `board_cards` — Kanban card state; moved and commented by gateway on pipeline events

**Reads (does not own):**
- `board_cards` — gateway reads for `GET /apps/{id}/board` responses
- Woodpecker CI state (read via Woodpecker API, not direct DB)

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /auth/login` | Portal | Web sign-in; returns JWT |
| `POST /auth/register-web` | Portal | First-time web registration (requires invite code) |
| `POST /chat` | Portal, Telegram bot | Route message through intake |
| `GET /messages` | Portal | Load conversation history |
| `POST /register` | Telegram bot | Register new user (Telegram flow) |
| `GET /apps` | Portal, Telegram bot | List user's apps |
| `GET /apps/{id}/board` | Portal | Kanban board state for one app |
| `POST /apps/{id}/board/cards` | Portal | Operator creates a Backlog card |
| `PATCH /apps/{id}/board/cards/{card_id}` | Portal | Move or update a card |
| `GET /apps/{id}/runs` | Portal | Build timeline (agent_runs) |
| `GET /apps/{id}/logs` | Portal | Log tail (proxied from Loki) |
| `GET /apps/{id}/issues` | Portal | Gitea issues list for the app |
| `GET /apps/{id}/docs` | Portal | App `README.md` content (proxied from Gitea) |
| `GET /apps/{id}/docs?path={filepath}` | Portal | Specific doc file from app's `docs/` directory (proxied from Gitea) |
| `POST /delete-app` | Portal, Telegram bot | Archive app and trigger infra teardown |
| `POST /apps/{name}/report-issue` | Watchdog | Ingest error report |
| `POST /apps/{name}/status` | Acceptance, remediation | Update app status |
| `POST /runs/log` | Agents | Append agent run event |
| `GET /health` | Traefik | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| `intake POST /intake` | Delegate chat messages |
| `infra POST /provision` | Provision per-app resources (conditional) |
| `planner POST /plan` | Generate build plan |
| `builder POST /build` | Generate application files |
| `ui-designer POST /design-ui` | Generate frontend templates |
| `reviewer POST /review` | Standards quality gate |
| `publisher POST /publish` | Commit files and activate CI |
| `acceptance POST /accept` | Post-deploy smoke check |
| `remediation POST /remediate` | Automated repair |
| `infra POST /teardown` | Clean up per-app resources on deletion |
| Gitea HTTP API | Create orgs, issues |
| Loki HTTP API | Proxy log queries for portal |
| Telegram Bot API | Send push notifications (via bot token) |

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Agent returns error during pipeline | `run_build()` sets `apps.status = failed`; logs step to `agent_runs`; moves board card to `failed`; does not retry (retries are per-agent) |
| Reviewer retry limit exceeded | Build aborted; status set to `failed` with `error_detail` explaining which standards were not met |
| Acceptance failure | Remediation agent called; if remediation exhausted, status set to `failed` |
| Database write failure | Unhandled exception; FastAPI returns 500; pipeline task dies; app left in intermediate status (operator must check portal) |
| JWT expired | Returns 401; portal redirects to sign-in |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | — | asyncpg DSN |
| `JWT_SECRET` | — | Secret for signing JWTs |
| `GITEA_URL` | — | Internal Gitea base URL |
| `GITEA_ADMIN_USER` / `GITEA_ADMIN_PASS` | — | Gitea API credentials |
| `TELEGRAM_BOT_TOKEN` | — | For outbound Telegram push notifications |
| `LOKI_URL` | `http://loki:3100` | Loki base URL for log proxying |
| `INVITE_CODE` | unset | If set, required during registration |

## Non-functional constraints

- `run_build()` uses bare `asyncio.create_task()` — fire-and-forget with no retry or concurrency limit. ADR-0001 proposes replacing this with Temporal.
- Each pipeline step is called sequentially in-process; a slow agent blocks the background task but does not block the HTTP server.
- No rate limiting on chat or build endpoints; a single user can saturate Ollama by submitting rapid build requests.

## Known limitations

- `run_build()` uses bare `asyncio.create_task()` — fire-and-forget with no retry or concurrency limit. ADR-0001 proposes replacing this with Temporal.
- Woodpecker activation (direct Postgres insert) couples the publisher to Woodpecker's internal schema; this is delegated to the publisher but remains a coupling point.
- Log proxying from Loki adds latency; large log tails may time out.
