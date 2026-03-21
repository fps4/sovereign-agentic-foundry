---
title: "Component design: Reviewer agent"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: reviewer
related:
  - docs/architecture/overview.md
  - docs/architecture/components/builder.md
  - docs/architecture/components/ui-designer.md
  - docs/architecture/components/publisher.md
---

## Purpose

The reviewer agent is a standards quality gate. It checks all generated files — backend code from the builder and frontend templates from the ui-designer — against the platform's standards YAML files before any commit to Gitea. It returns either a pass (files proceed to the publisher) or structured fix instructions (files return to the builder for correction).

## Responsibilities

**Owns:**
- Static standards checking against `naming.yaml`, `security.yaml`, `patterns.yaml`, and `ui-standards.yaml`
- LLM-assisted semantic review for issues that cannot be caught by static rules (e.g. incorrect pattern usage, insecure logic)
- Structured fix instruction generation: specific, actionable, scoped to the offending file and line
- Pass/fail verdict returned to the gateway

**Does not own:**
- Code generation (owned by the builder agent)
- Template generation (owned by the ui-designer agent)
- Git operations (owned by the publisher)
- Running tests (handled by pytest in the Woodpecker CI step)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, `POST /review` endpoint |
| Static checker | Rule-based checks from standards YAML: naming conventions, forbidden patterns, required security headers |
| LLM reviewer | Ollama call for semantic review; receives files + standards + static checker findings |
| Fix formatter | Structures LLM output into `{file, issue, fix_instruction}` items for the builder |

## Key flows

### Pass

1. Gateway calls `POST /review` with `{files: [{path, content}], spec}`
2. Static checker runs rules from standards YAML against all files
3. LLM reviewer checks for semantic issues not covered by static rules
4. No issues found: returns `{passed: true}`
5. Gateway proceeds to publisher

### Fix required

1. Static checker or LLM reviewer identifies one or more violations
2. Fix formatter produces `{passed: false, fix_instructions: [{file, issue, fix_instruction}]}`
3. Gateway sends fix instructions to builder for correction
4. Builder returns updated files; gateway calls reviewer again
5. Bounded by `MAX_REVIEWER_RETRIES` in the gateway; on exhaustion, build is aborted

## Data owned

The reviewer agent has no direct database access.

**Reads (via prompt context, not DB):**
- Generated files — received from gateway in the request body
- Standards YAML files (`naming.yaml`, `security.yaml`, `patterns.yaml`, `ui-standards.yaml`) — loaded from filesystem at startup

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Ollama unreachable | Returns HTTP 503 to gateway; build pipeline is aborted (files cannot be reviewed) |
| LLM returns unparseable verdict | Treated as a pass with a warning log; build proceeds (conservative: avoids blocking on reviewer instability) |
| Static checker finds a rule with no fix instruction | Returns the raw rule name as the fix instruction; builder may not be able to act on it |
| Fix loop diverges (corrected file re-introduces old issue) | Gateway enforces `MAX_REVIEWER_RETRIES`; build is aborted after limit is reached |

## Non-functional constraints

- Semantic review involves one Ollama call per review cycle; latency is typically 5–20 s.
- Non-deterministic LLM output means the same file may receive different verdicts across runs.
- Static checker is O(n) in the number of files; review time scales linearly with build plan size.

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /review` | Gateway | Run standards check on generated files |
| `GET /health` | Traefik / gateway | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| Ollama HTTP API | LLM semantic review |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `OLLAMA_MODEL` | `llama3.1:8b` | Model for semantic review |
| `OLLAMA_URL` | `http://ollama:11434` | |
| `STANDARDS_PATH` | `/standards` | Mount path; reviewer loads all YAML files at startup |

## Known limitations

- LLM semantic review is non-deterministic; the same file may receive different verdicts across runs, which can cause a fix loop where corrected output re-introduces a previously passing file's issue.
- Static checker rules are maintained manually in standards YAML; new security patterns must be explicitly added.
- Review covers generated files only; dependencies introduced in `requirements.txt` are not scanned for known vulnerabilities.
