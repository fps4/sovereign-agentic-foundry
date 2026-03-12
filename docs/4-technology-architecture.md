# Foundation Platform — Technology Architecture

**Version:** 0.1 (Draft)
**Date:** 2026-03-12
**Status:** For discussion

---

## Guiding Constraints

- Every component must have a viable open-source implementation — no proprietary lock-in at any layer
- All infrastructure runs on EU-sovereign cloud; no data leaves Dutch/EU jurisdiction
- Components are replaceable: no application code may hard-depend on a specific vendor's API
- Architecture and agent behavior are governed by versioned platform standards profiles
- POC runs on Docker Compose; production runs on Kubernetes (Helm-managed)

---

## Platform Standards Layer

The Platform Standards Layer is a control plane for architecture principles and agent guidance.

It defines:

- architecture principles (required patterns, banned patterns, component guardrails)
- agent operating guidelines (confirmation requirements, masking rules, escalation rules)
- environment profiles (POC vs production)
- application templates with prepared prompt scaffolds
- versioned policy bundles used by all agent sessions

Enforcement points:

- at planning time: agent cannot produce plans that violate active standards profile
- at tool call time: MCP gateway rejects disallowed operations
- at audit time: each major action records the standards profile version that governed it

Core standards-layer capabilities:

- **Standards Registry** — stores versioned principles, rules, and policy bundles
- **Template Registry** — stores versioned app templates (one-page app, analytics app, intake app)
- **Prompt Pack Store** — curated prompt scaffolds mapped to templates and profiles
- **Constraint Evaluator** — validates plans/tool calls against standards and template rules

POC profile enables only the `one-page-workflow-app` template and its associated prompt pack.

---

## Component Stack

| Layer | Component | Alternative |
|---|---|---|
| Container orchestration | Kubernetes (k3s for small, full k8s for large) | — |
| Service mesh | Istio | Linkerd |
| CNI / network policy | Cilium | Calico |
| Ingress | Nginx / Envoy | Traefik |
| Standards layer | Standards registry + policy bundle engine | Git-based standards catalog only (POC) |
| Template system | Template registry + prompt packs | Static template files only (POC) |
| FHIR server | HAPI FHIR R4 | Firely Server (commercial) |
| Identity | Keycloak | — |
| Secrets | OpenBao (Vault fork) | HashiCorp Vault |
| Object storage | MinIO | Ceph RadosGW |
| Block storage | Rook-Ceph | Longhorn |
| Relational DB | PostgreSQL + pgvector | — |
| Vector store | Qdrant | Weaviate |
| Message queue | NATS JetStream | Apache Kafka |
| LLM serving | vLLM | Ollama (POC / small) |
| Embedding models | multilingual-e5-large | all-MiniLM |
| Source control | Gitea | — |
| CI/CD | ArgoCD + Tekton | Flux |
| Observability | Prometheus + Grafana + Loki + Tempo | — |
| Policy enforcement | OPA / Kyverno | — |
| Runtime security | Falco | — |
| Workflow engine | Flowable / Camunda Community | — |
| MCP SDK | Anthropic MCP Python/TS SDK | — |

---

## LLM Strategy

The LLM backend is pluggable — swappable without changing the agent or MCP layer. The agent communicates with an OpenAI-compatible inference endpoint; the underlying model is a configuration choice.

**POC default:** `mistral-7b-instruct` via Ollama — good Dutch language support, runs on CPU (slow) or GPU (fast), fully open weights.

**Production candidates** (to be benchmarked before selection):
- `mistral-nemo-instruct` — stronger reasoning, still compact
- `llama-3.1-8b-instruct` — Apache 2.0 license, strong general performance
- `medalpaca-13b` / `openbiollm` — healthcare-specific (evaluate Dutch quality)

**Embeddings:** `multilingual-e5-large` for RAG (Dutch + English).

**External models (opt-in only):** Anthropic Claude or OpenAI GPT-4o may be used for tasks with no patient data in context (e.g., UI layout generation, code explanation). Patient data is never sent to external models.

---

## Security Architecture

### Zero-Trust Network

```
Internet → Ingress (TLS termination)
         → Agent Gateway (JWT validation)
         → MCP Gateway (scoped OAuth tokens)
         → Service Mesh (Istio mTLS between all pods)
         → Services (policy-enforced)
```

No service trusts any other service implicitly. All inter-service calls carry a short-lived JWT with explicit scope. Istio enforces mTLS; plain HTTP between pods is blocked by policy at the service mesh level.

### Secrets Management (OpenBao)

No secrets in code or environment variables. All secrets injected at runtime via OpenBao (Vault-compatible).

```yaml
# Example: FHIR server database credentials
vault_path: secret/tenant-hospital-a/fhir-server
keys:
  - db_password       # rotated every 90 days, automatic
  - db_username
  - fhir_client_secret
  - smtp_password
```

Agent-generated application code uses Vault agent sidecar injection. The agent produces only Vault path references — never actual secret values.

### Encryption Key Hierarchy

```
Platform Root Key (OpenBao-managed; HSM-backed in production — see doc 5)
└── Tenant Master Key (one per org, rotatable)
    ├── Database Encryption Key
    ├── Object Storage Key
    ├── Audit Log Signing Key
    └── Application Secrets Key
```

Tenant master keys are derived on first tenant provisioning. Platform operators cannot decrypt tenant data without the tenant's explicit participation (break-glass key ceremony).

### Audit Log Integrity

```
Event written → SHA-256 hash chained to previous event hash
             → Signed with tenant audit signing key
             → Written to append-only log storage
             → Periodically checkpointed to immutable archive (WORM)
```

The `audit-mcp` server is the sole write path for audit events. Agents can query logs but cannot create or modify audit records.

---

## Deployment

### POC — Docker Compose

Single Docker Compose stack for rapid iteration without Kubernetes overhead.

```
docker-compose.yml
├── agent-gateway        (Nginx)
├── agent-runner         (LLM + MCP client)
├── mcp-gateway          (MCP router)
├── fhir-mcp             (FHIR MCP server)
├── auth-mcp             (Auth MCP server)
├── audit-mcp            (Audit MCP server)
├── hapi-fhir            (FHIR R4 server)
├── keycloak             (Identity)
├── postgres             (Database)
├── minio                (Object storage)
├── ollama               (LLM serving — Mistral 7B)
└── qdrant               (Vector store)
```

Single command start: `docker compose up`. No real patient data; synthetic Zib-profiled test data only.

### Production — Kubernetes (Helm)

Platform is delivered as a managed service. Infrastructure is operated by the platform team; tenants access it via the agent UI and MCP endpoints.

```
helm/foundation-platform/
├── charts/
│   ├── core/        (ingress, cert-manager, vault, keycloak, monitoring)
│   └── tenant/      (per-tenant: FHIR server, postgres, minio, gitea)
└── values.yaml      (environment-specific overrides)
```

Tenant provisioning: Helm `tenant/` chart + provisioning script. Kubernetes Operator deferred to Phase 2.

For hosting provider options, HA targets, backup/DR, and capacity planning see `5-production-considerations.md`.

### GitOps + AgentOps Implementation Pattern

Every generated app is managed through repository-first operations.

Example repository layout:

```
repos/{tenant}/{app}/
├── app/                  # application code
├── deploy/               # Helm/Kustomize manifests
├── pipelines/            # CI pipeline definitions
├── standards/            # applied profile + template metadata
└── runbooks/             # approved low-risk remediation actions
```

Delivery flow:

- Agent writes changes to branch and opens PR
- CI executes required checks
- Protected branch merge triggers ArgoCD sync
- Deployment metadata is linked to commit SHA and standards/template versions

Observability and remediation flow:

- Prometheus/Loki/Tempo signals are evaluated against alert rules
- Agent receives alert context and classifies incident risk
- Low-risk incidents can execute approved runbooks
- High-risk incidents require explicit user/admin approval

---

## MCP Extension Points

Third-party MCP servers can be registered in the platform's MCP Gateway:
- Must pass security review (sandboxed, audited, scoped)
- Must declare data classifications for all tool inputs/outputs
- Tenant admins opt in to installing extension MCP servers per tenant
