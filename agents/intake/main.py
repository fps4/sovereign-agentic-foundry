"""Intake agent — multi-turn conversation that converges to a locked app spec.

Receives a message + conversation history from the gateway, calls Ollama, and
returns either a clarifying question or a locked spec.  Stateless: all history
is owned by the gateway (stored in Postgres) and passed on each call.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pythonjsonlogger.jsonlogger import JsonFormatter

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

APP_TYPES = ["form", "dashboard", "workflow", "connector", "assistant"]

SYSTEM_PROMPT = f"""You are an expert software product analyst helping a user define a web application to be automatically built.

Your job is to ask clarifying questions until you have enough information to produce a complete, unambiguous application specification. Then lock the spec.

APP TYPES available: {", ".join(APP_TYPES)}
- form: FastAPI + SQLite CRUD (data entry and retrieval)
- dashboard: read-only data visualization
- workflow: multi-stage task tracking with status transitions
- connector: headless backend integration (API-to-API)
- assistant: RAG chat over uploaded documents

REQUIRED spec fields before locking:
- name: short kebab-case identifier (e.g. expense-tracker)
- title: human-readable title
- app_type: one of the types above
- description: 2-3 sentence summary of purpose
- entities: list of main data objects (e.g. ["expense", "category"])
- features: list of key features (3-7 bullet points)

RULES:
- Ask ONE clarifying question at a time. Never ask multiple questions in one message.
- Do not lock the spec until ALL required fields can be inferred with confidence.
- When ready to lock, output ONLY valid JSON (no markdown, no explanation) with this structure:
  {{"spec_locked": true, "spec": {{"name": "...", "title": "...", "app_type": "...", "description": "...", "entities": [...], "features": [...]}}}}
- If still clarifying, output ONLY a plain text question (no JSON).
- Never mention internal field names to the user. Ask naturally.
"""


def _setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


log = _setup_logger("intake")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("intake.startup", extra={"model": OLLAMA_MODEL})
    yield


app = FastAPI(title="Intake Agent", lifespan=lifespan)


# ── Models ─────────────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []


class ChatResponse(BaseModel):
    reply: str
    spec_locked: bool = False
    spec: dict[str, Any] | None = None


# ── Ollama call ─────────────────────────────────────────────────────────────────

async def _call_ollama(messages: list[dict]) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
    except httpx.HTTPError as e:
        log.error("ollama.error", extra={"error": str(e)})
        raise HTTPException(status_code=502, detail=f"LLM unavailable: {e}")


# ── Spec parsing ────────────────────────────────────────────────────────────────

def _try_parse_spec(text: str) -> dict | None:
    """Return parsed spec dict if the LLM output is a locked spec, else None."""
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
        if data.get("spec_locked") and isinstance(data.get("spec"), dict):
            spec = data["spec"]
            required = {"name", "title", "app_type", "description", "entities", "features"}
            if required.issubset(spec.keys()) and spec["app_type"] in APP_TYPES:
                return spec
    except (json.JSONDecodeError, KeyError):
        pass
    return None


# ── Endpoint ───────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in req.history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.message})

    raw = await _call_ollama(messages)
    log.info("intake.llm_response", extra={"length": len(raw)})

    spec = _try_parse_spec(raw)
    if spec:
        log.info("intake.spec_locked", extra={"name": spec.get("name")})
        return ChatResponse(
            reply=f"Great, I have everything I need. I'll build **{spec['title']}** now.",
            spec_locked=True,
            spec=spec,
        )

    return ChatResponse(reply=raw, spec_locked=False)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="ollama_unavailable")
