"""
BaseAgent — shared foundation for all platform agents.

Every agent (coder, designer, tester, monitor, compliance) inherits from this.
It provides:
  - Structured JSON logging (identical setup across all agents)
  - run_log() — POST step events to the orchestrator's /runs/log endpoint
  - retry() — tenacity-based retry decorator with sensible defaults
  - health() — FastAPI route handler for GET /health

Usage:
    class CoderAgent(BaseAgent):
        name = "coder"

        async def build(self, req: BuildRequest) -> BuildResponse:
            await self.run_log(req.run_id, "build.start", {"name": req.name})
            ...
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from agentic_standards.observability.tracing import get_logger, run_log as _run_log


class BaseAgent:
    """
    Abstract base class for all platform agents.

    Subclasses must set the ``name`` class attribute.
    They optionally override ``orchestrator_url`` if the env var name differs.
    """

    name: str = "agent"

    def __init__(self) -> None:
        self.log = get_logger(self.name)
        self._orchestrator_url = os.environ.get(
            "ORCHESTRATOR_URL", "http://orchestrator:8000"
        )
        self._http: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP client (shared, lazy-initialised)
    # ------------------------------------------------------------------

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=60.0)
        return self._http

    async def close(self) -> None:
        """Call on shutdown to release the HTTP connection pool."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ------------------------------------------------------------------
    # Run logging — mirrors orchestrator's /runs/log endpoint contract
    # ------------------------------------------------------------------

    async def run_log(
        self,
        run_id: str,
        event: str,
        details: dict[str, Any] | None = None,
        *,
        status: str = "ok",
        duration_ms: int | None = None,
    ) -> None:
        """
        POST a step event to the orchestrator run log.

        Failures are swallowed and logged locally — a logging failure must
        never crash the agent's primary operation.
        """
        await _run_log(
            http=self.http,
            orchestrator_url=self._orchestrator_url,
            agent=self.name,
            run_id=run_id,
            event=event,
            status=status,
            duration_ms=duration_ms,
            details=details or {},
            log=self.log,
        )

    # ------------------------------------------------------------------
    # Retry decorator factory
    # ------------------------------------------------------------------

    @staticmethod
    def with_retry(
        attempts: int = 3,
        min_wait: float = 1.0,
        max_wait: float = 10.0,
    ):
        """
        Tenacity retry decorator for LLM / HTTP calls.

        Default: 3 attempts, exponential backoff 1–10 s.
        Only retries on httpx.HTTPError and general Exception;
        does NOT retry on Pydantic ValidationError (caller bug, not transient).
        """
        return retry(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(min=min_wait, max=max_wait),
            retry=retry_if_exception_type((httpx.HTTPError, TimeoutError)),
            reraise=True,
        )

    # ------------------------------------------------------------------
    # FastAPI health handler
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, str]:
        """
        Standard GET /health response.

        Override in subclass to add dependency checks (DB, Ollama, etc.)
        and return {"status": "degraded"} or {"status": "error"} accordingly.
        """
        return {"status": "ok"}
