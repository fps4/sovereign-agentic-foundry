from __future__ import annotations

import json
import os
from typing import TypedDict

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph

from standards import load_standards

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
CODER_URL = os.getenv("CODER_URL", "http://coder:8001")

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
    "• *Integration* — connect two services automatically, no screen needed\n"
    "• *Assistant* — get answers from your documents or knowledge base\n\n"
    "Just tell me again what you'd like, mentioning the type — for example:\n"
    "_I need a Form to collect patient intake information_"
)


class State(TypedDict):
    user_id: str
    message: str
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
                # Incomplete spec — fall back to chat so the user is asked for details
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
    result = llm.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=state["message"])]
    )
    return {**state, "reply": result.content}


async def invoke_coder(state: State) -> State:
    spec = {**state["task_spec"], "org": state.get("org", "")}
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{CODER_URL}/build", json=spec)
        resp.raise_for_status()
        data = resp.json()
    reply = (
        f"Your app is ready!\n\n"
        f"You can find it here: {data['repo_url']}\n\n"
        f"It will be built and deployed automatically when you push changes."
    )
    return {**state, "reply": reply}


def _route(state: State) -> str:
    return state["intent"]


workflow = StateGraph(State)
workflow.add_node("classify", classify)
workflow.add_node("respond", respond)
workflow.add_node("invoke_coder", invoke_coder)
workflow.add_node("ask_type", ask_type)
workflow.set_entry_point("classify")
workflow.add_conditional_edges(
    "classify", _route, {"chat": "respond", "build": "invoke_coder", "clarify_type": "ask_type"}
)
workflow.add_edge("respond", END)
workflow.add_edge("invoke_coder", END)
workflow.add_edge("ask_type", END)

graph = workflow.compile()
