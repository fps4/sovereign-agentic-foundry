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

Classify the user message as "build" (user wants to CREATE a new software project) \
or "chat" (question, advice, general conversation).

Respond with ONLY valid JSON — no markdown, no explanation.

Schema:
{
  "intent": "build" or "chat",
  "task_spec": {
    "name": "kebab-case-repo-name",
    "description": "one-sentence description",
    "stack": "python-fastapi | node-express | go-gin | ...",
    "requirements": ["feature1", "feature2"]
  }
}

For "chat", use: {"intent": "chat", "task_spec": {}}

Rules:
- Only set intent="build" when the user clearly wants to CREATE something new
- name must be kebab-case
- stack defaults to python-fastapi if unclear
- All three fields (name, description, stack) are required for a valid build intent
"""


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
        task_spec = data.get("task_spec", {})
        if intent == "build" and not all(
            k in task_spec for k in ("name", "description", "stack")
        ):
            # Incomplete spec — fall back to chat so the user is asked for details
            intent = "chat"
            task_spec = {}
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return {**state, "intent": intent, "task_spec": task_spec}


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
        f"Project scaffolded and committed to Gitea.\n\n"
        f"Repo: {data['repo_url']}\n\n"
        f"Woodpecker CI will trigger a pipeline on the next push to main."
    )
    return {**state, "reply": reply}


def _route(state: State) -> str:
    return state["intent"]


workflow = StateGraph(State)
workflow.add_node("classify", classify)
workflow.add_node("respond", respond)
workflow.add_node("invoke_coder", invoke_coder)
workflow.set_entry_point("classify")
workflow.add_conditional_edges("classify", _route, {"chat": "respond", "build": "invoke_coder"})
workflow.add_edge("respond", END)
workflow.add_edge("invoke_coder", END)

graph = workflow.compile()
