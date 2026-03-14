from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pythonjsonlogger.jsonlogger import JsonFormatter

from gitea import create_repo_with_files
from scaffold import scaffold_project

APP_DOMAIN = os.getenv("APP_DOMAIN", "localhost")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8000")


async def _log(run_id: str, event: str, status: str = "ok",
               repo: str | None = None, duration_ms: int | None = None,
               details: dict | None = None) -> None:
    if not run_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{ORCHESTRATOR_URL}/runs/log", json={
                "run_id": run_id, "agent": "coder", "event": event,
                "repo": repo, "status": status,
                "duration_ms": duration_ms, "details": details or {},
            })
    except Exception:
        pass


def _setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


log = _setup_logger("coder")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup")
    yield


app = FastAPI(title="Coder Agent", lifespan=lifespan)


class BuildRequest(BaseModel):
    name: str
    description: str
    stack: str = "python-fastapi"
    requirements: list[str] = []
    org: str = ""
    app_type: str = ""
    run_id: str = ""


class BuildResponse(BaseModel):
    repo_url: str
    app_url: str


@app.post("/build", response_model=BuildResponse)
async def build(req: BuildRequest) -> BuildResponse:
    import time as _time
    _t0 = _time.monotonic()
    log.info("build.started", extra={"app_name": req.name, "stack": req.stack, "app_type": req.app_type, "org": req.org, "run_id": req.run_id})
    await _log(req.run_id, "build.started", repo=req.name,
               details={"stack": req.stack, "app_type": req.app_type, "requirements": req.requirements})
    try:
        files = await scaffold_project(
            req.name, req.description, req.stack, req.requirements, req.app_type
        )
        log.info("build.scaffolded", extra={"app_name": req.name, "file_count": len(files), "run_id": req.run_id})
        await _log(req.run_id, "build.scaffolded", repo=req.name, details={"file_count": len(files)})
        repo_url = await create_repo_with_files(
            req.name, req.description, files, req.org
        )
        app_url = f"http://{req.name}.{APP_DOMAIN}"
        duration_ms = int((_time.monotonic() - _t0) * 1000)
        log.info("build.completed", extra={"app_name": req.name, "repo_url": repo_url, "app_url": app_url, "run_id": req.run_id})
        await _log(req.run_id, "build.completed", repo=req.name, status="ok",
                   duration_ms=duration_ms, details={"repo_url": repo_url, "app_url": app_url})
        return BuildResponse(repo_url=repo_url, app_url=app_url)
    except Exception as e:
        duration_ms = int((_time.monotonic() - _t0) * 1000)
        log.error("build.failed", extra={"app_name": req.name, "error": str(e), "run_id": req.run_id})
        await _log(req.run_id, "build.failed", repo=req.name, status="error",
                   duration_ms=duration_ms, details={"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
