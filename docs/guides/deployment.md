---
title: Deployment guide
status: current
last_updated: 2026-03-21
owners: [platform-team]
related:
  - docs/guides/setup.md
  - docs/architecture/overview.md
---

## Purpose

Day-to-day operations for a running stack: updating services, viewing logs, and managing the stack lifecycle.

## Running the stack

```bash
# Start all services (remote host)
DOCKER_HOST=ssh://ds1 docker compose up -d

# Stop all services
DOCKER_HOST=ssh://ds1 docker compose down

# Check service status
DOCKER_HOST=ssh://ds1 docker compose ps
```

## Updating a service

After changing code in an agent or the orchestrator:

```bash
DOCKER_HOST=ssh://ds1 docker compose build <service>
DOCKER_HOST=ssh://ds1 docker compose up -d <service>
```

Example — rebuild and restart the coder agent:

```bash
DOCKER_HOST=ssh://ds1 docker compose build coder && DOCKER_HOST=ssh://ds1 docker compose up -d coder
```

## Logs

```bash
# All services
DOCKER_HOST=ssh://ds1 docker compose logs -f

# Single service
DOCKER_HOST=ssh://ds1 docker compose logs -f orchestrator

# Platform services useful for debugging builds
DOCKER_HOST=ssh://ds1 docker compose logs -f coder tester orchestrator
```

Structured JSON logs from all platform services are also available in Grafana at `http://<DS1_HOST>:3001` via the Loki data source.

## End-to-end test

Validates the full pipeline: register → design → code → test → deploy.

```bash
ORCHESTRATOR_URL=http://<DS1_HOST>/api python scripts/e2e_test.py

# Skip health checks if agents are already confirmed up
SKIP_HEALTH=1 ORCHESTRATOR_URL=http://<DS1_HOST>/api python scripts/e2e_test.py
```

## Changing the LLM model

1. Pull the new model on the Docker host:
   ```bash
   DOCKER_HOST=ssh://ds1 ./scripts/pull_models.sh <model-name>
   ```
2. Update `OLLAMA_MODEL` in `.env`
3. Restart affected services:
   ```bash
   DOCKER_HOST=ssh://ds1 docker compose up -d orchestrator designer coder tester monitor
   ```

Recommended: `llama3.1:8b` for conversation and classification; `qwen2.5-coder:32b` for the coder and tester agents when VRAM allows.

## Deployed app containers

Apps deployed by Woodpecker CI run as standalone Docker containers on the `platform_platform` network. They are not managed by `docker compose` — use `docker` commands on the host directly:

```bash
# List deployed app containers
DOCKER_HOST=ssh://ds1 docker ps --filter "label=traefik.enable=true"

# Stop a specific app
DOCKER_HOST=ssh://ds1 docker stop <app-name>
```

Archiving an app via `/delete` in Telegram stops the container and sets `apps.archived = true` in Postgres. The Gitea repo is preserved.

## Observability

| Tool | URL | Notes |
|------|-----|-------|
| Grafana | `http://<DS1_HOST>:3001` | Loki logs + Postgres query panel |
| Woodpecker | `http://<DS1_HOST>:8080` | CI pipeline runs per app |
| Gitea | `http://<DS1_HOST>:3000` | App repos and issues |
| Agent run log | `GET /runs` on orchestrator | Step-level audit trail |
