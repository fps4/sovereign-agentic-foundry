---
title: "0008: Three-layer quality testing strategy for platform agents"
status: accepted
date: 2026-03-22
related:
  - docs/guides/testing.md
  - standards/testing.yaml
  - docs/architecture/components/intake.md
---

## Context

Platform agents are LLM-based services. They can fail in two distinct ways:

1. **Structural failure** — wrong HTTP status, missing schema fields, bad fallback logic. Deterministic, fast to catch, independent of model quality.
2. **Quality failure** — output is structurally valid but wrong: spec locked too early, fix instructions that don't reference the affected file, generated code that doesn't implement the stated requirements. Probabilistic, depends on the model and the prompt.

The existing `scripts/e2e_test.py` exercises the full pipeline end-to-end but is not designed to catch either type systematically:

- It requires a running stack with a live LLM.
- It tests the pipeline as a whole — a failure doesn't localise to the agent that caused it.
- It has no mechanism for scoring output quality.
- It cannot run on a PR without full infrastructure.

As the agent roster grows (10 agents planned), regressions introduced in one agent's prompt or logic become difficult to detect and attribute without per-agent tests.

## Options considered

### Option A: E2E tests only (extend the existing approach)

Extend `scripts/e2e_test.py` with more scenarios. Add per-agent health checks and response assertions to the existing pipeline test.

**Dropped because:** E2E tests are slow (minutes per run), require the full stack, and do not localise failures. Adding more scenarios makes the suite slower without improving the ability to catch structural failures in individual agents. Quality regressions (prompt drift, model changes) remain invisible.

### Option B: Unit tests with mocked LLM only

Write pytest unit tests for each agent's HTTP endpoints with a mock LLM. Validate schema, error paths, and fallback logic only. No real LLM calls.

**Dropped because:** Mocked tests confirm the plumbing works but say nothing about whether the agent does the right thing. An intake agent that always returns `spec_locked=false` would pass all contract tests. A reviewer that approves files with hardcoded secrets would pass if the mock returns `"approved"`. Quality — the core risk — is undetectable.

### Option C: Three-layer strategy — contract + behavioral + quality (chosen)

Define three test layers per agent, each serving a distinct purpose:

| Layer | LLM | Speed | CI gate |
|-------|-----|-------|---------|
| L1 Contract | Mocked | < 10 s total | Required on every PR |
| L2 Behavioral | Real | 30–120 s | Required on merge to main |
| L3 Quality | Real (LLM-as-judge) | Minutes | Advisory, scheduled weekly |

**Chosen because:**
- L1 catches structural regressions fast with no secrets or infrastructure required — suitable for every PR
- L2 catches behavioral regressions (prompt drift, logic changes) with deterministic pass/fail criteria even though the LLM output varies
- L3 scores subjective dimensions (question clarity, fix instruction specificity, code quality) over time — detecting gradual quality decay before it affects deployed apps
- The layers are independently runnable; L2 and L3 can be skipped locally when working on unrelated changes
- The approach scales: each new agent follows the same pattern, adding to the same test runner

## Decision

**Adopt the three-layer testing strategy** for all platform agents.

### Layer definitions

**L1 Contract** (`pytest.mark.contract`):
- Mock `agent.llm` with `MockLLM` (preset responses, call recording)
- Suppress `agent.run_log` with `AsyncMock` to avoid orchestrator connections
- Test: HTTP status codes, Pydantic validation, fallback logic, message construction, pure functions
- No LLM or network access; passes on every developer machine and CI runner

**L2 Behavioral** (`pytest.mark.behavioral`):
- Real LLM via `LLMRouter`; provider selected by `BEHAVIORAL_LLM_PROVIDER` env var
- Skipped automatically if `BEHAVIORAL_LLM_PROVIDER` is not set
- Evaluation criteria are deterministic: field presence, schema validation, count assertions, keyword matching
- Inputs are representative fixtures (vague message, complete spec, multi-turn conversation)

**L3 Quality** (`pytest.mark.quality`):
- Real LLM for the agent under test; Claude as the judge model
- Scores each output dimension 0–1 against a rubric
- Results stored in `quality-report.json`; alerts if any dimension drops >10% from the stored baseline
- Advisory gate only — does not block the pipeline

### LLM-as-judge rationale

Quality dimensions like "clarifying question is specific and advances the spec" or "fix instruction references the affected file" cannot be evaluated with a deterministic assertion. Options:

- **Reference comparison** (cosine similarity against a golden output): fragile — LLM phrasing varies legitimately, and similarity scores do not correlate well with correctness.
- **Human review**: does not scale; cannot run in CI.
- **LLM-as-judge**: scores a rubric criterion against the actual output. Non-deterministic but calibrated — variance is much smaller than quality gaps. Regression is detected by tracking the score trend, not a single threshold.

Claude (`claude-sonnet-4-6`) is used as the judge because it is independent of the agent under test (which may use Ollama or a different model), and its reasoning is inspectable in the score output.

### Infrastructure

| File | Purpose |
|------|---------|
| `pytest.ini` | `pythonpath` for agent modules, test markers, `testpaths = tests` |
| `tests/conftest.py` | Session-scoped `TestClient`, autouse `disable_run_log` mock |
| `tests/lib/mock_llm.py` | `MockLLM` — async drop-in for `LLMRouter` with call recording |
| `tests/lib/fixtures.py` | Shared request payloads and conversation fixtures |
| `standards/testing.yaml` | Full strategy spec: layer definitions, CI commands, quality regression config |
| `docs/guides/testing.md` | Operational guide: how to run, provider config, adding tests for a new agent |

Per-agent test specifications live in each `agents/<agent>/agent.yaml` under the `testing:` key.

## Consequences

### What changes

- Each agent implementation must be accompanied by `tests/agents/<agent>/test_contract.py` before merging
- `pytest.ini` `pythonpath` grows by one entry per new agent (source directory added)
- CI pipelines gain two jobs: `pytest -m contract` (PR gate) and `pytest -m behavioral` (main gate)
- A weekly scheduled job runs `pytest -m quality` and stores `quality-report.json`
- Agent module-level singletons (e.g. `agent = IntakeAgent()`) must have their LLM replaceable via direct attribute assignment for contract tests to work; no additional DI framework is required

### What does not change

- Production agent code does not change to accommodate testing — `MockLLM` is a drop-in that matches the `LLMRouter.complete` signature
- The e2e test suite (`scripts/e2e_test.py`) remains the end-to-end pipeline smoke test; these layers do not replace it
- Standards YAML files (`naming.yaml`, `security.yaml`, etc.) remain the authoritative rules injected into LLM prompts; the reviewer's L1 contract tests verify the static checker applies them correctly

### Deferred

- L3 quality evaluator tooling (`tests/lib/evaluators.py`) — stubbed in `standards/testing.yaml`; implemented when the first agent reaches production quality baseline
- Aggregate quality dashboard in the portal (surfacing per-agent scores over time)
- Mutation testing to validate L1 contract test coverage
