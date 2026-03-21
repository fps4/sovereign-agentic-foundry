---
title: Gateway (orchestrator) context
related:
  - docs/architecture/overview.md
  - docs/architecture/components/gateway.md
  - docs/architecture/data-model.md
  - docs/architecture/decisions/0001-workflow-orchestration.md
---

## What this module does

The `orchestrator/` directory contains the **gateway** service — the API facade and coordination layer for the platform. It owns user registration, the app registry, build pipeline dispatch, Kanban board card state, and agent run logging. This directory is named `orchestrator` for historical reasons; the canonical name in the architecture is `gateway`.

## Key files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, all HTTP endpoints, lifespan (DB connection pool) |
| `workflow.py` | `run_build()` background task — sequences agents, writes board cards, handles failures |
| `db.py` | asyncpg pool, schema auto-migration, query helpers for all platform tables |
| `standards.py` | Loads standards YAML files at startup; used for any gateway-level standards checks |
| `woodpecker.py` | Woodpecker CI activation helpers (direct Postgres insert + HMAC webhook) |

## Primary request handlers (main.py)

- `POST /chat` — routes to intake agent; triggers build if spec locked
- `POST /auth/login` — JWT issuance for web portal
- `GET /apps` / `POST /delete-app` — app registry
- `GET /apps/{id}/board` / `POST|PATCH /apps/{id}/board/cards` — Kanban board
- `GET /apps/{id}/runs` / `GET /apps/{id}/logs` — portal detail view
- `POST /apps/{name}/report-issue` — watchdog issue intake

## Gotchas

- `run_build()` uses `asyncio.create_task()` — fire-and-forget with no retry or concurrency limit. ADR-0001 proposes replacing this with Temporal.
- Schema auto-migration in `db.py` runs at startup; adding a new column requires a migration entry there, not a separate migration tool.
- The `woodpecker` DB (in the same Postgres instance) is written to directly by `woodpecker.py` — this couples the gateway to Woodpecker's internal schema.
- Board card writes happen inside `run_build()` at each pipeline stage — if the gateway crashes mid-build, some card moves may be missed.
