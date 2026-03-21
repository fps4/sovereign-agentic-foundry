---
title: Architecture overview
status: current
last_updated: 2026-03-21
owners: [platform-team]
related:
  - docs/product/vision.md
  - docs/architecture/data-model.md
  - docs/architecture/components/generated-app.md
  - docs/architecture/decisions/0001-workflow-orchestration.md
  - docs/architecture/decisions/0002-kanban-board-integration.md
  - docs/architecture/decisions/0006-per-agent-llm-provider-configuration.md
---

## Purpose

This document describes the system context (C4 L1) and container map (C4 L2) for Sovereign Agentic Foundry. It covers how all services fit together and how a user request flows from chat to a live deployed application.

## Two-tier model

The architecture is split into two distinct tiers with different lifecycles and ownership models.

**Platform tier — always running, managed by the platform administrator.**
The gateway, agents, portal, Telegram bot, and all platform infrastructure (Postgres, Gitea, Woodpecker, Traefik, Ollama, Loki, Grafana). These containers start once and run indefinitely. The platform administrator is responsible for their deployment, configuration, and updates.

**Tenant tier — dynamically created, scoped to an operator's tenant, managed by the platform.**
Generated application containers — one or more per operator request — produced by the build pipeline and deployed by Woodpecker CI. Each generated app has its own Gitea repository, its own CI pipeline, and optionally its own dedicated Postgres database or pgvector container. Apps are owned by a **tenant** (not directly by a user), enabling future team sharing without schema changes. In v1, each operator has exactly one tenant (`tenant_type = 'single_user'`), so the experience is identical to direct user ownership.

The platform tier builds and governs the tenant tier. The tenant tier never modifies the platform tier. See `docs/architecture/components/generated-app.md` for the full generated app runtime model and `docs/architecture/decisions/0003-tenant-model.md` for the tenant design decision.

## System context (C4 L1)

One external actor: the **operator**. The platform exposes two interaction channels:

- **Web portal** (primary) — a browser-based control plane at `portal.APP_DOMAIN`. Chat, apps dashboard, per-app Kanban board, build history, log viewer.
- **Telegram bot** (secondary) — push notifications and quick commands for mobile operators.

Operators use either channel or both. All infrastructure (Git, CI, LLM inference, database, reverse proxy) runs self-hosted on a single Docker host. No external API keys are required.

The operator also uses the generated applications directly — each deployed app is accessible at `{name}.APP_DOMAIN`.

## Container map (C4 L2)

### Build pipeline

```
Portal (chat) ─┐
               ├──→ Gateway → Intake Agent
Telegram Bot ──┘                  ↓ (spec locked)
                              Gateway ─────────────────────────→ board_cards (Postgres)
                                  ↓ (if app type needs               ↑ (card created / moved /
                              Infra Agent → provisions DB / store    ↑  commented at each stage)
                                  ↓                                  ↑
                              Planner Agent → build plan ─────────────
                                  ↓
                              Builder Agent → generated code files ───
                                  ↓                                  ↑
                              UI Designer Agent → frontend templates ──
                                  ↓                                  ↑
                              Reviewer Agent → standards gate ─────────
                                  ↓ (pass)
                              Publisher → Gitea commit
                                              ↓ webhook
                                         Woodpecker CI
                                              ↓
                                         Test Writer Agent (CI step)
                                              ↓
                                         pytest → docker build → deploy
                                              ↓
                                      Acceptance Agent → live smoke check
                                              ↓ pass
                                   ┌─ App live at {name}.APP_DOMAIN ──→ board_cards (Done)
                                   │          ↓ fail
                                   │  Remediation Agent → patch → redeploy → board_cards (Failed / retry)
                                   │
                                   └─ [Application tier: see below]
```

### Monitoring path (continuous, independent)

```
Watchdog → Docker socket (polls app containers) → Gateway /report-issue
                                                        ↓ (breaking error)
                                                  board_cards ← card created in "In Progress"
                                                        ↓
                                                  Remediation Agent → patch → redeploy
                                                        ↓ resolved           ↓ exhausted
                                                  board_cards (Done)    board_cards (Failed)
                                                                              ↓
                                                                 Gitea Issue + Telegram/Portal notification
```

### Tenant tier (generated app runtime)

```
                    ┌─────── Generated Application ──────────────────────────────────┐
                    │                                                                  │
  Traefik ─────────→  App Container        GET /health ←── Acceptance Agent          │
  {name}.APP_DOMAIN │  (FastAPI/Express)   GET /ready                                 │
                    │       │                                                          │
                    │       │ SQL (optional: connector, assistant)                     │
                    │       ↓                                                          │
                    │  Per-app Postgres DB  ←── Infra Agent (provision/teardown)      │
                    │  (in shared Postgres)                                            │
                    │       │ (optional: assistant only)                               │
                    │       ↓                                                          │
                    │  pgvector Container   ←── Infra Agent (provision/teardown)      │
                    └──────────────────────────────────────────────────────────────────┘
                              ↑
                         Watchdog (Docker socket, continuous log polling)
                         Promtail (Docker log driver, passive collection)
```

### Platform tier containers

#### Agents (LLM-driven)

| Container | Technology | Role |
|-----------|-----------|------|
| `intake` | Python, FastAPI | Multi-turn clarification conversation. Converges on a locked spec and hands off to the gateway. |
| `planner` | Python, FastAPI | Takes a locked spec and produces a build plan: file list, patterns, stack decisions, resource requirements. |
| `builder` | Python, FastAPI | Executes the build plan; generates all application code files. No architectural decisions. |
| `ui-designer` | Python, FastAPI | Generates styled, accessible frontend templates from the spec and route manifest. |
| `reviewer` | Python, FastAPI | Checks generated files against platform standards before commit. Returns pass or fix instructions. |
| `test-writer` | Python, FastAPI | Generates pytest files from application source. Invoked as a Woodpecker CI step. |
| `remediation` | Python, FastAPI | Analyses failures from the acceptance agent or watchdog; drives a targeted patch rebuild; escalates when retries are exhausted. |

#### Services (deterministic, no LLM)

| Container | Technology | Role |
|-----------|-----------|------|
| `portal` | Next.js 15, MUI Minimal v7 | Primary web interface. Chat, apps dashboard, per-app Kanban board, build history, log viewer. Calls gateway API only. |
| `telegram-bot` | Python, aiogram | Secondary mobile interface. Push notifications, quick commands. Routes messages to gateway. |
| `gateway` | Python, FastAPI | API facade. User registration, app registry, build dispatch, board card writes, agent run logging. No LLM. |
| `publisher` | Python, FastAPI | Commits generated files to Gitea, creates repos, activates Woodpecker pipelines via HMAC webhook. |
| `infra` | Python, FastAPI | Provisions per-app external resources (Postgres DB, pgvector). Injects secrets. Handles teardown on app deletion. |
| `acceptance` | Python, FastAPI | Post-deploy smoke check: exercises live app routes against the spec. Triggers remediation on failure. |
| `watchdog` | Python (no HTTP) | Polls all running app containers via Docker socket. Reports errors to gateway. |

#### Platform infrastructure

| Container | Technology | Role |
|-----------|-----------|------|
| `traefik` | Traefik v3 | Reverse proxy. Routes `*.APP_DOMAIN` to both platform services and deployed app containers via dynamic Docker labels. |
| `postgres` | PostgreSQL 16 | Shared database for platform state (`platform` DB), Woodpecker CI state (`woodpecker` DB), and per-app databases (each in its own named DB). |
| `ollama` | Ollama | Local LLM inference. Default provider for all agents (`llama3.1:8b`). Each agent can be independently redirected to OpenAI or Anthropic via per-agent env vars — see `docs/architecture/decisions/0006-per-agent-llm-provider-configuration.md`. |
| `gitea` | Gitea | Self-hosted Git. One private org per user. One repo per app. |
| `woodpecker-server` | Woodpecker CI v3 | CI server and web UI. Manages pipeline execution. |
| `woodpecker-agent` | Woodpecker CI v3 | CI runner. Executes pipeline steps in Docker containers on the platform network. |
| `loki` + `promtail` | Grafana Loki | Log aggregation. Promtail collects Docker container logs (both platform and app tier); Loki stores them. |
| `grafana` | Grafana | Observability dashboard. Loki and Postgres data sources. |

### Network

All platform containers and all generated app containers share a single Docker bridge network: `platform_platform`. This enables:
- Traefik routing to app containers via Docker label discovery
- CI steps' direct hostname access to platform services (e.g. `http://test-writer:8002`)
- App containers' direct access to their provisioned resources (e.g. `{app-name}-pgvector:5432`)

There is no network-level isolation between operators' app containers. All containers on `platform_platform` can reach each other by container name.

### Tenancy

Each registered user is assigned a **tenant** (see `docs/architecture/decisions/0003-tenant-model.md`). In v1 every tenant is `single_user` and is created atomically with the user row at registration. Each tenant receives a private Gitea organisation named `user-{telegram_id}`. All Gitea operations and all app ownership queries are scoped to the tenant, not the individual user.

Generated app containers carry a `platform.tenant={tenant_id}` Docker label, which the watchdog uses to scope container sweeps to the correct tenant. The label was previously `platform.owner=user-{telegram_id}`; the rename aligns the runtime marker with the tenant model.

**Future:** adding a second user to a tenant requires only a `tenant_memberships` join table — no changes to `apps`, `board_cards`, or any agent code.

### Template library

The builder and ui-designer use a template library of base scaffolds rather than generating all code from a blank slate. Templates guarantee the mandatory platform contract (health endpoints, Dockerfile security, CI structure) without LLM involvement. The LLM adds only app-specific code on top.

- **API templates:** `fastapi-base` (Python 3.12 / FastAPI) and `express-base` (Node 22 / Express). The planner selects the stack based on spec analysis; FastAPI is the default.
- **Frontend template:** `mui-minimal` (Next.js 15 / MUI Minimal v7). All app types with a browser UI use this template. The ui-designer adapts it for the app's specific pages, forms, and components.

Templates are versioned, baked into the builder and ui-designer Docker images, and mounted read-only at `/templates`. See `docs/architecture/components/template-library.md` and `docs/architecture/decisions/0005-template-library.md`.

### Standards injection

`standards/` contains YAML files (`naming.yaml`, `security.yaml`, `patterns.yaml`) loaded at agent startup and appended to every LLM system prompt. This is the mechanism that makes generated apps architecturally consistent across runs. The same standards define the mandatory runtime contract that every generated app must satisfy (health endpoints, logging format, Dockerfile rules).

## Observability standards

All platform HTTP services and agents follow the reliability contracts defined in `standards/reliability.yaml` (sourced from the agentic-standards package):

- **SLO targets:** 99.9% availability; p95 latency within tier budget (FAST < 3s, STANDARD < 30s, STRONG < 60s)
- **Golden signals:** latency (success and error separately), traffic (requests/min), errors (by type), saturation (CPU/memory; alert at 80%)
- **Burn rate alerts:** critical at 14.4× error rate over 5m:1h window; warning at 6× over 30m:6h window
- **Error budget policy:** if more than 50% of the monthly error budget is consumed with more than 50% of the window remaining, non-critical work is halted
- **Agent health contract:** `GET /health` must respond in < 2s; callers retry degraded agents 3 times with exponential backoff before escalating
- **LLM failure policy:** LLM timeout and malformed JSON output are retryable errors; after `max_retries` the agent emits a `RunEvent` with `status="error"` and the gateway surfaces the failure to the admin
