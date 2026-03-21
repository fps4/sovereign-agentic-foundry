---
title: "Component design: Telegram bot"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: telegram-bot
related:
  - docs/architecture/overview.md
  - docs/architecture/components/gateway.md
  - docs/architecture/decisions/0002-kanban-board-integration.md
---

## Purpose

The Telegram bot is the platform's secondary user-facing interface. It translates Telegram messages and commands into gateway API calls and formats responses back to the operator. Since the web portal was adopted as the primary interface (ADR-0002), the bot's role is notifications and quick mobile commands; full control-plane operations (Kanban, build history, logs) are handled by the portal.

The bot owns no business logic — all routing, state, and build decisions happen in the gateway and agents.

## Responsibilities

**Owns:**
- Telegram long-polling and message dispatch
- Command routing (`/start`, `/build`, `/apps`, `/fix`, `/delete`, `/help`)
- aiogram FSM state for multi-step Telegram flows
- Formatting gateway responses into user-friendly Telegram messages
- Receiving and forwarding push notifications from the gateway (build complete, app failed, remediation triggered)

**Does not own:**
- User registration logic (delegated to gateway)
- Intent classification (delegated to gateway and intake agent)
- App state (read from gateway)
- Conversation history (owned by gateway / intake agent)
- Kanban board management (owned by portal)
- Build history and log viewing (owned by portal)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | aiogram bot instance, dispatcher, all command and message handlers |
| aiogram FSM | `RegistrationStates`, `BuildStates` — multi-step Telegram interaction flows |
| Postgres FSM storage | aiogram state persisted to Postgres; survives bot restarts |
| Gateway HTTP client | All gateway calls via `httpx.AsyncClient` |

## Key flows

### Free-text message

1. Operator sends a plain message
2. Handler calls `POST /chat` on gateway with `{user_id, message}`
3. Returns `reply` text to operator
4. If `build_triggered: true` in the response, sends a "build started" notification

### `/build` command

1. Bot enters `BuildStates.waiting_description`
2. Operator provides description
3. Bot calls `POST /chat` on gateway (same path as free-text)
4. Gateway routes through intake agent; bot returns reply

### `/apps` command

1. Bot calls `GET /apps?user_id={id}` on gateway
2. Formats app list with status indicators, URLs, and health state
3. Includes a link to the portal for full details

### `/delete` command

1. Bot presents app list, enters `BuildStates.waiting_delete_confirm`
2. Operator confirms; bot calls `POST /delete-app` on gateway

### `/fix` command

1. Bot presents app list, enters state waiting for issue description
2. Operator describes the issue
3. Bot calls `POST /apps/{name}/report-issue` on gateway with the description

### Push notification received

1. Gateway calls the bot's internal notification endpoint with `{user_id, message, app_name}`
2. Bot sends a formatted Telegram message to the operator

## Data owned

**Writes:**
- Postgres (aiogram FSM storage) — `aiogram_fsm` state table; scoped to bot user sessions

**Reads:**
- Postgres (aiogram FSM storage) — resumes multi-step flows across restarts

The bot does not read or write platform tables (`users`, `apps`, `messages`). All platform data access goes through the gateway.

## External interfaces

### Calls

| Target | Purpose |
|--------|---------|
| `gateway POST /chat` | All user messages and `/build` |
| `gateway POST /register` | `/start` registration flow |
| `gateway GET /apps` | `/apps` command |
| `gateway POST /delete-app` | `/delete` command |
| `gateway POST /apps/{name}/report-issue` | `/fix` command |
| Telegram Bot API (polling) | Receive updates, send messages |

### No HTTP server

The bot uses Telegram long-polling and exposes no HTTP port.

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Gateway unreachable | Returns a user-visible error: "Service temporarily unavailable, try again shortly" |
| Telegram API timeout | aiogram retries automatically; user may not receive reply for up to 30 s |
| Unknown command | Returns help text listing available commands |
| FSM state corruption | State is reset on next `/start` or command; operator is notified |
| Operator not registered | Returns registration prompt on any command other than `/start` |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `TELEGRAM_BOT_TOKEN` | — | From @BotFather |
| `GATEWAY_URL` | `http://gateway:8000` | Gateway base URL |
| `DATABASE_URL` | — | asyncpg DSN for aiogram FSM state storage |
| `INVITE_CODE` | unset | Passed to gateway during registration if set |

## Non-functional constraints

- Processes one Telegram update at a time per polling cycle — high message volume may cause noticeable reply latency.
- FSM state is per-user; concurrent sessions from the same Telegram account may collide.
- Not the critical path for build pipeline operations; delays here do not affect build throughput.

## Known limitations

- Long-polling means the bot processes one update at a time per polling cycle; high message volume may cause noticeable latency.
- aiogram FSM state is per-user — if two Telegram clients message the same account simultaneously, state may collide.
- Operators cannot view Kanban boards, build history, or log tails via Telegram; the portal is required for those.
