---
title: "0005: Introduce a template library for generated apps"
status: accepted
date: 2026-03-21
related:
  - docs/architecture/components/template-library.md
  - docs/architecture/components/builder.md
  - docs/architecture/components/ui-designer.md
  - docs/architecture/components/planner.md
  - docs/architecture/components/generated-app.md
---

## Context

The builder agent currently generates all application code from a blank slate using LLM output in JSON mode. This approach has three systemic problems:

1. **Inconsistency.** The LLM produces structurally different output on each run — different project layouts, different import styles, different health endpoint implementations — even for the same app type. Standards YAML helps but does not fully constrain the LLM's structural choices.

2. **Boilerplate regrowth.** Every build regenerates the same boilerplate: FastAPI lifespan, structured logging, env var loading, Dockerfile non-root user setup, health endpoints. This consumes context window, adds latency, and introduces surface area for standards violations.

3. **Frontend fragmentation.** The ui-designer generates Jinja2 templates or inline HTML per app, producing a different visual style and component structure each time. Operators see inconsistent UIs across their apps. There is no shared component library, no design system, and no way to apply a brand update globally.

The portal itself is built on MUI Minimal Next.js v7. Standardising generated app frontends on the same template would produce UIs that look and behave consistently with the operator's own control plane.

## Options considered

### Option A: Tighter standards YAML constraints on the LLM

Add more rules to `patterns.yaml` and `security.yaml` that constrain LLM output structure. Expand the reviewer's static checks.

**Dropped because:** Standards YAML affects what the LLM *should* produce, not what it *does* produce. The underlying variance comes from the generation process itself. Reviewer retries add latency and do not eliminate structural inconsistency.

### Option B: Hardcoded fallback templates only (current partial model)

Extend the existing fallback template approach (currently only `form` type) to all five app types.

**Dropped because:** Fallbacks are invoked only on LLM parse failure, not on every build. Consistent output requires templates to be used as the *starting point* on every build, not as a fallback.

### Option C: Template library — base scaffolds + LLM augmentation (chosen)

Define a template library of base starting points for each stack (FastAPI, Express) and for the frontend (MUI Minimal Next.js). On every build:
- Builder loads the API template for the chosen stack
- LLM augments the template with app-specific routes, models, and business logic
- UI Designer loads the MUI Minimal frontend template
- LLM adapts the template to the app's specific routes and data model

**Chosen because:**
- Boilerplate is guaranteed: Dockerfile, health endpoints, logging, env var loading are always correct because they are in the template, not LLM output
- The LLM's role is narrowed to app-specific code only — it fills in routes, models, and logic, not infrastructure concerns
- Frontend visual consistency is guaranteed: all generated apps share the MUI Minimal design system
- The reviewer's static checks become simpler: check for LLM-added code only; template scaffolding is already correct
- Templates are versioned and can be updated globally to change all future builds (e.g. bump a dependency, apply a security fix)

## Decision

**Introduce a template library** stored as versioned directories, mounted read-only into the builder and ui-designer containers.

### API templates

Two base scaffolds, both pre-built with the mandatory platform contract (health endpoints, structured JSON logging, env-var-only configuration, non-root Dockerfile, `.woodpecker.yml`):

| Template | Stack | Used for |
|----------|-------|---------|
| `api/fastapi-base` | Python 3.12 / FastAPI | Default for all app types; required for `form`, `workflow`, `assistant` |
| `api/express-base` | Node.js 22 / Express | Alternative for `connector` and `dashboard` when operator spec or planner selects JS |

### Frontend template

One base frontend scaffold, built on the same MUI Minimal Next.js v7 template used by the portal:

| Template | Stack | Used for |
|----------|-------|---------|
| `frontend/mui-minimal` | Next.js 15 / MUI Minimal v7 | All app types with a browser-facing UI (`form`, `dashboard`, `workflow`, `assistant`) |

The frontend template is adapted per app by the ui-designer. The planner provides the route manifest and data model; the ui-designer instantiates MUI pages, layouts, and components appropriate for the app type.

### Stack selection

The planner selects the API stack and declares whether a frontend is required:
```json
{
  "stack": "fastapi",
  "frontend": true,
  "db": "postgres"
}
```

| Field | Values | Who decides |
|-------|--------|-------------|
| `stack` | `fastapi` (default) \| `express` | Planner (from spec analysis; FastAPI is default unless JS integration is required) |
| `frontend` | `true` \| `false` | Planner (false only for `connector` type) |
| `db` | `sqlite` \| `postgres` \| `mongo` \| `none` | Planner (sqlite for simple persistence; postgres for relational; mongo for document; none for stateless) |

### App container model (updated)

Apps with a frontend now produce **two containers**: an API container and a frontend container. Both are in the same Gitea repo under `api/` and `frontend/` subdirectories. The `.woodpecker.yml` builds and deploys both.

| App type | API container | Frontend container | DB |
|----------|--------------|-------------------|-----|
| `form` | FastAPI | Next.js (MUI Minimal) | SQLite or tenant Postgres |
| `dashboard` | FastAPI or Express | Next.js (MUI Minimal) | External read-only |
| `workflow` | FastAPI | Next.js (MUI Minimal) | Tenant Postgres |
| `connector` | FastAPI or Express | None | Tenant Postgres or tenant MongoDB |
| `assistant` | FastAPI | Next.js (MUI Minimal, chat-adapted) | Tenant Postgres (with pgvector extension) |

## Consequences

### What changes

- `builder.md`: template loading as first step (not fallback); LLM generates app-specific additions only
- `ui-designer.md`: MUI Minimal is the canonical starting point; Jinja2 templates are discontinued for new apps
- `planner.md`: build plan must include `stack`, `frontend`, and `db` fields
- `generated-app.md`: app types updated with 2-container model for UI apps; Dockerfile layout (api/ and frontend/ subdirs)
- `template-library.md`: new component doc describing templates, mount paths, versioning, and update process
- `standards/templates.yaml`: standards file listing allowed templates, required files per template, and rules for LLM augmentation
- CI pipeline (`.woodpecker.yml`): extended to build and deploy two containers for UI apps; two `platform.tenant` labels

### What does not change

- `.woodpecker.yml` structure: still `generate-tests → test → docker-build → deploy`; deploy step now handles two images
- Mandatory interface contract: `GET /health`, `GET /ready`, structured logging — guaranteed by templates, not LLM output
- Reviewer role: still reviews LLM-generated code against standards; template scaffolding is trusted and excluded from review scope
- Standards YAML files: remain the primary constraint on LLM-generated code; `templates.yaml` adds template-specific rules

### Deferred

- Multiple frontend theme variants (e.g. dark mode, custom brand colours per tenant)
- Mobile-native frontend templates (React Native, Expo)
- Non-MUI frontend templates (plain HTML, Vue, Svelte)
- Template hot-reload without full container rebuild
