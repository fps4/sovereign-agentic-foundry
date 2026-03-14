# POC Design

An agentic platform that builds applications on sovereign infrastructure. Users describe what they want via Telegram → a designer agent clarifies intent and writes a structured spec → specialist agents build, test, and deploy → a monitor agent closes the feedback loop.

- [Agent pipeline design](./agent-pipeline.md)
- [App types](./app-types.md)
- [High-level system design](./diagrams/high-level-system-design.png)
- [Orchestration detail](./diagrams/orchestration.png)
- [Docker Compose services](./diagrams/services.png)

---

## Build phases

**Phase 1 — Skeleton** ✅

Conversation loop only: Telegram bot → FastAPI orchestrator → Ollama → reply. No agents yet — just prove the messaging pipeline works and the LLM can classify intent. Services: `traefik`, `telegram-bot`, `orchestrator`, `ollama`, `postgres`.

**Phase 2 — Architecture standards** ✅

`standards/` YAML files (naming, patterns, security) loaded by the orchestrator at startup and injected into every LLM system prompt — the opinionated layer that makes it a platform, not a generic assistant.

**Phase 3 — First agent** ✅

`agents/coder/`: receives a task spec extracted by the orchestrator's intent classifier, uses the LLM to scaffold a repo (files + Dockerfile + `.woodpecker.yml`), commits to Gitea via API, and returns the repo URL. Woodpecker CI triggers a pipeline on every push. New services: `gitea`, `woodpecker-server`, `woodpecker-agent`, `coder`; per-user Gitea orgs with invite-code registration enforce tenancy.

## Deferred to a later stage with multi-node Docker or K8S

**Phase 4 — Infra + review agents**

Add OpenTofu for infra provisioning and Semgrep/Trivy for the review gate. Nothing gets committed unless the review agent approves. Stream status updates back during long-running operations.

**Phase 5 — Observability and web hub**

Add Prometheus + Grafana for the platform itself, and a minimal Next.js dashboard showing active jobs, deployment history, and alerts.

---

## Key design decisions

**LangGraph** models agent execution as a directed graph with checkpointed state — workflows can pause and resume, which matters when a deploy takes minutes. State is stored in PostgreSQL so nothing is lost on restart.

**Gitea + Woodpecker CI** are fully self-hosted and purpose-built to work together. Woodpecker triggers on every push to Gitea; the deploy step runs the container with Traefik labels so it is immediately accessible under `APP_DOMAIN`.

**Ollama** exposes any local model (Mistral, Llama 3, Qwen2.5-Coder) via HTTP with no setup overhead. Qwen2.5-Coder-32B is the best choice for the coder agent if VRAM allows; Llama 3.1 8B handles intent classification well.

**Tenancy** is enforced at the Gitea organisation level. Each registered user gets a private Gitea org (`user-<telegram_id>`). The orchestrator scopes all repo operations to the user's org. Registration requires an invite code supplied over Telegram — no email or external identity provider needed. If `INVITE_CODE` is unset, registration is open.

---

## Repo structure

```
sovereign-agentic-foundry/
├── docker-compose.yml
├── standards/          # Architecture YAML rules (naming, patterns, security)
│   ├── patterns.yaml
│   ├── security.yaml
│   └── naming.yaml
├── orchestrator/       # FastAPI + LangGraph (intent classification, chat, registry)
├── agents/
│   ├── coder/          # Scaffolds repos and commits to Gitea
│   └── monitor/        # Polls containers, files issues, notifies owners
├── bots/
│   └── telegram/       # Telegram polling bot
├── infra/              # Traefik config
└── docs/               # Design docs and diagrams
```
