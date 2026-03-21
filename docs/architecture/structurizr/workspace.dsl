workspace "Sovereign Agentic Foundry" "Self-hosted AI platform that turns natural-language Telegram messages into deployed web apps." {

    model {
        # ── External actors ──────────────────────────────────────────────────
        operator = person "Operator" "Registers apps and monitors deployments via Telegram. The only human in the loop." "External"

        telegram = softwareSystem "Telegram" "Cloud messaging platform. The sole UI surface for the operator." "External"

        # ── Sovereign Agentic Foundry ─────────────────────────────────────────
        foundry = softwareSystem "Sovereign Agentic Foundry" "Turns natural-language app descriptions into fully deployed, CI-tested web applications with no human approval gates." {

            # ── User-facing ──────────────────────────────────────────────────
            telegramBot = container "Telegram Bot" "Receives operator messages via aiogram long-polling. Maintains Telegram FSM state in Postgres. Forwards all messages to Orchestrator." "Python / aiogram"

            # ── Platform core ────────────────────────────────────────────────
            orchestrator = container "Orchestrator" "API gateway. Classifies intent, registers users, maintains app registry, dispatches builds, and receives monitor issue reports. Implements a LangGraph state machine." "Python / FastAPI / LangGraph" {
                workflow   = component "LangGraph Workflow"   "Multi-step state machine: classify → route → build → notify."
                appRegistry = component "App Registry"        "CRUD for the apps table; enforces soft-delete via archived flag."
                userReg    = component "User Registration"    "Creates Gitea org (user-{telegram_id}) and Postgres user row on first message."
                chatRouter = component "Chat Router"          "POST /chat endpoint; always delegates to Designer agent."
                issueIngest = component "Issue Ingestor"      "POST /report-issue; deduplicates errors, opens Gitea issue, sends Telegram alert."
            }

            designer = container "Designer Agent" "Runs a multi-turn clarification conversation until the spec is unambiguous, then signals orchestrator to begin a build." "Python / FastAPI" {
                convFSM  = component "Conversation FSM"  "Tracks clarification state in Postgres. Produces a structured JSON spec."
                specProd = component "Spec Producer"     "Validates and serialises the final spec; triggers build handoff."
            }

            coder = container "Coder Agent" "Scaffolds project files via Ollama JSON mode, runs local tests, commits to Gitea, and creates the Woodpecker pipeline config." "Python / FastAPI" {
                scaffolder  = component "Scaffolder"      "LLM-driven file generation; falls back to hardcoded templates on parse error."
                localTester = component "Local Tester"    "Runs pytest in-process before any Git push."
                giteaOps    = component "Gitea Client"    "Creates repo, branches, and pushes commits to the user's private org."
                pipelineCfg = component "Pipeline Config" "Emits .woodpecker.yml with generate-tests → test → docker-build → deploy steps."
            }

            tester = container "Tester Agent" "Generates pytest test files from scaffolded source. Invoked exclusively as a Woodpecker CI step, not by the orchestrator." "Python / FastAPI"

            monitor = container "Monitor Agent" "Polls all running app containers via Docker socket. Hashes unique errors and reports each once to Orchestrator /report-issue." "Python (no HTTP server)"

            traefik = container "Traefik" "Reverse proxy. Routes *.APP_DOMAIN to deployed app containers via dynamic Docker label discovery." "Traefik v3" "Infra"

            # ── Data stores ──────────────────────────────────────────────────
            postgres = container "PostgreSQL" "Shared database. 'platform' DB: users, apps, messages, agent_runs. 'woodpecker' DB: CI pipeline state." "PostgreSQL 16" "Database"

            ollama = container "Ollama" "Local LLM inference. Default model: llama3.1:8b. No external API keys required." "Ollama" "Infra"

            # ── Source control & CI ──────────────────────────────────────────
            gitea = container "Gitea" "Self-hosted Git. One private org per user (user-{telegram_id}), one repo per app." "Gitea" "Infra"

            woodpeckerServer = container "Woodpecker Server" "CI orchestrator. Receives HMAC-signed webhooks from Gitea and manages pipeline runs." "Woodpecker CI v3" "Infra"

            woodpeckerAgent  = container "Woodpecker Agent"  "CI runner. Executes pipeline steps (generate-tests, test, docker-build, deploy) inside Docker containers on the platform network." "Woodpecker CI v3" "Infra"

            # ── Observability ────────────────────────────────────────────────
            promtail = container "Promtail"  "Collects stdout/stderr from all Docker containers and ships to Loki." "Grafana Promtail" "Observability"
            loki     = container "Loki"      "Log aggregation store." "Grafana Loki" "Observability"
            grafana  = container "Grafana"   "Observability dashboard. Data sources: Loki and Postgres." "Grafana" "Observability"
        }

        # ── Relationships: external ───────────────────────────────────────────
        operator  -> telegram       "Sends messages / receives notifications"
        telegram  -> telegramBot    "Delivers updates via long-polling"
        telegramBot -> telegram     "Sends replies and alerts to operator"

        # ── Relationships: request path ───────────────────────────────────────
        telegramBot     -> orchestrator     "POST /chat"                            "HTTP/JSON"
        orchestrator    -> designer         "POST /chat (clarification loop)"       "HTTP/JSON"
        designer        -> orchestrator     "Spec complete — trigger build"         "HTTP/JSON"
        orchestrator    -> coder            "POST /build {spec}"                    "HTTP/JSON"
        coder           -> ollama           "Structured JSON generation"            "HTTP/JSON"
        coder           -> gitea            "Push scaffolded repo"                  "HTTP Git"
        gitea           -> woodpeckerServer "HMAC-signed webhook on push"           "HTTP"
        woodpeckerServer -> woodpeckerAgent "Dispatch pipeline"                     "Internal"
        woodpeckerAgent  -> tester          "POST /generate-tests"                  "HTTP/JSON"
        woodpeckerAgent  -> traefik         "Deployed app container (Docker label)" "Docker"

        # ── Relationships: monitoring path ────────────────────────────────────
        monitor -> orchestrator "POST /report-issue {error}"  "HTTP/JSON"

        # ── Relationships: data ───────────────────────────────────────────────
        telegramBot     -> postgres "Read/write FSM state, messages"
        orchestrator    -> postgres "Read/write users, apps, agent_runs"
        designer        -> postgres "Read/write conversation FSM state"

        # ── Relationships: observability ──────────────────────────────────────
        promtail -> loki    "Ship log streams"
        grafana  -> loki    "Query logs"
        grafana  -> postgres "Query platform metrics"

        # ── Orchestrator component relationships ──────────────────────────────
        chatRouter  -> workflow    "Triggers"
        workflow    -> appRegistry "Reads/writes app records"
        workflow    -> userReg     "Registers new users"
        workflow    -> designer    "Delegates conversation"
        workflow    -> coder       "Dispatches build"
        issueIngest -> gitea       "Opens issue"
        issueIngest -> telegram    "Sends Telegram alert"

        # ── Coder component relationships ─────────────────────────────────────
        scaffolder  -> ollama      "LLM generation"
        scaffolder  -> localTester "Run tests before push"
        giteaOps    -> gitea       "Commit and push"
        pipelineCfg -> giteaOps    "Attach .woodpecker.yml to commit"
    }

    views {
        # ── L1: System Context ────────────────────────────────────────────────
        systemContext foundry "SystemContext" {
            include *
            autoLayout lr
            title "L1 — System Context"
            description "Sovereign Agentic Foundry and its external dependencies."
        }

        # ── L2: Container Map ─────────────────────────────────────────────────
        container foundry "Containers" {
            include *
            autoLayout lr
            title "L2 — Container Map"
            description "All containers inside the platform and their primary interactions."
        }

        # ── L3: Orchestrator components ───────────────────────────────────────
        component orchestrator "OrchestratorComponents" {
            include *
            autoLayout tb
            title "L3 — Orchestrator Components"
            description "Internal structure of the Orchestrator container."
        }

        # ── L3: Coder components ──────────────────────────────────────────────
        component coder "CoderComponents" {
            include *
            autoLayout tb
            title "L3 — Coder Agent Components"
            description "Internal structure of the Coder agent."
        }

        # ── L3: Designer components ───────────────────────────────────────────
        component designer "DesignerComponents" {
            include *
            autoLayout tb
            title "L3 — Designer Agent Components"
            description "Internal structure of the Designer agent."
        }

        # ── Styles ────────────────────────────────────────────────────────────
        styles {
            element "Person" {
                shape Person
                background #1168bd
                color #ffffff
            }
            element "External" {
                background #999999
                color #ffffff
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "Component" {
                background #85bbf0
                color #000000
            }
            element "Database" {
                shape Cylinder
                background #438dd5
                color #ffffff
            }
            element "Infra" {
                background #6c757d
                color #ffffff
            }
            element "Observability" {
                background #e07c17
                color #ffffff
            }
        }
    }
}
