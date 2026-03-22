---
title: "Testing guide"
status: current
last_updated: 2026-03-22
owners: [platform-team]
related:
  - docs/architecture/components/intake.md
  - standards/testing.yaml
---

## Overview

The test suite has three layers. Each layer trades speed for depth.

| Layer | Marker | Speed | LLM required | Purpose |
|-------|--------|-------|--------------|---------|
| L1 Contract | `contract` | < 10 s | No | HTTP contracts, Pydantic validation, pure-function logic |
| L2 Behavioral | `behavioral` | 30–120 s | Yes | Agent does the right thing with representative inputs |
| L3 Quality | `quality` | Minutes | Yes | LLM-as-judge scoring on a rubric (scheduled, not blocking) |

The full testing strategy (infrastructure, CI integration, quality regression tracking) is in `standards/testing.yaml`. Per-agent test specifications are in each `agents/<agent>/agent.yaml` under the `testing:` key.

## Prerequisites

No additional packages are needed beyond what each agent already requires. The test configuration in `pytest.ini` puts `agents/_lib` and `agents/intake` on `PYTHONPATH` automatically, so there is nothing to install separately.

## Running L1 contract tests

No environment setup needed. Run from the repo root:

```bash
# Via make (preferred)
make test-intake-l1

# Direct pytest — all contract tests
pytest -m contract -v

# Direct pytest — intake agent only
pytest tests/agents/intake/test_contract.py -v
```

These tests use `MockLLM` to intercept all LLM calls. They pass regardless of LLM or network availability.

## Running L2 behavioral tests

L2 tests are skipped unless `BEHAVIORAL_LLM_PROVIDER` is set. Choose a provider:

**Anthropic (recommended for output quality):**

```bash
# Via make
make test-intake-l2 BEHAVIORAL_LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-...

# Direct pytest
BEHAVIORAL_LLM_PROVIDER=anthropic \
INTAKE_LLM_MODEL=claude-haiku-4-5 \
ANTHROPIC_API_KEY=sk-ant-... \
pytest -m behavioral -v
```

**OpenAI:**

```bash
# Via make
make test-intake-l2 BEHAVIORAL_LLM_PROVIDER=openai INTAKE_LLM_MODEL=gpt-4o OPENAI_API_KEY=sk-...

# Direct pytest
BEHAVIORAL_LLM_PROVIDER=openai \
INTAKE_LLM_MODEL=gpt-4o \
OPENAI_API_KEY=sk-... \
pytest -m behavioral -v
```

**Ollama (local, no API key):**

```bash
# Via make
make test-intake-l2 BEHAVIORAL_LLM_PROVIDER=ollama

# Direct pytest
BEHAVIORAL_LLM_PROVIDER=ollama \
OLLAMA_BASE_URL=http://localhost:11434 \
pytest -m behavioral -v
```

`INTAKE_LLM_MODEL` defaults to `ollama/llama3.1:8b` when using Ollama.

## Running all tests

```bash
# Contract + behavioral (requires LLM env vars for behavioral)
pytest -v

# Contract only (fast, no secrets)
pytest -m contract -v

# Skip behavioral even if env var is set
pytest -m "not behavioral" -v
```

## Test infrastructure

| File | Purpose |
|------|---------|
| `pytest.ini` | `pythonpath` setup, test markers, `testpaths = tests` |
| `tests/conftest.py` | Session-scoped `TestClient`, `autouse` mock for `agent.run_log` |
| `tests/lib/mock_llm.py` | `MockLLM` — async drop-in for `LLMRouter`, returns preset responses, records all calls |
| `tests/lib/fixtures.py` | Shared test data: valid spec JSON, request payloads, multi-turn conversation fixture |

## Adding tests for a new agent

When a new agent is implemented, follow this checklist:

1. Add the agent's source directory to `pytest.ini` `pythonpath`:
   ```ini
   pythonpath = agents/_lib agents/intake agents/planner
   ```

2. Create the test directory:
   ```
   tests/agents/<agent-name>/
   tests/agents/<agent-name>/__init__.py
   tests/agents/<agent-name>/test_contract.py
   tests/agents/<agent-name>/test_behavioral.py   # if agent uses LLM
   ```

3. Write L1 contract tests first. The pattern:
   ```python
   pytestmark = pytest.mark.contract

   def test_something(client):
       agent.llm = MockLLM(["mock response"])
       resp = client.post("/your-endpoint", json={...})
       assert resp.status_code == 200
       assert resp.json()["field"] == "expected"
   ```

4. The `disable_run_log` fixture from `conftest.py` applies automatically to every test via `autouse=True` — no explicit reference needed.

5. Gate L2 behavioral tests with the `_skip_if_no_llm` pattern:
   ```python
   pytestmark = pytest.mark.behavioral

   _skip_if_no_llm = pytest.mark.skipif(
       not os.environ.get("BEHAVIORAL_LLM_PROVIDER"),
       reason="BEHAVIORAL_LLM_PROVIDER not set",
   )

   @_skip_if_no_llm
   def test_something(client):
       ...
   ```

6. Add a `scope="module"` autouse fixture to reset `agent.llm` to a real `LLMRouter` before behavioral tests run (in case contract tests ran first and left a `MockLLM` on the singleton).

## MockLLM call recording

`MockLLM.calls` records every message list passed to `complete()`:

```python
mock = MockLLM(["response"])
agent.llm = mock

client.post("/intake", json={...})

# Inspect what was sent to the LLM
messages = mock.calls[0]
assert messages[0]["role"] == "system"          # system prompt first
assert messages[-1]["role"] == "user"           # current message last
assert len(mock.calls) == 1                     # called exactly once
```

## TestClient and async

Use Starlette's `TestClient` (synchronous). It handles async ASGI apps internally — no `pytest-asyncio` or `anyio` markers needed for L1/L2 tests.

The `client` fixture in `conftest.py` uses `with TestClient(app) as c` to trigger the FastAPI lifespan (which loads prompts). This runs once per session.

## CI integration

```yaml
# Run on every PR — no secrets needed
- name: Contract tests
  run: pytest -m contract -v

# Run on merge to main — requires LLM credentials
- name: Behavioral tests
  env:
    BEHAVIORAL_LLM_PROVIDER: anthropic
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    INTAKE_LLM_MODEL: claude-sonnet-4-6
  run: pytest -m behavioral -v --timeout=120
```
