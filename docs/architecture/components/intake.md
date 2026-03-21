---
title: "Component design: Intake agent"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: intake
related:
  - docs/architecture/overview.md
  - docs/architecture/components/gateway.md
---

## Purpose

The intake agent runs a multi-turn clarification conversation with the operator until their app requirement is unambiguous. It produces a locked, structured spec and signals the gateway to trigger the build pipeline. It is the single entry point for all user messages — the gateway always delegates `/chat` here.

## Responsibilities

**Owns:**
- Multi-turn conversation FSM until spec is locked
- App type inference (`form`, `dashboard`, `workflow`, `connector`, `assistant`)
- Structured spec production: `{name, description, app_type, stack, requirements}`
- Conversation state persistence in Postgres

**Does not own:**
- Build planning (owned by the planner agent)
- Code generation (owned by the builder agent)
- User registration (owned by the gateway)
- Telegram message formatting (owned by the Telegram bot)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, `POST /intake` endpoint, conversation loop |
| LangChain / Ollama | LLM calls for clarification turns and spec extraction |
| Postgres (`messages` table) | Persist conversation history; load context for each turn |

## Key flows

### Happy path: spec locked in one turn

1. Gateway calls `POST /intake` with `{user_id, message, history}`
2. Intake runs LLM prompt with message history and injected standards
3. LLM returns a complete spec (detected by JSON output structure)
4. Returns `{reply, spec, spec_locked: true}`
5. Gateway launches the build pipeline

### Multi-turn clarification

1. LLM returns a clarifying question (no valid spec JSON in output)
2. Intake returns `{reply: "<question>", spec_locked: false}`
3. Gateway stores reply in `messages`; operator answers via Telegram
4. Next call to `POST /intake` includes updated history
5. Continues until spec is extracted

### App type ambiguity

If the operator's description could match multiple app types, intake prompts with an explicit type menu rather than guessing.

## Data owned

**Writes:**
- `messages` table — appends each conversation turn (role: `assistant`) after the LLM responds

**Reads:**
- `messages` table — loads full history for the current user to provide LLM context on each turn

The intake agent does not read or write `apps`, `agent_runs`, or `board_cards`. Those are owned by the gateway.

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Ollama unreachable | Returns HTTP 503 to gateway; build is not triggered; operator receives an error reply |
| LLM returns malformed spec JSON | Treated as an incomplete spec; intake asks another clarifying question |
| LLM output is empty | Retries the prompt once; on second failure, returns a generic clarifying question |
| Database write failure | 500 returned to gateway; message may not be persisted; next turn may lose context for that turn |

## Non-functional constraints

- Each conversation turn involves one Ollama call; latency is bounded by `llama3.1:8b` inference time (~2–10 s on CPU, <1 s with GPU).
- Stateless horizontally within a single turn — no in-memory state between requests; all context is reloaded from `messages` per call.
- Context window grows with each clarification turn; very long conversations may approach the model's token limit and cause truncated context.

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /intake` | Gateway | Process one conversation turn |
| `GET /health` | Traefik / gateway | Health check |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `INTAKE_LLM_PROVIDER` | `ollama` | LLM provider: `ollama`, `openai`, `anthropic` |
| `INTAKE_LLM_MODEL` | provider default | Model name. Defaults: `llama3.1:8b` (ollama), `gpt-4o` (openai), `claude-sonnet-4-6` (anthropic) |
| `INTAKE_LLM_API_KEY` | — | API key for the chosen provider. Falls back to `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`. Required when provider ≠ `ollama` |
| `OLLAMA_URL` | `http://ollama:11434` | Used only when `INTAKE_LLM_PROVIDER=ollama` |
| `DATABASE_URL` | — | asyncpg DSN for message history |
| `STANDARDS_PATH` | `/standards` | Mount path for YAML standards files |

## Known limitations

- No timeout on the clarification loop — an operator who never resolves ambiguity will hold a conversation open indefinitely.
- Spec extraction relies on LLM JSON output; malformed output falls back to asking another clarifying question, which may loop.
