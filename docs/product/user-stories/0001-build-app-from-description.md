---
title: "0001: Build an app from a plain-language description"
status: ready
last_updated: 2026-03-21
prd: docs/product/prd/0001-sovereign-agentic-foundry.md
---

## Story

As a non-engineer operator,
I want to describe an internal tool I need in plain language and have it deployed automatically,
so that I can use the tool without involving an engineer.

## Context

The operator knows what they need (e.g. "a form to record patient intake and store it in a spreadsheet") but has no coding ability. They interact via the portal chat or Telegram. The platform clarifies the spec, builds the app, and sends a URL when it is live.

## Acceptance criteria

- [ ] Given I am a registered operator, when I send a description in the portal chat, the system asks at most three clarifying questions before triggering a build.
- [ ] Given a build has been triggered, when I view the Kanban board for that app, I see the active pipeline stage as an In Progress card.
- [ ] Given the build pipeline completes successfully, when the app is deployed, I receive a notification with the live URL.
- [ ] Given the live URL, when I open it in a browser, the app responds with an HTTP 200 on its root route.
- [ ] Given the deployed app fails the acceptance check, when automated remediation succeeds, I receive a notification with the live URL (no intermediate failure notification).
- [ ] Given automated remediation is exhausted, when the app cannot be repaired, I receive a failure notification with a plain-English description of the issue.
- [ ] Error state: given I submit an empty or incomprehensible description, the system asks a clarifying question rather than triggering a build.

## Out of scope

- The operator cannot choose the tech stack; the platform decides based on app type.
- The operator cannot view generated source code from the portal (they can view it in Gitea).
- Multi-step builds with human approval gates.

## Notes

- App types: `form`, `dashboard`, `workflow`, `connector`, `assistant`. The intake agent infers the type; if ambiguous, it prompts with a menu.
- The build pipeline is fully automated after spec lock: no human intervention is required or possible.
