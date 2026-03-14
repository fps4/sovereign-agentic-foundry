SOVEREIGN AGENTIC FOUNDRY — FEATURES
======================================

A self-hosted platform that builds, tests, deploys, and monitors applications
from natural-language descriptions. All infrastructure runs on your own hardware.


USER INTERFACE
--------------
- Telegram bot as the primary interface — no web sign-up, no account forms
- Invite-code registration (optional); open registration when no code is set
- Persistent FSM state — multi-step flows survive bot restarts
- /start        welcome and help on first contact
- /build        guided build flow with plain-language description
- /apps         list all apps with live status, issue count, and URL
- /fix          report an issue against a specific app (creates a Gitea issue)
- /delete       archive an app — stops the running container, hides from /apps,
                preserves the Gitea repo and history
- /help         context-sensitive help


INTENT CLASSIFICATION
---------------------
- LLM classifies every free-text message as build intent or general chat
- Extracts app name (kebab-case), description, stack, requirements, and app type
- Prompts for clarification when app type is ambiguous (form / dashboard /
  workflow / connector / assistant)
- Falls through to conversational response for non-build messages


DESIGNER AGENT
--------------
- Multi-turn clarification conversation until the spec is unambiguous
- Produces a structured spec (name, description, app type, stack, requirements)
- Hands off automatically — no user confirmation gate after spec is complete
- Design mode persisted in Postgres; survives restarts mid-conversation


APP TYPES
---------
Five built-in scaffolds:

  Form        Collect and manage structured records (POST / GET / PATCH / DELETE)
              SQLite-backed, non-root Docker user, /health endpoint
  Dashboard   Read-only data visualisation with filters and auto-refresh
  Workflow    Multi-stage task tracking with assignments and audit trail
  Connector   Headless backend linking two systems, no UI, stateless by design
  Assistant   RAG-powered chat and Q&A over uploaded documents


CODER AGENT
-----------
- Scaffolds a complete project from a spec: source files, Dockerfile, requirements,
  README, and CI configuration
- LLM-generated scaffold with typed fallback for Python/FastAPI and Node/Express
- Commits all files to a new Gitea repo in the user's private org
- Generates a .woodpecker.yml CI pipeline for every app


TESTER AGENT
------------
- Invoked as a Woodpecker CI step (generate-tests) immediately after commit
- Fetches app source files from Gitea and generates pytest test files via LLM
- Auto-corrects known LLM import mistakes (e.g. wrong TestClient import)
- Falls back to a minimal health-check test if LLM output cannot be parsed
- Test files are written directly into the CI workspace — no extra commit,
  no webhook loop


CI / CD PIPELINE  (Woodpecker)
-------------------------------
- Woodpecker repo activation is automatic on every new build — no manual
  dashboard setup required
- Pipeline steps per app:
    1. generate-tests   call tester agent, write pytest files to workspace
    2. test             pip install deps + pytest
    3. docker-build     build image tagged with repo name
    4. deploy           docker rm -f + docker run with Traefik labels on
                        platform_platform network
- CI containers run on the platform_platform Docker network — agents are
  reachable by service name
- Apps are live at http://{app-name}.APP_DOMAIN immediately after deploy


TENANCY & SECURITY
------------------
- One private Gitea organisation per registered user (user-<telegram_id>)
- All Gitea API operations scoped to the user's org
- Woodpecker repos activated via direct DB insert and HMAC-signed Gitea webhook;
  no shared CI credentials exposed to users
- Architecture standards (naming, patterns, security) injected into every
  LLM prompt via standards/ YAML files
- Non-root container users in all generated Dockerfiles


APP REGISTRY
------------
- Postgres-backed registry tracking every app: status, repo URL, app URL,
  error detail, issue count
- Status lifecycle: queued → provisioning → building → active / failed / degraded
- Soft-delete (archive) preserves history; deleted apps are filtered from /apps


MONITOR AGENT
-------------
- Polls all running platform containers on a configurable interval
- Detects log errors and container health failures
- Deduplicates alerts — each unique error hash is reported once
- Creates a Gitea issue on the app's repo with an LLM-generated plain-English summary
- Updates app status to degraded or failed
- Notifies the app owner via Telegram for breaking issues


OBSERVABILITY
-------------
- JSON-structured logs on every service
- Loki log aggregation
- Promtail log collector (reads Docker container logs)
- Grafana dashboard (Loki data source; admin password configurable)
- Agent run log: every pipeline step written to agent_runs table with timing
  and status — queryable via GET /runs


INFRASTRUCTURE
--------------
- Single docker-compose.yml — one command to start the full stack
- Traefik reverse proxy: routes APP_DOMAIN traffic to orchestrator and all
  deployed apps via dynamic Traefik labels
- Postgres shared by platform (users, apps, messages, agent_runs) and
  Woodpecker CI state
- Ollama for local LLM inference — no external API keys required
- Gitea + gitea-init: admin user created automatically on first start
- Docker socket mounted into woodpecker-agent (CI runner) and orchestrator
  (container lifecycle management)
- All services on a single bridge network (platform_platform)
- Remote Docker host support via DOCKER_HOST=ssh://ds1
