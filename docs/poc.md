# Sovereign Agentic Foundry — Design

A platform that builds, tests, deploys, and monitors applications from
natural-language descriptions. Users interact over Telegram; the platform
handles everything from spec to a live public URL, running entirely on
self-hosted infrastructure.

Diagrams: [system overview](./diagrams/high-level-system-design.png) · [orchestration detail](./diagrams/orchestration.png) · [services](./diagrams/services.png)

---

## Product Design

### User Experience

Users interact exclusively through a Telegram bot. Registration requires only
an invite code — no email, no web form. Once registered, a user describes what
they want to build in plain language:

> *"I need a form to track patient intake"*

The designer agent opens a short clarification conversation, confirms the spec,
then hands off. From that point the pipeline runs fully automatically: code is
generated, tests are written and run, the container is built and deployed, and
the user receives a live URL. Subsequent pushes to the repo retrigger CI and
redeploy automatically.

Commands:
- **/build** — start a new app with a guided description prompt
- **/apps** — list all apps with status, issue count, and live URL
- **/fix** — report a problem on a specific app (opens a Gitea issue)
- **/delete** — archive an app: stops the container, preserves the repo

### App Types

Five scaffolds are built in. The designer agent determines the type during
clarification; users can also name the type explicitly.

**Form** — collect and manage structured records  
A CRUD app backed by a database. Covers single-submission forms (intake,
consent, incident reports) and ongoing registries (staff directories, device
inventories). Generates POST / GET / PATCH / DELETE endpoints with a SQLite
backend, a non-root Docker user, and a `/health` endpoint.

**Dashboard** — display live or aggregated data  
A read-only interface that visualises metrics, lists, or statuses pulled from
an API or database. Includes filters, drill-downs, and auto-refresh. No write
operations. Examples: bed occupancy, clinical KPIs, equipment maintenance
status.

**Workflow** — move tasks through stages  
A multi-role app where items progress through defined states with assignments,
transitions, notifications, and an audit trail. Also covers scheduled or
event-driven automations that run without human interaction. Examples: referral
tracking, care pathway adherence, nightly report emails, appointment reminders.

**Connector** — link two systems, no UI  
A headless backend service that listens for events from one system, transforms
the data, and forwards it to another. Exposes a health endpoint but no
user-facing interface. Stateless by design. Examples: HL7v2 → FHIR R4 adapter,
lab result router, EHR-to-reporting-database sync.

**Assistant** — chat and Q&A over documents  
A RAG-powered conversational interface grounded in internal documents or a
knowledge base. Distinct architecture from the other four types — built around
a vector store and LLM inference rather than a traditional database schema.
Examples: protocol and SOP Q&A, drug formulary assistant, staff onboarding bot.

---

## Agent Pipeline

### Flow

```
User (Telegram)
  ↕  multi-turn conversation
Designer agent
  → produces structured spec (name, type, stack, requirements)
  ↓
Orchestrator
  → creates app registry entry, kicks off background build task
  ↓
Coder agent
  → scaffolds project files, Dockerfile, CI config
  → commits to Gitea repo in user's private org
  ↓  Gitea webhook → Woodpecker CI triggered
Tester agent  (Woodpecker step: generate-tests)
  → reads source from Gitea, generates pytest files via LLM
  → writes tests into CI workspace
  ↓
Test step
  → pip install + pytest — pipeline fails here if tests fail
  ↓
Docker build step
  → docker build, image tagged with repo name
  ↓
Deploy step
  → docker rm -f + docker run with Traefik labels on platform network
  → app live at http://{name}.APP_DOMAIN
  ↓
Monitor agent  (continuous, independent)
  → polls container logs and health
  → reports issues to orchestrator → Gitea issue + Telegram notification
```

No human approval gates exist between designer handoff and deploy.

### Agent Responsibilities

**Designer**  
Holds a multi-turn conversation until the spec is unambiguous. Produces a
structured spec (name, description, app type, stack, requirements). Design
state is persisted in Postgres — conversations survive restarts. Hands off
automatically once the spec is complete.

**Coder**  
Receives the spec from the orchestrator. Scaffolds or modifies project files
using the LLM, with typed fallbacks for Python/FastAPI and Node/Express.
Commits all files to a new Gitea repo in the user's private org. Returns the
repo URL and expected app URL.

**Tester**  
Invoked as the first Woodpecker CI step (`generate-tests`). Fetches source
files from Gitea, generates pytest test files via LLM, auto-corrects known
import mistakes, and writes them directly into the CI workspace. A subsequent
`test` step runs pytest — a failing test blocks deploy.

**Monitor**  
Runs continuously and independently. Polls all running platform containers,
detects log errors and container failures, deduplicates by error hash, creates
a Gitea issue with an LLM-generated plain-English summary, updates app status
(`degraded` / `failed`), and notifies the app owner via Telegram once per
unique error.

### Handoff Artefacts

| From | To | Artefact |
|---|---|---|
| User conversation | Designer | Clarified intent (Postgres FSM state) |
| Designer | Orchestrator | Structured spec (JSON) |
| Coder | Woodpecker CI | Gitea repo with source, Dockerfile, `.woodpecker.yml` |
| Tester (CI step) | Test step | pytest files written to CI workspace |
| CI | Deploy | Green build → image built, container started |
| Monitor | Owner | Gitea issue on app repo + Telegram notification |

### Feedback Loop

The pipeline is not linear — the monitor closes a continuous improvement loop:

```
Monitor detects issue
  → Gitea issue created on app repo
  → manual fix or future automated re-coder trigger
  → commit → CI → deploy
  → Monitor confirms container healthy
```

---

## Technology Design

### Orchestration — LangGraph

The orchestrator uses LangGraph to model the intent-classification and
designer-handoff flow as a directed graph with checkpointed state stored in
Postgres. Graph nodes: `classify → respond | confirm_build | ask_type`.
Workflows can pause mid-conversation and resume when the next message arrives,
surviving restarts without losing state.

### Git and CI — Gitea + Woodpecker

Gitea and Woodpecker are self-hosted and purpose-built to work together.
Woodpecker repo activation is automatic — the orchestrator inserts the repo
directly into Woodpecker's Postgres database and creates a HMAC-signed Gitea
webhook, so no manual dashboard interaction is ever needed. Woodpecker CI
agent containers run on the `platform_platform` Docker network, giving them
direct access to internal services (tester, Docker daemon) by hostname.

### Local Inference — Ollama

Ollama exposes any local model via HTTP with no setup overhead or external API
keys. Used by every agent: intent classification, designer clarification, code
scaffolding, test generation, and log summarisation. Recommended models:
`llama3.1:8b` for classification and conversation; `qwen2.5-coder:32b` for
the coder and tester agents when VRAM allows.

### Tenancy

Each registered user receives a private Gitea organisation (`user-<telegram_id>`).
All Gitea API operations in the orchestrator and coder agent are scoped to the
user's org. Registration requires only an invite code over Telegram — no email
or external identity provider. Setting `INVITE_CODE` restricts access; leaving
it unset opens registration.

### Standards Injection

`standards/` contains YAML files defining platform-wide architecture rules
(naming conventions, security requirements, code patterns). The orchestrator
loads them at startup and injects the combined block into every LLM system
prompt. This is the opinionated layer that makes generated apps consistent
across agents and runs.

---

## System Architecture

### Services

| Service | Description |
|---|---|
| `traefik` | Reverse proxy — routes `*.APP_DOMAIN` to deployed apps and orchestrator |
| `postgres` | Shared database for users, app registry, agent runs, Woodpecker state |
| `ollama` | Local LLM inference |
| `gitea` | Self-hosted Git — one private org per user, one repo per app |
| `woodpecker-server` | CI server and web UI |
| `woodpecker-agent` | CI runner — executes pipeline steps in Docker containers |
| `orchestrator` | FastAPI + LangGraph — intent, chat, registry, pipeline dispatch |
| `designer` | Multi-turn spec agent |
| `coder` | Scaffold and commit agent |
| `tester` | Test generation agent (called from within CI) |
| `monitor` | Continuous log and health monitor |
| `telegram-bot` | Telegram polling bot — the user-facing interface |
| `loki` + `promtail` | Log aggregation |
| `grafana` | Observability dashboard |

### Repo Structure

```
sovereign-agentic-foundry/
├── docker-compose.yml
├── standards/              # Architecture YAML rules (naming, patterns, security)
├── orchestrator/           # FastAPI + LangGraph
├── agents/
│   ├── designer/           # Multi-turn spec agent
│   ├── coder/              # Scaffold, commit, and CI config generation
│   ├── tester/             # LLM test generation (called as a CI step)
│   └── monitor/            # Container log and health monitor
├── bots/
│   └── telegram/           # Telegram polling bot
├── infra/                  # Traefik config, Loki, Promtail, Grafana
└── docs/                   # Design docs and diagrams
```

---

## Roadmap

| Status | What |
|---|---|
| ✅ Done | Conversation loop, standards injection, coder agent, Gitea + Woodpecker CI |
| ✅ Done | Designer agent (multi-turn clarification → spec) |
| ✅ Done | Tester agent (LLM test generation as mandatory CI step) |
| ✅ Done | App registry, status tracking, monitor → report-issue deduplication |
| ✅ Done | Automatic Woodpecker repo activation (no manual setup) |
| **Next** | Wiki app type — collaborative document editing |
| **Next** | Compliance agent — policy and standards review gate before deploy |
| **Next** | Improved monitor issue reporting — smarter deduplication and root-cause hints |
| **Later** | App lifecycle management — data retention, archival, breaking-change handling |
| **Later** | /examples — platform-hosted showcase apps by category |
| **Later** | Internal platform apps — Apps, Issues, Users, Statistics dashboards |
| **Later** | Security scan gate — Semgrep + Trivy before deploy |
| **Later** | Multi-node / Kubernetes — horizontal scale for CI and inference |
