---
title: "Component design: Coder agent"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: coder
related:
  - docs/architecture/overview.md
  - docs/architecture/components/orchestrator.md
---

## Purpose

The coder agent scaffolds a complete project from a structured spec, tests it locally, and commits all files to a new Gitea repository. It is invoked by the orchestrator once the designer agent has produced a confirmed spec.

## Responsibilities

**Owns:**
- LLM-based project file generation for all five app types
- Typed fallback templates when LLM output cannot be parsed
- Local test execution before committing (fail-fast gate)
- Gitea repo creation and file commit
- `.woodpecker.yml` CI pipeline generation

**Does not own:**
- Spec clarification (owned by the designer agent)
- pytest generation (owned by the tester agent, runs inside CI)
- Deployment (handled by Woodpecker CI after the commit)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, `POST /build` endpoint, orchestrates the scaffold → test → commit flow |
| `scaffold.py` | LLM-based project generation; JSON mode prompt + output parsing |
| `local_test.py` | Runs generated code locally before commit; returns pass/fail |
| `gitea.py` | Gitea API wrapper: create repo, commit files, set up webhook |
| `templates/form.py` | Hardcoded fallback scaffold for `form` app type |

## Key flows

### Happy path

1. Orchestrator calls `POST /build` with spec `{name, description, app_type, stack, requirements}`
2. `scaffold.py` calls Ollama in JSON mode; LLM returns `{files: [{path, content}]}`
3. `local_test.py` writes files to a temp directory, installs deps, runs `pytest` or a smoke check
4. On pass: `gitea.py` creates repo `app-{name}` in user's Gitea org, commits all files
5. `gitea.py` generates `.woodpecker.yml` and commits it
6. Orchestrator activates the Woodpecker repo (direct Postgres insert + HMAC webhook)
7. Returns `{repo_url, app_url}` to orchestrator

### LLM parse failure (fallback)

1. LLM returns malformed JSON or missing required fields
2. `scaffold.py` catches the parse error, loads the typed fallback template for the app type
3. Fallback files are used for local test and commit; scaffold proceeds normally

### Local test failure

1. `local_test.py` returns a failure
2. Build is aborted; orchestrator sets `apps.status = failed` with error detail
3. No Gitea repo is created

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /build` | Orchestrator | Scaffold and commit a new app |
| `GET /health` | Traefik / orchestrator | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| Ollama HTTP API | LLM-based file generation |
| Gitea HTTP API | Repo creation and file commits |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `OLLAMA_MODEL` | `llama3.1:8b` | Model for code generation (`qwen2.5-coder:32b` recommended when VRAM allows) |
| `OLLAMA_URL` | `http://ollama:11434` | |
| `GITEA_URL` | — | Internal Gitea base URL |
| `GITEA_ADMIN_USER` / `GITEA_ADMIN_PASS` | — | Gitea API credentials |
| `STANDARDS_PATH` | `/standards` | Mount path for YAML standards files injected into the scaffold prompt |

## Known limitations

- Local test execution runs inside the agent container — dependency installation (`pip install`) adds latency and can fail on network issues.
- Fallback templates only exist for `form` type; other app types that fail LLM parsing will surface an error rather than falling back.
- The `.woodpecker.yml` is generated once at build time; changes to the CI template require a new build.
