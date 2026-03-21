---
title: "Component design: Watchdog"
status: current
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: watchdog
related:
  - docs/architecture/overview.md
  - docs/architecture/components/gateway.md
  - docs/architecture/components/remediation.md
  - docs/architecture/data-model.md
---

## Purpose

The watchdog continuously monitors all running application containers for log errors and health failures. When it detects a new unique error, it reports it to the gateway. For breaking errors, the gateway triggers the remediation agent; for non-breaking errors, a Gitea issue is created and the operator is notified via Telegram. The watchdog is an independent background service with no HTTP server and no role in the build pipeline.

## Responsibilities

**Owns:**
- Polling running containers via the Docker socket
- Error detection via log regex pattern matching
- Error deduplication by hash (each unique error reported once)
- Container health state monitoring (unhealthy / exited)

**Does not own:**
- Error remediation (owned by the remediation agent)
- Gitea issue creation (owned by the gateway, which the watchdog reports to)
- App status updates (owned by the gateway)
- CI pipeline execution (owned by Woodpecker)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | Background polling loop; Docker socket access via `docker` SDK |
| Error regex | Pattern list matched against each log line |
| Hash deduplication | MD5 of normalised error text; checked against known hashes via gateway API |
| LLM summariser | Ollama call to produce a human-readable issue title and body for the gateway |
| Gateway client | `POST /apps/{name}/report-issue` — delegates all downstream actions |

## Key flows

### Polling loop

1. Every `WATCHDOG_POLL_INTERVAL` seconds: list all running containers on the platform network
2. For each container: fetch the last `WATCHDOG_LOG_LINES` log lines
3. Apply regex patterns to detect error-level entries
4. Normalise and hash the error text
5. Call `POST /apps/{name}/report-issue` on the gateway with `{error_hash, summary, is_breaking, logs}`
6. Gateway checks `app_issues` for duplicate hash; skips if already recorded
7. On new breaking error: gateway triggers remediation agent; sets `apps.status = degraded`
8. On new non-breaking error: gateway creates Gitea issue; sends Telegram notification
9. Apply `WATCHDOG_COOLDOWN` before re-checking the same container

### Container health failure

1. Docker SDK reports container in `unhealthy` or `exited` state
2. Treated as a breaking issue regardless of log content
3. Follows the same report path via gateway

## Data owned

The watchdog has no direct database access. All persistence (deduplication, issue tracking, status updates) is delegated to the gateway via `POST /apps/{name}/report-issue`.

**Reads:**
- Docker socket (read-only) — container list, logs, health state

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| Gateway unreachable | Error report is dropped; watchdog logs the failure and continues polling on next cycle |
| Docker socket unreachable | Watchdog logs a fatal error; polling loop stops; service must be restarted |
| Ollama unreachable | LLM summarisation skipped; raw log excerpt sent as the issue summary instead |
| Container produces continuous errors | Cooldown prevents repeated reports; only the first unique error per `WATCHDOG_COOLDOWN` window is reported |
| False positive (word "error" in user input echoed in logs) | Reported to gateway; gateway deduplication via hash prevents repeated Gitea issues |

## Non-functional constraints

- No HTTP server; not reachable from other platform services.
- Polling is synchronous per container; large numbers of running apps increase poll cycle duration.
- The cooldown is per-container, not per-error — a container with two distinct errors will only report one per cooldown window.

## External interfaces

### Calls

| Target | Purpose |
|--------|---------|
| Docker socket (read-only) | List containers, fetch logs, check health |
| `gateway POST /apps/{name}/report-issue` | Report detected error |
| Ollama HTTP API | LLM-generated issue summary |

### No HTTP server

The watchdog has no exposed port. It runs as a background process only.

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `WATCHDOG_POLL_INTERVAL` | `60` | Seconds between full container sweeps |
| `WATCHDOG_COOLDOWN` | `600` | Seconds before re-checking the same container after an alert |
| `WATCHDOG_LOG_LINES` | `50` | Log lines sampled per container per poll |
| `ORCHESTRATOR_URL` | `http://gateway:8000` | Gateway base URL |
| `WATCHDOG_LLM_PROVIDER` | `ollama` | LLM provider: `ollama`, `openai`, `anthropic` |
| `WATCHDOG_LLM_MODEL` | provider default | Model name. Defaults: `llama3.1:8b` (ollama), `gpt-4o` (openai), `claude-sonnet-4-6` (anthropic) |
| `WATCHDOG_LLM_API_KEY` | — | API key for the chosen provider. Falls back to `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`. Required when provider ≠ `ollama` |
| `OLLAMA_URL` | `http://ollama:11434` | Used only when `WATCHDOG_LLM_PROVIDER=ollama` |

## Known limitations

- Regex-based error detection produces false positives on log lines that contain words like "error" in non-error contexts (e.g. user input echoed in logs).
- The cooldown is per-container, not per-error-hash — a container with two distinct errors will only report one per cooldown window.
- Watchdog cannot trigger remediation directly; it reports to the gateway, which decides whether to invoke remediation. This adds one network hop to the critical path.
