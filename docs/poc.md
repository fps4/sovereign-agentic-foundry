---
prompt: 
    i'd like to build an agentic platform that can build applications (based on architecture principles, patterns, standards) for the users on the sovereign infrastructure (self-hosted or vendor-neutral). All the components must be open-source where possible.

    How should I approach this task? Can you draft POC design for that. Users will collaborate via Telegram (or Whatsapp, later with mobile app) or later with web app that also shows application status and alerts etc like a hub. 

    On the background POC should be possible to run on my docker host
---
This is a meaty challenge — essentially building an "AI DevOps co-pilot" on sovereign infrastructure. Let me sketch out the full architecture first, then show a POC design you can actually run on Docker.

The core idea: users describe what they want via Telegram → an orchestration layer interprets intent against your architecture standards → agents plan and execute the build → results and status stream back to the user.

Here's the [high-level system design](./diagrams/high-level-system-design.png)

Now let's zoom into the [orchestration brain](./diagrams/orchestration.png) — this is the most complex part, where intent becomes action.

And here's the full POC stack mapped to [Docker Compose services](./diagrams/services.png).

Here's how to approach the build, broken into phases:

---

**Phase 1 — Skeleton**

Start with just the conversation loop. Telegram bot → FastAPI orchestrator → Ollama (local LLM) → reply. No agents yet, just prove the messaging pipeline works and that the LLM can classify intent and respond sensibly. One `docker-compose.yml` with: `traefik`, `telegram-bot`, `orchestrator`, `ollama`, `postgres`.

**Phase 2 — Architecture standards**

Add a `standards/` directory of YAML files that define your patterns: naming conventions, required labels, allowed base images, mandatory sidecar patterns, etc. The orchestrator loads these at startup and injects them into every LLM system prompt. This is your "opinionated layer" — the thing that makes it *your* platform, not a generic AI assistant.

**Phase 3 — First agent**

Add the coder-agent. It receives a task spec (structured JSON from the orchestrator), uses the LLM + Aider/CodeAct to scaffold a repo, commits to Gitea, and sends the PR link back to the user via Telegram. Wire up Woodpecker CI so the push triggers a build automatically.

**Phase 4 — Infra + review agents**

Add OpenTofu for infra provisioning and Semgrep/Trivy for the review gate. Nothing gets committed unless the review agent approves. Status updates should stream back to the user during long-running operations ("⏳ building... ✅ tests passed... 🚀 deploying").

**Phase 5 — Observability and web hub**

Add Prometheus + Grafana for the platform itself, and a minimal Next.js dashboard that shows active jobs, deployment history, and alerts — the "hub" view for the future mobile/web app.

---

**Key design decisions for the POC:**

The LangGraph workflow engine is the right choice for the orchestrator because it models agent execution as a directed graph with state — you can pause, checkpoint, and resume workflows, which is essential when a deploy takes 5 minutes and the user wants updates. Store workflow state in PostgreSQL so nothing is lost on restart.

Gitea is the SCM rather than a cloud provider because it's fully self-hosted, has a solid API, and Woodpecker CI is purpose-built to work with it. ArgoCD can watch Gitea for GitOps-style deployments to K3s (or plain Docker Compose for the POC).

Ollama makes the LLM setup trivial on a single Docker host — you pull a model (Mistral, Llama 3, Qwen2.5-coder) and it's available via HTTP. For the coder agent, a code-specialized model like Qwen2.5-Coder-32B makes a big difference if you have the VRAM. Otherwise Llama 3.1 8B works surprisingly well for intent classification and planning.

Qdrant gives you the vector store for RAG over your architecture standards, past project patterns, and documentation. This is what lets the LLM answer "how do we usually do authentication?" without hallucinating.

---

**Repo structure suggestion:**

```
platform/
├── docker-compose.yml
├── standards/          # Your architecture YAML rules
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

Want me to draft the `docker-compose.yml` for Phase 1, or go deeper on any particular component — like the LangGraph workflow definition, the standards YAML schema, or the Telegram bot handler?