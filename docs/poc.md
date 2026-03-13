# POC Design

An agentic platform that builds applications on sovereign infrastructure. Users describe what they want via Telegram → an orchestration layer interprets intent against architecture standards → agents plan and execute the build → results and status stream back to the user.

- [High-level system design](./diagrams/high-level-system-design.png)
- [Orchestration detail](./diagrams/orchestration.png)
- [Docker Compose services](./diagrams/services.png)

---

## Build phases

**Phase 1 — Skeleton**

Conversation loop only: Telegram bot → FastAPI orchestrator → Ollama → reply. No agents yet — just prove the messaging pipeline works and the LLM can classify intent. Services: `traefik`, `telegram-bot`, `orchestrator`, `ollama`, `postgres`.

**Phase 2 — Architecture standards** ✅

`standards/` YAML files (naming, patterns, security) loaded by the orchestrator at startup and injected into every LLM system prompt — the opinionated layer that makes it a platform, not a generic assistant.

**Phase 3 — First agent**

Add the coder-agent. It receives a task spec (structured JSON from the orchestrator), uses the LLM + Aider/CodeAct to scaffold a repo, commits to Gitea, and returns the PR link. Wire up Woodpecker CI to trigger builds on push.

**Phase 4 — Infra + review agents**

Add OpenTofu for infra provisioning and Semgrep/Trivy for the review gate. Nothing gets committed unless the review agent approves. Stream status updates back during long-running operations.

**Phase 5 — Observability and web hub**

Add Prometheus + Grafana for the platform itself, and a minimal Next.js dashboard showing active jobs, deployment history, and alerts.

---

## Key design decisions

**LangGraph** models agent execution as a directed graph with checkpointed state — workflows can pause and resume, which matters when a deploy takes minutes. State is stored in PostgreSQL so nothing is lost on restart.

**Gitea + Woodpecker CI** are fully self-hosted and purpose-built to work together. ArgoCD watches Gitea for GitOps-style deployments to K3s (or plain Docker Compose for the POC).

**Ollama** exposes any local model (Mistral, Llama 3, Qwen2.5-Coder) via HTTP with no setup overhead. Qwen2.5-Coder-32B is the best choice for the coder agent if VRAM allows; Llama 3.1 8B handles intent classification well.

**Qdrant** is the vector store for RAG over architecture standards, past project patterns, and documentation — prevents hallucination on platform-specific questions.

---

## Repo structure

```
platform/
├── docker-compose.yml
├── standards/          # Architecture YAML rules
│   ├── patterns.yaml
│   ├── security.yaml
│   └── naming.yaml
├── orchestrator/       # FastAPI + LangGraph
├── agents/
│   ├── coder/
│   ├── infra/
│   └── review/
├── bots/
│   └── telegram/
└── infra/              # Traefik config, Gitea setup
```
