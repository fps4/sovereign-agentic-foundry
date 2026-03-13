"""Log monitoring agent.

Polls running platform app containers for errors, summarises them with an LLM,
and pushes a Telegram message directly to the app owner — no user action needed.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time

import docker
import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
POLL_INTERVAL = int(os.getenv("MONITOR_POLL_INTERVAL", "60"))
COOLDOWN = int(os.getenv("MONITOR_COOLDOWN", "600"))
LOG_LINES = int(os.getenv("MONITOR_LOG_LINES", "50"))

_ERROR_RE = re.compile(
    r"\b(error|exception|traceback|fatal|panic|critical)\b",
    re.IGNORECASE,
)

_SUMMARIZE_PROMPT = """\
You are a platform monitoring agent. A deployed app has errors in its logs.
Summarise the issue in 2-3 sentences for a non-technical user.
Cover: what went wrong, the likely cause, and a suggested action.
Do not include raw stack traces or log lines. Be concise and clear.
"""

# container_id → monotonic timestamp of last alert
_cooldowns: dict[str, float] = {}


def _platform_containers() -> list:
    client = docker.from_env()
    return client.containers.list(filters={"label": "platform.owner"})


def _read_logs(container) -> str:
    return container.logs(tail=LOG_LINES, timestamps=False).decode("utf-8", errors="replace")


def _has_errors(logs: str) -> bool:
    return bool(_ERROR_RE.search(logs))


async def _summarise(app_name: str, logs: str) -> str:
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)
    result = await llm.ainvoke([
        SystemMessage(content=_SUMMARIZE_PROMPT),
        HumanMessage(content=f"App: {app_name}\n\nLogs:\n{logs[-2000:]}"),
    ])
    return result.content.strip()


async def _notify(telegram_id: int, app_name: str, summary: str) -> None:
    text = f"Issue detected in *{app_name}*\n\n{summary}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": telegram_id, "text": text, "parse_mode": "Markdown"},
        )


async def _check(container) -> None:
    owner = container.labels.get("platform.owner", "")
    if not owner.startswith("user-"):
        return
    try:
        telegram_id = int(owner.split("-", 1)[1])
    except (ValueError, IndexError):
        log.warning("Cannot parse telegram_id from label: %s", owner)
        return

    now = time.monotonic()
    if now - _cooldowns.get(container.id, 0) < COOLDOWN:
        return

    logs = _read_logs(container)
    if not _has_errors(logs):
        return

    _cooldowns[container.id] = now
    log.info("Errors in %s — summarising", container.name)

    try:
        summary = await _summarise(container.name, logs)
    except Exception as exc:
        log.error("Summarisation failed for %s: %s", container.name, exc)
        summary = "Errors were detected but could not be summarised automatically."

    await _notify(telegram_id, container.name, summary)
    log.info("Alert sent to telegram_id=%d for app %s", telegram_id, container.name)


async def monitor_loop() -> None:
    log.info(
        "Monitor started — poll=%ds cooldown=%ds log_lines=%d",
        POLL_INTERVAL, COOLDOWN, LOG_LINES,
    )
    while True:
        try:
            containers = _platform_containers()
            log.debug("Checking %d platform container(s)", len(containers))
            for container in containers:
                await _check(container)
        except Exception as exc:
            log.error("Monitor loop error: %s", exc)
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(monitor_loop())
