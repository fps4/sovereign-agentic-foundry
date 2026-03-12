# Foundation Platform — POC

**Version:** 0.2 (Draft)  
**Date:** 2026-03-12  
**Status:** POC definition with implementation assumptions

---

## Purpose

Validate that non-IT healthcare teams can describe a workflow in natural language and receive a working application flow that is compliant by design through platform primitives.

This POC is a technical and product validation step, not a market rollout.

---

## Primary Use Case

### Self-Service User Authorization + Intake Form

A user at a VVT organization authenticates and completes a simple self-service intake form for a new care request.

Using the platform agent, they should be able to:

- generate a one-page self-service app with sign-in and intake
- apply user authorization before form access
- generate intake and consent form fields
- capture structured intake data in FHIR resources
- maintain an access and audit trail by default

Expected outcome: a working one-page self-service authorization and intake flow with enforceable identity, consent checks, and auditable events, built without custom infrastructure work.

---

## Scope

### In Scope

- Agent-assisted application building flow (chat + tool orchestration)
- Platform Standards Layer for architecture principles and agent operating guidelines
- One platform application template with prepared prompts: `one-page-workflow-app`
- MCP gateway with core domain services for:
  - FHIR access
  - authentication and identity
  - storage
  - audit logging
  - forms
- Docker Compose deployment for rapid iteration
- Synthetic Dutch patient data only (no real BSNs or production clinical data)
- Baseline policy checks for access control and consent-aware operations

### Out of Scope

- Multi-tenant production hardening
- Full DigiD/UZI production integration and certification workflows
- Large-scale performance benchmarking
- Formal ISO/NEN certification
- Commercial packaging and subscription operations

---

## Assumptions Adopted for Coding Start

These assumptions are intentionally fixed for the POC to reduce design churn.

### Product and Flow

- POC uses only `one-page-workflow-app`
- POC flow is only self-service authorization + intake form
- Demo includes happy path + failed authorization path

### Auth and Roles

- Auth provider: Keycloak with local POC users
- DigiD/UZI are mocked (interface-compatible, no production integration)
- Roles: `end-user`, `coordinator`, `admin`
- Role matrix is enforced for sign-in, form access, submit, and record view

### Data Contract

- Minimal intake fields are fixed in a versioned schema
- Consent text and flags are fixed in POC profile
- First FHIR mapping includes: `Patient`, `Consent`, `Questionnaire`, `QuestionnaireResponse`

### Standards and Templates

- Standards profile: `poc-default@v0.1`
- Template version: `one-page-workflow-app@v0.1`
- Prompt pack version is pinned and traceable in generated artifacts
- Allowed high-level tool sequence: auth -> form render -> submit -> audit

### GitOps and Runtime

- Each generated app is stored in a dedicated Git repository (`app/`, `deploy/`, `pipelines/`, `standards/`, `runbooks/`)
- Delivery path is PR-based only: branch -> checks -> merge -> deploy
- No direct runtime patching by agent outside approved runbooks

### Observability and AgentOps

- Baseline signals: logs, metrics, traces
- Alert channels: in-app + email
- Low-risk runbooks can auto-execute (restart/rollback/scale within limits)
- High-risk actions always require explicit approval

---

## Pre-Coding Deliverables (Minimum Set)

- `poc-default` standards profile `v0.1`
- `one-page-workflow-app` template spec `v0.1`
- prompt pack with required parameter schema
- intake field definition + FHIR mapping table
- authorization matrix (roles x actions)
- audit event list (event, trigger, required metadata)
- generated-app repository/pipeline baseline
- observability baseline and alert rules
- approved low-risk runbooks + escalation policy
- POC demo script (happy path + negative auth path)

---

## Design

### POC Architecture

1. **User Interaction Layer**  
   Web/CLI interface, with optional Telegram/WhatsApp integration path, where a user describes required behavior.

2. **Agent Layer**  
   LLM-based agent interprets intent and calls platform capabilities through MCP.

3. **Platform Standards Layer**  
   Versioned standards profile loaded by the agent and gateway, including architecture constraints and safety rules.

4. **MCP Gateway + Core MCP Services**  
   Core services include FHIR, auth, storage, audit, and forms.

5. **Platform Services**  
   PostgreSQL, object storage, auth provider, and observability components required to operate the flow.

6. **Deployment Substrate**  
   Docker Compose for POC execution and demos.

### Where User Code Runs

- **POC:** user-generated code runs as application services in the platform-managed Docker Compose runtime.
- **Future production:** user-generated code runs in tenant-isolated Kubernetes namespaces, deployed via GitOps.

### Compliance-by-Design in POC

Platform services enforce:

- encryption and protected data handling defaults
- identity and role checks on sensitive operations
- consent-aware access pathways
- immutable, queryable audit records

Application builders consume these controls as built-in capabilities rather than implementing them from scratch.

---

## Success Criteria

- self-service authorization + intake use case executes end-to-end
- `one-page-workflow-app` build completes end-to-end from template prompt pack
- standards profile and template versions are recorded in metadata/audit
- generated app is stored in Git and deployed through PR-based pipeline flow
- core intake/consent data is represented in FHIR resources
- consent and access checks apply on critical read/write operations
- audit events are captured and inspectable for key actions
- simulated failure triggers alerts and low-risk runbook execution
- non-specialist user can complete a meaningful build session with agent assistance

---

## Notes for Future Production Version

- move from Compose-first runtime to managed EU-sovereign Kubernetes operations
- expand compliance modules and evidence automation for certification
- strengthen tenant isolation controls and production SLO/SLA monitoring
- evaluate analytical data infrastructure (including ClickHouse) as query volume grows
