---
title: "0003: Introduce tenant as the primary scoping unit"
status: accepted
date: 2026-03-21
related:
  - docs/architecture/overview.md
  - docs/architecture/data-model.md
  - docs/product/vision.md
---

## Context

The current architecture scopes all resources — apps, Gitea organisations, Docker labels — directly to a Telegram user ID (`users.telegram_id`). This worked when Telegram was the sole interface and one Telegram account implied one operator. Two forces have changed this:

1. **Portal adoption (ADR-0002)** — the portal introduced email+password auth independent of Telegram. The binding between a Telegram account and the platform's user is now optional, not foundational.
2. **Multi-user operational need** — a hospital department or ops team might have multiple staff who should share visibility of the department's apps. The platform should support this without requiring them to share a Telegram account or portal login.

The current `user_id` foreign key on `apps` conflates two distinct concepts:
- **Who owns this app** (a team, a department, an organisation)
- **Who created this app** (the individual operator who submitted the spec)

These need to be separated for the platform to be useful in team settings.

## Options considered

### Option A: Multi-user roles on the `users` table

Add role columns (`is_admin`, `team_id`) to `users`. Share apps via a `team_id` FK.

**Dropped because:** this collapses the ownership unit into the user table, making future expansion messy. It does not generalise to a shared-tenant model (org-wide apps).

### Option B: Introduce `tenants` as a first-class entity (chosen)

Add a `tenants` table. Each tenant has a `tenant_type` that starts as `single_user` and can evolve to `team` or `shared`. Apps and Gitea orgs scope to tenants, not users.

**Chosen because:**
- The tenant abstraction cleanly separates "who owns this set of apps" from "which user is logged in"
- Single-user tenant is a trivial special case: registration creates one user and one tenant atomically
- Adding team members later requires only a `tenant_memberships` join table — no changes to `apps`, `board_cards`, `agent_runs`, or any agent code
- The `tenant_type` column acts as a discriminator for future models without schema changes for the common case

## Decision

**Introduce a `tenants` table** as the primary scoping unit for apps, Gitea organisations, and Docker container labels.

**v1 behaviour (single-user tenant):** registration creates one tenant per user automatically. The operator is unaware of the tenant concept — the experience is identical to the pre-tenant model. `tenant_type = 'single_user'`.

**Future team model:** an existing operator invites a second user to their tenant. Both users see the same apps, Kanban boards, and build history. The inviting user is `owner`; the invited user is `member`. No changes to `apps`, `board_cards`, or any agent code are required.

**Future shared model:** a platform-administrator-created tenant (`tenant_type = 'shared'`) whose apps are visible to all registered users. Use case: platform-wide utilities or demo apps.

## Consequences

### What changes

- `tenants` table added (see `docs/architecture/data-model.md`)
- `users.gitea_org` moves to `tenants.gitea_org`
- `users.tenant_id` FK added
- `apps.tenant_id` FK added (primary ownership); `apps.user_id` kept as `created_by_user_id` for audit
- Docker label `platform.owner` renamed to `platform.tenant` (value: `{tenant_id}`)
- Gateway registration flow creates a tenant row atomically with the user row
- All gateway queries that filter by `user_id` for app ownership migrate to filter by `tenant_id`
- Watchdog uses `platform.tenant` label instead of `platform.owner` to attribute containers

### What does not change

- `messages.user_id` stays user-scoped (conversation history is personal)
- `board_cards`, `app_issues`, `agent_runs` are unchanged (they reference `app_id`)
- All agent code is unchanged (agents receive tenant context via the build plan, not directly)
- Single-user operators see no change in behaviour

### Deferred to future ADRs

- `tenant_memberships` table design (roles: owner, member, viewer)
- Tenant invite flow (email invite vs. registration code)
- Shared tenant model and visibility rules
- Data isolation between tenants (currently none beyond logical FK scoping)
