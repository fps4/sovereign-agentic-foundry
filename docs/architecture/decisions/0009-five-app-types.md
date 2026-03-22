---
title: "0009: Define five canonical app types for generated applications"
status: accepted
date: 2026-03-22
related:
  - docs/architecture/components/generated-app.md
  - docs/architecture/decisions/0004-tenant-infra-layer.md
  - docs/architecture/decisions/0005-template-library.md
  - standards/templates.yaml
---

## Context

The platform builds and deploys web applications from natural-language descriptions. To do this reliably, the planner must be able to map an operator's description to a concrete structural model — choosing the right containers, database type, and infrastructure provisioning path.

Without a fixed set of application types, every app would require the planner to reason from scratch about what containers it needs, what kind of persistence is appropriate, and whether a frontend is required. This produces inconsistent output and makes it impossible to define deterministic templates or infra provisioning rules.

The set of applications a typical self-hosted operator wants covers a small, well-understood set of patterns: data collection forms, read-only dashboards, task trackers, API integrations, and document-backed chat. Formalising these as first-class types lets the planner, builder, infra agent, and template library all operate on a shared vocabulary.

## Decision

**Define five canonical app types.** The planner selects exactly one type per app. Each type has a fixed container model, a default database selection rule, and a defined set of infrastructure dependencies.

### The five types

| Type | One-line description | API container | Frontend | DB |
|------|----------------------|--------------|----------|----|
| `form` | Data entry and retrieval (CRUD) | FastAPI (`fastapi-base`) | Next.js (`mui-minimal`) | SQLite (default) or tenant Postgres |
| `dashboard` | Read-only data visualisation | FastAPI or Express | Next.js (`mui-minimal`) | None (external read-only) |
| `workflow` | Multi-stage task tracking with status transitions | FastAPI (`fastapi-base`) | Next.js (`mui-minimal`) | Tenant Postgres |
| `connector` | Headless backend integration (API-to-API) | FastAPI or Express | None | Tenant Postgres or tenant MongoDB |
| `assistant` | RAG chat over uploaded documents | FastAPI (`fastapi-base`) | Next.js (`mui-minimal`, chat-adapted) | Tenant Postgres with pgvector extension |

### Type definitions

#### `form`

Two containers: FastAPI API + Next.js frontend (MUI Minimal). Browser-facing CRUD — data entry forms with persistence. Default DB is SQLite (embedded, data lost on container removal without a volume); planner upgrades to tenant Postgres when the spec requires durable persistence. No infra agent call for SQLite; infra agent creates a per-app database in the tenant Postgres container for the Postgres variant.

#### `dashboard`

Two containers: FastAPI or Express API + Next.js frontend (MUI Minimal). Read-only data visualisation. Data comes from external sources injected as env vars (read-only DSNs, API keys). No write paths. No infra agent call required.

#### `workflow`

Two containers: FastAPI API + Next.js frontend (MUI Minimal). Stateful multi-stage task tracker. Tasks progress through operator-defined stages and require durable persistence — planner always selects tenant Postgres. Infra agent creates the per-app database in the tenant Postgres container before the builder runs.

#### `connector`

One container: FastAPI or Express API. Headless backend integration — API proxy, webhook consumer, or data sync job. No browser-facing frontend unless the spec explicitly requests a status page (in which case a second Next.js container is added). Planner selects tenant Postgres for relational integrations or tenant MongoDB for document-oriented integrations. Infra agent provisions the per-app database within the appropriate tenant container.

#### `assistant`

Three containers: FastAPI API + Next.js frontend (MUI Minimal, chat-adapted layout) + tenant Postgres with pgvector extension. Conversational UI backed by a RAG pipeline. Operator uploads documents; the app embeds them using pgvector and retrieves them to augment LLM responses. The app calls Ollama directly at runtime for inference. The infra agent ensures the tenant Postgres container has the pgvector extension enabled, then creates a per-app database within it.

### Infrastructure dependencies by type

| Type | Infra agent call | Tenant Postgres | Tenant MongoDB |
|------|-----------------|-----------------|----------------|
| `form` (SQLite) | No | No | No |
| `form` (Postgres) | Yes | Yes | No |
| `dashboard` | No | No | No |
| `workflow` | Yes | Yes | No |
| `connector` (Postgres) | Yes | Yes | No |
| `connector` (MongoDB) | Yes | No | Yes |
| `assistant` | Yes | Yes (pgvector) | No |

### Database selection rules

| Type | Default | Override condition |
|------|---------|--------------------|
| `form` | `sqlite` | Upgrade to `postgres` when spec requires data to survive container restarts or operator expects >100 rows |
| `dashboard` | `none` | Never; dashboards read external sources and do not write |
| `workflow` | `postgres` | No override; workflow state must survive restarts |
| `connector` | `postgres` | Use `mongo` when spec involves document storage, log ingestion, or schema-less event data |
| `assistant` | `postgres` | No override; pgvector extension requires tenant Postgres |

### Where the type set is enforced

- `agents/intake/main.py` — `APP_TYPES` constant; intake agent rejects any type not in this list
- `agents/intake/prompts/system.md` — type definitions injected into the intake agent's system prompt
- `standards/templates.yaml` — `stack_selection` and `db_selection` rules reference type names
- `docs/architecture/components/generated-app.md` — runtime model per type (containers, files, Traefik routing)

## Options considered

### Option A: Open-ended app types inferred per spec

Allow the planner to derive a structural model from scratch for each spec, without a fixed type taxonomy.

**Dropped because:** The planner cannot reliably infer container topology, database requirements, and infra provisioning needs from a natural-language description alone. Without fixed types, template selection, infra provisioning rules, and CI pipeline generation would all require unconstrained LLM reasoning on every build — making output inconsistent and hard to test.

### Option B: Two types (with-frontend / headless)

Define only two structural categories: apps with a browser-facing frontend and apps without one.

**Dropped because:** This conflates structurally different runtime models. A `form` (SQLite, no infra call) and a `workflow` (tenant Postgres, infra call required) are both "with frontend" but have different provisioning paths. Two types would still require the planner to reason about database and infra requirements case-by-case.

### Option C: Five canonical types (chosen)

Define five types that cover the common self-hosted operator use case space, with fixed container models, database defaults, and infra rules per type.

**Chosen because:**
- Five types cover the overwhelming majority of apps a self-hosted operator would request
- Each type has a deterministic infra provisioning path — no case-by-case reasoning required
- Template selection is mechanical: type → template ID (see ADR-0005)
- The intake agent can present the type menu when a description is ambiguous
- Tests can be written per type with known expected behaviour

## Consequences

- The intake agent's system prompt includes the type definitions and uses them to classify every spec.
- The planner selects one type per build plan; the `app_type` field is required in the locked spec.
- The infra agent's provisioning logic branches on type (and on the `db` field of the build plan).
- The template library (ADR-0005) maps each type to a template pair; `connector` maps to API-only.
- Adding a sixth type requires updates to: `APP_TYPES` constant, intake system prompt, `templates.yaml`, infra agent provisioning logic, template library, and this ADR.
- Types are intentionally narrow. Requests that do not fit are clarified by the intake agent until they map to one of the five types, or are declined.
