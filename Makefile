# Sovereign Agentic Foundry — top-level Makefile
#
# Usage (local):
#   make up
#   make down
#   make build svc=portal
#   make logs svc=gateway
#   make test
#
# Usage (remote ds1):
#   make up        HOST=ssh://ds1
#   make deploy    HOST=ssh://ds1  (build + up)
#   make test      HOST=ssh://ds1  GATEWAY_URL=http://ds1  INVITE_CODE=674523
#   make pull-models HOST=ssh://ds1

# ── Variables ──────────────────────────────────────────────────────────────────

# Docker host: 'local' (default) or 'ssh://hostname'
HOST ?= local

# URL the test scripts use to reach the gateway
GATEWAY_URL ?= http://localhost

# Invite code for registration tests (leave empty if INVITE_CODE is unset)
INVITE_CODE ?=

COMPOSE_FILE := infra/docker/docker-compose.yml

ifeq ($(HOST),local)
  DC := docker compose -f $(COMPOSE_FILE) --project-directory .
else
  DC := DOCKER_HOST=$(HOST) docker compose -f $(COMPOSE_FILE) --project-directory .
endif

# ── Core lifecycle ──────────────────────────────────────────────────────────────

.PHONY: up
up:                        ## Start all services (detached)
	$(DC) up -d

.PHONY: down
down:                      ## Stop and remove containers
	$(DC) down

.PHONY: restart
restart:                   ## Restart all (or one: make restart svc=gateway)
	$(DC) restart $(svc)

.PHONY: build
build:                     ## Build images (or one: make build svc=portal)
	$(DC) build $(svc)

.PHONY: deploy
deploy: build up           ## Build then start (full redeploy)

.PHONY: logs
logs:                      ## Tail logs (or one service: make logs svc=gateway)
	$(DC) logs -f $(svc)

.PHONY: ps
ps:                        ## Show running containers
	$(DC) ps

# ── Model management ───────────────────────────────────────────────────────────

.PHONY: pull-models
pull-models:               ## Pull default Ollama models (llama3.1:8b, nomic-embed-text)
ifeq ($(HOST),local)
	bash scripts/pull_models.sh
else
	DOCKER_HOST=$(HOST) bash scripts/pull_models.sh
endif

# ── Tests ──────────────────────────────────────────────────────────────────────

.PHONY: test-registration
test-registration:         ## Run web registration integration tests
	GATEWAY_URL=$(GATEWAY_URL) INVITE_CODE=$(INVITE_CODE) python3 scripts/test_web_registration.py

.PHONY: test-chat
test-chat:                 ## Run chat integration tests
	GATEWAY_URL=$(GATEWAY_URL) INVITE_CODE=$(INVITE_CODE) python3 scripts/test_chat.py

.PHONY: test
test: test-registration test-chat  ## Run all integration tests

# ── Help ───────────────────────────────────────────────────────────────────────

.PHONY: help
help:                      ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
