"""Gateway — API facade, user registry, and build pipeline dispatch."""
from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from pythonjsonlogger.jsonlogger import JsonFormatter

import auth
import db


def _setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


log = _setup_logger("gateway")

GITEA_URL = os.getenv("GITEA_URL", "http://gitea:3000")
GITEA_ADMIN_USER = os.getenv("GITEA_ADMIN_USER", "platform")
GITEA_ADMIN_PASS = os.getenv("GITEA_ADMIN_PASS", "")
APP_DOMAIN = os.getenv("APP_DOMAIN", "localhost")
INVITE_CODE = os.getenv("INVITE_CODE", "")
INTAKE_URL = os.getenv("INTAKE_URL", "http://intake:8001")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    log.info("gateway.startup")
    yield
    await db.close_pool()


app = FastAPI(title="Sovereign Agentic Foundry — Gateway", lifespan=lifespan)


# ── Gitea helpers ──────────────────────────────────────────────────────────────

def _gitea_auth() -> tuple[str, str]:
    return (GITEA_ADMIN_USER, GITEA_ADMIN_PASS)


async def _create_gitea_org(org: str, description: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{GITEA_URL}/api/v1/orgs",
            auth=_gitea_auth(),
            json={"username": org, "visibility": "private", "description": description},
        )
        if resp.status_code not in (201, 422):  # 422 = already exists
            resp.raise_for_status()


# ── Models ─────────────────────────────────────────────────────────────────────

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


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: str


class WebRegisterRequest(BaseModel):
    email: str
    password: str
    invite_code: str = ""


class AppInfo(BaseModel):
    id: int
    name: str
    description: str
    app_type: str
    status: str
    app_url: str | None
    repo_url: str | None
    issue_count: int


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    spec_locked: bool = False
    spec: dict | None = None


class RunLogRequest(BaseModel):
    run_id: str
    agent: str
    event: str
    repo: str | None = None
    task_ref: str | None = None
    status: str = "ok"
    payload: dict | None = None


# ── Telegram registration flow ─────────────────────────────────────────────────

@app.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest) -> RegisterResponse:
    log.info("user.register", extra={"telegram_id": req.telegram_id})
    user = await db.get_user(req.telegram_id)
    if user and user["verified"]:
        return RegisterResponse(code="", message="already_registered")
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
    try:
        await _create_gitea_org(org, f"Platform org for @{user['telegram_username'] or req.telegram_id}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Gitea error: {e}")

    tenant_id = await db.create_tenant(gitea_org=org)
    await db.verify_user(req.telegram_id, tenant_id)
    log.info("user.verified", extra={"telegram_id": req.telegram_id, "org": org, "tenant_id": tenant_id})
    return VerifyResponse(success=True, message="verified")


# ── Web portal auth ────────────────────────────────────────────────────────────

@app.post("/auth/register-web", response_model=LoginResponse)
async def register_web(req: WebRegisterRequest) -> LoginResponse:
    if INVITE_CODE and req.invite_code != INVITE_CODE:
        raise HTTPException(status_code=403, detail="invalid_invite_code")

    existing = await db.get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=409, detail="email_already_registered")

    org = f"web-{req.email.split('@')[0].lower().replace('.', '-')}-{secrets.token_hex(4)}"
    try:
        await _create_gitea_org(org, f"Platform org for {req.email}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Gitea error: {e}")

    tenant_id = await db.create_tenant(gitea_org=org)
    password_hash = auth.hash_password(req.password)
    user_id = await db.create_web_user(req.email, password_hash, tenant_id)

    log.info("user.register_web", extra={"email": req.email, "tenant_id": tenant_id})
    token = auth.create_token(user_id)
    return LoginResponse(token=token, user_id=user_id)


@app.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    user = await db.get_user_by_email(req.email)
    if not user or not user["password_hash"]:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    if not auth.verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid_credentials")

    token = auth.create_token(user["telegram_id"])
    return LoginResponse(token=token, user_id=user["telegram_id"])


# ── Chat ───────────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user_id: str = Depends(auth.get_current_user_id),
) -> ChatResponse:
    user = await db.get_user(user_id)
    if not user or not user["verified"]:
        raise HTTPException(status_code=403, detail="not_registered")

    # Persist the user's message
    await db.append_message(user_id, "user", req.message)

    # Load recent history (excluding the message we just stored)
    history = await db.get_history(user_id, limit=40)
    # history already includes the message we just appended; pass all but the last as context
    context = history[:-1]

    # Forward to intake agent
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{INTAKE_URL}/chat",
                json={"message": req.message, "history": context},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Intake agent error: {e}")

    # Persist the assistant reply
    await db.append_message(user_id, "assistant", data["reply"])

    log.info("chat.turn", extra={"user_id": user_id, "spec_locked": data.get("spec_locked")})
    return ChatResponse(
        reply=data["reply"],
        spec_locked=data.get("spec_locked", False),
        spec=data.get("spec"),
    )


# ── Apps ───────────────────────────────────────────────────────────────────────

@app.get("/apps", response_model=list[AppInfo])
async def list_apps(
    telegram_id: int | None = None,
    user_id: str = Depends(auth.get_current_user_id),
) -> list[AppInfo]:
    user = await db.get_user(user_id)
    if not user or not user["verified"] or not user["tenant_id"]:
        raise HTTPException(status_code=403, detail="not_registered")

    apps = await db.get_apps_for_tenant(user["tenant_id"])
    return [
        AppInfo(
            id=a["id"],
            name=a["name"],
            description=a["description"] or "",
            app_type=a["app_type"],
            status=a["status"],
            app_url=a["app_url"],
            repo_url=a["repo_url"],
            issue_count=a["issue_count"],
        )
        for a in apps
    ]


# ── Status ─────────────────────────────────────────────────────────────────────

@app.get("/me")
async def me(user_id: str = Depends(auth.get_current_user_id)) -> dict:
    user = await db.get_user(user_id)
    return {
        "user_id": user_id,
        "email": user["email"] if user else None,
        "registered": bool(user and user["verified"]),
    }


# ── Agent run log ──────────────────────────────────────────────────────────────

@app.post("/runs/log", status_code=204)
async def log_run(req: RunLogRequest) -> None:
    await db.log_run_step(
        run_id=req.run_id,
        agent=req.agent,
        event=req.event,
        repo=req.repo,
        task_ref=req.task_ref,
        status=req.status,
        payload=req.payload,
    )


@app.get("/runs")
async def get_runs(
    repo: str | None = None,
    run_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    rows = await db.get_run_steps(repo=repo, run_id=run_id, limit=limit)
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
    return rows


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
