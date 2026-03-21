---
title: Data model
status: current
last_updated: 2026-03-21
owners: [platform-team]
related:
  - docs/architecture/overview.md
  - orchestrator/db.py
---

## Purpose

Describes the entities and relationships in the platform's PostgreSQL database (`platform` DB). Schema is defined and auto-migrated in `orchestrator/db.py`. Woodpecker CI uses a separate `woodpecker` DB (created by `infra/init-db.sql`); its schema is managed by Woodpecker internally.

## Entities

### `users`

Registered platform users. One row per Telegram user.

| Column | Type | Notes |
|--------|------|-------|
| `telegram_id` | TEXT PK | Telegram user ID (string) |
| `telegram_username` | TEXT | Telegram @handle, nullable |
| `gitea_org` | TEXT | Gitea org name, e.g. `user-123456` |
| `verified` | BOOLEAN | True after registration flow completes |
| `verification_code` | TEXT | One-time code used during registration, nullable |
| `design_mode` | BOOLEAN | True while designer agent is actively clarifying a spec |
| `created_at` | TIMESTAMPTZ | |

### `messages`

Conversation history. Used to maintain LLM context across turns.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `user_id` | TEXT | FK → `users.telegram_id` |
| `role` | TEXT | `user` or `assistant` |
| `content` | TEXT | Message body |
| `created_at` | TIMESTAMPTZ | |

### `apps`

Registry of all generated applications.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `user_id` | TEXT | FK → `users.telegram_id` |
| `name` | TEXT | Kebab-case app name, unique within user |
| `description` | TEXT | Human-readable description from spec |
| `app_type` | TEXT | One of: `form`, `dashboard`, `workflow`, `connector`, `assistant` |
| `status` | TEXT | See status lifecycle below |
| `repo_url` | TEXT | Gitea repo URL, nullable until coder completes |
| `app_url` | TEXT | Public URL after deploy, nullable until deploy completes |
| `error_detail` | TEXT | Last error message if status is `failed` or `degraded` |
| `archived` | BOOLEAN | Soft-delete flag; archived apps are hidden from `/apps` |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**Status lifecycle:**

```
queued → provisioning → building → active
                                 → failed
                    → degraded (set by monitor after deploy)
```

### `app_issues`

Deduplication log for monitor-detected errors. Each unique error is recorded once.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `app_id` | INTEGER | FK → `apps.id` |
| `error_hash` | TEXT | MD5 of normalised error text; uniqueness key |
| `gitea_issue_url` | TEXT | URL of the created Gitea issue |
| `is_breaking` | BOOLEAN | If true, sets app status to `failed` and sends Telegram notification |
| `created_at` | TIMESTAMPTZ | |

### `agent_runs`

Audit trail for every pipeline step.

| Column | Type | Notes |
|--------|------|-------|
| `id` | BIGSERIAL PK | |
| `run_id` | TEXT | Groups steps for one build pipeline run |
| `agent` | TEXT | Agent or step name (e.g. `coder`, `tester`) |
| `repo` | TEXT | Gitea repo name, nullable |
| `task_ref` | TEXT | Free-form reference (e.g. Woodpecker build ID), nullable |
| `event` | TEXT | Step name within the agent's execution |
| `status` | TEXT | `ok` or `error` |
| `payload` | JSONB | Step input/output snapshot |
| `created_at` | TIMESTAMPTZ | |

## Relationships

```
users ─< messages       (one user, many messages)
users ─< apps           (one user, many apps)
apps  ─< app_issues     (one app, many deduplicated issues)
```

`agent_runs` is append-only and not foreign-keyed to `apps`; it references repos and run IDs by string for resilience across deploys.
