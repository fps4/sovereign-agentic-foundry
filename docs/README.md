# Documentation index

## Product

| File | Description |
|------|-------------|
| [`product/vision.md`](product/vision.md) | Problem, users, goals, non-goals, success metrics |
| [`product/prd/0001-sovereign-agentic-foundry.md`](product/prd/0001-sovereign-agentic-foundry.md) | PRD-0001: Core platform — build apps from natural language |

### User stories

| File | Description |
|------|-------------|
| [`product/user-stories/0001-build-app-from-description.md`](product/user-stories/0001-build-app-from-description.md) | As an operator, I want to describe an app and have it deployed |
| [`product/user-stories/0002-monitor-app-health.md`](product/user-stories/0002-monitor-app-health.md) | As an operator, I want to see the health of my running apps |
| [`product/user-stories/0003-manage-app-kanban.md`](product/user-stories/0003-manage-app-kanban.md) | As an operator, I want to manage my app backlog on a Kanban board |

## Architecture

| File | Description |
|------|-------------|
| [`architecture/overview.md`](architecture/overview.md) | C4 L1/L2: system context and container map |
| [`architecture/data-model.md`](architecture/data-model.md) | Database entities and relationships |

### Generated application

| File | Description |
|------|-------------|
| [`architecture/components/generated-app.md`](architecture/components/generated-app.md) | Runtime model for generated apps: app types, resource model, interface contract, lifecycle |
| [`architecture/components/template-library.md`](architecture/components/template-library.md) | Template library: API and frontend base scaffolds used by builder and ui-designer |

### Components — agents

| File | Description |
|------|-------------|
| [`architecture/components/intake.md`](architecture/components/intake.md) | Intake agent — multi-turn spec clarification |
| [`architecture/components/planner.md`](architecture/components/planner.md) | Planner agent — spec to build plan |
| [`architecture/components/builder.md`](architecture/components/builder.md) | Builder agent — code file generation |
| [`architecture/components/ui-designer.md`](architecture/components/ui-designer.md) | UI designer agent — frontend templates |
| [`architecture/components/reviewer.md`](architecture/components/reviewer.md) | Reviewer agent — standards quality gate |
| [`architecture/components/test-writer.md`](architecture/components/test-writer.md) | Test-writer agent — pytest generation (CI step) |
| [`architecture/components/acceptance.md`](architecture/components/acceptance.md) | Acceptance agent — post-deploy smoke check |
| [`architecture/components/remediation.md`](architecture/components/remediation.md) | Remediation agent — automated error repair |

### Components — services

| File | Description |
|------|-------------|
| [`architecture/components/gateway.md`](architecture/components/gateway.md) | Gateway — API facade, registry, pipeline dispatch |
| [`architecture/components/publisher.md`](architecture/components/publisher.md) | Publisher — Gitea commit and CI activation |
| [`architecture/components/infra.md`](architecture/components/infra.md) | Infra agent — per-app resource provisioning |
| [`architecture/components/watchdog.md`](architecture/components/watchdog.md) | Watchdog — continuous container monitoring |
| [`architecture/components/portal.md`](architecture/components/portal.md) | Portal — primary web interface (chat, dashboard, Kanban, logs) |
| [`architecture/components/telegram-bot.md`](architecture/components/telegram-bot.md) | Telegram bot — secondary mobile interface |

## Decisions

| File | Description |
|------|-------------|
| [`architecture/decisions/0001-workflow-orchestration.md`](architecture/decisions/0001-workflow-orchestration.md) | ADR-0001: Adopt Temporal for workflow orchestration |
| [`architecture/decisions/0002-kanban-board-integration.md`](architecture/decisions/0002-kanban-board-integration.md) | ADR-0002: Unified web portal as primary user interface |
| [`architecture/decisions/0003-tenant-model.md`](architecture/decisions/0003-tenant-model.md) | ADR-0003: Introduce tenant as the primary scoping unit |
| [`architecture/decisions/0004-tenant-infra-layer.md`](architecture/decisions/0004-tenant-infra-layer.md) | ADR-0004: Per-tenant database infrastructure layer |
| [`architecture/decisions/0005-template-library.md`](architecture/decisions/0005-template-library.md) | ADR-0005: Template library for generated app scaffolding |

## Guides

| File | Description |
|------|-------------|
| [`guides/setup.md`](guides/setup.md) | First-time setup from scratch |
| [`guides/deployment.md`](guides/deployment.md) | Deploying and managing the stack |
