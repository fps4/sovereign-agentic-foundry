from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TypedDict

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph
from pythonjsonlogger.jsonlogger import JsonFormatter

from standards import load_standards

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
CODER_URL = os.getenv("CODER_URL", "http://coder:8001")
DESIGNER_URL = os.getenv("DESIGNER_URL", "http://designer:8003")


def _setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


log = _setup_logger("workflow")

_STANDARDS_BLOCK = load_standards()

_CHAT_SYSTEM_PROMPT = """\
You are the assistant for a sovereign agentic platform that helps users design \
and build applications on self-hosted infrastructure. You can:
- Help users describe what they want to build
- Explain architecture decisions and patterns
- Guide users through the build process
- Answer questions about the platform

Be concise and practical. When a user describes something they want to build, ask \
clarifying questions to understand: what kind of app, what stack, any specific requirements.""" + (
    "\n\n## Platform architecture standards\n\n"
    "All suggestions and generated code MUST comply with these standards:\n\n"
    + _STANDARDS_BLOCK if _STANDARDS_BLOCK else ""
)

_CLASSIFY_PROMPT = """\
You are an intent classifier for a sovereign agentic platform.

Classify the user message and respond with ONLY valid JSON — no markdown, no explanation.

Schema:
{
  "intent": "build" or "chat",
  "app_type": "form" | "dashboard" | "workflow" | "connector" | "assistant" | "unknown",
  "task_spec": {
    "name": "kebab-case-repo-name",
    "description": "one-sentence description",
    "stack": "python-fastapi | node-express | go-gin | ...",
    "requirements": ["feature1", "feature2"]
  }
}

App type definitions:
- "form": collect or manage structured data — forms, registries, records
- "dashboard": display or visualise data, read-only interface
- "workflow": multi-step processes with stages, assignments, notifications
- "connector": headless backend linking two systems, no UI
- "assistant": RAG chat or Q&A over documents
- "unknown": cannot determine the type from the description

For "chat", use: {"intent": "chat", "app_type": "", "task_spec": {}}

Rules:
- Only set intent="build" when the user clearly wants to CREATE something new
- name must be kebab-case
- stack defaults to python-fastapi if unclear
- All three fields (name, description, stack) are required for a valid build intent
- If intent="build" but the app type is ambiguous, set app_type="unknown"
"""

_APP_TYPE_MENU = (
    "I'd love to help! To point you in the right direction, "
    "which of these best describes what you have in mind?\n\n"
    "• *Form* — capture or manage information (e.g. registrations, requests, records)\n"
    "• *Dashboard* — see data at a glance (e.g. sales, performance, live metrics)\n"
    "• *Workflow* — move things through steps or approvals (e.g. onboarding, reviews)\n"
    "• *Connector* — connect two services automatically, no screen needed\n"
    "• *Assistant* — get answers from your documents or knowledge base\n\n"
    "Just tell me again what you'd like, mentioning the type — for example:\n"
    "_I need a Form to collect patient intake information_"
)


class State(TypedDict):
    user_id: str
    message: str
    history: list
    reply: str
    intent: str
    task_spec: dict
    org: str
    run_id: str


def classify(state: State) -> State:
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, format="json")
    result = llm.invoke(
        [SystemMessage(content=_CLASSIFY_PROMPT), HumanMessage(content=state["message"])]
    )
    intent = "chat"
    task_spec: dict = {}
    try:
        data = json.loads(result.content)
        intent = data.get("intent", "chat")
        app_type = data.get("app_type", "")
        task_spec = data.get("task_spec", {})
        if intent == "build":
            if not all(k in task_spec for k in ("name", "description", "stack")):
                intent = "chat"
                task_spec = {}
            elif app_type == "unknown":
                intent = "clarify_type"
            else:
                task_spec["app_type"] = app_type
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return {**state, "intent": intent, "task_spec": task_spec}


def ask_type(state: State) -> State:
    return {**state, "reply": _APP_TYPE_MENU}


def respond(state: State) -> State:
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)
    msgs = [SystemMessage(content=_CHAT_SYSTEM_PROMPT)]
    for turn in state.get("history", []):
        if turn["role"] == "user":
            msgs.append(HumanMessage(content=turn["content"]))
        else:
            msgs.append(AIMessage(content=turn["content"]))
    msgs.append(HumanMessage(content=state["message"]))
    result = llm.invoke(msgs)
    return {**state, "reply": result.content}


def confirm_build(state: State) -> State:
    """Return an immediate acknowledgement — the actual build runs in the background."""
    spec = state["task_spec"]
    name = spec.get("name", "your app")
    description = spec.get("description", "")
    app_type = spec.get("app_type", "")
    requirements = spec.get("requirements", [])

    lines = ["Got it! Here's what I'm going to build:\n"]
    lines.append(f"*{name}* — {description}")
    if app_type:
        lines.append(f"Type: {app_type}")
    if requirements:
        lines.append(f"Features: {', '.join(requirements)}")
    lines.append("\nScaffolding the project and pushing to your repo now. I'll message you when it's ready.")

    return {**state, "reply": "\n".join(lines)}


def _route(state: State) -> str:
    return state["intent"]


workflow = StateGraph(State)
workflow.add_node("classify", classify)
workflow.add_node("respond", respond)
workflow.add_node("confirm_build", confirm_build)
workflow.add_node("ask_type", ask_type)
workflow.set_entry_point("classify")
workflow.add_conditional_edges(
    "classify", _route, {"chat": "respond", "build": "confirm_build", "clarify_type": "ask_type"}
)
workflow.add_edge("respond", END)
workflow.add_edge("confirm_build", END)
workflow.add_edge("ask_type", END)

graph = workflow.compile()


# ── Background build ──────────────────────────────────────────────────────────

async def run_build(
    spec: dict,
    org: str,
    telegram_id: int,
    bot_token: str,
    app_id: int,
    run_id: str = "",
) -> None:
    """Call the coder agent and push the result to Telegram. Runs as a background task."""
    name = spec.get("name", "your app")
    _t0 = asyncio.get_event_loop().time()

    async def _telegram(text: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": telegram_id, "text": text, "parse_mode": "Markdown"},
            )

    from db import update_app_status, log_run_step

    log.info("build.provisioning", extra={"app_id": app_id, "app_name": name, "org": org, "run_id": run_id})
    await update_app_status(app_id, "provisioning")
    if run_id:
        await log_run_step(
            run_id=run_id, agent="orchestrator", event="build.provisioning",
            repo=name, telegram_id=telegram_id,
            details={"stack": spec.get("stack"), "app_type": spec.get("app_type")},
        )

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{CODER_URL}/build", json={**spec, "org": org, "run_id": run_id})
            resp.raise_for_status()
            data = resp.json()

        duration_ms = int((asyncio.get_event_loop().time() - _t0) * 1000)

        # Activate in Woodpecker CI so the push webhook triggers the pipeline
        try:
            from woodpecker import activate_repo
            await activate_repo(org, name)
        except Exception as exc:
            log.warning("woodpecker.activation_failed", extra={"app_name": name, "error": str(exc)})

        # Status is "building" — Woodpecker CI will deploy the container
        await update_app_status(
            app_id, "building",
            repo_url=data["repo_url"],
            app_url=data["app_url"],
        )
        log.info("build.active", extra={
            "app_id": app_id, "app_name": name,
            "repo_url": data["repo_url"], "app_url": data["app_url"], "run_id": run_id,
        })
        if run_id:
            await log_run_step(
                run_id=run_id, agent="orchestrator", event="build.active",
                repo=name, telegram_id=telegram_id, status="ok",
                duration_ms=duration_ms,
                details={"repo_url": data["repo_url"], "app_url": data["app_url"]},
            )
        await _telegram(
            f"✅ *{name}* code is ready — CI is building the container now!\n\n"
            f"Code: {data['repo_url']}\n"
            f"App (live in ~2 min): {data['app_url']}\n\n"
            f"It updates automatically on every push to main."
        )
    except Exception as exc:
        duration_ms = int((asyncio.get_event_loop().time() - _t0) * 1000)
        log.error("build.failed", extra={"app_id": app_id, "app_name": name, "error": str(exc), "run_id": run_id})
        await update_app_status(app_id, "failed", error_detail=str(exc))
        if run_id:
            await log_run_step(
                run_id=run_id, agent="orchestrator", event="build.failed",
                repo=name, telegram_id=telegram_id, status="error",
                duration_ms=duration_ms, details={"error": str(exc)},
            )
        await _telegram(
            f"Build failed for *{name}*.\n\n"
            f"Error: {exc}\n\n"
            f"Use /fix to log the issue or try again."
        )
