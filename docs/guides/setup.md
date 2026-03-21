---
title: Setup guide
status: current
last_updated: 2026-03-21
owners: [platform-team]
related:
  - docs/guides/deployment.md
  - docs/architecture/overview.md
---

## Purpose

How to bring up Sovereign Agentic Foundry from scratch on a new Docker host.

## Prerequisites

- Docker installed on the target host
- SSH access to the target host (if remote)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A public domain (or subdomain) with wildcard DNS pointing to the Docker host (`*.APP_DOMAIN → host:80`)

## Steps

### 1. Configure environment

```bash
cp .env.example .env
```

Set the required variables in `.env`:

| Variable | What to set |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather |
| `DS1_HOST` | Hostname or IP of the Docker host |
| `APP_DOMAIN` | Public domain for app URLs (e.g. `apps.example.com`) |
| `GITEA_ADMIN_PASS` | Password for the auto-created Gitea admin account |

### 2. Pull the Ollama model

```bash
DOCKER_HOST=ssh://ds1 ./scripts/pull_models.sh
```

Default model: `llama3.1:8b`. For a stronger code model (requires more VRAM):

```bash
DOCKER_HOST=ssh://ds1 ./scripts/pull_models.sh qwen2.5-coder:32b
```

### 3. Start the stack

```bash
DOCKER_HOST=ssh://ds1 docker compose up -d
```

The `gitea-init` service creates the Gitea admin user on first start using `GITEA_ADMIN_USER` / `GITEA_ADMIN_PASS` / `GITEA_ADMIN_EMAIL`, then exits. On subsequent restarts it detects the user exists and skips.

### 4. Connect Woodpecker to Gitea (one-time)

Woodpecker authenticates via Gitea OAuth2. This step is required once per installation.

1. Open Gitea at `http://<DS1_HOST>:3000` and log in with `GITEA_ADMIN_USER` / `GITEA_ADMIN_PASS`
2. Go to **User menu → Settings → Applications → OAuth2 Applications**
3. Create a new application:
   - **Name**: `woodpecker`
   - **Redirect URI**: `http://<DS1_HOST>:8080/authorize`
4. Copy the **Client ID** and **Client Secret** (shown once)
5. Add to `.env`:
   ```
   WOODPECKER_GITEA_CLIENT=<client-id>
   WOODPECKER_GITEA_SECRET=<client-secret>
   ```
6. Restart Woodpecker:
   ```bash
   DOCKER_HOST=ssh://ds1 docker compose up -d woodpecker-server woodpecker-agent
   ```

Open `http://<DS1_HOST>:8080` and log in with Gitea to confirm Woodpecker is connected.

> If the secret is lost: delete the OAuth2 app in Gitea and repeat from step 2.

### 5. Verify

```bash
DOCKER_HOST=ssh://ds1 docker compose ps
```

All services should show `healthy` or `Up`. Then:

```bash
curl http://<DS1_HOST>/health
```

Open Telegram, find your bot, send `/start`. If `INVITE_CODE` is set in `.env`, enter it when prompted.
