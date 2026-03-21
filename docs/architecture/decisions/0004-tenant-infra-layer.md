---
title: "0004: Introduce a tenant infrastructure layer"
status: accepted
date: 2026-03-21
related:
  - docs/architecture/decisions/0003-tenant-model.md
  - docs/architecture/components/infra.md
  - docs/architecture/data-model.md
  - docs/architecture/components/generated-app.md
---

## Context

The current infra agent provisions resources per app inside the **platform** Postgres instance: a dedicated database and user for `connector` and `assistant` apps, and a separate pgvector container for `assistant` apps. This model has two problems:

1. **No isolation between tenants.** All per-app databases share one Postgres instance with the platform's own operational data (`users`, `apps`, `messages`, etc.). A runaway query or large dataset from one operator's app can degrade the platform itself.

2. **No MongoDB support.** Some connector and assistant use cases are document-oriented (log ingestion, unstructured event storage, RAG over heterogeneous document types). The current model forces everything into a relational schema.

3. **Resource proliferation.** As tenant app count grows, the number of databases in the platform Postgres and the number of pgvector containers on the platform network grows without bound. There is no lifecycle management at the tenant level — only at the individual app level.

The ADR-0003 tenant model introduced `tenants` as the primary ownership unit. The natural extension is to scope database infrastructure to the tenant as well as to individual apps.

## Options considered

### Option A: Keep per-app provisioning inside platform Postgres

Add MongoDB support alongside the existing Postgres approach. No tenant-level container.

**Dropped because:** Does not address isolation. MongoDB would require its own shared instance with the same multi-tenancy problems. Resource proliferation continues to worsen over time.

### Option B: Per-app dedicated containers (current partial model extended)

Each app that needs a database gets its own Postgres or MongoDB container.

**Dropped because:** Extremely high container count at scale. One Postgres container per connector app is operationally unmanageable. Does not give operators a stable, always-available data layer they can reason about.

### Option C: Tenant-level database containers, lazily provisioned (chosen)

Each tenant receives one Postgres container and one MongoDB container, provisioned the first time an app in that tenant requests the database type. All subsequent apps in the same tenant create databases **within** the tenant's container. pgvector is enabled as an extension on the tenant Postgres rather than as a separate container.

**Chosen because:**
- One container per tenant per database type scales predictably with operator count, not app count.
- Tenants are isolated from each other and from the platform database — a tenant's container has no visibility into the platform DB or other tenants' containers.
- Adding a new app within a tenant is cheap: create a database and user within the existing container; no new Docker container required.
- pgvector as an extension eliminates the per-app pgvector container; all vector stores for a tenant live in one container and can be managed together.
- Teardown of all tenant apps (e.g. tenant offboarding) is a single container stop-and-remove, not N individual teardowns.

## Decision

**Introduce a tenant infrastructure layer** managed by the infra agent.

**Tenant Postgres container:**
- Container name: `tenant-{tenant_id}-postgres`
- Image: `pgvector/pgvector` (Postgres with pgvector extension pre-installed, eliminating the per-app pgvector container)
- Provisioned on first request from any app in the tenant that requires relational storage
- Joined to `platform_platform` Docker network; addressable as `tenant-{tenant_id}-postgres:5432`
- Per-app: create a database (`{app-name}`) and scoped user (`{app-name}-user`) within this container

**Tenant MongoDB container:**
- Container name: `tenant-{tenant_id}-mongo`
- Image: `mongo` (pinned version)
- Provisioned on first request from any app in the tenant that requires document storage
- Joined to `platform_platform` Docker network; addressable as `tenant-{tenant_id}-mongo:27017`
- Per-app: create a database (`{app-name}`) and scoped user within this container

**Provisioning triggers:**
- Infra agent receives `POST /provision` with `{tenant_id, app_name, resources: ["postgres"]}` or `resources: ["mongo"]`
- Agent checks `tenant_resources` table: if a container for this tenant+type already exists, skip container creation and proceed directly to per-app database creation
- If no container exists: start the container, wait for readiness, then create the per-app database

**pgvector migration:**
- The per-app pgvector container (current model) is replaced by the pgvector extension on the tenant Postgres container
- The `PGVECTOR_URL` env var for assistant apps now points to the tenant Postgres container with a vector-enabled database (not a separate container)
- Existing per-app pgvector containers are deprecated; new builds use the tenant Postgres

## Consequences

### What changes

- `infra.md`: two-phase provisioning model (tenant-level container check → app-level database creation)
- `tenant_resources` table added to data model: tracks per-tenant provisioned containers and their status
- `app_resources` table: existing per-app resource tracking; now records DB credentials pointing into tenant containers
- `generated-app.md`: per-app pgvector container removed from the runtime model; pgvector is now tenant infrastructure
- `generated-app.md`: app types `connector` and `assistant` use `TENANT_POSTGRES_URL` and `TENANT_MONGO_URL` env vars (set to the tenant container); `DATABASE_URL` and `PGVECTOR_URL` remain available as app-scoped credentials pointing into those containers
- Gateway `POST /provision` call to infra now always includes `tenant_id`
- Structurizr DSL: add `tenantPostgres` and `tenantMongo` containers to the tenant tier

### What does not change

- Platform Postgres instance: continues to store platform state (`users`, `apps`, `messages`, etc.); no longer used for per-app application databases
- App code: generated code still reads `DATABASE_URL` and `PGVECTOR_URL` env vars; the values now point into tenant containers instead of the platform Postgres or per-app pgvector containers — no app-level change required
- Single-user tenant experience: operator is unaware of the tenant container; it is a platform-managed detail

### Deferred to future ADRs

- Backup and restore for tenant database containers
- Storage quotas per tenant container
- Cross-tenant database access (shared tenant model — deferred per ADR-0003)
- Container restart and crash recovery for tenant database containers
