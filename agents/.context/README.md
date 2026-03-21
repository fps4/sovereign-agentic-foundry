---
title: Agents context
related:
  - docs/architecture/overview.md
  - docs/architecture/components/intake.md
  - docs/architecture/components/planner.md
  - docs/architecture/components/builder.md
  - docs/architecture/components/ui-designer.md
  - docs/architecture/components/reviewer.md
  - docs/architecture/components/test-writer.md
  - docs/architecture/components/acceptance.md
  - docs/architecture/components/remediation.md
  - docs/architecture/components/watchdog.md
---

## What this directory contains

LLM-driven agent services. Each subdirectory is a self-contained FastAPI service deployed as a Docker container.

## Directory map

| Path | Agent | Design doc |
|------|-------|------------|
| `coder/` | Builder agent — generates application code files from a build plan | `docs/architecture/components/builder.md` |
| `designer/` | Intake agent — multi-turn spec clarification conversation | `docs/architecture/components/intake.md` |
| `tester/` | Test-writer agent — generates pytest files (CI step) | `docs/architecture/components/test-writer.md` |
| `monitor/` | Watchdog — continuous container monitoring via Docker socket | `docs/architecture/components/watchdog.md` |

Note: directory names reflect the original naming. The canonical names in docs and the architecture are: `builder` (was `coder`), `intake` (was `designer`), `test-writer` (was `tester`), `watchdog` (was `monitor`).

## Key entry points

- Each agent: `<agent>/main.py` — FastAPI app, primary endpoint, lifespan handler
- LLM calls: all agents use `langchain-ollama`; model read from `OLLAMA_MODEL` env var
- Standards injection: YAML files from `standards/` are mounted at `/standards` and loaded at startup

## Conventions

- All agents expose `GET /health` and at least one domain endpoint (e.g. `POST /build`, `POST /plan`)
- Agents have no direct Postgres access except for the intake agent (which persists message history)
- Agents do not call each other — all inter-agent orchestration goes through the gateway
- JSON-structured logging via `python-json-logger`

## Gotchas

- The `coder/templates/` directory contains hardcoded fallback scaffolds used when LLM JSON parsing fails
- `monitor/main.py` is a background polling loop with no HTTP server — it exits if the Docker socket is unavailable
- Standards YAML files must be present at startup; missing standards cause the agent to fail to initialise
