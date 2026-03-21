---
title: "0001: Adopt Temporal for workflow orchestration"
status: accepted
date: 2026-03-14
related:
  - docs/architecture/overview.md
  - docs/architecture/components/gateway.md
---

## Context

The current gateway runs a linear agent pipeline:

```
User → Intake → Planner → Builder → UI Designer → Reviewer → Publisher → CI → Acceptance
```

State is tracked via direct Postgres writes (`apps.status`), step events are appended to `agent_runs`, and background builds are launched with bare `asyncio.create_task()` — fire-and-forget, no retries, no concurrency limits.

The following capabilities are planned that will strain this model:

1. **Compliance agent** — a gate that validates generated code against compliance rules before any commit reaches Gitea. A failing gate must block the build and be visible to admins.
2. **Multi-model routing** — agents will use different LLM backends depending on task type (e.g. fast/cheap model for classification, stronger model for code generation, dedicated model for compliance).
3. **Admin dashboards** — operators need real-time visibility into every pipeline run: which step is active, which failed, inputs/outputs per step, retry history.

These requirements together describe a **durable multi-step workflow with conditional gates** — not a job queue.

### Current pain points

| Issue | Impact |
|---|---|
| No retries or backoff | One LLM timeout = permanent build failure |
| Unbounded `asyncio.create_task()` | Unlimited concurrent builds; saturates Ollama under load |
| State fragmented across three systems | Chat state, build state in Postgres, CI state in Woodpecker |
| Adding a step requires code change + redeploy | Compliance agent cannot be inserted without touching the gateway |
| No real-time step visibility | Admins must poll `/runs` or wait for Telegram notification |
| Watchdog runs as independent polling loop | Cannot trigger orchestrated remediation; isolated from the build pipeline |

## Options considered

### Option A: Temporal

Temporal is a durable workflow execution engine. A **workflow** maps to one build pipeline. Each **activity** maps to one agent call. Workers are separate processes and can be configured per-activity with their own model.

**Fits the requirements because:**
- Compliance gate = activity with conditional logic; blocked workflows are first-class — visible and resumable
- Multi-model: each activity worker carries its own `OLLAMA_MODEL` env var; zero coupling between models
- Temporal UI provides a best-in-class real-time dashboard: workflow graph, step states, retry counts, input/output payloads per activity
- Durable execution: if an agent times out mid-build, Temporal resumes from the last completed activity, not from scratch
- Self-hosted via Docker; fits the existing compose-based infrastructure

**Tradeoffs:**
- Adds a Temporal server process (~200 MB) and one or more worker processes
- Medium operational overhead — Temporal requires its own database (can reuse Postgres)
- Steeper learning curve than a simple queue

### Option B: Hatchet

Hatchet is a newer workflow engine designed specifically for AI/LLM agent pipelines. It is Postgres-backed (no additional datastore needed) and ships with a built-in admin dashboard.

**Fits the requirements because:**
- Purpose-built for LLM agent workflows: step-level retries, conditional gates, approval steps
- Postgres-backed — reuses the existing `platform` database, no new infrastructure
- Lighter footprint than Temporal
- Built-in dashboard covers per-run visibility out of the box

**Tradeoffs:**
- Younger project; smaller community and less battle-tested than Temporal
- Fewer integrations and ecosystem tooling
- API surface is still evolving

### Option C: Expand LangGraph + custom observability

LangGraph could be extended with more nodes (compliance gate, retry loops) and wired to an OpenTelemetry exporter feeding the existing Grafana instance.

**Fits the requirements because:**
- Zero new infrastructure
- LangGraph supports multi-agent graphs, interrupt/approval for gates, and parallel node execution

**Tradeoffs:**
- LangSmith (the natural observability layer) is cloud-hosted — conflicts with the self-sovereign requirement
- Retries, concurrency limits, and durability across restarts are all DIY
- Wrong abstraction level: LangGraph is a conversation/agent graph library, not a durable task execution engine

## Decision

**Adopt Temporal** as the workflow orchestration layer.

The compliance gate requirement is the deciding factor. Temporal's model — workflow as a durable function, activity as an agent call — maps directly to the pipeline shape that is emerging. The Temporal UI provides the admin visibility that a custom Grafana dashboard would take significant effort to replicate.

Hatchet is a close second and remains a valid fallback if Temporal's operational overhead proves too high at this scale.

LangGraph stays in place for **conversational routing only** (classify intent, route to build vs. chat vs. clarify). It is not extended into the build pipeline.

## Consequences

### What changes

- A `workflow-worker` service is added to `docker-compose.yml` running Temporal Python SDK workers
- Temporal server is added (uses the existing Postgres instance as its backing store)
- `gateway/pipeline.py` `run_build()` is refactored into a Temporal workflow with activities:
  - `intake_activity` → calls Intake agent
  - `infra_activity` → calls Infra agent (conditional)
  - `plan_activity` → calls Planner agent
  - `build_activity` → calls Builder agent
  - `ui_design_activity` → calls UI Designer agent
  - `review_activity` → calls Reviewer agent
  - `publish_activity` → calls Publisher
  - `acceptance_activity` → calls Acceptance agent
  - `compliance_activity` → placeholder, returns approved initially
  - `notify_activity` → sends Telegram/portal notification
- Each activity gets its own retry policy and timeout
- `asyncio.create_task()` fire-and-forget is replaced by `client.start_workflow()`
- `agent_runs` table continues to be written to (Temporal events supplement, not replace, it)

### What does not change

- Woodpecker CI pipeline remains unchanged (build/test/deploy inside CI)
- Gitea remains the git host
- The portal and Telegram bot remain the user-facing interfaces
- `agent_runs` remains the audit trail visible to the portal

### Admin visibility

The Temporal UI (bundled with the server) is exposed internally. For the existing Grafana setup, a Temporal metrics exporter (Prometheus) can feed build duration, failure rates, and retry counts into existing dashboards.
