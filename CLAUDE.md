# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

Sovereign Agentic Foundry is a self-hosted AI platform that turns natural-language Telegram messages into deployed web apps. A user describes what they want; the system designs, codes, tests, and deploys it fully automatically — no human approval gates.

The full stack runs via a single `docker-compose.yml` and supports remote Docker hosts via SSH.

## Development Commands

```bash
# Start the full stack (locally or via SSH remote host)
docker compose up -d
DOCKER_HOST=ssh://ds1 docker compose up -d

# Pull Ollama LLM models on first run
bash scripts/pull_models.sh

# Run end-to-end tests (requires running stack)
ORCHESTRATOR_URL=http://localhost:8000 python scripts/e2e_test.py

# View logs for a specific service
docker compose logs -f designer
docker compose logs -f orchestrator

# Rebuild a single service after code changes
docker compose build coder && docker compose up -d coder
```

## Architecture Overview

### Request Flow

All user messages enter via the **Telegram Bot** → **Orchestrator** → **Designer Agent** (the single front door). The designer runs a multi-turn clarification conversation until the spec is unambiguous, then triggers a build:

```
Telegram → Orchestrator /chat → Designer (multi-turn FSM) → confirm build
                                                              → Coder Agent (scaffold + commit to Gitea)
                                                                → Woodpecker CI (generate-tests → test → docker-build → deploy)
                                                                  → App live at http://{app-name}.APP_DOMAIN
```

### Services & Ports

| Service | Port | Role |
|---|---|---|
| Orchestrator | 8000 | API gateway, LangGraph workflow, user registration |
| Designer | 8003 | Multi-turn conversation, spec production |
| Coder | 8001 | LLM-based project scaffolding, Gitea commits |
| Tester | 8002 | pytest generation (invoked by Woodpecker CI step) |
| Monitor | — | Background Docker log polling, creates Gitea issues |
| Telegram Bot | — | User-facing interface (aiogram polling) |
| Traefik | 80 | Reverse proxy routing via Docker labels |
| PostgreSQL | 5432 | Shared DB for users, apps, messages, agent_runs |
| Ollama | 11434 | Local LLM inference (no external API keys) |
| Gitea | 3000 | Self-hosted Git, one private org per user |
| Woodpecker | 8080 | CI/CD, activated per repo via direct DB + HMAC webhook |

### Key Architectural Patterns

**Stateful FSM in Postgres**: Conversation state persists across restarts. Designer and Telegram bot store FSM state in PostgreSQL via asyncpg.

**Single Front Door**: Orchestrator's `/chat` endpoint always delegates to the Designer agent. The Designer decides whether to keep clarifying or trigger a build.

**Tenancy**: One private Gitea org per user (`user-{telegram_id}`). All operations are scoped to the user's org.

**Standards-as-Code**: `/standards/*.yaml` files (naming, security, patterns) are mounted read-only into agents and injected into every LLM prompt for consistent generated architecture.

**Webhook-Triggered CI**: After coder pushes to Gitea, a HMAC-signed webhook fires Woodpecker. The CI pipeline: `generate-tests` (calls tester agent) → `test` (pytest) → `docker-build` → `deploy` (docker run with Traefik labels).

**Monitor Deduplication**: The monitor agent hashes each unique error; it only creates a Gitea issue and sends a Telegram alert once per unique error.

**Local LLM with Typed Fallbacks**: Coder uses Ollama JSON mode. If parsing fails, it falls back to hardcoded scaffold templates (`agents/coder/templates/`).

**Local Testing Before Commit**: Coder runs tests locally (`agents/coder/local_test.py`) before pushing scaffolded code to Gitea.

### Five App Types

The platform scaffolds five canonical app types: `form` (FastAPI+SQLite CRUD), `dashboard` (read-only visualization), `workflow` (multi-stage task tracking), `connector` (headless backend integration), `assistant` (RAG chat over documents).

### Database Schema

Key tables in PostgreSQL: `users`, `apps` (soft-deleted via `archived` flag), `messages` (conversation history), `agent_runs` (audit trail with timing and status).

## Environment Setup

Copy `.env.example` to `.env`. Required variables:

- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `DS1_HOST` — hostname of the target Docker host
- `APP_DOMAIN` — base domain for deployed apps (apps live at `{name}.APP_DOMAIN`)
- `POSTGRES_PASSWORD` — database password
- `GITEA_*` — admin credentials (auto-created on first start)
- `WOODPECKER_*` — OAuth2 app credentials (set up via Gitea admin UI)

One-time manual step: create a Gitea OAuth2 app and set `WOODPECKER_GITEA_CLIENT_*` before first run.

## Code Location Guide

- `orchestrator/main.py` — all HTTP endpoints; `orchestrator/workflow.py` — LangGraph state machine
- `agents/designer/main.py` — conversation FSM, spec production
- `agents/coder/main.py` — build endpoint; `scaffold.py` — LLM generation; `gitea.py` — repo ops
- `agents/tester/main.py` — test generation (called as Woodpecker step)
- `agents/monitor/main.py` — background Docker log polling loop
- `bots/telegram/main.py` — user commands and aiogram FSM handlers
- `standards/` — YAML rules injected into LLM prompts
- `infra/` — Traefik, Loki, Promtail, Grafana configs

## Documentation

- `CODEBASE.md` — repo orientation map and naming notes
- `GLOSSARY.md` — domain term definitions
- `AGENTS.md` — agent permissions and conventions
- `docs/README.md` — full documentation index
- `docs/architecture/components/` — per-service design docs
- `docs/architecture/decisions/` — ADRs
