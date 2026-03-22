---
title: "0006: Per-agent LLM provider and model configuration"
status: superseded
date: 2026-03-21
superseded_by: docs/architecture/decisions/0007-litellm-provider-abstraction.md
related:
  - docs/architecture/overview.md
  - docs/architecture/decisions/0001-workflow-orchestration.md
  - docs/architecture/components/intake.md
  - docs/architecture/components/planner.md
  - docs/architecture/components/builder.md
  - docs/architecture/components/ui-designer.md
  - docs/architecture/components/reviewer.md
  - docs/architecture/components/test-writer.md
  - docs/architecture/components/remediation.md
  - docs/architecture/components/watchdog.md
---

## Context

All LLM-using agents currently call Ollama exclusively, via a shared `OLLAMA_MODEL` + `OLLAMA_URL` pattern. This satisfies the self-sovereign requirement but creates a hard constraint: every agent uses the same local model regardless of task characteristics.

Different pipeline stages have different needs:

| Stage | Task characteristics | Optimal provider |
|-------|---------------------|-----------------|
| Intake | Conversational, low-stakes, frequent calls | Small/fast model; local or cheap commercial |
| Planner | Architectural reasoning, structured JSON output | Stronger model benefits quality |
| Builder | Large context window, code generation | Strongest model; quality directly affects app success rate |
| UI Designer | Frontend template generation, structured output | Stronger model; same as builder |
| Reviewer | Standards compliance, deterministic checklist | Medium model; task is well-defined |
| Test Writer | Code comprehension, pytest generation | Medium-to-strong code model |
| Remediation | Error analysis, targeted patch | Stronger model; repair quality affects retry count |
| Watchdog | Log summarisation only | Small/fast model |

A flat Ollama-only policy forces operators to choose one model that balances all these needs — in practice defaulting to a mid-range model that is suboptimal for both fast classification tasks and deep code generation tasks.

The platform should allow operators to route each agent to a different provider and model independently, while keeping Ollama as the zero-configuration default.

## Decision

Each LLM-using agent is independently configurable via three env vars:

```
{AGENT_PREFIX}_LLM_PROVIDER   # ollama (default) | openai | anthropic
{AGENT_PREFIX}_LLM_MODEL      # model name; falls back to provider default if unset
{AGENT_PREFIX}_LLM_API_KEY    # API key; only required when provider ≠ ollama
```

Agent prefixes: `INTAKE`, `PLANNER`, `BUILDER`, `UI_DESIGNER`, `REVIEWER`, `TEST_WRITER`, `REMEDIATION`, `WATCHDOG`.

Global env vars shared across all agents:

```
OLLAMA_URL          # http://ollama:11434 (default); used by any agent whose provider is ollama
OPENAI_API_KEY      # Fallback API key for agents using openai provider without a per-agent key
ANTHROPIC_API_KEY   # Fallback API key for agents using anthropic provider without a per-agent key
```

**Provider default models** (used when `{AGENT_PREFIX}_LLM_MODEL` is not set):

| Provider | Default model |
|----------|--------------|
| `ollama` | `llama3.1:8b` |
| `openai` | `gpt-4o` |
| `anthropic` | `claude-sonnet-4-6` |

**Key lookup order** for a given agent: per-agent key (`{PREFIX}_LLM_API_KEY`) → global key (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`) → error at startup if neither is set.

## Options considered

### Option A: Single global provider switch

One `LLM_PROVIDER` env var routes all agents to the same provider. Simpler to configure but defeats the purpose — the point is to mix providers by task type.

Rejected: does not address the core requirement.

### Option B: Per-agent provider + model (chosen)

Each agent configures its own provider and model independently. Operator has full control. Defaults to Ollama for all agents, so existing deployments require no changes.

### Option C: Model routing table in a config file

A `llm-routing.yaml` mounted into the gateway maps agent names to provider/model pairs. Centralised configuration, but requires a new config file format, a parser in each agent, and a mount in `docker-compose.yml`.

Rejected: adds operational complexity for a problem that env vars already solve cleanly at this scale.

## Consequences

### What changes

- Each LLM-using agent reads `{PREFIX}_LLM_PROVIDER` at startup to select a provider client (`ollama`, `openai`, or `anthropic`).
- `{PREFIX}_LLM_MODEL` overrides the provider default model.
- `{PREFIX}_LLM_API_KEY` (or the global fallback) is required when provider ≠ `ollama`; agents fail fast at startup if the key is missing.
- `OLLAMA_MODEL` and `OLLAMA_URL` are removed from per-agent configuration. `OLLAMA_URL` becomes a single global variable.
- `docker-compose.yml` gains optional `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` entries and per-agent provider/model overrides.
- Agent documentation configuration tables are updated to reflect the new variables.

### What does not change

- Default behaviour is identical to the current Ollama-only setup — no env vars need to change for existing deployments.
- Ollama container is not removed; it remains in `docker-compose.yml` and is used by any agent whose provider is `ollama`.
- The build pipeline, workflow orchestration, and agent interfaces are unaffected.
- Standards injection (YAML files into prompts) works the same regardless of provider.

### Recommended defaults by agent (not enforced)

| Agent | Suggested provider | Rationale |
|-------|--------------------|-----------|
| Intake | `ollama` | Frequent, low-stakes; local model keeps latency and cost low |
| Planner | `openai` or `anthropic` | Architectural reasoning benefits from a stronger model |
| Builder | `openai` or `anthropic` | Code generation quality directly determines app success rate |
| UI Designer | `openai` or `anthropic` | Frontend template quality; same reasoning as builder |
| Reviewer | `ollama` | Well-defined checklist task; local model is sufficient |
| Test Writer | `ollama` or `openai` | Mid-tier task; `qwen2.5-coder` via Ollama is competitive |
| Remediation | `openai` or `anthropic` | Error analysis on failure paths; quality reduces retry cycles |
| Watchdog | `ollama` | Log summarisation only; small fast model is optimal |

These are guidance only. Operators choose based on their cost, latency, and privacy constraints.

### Privacy note

Agents configured with a commercial provider will send prompt content (including operator app descriptions and generated source code) to the provider's API. Operators who require all data to remain on-premises must keep those agents on `ollama`.
