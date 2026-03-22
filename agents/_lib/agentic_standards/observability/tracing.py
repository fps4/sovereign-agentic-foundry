"""
Structured logging and run_log — the canonical implementations for the foundry.

Every agent currently copy-pastes _setup_logger() and a _log() helper.
This module is the single source of truth for both.

Usage:
    from agentic_standards.observability.tracing import get_logger, run_log

    log = get_logger("coder")
    log.info("build.start", extra={"run_id": run_id, "name": name})

    # inside an async context:
    await run_log(http, orchestrator_url, agent="coder", run_id=..., event=...)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

try:
    from pythonjsonlogger import jsonlogger  # type: ignore[import-untyped]
    _JSON_LOGGER_AVAILABLE = True
except ImportError:
    _JSON_LOGGER_AVAILABLE = False


# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------


def get_logger(name: str) -> logging.Logger:
    """
    Return a structured-JSON logger for the given service name.

    Idempotent — safe to call multiple times with the same name.
    Falls back to plain text if python-json-logger is not installed.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler()

    if _JSON_LOGGER_AVAILABLE:
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


# ---------------------------------------------------------------------------
# Run log — POST step events to orchestrator
# ---------------------------------------------------------------------------


async def run_log(
    *,
    http: httpx.AsyncClient,
    orchestrator_url: str,
    agent: str,
    run_id: str,
    event: str,
    status: str = "ok",
    duration_ms: int | None = None,
    details: dict[str, Any] | None = None,
    log: logging.Logger | None = None,
) -> None:
    """
    POST a step event to the orchestrator's /runs/log endpoint.

    Silently swallows HTTP errors — a logging failure must never crash
    the agent's primary operation. Errors are recorded locally.

    Args:
        http: Shared AsyncClient instance (caller owns lifecycle).
        orchestrator_url: Base URL of the orchestrator service.
        agent: Name of the emitting agent (e.g. 'coder').
        run_id: Correlation ID for this pipeline run.
        event: Dot-separated event name (e.g. 'build.scaffold.done').
        status: 'ok', 'error', or 'warning'.
        duration_ms: Optional wall-clock duration for this step.
        details: Arbitrary structured context (no secrets).
        log: Optional logger for local error recording.
    """
    payload: dict[str, Any] = {
        "run_id": run_id,
        "agent": agent,
        "event": event,
        "status": status,
        "details": details or {},
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms

    try:
        await http.post(f"{orchestrator_url}/runs/log", json=payload, timeout=5.0)
    except Exception as exc:  # noqa: BLE001
        if log:
            log.warning(
                "run_log.failed",
                extra={"run_id": run_id, "event": event, "error": str(exc)},
            )
