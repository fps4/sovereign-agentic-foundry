# Agent instructions

## Allowed

- Read any file in the repository
- Create and edit files in `agents/`, `orchestrator/`, `bots/`, `standards/`, `docs/`, `scripts/`
- Run: `docker compose up -d`, `docker compose logs -f <service>`, `docker compose build <service>`
- Run: `python scripts/e2e_test.py`

## Not allowed

- Modify `infra/` without explicit instruction — Traefik and log pipeline config affects all services
- Commit or push directly — output diffs for human review
- Edit `docs/architecture/decisions/` — propose new ADRs instead of modifying existing ones
- Modify `docker-compose.yml` network or volume names — `platform_platform` is referenced by deployed app containers at runtime

## How to run tests

```bash
# End-to-end (requires full stack running)
ORCHESTRATOR_URL=http://localhost:8000 python scripts/e2e_test.py

# Single service logs
docker compose logs -f <service-name>

# Rebuild and restart a single service after code changes
docker compose build <service> && docker compose up -d <service>
```

## Agent roster

| Agent | Container | Role |
|-------|-----------|------|
| Intake | `intake` | Multi-turn clarification conversation; converges on a locked spec and hands off to the gateway. |
| Planner | `planner` | Takes a locked spec and produces a build plan: file list, patterns, stack decisions, resource requirements. |
| Builder | `builder` | Executes the build plan; generates all application code files. No architectural decisions. |
| UI Designer | `ui-designer` | Generates styled, accessible frontend templates from the spec and route manifest. |
| Reviewer | `reviewer` | Checks generated files against platform standards before commit; returns pass or fix instructions. |
| Test Writer | `test-writer` | Generates pytest files from application source; invoked as a Woodpecker CI step. |
| Acceptance | `acceptance` | Post-deploy smoke check; exercises live app routes against the spec; triggers remediation on failure. |
| Remediation | `remediation` | Analyses failures from the acceptance agent or watchdog; drives a targeted patch rebuild; escalates when retries are exhausted. |
| Infra | `infra` | Provisions per-app external resources (Postgres DB, pgvector); injects secrets; handles teardown on app deletion. |
| Watchdog | `watchdog` | Polls all running app containers via Docker socket; reports errors to gateway. |

## Reliability standards

All agents follow the reliability contracts defined in `standards/reliability.yaml` (sourced from the agentic-standards package):

- **SLO targets:** 99.9% availability; p95 latency within tier budget (FAST < 3 s, STANDARD < 30 s, STRONG < 60 s)
- **Golden signals:** latency (success and error separately), traffic (requests/min), errors (by type), saturation (CPU/memory; alert at 80%)
- **Burn rate alerts:** critical at 14.4× error rate over a 5 m:1 h window; warning at 6× over a 30 m:6 h window
- **Error budget policy:** if more than 50% of the monthly error budget is consumed with more than 50% of the window remaining, non-critical work is halted
- **Agent health contract:** `GET /health` must respond in < 2 s; callers retry degraded agents 3 times with exponential backoff before escalating
- **LLM failure policy:** LLM timeout and malformed JSON output are retryable errors; after `max_retries` the agent emits a `RunEvent` with `status="error"` and the gateway surfaces the failure to the admin

## Orchestrator boundary rule

The gateway must not add direct HTTP calls to agents — new agents must be wired through workflow activities (see `patterns/05-orchestrator-boundary.md` in agentic-standards). Violating this rule makes the workflow unrecoverable on restart and bypasses audit logging.

## Key conventions

- All agents are FastAPI services with a `/health` endpoint and JSON-structured logging via `python-json-logger`
- LLM calls use `langchain-ollama`; the model is read from the `OLLAMA_MODEL` env var
- Database access is async via `asyncpg`; connection pools are initialised in `lifespan` handlers
- Standards YAML files in `standards/` are loaded at startup and injected into LLM system prompts — do not inline them into agent code
- Generated app Dockerfiles must use non-root users (enforced by `standards/security.yaml`)
- App and repo names use kebab-case (enforced by `standards/naming.yaml`)

## Before proposing changes

1. Read the component design doc in `docs/architecture/components/` for the service you are modifying
2. Check `docs/architecture/decisions/` for any ADR that covers the area
3. If your change affects the build pipeline flow, update `docs/architecture/overview.md`
4. If a significant trade-off is being made, propose a new ADR in `docs/architecture/decisions/`
