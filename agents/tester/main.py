"""Tester agent.

Called from a Woodpecker CI pipeline step. Fetches source files from Gitea,
generates a test suite using the LLM, commits the test files back to the repo,
and returns the generated file list for the CI step to run with pytest.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

import httpx
import logging
import yaml
from fastapi import FastAPI, HTTPException
from pythonjsonlogger.jsonlogger import JsonFormatter
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel
from pythonjsonlogger.jsonlogger import JsonFormatter

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
GITEA_URL = os.getenv("GITEA_URL", "http://gitea:3000")
GITEA_ADMIN_USER = os.getenv("GITEA_ADMIN_USER", "platform")
GITEA_ADMIN_PASS = os.getenv("GITEA_ADMIN_PASS", "")
STANDARDS_DIR = Path(os.getenv("STANDARDS_DIR", "/app/standards"))
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8000")


async def _log(run_id: str, event: str, status: str = "ok",
               repo: str | None = None, duration_ms: int | None = None,
               details: dict | None = None) -> None:
    if not run_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{ORCHESTRATOR_URL}/runs/log", json={
                "run_id": run_id, "agent": "tester", "event": event,
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


log = _setup_logger("tester")
def _setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


log = _setup_logger("tester")

app = FastAPI(title="Tester Agent")


# ── Standards ─────────────────────────────────────────────────────────────────

def _load_tester_standards() -> str:
    path = STANDARDS_DIR / "agents" / "tester.yaml"
    if not path.exists():
        return ""
    try:
        data = yaml.safe_load(path.read_text()) or {}
        return yaml.dump(data, default_flow_style=False, sort_keys=False).strip()
    except Exception:
        return ""


_STANDARDS = _load_tester_standards()

_SYSTEM_PROMPT = """\
You are a test generation agent. Given application source files, generate a
comprehensive pytest test suite.

Rules:
- Cover every API endpoint: happy path, invalid input, and not-found cases
- Mock all databases and external services using pytest fixtures or monkeypatching
- Use the FastAPI TestClient for HTTP endpoint tests
- Generate at least 3 meaningful test functions per endpoint
- Tests must be runnable with: pip install pytest httpx fastapi && pytest tests/

Respond with ONLY valid JSON — no markdown, no explanation.

Schema:
{
  "files": [
    {"path": "tests/test_main.py", "content": "full file content"}
  ]
}
""" + (f"\n\n## Tester standards\n```yaml\n{_STANDARDS}\n```" if _STANDARDS else "")


# ── Gitea helpers ─────────────────────────────────────────────────────────────

def _auth() -> tuple[str, str]:
    return (GITEA_ADMIN_USER, GITEA_ADMIN_PASS)


async def _fetch_source_files(org: str, repo: str) -> list[dict]:
    """Fetch all Python source files from the repo root (non-recursive for speed)."""
    files: list[dict] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{GITEA_URL}/api/v1/repos/{org}/{repo}/contents/",
            auth=_auth(),
        )
        if resp.status_code != 200:
            return files
        for item in resp.json():
            if item["type"] != "file":
                continue
            if not item["name"].endswith((".py", ".js", ".ts")):
                continue
            if item["name"].startswith("test_") or item["name"].endswith(".test.js"):
                continue
            file_resp = await client.get(item["download_url"])
            if file_resp.status_code == 200:
                files.append({"path": item["path"], "content": file_resp.text})
    return files


async def _commit_file(org: str, repo: str, path: str, content: str) -> None:
    content_b64 = base64.b64encode(content.encode()).decode()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{GITEA_URL}/api/v1/repos/{org}/{repo}/contents/{path}",
            auth=_auth(),
            json={"message": "test: add generated test suite", "content": content_b64, "branch": "main"},
        )
        if resp.status_code == 422:
            get_resp = await client.get(
                f"{GITEA_URL}/api/v1/repos/{org}/{repo}/contents/{path}", auth=_auth()
            )
            sha = get_resp.json()["sha"]
            await client.put(
                f"{GITEA_URL}/api/v1/repos/{org}/{repo}/contents/{path}",
                auth=_auth(),
                json={"message": "test: update generated test suite", "content": content_b64,
                      "sha": sha, "branch": "main"},
            )
        else:
            resp.raise_for_status()


def _minimal_tests(repo: str) -> list[dict]:
    return [{
        "path": "tests/test_health.py",
        "content": (
            "from fastapi.testclient import TestClient\n"
            "from main import app\n\n"
            "client = TestClient(app)\n\n\n"
            "def test_health():\n"
            '    resp = client.get("/health")\n'
            "    assert resp.status_code == 200\n"
            '    assert resp.json()["status"] == "ok"\n'
        ),
    }]


# ── Models ────────────────────────────────────────────────────────────────────

class GenerateTestsRequest(BaseModel):
    repo: str
    org: str
    branch: str = "main"
    run_id: str = ""  # optional — CI step may pass one


class GenerateTestsResponse(BaseModel):
    files: list[dict]
    summary: str


# ── Endpoint ──────────────────────────────────────────────────────────────────

@app.post("/generate-tests", response_model=GenerateTestsResponse)
async def generate_tests(req: GenerateTestsRequest) -> GenerateTestsResponse:
    import time as _time
    from uuid import uuid4 as _uuid4
    _t0 = _time.monotonic()
    run_id = req.run_id or f"tester-{str(_uuid4())[:8]}"
    log.info("tests.request", extra={"repo": req.repo, "org": req.org, "run_id": run_id})
    await _log(run_id, "tests.started", repo=req.repo, details={"org": req.org})
    source_files = await _fetch_source_files(req.org, req.repo)
    if not source_files:
        log.warning("tests.no_source_files", extra={"repo": req.repo, "org": req.org})
        await _log(run_id, "tests.no_source_files", repo=req.repo, status="error")
        raise HTTPException(status_code=422, detail="No source files found in repo")
    log.info("tests.files_fetched", extra={"repo": req.repo, "count": len(source_files), "run_id": run_id})
    await _log(run_id, "tests.files_fetched", repo=req.repo, details={"count": len(source_files)})
    source_block = "\n\n".join(
        f"# File: {f['path']}\n{f['content']}" for f in source_files
    )

    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, format="json")
    result = await llm.ainvoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"Repository: {req.repo}\n\nSource files:\n\n{source_block[:6000]}"),
    ])

    test_files: list[dict] = []
    try:
        data = json.loads(result.content)
        test_files = data.get("files", [])
        if not (test_files and all("path" in f and "content" in f for f in test_files)):
            log.warning("tests.fallback_minimal", extra={"repo": req.repo, "reason": "invalid_llm_output"})
            await _log(run_id, "tests.fallback_minimal", repo=req.repo, details={"reason": "invalid_llm_output"})
            test_files = _minimal_tests(req.repo)
    except (json.JSONDecodeError, AttributeError, TypeError):
        log.warning("tests.fallback_minimal", extra={"repo": req.repo, "reason": "json_parse_error"})
        await _log(run_id, "tests.fallback_minimal", repo=req.repo, details={"reason": "json_parse_error"})
        test_files = _minimal_tests(req.repo)

    log.info("tests.generated", extra={"repo": req.repo, "file_count": len(test_files), "files": [f["path"] for f in test_files], "run_id": run_id})

    # Ensure tests/__init__.py exists
    paths = {f["path"] for f in test_files}
    if not any(p.startswith("tests/") and p.endswith("__init__.py") for p in paths):
        test_files.append({"path": "tests/__init__.py", "content": ""})

    # Commit test files back to repo
    for f in test_files:
        try:
            await _commit_file(req.org, req.repo, f["path"], f["content"])
        except Exception:
            pass

    duration_ms = int((_time.monotonic() - _t0) * 1000)
    test_paths = [f["path"] for f in test_files]
    log.info("tests.committed", extra={"repo": req.repo, "files": test_paths, "run_id": run_id})
    await _log(run_id, "tests.committed", repo=req.repo, status="ok",
               duration_ms=duration_ms, details={"files": test_paths})
    return GenerateTestsResponse(
        files=test_files,
        summary=f"{len([f for f in test_files if f['path'].endswith('.py') and not f['path'].endswith('__init__.py')])} test file(s) generated for {req.repo}",
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
