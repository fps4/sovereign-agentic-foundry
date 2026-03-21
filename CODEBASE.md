# Codebase overview

Sovereign Agentic Foundry is a self-hosted platform that turns a natural-language Telegram message into a running, tested, deployed web application. The full pipeline — spec clarification, code scaffolding, CI, and deployment — runs automatically on your own infrastructure with no external API keys.

## Directory map

| Path | Purpose |
|------|---------|
| `orchestrator/` | FastAPI API gateway + LangGraph intent routing; dispatches build pipeline |
| `agents/designer/` | Multi-turn spec clarification agent (FastAPI, port 8003) |
| `agents/coder/` | LLM scaffold, Gitea commit, CI config generation (FastAPI, port 8001) |
| `agents/tester/` | pytest generation, invoked as a Woodpecker CI step (FastAPI, port 8002) |
| `agents/monitor/` | Continuous container log and health monitor; no HTTP port |
| `bots/telegram/` | Telegram polling bot — the user-facing interface (aiogram) |
| `standards/` | YAML rules (naming, security, patterns) injected into every LLM prompt |
| `infra/` | Traefik, Loki, Promtail, Grafana configuration files |
| `scripts/` | `e2e_test.py` end-to-end test suite; `pull_models.sh` Ollama model downloader |
| `docs/` | Product, architecture, API, and operational guides |

## Entry points

- **User traffic**: Telegram bot (`bots/telegram/main.py`) → orchestrator `POST /chat`
- **Orchestrator HTTP**: `orchestrator/main.py` — all platform API endpoints
- **Build dispatch**: `orchestrator/workflow.py` `run_build()` → coder agent
- **CI test step**: `agents/tester/main.py` `POST /generate` (called by Woodpecker)
- **Full stack**: `docker-compose.yml` — single command brings up all 14 services

## Naming notes

- "app" in the domain = a generated project; maps to the `apps` table and a Gitea repo named `app-{name}`
- "design mode" = the FSM state where the designer agent is actively clarifying a spec; tracked as `users.design_mode` in Postgres
- "standards" = the YAML rules in `standards/`; injected verbatim into LLM system prompts, not a separate service
- `platform_platform` = the Docker bridge network shared by all services and every deployed app container
- Woodpecker repos are activated via **direct Postgres insert + HMAC webhook**, not through the Woodpecker UI or API
