workspace "Sovereign Agentic Foundry" "Self-hosted AI platform that turns natural-language descriptions into deployed web apps. No external API keys required." {

    model {
        # ── External actors ──────────────────────────────────────────────────
        operator = person "Operator" "Non-engineer who builds and monitors internal apps. Uses the web portal (primary) or Telegram (secondary)." "External"

        telegram = softwareSystem "Telegram" "Cloud messaging platform. Secondary interface for push notifications and quick mobile commands." "External"

        # ── Tenant tier (Generated Applications) ──────────────────────────────
        # Represents the class of apps the platform produces. Not a platform
        # component — an independent deployable artefact scoped to an operator's
        # tenant. In v1 each tenant is single_user; future: team and shared tenants.
        generatedApp = softwareSystem "Generated Application" "Any application produced by the platform. Scoped to an operator's tenant. One or more Docker containers per app. Has its own Gitea repo and CI pipeline. Operators use these directly." "Generated" {

            appContainer = container "App Container" "The primary generated app. FastAPI (Python) or Express (Node). Must expose GET /health and GET /ready. Joined to platform_platform network." "Python/FastAPI or Node/Express" "Generated"

            appDb = container "Per-app Postgres DB" "Dedicated database inside the shared Postgres instance. Provisioned for connector and assistant app types only. Created and destroyed by the infra agent." "PostgreSQL (in shared instance)" "Database"

            appVectorStore = container "Per-app pgvector Container" "Dedicated vector store container. Provisioned for assistant app type only. Started and removed by the infra agent." "pgvector" "Database"
        }

        # ── Sovereign Agentic Foundry (Platform tier) ─────────────────────────
        foundry = softwareSystem "Sovereign Agentic Foundry" "The platform tier. Builds, deploys, monitors, and repairs generated applications. Always running." {

            # ── User-facing ──────────────────────────────────────────────────
            portal = container "Portal" "Primary web interface. Chat, apps dashboard, per-app Kanban board, build history, log viewer. Calls gateway API only." "Next.js 15 / MUI Minimal v7"

            telegramBot = container "Telegram Bot" "Secondary mobile interface. Push notifications and quick commands (/apps, /fix, /help). Routes messages to gateway." "Python / aiogram"

            # ── API layer ─────────────────────────────────────────────────────
            gateway = container "Gateway" "API facade. User registration, app registry, build dispatch, board card writes, agent run logging. No LLM." "Python / FastAPI" {
                pipelineRunner = component "Pipeline Runner"   "run_build() background task; sequences agents; writes board_cards at each stage."
                appRegistry    = component "App Registry"     "CRUD for users and apps tables; enforces soft-delete via archived flag."
                userReg        = component "User Registration" "Creates Gitea org (user-{telegram_id}) and Postgres user row on first message."
                chatRouter     = component "Chat Router"       "POST /chat endpoint; delegates to intake agent; returns spec_locked flag."
                boardManager   = component "Board Manager"     "Owns board_cards writes; creates and moves cards at each pipeline stage."
                issueIngest    = component "Issue Ingestor"    "POST /report-issue; deduplicates errors by hash; triggers remediation or Gitea issue."
                authModule     = component "Auth Module"       "POST /auth/login; JWT issuance and validation; bcrypt password check."
            }

            # ── Agents (LLM-driven) ───────────────────────────────────────────
            intake = container "Intake Agent" "Multi-turn clarification conversation. Converges on a locked spec and hands off to the gateway." "Python / FastAPI" {
                convFSM  = component "Conversation FSM"  "Tracks clarification state in Postgres messages table."
                specProd = component "Spec Producer"     "Validates and serialises the final spec; signals spec_locked to gateway."
            }

            planner = container "Planner Agent" "Takes a locked spec and produces a build plan: file list, patterns, stack decisions, resource requirements." "Python / FastAPI"

            builder = container "Builder Agent" "Executes the build plan; generates all application code files. No architectural decisions." "Python / FastAPI" {
                generator    = component "Generator"        "LLM-driven file generation in JSON mode; falls back to hardcoded templates on parse failure."
                routeExtract = component "Route Extractor"  "Derives route manifest from generated files for the ui-designer."
            }

            uiDesigner = container "UI Designer Agent" "Generates styled, accessible frontend templates from the spec and route manifest." "Python / FastAPI"

            reviewer = container "Reviewer Agent" "Checks generated files against platform standards before commit. Returns pass or fix instructions." "Python / FastAPI" {
                staticChecker = component "Static Checker"   "Rule-based checks from standards YAML: naming, forbidden patterns, required headers."
                llmReviewer   = component "LLM Reviewer"     "Semantic review for issues not caught by static rules."
                fixFormatter  = component "Fix Formatter"    "Structures findings into {file, issue, fix_instruction} for the builder."
            }

            testWriter = container "Test-writer Agent" "Generates pytest files from application source. Invoked as a Woodpecker CI step." "Python / FastAPI"

            acceptance = container "Acceptance Agent" "Post-deploy smoke check: exercises live app routes against the spec. Triggers remediation on failure." "Python / FastAPI"

            remediation = container "Remediation Agent" "Analyses failures; drives a targeted patch rebuild; escalates when retries are exhausted." "Python / FastAPI"

            # ── Services (deterministic, no LLM) ─────────────────────────────
            publisher = container "Publisher" "Commits generated files to Gitea, creates repos, activates Woodpecker pipelines via HMAC webhook." "Python / FastAPI"

            infra = container "Infra Agent" "Provisions per-app external resources (Postgres DB, pgvector). Injects secrets. Handles teardown on app deletion." "Python / FastAPI"

            watchdog = container "Watchdog" "Polls all running app containers via Docker socket. Reports errors to gateway. No HTTP server." "Python (no HTTP)"

            traefik = container "Traefik" "Reverse proxy. Routes *.APP_DOMAIN to both platform services and generated app containers via dynamic Docker labels." "Traefik v3" "Infra"

            # ── Data stores ──────────────────────────────────────────────────
            postgres = container "PostgreSQL" "Shared DB. platform DB: users, apps, messages, agent_runs, app_issues, board_cards. woodpecker DB: CI state. Per-app DBs: one per connector/assistant app." "PostgreSQL 16" "Database"

            ollama = container "Ollama" "Local LLM inference for all agents. Default model: llama3.1:8b. No external API keys required." "Ollama" "Infra"

            # ── Source control & CI ──────────────────────────────────────────
            gitea = container "Gitea" "Self-hosted Git. One private org per user (user-{telegram_id}), one repo per app." "Gitea" "Infra"

            woodpeckerServer = container "Woodpecker Server" "CI server. Manages pipeline execution. Receives HMAC-signed webhooks from Gitea." "Woodpecker CI v3" "Infra"

            woodpeckerAgent = container "Woodpecker Agent" "CI runner. Executes pipeline steps (generate-tests, test, docker-build, deploy) in Docker containers on the platform network." "Woodpecker CI v3" "Infra"

            # ── Observability ────────────────────────────────────────────────
            promtail = container "Promtail" "Collects stdout/stderr from all Docker containers (platform and app tier) and ships to Loki." "Grafana Promtail" "Observability"
            loki     = container "Loki"     "Log aggregation store. Queried by the gateway for portal log tail." "Grafana Loki" "Observability"
            grafana  = container "Grafana"  "Observability dashboard. Data sources: Loki and Postgres." "Grafana" "Observability"
        }

        # ── Relationships: operator ───────────────────────────────────────────
        operator -> portal         "Uses (primary interface)"
        operator -> telegramBot    "Uses (secondary, mobile)"
        operator -> generatedApp   "Uses deployed internal tools" "HTTP (browser)"
        telegramBot -> telegram    "Sends replies and push notifications" "Telegram Bot API"
        telegram    -> telegramBot "Delivers updates via long-polling"

        # ── Relationships: interfaces → gateway ──────────────────────────────
        portal      -> gateway "All API calls (chat, apps, Kanban, auth)" "HTTP/JSON"
        telegramBot -> gateway "POST /chat, /register, /apps, /delete-app, /report-issue" "HTTP/JSON"

        # ── Relationships: gateway → agents (build pipeline) ─────────────────
        gateway -> intake      "POST /intake"                  "HTTP/JSON"
        gateway -> infra       "POST /provision (conditional)" "HTTP/JSON"
        gateway -> planner     "POST /plan"                    "HTTP/JSON"
        gateway -> builder     "POST /build"                   "HTTP/JSON"
        gateway -> uiDesigner  "POST /design-ui"               "HTTP/JSON"
        gateway -> reviewer    "POST /review"                  "HTTP/JSON"
        gateway -> publisher   "POST /publish"                 "HTTP/JSON"
        gateway -> acceptance  "POST /accept"                  "HTTP/JSON"
        gateway -> remediation "POST /remediate"               "HTTP/JSON"
        gateway -> infra       "POST /teardown (on delete)"    "HTTP/JSON"

        # ── Relationships: remediation sub-pipeline ──────────────────────────
        remediation -> planner   "POST /plan (patch)"    "HTTP/JSON"
        remediation -> builder   "POST /build (patch)"   "HTTP/JSON"
        remediation -> reviewer  "POST /review (patch)"  "HTTP/JSON"
        remediation -> publisher "POST /publish (patch)" "HTTP/JSON"

        # ── Relationships: agents → LLM ──────────────────────────────────────
        intake      -> ollama "LLM clarification and spec extraction" "HTTP/JSON"
        planner     -> ollama "LLM plan generation"                   "HTTP/JSON"
        builder     -> ollama "LLM code generation"                   "HTTP/JSON"
        uiDesigner  -> ollama "LLM template generation"               "HTTP/JSON"
        reviewer    -> ollama "LLM semantic review"                   "HTTP/JSON"
        testWriter  -> ollama "LLM test generation"                   "HTTP/JSON"
        watchdog    -> ollama "LLM log summarisation"                 "HTTP/JSON"
        remediation -> ollama "LLM error analysis"                    "HTTP/JSON"

        # ── Relationships: publisher → Git/CI ────────────────────────────────
        publisher -> gitea            "Create repo, commit generated files"   "HTTPS"
        publisher -> woodpeckerServer "HMAC-signed activation webhook"        "HTTP"
        publisher -> postgres         "Woodpecker repo activation (direct write to woodpecker DB)" "SQL"

        # ── Relationships: CI pipeline ───────────────────────────────────────
        gitea            -> woodpeckerServer "Webhook on push"                     "HTTP"
        woodpeckerServer -> woodpeckerAgent  "Dispatch pipeline run"               "Internal"
        woodpeckerAgent  -> testWriter       "POST /generate (generate-tests step)" "HTTP/JSON"
        woodpeckerAgent  -> appContainer     "docker build + docker run (deploy step)" "Docker"

        # ── Relationships: platform → application tier (runtime) ─────────────
        traefik      -> appContainer   "Routes {name}.APP_DOMAIN requests (Docker label discovery)" "HTTP"
        acceptance   -> appContainer   "GET /health, GET /ready, route smoke checks" "HTTP"
        watchdog     -> appContainer   "Polls logs and health state (read-only)" "Docker socket"
        infra        -> appDb          "Creates DB and user; drops on teardown" "SQL (admin)"
        infra        -> appVectorStore "Starts container; removes on teardown" "Docker"

        # ── Relationships: app tier internal ─────────────────────────────────
        appContainer -> appDb          "Reads and writes application data" "SQL (via DATABASE_URL)"
        appContainer -> appVectorStore "Embedding storage and similarity search" "pgvector protocol"

        # ── Relationships: monitoring ─────────────────────────────────────────
        watchdog -> gateway "POST /apps/{name}/report-issue" "HTTP/JSON"

        # ── Relationships: infra agent ────────────────────────────────────────
        infra -> postgres "Create and drop per-app databases (admin connection)" "SQL"
        infra -> gitea    "Write .env.platform with injected secrets"            "HTTPS"

        # ── Relationships: agent → source control ────────────────────────────
        testWriter  -> gitea "Fetch app source files (generate-tests step)" "HTTPS"
        remediation -> gitea "Fetch current source for repair context"       "HTTPS"

        # ── Relationships: data ───────────────────────────────────────────────
        gateway     -> postgres "Read/write users, apps, messages, agent_runs, app_issues, board_cards" "SQL"
        intake      -> postgres "Read/write messages (conversation history)" "SQL"
        telegramBot -> postgres "Read/write aiogram FSM state"               "SQL"
        gateway     -> loki     "Proxy log queries for portal /apps/{id}/logs" "HTTP"

        # ── Relationships: observability ─────────────────────────────────────
        promtail -> loki    "Ship log streams (platform + app tier containers)"
        grafana  -> loki    "Query logs"
        grafana  -> postgres "Query platform metrics"

        # ── Gateway component relationships ──────────────────────────────────
        chatRouter     -> convFSM      "Triggers intake conversation"
        pipelineRunner -> boardManager "Writes board cards at each pipeline stage"
        pipelineRunner -> appRegistry  "Reads/writes app records"
        pipelineRunner -> userReg      "Registers new users"
        issueIngest    -> boardManager "Creates board card on breaking error"
        authModule     -> appRegistry  "Looks up user by email"

        # ── Intake component relationships ────────────────────────────────────
        convFSM  -> postgres "Persist/load message history"

        # ── Builder component relationships ───────────────────────────────────
        generator    -> ollama "LLM file generation"

        # ── Reviewer component relationships ──────────────────────────────────
        staticChecker -> llmReviewer  "Passes static findings as context"
        llmReviewer   -> fixFormatter "Raw findings → structured instructions"
    }

    views {
        # ── L1: System Context ────────────────────────────────────────────────
        systemContext foundry "SystemContext" {
            include *
            autoLayout lr
            title "L1 — System Context"
            description "Sovereign Agentic Foundry, the Generated Application it produces, and external actors."
        }

        # ── L2: Platform tier containers ──────────────────────────────────────
        container foundry "PlatformContainers" {
            include *
            autoLayout lr
            title "L2 — Platform Tier"
            description "All containers inside the platform and their primary interactions."
        }

        # ── L2: Tenant tier containers ────────────────────────────────────────
        container generatedApp "TenantTierContainers" {
            include *
            autoLayout lr
            title "L2 — Tenant Tier"
            description "Structure of a generated application (tenant tier). appDb and appVectorStore are conditional on app type. Each app is scoped to an operator's tenant."
        }

        # ── L3: Gateway components ────────────────────────────────────────────
        component gateway "GatewayComponents" {
            include *
            autoLayout tb
            title "L3 — Gateway Components"
            description "Internal structure of the Gateway container."
        }

        # ── L3: Builder components ────────────────────────────────────────────
        component builder "BuilderComponents" {
            include *
            autoLayout tb
            title "L3 — Builder Agent Components"
            description "Internal structure of the Builder agent."
        }

        # ── L3: Reviewer components ───────────────────────────────────────────
        component reviewer "ReviewerComponents" {
            include *
            autoLayout tb
            title "L3 — Reviewer Agent Components"
            description "Internal structure of the Reviewer agent."
        }

        # ── L3: Intake components ─────────────────────────────────────────────
        component intake "IntakeComponents" {
            include *
            autoLayout tb
            title "L3 — Intake Agent Components"
            description "Internal structure of the Intake agent."
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
            element "Generated" {
                background #2e7d32
                color #ffffff
            }
        }
    }
}
