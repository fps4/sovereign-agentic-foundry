"""
Workflow-level contracts: specs, step results, and gate results.

These are used by the orchestrator (and eventually Temporal activities)
to pass structured state between workflow steps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from agentic_standards.contracts.agent_io import AppSpec


# ---------------------------------------------------------------------------
# Workflow spec — the top-level input to a build pipeline run
# ---------------------------------------------------------------------------


class WorkflowSpec(BaseModel):
    """
    Input to a full build pipeline run.

    Created by the orchestrator after the designer agent reaches status='ready'.
    Passed through every subsequent activity as the canonical source of truth.
    """

    run_id: str
    user_id: str = Field(description="Telegram user ID of the requesting user.")
    org: str = Field(description="Gitea organisation name for this user.")
    app_spec: AppSpec
    initiated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Step result — what each workflow activity returns
# ---------------------------------------------------------------------------


class StepResult(BaseModel):
    """
    Return type for every workflow activity / pipeline step.

    Activities should never raise unhandled exceptions — they catch errors,
    set status='error', and return a StepResult so the workflow engine
    (Temporal / LangGraph) can apply its retry/failure policy.
    """

    step: str = Field(description="Step name, e.g. 'design', 'compliance', 'coder'.")
    status: Literal["ok", "error", "skipped"] = "ok"
    outputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Step-specific output data. Schema defined per step.",
    )
    error: str | None = None
    duration_ms: int | None = None


# ---------------------------------------------------------------------------
# Gate result — compliance / quality gate output
# ---------------------------------------------------------------------------


class GateVerdict(str):
    APPROVED = "approved"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"


class Finding(BaseModel):
    """
    A single finding from a gate check.

    Severity maps to the compliance agent's finding_severities:
      blocker     → verdict=blocked   (halts the pipeline)
      suggestion  → verdict=needs_review (soft block, surfaced to admin)
      nit         → verdict=approved  (logged but does not change verdict)
    """

    severity: Literal["blocker", "suggestion", "nit"]
    check: str = Field(description="The check that produced this finding.")
    detail: str = Field(description="What was found and where (file, line if known).")


class GateResult(BaseModel):
    """
    Output from any gate activity (compliance, security, quality).

    Verdict is derived from findings:
      - Any blocker  → blocked
      - Any suggestion (no blockers) → needs_review
      - Only nits or empty → approved

    A BLOCKED verdict must halt the pipeline. NEEDS_REVIEW is a soft block
    that surfaces in the admin dashboard but does not stop the build.
    """

    gate: str = Field(description="Gate name, e.g. 'compliance', 'security'.")
    verdict: Literal["approved", "blocked", "needs_review"] = "approved"
    findings: list[Finding] = Field(
        default_factory=list,
        description="Structured findings list. Empty when verdict='approved'.",
    )
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def is_blocking(self) -> bool:
        return self.verdict == "blocked"

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "blocker"]

    @property
    def suggestions(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "suggestion"]

    @classmethod
    def from_findings(cls, gate: str, findings: list[Finding]) -> "GateResult":
        """Derive the correct verdict from a list of findings."""
        if any(f.severity == "blocker" for f in findings):
            verdict = "blocked"
        elif any(f.severity == "suggestion" for f in findings):
            verdict = "needs_review"
        else:
            verdict = "approved"
        return cls(gate=gate, verdict=verdict, findings=findings)
