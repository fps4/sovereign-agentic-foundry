---
title: Bots context
related:
  - docs/architecture/overview.md
  - docs/architecture/components/telegram-bot.md
  - docs/architecture/components/gateway.md
  - docs/architecture/decisions/0002-kanban-board-integration.md
---

## What this directory contains

User-facing bot services. Currently contains only the Telegram bot. Since ADR-0002, the Telegram bot is the **secondary** interface; the web portal is primary.

## Directory map

| Path | Purpose | Design doc |
|------|---------|------------|
| `telegram/` | Telegram bot — push notifications and quick commands for mobile operators | `docs/architecture/components/telegram-bot.md` |

## Key entry point

- `telegram/main.py` — aiogram bot instance, all command handlers, FSM state definitions

## Conventions

- The bot uses Telegram long-polling (`dp.start_polling(bot)`); it exposes no HTTP port
- All gateway calls use `httpx.AsyncClient`; the base URL is `GATEWAY_URL` (not `ORCHESTRATOR_URL` — update env var name on next redeploy)
- aiogram FSM state is persisted to Postgres using aiogram's built-in storage adapter

## Gotchas

- The env var `ORCHESTRATOR_URL` in the existing code still points at the gateway — it should be renamed `GATEWAY_URL` in a future cleanup
- aiogram FSM state is per-user; concurrent messages from two Telegram clients on the same account may cause state collisions
- The bot does not have access to Kanban board state; operators who want board visibility must use the portal
