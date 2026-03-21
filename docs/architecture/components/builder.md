---
title: "Component design: Builder agent"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: builder
related:
  - docs/architecture/overview.md
  - docs/architecture/components/planner.md
  - docs/architecture/components/reviewer.md
  - docs/architecture/components/ui-designer.md
  - docs/architecture/components/template-library.md
  - docs/architecture/decisions/0005-template-library.md
---

## Purpose

The builder agent generates application code files from a build plan produced by the planner. It makes no architectural decisions — those are fully resolved in the build plan. Its output is a set of files passed to the ui-designer and reviewer before any commit to Gitea.

## Responsibilities

**Owns:**
- Template loading: reads the API template selected by the planner from `/templates/api/`
- LLM-based augmentation of the template with app-specific routes, models, and business logic
- Applying fix instructions from the reviewer on retry (bounded)
- Returning a route manifest alongside generated files for the ui-designer
- Generating `README.md` and optional `docs/` files co-located with the application code

**Does not own:**
- Architectural decisions (owned by the planner agent)
- Frontend template generation (owned by the ui-designer agent)
- Standards compliance review (owned by the reviewer agent)
- Git operations and CI config (owned by the publisher)
- Infrastructure provisioning (owned by the infra agent)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, `POST /build` endpoint |
| `template_loader.py` | Reads the base template from `/templates/api/{template_id}/`; exposes template file set |
| `generate.py` | LLM-based augmentation; sends template files + spec + build plan; merges LLM additions into template |
| `docs.py` | Generates `README.md` and optional `docs/` files from the spec, route manifest, and build plan |

## Key flows

### Happy path

1. Gateway calls `POST /build` with `{spec, build_plan}` (build plan includes `template`, `template_version`, `frontend`, `db`)
2. `template_loader.py` reads base files from `/templates/api/{build_plan.template}/`
3. `generate.py` sends template files + spec + build plan to Ollama: *"These template files implement the platform contract. Add app-specific routes, models, and business logic only."*
4. LLM returns `{files: [{path, content}]}` — only additions and modifications; protected files are excluded from LLM output
5. Builder merges LLM output into the template file set; template-provided files that LLM did not touch pass through unchanged
6. Builder extracts a route manifest from the merged file set for the ui-designer
7. Returns `{files, routes: [{method, path, description}], template_used: "fastapi-base/v1"}`

### Reviewer fix loop

1. Reviewer returns `{passed: false, fix_instructions: [...]}`
2. Gateway calls `POST /build` again with original build plan + fix instructions as additional context
3. Builder regenerates only the LLM-added files; template-provided files are not re-evaluated
4. Returns updated file set to reviewer
5. Bounded by `MAX_REVIEWER_RETRIES` in the gateway

### LLM parse failure (fallback)

1. LLM returns malformed JSON or unusable output
2. Builder returns the base template file set unchanged (a minimal but standards-compliant app)
3. Fallback is logged to `agent_runs`; build continues (unlike the previous per-type fallback model, all types now have a valid fallback — the template itself)

### Documentation generation

Documentation files are generated alongside application code from the same build context (spec + route manifest + build plan). They are committed to the Gitea repo by the publisher and versioned with the code they describe.

**Always generated:**
- `README.md` — operator-facing reference with six sections:
  1. **Overview** — one-paragraph description from the spec
  2. **Access** — live URL (`{name}.APP_DOMAIN`) and Gitea repo link
  3. **API reference** — table of routes derived from the route manifest: method, path, description, auth required
  4. **Data model** — entities and fields for `form`, `workflow`, `connector`, `assistant` types; omitted for `dashboard`
  5. **Environment variables** — table of all env vars the app reads, their purpose, and whether required
  6. **Usage notes** — operator-facing instructions specific to the app (e.g. how to submit a form, how to upload documents for an assistant)

**Generated for `connector` and `assistant` types:**
- `docs/api.md` — expanded API reference with request/response examples and error codes

**Generated for `assistant` type:**
- `docs/data-ingestion.md` — how to upload and index documents; supported file types; chunking strategy

Documentation generation is deterministic from the build context — it does not require an additional LLM call. The spec, route manifest, and build plan contain all the information needed. If any section cannot be derived (e.g. no routes in the manifest), that section is omitted rather than fabricated.

## Data owned

The builder agent has no direct database access. It does not read or write any Postgres tables.

**Reads (via prompt context, not DB):**
- Build plan — received from gateway in the request body
- Standards YAML files — loaded from filesystem at startup and injected into the generation prompt

**Writes (filesystem only):**
- Generated files are returned in the response body; they are not persisted by the builder itself. The publisher handles committing them to Gitea.

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Ollama unreachable | Returns HTTP 503 to gateway; build pipeline is aborted |
| LLM returns malformed JSON | Loads typed fallback template for the app type (currently only `form` type has a fallback; other types surface an error) |
| Reviewer fix loop exceeds `MAX_REVIEWER_RETRIES` | Gateway aborts the build; builder is not called again |
| Route manifest extraction fails | Returns an empty route manifest; ui-designer receives no routes and generates a minimal fallback template |

## Non-functional constraints

- Code generation involves one Ollama call per build; latency is typically 10–60 s depending on app complexity and model.
- Generated code size is bounded by the LLM output token limit; large apps with many routes may be truncated.
- Stateless — each `POST /build` call is independent; no in-memory state between requests.

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /build` | Gateway | Generate application files from a build plan |
| `GET /health` | Traefik / gateway | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| Ollama HTTP API | LLM-based file generation |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `OLLAMA_MODEL` | `llama3.1:8b` | Model for code generation (`qwen2.5-coder:32b` recommended when VRAM allows) |
| `OLLAMA_URL` | `http://ollama:11434` | |
| `STANDARDS_PATH` | `/standards` | Mount path for YAML standards files injected into the generation prompt |

## Known limitations

- The LLM may modify template-provided protected files (Dockerfile, logging setup) despite prompt instructions; the reviewer's static checks catch these regressions but add a retry cycle.
- Route manifest extraction from merged files is heuristic; non-standard route registration patterns may produce an incomplete manifest.
- Template files are baked into the builder image; updating a template requires rebuilding the builder container. Running builds are not affected.
- LLM augmentation prompt length grows with template file count; very large templates may need summarisation rather than full inclusion to fit within the context window.
