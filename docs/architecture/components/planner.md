---
title: "Component design: Planner agent"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: planner
related:
  - docs/architecture/overview.md
  - docs/architecture/components/intake.md
  - docs/architecture/components/builder.md
  - docs/architecture/components/infra.md
  - docs/architecture/components/template-library.md
  - docs/architecture/decisions/0005-template-library.md
---

## Purpose

The planner agent translates a locked spec into a concrete build plan: the file structure, architectural patterns, dependency choices, stack configuration, and external resource requirements. It makes all design decisions so that the builder agent can focus exclusively on generating code without reasoning about architecture.

## Responsibilities

**Owns:**
- Template selection: which API template (`fastapi-base` or `express-base`) and whether a frontend is required — from `standards/templates.yaml` rules
- Database selection: `sqlite`, `postgres`, `mongo`, or `none` — from `templates.yaml` db selection rules and spec analysis
- File and directory structure decisions for the target app type
- Pattern selection from `patterns.yaml` (e.g. repository pattern, middleware chain)
- Dependency manifest (which libraries, which versions, layered on top of template deps)
- External resource requirements: signals whether the app needs tenant Postgres, tenant MongoDB, or no infra agent call
- Test strategy: which routes and behaviours the test-writer should target

**Does not own:**
- Code file content (owned by the builder agent)
- Frontend template generation (owned by the ui-designer agent)
- Infrastructure provisioning (owned by the infra agent; planner only declares requirements)
- Standards compliance review (owned by the reviewer agent)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, `POST /plan` endpoint |
| LangChain / Ollama | LLM calls for plan generation; receives spec + standards + available patterns |
| Plan validator | Structural validation of LLM output before returning to gateway |

## Key flows

### Happy path

1. Gateway calls `POST /plan` with `{spec, provisioned_resources}` (provisioned resources may be empty)
2. Planner loads `patterns.yaml`, `naming.yaml`, `security.yaml` and injects into LLM system prompt
3. LLM returns a build plan:
   ```json
   {
     "template": "fastapi-base",
     "template_version": "v1",
     "frontend": true,
     "frontend_template": "mui-minimal",
     "stack": "fastapi",
     "db": "postgres",
     "files": [{"path": "api/routes/items.py", "description": "CRUD routes for items"}],
     "dependencies": ["sqlalchemy", "alembic"],
     "routes": [{"method": "GET", "path": "/items", "description": "List all items"}],
     "resources_required": ["postgres"],
     "test_targets": [{"route": "GET /items", "scenario": "returns 200 with empty list"}]
   }
   ```
4. Plan validator checks required fields are present and that `template` is a valid id from `standards/templates.yaml`
5. Returns plan to gateway

### Resource requirements identified

1. LLM sets `db: "postgres"` or `db: "mongo"` in the plan
2. Plan includes `"resources_required": ["postgres"]` or `["mongo"]`
3. Gateway calls infra agent `POST /provision` with `{tenant_id, app_name, resources}`
4. Infra provisions tenant container (if needed) and per-app database; returns connection env vars
5. Builder receives provisioned resource context and references the env vars in generated code

### Plan validation failure

1. LLM output missing required fields or structurally invalid
2. Planner retries with a more constrained prompt (JSON schema enforcement)
3. After `MAX_PLAN_RETRIES`: returns error to gateway; build is aborted

## Data owned

The planner agent has no direct database access. All data persistence (agent run logging, app status) is handled by the gateway.

**Reads (via prompt context, not DB):**
- Locked spec — received from gateway in the request body
- Provisioned resource context — received from gateway in the request body
- Standards YAML files (`patterns.yaml`, `naming.yaml`, `security.yaml`) — loaded from filesystem at startup

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Ollama unreachable | Returns HTTP 503 to gateway; build pipeline is aborted |
| Plan validation failure | Retries with more constrained JSON schema prompt; after `MAX_PLAN_RETRIES` returns error to gateway |
| Missing required fields in plan | Plan validator rejects output; treated as validation failure and retried |
| Standards files not found at startup | Planner fails to start; logged as a misconfiguration |

## Non-functional constraints

- Plan generation involves one Ollama call; latency is typically 5–30 s depending on spec complexity and model.
- The plan must fit in a single LLM response; very large or multi-component app specs may produce incomplete plans.
- Planner has no feedback loop from the reviewer; if a selected pattern consistently causes standards violations, the issue must be addressed in `patterns.yaml`, not in the planner.

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /plan` | Gateway | Generate a build plan from a locked spec |
| `GET /health` | Traefik / gateway | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| Ollama HTTP API | LLM plan generation |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `PLANNER_LLM_PROVIDER` | `ollama` | LLM provider: `ollama`, `openai`, `anthropic` |
| `PLANNER_LLM_MODEL` | provider default | Model name. Defaults: `llama3.1:8b` (ollama), `gpt-4o` (openai), `claude-sonnet-4-6` (anthropic). `qwen2.5-coder:32b` recommended when using Ollama with sufficient VRAM |
| `PLANNER_LLM_API_KEY` | — | API key for the chosen provider. Falls back to `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`. Required when provider ≠ `ollama` |
| `OLLAMA_URL` | `http://ollama:11434` | Used only when `PLANNER_LLM_PROVIDER=ollama` |
| `STANDARDS_PATH` | `/standards` | Mount path for YAML standards files |
| `MAX_PLAN_RETRIES` | `2` | Retry attempts on plan validation failure before aborting |

## Known limitations

- Plan quality degrades for `connector` and `assistant` app types where the operator's requirements tend to be underspecified; intake must elicit sufficient detail before locking the spec.
- The planner has no feedback loop from the reviewer — if a pattern it selects consistently causes standards violations, there is no automated correction signal.
- Template selection is rule-based (from `templates.yaml`); the LLM cannot override the template choice even if the spec implies a different stack. Stack overrides require updating `templates.yaml`.
