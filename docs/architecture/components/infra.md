---
title: "Component design: Infra agent"
status: proposed
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: infra
related:
  - docs/architecture/overview.md
  - docs/architecture/decisions/0004-tenant-infra-layer.md
  - docs/architecture/components/planner.md
  - docs/architecture/components/builder.md
  - docs/architecture/data-model.md
---

## Purpose

The infra agent provisions and manages infrastructure resources for the tenant tier. It operates at two levels:

1. **Tenant-level provisioning** — dedicated Postgres and MongoDB containers, one per tenant per database type, provisioned lazily on first need. These containers are long-lived and shared by all apps within the tenant.
2. **App-level provisioning** — creates a database and scoped user within the tenant's already-running container when an individual app needs persistent storage. Writes connection secrets to the app's Gitea repo.

The infra agent is not involved for apps that use only SQLite (`form` in simple cases). It is required for any app that needs relational storage (`postgres`), document storage (`mongo`), or vector search (pgvector extension on the tenant Postgres container).

See `docs/architecture/decisions/0004-tenant-infra-layer.md` for the rationale behind this two-phase model.

## Responsibilities

**Owns:**
- Tenant Postgres container lifecycle: start, readiness check, record in `tenant_resources`
- Tenant MongoDB container lifecycle: start, readiness check, record in `tenant_resources`
- Per-app database and user creation within tenant containers
- pgvector extension setup on the tenant Postgres container (for `assistant` apps)
- Per-app secret generation and secure injection into the app's Gitea repo (`.env.platform`)
- Teardown: per-app database drop on app deletion; tenant container removal only when all apps in the tenant are deleted

**Does not own:**
- Application container lifecycle (owned by Woodpecker CI and Traefik)
- CI pipeline configuration (owned by the builder agent)
- Platform-level infrastructure (platform Postgres, Gitea, Woodpecker — fixed, not managed by this agent)
- Backup or restore of tenant databases

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app; all endpoints |
| `tenant_provisioner.py` | Manages tenant-level container lifecycle (start, health check, record state) |
| `app_provisioner.py` | Creates per-app databases and users within tenant containers |
| `secret_manager.py` | Generates credentials; writes `.env.platform` to Gitea |
| Docker SDK client | Starts and stops tenant containers; checks health |

## Key flows

### Provision (two-phase, called during build pipeline)

**Phase 1 — ensure tenant infrastructure exists:**

1. Gateway calls `POST /provision` with `{tenant_id, app_name, resources: ["postgres"]}` (or `"mongo"`)
2. Infra queries `tenant_resources` for `{tenant_id, resource_type}`
3. **If container exists and is running:** skip to Phase 2
4. **If container does not exist:**
   a. Pull image if not present (`pgvector/pgvector` for Postgres, `mongo` pinned for MongoDB)
   b. Start container: `tenant-{tenant_id}-postgres` or `tenant-{tenant_id}-mongo`
   c. Join container to `platform_platform` network
   d. Wait for readiness (retry with backoff, max 60 s)
   e. For Postgres: enable pgvector extension (`CREATE EXTENSION IF NOT EXISTS vector`)
   f. Record container name, host, port, and status in `tenant_resources`

**Phase 2 — provision per-app database:**

5. Create database `{app-name}` within the tenant's container
6. Create scoped user `{app-name}-user` with `SELECT, INSERT, UPDATE, DELETE` on the app's database only
7. Generate credentials; build connection DSN
8. Write DSN and credentials to `.env.platform` in the app's Gitea repo
9. Return `{provisioned: [{type, connection_env_var, dsn_env_var, status}]}` to gateway

### Teardown (app deletion)

1. Gateway calls `POST /teardown` with `{tenant_id, app_name}`
2. Infra reads `app_resources` for the app
3. Drops database `{app-name}` and user `{app-name}-user` from the tenant container
4. Deletes `.env.platform` from the app's Gitea repo
5. Removes app rows from `app_resources`
6. Does **not** remove the tenant container (other apps may use it)
7. Returns `{torn_down: [...]}` to gateway

### Tenant teardown (all apps deleted, offboarding)

1. Gateway calls `POST /tenants/{tenant_id}/teardown` (future endpoint; called on tenant offboarding)
2. Infra stops and removes `tenant-{tenant_id}-postgres` and `tenant-{tenant_id}-mongo` (if running)
3. Removes rows from `tenant_resources`

### No resources required

1. Planner build plan has `db: "sqlite"` or `db: "none"`
2. Gateway does not call infra agent
3. Build pipeline proceeds directly to the builder

## Data owned

**Writes:**
- `tenant_resources` table — tracks per-tenant containers: type, container name, host, port, status
- `app_resources` table — tracks per-app databases: type, dsn reference, status
- Per-app databases and users inside tenant containers
- `.env.platform` files in Gitea repos

**Reads:**
- `tenant_resources` — to check if a container already exists before starting one
- `app_resources` — read during teardown

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Docker socket unreachable | Returns error to gateway; build aborted |
| Tenant container fails to start | Returns error to gateway; build aborted; `tenant_resources` row not written |
| Container readiness timeout | Returns error after 60 s; build aborted; partial `tenant_resources` row marked `error` |
| Per-app DB creation fails (container running but SQL error) | Returns error to gateway; no `app_resources` row written |
| Gitea secret write fails | Returns error; generated code will have missing env vars at runtime; build is aborted |
| Teardown: database not found | Logs warning; assumes already dropped; continues |
| Teardown: container not found | Logs warning; clears `tenant_resources`; continues |

## Non-functional constraints

- Tenant containers share the platform Docker host; no CPU or storage isolation.
- Tenant Postgres container hosts all apps for one tenant; a single large app dataset can degrade other apps in the same tenant.
- pgvector is enabled at the tenant container level; all vector operations for all `assistant` apps within the tenant share one container.
- Secret rotation is not supported; credentials are static for the app's lifetime.
- The agent is idempotent: calling `POST /provision` twice for the same `{tenant_id, app_name, resources}` skips container creation and re-writes the same secrets without error.

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /provision` | Gateway (during build) | Provision tenant infra (if needed) and per-app database |
| `POST /teardown` | Gateway (on app delete) | Drop per-app database and remove secrets |
| `GET /health` | Traefik / gateway | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| Docker socket (read/write) | Start tenant containers; check health; remove on offboarding |
| Tenant Postgres admin connection | Create and drop per-app databases and users |
| Tenant MongoDB admin connection | Create and drop per-app databases and users |
| Gitea HTTP API | Write `.env.platform` with injected secrets |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `DOCKER_HOST` | unix socket | Docker socket path or SSH remote host |
| `PLATFORM_NETWORK` | `platform_platform` | Docker network all tenant containers join |
| `POSTGRES_ADMIN_PASSWORD` | — | Password used when creating the tenant Postgres container |
| `MONGO_ADMIN_PASSWORD` | — | Password used when creating the tenant MongoDB container |
| `GITEA_URL` | — | Internal Gitea base URL |
| `GITEA_ADMIN_USER` / `GITEA_ADMIN_PASS` | — | Gitea API credentials |
| `TENANT_CONTAINER_READY_TIMEOUT` | `60` | Seconds to wait for a new container to pass readiness check |

## Known limitations

- No backup or restore for tenant databases; data is lost on container removal.
- All tenant containers share the platform Docker host — a runaway query in one tenant's container can affect other tenants on the same host.
- pgvector is shared across all `assistant` apps within one tenant; no per-app vector store isolation.
- Secret rotation is not supported; credentials generated at provision time are static.
- Partial provision (tenant container started, per-app DB creation fails) leaves a running container with no associated `app_resources` row; teardown handles this gracefully but the container persists until the next successful provision or offboarding.
