"""LLM-based project scaffolding.

Calls the local Ollama model with JSON mode to generate a list of files.
Falls back to a minimal hard-coded scaffold if the model output cannot be
parsed — this keeps the agent working even with smaller models.
"""

from __future__ import annotations

import base64
import json
import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
APP_DOMAIN = os.getenv("APP_DOMAIN", "localhost")

_SCAFFOLD_PROMPT = """\
You are a code scaffolding agent for a sovereign agentic platform.
Generate a minimal but working project given the spec below.

Respond with ONLY a JSON object — no markdown, no explanation, no code fences.

Schema:
{
  "files": [
    {"path": "relative/path/to/file.ext", "content": "full file content"}
  ]
}

Always include:
1. Main application entry point
2. requirements.txt (Python) or package.json (Node)
3. Dockerfile — non-root user, pin to python:3.12-slim or node:20-alpine
4. .woodpecker.yml — see template below
5. README.md — one paragraph description

.woodpecker.yml template:
steps:
  - name: test
    image: python:3.12-slim
    commands:
      - pip install -r requirements.txt
      - python -m pytest -v || echo "no tests"
  - name: docker-build
    image: docker:cli
    commands:
      - docker build -t ${CI_REPO_NAME}:latest .
    when:
      branch: main
  - name: deploy
    image: docker:cli
    commands:
      - docker rm -f ${CI_REPO_NAME} || true
      - docker run -d --name ${CI_REPO_NAME} --restart unless-stopped --network platform_platform --label "traefik.enable=true" --label "traefik.http.routers.${CI_REPO_NAME}.rule=Host(`${CI_REPO_NAME}.%%APP_DOMAIN%%`)" --label "traefik.http.routers.${CI_REPO_NAME}.entrypoints=web" --label "traefik.http.services.${CI_REPO_NAME}.loadbalancer.server.port=8000" --label "platform.owner=${CI_REPO_OWNER}" ${CI_REPO_NAME}:latest
    when:
      branch: main

Adjust the test step image and commands to match the stack.
"""


async def scaffold_project(
    name: str, description: str, stack: str, requirements: list[str], app_type: str = ""
) -> list[dict]:
    """Return a list of {path, content} dicts for the scaffolded project."""
    if app_type == "form":
        from templates.form import scaffold_form
        return await scaffold_form(name, description, requirements)
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, format="json")
    user_prompt = (
        f"name: {name}\n"
        f"description: {description}\n"
        f"stack: {stack}\n"
        f"requirements: {', '.join(requirements) if requirements else 'none'}"
    )
    result = await llm.ainvoke(
        [SystemMessage(content=_SCAFFOLD_PROMPT), HumanMessage(content=user_prompt)]
    )
    try:
        data = json.loads(result.content)
        files = data.get("files", [])
        if files and all("path" in f and "content" in f for f in files):
            return _inject_domain(files)
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    return _minimal_scaffold(name, description, stack)


def _inject_domain(files: list[dict]) -> list[dict]:
    """Replace %%APP_DOMAIN%% placeholder with the actual APP_DOMAIN value."""
    return [
        {**f, "content": f["content"].replace("%%APP_DOMAIN%%", APP_DOMAIN)}
        for f in files
    ]


def _woodpecker_yml(name: str, image: str, test_cmd: str) -> str:
    # Encode the test-generator script as base64 to avoid YAML indentation issues
    gen_script = (
        "import httpx, json, os\n"
        "from pathlib import Path\n"
        "r = httpx.post(os.environ['TESTER_URL'] + '/generate-tests',\n"
        "               json={'repo': os.environ['CI_REPO_NAME'], 'org': os.environ['CI_REPO_OWNER']},\n"
        "               timeout=httpx.Timeout(connect=10, read=900, write=10, pool=10))\n"
        "r.raise_for_status()\n"
        "for f in r.json()['files']:\n"
        "    p = Path(f['path']); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(f['content'])\n"
        "print(r.json()['summary'])\n"
    )
    gen_b64 = base64.b64encode(gen_script.encode()).decode()
    return (
        "steps:\n"
        "  - name: generate-tests\n"
        "    image: python:3.12-slim\n"
        "    environment:\n"
        "      TESTER_URL: http://tester:8002\n"
        "      CI_REPO_NAME: ${CI_REPO_NAME}\n"
        "      CI_REPO_OWNER: ${CI_REPO_OWNER}\n"
        "    commands:\n"
        "      - pip install httpx --quiet\n"
        f"      - echo {gen_b64} | base64 -d | python3\n"
        "  - name: test\n"
        f"    image: {image}\n"
        "    commands:\n"
        "      - pip install -r requirements.txt pytest httpx --quiet\n"
        "      - python -m pytest tests/ -v\n"
        "  - name: docker-build\n"
        "    image: docker:cli\n"
        "    commands:\n"
        f"      - docker build -t {name}:latest .\n"
        "    when:\n"
        "      branch: main\n"
        "  - name: deploy\n"
        "    image: docker:cli\n"
        "    commands:\n"
        f"      - docker rm -f {name} || true\n"
        f"      - docker run -d --name {name} --restart unless-stopped"
        f" --network platform_platform"
        f' --label "traefik.enable=true"'
        f' --label "traefik.http.routers.{name}.rule=Host(\\`{name}.{APP_DOMAIN}\\`)"'
        f' --label "traefik.http.routers.{name}.entrypoints=web"'
        f' --label "traefik.http.services.{name}.loadbalancer.server.port=8000"'
        f' --label "platform.owner=${{CI_REPO_OWNER}}"'
        f" {name}:latest\n"
        "    when:\n"
        "      branch: main\n"
    )


def _minimal_scaffold(name: str, description: str, stack: str) -> list[dict]:
    s = stack.lower()

    if "node" in s or "express" in s:
        return [
            {
                "path": "index.js",
                "content": (
                    f"// {description}\n"
                    'const express = require("express");\n'
                    "const app = express();\n"
                    'app.use(express.json());\n'
                    'app.get("/health", (_req, res) => res.json({ status: "ok" }));\n'
                    'app.listen(3000, () => console.log("Listening on :3000"));\n'
                ),
            },
            {
                "path": "package.json",
                "content": json.dumps(
                    {
                        "name": name,
                        "version": "0.1.0",
                        "main": "index.js",
                        "scripts": {"start": "node index.js"},
                        "dependencies": {"express": "^4.18.0"},
                    },
                    indent=2,
                )
                + "\n",
            },
            {
                "path": "Dockerfile",
                "content": (
                    "FROM node:20-alpine\n"
                    "WORKDIR /app\n"
                    "COPY package*.json ./\n"
                    "RUN npm ci --omit=dev\n"
                    "COPY . .\n"
                    "RUN addgroup -S app && adduser -S app -G app\n"
                    "USER app\n"
                    "EXPOSE 3000\n"
                    'CMD ["node", "index.js"]\n'
                ),
            },
            {
                "path": ".woodpecker.yml",
                "content": _woodpecker_yml(name, "node:20-alpine", "node index.js --help || true"),
            },
            {"path": "README.md", "content": f"# {name}\n\n{description}\n"},
        ]

    # Default: Python / FastAPI
    return [
        {
            "path": "main.py",
            "content": (
                f'"""{description}"""\n'
                "from fastapi import FastAPI\n\n"
                f'app = FastAPI(title="{name}")\n\n\n'
                '@app.get("/health")\n'
                "def health() -> dict:\n"
                '    return {"status": "ok"}\n'
            ),
        },
        {
            "path": "requirements.txt",
            "content": "fastapi>=0.115\nuvicorn[standard]>=0.30\n",
        },
        {
            "path": "Dockerfile",
            "content": (
                "FROM python:3.12-slim\n"
                "WORKDIR /app\n"
                "COPY requirements.txt .\n"
                "RUN pip install --no-cache-dir -r requirements.txt\n"
                "COPY . .\n"
                "RUN useradd -r appuser && chown -R appuser /app\n"
                "USER appuser\n"
                "EXPOSE 8000\n"
                'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]\n'
            ),
        },
        {
            "path": ".woodpecker.yml",
            "content": _woodpecker_yml(
                name,
                "python:3.12-slim",
                "pip install -r requirements.txt && python -m pytest -v || echo 'no tests'",
            ),
        },
        {"path": "README.md", "content": f"# {name}\n\n{description}\n"},
    ]
