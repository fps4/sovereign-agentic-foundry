---
title: "Component design: Publisher"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: publisher
related:
  - docs/architecture/overview.md
  - docs/architecture/components/builder.md
  - docs/architecture/components/reviewer.md
  - docs/architecture/components/gateway.md
---

## Purpose

The publisher is a deterministic service that commits reviewer-approved files to a new Gitea repository, generates the Woodpecker CI pipeline configuration, and activates the CI pipeline via a HMAC-signed webhook. It contains no LLM calls. Its job is to move validated artefacts from the build pipeline into version control and trigger deployment.

## Responsibilities

**Owns:**
- Gitea repository creation in the user's org (`app-{name}` under `user-{telegram_id}`)
- Committing all generated files (backend, frontend templates, dependencies) to the repo
- Generating `.woodpecker.yml`: `generate-tests` → `test` → `docker-build` → `deploy` steps
- Woodpecker repo activation: direct Postgres insert and HMAC-signed Gitea webhook

**Does not own:**
- File generation (owned by the builder and ui-designer agents)
- Standards review (owned by the reviewer agent)
- CI execution (handled by Woodpecker CI after the webhook fires)
- Infrastructure provisioning (owned by the infra agent)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, `POST /publish` endpoint |
| `gitea.py` | Gitea API wrapper: create repo, commit files in a single batch |
| `pipeline.py` | Generates `.woodpecker.yml` from app name and app type |
| `woodpecker.py` | Activates repo: inserts into Woodpecker Postgres DB, fires HMAC-signed webhook |

## Key flows

### Happy path

1. Gateway calls `POST /publish` with `{spec, files: [{path, content}], user_id}`
2. `gitea.py` creates repo `app-{name}` in org `user-{telegram_id}`
3. `pipeline.py` generates `.woodpecker.yml` with correct service URLs and app name
4. `gitea.py` commits all files (application files + `.woodpecker.yml`) in a single API call
5. `woodpecker.py` inserts repo activation row into Woodpecker Postgres DB
6. `woodpecker.py` sends HMAC-signed webhook to Woodpecker server; this triggers the first pipeline run
7. Returns `{repo_url, app_url}` to gateway

### Commit failure

1. Gitea API returns an error during repo creation or file commit
2. Publisher returns error to gateway; gateway sets `apps.status = failed`
3. No partial state cleanup — Gitea repo may exist but be empty; this is acceptable as the repo name is unique per user

## Data owned

**Writes (external systems, not platform DB):**
- Gitea: creates repos and commits all generated files
- Woodpecker internal DB: inserts repo activation row (direct Postgres write to Woodpecker's `woodpecker` DB)

**Reads:**
- Woodpecker internal DB: checks for existing repo activation before inserting

The publisher does not read or write any platform Postgres tables (`users`, `apps`, etc.). The gateway owns those.

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Gitea API error on repo creation | Returns error to gateway; gateway sets `apps.status = failed`; no partial cleanup (repo name is reserved) |
| Gitea API error on file commit | Returns error to gateway; repo may exist but be empty — acceptable since repo names are unique per user |
| Woodpecker DB insert fails | Returns error to gateway; repo is committed but CI is not activated; app stuck in `building` |
| Webhook rejected by Woodpecker | Repo and DB row exist but pipeline does not start; manual intervention required |

## Non-functional constraints

- All generated files are committed in a single Gitea API call (batch commit); avoids multiple round-trips.
- `.woodpecker.yml` is generated once at publish time; changes to the CI template require a new build.
- Woodpecker activation couples the publisher to Woodpecker's internal schema; Woodpecker upgrades may change the schema without warning.

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /publish` | Gateway | Commit files and activate CI for a new app |
| `GET /health` | Traefik / gateway | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| Gitea HTTP API | Create repo, commit files |
| Woodpecker Postgres DB (direct) | Activate repo for CI |
| Woodpecker HTTP API | Send HMAC-signed webhook to trigger first pipeline run |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `GITEA_URL` | — | Internal Gitea base URL |
| `GITEA_ADMIN_USER` / `GITEA_ADMIN_PASS` | — | Gitea API credentials |
| `WOODPECKER_DB_URL` | — | Direct Postgres DSN for Woodpecker's internal DB |
| `WOODPECKER_SECRET` | — | HMAC secret for signing the activation webhook |
| `APP_DOMAIN` | — | Base domain; used to construct `{name}.APP_DOMAIN` app URL |

## Known limitations

- Direct Woodpecker Postgres insert couples the publisher to Woodpecker's internal schema; schema changes in Woodpecker upgrades may break activation without warning.
- `.woodpecker.yml` is generated once at publish time; changes to the CI template require a new build.
- No rollback on partial failure: if the webhook fires but Woodpecker rejects it, the repo exists in Gitea without an active CI pipeline.
