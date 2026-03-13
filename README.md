# Sovereign Agentic Foundry

An agentic platform that builds applications on sovereign (self-hosted) infrastructure. Users describe what they want via Telegram; an orchestration layer interprets intent and agents plan and execute the build.

See [docs/poc.md](docs/poc.md) for the full design.

## Prerequisites

- Docker (local or remote)
- A Telegram bot token — create one via [@BotFather](https://t.me/BotFather)

## Setup

**1. Configure environment**

```bash
cp .env.example .env
# Set TELEGRAM_BOT_TOKEN in .env
```

**2. Pull the Ollama model**

```bash
# Local Docker host
./scripts/pull_models.sh

# Remote Docker host
DOCKER_HOST=ssh://ds1 ./scripts/pull_models.sh
```

Default model is `llama3.1:8b`. To pull a different model:

```bash
DOCKER_HOST=ssh://ds1 ./scripts/pull_models.sh qwen2.5-coder:7b
```

**3. Start the stack**

```bash
# Local
docker compose up -d

# Remote
DOCKER_HOST=ssh://ds1 docker compose up -d
```

**4. Verify**

```bash
DOCKER_HOST=ssh://ds1 docker compose ps
```

All services should show `healthy` or `Up`. Then open Telegram, find your bot, and send `/start`.

## Services

| Service | Description |
|---|---|
| `traefik` | Reverse proxy, routes HTTP traffic on port 80 |
| `postgres` | Database for workflow state (Phase 2+) |
| `ollama` | Local LLM inference |
| `orchestrator` | FastAPI + LangGraph, handles chat requests |
| `telegram-bot` | Telegram polling bot, relays messages to orchestrator |

## Useful commands

```bash
# Logs
DOCKER_HOST=ssh://ds1 docker compose logs -f

# Logs for a single service
DOCKER_HOST=ssh://ds1 docker compose logs -f orchestrator

# Health check
curl http://<ds1-ip>/health

# Stop
DOCKER_HOST=ssh://ds1 docker compose down
```

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `POSTGRES_PASSWORD` | No | `changeme` | Postgres password |
| `OLLAMA_MODEL` | No | `llama3.1:8b` | Model used by the orchestrator |

## Build phases

- **Phase 1** ✅ Conversation loop: Telegram → orchestrator → Ollama → reply
- **Phase 2** ✅ Architecture standards: YAML rules injected into every LLM prompt
- **Phase 3** Coder agent: scaffolds repos, commits to Gitea, triggers CI
- **Phase 4** Infra + review agents: OpenTofu provisioning, Semgrep/Trivy gate
- **Phase 5** Observability + web hub: Prometheus, Grafana, Next.js dashboard
