from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import db
from workflow import graph

GITEA_URL = os.getenv("GITEA_URL", "http://gitea:3000")
GITEA_ADMIN_USER = os.getenv("GITEA_ADMIN_USER", "platform")
GITEA_ADMIN_PASS = os.getenv("GITEA_ADMIN_PASS", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    yield
    await db.close_pool()


app = FastAPI(title="Sovereign Agentic Foundry — Orchestrator", lifespan=lifespan)


# ── Models ────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


class RegisterRequest(BaseModel):
    telegram_id: int
    telegram_username: str


class RegisterResponse(BaseModel):
    code: str
    message: str


class VerifyRequest(BaseModel):
    telegram_id: int
    code: str


class VerifyResponse(BaseModel):
    success: bool
    message: str


class AppInfo(BaseModel):
    name: str
    description: str
    url: str


class MeResponse(BaseModel):
    registered: bool


class IssueRequest(BaseModel):
    telegram_id: int
    repo_name: str
    title: str
    body: str


class IssueResponse(BaseModel):
    issue_url: str


class DeleteAppRequest(BaseModel):
    telegram_id: int
    repo_name: str


class DeleteAppResponse(BaseModel):
    success: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gitea_auth() -> tuple[str, str]:
    return (GITEA_ADMIN_USER, GITEA_ADMIN_PASS)


async def _create_gitea_org(org: str, description: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{GITEA_URL}/api/v1/orgs",
            auth=_gitea_auth(),
            json={
                "username": org,
                "visibility": "private",
                "description": description,
            },
        )
        if resp.status_code not in (201, 422):  # 422 = already exists
            resp.raise_for_status()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest) -> RegisterResponse:
    user = await db.get_user(req.telegram_id)
    if user and user["verified"]:
        return RegisterResponse(
            code="", message="already_registered"
        )
    code = f"{secrets.randbelow(900000) + 100000}"
    await db.upsert_pending_user(req.telegram_id, req.telegram_username, code)
    return RegisterResponse(code=code, message="pending_verification")


@app.post("/verify", response_model=VerifyResponse)
async def verify(req: VerifyRequest) -> VerifyResponse:
    user = await db.get_user(req.telegram_id)
    if not user:
        return VerifyResponse(success=False, message="not_registered")
    if user["verified"]:
        return VerifyResponse(success=True, message="already_verified")
    if user["verification_code"] != req.code:
        return VerifyResponse(success=False, message="wrong_code")

    org = f"user-{req.telegram_id}"
    description = f"Platform org for @{user['telegram_username'] or req.telegram_id}"
    try:
        await _create_gitea_org(org, description)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Gitea error: {e}")

    await db.verify_user(req.telegram_id, org)
    return VerifyResponse(success=True, message="verified")


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    user = await db.get_user(int(req.user_id))
    if not user or not user["verified"]:
        return ChatResponse(
            reply="You'll need an account first. Send /register to get started."
        )
    try:
        result = await graph.ainvoke(
            {
                "user_id": req.user_id,
                "message": req.message,
                "reply": "",
                "intent": "",
                "task_spec": {},
                "org": user["gitea_org"] or "",
            }
        )
        return ChatResponse(reply=result["reply"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/apps", response_model=list[AppInfo])
async def list_apps(telegram_id: int) -> list[AppInfo]:
    user = await db.get_user(telegram_id)
    if not user or not user["verified"]:
        raise HTTPException(status_code=403, detail="not_registered")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{GITEA_URL}/api/v1/orgs/{user['gitea_org']}/repos",
                auth=_gitea_auth(),
                params={"limit": 50},
            )
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Gitea unreachable: {e}")

    return [
        AppInfo(
            name=r["name"],
            description=r.get("description") or "No description",
            url=r["html_url"],
        )
        for r in resp.json()
    ]


@app.post("/issue", response_model=IssueResponse)
async def create_issue(req: IssueRequest) -> IssueResponse:
    user = await db.get_user(req.telegram_id)
    if not user or not user["verified"]:
        raise HTTPException(status_code=403, detail="not_registered")

    org = user["gitea_org"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{GITEA_URL}/api/v1/repos/{org}/{req.repo_name}/issues",
                auth=_gitea_auth(),
                json={"title": req.title, "body": req.body},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Gitea error: {e}")

    return IssueResponse(issue_url=data["html_url"])


@app.post("/delete-app", response_model=DeleteAppResponse)
async def delete_app(req: DeleteAppRequest) -> DeleteAppResponse:
    user = await db.get_user(req.telegram_id)
    if not user or not user["verified"]:
        raise HTTPException(status_code=403, detail="not_registered")

    org = user["gitea_org"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{GITEA_URL}/api/v1/repos/{org}/{req.repo_name}",
                auth=_gitea_auth(),
            )
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="app_not_found")
            resp.raise_for_status()
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Gitea error: {e}")

    return DeleteAppResponse(success=True)


@app.get("/me", response_model=MeResponse)
async def me(telegram_id: int) -> MeResponse:
    user = await db.get_user(telegram_id)
    return MeResponse(registered=bool(user and user["verified"]))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
