# Agent Pipeline Design

The platform builds applications through a pipeline of specialised agents. No human approval gates exist once the designer is satisfied with the spec — the pipeline runs fully automatically from that point.

---

## Pipeline

```
User (Telegram)
  ↕  multi-turn conversation
Designer agent
  → creates Gitea repo with design doc + issue(s)
  ↓  Gitea webhook on issue creation
Coder agent
  → implements, commits to branch, opens PR
  ↓  Woodpecker CI triggered on PR
Tester agent
  → reads source from repo, writes tests, commits to branch
  → CI runs tests — must pass to proceed
  ↓  tests green
Security scan (Phase 4)
  → Semgrep + Trivy gate
  ↓  scan clean
Deploy
  → Woodpecker merges PR, builds image, runs container with Traefik labels
  ↓  app live
Monitor agent
  → polls containers, detects errors, calls orchestrator report-issue endpoint
  → orchestrator creates Gitea issue on the app repo → coder picks it up
```

---

## Agent responsibilities

### Designer
- Holds a multi-turn conversation with the user until the spec is unambiguous
- Creates the Gitea repo (empty shell) in the user's org
- Commits a `DESIGN.md` — app type, stack, requirements, acceptance criteria, data model sketch
- Opens one or more Gitea issues tagged `task` with structured implementation instructions
- Hands off automatically once issues are created — no user confirmation gate

### Coder
- Triggered by a Gitea webhook when a `task` issue is opened or assigned
- Reads the issue body and `DESIGN.md` from the repo
- Scaffolds or modifies files, commits to a feature branch, opens a PR
- Updates issue status to `in progress` / closes it on merge

### Tester
- Triggered by a Woodpecker pipeline step after the coder's commit
- Reads the source files from the repo
- Generates `tests/` using the LLM, guided by the tester agent standards
- Commits tests to the same branch
- CI re-runs; tests must pass before the pipeline continues
- On failure: creates a `test-failure` Gitea issue → coder picks it up for a fix iteration

### Monitor
- Polls all running platform containers continuously
- Detects errors (log errors) and breaking state (container down/unhealthy)
- Reports to the orchestrator's `/apps/{name}/report-issue` endpoint
- Orchestrator: deduplicates, creates Gitea issue on the app repo, updates app status, notifies user once per unique error

---

## Handoff artefacts

| From | To | Artefact |
|---|---|---|
| User conversation | Designer | Clarified intent (in memory) |
| Designer | Coder | Gitea repo + `DESIGN.md` + `task` issue(s) |
| Coder | Tester | Committed source code on feature branch |
| Tester | CI | Test files committed; pipeline gate |
| CI | Deploy | Green build → image pushed, container started |
| Monitor | Coder | Gitea issue on app repo (`monitor` label) |

---

## Where the workflow is defined

| Layer | Purpose | Location |
|---|---|---|
| **Pipeline topology** | Stage order, transitions, webhook triggers | LangGraph graph in `orchestrator/` |
| **Agent behaviour** | Reasoning, output format, constraints per agent | `standards/agents/{designer,coder,tester,monitor}.yaml` |
| **Platform standards** | Architecture, security, naming rules (shared by all agents) | `standards/{patterns,security,naming}.yaml` |

The orchestrator's LangGraph graph is the single source of truth for pipeline flow. Each active pipeline run is a checkpointed workflow in Postgres — it can pause on a Gitea webhook, resume when the webhook fires, and survive restarts.

---

## Iteration loop

The pipeline is not linear — it loops:

```
Monitor detects issue
  → Gitea issue created on app repo (label: monitor)
  → Coder triggered (same webhook as task issues)
  → fix committed → Tester → CI → Deploy
  → Monitor confirms issue resolved (container healthy, no more errors)
```

Breaking issues additionally notify the user via Telegram once per unique error.

---

## What this is not

- No user approval gates between stages — the designer is the quality gate
- No manual `/test` or `/deploy` commands — fully automatic after designer handoff
- No external CI service — Woodpecker is self-hosted and the only CI runner

---

## Roadmap

| Phase | What |
|---|---|
| ✅ 1–3 | Conversation loop, standards injection, coder agent (scaffold + deploy) |
| ✅ Current | App registry, status tracking, monitor → report-issue deduplication |
| **Next** | Designer agent (multi-turn spec → repo + issue) replacing the current intent classifier |
| **Next** | Tester agent (LLM test generation as a mandatory Woodpecker step) |
| **Phase 4** | Security scan gate (Semgrep + Trivy) |
| **Phase 5** | Observability + web hub (Prometheus, Grafana, Next.js dashboard) |
