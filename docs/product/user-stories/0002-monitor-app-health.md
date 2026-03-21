---
title: "0002: Monitor the health of running apps"
status: ready
last_updated: 2026-03-21
prd: docs/product/prd/0001-sovereign-agentic-foundry.md
---

## Story

As an operator,
I want to see the health status and recent logs of my running apps from the portal,
so that I know whether my apps are functioning correctly without checking Gitea or Telegram.

## Context

Once an app is live, the operator needs visibility without developer tooling. The watchdog monitors containers continuously and creates Gitea issues for errors; the portal surfaces this as health indicators and log tails. Critical failures also trigger automated remediation.

## Acceptance criteria

- [ ] Given I am on the Apps dashboard, when one of my apps has status `active`, I see a green health indicator.
- [ ] Given an app has `degraded` or `failed` status, when I view the Apps dashboard, I see an amber or red health indicator respectively.
- [ ] Given I open an app's detail view, when the app has recent log entries, I see the last 100 log lines in the log tail section.
- [ ] Given an app has open Gitea issues, when I view the App detail, I see the issue titles and links.
- [ ] Given a breaking error is detected by the watchdog, when automated remediation succeeds, the app status returns to `active` without operator action.
- [ ] Given a breaking error is detected and remediation is exhausted, when I check the portal, I see the app status as `failed` with an error description.
- [ ] Error state: given the log service (Loki) is unavailable, when I open the log tail, I see an "logs unavailable" message rather than a blank panel.

## Out of scope

- Real-time log streaming (log tail is polled; SSE/WebSocket are deferred).
- Alerting to external systems (PagerDuty, email).
- Viewing logs for platform services (only deployed app containers are exposed).

## Notes

- Health indicators are derived from `apps.status` and the count of open `app_issues`.
- Log tail is proxied from Loki by the gateway; the portal does not call Loki directly.
