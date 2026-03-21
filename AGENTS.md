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
