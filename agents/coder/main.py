from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from gitea import create_repo_with_files
from scaffold import scaffold_project

app = FastAPI(title="Coder Agent")


class BuildRequest(BaseModel):
    name: str
    description: str
    stack: str = "python-fastapi"
    requirements: list[str] = []
    org: str = ""


class BuildResponse(BaseModel):
    repo_url: str


@app.post("/build", response_model=BuildResponse)
async def build(req: BuildRequest) -> BuildResponse:
    try:
        files = await scaffold_project(
            req.name, req.description, req.stack, req.requirements
        )
        repo_url = await create_repo_with_files(
            req.name, req.description, files, req.org
        )
        return BuildResponse(repo_url=repo_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
