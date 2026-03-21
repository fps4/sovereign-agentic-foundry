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

## Goals

- An operator can describe a need in plain language and receive a running application at a public URL without any engineering involvement
- Generated applications conform to the organisation's architecture and security standards automatically
- All infrastructure — code, data, CI, runtime — runs on hardware the organisation controls
- The operator can monitor app health and report issues without leaving Telegram

## Non-goals

- General-purpose software development (multi-developer collaboration, branching workflows, code review)
- Consumer-facing applications (the platform generates internal tools only)
- Cloud-hosted inference or external SaaS dependencies
- Supporting arbitrary tech stacks (the platform opinionates on Python/FastAPI and Node/Express)

## Success metrics

**Leading:** percentage of build requests that reach a live URL without human intervention in the pipeline.

**Lagging:** time from first message to live app URL for a new operator with no prior setup.
