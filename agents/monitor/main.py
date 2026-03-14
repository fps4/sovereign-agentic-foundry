"""Log monitoring agent.

Polls running platform app containers for errors and reports them to the
orchestrator's /apps/{name}/report-issue endpoint, which owns deduplication,
Gitea issue creation, LLM summarisation, and Telegram notifications.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time

import docker
import httpx

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8000")
POLL_INTERVAL = int(os.getenv("MONITOR_POLL_INTERVAL", "60"))
COOLDOWN = int(os.getenv("MONITOR_COOLDOWN", "600"))
LOG_LINES = int(os.getenv("MONITOR_LOG_LINES", "50"))

_ERROR_RE = re.compile(
    r"\b(error|exception|traceback|fatal|panic|critical)\b",
    re.IGNORECASE,
)

# container_id → monotonic timestamp of last check that found errors
_cooldowns: dict[str, float] = {}


def _platform_containers() -> list:
    client = docker.from_env()
    return client.containers.list(
        all=True, filters={"label": "platform.owner"}
    )


def _read_logs(container) -> str:
    return container.logs(tail=LOG_LINES, timestamps=False).decode("utf-8", errors="replace")


async def _platform_containers_async() -> list:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _platform_containers)


async def _read_logs_async(container) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _read_logs, container)


def _is_breaking(container) -> bool:
    """A container is breaking if it has exited or its health check is unhealthy."""
    if container.status != "running":
        return True
    health = container.attrs.get("State", {}).get("Health", {})
    return health.get("Status") == "unhealthy"


def _error_hash(logs: str) -> str:
    """Stable hash of the first error line found — used for deduplication."""
    for line in logs.splitlines():
        if _ERROR_RE.search(line):
            normalised = re.sub(r"\d+", "", line.lower()).strip()
            return hashlib.sha256(normalised.encode()).hexdigest()[:16]
    return hashlib.sha256(logs[-500:].encode()).hexdigest()[:16]


async def _check(container) -> None:
    owner = container.labels.get("platform.owner", "")
    if not owner.startswith("user-"):
        return
    try:
        telegram_id = int(owner.split("-", 1)[1])
    except (ValueError, IndexError):
        log.warning("Cannot parse telegram_id from label: %s", owner)
        return

    breaking = _is_breaking(container)

    now = time.monotonic()
    if not breaking and now - _cooldowns.get(container.id, 0) < COOLDOWN:
        return

    logs = await _read_logs_async(container)
    if not breaking and not _ERROR_RE.search(logs):
        return

    _cooldowns[container.id] = now
    error_hash = _error_hash(logs)

    log.info(
        "Reporting issue for %s (breaking=%s hash=%s)",
        container.name, breaking, error_hash,
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/apps/{container.name}/report-issue",
                json={
                    "telegram_id": telegram_id,
                    "log_excerpt": logs[-2000:],
                    "is_breaking": breaking,
                    "error_hash": error_hash,
                },
            )
            resp.raise_for_status()
            result = resp.json()
            log.info(
                "report-issue response for %s: notified=%s issue_url=%s",
                container.name, result.get("notified"), result.get("issue_url"),
            )
    except httpx.HTTPError as exc:
        log.error("Failed to report issue for %s: %s", container.name, exc)


async def monitor_loop() -> None:
    log.info(
        "Monitor started — poll=%ds cooldown=%ds log_lines=%d",
        POLL_INTERVAL, COOLDOWN, LOG_LINES,
    )
    while True:
        try:
            containers = await _platform_containers_async()
            log.debug("Checking %d platform container(s)", len(containers))
            for container in containers:
                await _check(container)
        except Exception as exc:
            log.error("Monitor loop error: %s", exc)
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(monitor_loop())
