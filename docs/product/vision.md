---
title: Product vision — Sovereign Agentic Foundry
status: current
last_updated: 2026-03-21
owners: [platform-team]
related:
  - docs/architecture/overview.md
---

## Problem

Building and deploying internal tools requires engineering time that most small teams — especially in healthcare, operations, and public sector — do not have. Even simple forms, dashboards, and workflow trackers require provisioning infrastructure, writing code, setting up CI, and maintaining containers. The barrier is not the idea; it is the execution.

Existing low-code platforms trade away data sovereignty: the data leaves the organisation, the vendor controls uptime, and customisation hits a ceiling.

## Users

**Primary — the non-engineer operator**: a healthcare administrator, ops lead, or team manager who has a clear internal need (track patient intake, monitor bed occupancy, route referrals) but no engineering resource. They communicate in plain language and need a result, not a development environment.

**Secondary — the platform administrator**: an engineer responsible for the organisation's internal tooling. They want predictable, standards-compliant output they can trust and audit, running on infrastructure they control.

## Interaction channels

The platform exposes two interfaces. Operators choose either or both.

**Web portal (primary)** — a browser-based control plane at `portal.APP_DOMAIN`. Provides: multi-turn chat to build apps, an apps dashboard with health indicators, a per-app Kanban board showing build progress and backlog, app detail with build history and logs, and settings. This is the recommended interface for operators doing structured work.

**Telegram bot (secondary)** — a mobile-first interface for operators who want push notifications and quick commands. Suitable for checking app status, triggering a build from a phone, and receiving alerts. Remains available alongside the portal; operators are not required to use either exclusively.

## Goals

- An operator can describe a need in plain language and receive a running application at a public URL without any engineering involvement
- The operator has a unified web interface showing all their apps, build status, pipeline progress, and a backlog — without needing Telegram
- Generated applications conform to the organisation's architecture and security standards automatically
- All infrastructure — code, data, CI, runtime — runs on hardware the organisation controls
- The operator can monitor app health and report issues from the web portal or Telegram

## Non-goals

- General-purpose software development (multi-developer collaboration, branching workflows, code review)
- Consumer-facing applications (the platform generates internal tools only)
- Cloud-hosted inference or external SaaS dependencies
- Supporting arbitrary tech stacks (the platform opinionates on Python/FastAPI and Node/Express)

## Tenant model

The platform scopes all resources — apps, Gitea organisations, build history — to a **tenant**, not directly to an individual user login.

**v1 (single-user tenant):** registration creates one tenant per operator automatically. The operator is unaware of the tenant concept — the experience is identical to direct ownership. Each tenant gets a private Gitea org and all apps belong to it.

**Future — team tenant:** an operator invites a second user to their tenant. Both users see the same apps, Kanban boards, and build history. No changes to apps, board cards, or any agent code are required — only a `tenant_memberships` join table is added.

**Future — shared tenant:** a platform-administrator-created tenant whose apps are visible to all registered users. Use case: platform-wide utilities or demo apps.

This model is designed to be invisible to v1 operators while enabling multi-user and org-wide scenarios without architectural rework. See `docs/architecture/decisions/0003-tenant-model.md` for the full decision record.

## Success metrics

**Leading:** percentage of build requests that reach a live URL without human intervention in the pipeline.

**Lagging:** time from first message to live app URL for a new operator with no prior setup.
