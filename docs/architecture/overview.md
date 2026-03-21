---
title: Architecture overview
status: current
last_updated: 2026-03-21
owners: [platform-team]
related:
  - docs/product/vision.md
  - docs/architecture/data-model.md
  - docs/architecture/decisions/0001-workflow-orchestration.md
---

## Purpose

This document describes the system context (C4 L1) and container map (C4 L2) for Sovereign Agentic Foundry. It covers how all services fit together and how a user request flows from Telegram to a live deployed application.

## System context (C4 L1)

One external actor: the **operator** communicates exclusively via Telegram. The platform has no web UI. All infrastructure (Git, CI, LLM inference, database, reverse proxy) is self-hosted on a single Docker host.

No external API keys are required. Ollama provides local LLM inference.

## Container map (C4 L2)

### Request path

```
Telegram → Telegram Bot → Orchestrator → Designer Agent
                                              ↓ (spec complete)
                                         Orchestrator
                                              ↓
                                         Coder Agent → Gitea
                                                          ↓ webhook
                                                     Woodpecker CI
                                                          ↓
                                                     Tester Agent (CI step)
                                                          ↓
                                                     docker build + deploy
                                                          ↓
                                              App live at {name}.APP_DOMAIN
```

### Monitoring path (continuous, independent)

```
Monitor Agent → Docker socket (read logs) → Orchestrator /report-issue
                                                  ↓
                                             Gitea Issue + Telegram notification
```

### Containers

| Container | Technology | Role |
|-----------|-----------|------|
| `telegram-bot` | Python, aiogram | User interface. Routes all messages to orchestrator. Maintains Telegram FSM state in Postgres. |
| `orchestrator` | Python, FastAPI, LangGraph | API gateway. Intent classification, user registration, app registry, build dispatch. |
| `designer` | Python, FastAPI | Multi-turn spec clarification. Converges on a structured spec and hands off to orchestrator. |
| `coder` | Python, FastAPI | Scaffolds project files via LLM, commits to Gitea, generates Woodpecker pipeline config. |
| `tester` | Python, FastAPI | Generates pytest files from source. Invoked as a Woodpecker CI step, not by the orchestrator. |
| `monitor` | Python (no HTTP) | Polls all running app containers via Docker socket. Reports errors as Gitea issues. |
| `traefik` | Traefik v3 | Reverse proxy. Routes `*.APP_DOMAIN` to deployed apps via dynamic Docker labels. |
| `postgres` | PostgreSQL 16 | Shared database for platform state (`platform` DB) and Woodpecker CI state (`woodpecker` DB). |
| `ollama` | Ollama | Local LLM inference for all agents. Default model: `llama3.1:8b`. |
| `gitea` | Gitea | Self-hosted Git. One private org per user. One repo per app. |
| `woodpecker-server` | Woodpecker CI v3 | CI server and web UI. Manages pipeline execution. |
| `woodpecker-agent` | Woodpecker CI v3 | CI runner. Executes pipeline steps in Docker containers on the platform network. |
| `loki` + `promtail` | Grafana Loki | Log aggregation. Promtail collects Docker container logs; Loki stores them. |
| `grafana` | Grafana | Observability dashboard. Loki and Postgres data sources. |

### Network

All containers share a single Docker bridge network: `platform_platform`. Every deployed app container is also attached to this network, enabling Traefik routing and giving CI steps direct hostname access to platform services (e.g. `http://tester:8002`).

### Tenancy

Each registered user receives a private Gitea organisation named `user-{telegram_id}`. All Gitea operations in the orchestrator and coder agent are scoped to that org. Woodpecker repo activation happens via direct Postgres insert and HMAC-signed Gitea webhook — no manual Woodpecker UI interaction is required.

### Standards injection

`standards/` contains YAML files (`naming.yaml`, `security.yaml`, `patterns.yaml`) loaded at agent startup and appended to every LLM system prompt. This is the mechanism that makes generated apps architecturally consistent across runs.
