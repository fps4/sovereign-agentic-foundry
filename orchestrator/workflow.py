from __future__ import annotations

import json
import os
from typing import TypedDict

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph

from standards import load_standards

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
CODER_URL = os.getenv("CODER_URL", "http://coder:8001")
DESIGNER_URL = os.getenv("DESIGNER_URL", "http://designer:8003")

_STANDARDS_BLOCK = load_standards()

_CHAT_SYSTEM_PROMPT = """\
You are the assistant for a sovereign agentic platform that builds applications on \
self-hosted infrastructure. You help users understand what they can build, explain \
architecture decisions, and answer questions about the platform.

Be concise and practical. If a user seems to want to build something, let them know \
they can just describe it in plain language and you'll get started.""" + (
    "\n\n## Platform architecture standards\n\n"
    "All suggestions MUST comply with these standards:\n\n"
    + _STANDARDS_BLOCK if _STANDARDS_BLOCK else ""
)

_INTENT_PROMPT = """\
You are a binary intent classifier for a sovereign agentic platform.

Classify the user message and respond with ONLY valid JSON.

Schema: {"intent": "build" | "chat"}

Rules:
- "build": the user wants to CREATE a new application or add a feature to an existing one
- "chat": questions, explanations, general conversation, greetings

Examples:
- "build me a form for patient intake" → {"intent": "build"}
- "I need a dashboard to track sales" → {"intent": "build"}
- "what is a connector?" → {"intent": "chat"}
- "how does the platform work?" → {"intent": "chat"}
"""


class State(TypedDict):
    user_id: str
    message: str
    history: list
    reply: str
    intent: str
    task_spec: dict
    org: str
    repo_url: str | None
    issue_url: str | None


def classify(state: State) -> State:
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, format="json")
    result = llm.invoke(
        [SystemMessage(content=_INTENT_PROMPT), HumanMessage(content=state["message"])]
    )
    intent = "chat"
    try:
        intent = json.loads(result.content).get("intent", "chat")
        if intent not in ("build", "chat"):
            intent = "chat"
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return {**state, "intent": intent}


def respond(state: State) -> State:
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)
    msgs = [SystemMessage(content=_CHAT_SYSTEM_PROMPT)]
    for turn in state.get("history", []):
        msgs.append(
            HumanMessage(content=turn["content"])
            if turn["role"] == "user"
            else AIMessage(content=turn["content"])
        )
    msgs.append(HumanMessage(content=state["message"]))
    result = llm.invoke(msgs)
    return {**state, "reply": result.content}


def design(state: State) -> State:
    """Call the designer agent. Returns clarifying reply or ready spec."""
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{DESIGNER_URL}/design",
                json={
                    "user_id": state["user_id"],
                    "message": state["message"],
                    "history": state.get("history", []),
                    "org": state["org"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return {**state, "intent": "chat", "reply": f"I'm having trouble reaching the designer right now ({exc}). Please try again in a moment."}

    if data["status"] == "ready":
        return {
            **state,
            "intent": "build",
            "reply": data["reply"],
            "task_spec": data.get("spec") or {},
            "repo_url": data.get("repo_url"),
            "issue_url": data.get("issue_url"),
        }
    return {**state, "intent": "clarifying", "reply": data["reply"]}


def _route_classify(state: State) -> str:
    return state["intent"]


def _route_design(state: State) -> str:
    return state["intent"]  # "build" or "clarifying"


workflow = StateGraph(State)
workflow.add_node("classify", classify)
workflow.add_node("respond", respond)
workflow.add_node("design", design)
workflow.set_entry_point("classify")
workflow.add_conditional_edges(
    "classify", _route_classify, {"chat": "respond", "build": "design"}
)
workflow.add_conditional_edges(
    "design", _route_design, {"build": END, "clarifying": END}
)
workflow.add_edge("respond", END)

graph = workflow.compile()


# ── Background build ──────────────────────────────────────────────────────────

async def run_build(spec: dict, org: str, telegram_id: int, bot_token: str, app_id: int) -> None:
    """Call the coder agent and push the result to Telegram. Runs as a background task."""
    name = spec.get("name", "your app")

    async def _telegram(text: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": telegram_id, "text": text, "parse_mode": "Markdown"},
            )

    from db import update_app_status
    await update_app_status(app_id, "provisioning")

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{CODER_URL}/build", json={**spec, "org": org})
            resp.raise_for_status()
            data = resp.json()

        await update_app_status(
            app_id, "active",
            repo_url=data["repo_url"],
            app_url=data["app_url"],
        )
        await _telegram(
            f"*{name}* is ready!\n\n"
            f"Open it: {data['app_url']}\n"
            f"Code: {data['repo_url']}\n\n"
            f"It updates automatically whenever you push to main."
        )
    except Exception as exc:
        await update_app_status(app_id, "failed", error_detail=str(exc))
        await _telegram(
            f"Build failed for *{name}*.\n\n"
            f"Error: {exc}\n\n"
            f"Use /fix to log the issue or try again."
        )


_STANDARDS_BLOCK = load_standards()

_BASE_PROMPT = """\
You are the assistant for a sovereign agentic platform that helps users design \
and build applications on self-hosted infrastructure. You can:
- Help users describe what they want to build
- Explain architecture decisions and patterns
- Guide users through the build process
- Answer questions about the platform

Be concise and practical. When a user describes something they want to build, ask \
clarifying questions to understand: what kind of app, what stack, any specific requirements."""

SYSTEM_PROMPT = _BASE_PROMPT + (
    "\n\n## Platform architecture standards\n\n"
    "All suggestions and generated code MUST comply with these standards:\n\n"
    + _STANDARDS_BLOCK
    if _STANDARDS_BLOCK
    else ""
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
    msgs = [SystemMessage(content=SYSTEM_PROMPT)]
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

    lines = [f"Got it! Here's what I'm going to build:\n"]
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

async def run_build(spec: dict, org: str, telegram_id: int, bot_token: str, app_id: int) -> None:
    """Call the coder agent and push the result to Telegram. Runs as a background task."""
    name = spec.get("name", "your app")

    async def _telegram(text: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": telegram_id, "text": text, "parse_mode": "Markdown"},
            )

    from db import update_app_status
    await update_app_status(app_id, "provisioning")

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{CODER_URL}/build", json={**spec, "org": org})
            resp.raise_for_status()
            data = resp.json()

        await update_app_status(
            app_id, "active",
            repo_url=data["repo_url"],
            app_url=data["app_url"],
        )
        await _telegram(
            f"*{name}* is ready!\n\n"
            f"Open it: {data['app_url']}\n"
            f"Code: {data['repo_url']}\n\n"
            f"It updates automatically whenever you push to main."
        )
    except Exception as exc:
        await update_app_status(app_id, "failed", error_detail=str(exc))
        await _telegram(
            f"Build failed for *{name}*.\n\n"
            f"Error: {exc}\n\n"
            f"Use /fix to log the issue or try /build again."
        )
