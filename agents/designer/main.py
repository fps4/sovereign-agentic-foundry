"""Designer agent.

Holds a multi-turn conversation with the user until the app specification is
unambiguous, then creates the Gitea repo, commits DESIGN.md, and opens a task
issue — ready for the coder agent to pick up.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
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
               repo: str | None = None, task_ref: str | None = None,
               duration_ms: int | None = None, details: dict | None = None) -> None:
    if not run_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{ORCHESTRATOR_URL}/runs/log", json={
                "run_id": run_id, "agent": "designer", "event": event,
                "repo": repo, "task_ref": task_ref, "status": status,
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


log = _setup_logger("designer")
app = FastAPI(title="Designer Agent")


# ── Standards ─────────────────────────────────────────────────────────────────

def _load_agent_standards() -> str:
    sections: list[str] = []
    for subdir in ("", "agents"):
        d = STANDARDS_DIR / subdir if subdir else STANDARDS_DIR
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.yaml")):
            if path.parent.name == "agents" and path.stem != "designer":
                continue
            try:
                data = yaml.safe_load(path.read_text()) or {}
                name = path.stem.replace("_", " ").title()
                sections.append(
                    f"### {name}\n```yaml\n{yaml.dump(data, default_flow_style=False, sort_keys=False).strip()}\n```"
                )
            except Exception:
                pass
    return "\n\n".join(sections)


_STANDARDS = _load_agent_standards()

_SYSTEM_PROMPT = """\
You are the AI assistant for a sovereign agentic platform that builds and
deploys applications on self-hosted infrastructure.

You are the first point of contact for every user message. You handle both
general conversation and app design. When the user wants to build something,
guide them through clarification until you have a complete spec, then produce it.

Rules:
- Respond warmly and naturally to greetings, thanks, and off-topic messages.
- For build requests: ask at most ONE clarifying question per turn.
- Once you know app type, purpose, and at least 3 requirements — produce the spec.
- Default stack to python-fastapi unless the user specifies otherwise.
- App types: form | dashboard | workflow | connector | assistant
- Keep designs simple and minimal — do not over-engineer.
- NEVER produce a spec unless the user has clearly described something to build.

Always respond with ONLY valid JSON — no markdown, no explanation.

Schema when still chatting or clarifying:
{
  "ready": false,
  "reply": "your response to the user"
}

Schema when spec is complete:
{
  "ready": true,
  "reply": "summary of what you are about to build",
  "spec": {
    "name": "kebab-case-app-name",
    "description": "one concise sentence",
    "app_type": "form|dashboard|workflow|connector|assistant",
    "stack": "python-fastapi|node-express|go-gin",
    "requirements": ["requirement 1", "requirement 2", "..."],
    "acceptance_criteria": ["criterion 1", "..."],
    "data_model": [
      {"field": "field_name", "type": "str|int|float|bool|date", "required": true, "label": "Human Label"}
    ]
  }
}
""" + (f"\n\n## Platform standards\n\n{_STANDARDS}" if _STANDARDS else "")


# ── Gitea helpers ─────────────────────────────────────────────────────────────

def _auth() -> tuple[str, str]:
    return (GITEA_ADMIN_USER, GITEA_ADMIN_PASS)


async def _create_repo(name: str, description: str, org: str) -> str:
    url = f"{GITEA_URL}/api/v1/orgs/{org}/repos"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url, auth=_auth(),
            json={"name": name, "description": description, "private": False,
                  "auto_init": False, "default_branch": "main"},
        )
        if resp.status_code not in (201, 409):
            resp.raise_for_status()
    return f"{GITEA_URL}/{org}/{name}"


async def _commit_file(org: str, repo: str, path: str, content: str, message: str) -> None:
    content_b64 = base64.b64encode(content.encode()).decode()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{GITEA_URL}/api/v1/repos/{org}/{repo}/contents/{path}",
            auth=_auth(),
            json={"message": message, "content": content_b64, "branch": "main"},
        )
        if resp.status_code == 422:
            get_resp = await client.get(
                f"{GITEA_URL}/api/v1/repos/{org}/{repo}/contents/{path}",
                auth=_auth(),
            )
            sha = get_resp.json()["sha"]
            await client.put(
                f"{GITEA_URL}/api/v1/repos/{org}/{repo}/contents/{path}",
                auth=_auth(),
                json={"message": message, "content": content_b64, "sha": sha, "branch": "main"},
            )
        else:
            resp.raise_for_status()


async def _create_issue(org: str, repo: str, title: str, body: str) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{GITEA_URL}/api/v1/repos/{org}/{repo}/issues",
            auth=_auth(),
            json={"title": title, "body": body, "labels": []},
        )
        resp.raise_for_status()
        return resp.json()["html_url"]


def _build_design_md(spec: dict, issue_url: str = "") -> str:
    lines = [
        f"# {spec['name']}\n",
        f"{spec['description']}\n",
        f"## App Type\n{spec['app_type']}\n",
        f"## Stack\n{spec['stack']}\n",
        "## Requirements\n" + "\n".join(f"- {r}" for r in spec.get("requirements", [])) + "\n",
    ]
    if spec.get("acceptance_criteria"):
        lines.append(
            "## Acceptance Criteria\n"
            + "\n".join(f"- {c}" for c in spec["acceptance_criteria"]) + "\n"
        )
    if spec.get("data_model"):
        rows = "\n".join(
            f"| `{f['field']}` | {f['type']} | {'yes' if f.get('required') else 'no'} | {f.get('label', f['field'])} |"
            for f in spec["data_model"]
        )
        lines.append(
            "## Data Model\n\n| Field | Type | Required | Label |\n|---|---|---|---|\n" + rows + "\n"
        )
    lines.append(
        f"\n---\n*Generated by Designer Agent — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}*"
    )
    if issue_url:
        lines[-1] += f"\nImplementation task: {issue_url}"
    return "\n".join(lines)


def _build_issue_body(spec: dict) -> str:
    reqs = "\n".join(f"- [ ] {r}" for r in spec.get("requirements", []))
    criteria = "\n".join(f"- [ ] {c}" for c in spec.get("acceptance_criteria", []))
    return (
        f"## Task\n\nImplement **{spec['name']}** per the specification in `DESIGN.md`.\n\n"
        f"## Requirements\n{reqs}\n\n"
        + (f"## Acceptance Criteria\n{criteria}\n\n" if criteria else "")
        + f"**Stack:** {spec['stack']}  \n**App type:** {spec['app_type']}\n"
    )


# ── Models ────────────────────────────────────────────────────────────────────

class DesignRequest(BaseModel):
    user_id: str
    message: str
    history: list[dict] = []
    org: str = ""
    run_id: str = ""


class DesignResponse(BaseModel):
    status: str        # "clarifying" | "ready"
    reply: str
    spec: dict | None = None
    repo_url: str | None = None
    issue_url: str | None = None


# ── Endpoint ──────────────────────────────────────────────────────────────────

@app.post("/design", response_model=DesignResponse)
async def design(req: DesignRequest) -> DesignResponse:
    import time as _time
    _t0 = _time.monotonic()
    log.info("design.request", extra={"user_id": req.user_id, "history_len": len(req.history), "org": req.org, "run_id": req.run_id})
    await _log(req.run_id, "design.started", repo=None,
               details={"user_id": req.user_id, "history_len": len(req.history)})
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, format="json")

    msgs = [SystemMessage(content=_SYSTEM_PROMPT)]
    for turn in req.history[-12:]:
        msgs.append(
            HumanMessage(content=turn["content"])
            if turn["role"] == "user"
            else AIMessage(content=turn["content"])
        )
    msgs.append(HumanMessage(content=req.message))

    result = llm.invoke(msgs)
    try:
        data = json.loads(result.content)
    except (json.JSONDecodeError, AttributeError):
        return DesignResponse(
            status="clarifying",
            reply="Could you tell me a bit more about what you'd like to build?",
        )

    if not data.get("ready"):
        log.info("design.clarifying", extra={"user_id": req.user_id, "reply_preview": data.get("reply", "")[:80]})
        await _log(req.run_id, "design.clarifying",
                   details={"turn": len(req.history) + 1, "reply_preview": data.get("reply", "")[:80]})
        return DesignResponse(
            status="clarifying",
            reply=data.get("reply", "What else can you tell me about what you need?"),
        )

    spec = data.get("spec", {})
    if not spec or not all(k in spec for k in ("name", "description", "app_type", "stack")):
        return DesignResponse(
            status="clarifying",
            reply="I need a bit more detail — what should the app be called and what should it do?",
        )

    log.info("design.spec_ready", extra={"user_id": req.user_id, "app_name": spec["name"], "app_type": spec["app_type"], "stack": spec["stack"]})
    await _log(req.run_id, "design.spec_ready", repo=spec["name"],
               duration_ms=int((_time.monotonic() - _t0) * 1000),
               details={"app_name": spec["name"], "app_type": spec["app_type"],
                        "stack": spec["stack"], "requirements": spec.get("requirements", [])})

    # Create repo, commit DESIGN.md, open issue
    repo_url: str | None = None
    issue_url: str | None = None
    if req.org:
        try:
            repo_url = await _create_repo(spec["name"], spec["description"], req.org)
            log.info("design.repo_created", extra={"org": req.org, "repo": spec["name"], "repo_url": repo_url})
            await _log(req.run_id, "design.repo_created", repo=spec["name"],
                       details={"repo_url": repo_url})
            issue_body = _build_issue_body(spec)
            issue_url = await _create_issue(req.org, spec["name"], f"feat: implement {spec['name']}", issue_body)
            log.info("design.issue_created", extra={"org": req.org, "repo": spec["name"], "issue_url": issue_url})
            await _log(req.run_id, "design.issue_created", repo=spec["name"],
                       task_ref=issue_url, details={"issue_url": issue_url})
            design_md = _build_design_md(spec, issue_url)
            await _commit_file(req.org, spec["name"], "DESIGN.md", design_md, "docs: add design specification")
        except Exception as exc:
            log.error("design.error", extra={"user_id": req.user_id, "error": str(exc)})
            await _log(req.run_id, "design.error", repo=spec.get("name"), status="error",
                       details={"error": str(exc)})
            return DesignResponse(
                status="clarifying",
                reply=f"Something went wrong setting up the repo: {exc}. Please try again.",
            )

    return DesignResponse(
        status="ready",
        reply=data.get("reply", f"Spec ready! Setting up *{spec['name']}* now."),
        spec=spec,
        repo_url=repo_url,
        issue_url=issue_url,
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
