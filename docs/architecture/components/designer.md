---
title: "Component design: Designer agent"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: designer
related:
  - docs/architecture/overview.md
  - docs/architecture/components/orchestrator.md
---

## Purpose

The designer agent runs a multi-turn clarification conversation with the user until their app requirement is unambiguous. It produces a structured spec and signals the orchestrator to trigger a build. It is the single entry point for all user messages — the orchestrator always delegates `/chat` here.

## Responsibilities

**Owns:**
- Multi-turn conversation FSM until spec is complete
- App type inference (`form`, `dashboard`, `workflow`, `connector`, `assistant`)
- Structured spec production: `{name, description, app_type, stack, requirements}`
- Conversation state persistence in Postgres

**Does not own:**
- Code generation (owned by the coder agent)
- User registration (owned by the orchestrator)
- Telegram message formatting (owned by the Telegram bot)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, `POST /design` endpoint, conversation loop |
| LangChain / Ollama | LLM calls for clarification turns and spec extraction |
| Postgres (`messages` table) | Persist conversation history; load context for each turn |

## Key flows

### Happy path: spec reached in one turn

1. Orchestrator calls `POST /design` with `{user_id, message, history}`
2. Designer runs LLM prompt with message history + standards
3. LLM returns either a clarifying question or a complete spec (detected by JSON output structure)
4. If spec complete: returns `{reply, spec, build_triggered: true}`
5. Orchestrator triggers build

### Multi-turn clarification

1. LLM returns a clarifying question (no valid spec JSON)
2. Designer returns `{reply: "<question>", build_triggered: false}`
3. Orchestrator sets `users.design_mode = true`, stores reply in `messages`
4. User answers via Telegram → next call to `POST /design` with updated history
5. Continues until spec is extracted

### App type ambiguity

If the user's description could match multiple app types, the designer prompts with an explicit type menu rather than guessing.

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /design` | Orchestrator | Process one conversation turn |
| `GET /health` | Traefik / orchestrator | Health check |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `OLLAMA_MODEL` | `llama3.1:8b` | Model for clarification and spec extraction |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama base URL |
| `DATABASE_URL` | — | asyncpg DSN for message history |
| `STANDARDS_PATH` | `/standards` | Mount path for YAML standards files |

## Known limitations

- No timeout on the clarification loop — a user who never resolves ambiguity will keep a `design_mode = true` row open indefinitely.
- Spec extraction relies on LLM JSON output; malformed output falls back to asking another clarifying question, which may loop.
