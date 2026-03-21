---
title: "0002: Unified web portal as primary user interface"
status: accepted
date: 2026-03-21
related:
  - docs/architecture/overview.md
  - docs/product/vision.md
  - docs/architecture/components/portal.md
  - docs/architecture/components/gateway.md
  - docs/architecture/data-model.md
---

## Context

The platform originally exposed one interaction channel: Telegram. This made sense at inception — no frontend to build, operators already have Telegram on their phones. But as the platform matures, Telegram as the sole surface has concrete gaps:

1. **No persistent visibility** — the operator has no way to see all their apps, build history, health status, or pipeline progress in one place. Telegram history is a flat chat log, not a structured view.
2. **No backlog management** — there is no surface for queuing feature requests or bug reports against an app without immediately starting a conversation.
3. **Input is conversational-only** — structured actions (delete app, view logs, move a story to in-progress) require Telegram commands or free-text. A web UI can expose these as first-class interactions.
4. **Kanban board requires a UI** — the decision to give each app a Kanban board (pipeline visibility + backlog) has no natural home in Telegram. An external Trello integration was considered but introduces an external SaaS dependency and solves the output side only — the input side (operator-created stories) still requires polling or webhooks from Trello.

The platform needs a proper web-based control plane.

## Options considered

### Option A: Trello integration (dropped)

Maintain Telegram as the sole input channel; add Trello as a read-only board surface per app.

**Dropped because:**
- Trello is an external SaaS dependency. Data sovereignty is a stated product non-goal to violate.
- Trello write-back (operator creates a story → build triggered) requires either polling or a public webhook endpoint — incompatible with private self-hosted deployments.
- Provides visibility only; does not solve the input, backlog, or history gaps.

### Option B: Self-hosted Kanban add-on (Planka / Focalboard)

Deploy an open-source Kanban tool alongside the platform and sync build events to it.

**Dropped because:**
- Adds a new external service with its own data store, users, and auth — duplicating what the platform already has.
- Solves only the Kanban gap, not chat, app dashboard, or log visibility.
- Integration requires maintaining a sync bridge between two user models.

### Option C: Unified web portal (chosen)

Build a purpose-built Next.js web application that is the operator's primary control plane. It covers:
- **Chat** — multi-turn intake conversation (same gateway endpoint as Telegram)
- **Apps dashboard** — all apps with live status, health indicators, and URLs
- **Kanban** — per-app board with pipeline-driven card state and operator-managed backlog
- **App detail** — build history, logs, CI pipeline status, Gitea issues
- **Settings** — user preferences and notification configuration

The portal is built on the **MUI Minimal JavaScript v7 Next.js template**, which ships with production-ready Chat, Kanban (dnd-kit), and Analytics dashboard sections that map directly to the required features.

**Chosen because:**
- Solves all four gaps: visibility, backlog, structured input, and Kanban — in one surface.
- Board state, cards, and history live in the platform's existing Postgres database. No external service.
- Input from the board (operator creates a Backlog card) calls the gateway API directly — no polling, no webhooks, no public endpoint required.
- Telegram is demoted to a **notification and quick-action channel** rather than the primary interface — it remains valuable for mobile operators who want push notifications and simple commands.
- The MUI Minimal template eliminates design and component work: Chat, Kanban, and App Dashboard sections are near-ready to wire up.

## Decision

**Build the unified web portal** as the platform's primary user interface, served by a new `portal` container at `portal.APP_DOMAIN`. The portal is a Next.js 15 application using the MUI Minimal JavaScript v7 template.

**Telegram remains** as a secondary channel for:
- Push notifications (build complete, app failed, remediation triggered)
- Quick commands (`/apps`, `/fix`, `/help`) for operators who prefer mobile

Operators who want full control — building apps, managing stories, inspecting logs — use the portal.

## Portal sections

| Section | Source in MUI template | Purpose |
|---------|------------------------|---------|
| Chat | `sections/chat` | Multi-turn intake conversation. Calls `POST /gateway/chat`. Streams agent replies. |
| Apps | `sections/app` + custom | Grid of all user apps with status chip, health indicator, live URL, last build timestamp. |
| Kanban | `sections/kanban` | Per-app board. Five fixed columns: Backlog / In Progress / Review / Done / Failed. Pipeline moves cards; operator manages Backlog. |
| App detail | `sections/analytics` (adapted) | Build history timeline, log tail, CI pipeline steps, linked Gitea issues. |
| Settings | `sections/user` (account) | User preferences, notification channel configuration. |

## Board data model

A board is implicit per app — no separate `boards` table is needed. A `board_cards` table stores card state:

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `app_id` | INTEGER | FK → `apps.id` |
| `title` | TEXT | Card title |
| `description` | TEXT | Body; pipeline events appended here |
| `list` | TEXT | `backlog`, `in_progress`, `review`, `done`, `failed` |
| `position` | INTEGER | Sort order within a list |
| `created_by` | TEXT | Agent name or `user` |
| `locked` | BOOLEAN | True for pipeline-created cards; operator cannot drag these |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

The gateway owns all writes to `board_cards`. Agents report pipeline events to the gateway; the gateway updates the card. The portal reads board state via `GET /apps/{app_id}/board`.

## Web authentication

The existing `users` table is keyed by `telegram_id`. Web auth is layered on top:

- `users` gains `email` (nullable) and `password_hash` (nullable) columns — existing Telegram-only users are unaffected
- Gateway exposes `POST /auth/login` (email + password → JWT) and `POST /auth/register-web`
- First-time web registration requires a Telegram invite code (same mechanism as bot registration)
- The portal authenticates all gateway requests with `Authorization: Bearer <jwt>`

## Consequences

### What is added

- New `portal` service in `docker-compose.yml` (Next.js, exposed via Traefik at `portal.APP_DOMAIN`)
- `board_cards` table in Postgres
- `users.email` and `users.password_hash` columns
- New gateway endpoints: `POST /auth/login`, `POST /auth/register-web`, `GET /apps/{app_id}/board`, `POST /apps/{app_id}/board/cards`, `PATCH /apps/{app_id}/board/cards/{card_id}`, `GET /apps/{app_id}/runs`, `GET /apps/{app_id}/issues`, `GET /apps/{app_id}/logs`

### What changes

- `docs/architecture/overview.md` — system context updated; portal added as primary interface; Telegram demoted to secondary
- `docs/product/vision.md` — portal added as a goal; Telegram listed as secondary channel

### What is removed

- The `kanban-bridge` service concept is dropped entirely. No Trello integration.

### What does not change

- The build pipeline is unaffected
- Telegram bot continues to work — operators are not forced to use the portal
- Gateway remains the single API backend; portal and Telegram bot are both clients of it
