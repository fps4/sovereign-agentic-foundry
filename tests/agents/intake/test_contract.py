"""
L1 Contract tests for the intake agent.

Covers:
- HTTP plumbing: status codes, response schema
- Pydantic validation: required fields, field constraints
- _try_parse_spec: pure-function logic (no HTTP needed)
- LLM message construction: history and system prompt forwarded correctly

No real LLM is used. All LLM calls are intercepted by MockLLM.
Target runtime: < 10 seconds total.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from main import agent, _try_parse_spec
from agentic_standards.contracts.agent_io import AppSpec
from tests.lib.mock_llm import MockLLM
from tests.lib.fixtures import VALID_SPEC_RESPONSE

pytestmark = pytest.mark.contract


# ── Helpers ───────────────────────────────────────────────────────────────────

def post(client: TestClient, **overrides) -> object:
    """POST /intake with sensible defaults. Returns the raw response."""
    payload = {"tenant_id": "t-test", "message": "test message", **overrides}
    return client.post("/intake", json=payload)


# ── HTTP plumbing ─────────────────────────────────────────────────────────────

def test_llm_question_response_gives_spec_locked_false(client):
    """Plain text from LLM → spec_locked=false, non-empty reply, HTTP 200."""
    agent.llm = MockLLM(["What kind of data does your form collect?"])

    resp = post(client, message="build me something")

    assert resp.status_code == 200
    body = resp.json()
    assert body["spec_locked"] is False
    assert body["reply"] != ""
    assert body["spec"] is None


def test_llm_valid_spec_json_locks_spec(client):
    """Valid spec JSON from LLM → spec_locked=true, AppSpec present and valid."""
    agent.llm = MockLLM([VALID_SPEC_RESPONSE])

    resp = post(client, message="feedback form with name, dept, comment")

    assert resp.status_code == 200
    body = resp.json()
    assert body["spec_locked"] is True
    assert body["spec"] is not None
    spec = AppSpec(**body["spec"])
    assert spec.app_type == "form"
    assert spec.name == "employee-feedback"
    assert len(spec.requirements) >= 3


def test_llm_malformed_json_falls_back_gracefully(client):
    """Malformed JSON from LLM is treated as a clarifying reply — no 500."""
    agent.llm = MockLLM(["{broken json <<<"])

    resp = post(client, message="build something")

    assert resp.status_code == 200
    body = resp.json()
    assert body["spec_locked"] is False
    assert body["spec"] is None


def test_llm_empty_string_falls_back_gracefully(client):
    """Empty string from LLM causes no 500 and returns spec_locked=false."""
    agent.llm = MockLLM([""])

    resp = post(client, message="build something")

    assert resp.status_code == 200
    body = resp.json()
    assert body["spec_locked"] is False
    assert body["spec"] is None


# ── Pydantic validation ───────────────────────────────────────────────────────

def test_missing_tenant_id_returns_422(client):
    """Request without tenant_id fails schema validation with HTTP 422."""
    resp = client.post("/intake", json={"message": "build me an app"})

    assert resp.status_code == 422
    fields = [e["loc"] for e in resp.json()["detail"]]
    assert any("tenant_id" in loc for loc in fields)


def test_missing_message_returns_422(client):
    """Request without message fails schema validation with HTTP 422."""
    resp = client.post("/intake", json={"tenant_id": "t-test"})

    assert resp.status_code == 422
    fields = [e["loc"] for e in resp.json()["detail"]]
    assert any("message" in loc for loc in fields)


# ── _try_parse_spec pure function ─────────────────────────────────────────────

def test_parse_spec_rejects_fewer_than_3_requirements():
    """_try_parse_spec returns None when requirements list has < 3 items."""
    payload = json.dumps({
        "spec_locked": True,
        "spec": {
            "name": "short-app",
            "description": "An app.",
            "app_type": "form",
            "stack": "python-fastapi",
            "requirements": ["Only one requirement"],
        },
    })
    assert _try_parse_spec(payload) is None


def test_parse_spec_rejects_unknown_app_type():
    """_try_parse_spec returns None when app_type is not in the allowed list."""
    payload = json.dumps({
        "spec_locked": True,
        "spec": {
            "name": "blog-app",
            "description": "A blog.",
            "app_type": "blog",
            "stack": "python-fastapi",
            "requirements": ["Post articles", "Comment on posts", "Tag posts"],
        },
    })
    assert _try_parse_spec(payload) is None


def test_parse_spec_accepts_valid_spec():
    """_try_parse_spec returns an AppSpec when all required fields are valid."""
    payload = json.dumps({
        "spec_locked": True,
        "spec": {
            "name": "contract-tracker",
            "description": "Tracks contracts through a four-stage approval workflow.",
            "app_type": "workflow",
            "stack": "python-fastapi",
            "requirements": [
                "User can submit a new contract for review",
                "Contracts move through submitted, under-review, approved, rejected",
                "Admin can view all contracts and their current stage",
            ],
        },
    })
    spec = _try_parse_spec(payload)
    assert spec is not None
    assert isinstance(spec, AppSpec)
    assert spec.app_type == "workflow"
    assert spec.name == "contract-tracker"


# ── LLM message construction ──────────────────────────────────────────────────

def test_history_is_forwarded_to_llm(client):
    """Prior conversation history turns appear in the messages list sent to LLM."""
    mock_llm = MockLLM(["What type of app?"])
    agent.llm = mock_llm

    history = [
        {"role": "user", "content": "I need an app"},
        {"role": "assistant", "content": "What kind of app would you like?"},
    ]
    post(client, message="something with forms", history=history)

    assert len(mock_llm.calls) == 1
    messages = mock_llm.calls[0]

    # System prompt is always first
    assert messages[0]["role"] == "system"

    # History turns present before the final user message
    sent_pairs = [(m["role"], m["content"]) for m in messages[1:]]
    assert ("user", "I need an app") in sent_pairs
    assert ("assistant", "What kind of app would you like?") in sent_pairs

    # Current message is the final entry
    assert messages[-1] == {"role": "user", "content": "something with forms"}
