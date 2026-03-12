from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from workflow import graph

app = FastAPI(title="Sovereign Agentic Foundry — Orchestrator")


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        result = await graph.ainvoke(
            {"user_id": req.user_id, "message": req.message, "reply": ""}
        )
        return ChatResponse(reply=result["reply"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
