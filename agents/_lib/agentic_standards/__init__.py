"""
agentic-standards — shared base classes, schemas, and patterns
for the sovereign agentic foundry.

Import surface:
    from agentic_standards.agent import BaseAgent
    from agentic_standards.router import LLMRouter, ModelTier
    from agentic_standards.contracts.agent_io import AgentRequest, AgentResponse, RunEvent
    from agentic_standards.contracts.workflow import WorkflowSpec, StepResult, GateResult
    from agentic_standards.observability.tracing import get_logger, run_log
"""

__version__ = "0.1.0"
