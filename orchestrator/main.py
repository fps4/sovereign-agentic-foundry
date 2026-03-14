from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pythonjsonlogger.jsonlogger import JsonFormatter

import db
from workflow import run_build


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
DESIGNER_URL = os.getenv("DESIGNER_URL", "http://designer:8003")

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


class RunLogRequest(BaseModel):
    run_id: str
    agent: str
    event: str
    repo: str | None = None
    task_ref: str | None = None
    telegram_id: int | None = None
    status: str = "ok"
    duration_ms: int | None = None
    details: dict | None = None


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
        run_id = str(uuid4())
        history = await db.get_history(req.user_id)
        return await _handle_design(req, user, org, run_id, history)
    except Exception as e:
        log.error("chat.error", extra={"user_id": req.user_id, "error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


async def _handle_design(
    req: ChatRequest,
    user: dict,
    org: str,
    run_id: str,
    history: list,
) -> ChatResponse:
    """Route every message through the designer agent — the single front door."""
    log.info("chat.request", extra={"user_id": req.user_id, "run_id": run_id, "message_preview": req.message[:60]})
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{DESIGNER_URL}/design",
                json={
                    "user_id": req.user_id,
                    "message": req.message,
                    "history": history,
                    "org": org,
                    "run_id": run_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        log.error("chat.designer_error", extra={"user_id": req.user_id, "error": str(exc)})
        return ChatResponse(
            reply="Something went wrong on our end. Please try again in a moment."
        )

    await db.append_message(req.user_id, "user", req.message)
    await db.append_message(req.user_id, "assistant", data["reply"])

    if data["status"] == "clarifying":
        log.info("chat.clarifying", extra={"user_id": req.user_id, "run_id": run_id})
        return ChatResponse(reply=data["reply"])

    # Designer produced a complete spec — kick off the build
    spec = data.get("spec", {})
    if not spec:
        return ChatResponse(reply=data["reply"])

    existing = await db.get_app_by_name(int(req.user_id), spec["name"])
    if existing and existing["status"] in ("queued", "provisioning"):
        log.info("build.duplicate_skip", extra={"user_id": req.user_id, "app_name": spec["name"]})
        return ChatResponse(
            reply=(
                f"*{spec['name']}* is already being built — I'll message you when it's ready. "
                "Use /apps to check the current status."
            )
        )

    app_id = await db.register_app(
        telegram_id=int(req.user_id),
        name=spec["name"],
        description=spec.get("description", ""),
        app_type=spec.get("app_type", ""),
    )
    log.info("build.queued", extra={"user_id": req.user_id, "app_id": app_id, "app_name": spec["name"], "run_id": run_id})
    await db.log_run_step(
        run_id=run_id, agent="orchestrator", event="pipeline.started",
        repo=spec["name"], telegram_id=int(req.user_id),
        details={"message_preview": req.message[:120]},
    )
    asyncio.create_task(
        run_build(
            spec=spec,
            org=org,
            telegram_id=int(req.user_id),
            bot_token=TELEGRAM_BOT_TOKEN,
            app_id=app_id,
            run_id=run_id,
        )
    )
    return ChatResponse(reply=data["reply"])


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


async def _stop_app_container(name: str) -> None:
    """Stop and remove the running app container via the Docker socket."""
    try:
        transport = httpx.AsyncHTTPTransport(uds="/var/run/docker.sock")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://docker", timeout=15.0
        ) as client:
            await client.delete(f"/v1.44/containers/{name}", params={"force": "true"})
    except Exception as exc:
        log.warning("delete.container_stop_failed", extra={"app_name": name, "error": str(exc)})


@app.post("/delete-app", response_model=DeleteAppResponse)
async def delete_app(req: DeleteAppRequest) -> DeleteAppResponse:
    user = await db.get_user(req.telegram_id)
    if not user or not user["verified"]:
        raise HTTPException(status_code=403, detail="not_registered")

    app_record = await db.get_app_by_name(req.telegram_id, req.repo_name)
    if not app_record or app_record["status"] == "deleted":
        raise HTTPException(status_code=404, detail="app_not_found")

    # Stop the running container (best-effort — may already be stopped)
    await _stop_app_container(req.repo_name)

    await db.soft_delete_app(req.telegram_id, req.repo_name)
    log.info("app.deleted", extra={"telegram_id": req.telegram_id, "app_name": req.repo_name})
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


# ── Agent run log ─────────────────────────────────────────────────────────────

@app.post("/runs/log", status_code=204)
async def log_run(req: RunLogRequest) -> None:
    await db.log_run_step(
        run_id=req.run_id,
        agent=req.agent,
        event=req.event,
        repo=req.repo,
        task_ref=req.task_ref,
        telegram_id=req.telegram_id,
        status=req.status,
        duration_ms=req.duration_ms,
        details=req.details,
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


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
