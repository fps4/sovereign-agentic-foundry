from __future__ import annotations

import os
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

SYSTEM_PROMPT = """You are the assistant for a sovereign agentic platform that helps \
users design and build applications on self-hosted infrastructure. You can:
- Help users describe what they want to build
- Explain architecture decisions and patterns
- Guide users through the build process
- Answer questions about the platform

Be concise and practical. When a user describes something they want to build, ask \
clarifying questions to understand: what kind of app, what stack, any specific requirements."""


class State(TypedDict):
    user_id: str
    message: str
    reply: str


def respond(state: State) -> State:
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)
    result = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=state["message"]),
        ]
    )
    return {**state, "reply": result.content}


workflow = StateGraph(State)
workflow.add_node("respond", respond)
workflow.set_entry_point("respond")
workflow.add_edge("respond", END)

graph = workflow.compile()
