"""Form app template.

Generates a FastAPI + SQLAlchemy CRUD service.
The LLM extracts the form fields from the description; the rest of the
scaffold is deterministic so small models only need to produce a short
JSON list, not entire file contents.
"""

from __future__ import annotations

import json
import os
import re

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

_FIELDS_PROMPT = """\
Extract the form fields from the description below. Output ONLY valid JSON, nothing else.

Schema:
{{"fields": [{{"name": "snake_case", "type": "str|int|float|bool", "required": true|false, "label": "Human Label"}}]}}

Rules:
- Always return at least 3 meaningful fields
- Infer sensible fields if none are specified
- "name" must be snake_case

Description: {description}
Requirements: {requirements}
"""

_SA_TYPES = {"str": "String(255)", "int": "Integer", "float": "Float", "bool": "Boolean"}
_PY_TYPES = {"str": "str", "int": "int", "float": "float", "bool": "bool"}


def _pascal(s: str) -> str:
    return "".join(w.title() for w in re.split(r"[-_\s]+", s))


def _snake(s: str) -> str:
    return re.sub(r"[-\s]+", "_", s).lower()


async def scaffold_form(name: str, description: str, requirements: list[str]) -> list[dict]:
    fields = await _extract_fields(description, requirements)
    return _build_files(name, description, fields)


async def _extract_fields(description: str, requirements: list[str]) -> list[dict]:
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, format="json")
    prompt = _FIELDS_PROMPT.format(
        description=description,
        requirements=", ".join(requirements) if requirements else "none",
    )
    result = await llm.ainvoke([HumanMessage(content=prompt)])
    try:
        data = json.loads(result.content)
        fields = data.get("fields", [])
        if isinstance(fields, list) and fields:
            return fields
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return [
        {"name": "title", "type": "str", "required": True, "label": "Title"},
        {"name": "notes", "type": "str", "required": False, "label": "Notes"},
        {"name": "status", "type": "str", "required": True, "label": "Status"},
    ]


def _build_files(name: str, description: str, fields: list[dict]) -> list[dict]:
    model = _pascal(name)
    table = _snake(name) + "s"

    col_lines = "\n".join(
        f"    {f['name']} = Column("
        f"{_SA_TYPES.get(f['type'], 'String(255)')}, "
        f"nullable={not f.get('required', True)})"
        for f in fields
    )

    base_fields = "\n".join(
        f"    {f['name']}: {_PY_TYPES.get(f['type'], 'str')}"
        + ("" if f.get("required") else " = None")
        for f in fields
    )

    update_fields = "\n".join(
        f"    {f['name']}: Optional[{_PY_TYPES.get(f['type'], 'str')}] = None"
        for f in fields
    )

    field_docs = "\n".join(
        f"| `{f['name']}` | {f.get('label', f['name'])} | "
        f"{'required' if f.get('required') else 'optional'} |"
        for f in fields
    )

    return [
        {"path": "main.py",         "content": _main_py(name, model)},
        {"path": "models.py",       "content": _models_py(model, table, col_lines)},
        {"path": "schemas.py",      "content": _schemas_py(model, base_fields, update_fields)},
        {"path": "database.py",     "content": _database_py()},
        {"path": "requirements.txt","content": _requirements()},
        {"path": "Dockerfile",      "content": _dockerfile()},
        {"path": ".woodpecker.yml", "content": _woodpecker(name)},
        {"path": "README.md",       "content": _readme(name, description, field_docs)},
    ]


# ── File generators ────────────────────────────────────────────────────────────

def _main_py(name: str, model: str) -> str:
    return (
        f'"""{name}"""\n'
        "from contextlib import asynccontextmanager\n"
        "from fastapi import Depends, FastAPI, HTTPException\n"
        "from sqlalchemy.orm import Session\n"
        "import models\n"
        "import schemas\n"
        "from database import engine, get_db\n"
        "\n\n"
        "@asynccontextmanager\n"
        "async def lifespan(app: FastAPI):\n"
        "    models.Base.metadata.create_all(bind=engine)\n"
        "    yield\n"
        "\n\n"
        f'app = FastAPI(title="{name}", lifespan=lifespan)\n'
        "\n\n"
        "@app.get(\"/health\")\n"
        "def health() -> dict:\n"
        '    return {"status": "ok"}\n'
        "\n\n"
        f"@app.post(\"/records\", response_model=schemas.{model}Response, status_code=201)\n"
        f"def create(item: schemas.{model}Create, db: Session = Depends(get_db)):\n"
        f"    db_item = models.{model}(**item.model_dump())\n"
        "    db.add(db_item)\n"
        "    db.commit()\n"
        "    db.refresh(db_item)\n"
        "    return db_item\n"
        "\n\n"
        f"@app.get(\"/records\", response_model=list[schemas.{model}Response])\n"
        "def list_records(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):\n"
        f"    return db.query(models.{model}).offset(skip).limit(limit).all()\n"
        "\n\n"
        f"@app.get(\"/records/" + "{record_id}" + f"\", response_model=schemas.{model}Response)\n"
        "def get_record(record_id: int, db: Session = Depends(get_db)):\n"
        f"    item = db.query(models.{model}).filter(models.{model}.id == record_id).first()\n"
        "    if not item:\n"
        "        raise HTTPException(status_code=404, detail=\"Not found\")\n"
        "    return item\n"
        "\n\n"
        f"@app.put(\"/records/" + "{record_id}" + f"\", response_model=schemas.{model}Response)\n"
        f"def update_record(record_id: int, update: schemas.{model}Update, db: Session = Depends(get_db)):\n"
        f"    item = db.query(models.{model}).filter(models.{model}.id == record_id).first()\n"
        "    if not item:\n"
        "        raise HTTPException(status_code=404, detail=\"Not found\")\n"
        "    for k, v in update.model_dump(exclude_unset=True).items():\n"
        "        setattr(item, k, v)\n"
        "    db.commit()\n"
        "    db.refresh(item)\n"
        "    return item\n"
        "\n\n"
        "@app.delete(\"/records/" + "{record_id}" + "\", status_code=204)\n"
        "def delete_record(record_id: int, db: Session = Depends(get_db)):\n"
        f"    item = db.query(models.{model}).filter(models.{model}.id == record_id).first()\n"
        "    if not item:\n"
        "        raise HTTPException(status_code=404, detail=\"Not found\")\n"
        "    db.delete(item)\n"
        "    db.commit()\n"
    )


def _models_py(model: str, table: str, col_lines: str) -> str:
    return (
        "from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String\n"
        "from sqlalchemy.sql import func\n"
        "from database import Base\n"
        "\n\n"
        f"class {model}(Base):\n"
        f'    __tablename__ = "{table}"\n'
        "    id = Column(Integer, primary_key=True, index=True)\n"
        f"{col_lines}\n"
        "    created_at = Column(DateTime(timezone=True), server_default=func.now())\n"
        "    updated_at = Column(DateTime(timezone=True), onupdate=func.now())\n"
    )


def _schemas_py(model: str, base_fields: str, update_fields: str) -> str:
    return (
        "from datetime import datetime\n"
        "from typing import Optional\n"
        "from pydantic import BaseModel\n"
        "\n\n"
        f"class {model}Base(BaseModel):\n"
        f"{base_fields}\n"
        "\n\n"
        f"class {model}Create({model}Base):\n"
        "    pass\n"
        "\n\n"
        f"class {model}Update(BaseModel):\n"
        f"{update_fields}\n"
        "\n\n"
        f"class {model}Response({model}Base):\n"
        "    id: int\n"
        "    created_at: datetime\n"
        '    model_config = {"from_attributes": True}\n'
    )


def _database_py() -> str:
    return (
        "import os\n"
        "from sqlalchemy import create_engine\n"
        "from sqlalchemy.orm import DeclarativeBase, sessionmaker\n"
        "\n"
        'DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")\n'
        "\n"
        'if "sqlite" in DATABASE_URL:\n'
        '    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})\n'
        "else:\n"
        "    engine = create_engine(DATABASE_URL)\n"
        "\n"
        "SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\n"
        "\n\n"
        "class Base(DeclarativeBase):\n"
        "    pass\n"
        "\n\n"
        "def get_db():\n"
        "    db = SessionLocal()\n"
        "    try:\n"
        "        yield db\n"
        "    finally:\n"
        "        db.close()\n"
    )


def _requirements() -> str:
    return (
        "fastapi>=0.115\n"
        "uvicorn[standard]>=0.30\n"
        "sqlalchemy>=2.0\n"
        "pydantic>=2.9\n"
    )


def _dockerfile() -> str:
    return (
        "FROM python:3.12-slim\n"
        "WORKDIR /app\n"
        "COPY requirements.txt .\n"
        "RUN pip install --no-cache-dir -r requirements.txt\n"
        "COPY . .\n"
        "RUN useradd -r appuser\n"
        "USER appuser\n"
        "EXPOSE 8000\n"
        'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]\n'
    )


def _woodpecker(name: str) -> str:
    return (
        "steps:\n"
        "  - name: test\n"
        "    image: python:3.12-slim\n"
        "    commands:\n"
        "      - pip install -r requirements.txt\n"
        "      - python -m pytest -v || echo 'no tests'\n"
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
        f" --network platform"
        f' --label "traefik.enable=true"'
        f' --label "traefik.http.routers.{name}.rule=Host(\\`{name}.${{APP_DOMAIN:-localhost}}\\`)"'
        f' --label "traefik.http.routers.{name}.entrypoints=web"'
        f' --label "traefik.http.services.{name}.loadbalancer.server.port=8000"'
        f' --label "platform.owner=${{CI_REPO_OWNER}}"'
        f" {name}:latest\n"
        "    when:\n"
        "      branch: main\n"
    )


def _readme(name: str, description: str, field_docs: str) -> str:
    return (
        f"# {name}\n\n"
        f"{description}\n\n"
        "## Fields\n\n"
        "| Field | Label | Required |\n"
        "|---|---|---|\n"
        f"{field_docs}\n\n"
        "## API\n\n"
        "| Method | Path | Description |\n"
        "|---|---|---|\n"
        "| POST | `/records` | Create a record |\n"
        "| GET | `/records` | List all records |\n"
        "| GET | `/records/{id}` | Get one record |\n"
        "| PUT | `/records/{id}` | Update a record |\n"
        "| DELETE | `/records/{id}` | Delete a record |\n"
        "| GET | `/health` | Health check |\n\n"
        "## Environment variables\n\n"
        "| Variable | Default | Description |\n"
        "|---|---|---|\n"
        "| `DATABASE_URL` | `sqlite:///./app.db` | SQLAlchemy connection string |\n"
    )
