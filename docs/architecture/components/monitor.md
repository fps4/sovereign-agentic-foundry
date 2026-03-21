---
title: "Component design: Monitor agent"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: monitor
related:
  - docs/architecture/overview.md
  - docs/architecture/components/orchestrator.md
  - docs/architecture/data-model.md
---

## Purpose

The monitor agent continuously watches all running application containers for log errors and health failures. When it detects a new unique error, it creates a Gitea issue on the affected app's repository and notifies the app owner via Telegram. It is an independent background service, not part of the build pipeline.

## Responsibilities

**Owns:**
- Polling running containers via the Docker socket
- Error detection via log regex pattern matching
- Error deduplication by hash (each unique error reported once)
- Gitea issue creation with LLM-generated plain-English summary
- App status updates (`degraded` / `failed`)
- Telegram notification for breaking issues

**Does not own:**
- Fixing errors (that is a future automated re-coder trigger)
- CI pipeline execution (owned by Woodpecker)
- App registry CRUD (owned by the orchestrator)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | Background polling loop; Docker socket access via `docker` SDK |
| Error regex | Pattern list matched against each log line |
| Hash deduplication | MD5 of normalised error text; checked against `app_issues` via orchestrator API |
| LLM summariser | Ollama call to produce a human-readable issue title and body |
| Orchestrator client | `POST /apps/{name}/report-issue` — delegates issue creation and notification |

## Key flows

### Polling loop

1. Every `MONITOR_POLL_INTERVAL` seconds: list all running containers on the platform network
2. For each container: fetch the last `MONITOR_LOG_LINES` log lines
3. Apply regex patterns to detect error-level entries
4. Normalise and hash the error text
5. Call `POST /apps/{name}/report-issue` on the orchestrator with `{error_hash, summary, is_breaking}`
6. Orchestrator checks `app_issues` for duplicate hash; skips if already recorded
7. On new error: orchestrator creates Gitea issue, updates `apps.status`, sends Telegram notification if breaking
8. Apply `MONITOR_COOLDOWN` before re-checking the same container

### Container health failure

1. Docker SDK reports container in `unhealthy` or `exited` state
2. Treated as a breaking issue regardless of logs
3. Follows the same report path via orchestrator

## External interfaces

### Calls

| Target | Purpose |
|--------|---------|
| Docker socket (read-only) | List containers, fetch logs, check health |
| `orchestrator POST /apps/{name}/report-issue` | Delegate issue creation and notification |
| Ollama HTTP API | LLM-generated issue summary |

### No HTTP server

The monitor has no exposed port. It runs as a background process only.

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `MONITOR_POLL_INTERVAL` | `60` | Seconds between full container sweeps |
| `MONITOR_COOLDOWN` | `600` | Seconds before re-checking the same container after an alert |
| `MONITOR_LOG_LINES` | `50` | Log lines sampled per container per poll |
| `ORCHESTRATOR_URL` | `http://orchestrator:8000` | |
| `OLLAMA_MODEL` | `llama3.1:8b` | Model for log summarisation |
| `OLLAMA_URL` | `http://ollama:11434` | |

## Known limitations

- Regex-based error detection produces false positives on log lines that contain words like "error" in non-error contexts (e.g. user input).
- The cooldown is per-container, not per-error-hash — a container with two different errors will only report one per cooldown window.
- Monitor runs independently and cannot trigger orchestrated remediation (e.g. re-running the coder). ADR-0001 notes this as a future integration point.
