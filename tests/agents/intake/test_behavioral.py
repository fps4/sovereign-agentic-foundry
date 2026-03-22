"""
L2 Behavioral tests for the intake agent.

These tests use a real LLM and verify the agent does the right thing with
representative inputs. All tests are skipped unless BEHAVIORAL_LLM_PROVIDER
is set in the environment.

Running:
    # Anthropic (recommended)
    BEHAVIORAL_LLM_PROVIDER=anthropic \\
    INTAKE_LLM_MODEL=claude-sonnet-4-6 \\
    ANTHROPIC_API_KEY=sk-ant-... \\
    pytest tests/agents/intake/test_behavioral.py -v

    # Ollama (local, no API key)
    BEHAVIORAL_LLM_PROVIDER=ollama \\
    OLLAMA_BASE_URL=http://localhost:11434 \\
    pytest tests/agents/intake/test_behavioral.py -v
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from main import agent
from agentic_standards.contracts.agent_io import AppSpec
from agentic_standards.router import LLMRouter
from tests.lib.fixtures import (
    VAGUE_MESSAGES,
    FORM_SPEC_MESSAGE,
    DASHBOARD_VAGUE_MESSAGE,
    WORKFLOW_SPEC_MESSAGE,
    MULTI_TURN_FIXTURE,
    HISTORY_WITH_APP_TYPE,
)

pytestmark = pytest.mark.behavioral

_skip_if_no_llm = pytest.mark.skipif(
    not os.environ.get("BEHAVIORAL_LLM_PROVIDER"),
    reason="BEHAVIORAL_LLM_PROVIDER not set — behavioral tests require a real LLM",
)


@pytest.fixture(scope="module", autouse=True)
def configure_real_llm():
    """Reset agent.llm to a real LLMRouter before behavioral tests run.

    The disable_run_log autouse fixture from conftest.py still applies,
    so run_log calls remain suppressed.
    """
    agent.llm = LLMRouter()
    yield


# ── Helpers ───────────────────────────────────────────────────────────────────

def post_intake(client: TestClient, payload: dict) -> dict:
    resp = client.post("/intake", json=payload)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
    return resp.json()


# ── Tests ─────────────────────────────────────────────────────────────────────

@_skip_if_no_llm
def test_vague_message_does_not_lock_spec(client):
    """'build me an app' is too vague — spec must not be locked in one turn."""
    body = post_intake(client, VAGUE_MESSAGES)
    assert body["spec_locked"] is False, (
        f"Spec locked prematurely on vague input. Reply: {body['reply']}"
    )


@_skip_if_no_llm
def test_detailed_form_message_locks_spec(client):
    """A specific form description with named fields should lock immediately."""
    body = post_intake(client, FORM_SPEC_MESSAGE)
    assert body["spec_locked"] is True, (
        f"Expected spec to lock on complete form description. Reply: {body['reply']}"
    )
    spec = AppSpec(**body["spec"])
    assert spec.app_type == "form"


@_skip_if_no_llm
def test_vague_dashboard_asks_about_data(client):
    """'I need a dashboard' should prompt a question about what data to display."""
    body = post_intake(client, DASHBOARD_VAGUE_MESSAGE)
    assert body["spec_locked"] is False
    reply_lower = body["reply"].lower()
    data_keywords = {"data", "show", "display", "metric", "information", "track", "visuali"}
    assert any(kw in reply_lower for kw in data_keywords), (
        f"Expected reply to ask about data to display. Got: {body['reply']}"
    )


@_skip_if_no_llm
def test_workflow_message_locks_spec_with_correct_type(client):
    """A workflow tracker description should lock with app_type=workflow."""
    body = post_intake(client, WORKFLOW_SPEC_MESSAGE)
    assert body["spec_locked"] is True, (
        f"Expected spec to lock on workflow description. Reply: {body['reply']}"
    )
    spec = AppSpec(**body["spec"])
    assert spec.app_type == "workflow"


@_skip_if_no_llm
def test_multi_turn_conversation_locks_by_turn_5(client):
    """A conversation that starts vague but answers questions should lock by turn 5."""
    history = []
    locked = False
    last_body: dict = {}

    for user_message in MULTI_TURN_FIXTURE:
        payload = {
            "tenant_id": "t-multi",
            "message": user_message,
            "history": history,
        }
        last_body = post_intake(client, payload)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": last_body["reply"]})

        if last_body["spec_locked"]:
            locked = True
            spec = AppSpec(**last_body["spec"])
            assert spec.app_type in ["workflow", "form", "dashboard", "connector", "assistant"]
            break

    assert locked, (
        f"Spec not locked after {len(MULTI_TURN_FIXTURE)} turns. "
        f"Last reply: {last_body.get('reply')}"
    )


@_skip_if_no_llm
def test_second_message_with_app_type_in_history_does_not_re_ask(client):
    """When history already establishes app type, agent should not ask about it again."""
    payload = {
        "tenant_id": "t-history",
        "message": "It should have three fields: name, email, and feedback",
        "history": HISTORY_WITH_APP_TYPE,
    }
    body = post_intake(client, payload)

    reply_lower = body["reply"].lower()
    re_ask_phrases = ["what type", "which type", "type of app", "form, dashboard"]
    for phrase in re_ask_phrases:
        assert phrase not in reply_lower, (
            f"Agent re-asked about app type despite it being in history. "
            f"Reply: {body['reply']}"
        )
