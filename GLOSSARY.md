# Glossary

| Term | Definition |
|------|------------|
| App | A generated project — source code, Dockerfile, CI config — living in a Gitea repo and running as a Docker container. Maps to a row in the `apps` table. |
| App type | The scaffold category the platform generates: `form`, `dashboard`, `workflow`, `connector`, or `assistant`. Determined during designer clarification. |
| Design mode | The FSM state where a user has an active spec-clarification conversation with the designer agent. Stored as `users.design_mode = true`. Cleared when the spec is handed off. |
| Spec | The structured output of the designer agent: `{name, description, app_type, stack, requirements}`. Passed as JSON to the coder agent to drive scaffolding. |
| Standards | YAML rule files in `standards/` (naming, security, patterns) injected into every LLM system prompt. Not a runtime service. |
| Org | A private Gitea organisation created per registered user, named `user-{telegram_id}`. All user repos live inside it. |
| Platform network | The Docker bridge network `platform_platform`. Every platform service and every deployed app container joins this network, enabling hostname-based routing. |
| Woodpecker activation | The process of enabling CI for a repo: a direct insert into Woodpecker's Postgres tables plus a HMAC-signed Gitea webhook. Done programmatically by the orchestrator — no dashboard interaction required. |
| Agent run | A single logged event in the `agent_runs` table: one step in the build pipeline with agent name, status, timing, and payload. |
| Error hash | An MD5 of a normalised error message, used by the monitor agent to deduplicate alerts. The same error is reported to Gitea Issues and Telegram only once. |
| Breaking issue | A monitor-detected failure where `is_breaking = true` in `app_issues`. Triggers a Telegram notification to the app owner and sets app status to `failed`. |
