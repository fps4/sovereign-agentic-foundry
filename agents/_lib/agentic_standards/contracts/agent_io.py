"""
Typed contracts for agent request/response and run event logging.

All inter-agent HTTP calls must use these models as their payload schemas.
No ad-hoc dicts across service boundaries.

Hierarchy:
    AgentRequest   — what the caller sends to an agent endpoint
    AgentResponse  — what every agent endpoint returns
    RunEvent       — what agents POST to /runs/log on the orchestrator
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared envelope
# ---------------------------------------------------------------------------


class AgentRequest(BaseModel):
    """
    Minimal envelope every agent endpoint should accept.

    Agents may extend this with their own fields:
        class BuildRequest(AgentRequest):
            name: str
            description: str
    """

    run_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Correlation ID for this pipeline run. Propagated across all agents.",
    )
    model_tier: Literal["fast", "standard", "strong"] = Field(
        default="standard",
        description="Which model tier the caller expects this agent to use.",
    )


class AgentResponse(BaseModel):
    """
    Minimal envelope every agent endpoint should return.

    Agents may extend this with their own output fields:
        class BuildResponse(AgentResponse):
            repo_url: str
            app_url: str
    """

    run_id: str
    status: Literal["ok", "error"] = "ok"
    error: str | None = Field(
        default=None,
        description="Human-readable error message. None when status='ok'.",
    )


# ---------------------------------------------------------------------------
# Run event logging (mirrors /runs/log on the orchestrator)
# ---------------------------------------------------------------------------


class RunEvent(BaseModel):
    """
    A single step event emitted by an agent during a pipeline run.

    Agents call BaseAgent.run_log() which serialises to this schema and
    POSTs it to the orchestrator's /runs/log endpoint.
    """

    run_id: str
    agent: str = Field(description="Name of the emitting agent, e.g. 'coder'.")
    event: str = Field(
        description="Dot-separated event name, e.g. 'build.start', 'build.scaffold.done'."
    )
    status: Literal["ok", "error", "warning"] = "ok"
    duration_ms: int | None = Field(
        default=None,
        description="Wall-clock milliseconds for this step. None if not applicable.",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary structured context — never include secrets.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Design spec (produced by designer, consumed by coder and compliance)
# ---------------------------------------------------------------------------


class DataField(BaseModel):
    field: str
    type: Literal["str", "int", "float", "bool", "date"]
    required: bool = True
    label: str


class AppSpec(BaseModel):
    """
    The canonical application specification produced by the designer agent
    and consumed by the coder, tester, and compliance agents.
    """

    name: str = Field(
        description="kebab-case app name, max 40 chars.",
        pattern=r"^[a-z][a-z0-9-]{0,38}[a-z0-9]$",
    )
    description: str = Field(description="One concise sentence.")
    app_type: Literal["form", "dashboard", "workflow", "connector", "assistant"]
    stack: Literal["python-fastapi", "node-express", "go-gin"] = "python-fastapi"
    requirements: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(default_factory=list)
    data_model: list[DataField] = Field(default_factory=list)
