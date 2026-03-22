---
title: "0007: LiteLLM provider abstraction with per-agent model overrides"
status: accepted
date: 2026-03-22
supersedes: docs/architecture/decisions/0006-per-agent-llm-provider-configuration.md
related:
  - agentic-standards/decisions/adr-002-provider-abstraction.md
  - docs/architecture/decisions/0001-workflow-orchestration.md
  - docs/architecture/overview.md
---

## Context

ADR-0006 (2026-03-21) established per-agent provider/model configuration via
`{AGENT_PREFIX}_LLM_PROVIDER`, `{AGENT_PREFIX}_LLM_MODEL`, and
`{AGENT_PREFIX}_LLM_API_KEY` env vars. It addressed the right problem — agents
have different quality/cost/latency requirements — but was written before
the org-level provider abstraction was decided.

The org standard (agentic-standards ADR-002, 2026-03-15) mandates **LiteLLM**
via `agentic_standards.router.LLMRouter` as the single call-site for all LLM
calls. LiteLLM model strings encode the provider inside the model name
(`ollama/llama3.1:8b`, `anthropic/claude-sonnet-4-6`, `openai/gpt-4o`),
making a separate `_LLM_PROVIDER` variable redundant.

This ADR supersedes ADR-0006 and brings the project into alignment with
ADR-002, while preserving the per-agent routing granularity that ADR-0006
established.

---

## Decision

**All LLM calls go through `agentic_standards.router.LLMRouter`.**
No agent may instantiate `ChatOllama`, `ChatAnthropic`, `AsyncOpenAI`, or any
provider-specific client directly.

### Tier-based global defaults

Three env vars define the system-wide model tier slots. These are the defaults
when no per-agent override is set:

| Var | Purpose | Default |
|-----|---------|---------|
| `MODEL_FAST` | Conversational, high-frequency, low-stakes | `ollama/llama3.1:8b` |
| `MODEL_STANDARD` | Structured output, medium reasoning | `ollama/llama3.1:8b` |
| `MODEL_STRONG` | Code generation, architectural reasoning | `ollama/llama3.1:8b` |

Setting `MODEL_STRONG=anthropic/claude-sonnet-4-6` upgrades every agent that
targets the strong tier without touching agent-level configuration.

### Per-agent model overrides

Each agent may override its model via a single env var using the LiteLLM
model string format:

```
{AGENT_PREFIX}_LLM_MODEL     # e.g. anthropic/claude-sonnet-4-6
{AGENT_PREFIX}_LLM_API_KEY   # per-agent API key; falls back to global key
```

`_LLM_PROVIDER` is removed. The provider is encoded in `_LLM_MODEL`:
`ollama/…`, `anthropic/…`, `openai/…`.

Agent prefixes: `INTAKE`, `PLANNER`, `BUILDER`, `UI_DESIGNER`, `REVIEWER`,
`TEST_WRITER`, `REMEDIATION`, `WATCHDOG`.

### Key lookup order

1. `{AGENT_PREFIX}_LLM_API_KEY`
2. `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` global fallback
3. No key required when model string starts with `ollama/`

### Agent tier assignments and recommended defaults

| Agent | Default tier | Suggested override | Rationale |
|-------|-------------|-------------------|-----------|
| Intake | `FAST` | — | Conversational, frequent, low-stakes |
| Planner | `STRONG` | `anthropic/claude-sonnet-4-6` | Architectural reasoning; quality affects downstream stages |
| Builder | `STRONG` | `anthropic/claude-sonnet-4-6` | Code generation quality determines app success rate |
| UI Designer | `STRONG` | `anthropic/claude-sonnet-4-6` | Template generation; same reasoning as builder |
| Reviewer | `STANDARD` | — | Well-defined checklist; local model is sufficient |
| Test Writer | `STANDARD` | `ollama/qwen2.5-coder:7b` | Code-focused model competitive with mid-tier cloud |
| Remediation | `STRONG` | `anthropic/claude-sonnet-4-6` | Error analysis quality reduces retry cycles |
| Watchdog | `FAST` | — | Log summarisation only; smallest model is optimal |

Tier assignments are defaults in agent code. Operators override via env vars.

### Resolution hierarchy

When an agent selects its model, the lookup order is:

1. `{AGENT_PREFIX}_LLM_MODEL` (explicit per-agent override)
2. `MODEL_{TIER}` for the agent's declared tier
3. `ollama/llama3.1:8b` (hardcoded final fallback — system always works air-gapped)

---

## Options considered

### Option A: Adopt ADR-002 tier model only (drop per-agent vars)

Route every agent to a tier; no per-agent overrides. Simpler configuration.

**Rejected:** Loses the ability to upgrade a single critical agent (e.g., Builder)
to a cloud model while keeping the rest local. Tier globals affect all agents
that share a tier, which is too coarse when cost control matters.

### Option B: Keep ADR-0006 as-is, skip LiteLLM

Implement a thin dispatcher per provider in each agent. No new dependency.

**Rejected:** Each agent would duplicate provider-switching logic. Adding a new
provider (e.g., Gemini) requires touching every agent. Violates the org standard
(ADR-002).

### Option C: LiteLLM + tier globals + per-agent model override (chosen)

LiteLLM handles provider dispatch. Tier globals cover the common case.
Per-agent `_LLM_MODEL` handles exceptions. The provider is encoded in the
model string — no `_LLM_PROVIDER` var needed.

---

## Consequences

### What changes

- `agentic_standards` package is added to each agent's dependencies
  (`litellm>=1.40` is pulled transitively).
- Each agent replaces direct Ollama calls with
  `await router.complete(messages, tier=ModelTier.STANDARD)` (or the agent's
  declared tier).
- `{AGENT_PREFIX}_LLM_PROVIDER` is removed from all agent env var tables.
- `{AGENT_PREFIX}_LLM_MODEL` now takes a LiteLLM model string, not a bare name.
- `OLLAMA_MODEL` per-agent vars are removed. `OLLAMA_URL` remains a single
  global var consumed by LiteLLM.
- `docker-compose.yml` gains `MODEL_FAST`, `MODEL_STANDARD`, `MODEL_STRONG`
  and optional per-agent `_LLM_MODEL` / `_LLM_API_KEY` entries.
- Agent component docs are updated to reflect the new env var schema.
- ADR-0006 is superseded.

### What does not change

- Default behaviour is identical to current Ollama-only setup — no env vars
  need to change for existing deployments. All three tier vars default to a
  local Ollama model.
- Ollama container is not removed; it remains in `docker-compose.yml`.
- The pipeline, workflow orchestration, and agent interfaces are unaffected.
- Standards injection (YAML files into prompts) works the same regardless of
  provider.

### Privacy note

Agents whose `_LLM_MODEL` (or tier default) resolves to a commercial provider
will send prompt content — including operator app descriptions and generated
source code — to that provider's API. Operators who require all data to remain
on-premises must keep all tier vars and per-agent overrides pointed at
`ollama/…` models.
