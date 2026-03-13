from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from gitea import create_repo_with_files
from scaffold import scaffold_project

APP_DOMAIN = os.getenv("APP_DOMAIN", "localhost")

app = FastAPI(title="Coder Agent")


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
    try:
        files = await scaffold_project(
            req.name, req.description, req.stack, req.requirements, req.app_type
        )
        repo_url = await create_repo_with_files(
            req.name, req.description, files, req.org
        )
        app_url = f"http://{req.name}.{APP_DOMAIN}"
        return BuildResponse(repo_url=repo_url, app_url=app_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
