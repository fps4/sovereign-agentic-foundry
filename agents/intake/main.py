"""Intake agent — multi-turn conversation that converges to a locked app spec.

Receives a message + conversation history from the gateway, calls the LLM via
LLMRouter, and returns either a clarifying question or a locked AppSpec.
Stateless: all history is owned by the gateway and passed on each call.
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agentic_standards.agent import BaseAgent
from agentic_standards.contracts.agent_io import AgentRequest, AgentResponse, AppSpec
from agentic_standards.router import LLMRouter, ModelTier

# ── Config ─────────────────────────────────────────────────────────────────────

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
STANDARDS_PATH = Path(os.getenv("STANDARDS_PATH", "/standards"))
PROMPTS_PATH = Path(__file__).parent / "prompts"

APP_TYPES = ["form", "dashboard", "workflow", "connector", "assistant"]

# ── Agent ──────────────────────────────────────────────────────────────────────


class IntakeAgent(BaseAgent):
    name = "intake"

    def __init__(self) -> None:
        super().__init__()
        # Per-agent model override: INTAKE_LLM_MODEL takes precedence over
        # the global MODEL_STANDARD tier var (ADR-0007).
        per_agent_model = os.getenv("INTAKE_LLM_MODEL")
        model_map = None
        if per_agent_model:
            from agentic_standards.router import _DEFAULT_MODEL_MAP
            model_map = {**_DEFAULT_MODEL_MAP, ModelTier.STANDARD: per_agent_model}
        self.llm = LLMRouter(model_map=model_map, api_base=OLLAMA_URL)
        self.system_prompt: str = ""

    def load_prompts(self) -> None:
        prompt_file = PROMPTS_PATH / "system.md"
        if not prompt_file.exists():
            raise RuntimeError(f"System prompt not found: {prompt_file}")
        base = prompt_file.read_text()

        agent_standard = STANDARDS_PATH / "agents" / "intake.yaml"
        if agent_standard.exists():
            base += f"\n\n--- AGENT STANDARDS ---\n{agent_standard.read_text()}"

        self.system_prompt = base


agent = IntakeAgent()


@asynccontextmanager
async def lifespan(app: FastAPI):
    agent.load_prompts()
    agent.log.info("intake.startup", extra={"standards_path": str(STANDARDS_PATH)})
    yield
    await agent.close()


app = FastAPI(title="Intake Agent", lifespan=lifespan)


# ── Request / response models ──────────────────────────────────────────────────


class Message(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class IntakeRequest(AgentRequest):
    message: str
    tenant_id: str
    history: list[Message] = []


class IntakeResponse(AgentResponse):
    reply: str = ""
    spec_locked: bool = False
    spec: AppSpec | None = None


# ── Spec parsing ───────────────────────────────────────────────────────────────


def _try_parse_spec(text: str) -> AppSpec | None:
    """Return AppSpec if the LLM output is a locked spec, else None."""
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
        if not (data.get("spec_locked") and isinstance(data.get("spec"), dict)):
            return None
        s = data["spec"]
        required = {"name", "description", "app_type", "requirements"}
        if not required.issubset(s.keys()):
            return None
        if s["app_type"] not in APP_TYPES:
            return None
        if len(s.get("requirements", [])) < 3:
            return None
        return AppSpec(
            name=s["name"],
            description=s["description"],
            app_type=s["app_type"],
            stack=s.get("stack", "python-fastapi"),
            requirements=s["requirements"],
            acceptance_criteria=s.get("acceptance_criteria", []),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


# ── Endpoint ───────────────────────────────────────────────────────────────────


@app.post("/intake", response_model=IntakeResponse)
async def intake(req: IntakeRequest) -> IntakeResponse:
    await agent.run_log(req.run_id, "intake.start", {"tenant_id": req.tenant_id})

    messages: list[dict] = [{"role": "system", "content": agent.system_prompt}]
    for m in req.history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.message})

    tier = ModelTier(req.model_tier)
    try:
        raw = await agent.llm.complete(messages, tier=tier)
    except Exception as exc:
        await agent.run_log(req.run_id, "intake.failed", {"error": str(exc)}, status="error")
        raise

    agent.log.info("intake.llm_response", extra={"length": len(raw)})

    spec = _try_parse_spec(raw)
    if spec:
        agent.log.info("intake.spec_locked", extra={"name": spec.name, "app_type": spec.app_type})
        await agent.run_log(req.run_id, "intake.done", {"spec_name": spec.name, "status": "ready"})
        return IntakeResponse(
            run_id=req.run_id,
            status="ok",
            reply=f"Got it — I have everything I need to build **{spec.name}**.",
            spec_locked=True,
            spec=spec,
        )

    await agent.run_log(req.run_id, "intake.done", {"status": "clarifying"})
    return IntakeResponse(run_id=req.run_id, status="ok", reply=raw, spec_locked=False)


# ── Health ─────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail={"status": "degraded", "reason": "ollama_unavailable"})
