"""LLM-based project scaffolding.

Calls the local Ollama model with JSON mode to generate a list of files.
Falls back to a minimal hard-coded scaffold if the model output cannot be
parsed — this keeps the agent working even with smaller models.
"""

from __future__ import annotations

import json
import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

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
    image: plugins/docker
    settings:
      repo: registry.local/${CI_REPO_NAME}
      tags: latest,${CI_COMMIT_SHA:0:8}
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
            return files
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    return _minimal_scaffold(name, description, stack)


def _woodpecker_yml(name: str, image: str, test_cmd: str) -> str:
    return (
        "steps:\n"
        "  - name: test\n"
        f"    image: {image}\n"
        "    commands:\n"
        f"      - {test_cmd}\n"
        "  - name: docker-build\n"
        "    image: plugins/docker\n"
        "    settings:\n"
        f"      repo: registry.local/{name}\n"
        "      tags: latest,${{CI_COMMIT_SHA:0:8}}\n"
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
                "RUN useradd -r appuser\n"
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
