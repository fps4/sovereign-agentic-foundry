# TODO

## UX

- Improve issue reporting by the monitor agent
- think of app lifecycle management including archival based on retention requirements. Can we take care of that in the background? How to do breaking changes?
- add /examples to show apps in different categories via URLs to view. Those examples will be hosted and owned by the platform
- internal (platform) apps (part of user workspace) for enhanced / simplified user expereince: Apps, Issues, Users, Statistics, etc.

## Extended POC

- **Missing app type templates** — only `form` has a deterministic scaffold. Add proper templates for `dashboard`, `workflow`, `connector`, and `assistant` so the coder agent doesn't fall back to raw LLM generation for every other type.

## Next: multi-agent pipeline

See [docs/agent-pipeline.md](docs/agent-pipeline.md) for the full design.

- **Designer agent** — replace the current one-shot intent classifier with a multi-turn designer that clarifies requirements, creates the Gitea repo, commits `DESIGN.md`, and opens `task` issues. Prompt/guidelines go in `standards/agents/designer.yaml`.
- **Tester agent** — mandatory Woodpecker pipeline step after every coder commit. Reads source from the repo, generates `tests/` with the LLM, commits them, and gates the pipeline. Guidelines in `standards/agents/tester.yaml`.
- **Agent standards directory** — create `standards/agents/` with YAML guidelines for each agent (designer, coder, tester, monitor) that the orchestrator injects into each agent's system prompt.
- **LangGraph pipeline coordination** — evolve the orchestrator's LangGraph graph from a single-turn classifier into a durable, webhook-driven pipeline coordinator. Each stage checkpoints to Postgres; the graph resumes on Gitea webhooks.
