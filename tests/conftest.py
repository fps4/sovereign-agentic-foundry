"""
Shared pytest fixtures for all agent test layers.

Fixtures here are available to every test under tests/ without explicit import.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from main import app, agent


@pytest.fixture(scope="session")
def client() -> TestClient:
    """
    Session-scoped synchronous ASGI test client.

    Using a context manager triggers the FastAPI lifespan, which calls
    agent.load_prompts(). This runs once per session — the prompt file
    is small and idempotent to reload.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def disable_run_log(monkeypatch):
    """
    Replace agent.run_log with a no-op AsyncMock for every test.

    Prevents connection attempts to the orchestrator, keeping tests fast.
    autouse=True applies this automatically without explicit fixture requests.

    Tests that want to assert on run_log calls can reference this fixture:
        def test_something(disable_run_log):
            ...
            assert disable_run_log.call_count == 1
    """
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(agent, "run_log", mock)
    return mock
