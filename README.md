# Sovereign Agentic Foundry

An agentic platform that builds applications on sovereign (self-hosted) infrastructure. Users describe what they want via Telegram; an orchestration layer interprets intent and agents plan and execute the build.

The platform supports five app types out of the box:

| Type | What it builds |
|---|---|
| **Form** | Collect or manage structured data — registrations, requests, records |
| **Dashboard** | Display and visualise data — metrics, lists, live status |
| **Workflow** | Move tasks through stages with assignments and notifications |
| **Connector** | Headless backend linking two systems, no UI |
| **Assistant** | RAG-powered chat and Q&A over your documents |

See [docs/poc.md](docs/poc.md) for the full design, [docs/agent-pipeline.md](docs/agent-pipeline.md) for the agent pipeline, and [docs/app-types.md](docs/app-types.md) for type definitions and coverage.

## Prerequisites

- Docker (local or remote)
- A Telegram bot token — create one via [@BotFather](https://t.me/BotFather)

## Setup

**1. Configure environment**

```bash
cp .env.example .env
```

Edit `.env` and set:
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `DS1_HOST` — hostname or IP of your Docker host
- `APP_DOMAIN` — public domain for live app URLs (e.g. `apps.yourdomain.com`); route `*.APP_DOMAIN → ds1:80` via Cloudflare Tunnel or a wildcard DNS record
- `GITEA_ADMIN_PASS` — password for the Gitea admin account (choose any)

**2. Pull the Ollama model**

```bash
DOCKER_HOST=ssh://ds1 ./scripts/pull_models.sh
```

Default is `llama3.1:8b`. To use a different model:

```bash
DOCKER_HOST=ssh://ds1 ./scripts/pull_models.sh qwen2.5-coder:7b
```

**3. Start the stack**

```bash
DOCKER_HOST=ssh://ds1 docker compose up -d
```

The `gitea-init` service runs automatically on first start and creates the Gitea admin user using `GITEA_ADMIN_USER` / `GITEA_ADMIN_PASS` / `GITEA_ADMIN_EMAIL` from `.env`. It exits after the user is created; on subsequent restarts it detects the user already exists and skips.

**4. One-time: connect Woodpecker to Gitea**

Woodpecker authenticates via Gitea OAuth2. This requires creating an OAuth2 app in Gitea once:

1. Open Gitea at `http://<DS1_HOST>:3000` and log in (`GITEA_ADMIN_USER` / `GITEA_ADMIN_PASS`)
2. Go to **User menu → Settings → Applications → OAuth2 Applications**
3. Fill in:
   - **Application name**: `woodpecker`
   - **Redirect URI**: `http://<DS1_HOST>:8080/authorize`
4. Click **Create Application** — Gitea shows the Client ID and Client Secret **once**
5. Add both to `.env`:
   ```
   WOODPECKER_GITEA_CLIENT=<client-id>
   WOODPECKER_GITEA_SECRET=<client-secret>
   ```
6. Restart Woodpecker:
   ```bash
   DOCKER_HOST=ssh://ds1 docker compose up -d woodpecker-server woodpecker-agent
   ```

Open `http://<DS1_HOST>:8080` — you'll be redirected to Gitea to authorise. Log in as `GITEA_ADMIN_USER` and the Woodpecker dashboard loads.

> If you lose the secret, delete the OAuth2 app in Gitea and create a new one.
> The `platform` user is pre-configured as Woodpecker admin via `WOODPECKER_ADMIN` — no open registration needed.

**5. Verify**

```bash
DOCKER_HOST=ssh://ds1 docker compose ps
```

All services should show `healthy` or `Up`.

Open Telegram, find your bot, and send `/start`. If `INVITE_CODE` is set, enter it when prompted — you'll be registered immediately. Once in, describe what you want to build:

> *build me a REST API for managing users in Python*

The bot classifies intent, scaffolds the project, pushes it to your private Gitea org, and replies with the live app URL (`http://{app-name}.APP_DOMAIN`). Woodpecker CI builds and deploys the container, attaching Traefik labels so it becomes publicly accessible immediately.

---

## Services

| Service | Port | Description |
|---|---|---|
| `traefik` | 80 | Reverse proxy — routes `APP_DOMAIN` traffic to the orchestrator and all deployed apps |
| `postgres` | — | Database for user accounts, app registry, and Woodpecker CI state |
| `ollama` | — | Local LLM inference (intent classification, code scaffolding, log summarisation) |
| `gitea` | 3000 | Self-hosted Git — one private org per user, one repo per app |
| `gitea-init` | — | One-shot init container: creates the Gitea admin user on first start |
| `woodpecker-server` | 8080 | CI server and web UI |
| `woodpecker-agent` | — | CI runner — builds Docker images, deploys containers with Traefik labels |
| `coder` | — | Coder agent: LLM scaffold → file generation → Gitea commit |
| `monitor` | — | Log monitor agent: polls app containers, files Gitea issues, notifies owner via Telegram |
| `orchestrator` | — | FastAPI + LangGraph: intent classification, chat, user registration, app registry |
| `telegram-bot` | — | Telegram polling bot — the primary user interface |

## Useful commands

```bash
# All logs
DOCKER_HOST=ssh://ds1 docker compose logs -f

# Single service
DOCKER_HOST=ssh://ds1 docker compose logs -f orchestrator

# Health check (via Traefik)
curl http://<DS1_HOST>/health

# Stop everything
DOCKER_HOST=ssh://ds1 docker compose down
```

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `DS1_HOST` | Yes | `localhost` | Hostname/IP of the Docker host (used for Gitea/Woodpecker internal URLs) |
| `APP_DOMAIN` | Yes | `localhost` | Public domain for live app URLs — apps are served at `{app-name}.APP_DOMAIN`; route `*.APP_DOMAIN → ds1:80` via Cloudflare Tunnel or wildcard DNS |
| `POSTGRES_PASSWORD` | No | `changeme` | Postgres password |
| `OLLAMA_MODEL` | No | `llama3.1:8b` | Model used by orchestrator and coder |
| `GITEA_ADMIN_USER` | No | `platform` | Gitea admin username |
| `GITEA_ADMIN_PASS` | Yes | — | Gitea admin password (auto-creates user on first start); also used for all Gitea API calls in the registration flow |
| `GITEA_ADMIN_EMAIL` | No | `admin@platform.local` | Gitea admin email |
| `WOODPECKER_GITEA_CLIENT` | Step 4 | — | Gitea OAuth2 client ID |
| `WOODPECKER_GITEA_SECRET` | Step 4 | — | Gitea OAuth2 client secret |
| `WOODPECKER_AGENT_SECRET` | No | `changeme` | Shared secret between Woodpecker server and agent |
| `INVITE_CODE` | No | — | If set, users must supply this code to register. Leave unset to allow open registration |
| `MONITOR_POLL_INTERVAL` | No | `60` | Seconds between log checks |
| `MONITOR_COOLDOWN` | No | `600` | Seconds before re-checking the same container after an alert |
| `MONITOR_LOG_LINES` | No | `50` | Log lines sampled per check |

## Build phases

- **Phase 1** ✅ Conversation loop: Telegram → orchestrator → Ollama → reply
- **Phase 2** ✅ Architecture standards: YAML rules injected into every LLM prompt
- **Phase 3** ✅ Coder agent: scaffolds repos, commits to Gitea, triggers Woodpecker CI

## Later for an extended POC

- **Phase 4** Infra + review agents: OpenTofu provisioning, Semgrep/Trivy gate
- **Phase 5** Observability + web hub: Prometheus, Grafana, Next.js dashboard
