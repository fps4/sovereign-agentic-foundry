---
title: "Component design: Remediation agent"
status: proposed
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: remediation
related:
  - docs/architecture/overview.md
  - docs/architecture/components/acceptance.md
  - docs/architecture/components/watchdog.md
  - docs/architecture/components/planner.md
  - docs/architecture/components/builder.md
---

## Purpose

The remediation agent attempts automated repair of a failing application. It is triggered by the acceptance agent (post-deploy failure) or the watchdog (runtime degradation). It assembles the error context, produces a targeted repair plan, drives a partial rebuild through the planner and builder, and re-triggers deployment. If repair fails after the maximum retry count, it escalates to the operator.

This agent closes the automated loop: the platform promises no human approval gates, and remediation is what makes that hold beyond initial deployment.

## Responsibilities

**Owns:**
- Error analysis: mapping error context (logs, failing routes, stack traces) to a repair strategy
- Targeted repair plan: calling the planner with the original spec plus repair context, requesting a patch rather than a full rebuild
- Driving the partial rebuild through builder → reviewer → publisher
- Retry tracking: enforcing `MAX_RETRIES` and escalating when exceeded
- Escalation: setting `apps.status = needs_human` and notifying the operator with a plain-English summary when automated repair is exhausted

**Does not own:**
- Error detection (owned by the watchdog and acceptance agents)
- Code generation (owned by the builder agent)
- Test generation (owned by the test-writer agent, runs in CI)
- Deployment (handled by Woodpecker CI after publisher commits the patch)
- App status updates (owned by the gateway)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, `POST /remediate` endpoint |
| Context assembler | Fetches current source from Gitea; bundles error, logs, spec, and source into repair context |
| LLM analyser | Identifies error category (runtime crash, import failure, config error, logic bug) and drafts repair instructions |
| Retry tracker | Reads and increments `app_issues.remediation_attempts`; enforces `MAX_RETRIES` |
| Escalation handler | Generates operator-friendly summary; calls gateway to set status and trigger Telegram notification |

## Key flows

### Automated repair (happy path)

1. Gateway calls `POST /remediate` with `{app_name, error_hash, error_summary, logs, failing_routes}`
2. Context assembler fetches current source files from Gitea
3. LLM analyses error and produces repair instructions: `{error_category, affected_files, fix_description}`
4. Remediation calls planner `POST /plan` with original spec + repair instructions as context
5. Planner returns a targeted build plan (patch scope, not full rebuild)
6. Remediation drives builder → reviewer → publisher with the patch plan
7. Publisher commits patch; Woodpecker CI runs; acceptance validates the redeploy
8. On acceptance pass: gateway sets `apps.status = active`

### Infra-level failure (escalate immediately)

1. Error category is identified as infrastructure (OOM, disk full, network partition)
2. Remediation cannot address these with a code patch
3. Skips repair; immediately calls escalation handler
4. Gateway sets `apps.status = needs_human`; operator is notified with diagnosis

### Retry limit reached

1. `app_issues.remediation_attempts` reaches `MAX_RETRIES`
2. Remediation stops attempting repair
3. Escalation handler summarises all attempted fixes and their outcomes
4. Gateway sets `apps.status = needs_human`; operator receives full context

## Data owned

The remediation agent has no direct database access. Retry state is tracked via `app_issues.remediation_attempts`, but reads and increments are delegated to the gateway.

**Reads (via prompt context and external calls, not DB):**
- Current app source — fetched from Gitea per repair attempt
- Error context — received from gateway in the request body

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Gitea unreachable | Cannot fetch source; returns error to gateway; gateway sets `apps.status = failed` |
| Ollama unreachable | Cannot analyse error; escalates immediately to operator |
| Patch build fails reviewer | Remediation counts as one attempt; retry if below `MAX_RETRIES` |
| Infra-level error detected (OOM, disk) | Escalates immediately without attempting a code patch |
| All retries exhausted | Calls escalation handler; gateway sets `apps.status = needs_human`; operator notified with full repair history |

## Non-functional constraints

- Each repair attempt drives a partial build pipeline (planner → builder → reviewer → publisher → CI → acceptance); total time per attempt can be 5–15 minutes.
- Repair context is bounded by the LLM context window; source files are truncated if too large.
- No rollback mechanism; every repair attempt moves the repo forward.

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /remediate` | Gateway | Initiate automated repair for a failing app |
| `GET /health` | Traefik / gateway | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| Gitea HTTP API | Fetch current source files for repair context |
| `planner POST /plan` | Generate targeted patch build plan |
| `builder POST /build` | Execute patch plan |
| `reviewer POST /review` | Validate patched files before commit |
| `publisher POST /publish` | Commit patch and trigger CI |
| Ollama HTTP API | Error analysis and escalation summary generation |
| Gateway `POST /apps/{name}/status` | Update app status |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `MAX_RETRIES` | `3` | Maximum automated repair attempts per error hash before escalation |
| `REMEDIATION_LLM_PROVIDER` | `ollama` | LLM provider: `ollama`, `openai`, `anthropic` |
| `REMEDIATION_LLM_MODEL` | provider default | Model name. Defaults: `llama3.1:8b` (ollama), `gpt-4o` (openai), `claude-sonnet-4-6` (anthropic) |
| `REMEDIATION_LLM_API_KEY` | — | API key for the chosen provider. Falls back to `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`. Required when provider ≠ `ollama` |
| `OLLAMA_URL` | `http://ollama:11434` | Used only when `REMEDIATION_LLM_PROVIDER=ollama` |
| `GITEA_URL` | — | Internal Gitea base URL for fetching source |
| `GITEA_ADMIN_USER` / `GITEA_ADMIN_PASS` | — | Gitea API credentials |
| `ORCHESTRATOR_URL` | `http://gateway:8000` | Gateway base URL |

## Known limitations

- Repair context is bounded by the LLM context window; large apps may require source truncation, which can cause the LLM to miss the relevant file.
- Remediation only patches committed source; if the failure is in a dependency version or base image, a code patch will not resolve it.
- The retry count is per error hash — a new error introduced by a bad patch gets its own retry budget, which can mask a cycle of repairs that are making things worse.
- No mechanism to roll back to a previous known-good commit; remediation always moves forward.
