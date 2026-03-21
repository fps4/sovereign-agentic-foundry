---
title: "Component design: Infra agent"
status: proposed
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: infra
related:
  - docs/architecture/overview.md
  - docs/architecture/components/planner.md
  - docs/architecture/components/builder.md
  - docs/architecture/data-model.md
---

## Purpose

The infra agent provisions and manages per-app infrastructure resources that go beyond a single application container: dedicated databases, vector stores for RAG apps, and per-app secret injection. It is called by the build pipeline when the planner determines that the app type requires external resources. It also handles teardown when an app is deleted.

The infra agent is not required for app types that only need a self-contained container (`form`, `dashboard`, `workflow`). It becomes necessary when apps need persistent external state or external API credentials (`connector`, `assistant`).

## Responsibilities

**Owns:**
- Per-app PostgreSQL database and user provisioning
- pgvector instance provisioning for `assistant` apps
- Per-app secret generation (DB credentials, API keys) and secure injection into the app's runtime environment via Docker labels or Gitea-stored env files
- Resource inventory: tracking what each app has provisioned
- Teardown of all provisioned resources when an app is deleted or archived

**Does not own:**
- Application container lifecycle (owned by Woodpecker CI and Traefik)
- CI pipeline configuration (owned by the builder agent)
- Platform-level infrastructure (Postgres platform DB, Gitea, Woodpecker — these are fixed and not managed by this agent)
- Backup or restore of per-app databases

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, `POST /provision` and `POST /teardown` endpoints |
| Docker SDK client | Spins up and removes per-app resource containers on the platform network |
| Postgres provisioner | Creates a database and scoped user in the platform Postgres instance for apps that need relational storage |
| Secret manager | Generates credentials; writes them as environment variables into the app's Gitea repo (`.env.platform`) |
| Resource registry | `app_resources` table — tracks resource type, container name, and connection details per app |

## Key flows

### Provision (called during build pipeline)

1. Planner identifies that the app type requires external resources and includes `{resources: ["postgres"]}` or `{resources: ["pgvector"]}` in the build plan
2. Gateway calls `POST /provision` with `{app_name, user_id, resources}`
3. For each requested resource:
   - `postgres`: creates a dedicated database and user in the platform Postgres instance; records credentials
   - `pgvector`: starts a `pgvector/pgvector` container on the platform network; records connection string
4. Secrets are written to `.env.platform` in the app's Gitea repo (created or updated before builder runs)
5. Returns `{provisioned: [{type, connection_env_var, status}]}` to the gateway
6. Builder receives the provisioned resource list as part of its build context and references the env vars in generated code

### Teardown (called on app deletion)

1. Operator calls `/delete` via Telegram; gateway calls `POST /teardown` with `{app_name}`
2. Infra reads `app_resources` for the app
3. Removes per-app resource containers (pgvector instances)
4. Drops the per-app Postgres database and user
5. Deletes `.env.platform` from the app's Gitea repo
6. Removes rows from `app_resources`
7. Returns `{torn_down: [...]}` to gateway; gateway proceeds with Gitea repo archive

### No resources required

1. Planner build plan contains no `resources` field or `resources: []`
2. Gateway does not call the infra agent
3. Build pipeline proceeds directly to builder

## Data owned

**Writes:**
- `app_resources` table (Postgres) — records each provisioned resource: type, container name, connection string, per app
- Per-app Postgres databases and users (admin connection to platform Postgres)
- `.env.platform` files in Gitea repos — injected secrets for the generated app

**Reads:**
- `app_resources` — read during teardown to determine what to remove

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Postgres admin connection fails | Returns error to gateway; build aborted; no resources provisioned |
| Docker socket unreachable | Returns error to gateway; pgvector container cannot be started; build aborted |
| Partial provision (Postgres DB created, pgvector fails) | Returns error to gateway; `app_resources` may contain partial records; teardown must handle partial state |
| Gitea secret write fails | Returns error to gateway; generated code will have missing env vars at runtime |
| Teardown: resource container not found | Logs warning and continues; assumes already removed |

## Non-functional constraints

- All resource containers share the platform Docker host; no compute or storage isolation beyond Docker networking.
- Per-app Postgres databases are on the same Postgres instance as the platform DB; large apps can affect platform performance.
- pgvector containers are one per app; no connection pooling.
- Secret rotation is not supported; credentials are static for the app's lifetime.

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /provision` | Gateway (during build) | Provision external resources for a new app |
| `POST /teardown` | Gateway (on app delete) | Remove all resources for a deleted app |
| `GET /health` | Traefik / gateway | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| Docker socket (read/write) | Start and stop per-app resource containers |
| Platform Postgres (admin connection) | Create and drop per-app databases and users |
| Gitea HTTP API | Write `.env.platform` with injected secrets |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `DOCKER_HOST` | unix socket | Docker socket path or SSH remote host |
| `PLATFORM_NETWORK` | `platform_platform` | Docker network all resource containers join |
| `POSTGRES_ADMIN_URL` | — | Admin DSN for the platform Postgres instance (used to create per-app DBs) |
| `GITEA_URL` | — | Internal Gitea base URL |
| `GITEA_ADMIN_USER` / `GITEA_ADMIN_PASS` | — | Gitea API credentials |

## Known limitations

- No backup or restore for per-app databases; data is lost on teardown.
- All resource containers share the platform Docker host — there is no compute or storage isolation beyond Docker networking.
- pgvector container provisioning is one instance per app; no connection pooling or shared vector store across apps.
- Secret rotation is not supported; credentials generated at provision time are static for the app's lifetime.
- If provision partially succeeds (e.g. Postgres DB created but pgvector container fails), the teardown path must handle partial state.
