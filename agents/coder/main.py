from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pythonjsonlogger.jsonlogger import JsonFormatter

from gitea import create_repo_with_files
from scaffold import scaffold_project

APP_DOMAIN = os.getenv("APP_DOMAIN", "localhost")


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


class BuildResponse(BaseModel):
    repo_url: str
    app_url: str


@app.post("/build", response_model=BuildResponse)
async def build(req: BuildRequest) -> BuildResponse:
    log.info("build.started", extra={"app_name": req.name, "stack": req.stack, "app_type": req.app_type, "org": req.org})
    try:
        files = await scaffold_project(
            req.name, req.description, req.stack, req.requirements, req.app_type
        )
        log.info("build.scaffolded", extra={"app_name": req.name, "file_count": len(files)})
        repo_url = await create_repo_with_files(
            req.name, req.description, files, req.org
        )
        app_url = f"http://{req.name}.{APP_DOMAIN}"
        log.info("build.completed", extra={"app_name": req.name, "repo_url": repo_url, "app_url": app_url})
        return BuildResponse(repo_url=repo_url, app_url=app_url)
    except Exception as e:
        log.error("build.failed", extra={"app_name": req.name, "error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
