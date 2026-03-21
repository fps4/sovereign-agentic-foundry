---
title: "Component design: Telegram bot"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: telegram-bot
related:
  - docs/architecture/overview.md
  - docs/architecture/components/orchestrator.md
---

## Purpose

The Telegram bot is the sole user-facing interface. It translates Telegram messages and commands into orchestrator API calls and formats responses back to the user. It owns no business logic — all routing, state, and build decisions happen in the orchestrator and agents.

## Responsibilities

**Owns:**
- Telegram polling and message handling
- Command routing (`/start`, `/build`, `/apps`, `/fix`, `/delete`, `/help`)
- aiogram FSM state for multi-step Telegram flows
- Formatting orchestrator responses into user-friendly messages

**Does not own:**
- User registration logic (delegated to orchestrator)
- Intent classification (delegated to orchestrator)
- App state (read from orchestrator)
- Conversation history (owned by orchestrator/designer)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | aiogram bot instance, dispatcher, all command and message handlers |
| aiogram FSM | `RegistrationStates`, `BuildStates` — multi-step Telegram interaction flows |
| Postgres FSM storage | aiogram state persisted to Postgres; survives bot restarts |
| Orchestrator HTTP client | All calls via `httpx.AsyncClient` |

## Key flows

### Free-text message

1. User sends a plain message
2. Handler calls `POST /chat` on orchestrator with `{user_id, message}`
3. Returns `reply` text to user
4. If `build_triggered` is true in the response, sends a "build started" notification

### `/build` command

1. Bot enters `BuildStates.waiting_description`
2. User provides description
3. Bot calls `POST /chat` on orchestrator (same path as free-text)
4. Orchestrator routes through designer; bot returns reply

### `/apps` command

1. Bot calls `GET /apps?user_id={id}` on orchestrator
2. Formats app list with status indicators, URLs, and issue counts

### `/delete` command

1. Bot presents app list, enters `BuildStates.waiting_delete_confirm`
2. User confirms; bot calls `POST /delete-app`

### `/fix` command

1. Bot presents app list, enters state waiting for issue description
2. User describes the issue; bot calls `POST /issue` on orchestrator
3. Orchestrator creates a Gitea issue on the app's repo

## External interfaces

### Calls

| Target | Purpose |
|--------|---------|
| `orchestrator POST /chat` | All user messages and `/build` |
| `orchestrator POST /register` | `/start` registration flow |
| `orchestrator GET /apps` | `/apps` command |
| `orchestrator POST /delete-app` | `/delete` command |
| `orchestrator POST /issue` | `/fix` command |
| Telegram Bot API (polling) | Receive updates, send messages |

### No HTTP server

The bot uses Telegram long-polling and exposes no HTTP port.

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `TELEGRAM_BOT_TOKEN` | — | From @BotFather |
| `ORCHESTRATOR_URL` | `http://orchestrator:8000` | |
| `DATABASE_URL` | — | asyncpg DSN for aiogram FSM state storage |
| `INVITE_CODE` | unset | Passed to orchestrator during registration |

## Known limitations

- Long-polling means the bot processes one update at a time per polling cycle; high message volume may cause noticeable latency.
- aiogram FSM state is per-user — if two Telegram clients message the same account simultaneously, state may collide.
