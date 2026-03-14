from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pythonjsonlogger.jsonlogger import JsonFormatter

import db
from workflow import graph, run_build


def _setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


log = _setup_logger("orchestrator")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

_SUMMARIZE_PROMPT = """\
You are a platform monitoring agent. A deployed app has errors in its logs.
Summarise the issue in 2-3 sentences for a non-technical user.
Cover: what went wrong, the likely cause, and a suggested action.
Do not include raw stack traces or log lines. Be concise and clear.
"""
GITEA_URL = os.getenv("GITEA_URL", "http://gitea:3000")
GITEA_ADMIN_USER = os.getenv("GITEA_ADMIN_USER", "platform")
GITEA_ADMIN_PASS = os.getenv("GITEA_ADMIN_PASS", "")
APP_DOMAIN = os.getenv("APP_DOMAIN", "localhost")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    log.info("startup")
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
    app_type: str
    status: str
    url: str | None
    repo_url: str | None
    issue_count: int


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


class ReportIssueRequest(BaseModel):
    telegram_id: int
    log_excerpt: str
    is_breaking: bool
    error_hash: str


class ReportIssueResponse(BaseModel):
    issue_url: str | None
    notified: bool


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


async def _create_gitea_issue(org: str, repo: str, title: str, body: str) -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{GITEA_URL}/api/v1/repos/{org}/{repo}/issues",
            auth=_gitea_auth(),
            json={"title": title, "body": body},
        )
        resp.raise_for_status()
        return resp.json()["html_url"]


async def _summarise(app_name: str, log_excerpt: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_ollama import ChatOllama
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)
    result = await llm.ainvoke([
        SystemMessage(content=_SUMMARIZE_PROMPT),
        HumanMessage(content=f"App: {app_name}\n\nLogs:\n{log_excerpt[-2000:]}"),
    ])
    return result.content.strip()


async def _telegram_notify(telegram_id: int, text: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": telegram_id, "text": text, "parse_mode": "Markdown"},
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest) -> RegisterResponse:
    log.info("user.register", extra={"telegram_id": req.telegram_id})
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
    log.info("user.verify", extra={"telegram_id": req.telegram_id, "org": org})
    return VerifyResponse(success=True, message="verified")


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    user = await db.get_user(int(req.user_id))
    if not user or not user["verified"]:
        return ChatResponse(
            reply="You'll need an account first. Send /register to get started."
        )
    try:
        org = user["gitea_org"] or ""
        history = await db.get_history(req.user_id)
        result = await graph.ainvoke(
            {
                "user_id": req.user_id,
                "message": req.message,
                "history": history,
                "reply": "",
                "intent": "",
                "task_spec": {},
                "org": org,
                "repo_url": None,
                "issue_url": None,
            }
        )
        log.info("chat.request", extra={"user_id": req.user_id, "intent": result["intent"], "message_preview": req.message[:60]})
        await db.append_message(req.user_id, "user", req.message)
        await db.append_message(req.user_id, "assistant", result["reply"])
        if result["intent"] == "build" and result.get("task_spec"):
            spec = result["task_spec"]
            app_id = await db.register_app(
                telegram_id=int(req.user_id),
                name=spec["name"],
                description=spec.get("description", ""),
                app_type=spec.get("app_type", ""),
            )
            log.info("build.queued", extra={"user_id": req.user_id, "app_id": app_id, "app_name": spec["name"], "org": org})
            asyncio.create_task(
                run_build(
                    spec=spec,
                    org=org,
                    telegram_id=int(req.user_id),
                    bot_token=TELEGRAM_BOT_TOKEN,
                    app_id=app_id,
                )
            )
        return ChatResponse(reply=result["reply"])
    except Exception as e:
        log.error("chat.error", extra={"user_id": req.user_id, "error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/apps", response_model=list[AppInfo])
async def list_apps(telegram_id: int) -> list[AppInfo]:
    user = await db.get_user(telegram_id)
    if not user or not user["verified"]:
        raise HTTPException(status_code=403, detail="not_registered")

    apps = await db.get_apps_for_user(telegram_id)
    return [
        AppInfo(
            name=a["name"],
            description=a["description"] or "No description",
            app_type=a["app_type"],
            status=a["status"],
            url=a["app_url"],
            repo_url=a["repo_url"],
            issue_count=a["issue_count"],
        )
        for a in apps
    ]


@app.post("/issue", response_model=IssueResponse)
async def create_issue(req: IssueRequest) -> IssueResponse:
    user = await db.get_user(req.telegram_id)
    if not user or not user["verified"]:
        raise HTTPException(status_code=403, detail="not_registered")

    org = user["gitea_org"]
    try:
        issue_url = await _create_gitea_issue(org, req.repo_name, req.title, req.body)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Gitea error: {e}")

    return IssueResponse(issue_url=issue_url)


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

    await db.soft_delete_app(req.telegram_id, req.repo_name)
    return DeleteAppResponse(success=True)


@app.post("/apps/{app_name}/report-issue", response_model=ReportIssueResponse)
async def report_issue(app_name: str, req: ReportIssueRequest) -> ReportIssueResponse:
    app_record = await db.get_app_by_name(req.telegram_id, app_name)
    if not app_record or app_record["status"] == "deleted":
        return ReportIssueResponse(issue_url=None, notified=False)

    # Dedup check — if we've seen this exact error before, stay silent
    existing = await db.get_app_issue(app_record["id"], req.error_hash)
    if existing is not None:
        log.info("issue.dedup_skip", extra={"app_name": app_name, "error_hash": req.error_hash})
        return ReportIssueResponse(issue_url=existing, notified=False)

    user = await db.get_user(req.telegram_id)
    if not user:
        return ReportIssueResponse(issue_url=None, notified=False)

    try:
        summary = await _summarise(app_name, req.log_excerpt)
    except Exception:
        summary = "Errors were detected but could not be summarised automatically."

    title = summary[:72] + ("…" if len(summary) > 72 else "")
    issue_url: str | None = None
    try:
        issue_url = await _create_gitea_issue(
            user["gitea_org"],
            app_name,
            title,
            f"{summary}\n\n---\n*Detected automatically by the platform monitor.*",
        )
    except httpx.HTTPError:
        pass

    await db.insert_app_issue(app_record["id"], req.error_hash, issue_url, req.is_breaking)

    new_status = "failed" if req.is_breaking else "degraded"
    await db.update_app_status(app_record["id"], new_status)

    notified = False
    try:
        label = "🔴 Breaking issue" if req.is_breaking else "⚠️ Issue"
        text = f"{label} detected in *{app_name}*\n\n{summary}"
        if issue_url:
            text += f"\n\nTracked: {issue_url}"
        await _telegram_notify(req.telegram_id, text)
        notified = True
    except Exception:
        pass

    log.info("issue.reported", extra={"app_name": app_name, "error_hash": req.error_hash, "issue_url": issue_url, "notified": notified})
    return ReportIssueResponse(issue_url=issue_url, notified=notified)


@app.get("/me", response_model=MeResponse)
async def me(telegram_id: int) -> MeResponse:
    user = await db.get_user(telegram_id)
    return MeResponse(registered=bool(user and user["verified"]))


@app.post("/admin/backfill-apps")
async def backfill_apps() -> dict:
    """One-shot: sync Gitea repos into the apps table for all verified users."""
    users = await db.get_all_verified_users()
    inserted = 0
    skipped = 0

    async with httpx.AsyncClient(timeout=15.0) as client:
        for user in users:
            org = user["gitea_org"]
            if not org:
                continue
            resp = await client.get(
                f"{GITEA_URL}/api/v1/orgs/{org}/repos?limit=50",
                auth=_gitea_auth(),
            )
            if resp.status_code != 200:
                continue
            for repo in resp.json():
                name = repo["name"]
                existing = await db.get_app_by_name(user["telegram_id"], name)
                if existing:
                    skipped += 1
                    continue
                app_id = await db.register_app(
                    telegram_id=user["telegram_id"],
                    name=name,
                    description=repo.get("description", ""),
                    app_type="",
                )
                await db.update_app_status(
                    app_id, "active",
                    repo_url=repo["html_url"],
                    app_url=f"http://{name}.{APP_DOMAIN}",
                )
                inserted += 1

    return {"inserted": inserted, "skipped": skipped}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
