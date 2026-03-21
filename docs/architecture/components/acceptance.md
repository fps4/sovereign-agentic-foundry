---
title: "Component design: Acceptance agent"
status: proposed
last_updated: 2026-03-21
owners: [platform-team]
c4_level: component
container: acceptance
related:
  - docs/architecture/overview.md
  - docs/architecture/components/remediation.md
  - docs/architecture/components/watchdog.md
---

## Purpose

The acceptance agent validates a newly deployed application by exercising its live HTTP endpoints against the spec. It runs once after each successful Woodpecker deploy step. A passing acceptance check transitions the app to `active`; a failure triggers the remediation agent before the operator is notified.

This is distinct from the `test-writer` / pytest step, which validates source correctness at CI time. Acceptance validates the running deployment: container started, routes bound, responses healthy.

## Responsibilities

**Owns:**
- Deriving expected routes and flows from the locked spec
- Issuing HTTP requests against the live app URL with retry/backoff for container startup lag
- Recording per-route results (status code, latency, error body)
- Reporting pass/fail to the gateway

**Does not own:**
- Source-level test generation (owned by the test-writer agent)
- Error remediation (owned by the remediation agent)
- Continuous monitoring after the initial deploy check (owned by the watchdog)
- App status updates (owned by the gateway)

## Internal structure

| Component | Responsibility |
|-----------|----------------|
| `main.py` | FastAPI app, `POST /accept` endpoint |
| Route exerciser | Derives expected endpoints from spec; issues requests in dependency order (health → read → write) |
| Retry controller | Exponential backoff for container startup; configurable max wait |
| Result recorder | Structures per-route outcomes for the gateway and remediation context |

## Key flows

### Happy path

1. Woodpecker CI signals deploy complete to gateway (via webhook or polling)
2. Gateway calls `POST /accept` with `{app_name, app_url, spec}`
3. Acceptance derives expected routes from spec (e.g. `GET /`, `GET /health`, form POST endpoints)
4. Issues `GET /health` first; retries with backoff up to `ACCEPTANCE_STARTUP_WAIT` seconds
5. Exercises remaining routes in order; records status code and latency per route
6. Returns `{passed: true, results: [...]}` to gateway
7. Gateway sets `apps.status = active`, sends Telegram notification to operator with app URL

### Failure: container not healthy within startup window

1. `GET /health` does not return 200 within `ACCEPTANCE_STARTUP_WAIT` seconds
2. Returns `{passed: false, failures: [{route: "/health", reason: "timeout"}]}`
3. Gateway calls remediation agent with failure context; does not notify operator yet

### Failure: route returns error

1. A spec-derived route returns 5xx or connection error
2. Returns `{passed: false, results: [...], failures: [{route, status, body}]}`
3. Gateway calls remediation agent; remediation attempts patch and redeploy
4. Acceptance is called again after redeploy; bounded by `MAX_REMEDIATION_RETRIES`
5. If still failing after retries: gateway sets `apps.status = failed`, notifies operator

## Data owned

The acceptance agent has no direct database access. It reports results to the gateway, which owns all status writes.

**Reads (via request body, not DB):**
- App spec and app URL — received from gateway in the request body

## Error handling and failure modes

| Failure | Behaviour |
|---------|-----------|
| App container not reachable within startup window | Returns `{passed: false, failures: [{route: "/health", reason: "timeout"}]}`; gateway calls remediation |
| Route returns 5xx | Returns `{passed: false, failures: [...]}`; gateway calls remediation |
| Network partition between acceptance and deployed app | Treated as a health timeout; remediation is called |
| Gateway unreachable after check | Result cannot be reported; acceptance container logs the outcome; app status remains in intermediate state until gateway is restored |

## Non-functional constraints

- Acceptance is called once per deploy; it is not a continuous monitor (that is the watchdog's role).
- Total acceptance time is bounded by `ACCEPTANCE_STARTUP_WAIT` + (number of routes × `ACCEPTANCE_REQUEST_TIMEOUT`).
- Write-path checks use synthetic payloads; they validate route binding but not data integrity.

## External interfaces

### Exposes

| Endpoint | Caller | Purpose |
|----------|--------|---------|
| `POST /accept` | Gateway | Run acceptance check for a freshly deployed app |
| `GET /health` | Traefik / gateway | Health check |

### Calls

| Target | Purpose |
|--------|---------|
| Deployed app HTTP endpoints | Exercise live routes against spec |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `ACCEPTANCE_STARTUP_WAIT` | `60` | Seconds to wait for `/health` to return 200 after deploy |
| `ACCEPTANCE_RETRY_INTERVAL` | `5` | Seconds between startup retries |
| `ACCEPTANCE_REQUEST_TIMEOUT` | `10` | Per-request timeout in seconds |

## Known limitations

- Route derivation from the spec is heuristic; routes added by the builder that are not reflected in the spec will not be exercised.
- Write-path testing (e.g. form submissions that mutate state) is limited to well-formed synthetic payloads and may miss validation edge cases.
- Acceptance runs once at deploy time; it does not detect regressions introduced after the initial deploy (that is the watchdog's role).
