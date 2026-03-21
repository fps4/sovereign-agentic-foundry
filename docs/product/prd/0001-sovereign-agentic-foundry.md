---
title: "0001: Core platform — build and deploy apps from natural language"
status: approved
last_updated: 2026-03-21
owners: [platform-team]
related:
  - docs/product/vision.md
  - docs/product/user-stories/0001-build-app-from-description.md
  - docs/product/user-stories/0002-monitor-app-health.md
  - docs/product/user-stories/0003-manage-app-kanban.md
---

## Summary

The core platform enables a non-engineer operator to describe an internal tool in plain language and receive a running application at a public URL — with no engineering involvement after the initial platform setup. This PRD covers the complete operator journey: spec clarification via the web portal or Telegram, automated build and deploy pipeline, app health monitoring, and backlog management via a Kanban board.

This advances the vision goal: "An operator can describe a need in plain language and receive a running application at a public URL without any engineering involvement."

## Problem statement

Healthcare administrators, ops leads, and team managers have internal tool needs (patient intake forms, bed occupancy dashboards, referral routing workflows) but no engineering resource to build them. Existing low-code platforms require vendor accounts and export data off-premises. The gap is not imagination — it is execution access.

## Users and context

**Primary:** Non-engineer operator. When they identify a repetitive manual process, they want to describe it in plain language and have a working app running on their organisation's infrastructure, so they can redirect staff effort away from the manual process.

**Secondary:** Platform administrator. When an operator's app is deployed, they want to inspect the build output, review logs, and trust that the generated code meets their organisation's standards.

## Scope

### In scope

- Multi-turn spec clarification conversation (web portal chat or Telegram)
- Automated five-stage build pipeline: plan → build → UI → review → publish
- Woodpecker CI integration: test generation → pytest → docker build → deploy
- Post-deploy acceptance check; automated remediation on failure
- Per-app Kanban board tracking pipeline progress and operator backlog
- Web portal with chat, apps dashboard, Kanban, app detail (logs, build history, issues)
- Telegram bot as secondary interface for notifications and quick commands
- Five app types: `form`, `dashboard`, `workflow`, `connector`, `assistant`
- Self-hosted deployment via Docker Compose; no external API keys

### Out of scope

- Multi-developer collaboration on a single app (branching, code review, merge requests)
- Consumer-facing applications; the platform generates internal tools only
- Cloud-hosted inference; all LLM inference is local via Ollama
- Arbitrary tech stacks; the platform generates Python/FastAPI and Node/Express only
- Backup and restore of per-app databases
- Email notifications (deferred; Telegram and portal are the supported channels)

## Requirements

### Functional requirements

1. An operator can start a new app build by sending a plain-language description in the portal chat or via the Telegram bot.
2. The intake agent asks clarifying questions until the spec is unambiguous; the operator can answer in the same chat turn.
3. The operator receives a notification (portal or Telegram) when their app is live, including the URL.
4. A failed build triggers automated remediation; the operator is only notified if remediation is exhausted.
5. Each app has a dedicated Kanban board with five columns: Backlog, In Progress, Review, Done, Failed.
6. Pipeline events (each build stage) automatically create and move cards on the Kanban board.
7. The operator can create cards in the Backlog column from the portal without starting a chat.
8. Pipeline-created cards cannot be manually moved by the operator (locked).
9. The operator can view the build history, log tail, and CI pipeline status for any app from the portal.
10. The operator can delete an app; deletion archives the app and tears down its provisioned infrastructure.
11. All generated applications conform to the organisation's standards (naming, security, patterns) automatically.
12. The entire platform runs on a single Docker host with a single `docker compose up -d`.

### Non-functional requirements

- All data (code, builds, runtime, logs) remains on the organisation's infrastructure — no external SaaS.
- The platform must function without internet access after initial Docker image pulls.
- Generated apps must use non-root Docker users (security standard).
- Web portal authentication uses email + password with bcrypt; first-time registration requires a Telegram invite code.

## Open questions

| Question | Owner | Due |
|----------|-------|-----|
| Should the operator be able to trigger a rebuild of an existing app from the portal? | platform-team | 2026-04-01 |
| What is the retention policy for `agent_runs` and `messages`? | platform-team | 2026-04-01 |

## Out of scope decisions deferred to engineering

- Workflow orchestration engine choice (Temporal vs. bare asyncio) — see ADR-0001
- LLM model selection per agent type
- Postgres connection pool sizing
- Log retention policy in Loki
