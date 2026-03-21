---
title: "Component design: UI designer agent"
status: proposed
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: ui-designer
related:
  - docs/architecture/overview.md
  - docs/architecture/components/builder.md
  - docs/architecture/components/reviewer.md
---

## Purpose

The UI designer agent generates styled, accessible frontend templates for a scaffolded application. It runs after the builder has produced backend code and before the reviewer validates the full project. It owns all presentation-layer decisions so that the builder can focus exclusively on backend logic.

## Responsibilities

**Owns:**
- Layout and navigation structure for each app type
- HTML/CSS template generation (Jinja2 for FastAPI apps, Handlebars for Express apps)
- Applying the platform UI standards (`ui-standards.yaml`): spacing, colour, typography, accessibility
- Deriving UI structure from the spec and the backend routes produced by the builder

**Does not own:**
- Backend code generation (owned by the builder agent)
- Spec clarification (owned by the intake agent)
- Standards compliance review (owned by the reviewer agent)
- Deployment or routing (owned by Woodpecker CI and Traefik)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, `POST /design-ui` endpoint |
| LangChain / Ollama | LLM calls for template generation; receives spec + route manifest |
| `ui-standards.yaml` | Design system rules: component palette, spacing scale, colour tokens, accessibility requirements |
| Template corrector | Post-processes LLM output to fix known structural issues (unclosed tags, missing CSRF tokens on forms) |

## Key flows

### Happy path

1. Build pipeline calls `POST /design-ui` with `{spec, routes: [{method, path, description}]}`
2. UI designer loads `ui-standards.yaml` and injects it into the LLM system prompt
3. LLM generates templates appropriate to the app type:
   - `form`: input form, confirmation page, success/error states
   - `dashboard`: data table or chart layout, filter controls
   - `workflow`: step indicator, status badges, action buttons
   - `connector`: status page, last-sync indicator
   - `assistant`: chat interface, document upload, response panel
4. Template corrector post-processes output for known LLM mistakes
5. Returns `{files: [{path, content}]}` in the same format as the builder

### LLM output unusable

1. LLM returns malformed or empty templates
2. UI designer falls back to typed base templates per app type (minimal but functional)
3. Build proceeds with fallback templates; limitation is logged

## Data owned

The UI designer agent has no direct database access. It does not read or write any Postgres tables.

**Reads (via prompt context, not DB):**
- Spec and route manifest — received from gateway in the request body
- `ui-standards.yaml` — loaded from filesystem at startup

**Writes (response body only):**
- Generated template files are returned in the response body; not persisted by the UI designer.

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Ollama unreachable | Returns HTTP 503 to gateway; build pipeline is aborted |
| LLM returns malformed or empty templates | Falls back to typed base templates per app type; build proceeds |
| Route manifest is empty | UI designer generates a single index template with no navigation structure |
| Template corrector finds unresolvable issue | Logs the issue; returns the best-effort output; reviewer may catch the problem |

## Non-functional constraints

- Template generation involves one Ollama call; latency is typically 5–30 s.
- Fallback templates are minimal and unstyled; they pass the reviewer but produce a degraded operator experience.
- Stateless — each `POST /design-ui` call is independent.

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /design-ui` | Build pipeline (gateway) | Generate frontend templates |
| `GET /health` | Traefik / gateway | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| Ollama HTTP API | LLM template generation |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `OLLAMA_MODEL` | `llama3.1:8b` | Model for template generation |
| `OLLAMA_URL` | `http://ollama:11434` | |
| `STANDARDS_PATH` | `/standards` | Mount path; expects `ui-standards.yaml` alongside existing YAML files |

## Known limitations

- No browser-based visual validation — generated templates are not rendered and checked; only structural correctness is verified.
- Template quality degrades when the builder's route manifest is sparse or undescribed.
- Fallback templates are minimal and unstyled; they pass the reviewer but produce a poor operator experience.
- No support for single-page application frameworks; all output is server-rendered templates.
