---
title: "Component design: Portal"
status: proposed
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: portal
related:
  - docs/architecture/overview.md
  - docs/architecture/components/gateway.md
  - docs/architecture/data-model.md
  - docs/architecture/decisions/0002-kanban-board-integration.md
---

## Purpose

The portal is the operator's primary web-based control plane. It provides a unified interface for building apps via chat, monitoring running apps, managing work on per-app Kanban boards, and inspecting build history and logs. It is a Next.js 15 application built on the MUI Minimal JavaScript v7 template.

The portal is a pure client of the gateway API. It owns no business logic and writes no data directly to Postgres — all mutations go through the gateway.

## Responsibilities

**Owns:**
- All web UI rendering and client-side state
- Authentication token management (JWT storage, refresh)
- Real-time update polling for build status and chat replies
- Drag-and-drop card management on the Kanban board

**Does not own:**
- Business logic (owned by gateway and agents)
- Board card state (owned by gateway / Postgres)
- App build pipeline (owned by gateway and agents)
- Telegram notifications (owned by Telegram bot)

## Internal structure

| Component | Technology | Notes |
|-----------|-----------|-------|
| `src/app/` | Next.js App Router | Page routes |
| `src/sections/` | MUI Minimal sections | Adapted from template; one folder per section |
| `src/lib/api.js` | Axios + SWR | All gateway calls; base URL from `NEXT_PUBLIC_GATEWAY_URL` |
| `src/auth/` | JWT context | Token stored in `httpOnly` cookie via Next.js middleware |
| `src/theme/` | MUI theme | Minimal v7 theme; brand colours overridden |

## Sections

### Chat

The intake conversation surface. Equivalent to sending a free-text message in Telegram.

- Renders conversation history from `GET /messages?user_id=`
- Sends messages via `POST /chat`
- Polls or uses SSE for streaming agent replies
- Shows a "build started" banner when gateway returns `build_triggered: true`
- Source section: `sections/chat` in MUI template (near-complete mapping)

### Apps dashboard

Overview of all apps belonging to the authenticated user.

- Card grid showing: app name, type badge, status chip (`building`, `active`, `failed`, `degraded`), live URL link, last updated timestamp
- Health indicator: green/amber/red derived from `apps.status` and open issue count
- Quick actions: open Kanban, view detail, delete
- Source section: `sections/app` (adapted; uses existing widget and card components)

### Kanban

Per-app drag-and-drop board. Navigated to from the Apps dashboard.

- Five fixed columns: `Backlog` / `In Progress` / `Review` / `Done` / `Failed`
- Cards show title, creator badge (agent name or "you"), and last-updated timestamp
- Operator can create cards in `Backlog` (triggers `POST /apps/{app_id}/board/cards`)
- Operator can drag cards between `Backlog` and any column (triggers `PATCH /apps/{app_id}/board/cards/{card_id}`)
- Pipeline-created cards are read-only (cannot be dragged by operator) — indicated by a lock icon
- Source section: `sections/kanban` (dnd-kit columns + cards; minimal adaptation needed)

### App detail

Deep-dive view for a single app. Navigated to from the Apps dashboard or a Kanban card. Tabs:

- **Docs** — rendered markdown documentation from the app's Gitea repo (`GET /apps/{app_id}/docs`). Shows `README.md` by default; a file list sidebar lets the operator navigate to `docs/api.md` and other generated doc files. Rendered with `react-markdown`. This is the primary tab — it surfaces the app's usage instructions, API reference, and data model without requiring Gitea access.
- **Build timeline** — chronological list of `agent_runs` steps with status and duration (`GET /apps/{app_id}/runs`)
- **Log tail** — last N log lines from the running container (`GET /apps/{app_id}/logs`; sourced from Loki via gateway proxy)
- **CI pipeline** — Woodpecker build status per step, linked from `apps.repo_url`
- **Issues** — open Gitea issues for the app (`GET /apps/{app_id}/issues`); links open in Gitea
- Source section: `sections/analytics` timeline + `sections/file-manager` (for log browsing and doc file tree, adapted)

### Settings

User account and notification preferences.

- Change password
- Configure notification channels (Telegram on/off, future: email)
- View registered Gitea org and invite code
- Source section: `sections/user` account page

## Key flows

### Authentication

1. Operator visits portal; Next.js middleware checks for valid JWT cookie
2. No valid JWT → redirect to `/auth/sign-in`
3. Operator submits email + password → `POST /gateway/auth/login` → JWT returned
4. JWT stored as `httpOnly` cookie by Next.js middleware
5. All subsequent gateway calls attach `Authorization: Bearer <token>` header
6. JWT expiry → 401 from gateway → Next.js middleware redirects to sign-in

### Starting a build

1. Operator types in the Chat section and submits
2. Portal calls `POST /chat` with `{user_id, message}`
3. Gateway delegates to intake agent; returns `{reply, spec_locked}`
4. Portal renders reply; if `spec_locked: true`, shows "build started" banner
5. Portal polls `GET /apps` every 2 s; status chip transitions `queued → building → active`

### Kanban drag-and-drop

1. Operator drags a card from `Backlog` to `In Progress`
2. dnd-kit fires `onDragEnd`; portal calls `PATCH /apps/{id}/board/cards/{card_id}` with `{list: "in_progress", position}`
3. Gateway updates `board_cards`; returns updated card
4. Portal optimistically updates local state; reverts on error

### Reading app documentation

1. Operator opens App detail and lands on the Docs tab
2. Portal calls `GET /apps/{id}/docs` (no path parameter → gateway fetches `README.md`)
3. Gateway proxies the file from Gitea; returns `{path, content, last_updated}`
4. Portal renders `content` with `react-markdown`; displays `last_updated` timestamp
5. If the app has a `docs/` directory, gateway returns a `doc_files` list alongside `README.md`
6. Operator clicks a file in the sidebar → portal calls `GET /apps/{id}/docs?path=docs/api.md`
7. Portal replaces the rendered content with the new file; browser URL updates with `?doc=docs/api.md` for shareable links

### Real-time build updates

1. Portal polls `GET /apps/{id}/board` every 5 s while app status is `building`
2. Gateway returns updated board cards (pipeline steps create/move cards)
3. Portal re-renders Kanban columns with new card positions

## Data owned

The portal owns no persistent data. All state is in Postgres via the gateway.

**Reads (via gateway):**
- `apps`, `messages`, `board_cards`, `agent_runs` — for rendering all sections

## External interfaces

### Calls (all via gateway)

| Endpoint | Purpose |
|----------|---------|
| `POST /auth/login` | Web sign-in |
| `POST /chat` | Send chat message / build request |
| `GET /messages` | Load conversation history |
| `GET /apps` | Apps dashboard list |
| `GET /apps/{id}/board` | Kanban board state |
| `POST /apps/{id}/board/cards` | Operator creates a Backlog card |
| `PATCH /apps/{id}/board/cards/{card_id}` | Move or update a card |
| `GET /apps/{id}/runs` | Build timeline |
| `GET /apps/{id}/logs` | Log tail (gateway proxies Loki) |
| `GET /apps/{id}/issues` | Gitea issues list |
| `GET /apps/{id}/docs` | App README.md content (gateway proxies from Gitea) |
| `GET /apps/{id}/docs?path={filepath}` | Specific doc file from app's `docs/` directory |
| `POST /delete-app` | Delete an app |

### No direct database access

The portal never connects to Postgres. All reads and writes go through the gateway.

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Gateway unreachable | SWR shows stale data; error banner displayed |
| Card drag fails (PATCH returns error) | Optimistic update reverted; card snaps back to previous position |
| JWT expired mid-session | Next.js middleware detects 401; redirects to sign-in; session state preserved in localStorage for restore |
| Chat reply timeout | Spinner shown; user can retry; previous messages preserved |

## Configuration

| Variable | Notes |
|----------|-------|
| `NEXT_PUBLIC_GATEWAY_URL` | Gateway base URL, e.g. `http://gateway:8000` (internal) or `https://api.APP_DOMAIN` (external) |
| `NEXTAUTH_SECRET` | Secret for cookie signing |

## Deployment

Served at `portal.APP_DOMAIN` via Traefik. The Next.js app runs in standalone output mode (`output: 'standalone'` in `next.config.mjs`). Static assets are served by the Next.js server; no separate nginx container is needed.

```yaml
portal:
  build: ./portal
  labels:
    - "traefik.http.routers.portal.rule=Host(`portal.${APP_DOMAIN}`)"
  environment:
    - NEXT_PUBLIC_GATEWAY_URL=http://gateway:8000
```

## Non-functional constraints

- No real-time push: build status and chat replies are polled (1–5 s interval). SSE or WebSocket upgrades are deferred.
- All data access goes through the gateway; portal performance is bounded by gateway latency.

## Known limitations

- No real-time push: build status and chat replies are polled (1–5 s interval). SSE or WebSocket upgrades are deferred.
- Log tail is capped by the gateway at a fixed line count; live streaming is a future enhancement.
- Mobile experience relies on MUI's responsive layout; not a native app.
