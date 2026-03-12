# Foundation Platform — Product Design

**Version:** 0.1 (Draft)
**Date:** 2026-03-11
**Status:** For discussion

---

## Design Principles

1. **Compliance is infrastructure, not code.** Regulatory requirements (encryption, audit, consent, identity) are enforced at the platform level. Application builders cannot accidentally bypass them.

2. **Open source by default.** Every component has a viable open-source implementation. No proprietary lock-in at any layer.

3. **Agent-native architecture.** The AI agent is a first-class citizen, not a wrapper. Platform capabilities are designed to be discovered and invoked by agents via MCP.

4. **Standards-first execution.** The platform maintains a versioned standards layer (architecture principles, implementation guidelines, and agent safety rules) that all agents must apply before taking action.

5. **Tenant isolation is absolute.** No shared state, no cross-tenant data leakage — even in failure conditions.

6. **Well-structured internals.** Dutch healthcare domain knowledge is cleanly separated from platform infrastructure — FHIR profiles, identity methods, audit rules, and terminology are configuration, not hardcoded logic.

7. **Fail closed.** When compliance status is unknown, the platform denies access rather than permits it.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                              │
│  Web Agent UI  │ Claude Code (IDE) │ Telegram/WhatsApp │ Mobile │
└────────────────────────┬─────────────────────────────────────────┘
                         │ HTTPS / WebSocket
┌────────────────────────▼─────────────────────────────────────────┐
│                    AGENT GATEWAY                                  │
│  Nginx / Envoy ingress · TLS termination · Rate limiting         │
│  Session management · WebSocket proxy                            │
└────────────────────────┬─────────────────────────────────────────┘
                         │
        ┌────────────────▼──────────────────────────────────────────┐
        │             PLATFORM STANDARDS LAYER                      │
        │  Architecture principles · Agent guidelines               │
        │  Versioned policy profiles (POC / production)            │
        └────────────────┬──────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
┌───────▼──────┐ ┌───────▼──────┐ ┌──────▼───────┐
│ Agent Runner │ │ MCP Gateway  │ │  Auth Service │
│              │ │              │ │  (Keycloak)   │
│ LLM + MCP    │ │ Routes tool  │ │               │
│ client       │ │ calls to     │ │ OIDC / SAML   │
│ Manages      │ │ domain MCP   │ │ DigiD / UZI   │
│ conversation │ │ servers      │ │ eHerkenning   │
│ context      │ │              │ │               │
└───────┬──────┘ └──────┬───────┘ └──────────────┘
        │               │
        └───────┬────────┘
                │ MCP Protocol (stdio / SSE / HTTP)
┌───────────────▼──────────────────────────────────────────────────┐
│                     DOMAIN MCP SERVERS                            │
│                                                                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐  │
│  │  FHIR   │ │  Auth   │ │ Storage │ │  Audit  │ │   AI     │  │
│  │  MCP    │ │  MCP    │ │  MCP    │ │  MCP    │ │  MCP     │  │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬─────┘  │
│       │           │           │           │           │         │
│  ┌────┴────┐ ┌────┴────┐ ┌────┴────┐ ┌────┴────┐ ┌────┴─────┐  │
│  │Workflow │ │  Forms  │ │  Code   │ │Registry │ │Notif.    │  │
│  │  MCP    │ │  MCP    │ │  MCP    │ │  MCP    │ │  MCP     │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └──────────┘  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                   PLATFORM SERVICES (per tenant)                  │
│                                                                   │
│  HAPI FHIR · PostgreSQL · MinIO · Qdrant · Kafka                 │
│  Keycloak · OpenBao (Vault) · Gitea · ArgoCD                     │
│  vLLM / Ollama · Prometheus · Loki · Tempo                       │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                KUBERNETES INFRASTRUCTURE                          │
│  Namespaced per tenant · Cilium CNI · Istio service mesh         │
│  OPA/Kyverno policy enforcement · Falco runtime security         │
│  Rook-Ceph or Longhorn storage · cert-manager TLS               │
└──────────────────────────────────────────────────────────────────┘
```

---

## MCP Architecture

The Model Context Protocol is the central nervous system of the platform. Every platform capability is exposed as an MCP server, making it discoverable and invokable by any AI agent.

### MCP Server Catalog

#### `fhir-mcp`
Tools for reading and writing clinical data via FHIR R4.

```
fhir_search(resource_type, params, patient_id?) → Bundle
fhir_read(resource_type, id) → Resource
fhir_create(resource_type, body) → Resource
fhir_update(resource_type, id, body) → Resource
fhir_operation(resource_type, operation, params) → Result
fhir_validate(resource_type, body) → ValidationResult
zib_get_patient_summary(bsn) → PatientSummary
zib_get_medication_overview(bsn) → MedicationOverview
fhir_questionnaire_render(questionnaire_id) → FormSchema
fhir_questionnaireresponse_submit(questionnaire_id, answers) → QuestionnaireResponse
```

*Each tool call is authorization-checked against patient consent records before execution.*

#### `auth-mcp`
Identity and access management tools.

```
auth_get_current_user() → UserProfile
auth_verify_uzi(uzi_token) → ProfessionalIdentity
auth_verify_digid(digid_token) → PatientIdentity
auth_check_big_register(bignummer) → ProfessionalQualification
auth_check_agb(agb_code) → ProviderDetails
auth_get_consent(patient_id, purpose) → ConsentStatus
auth_set_consent(patient_id, purpose, granted) → ConsentRecord
auth_request_access(resource_id, purpose, justification) → AccessRequest
```

#### `storage-mcp`
Encrypted, classified document storage.

```
storage_upload(file, classification, metadata) → FileRef
storage_download(file_ref) → File
storage_list(prefix, filters) → FileList
storage_set_retention(file_ref, policy) → RetentionRecord
storage_delete(file_ref) → void  // soft delete with audit
storage_share(file_ref, recipient, expiry) → ShareLink
```

#### `audit-mcp`
NEN 7513-compliant access logging and querying.

```
audit_log(event_type, resource, purpose, outcome) → EventId
audit_query(filters, date_range) → AuditLog
audit_patient_log(patient_id, date_range) → PatientAccessLog
audit_export(format, date_range) → AuditExport
audit_alert_create(condition, recipient) → AlertId
```

*Note: `audit_log` is called automatically by all other MCP servers. This tool is for explicit application-level logging.*

#### `ai-mcp`
LLM inference and RAG, with automatic data governance.

```
ai_complete(prompt, context?, model?) → Completion
ai_embed(text) → Embedding
ai_rag_query(query, sources, filters?) → RAGResult
ai_classify_document(document, taxonomy) → Classification
ai_extract_structured(document, schema) → ExtractedData
ai_summarize_clinical(fhir_bundle, purpose) → Summary
ai_flag_ai_act_risk(feature_description) → RiskClassification
```

*Patient data in prompts is automatically detected and masked before routing to external LLMs.*

#### `workflow-mcp`
BPMN-based process automation.

```
workflow_start(process_id, input) → WorkflowInstance
workflow_get_status(instance_id) → WorkflowStatus
workflow_complete_task(task_id, outcome) → void
workflow_create_process(bpmn_xml) → ProcessId
workflow_list_pending(user_id) → TaskList
workflow_escalate(task_id, reason) → EscalationId
```

#### `forms-mcp`
Generate and handle compliant web forms.

```
forms_generate(fhir_questionnaire_id | schema, options) → FormSpec
forms_render_url(form_id) → URL
forms_get_response(form_id, response_id) → FormResponse
forms_create_from_description(natural_language_spec) → FormSpec
forms_export_to_fhir(form_id) → FHIRQuestionnaire
```

#### `code-mcp`
Sandboxed code generation and execution.

```
code_generate(description, target_language, constraints) → CodeArtifact
code_execute(code, runtime, timeout) → ExecutionResult
code_scaffold_app(spec) → AppProject
code_lint(code, rules) → LintResult
code_deploy(project, environment) → DeploymentStatus
code_review_compliance(code) → ComplianceReport
```

#### `notification-mcp`
Compliant messaging and notifications.

```
notification_send_secure_email(to, subject, body, attachment?) → MessageId
notification_send_zorgmail(to_uzi, subject, body) → MessageId
notification_send_in_app(user_id, message) → NotificationId
notification_subscribe_fhir(subscription_criteria, webhook) → SubscriptionId
notification_broadcast(org_id, message, urgency) → BroadcastId
```

#### `registry-mcp`
Application and service registry.

```
registry_list_apps(tenant_id) → AppList
registry_get_app(app_id) → AppDefinition
registry_register_app(manifest) → AppId
registry_get_compliance_status(app_id) → ComplianceStatus
registry_get_dependencies(app_id) → DependencyGraph
```

---

## Agent Interaction Design

### Vibe-Coding Flow

The core user experience is a conversational loop between the user and the AI agent. The agent uses MCP tools to gather context, propose solutions, and execute actions.

```
User: "Ik wil een formulier waarmee patiënten hun medicatieoverzicht
       kunnen opvragen en een PDF kunnen downloaden."

Agent → (thinks):
  1. fhir_search(Questionnaire) — check for existing templates
  2. auth_check_consent requirements for medication data
  3. forms_create_from_description("medication overview request form")
  4. ai_rag_query("MedMij medicatieoverzicht spec") — check compliance req.

Agent → User:
  "Ik stel voor om een formulier te bouwen met:
   - DigiD login (patiënt authenticatie)
   - Raadplegen van uw medicatieoverzicht via FHIR (MedMij profiel)
   - PDF export die voldoet aan NTA 7516 voor beveiligde communicatie

   Schematisch ziet het er zo uit: [preview]

   Vragen:
   - Welke zorgaanbieder(s) moeten worden bevraagd?
   - Moet de patiënt toestemming geven per raadpleging?

   Zal ik een testversie bouwen? [Ja] [Aanpassen] [Nee]"

User: "Ja, ga door"

Agent → code_scaffold_app({
  template: "medmij-patient-portal",
  features: ["digid-auth", "fhir-medication", "pdf-export"],
  compliance: ["nen7510", "medmij", "nta7516"]
}) → AppProject

Agent → code_deploy(AppProject, "staging") → URL

Agent → User:
  "Testversie staat klaar op [staging URL].
   Inclusief synthetische patiëntdata (geen echte BSN's).
   Compliance check: ✓ NEN 7510, ✓ MedMij, ✓ AVG consent

   Bekijk het, en als het goed is kan ik het live zetten. [Live zetten]"
```

### Agent Safety Rules

The agent enforces these rules from the Platform Standards Layer before taking any action:

1. **Destructive actions require explicit confirmation** — deleting data, revoking access, going live
2. **Clinical decision support is advisory only** — any AI-generated clinical suggestion must present a disclaimer and log the interaction
3. **BSN and patient data never appear in agent responses** — masked as `PATIENT-XXX` in conversation
4. **EU AI Act high-risk actions** (clinical decision support, biometric identification) trigger mandatory human review gate
5. **Agent cannot modify its own audit trail**
6. **Ambiguous compliance requests** — agent refuses with a clear explanation; tenant admins can configure optional escalation to a compliance officer. Agent never proceeds with a warning on patient data operations.

### Standards Profile Resolution

Before generating workflows, forms, or code, the agent resolves an active standards profile:

1. Determine tenant profile (`poc-default`, `nl-healthcare-prod`, or tenant-specific extension)
2. Load architecture constraints (allowed components, required patterns, prohibited patterns)
3. Load agent operating rules (confirmation requirements, masking requirements, escalation gates)
4. Validate planned actions against profile
5. Include standards profile version in output metadata and audit trail

### Template-Driven Application Starts

To reduce ambiguity and speed up delivery, the Platform Standards Layer also provides versioned application templates with prepared prompts.

Initial template types:

- `one-page-workflow-app` — lightweight operational app for a single workflow
- `analytics-dashboard-app` — KPI and operations dashboard with governed data access
- `intake-consent-app` — intake flow with consent capture and audit defaults

POC constraint: only `one-page-workflow-app` is enabled to keep validation scope narrow.

Each template package contains:

- a prompt scaffold for the agent
- required MCP tools and allowed tool sequence patterns
- mandatory compliance checks and safety gates
- configurable fields the user can customize

Agent execution pattern:

1. Suggest a best-fit template from user intent
2. Ask for required template parameters
3. Generate architecture and app plan using the template scaffold
4. Validate against standards profile and compliance rules
5. Produce deployable output with template ID/version traceability

### GitOps + AgentOps Runtime Loop

For each generated application, the platform uses a controlled loop:

1. Agent scaffolds or updates application artifacts in a dedicated Git repository
2. Agent opens a PR with a change summary and compliance context
3. CI validates policy, security, and quality checks
4. On merge, GitOps sync deploys to target environment
5. Observability signals (metrics/logs/traces/alerts) are analyzed by the agent
6. Agent notifies users and either:
   - applies low-risk approved runbook actions automatically, or
   - asks for approval for high-risk remediation actions

The agent does not patch running workloads directly outside the approved runbook path.

---

## Multi-Tenancy Design

### Isolation Model

Each tenant (organization) gets:

```
Namespace: tenant-{org-id}/
├── fhir-server          (HAPI FHIR pod + PostgreSQL)
├── minio-bucket         (encrypted, key: tenant-{org-id}-key)
├── keycloak-realm       (identity, users, clients)
├── qdrant-collection    (vector store)
├── gitea-org            (source code)
├── argocd-project       (deployments)
├── vault-path           (secrets: secret/tenant-{org-id}/)
└── kafka-topics         (events: tenant-{org-id}.*)
```

Kubernetes NetworkPolicy ensures pods in `tenant-A` cannot reach pods in `tenant-B`. OPA/Kyverno policies enforce at admission time.

### Encryption Key Hierarchy

```
Platform Root Key (HSM or Vault-managed)
└── Tenant Master Key (one per org, rotatable)
    ├── Database Encryption Key
    ├── Object Storage Key
    ├── Audit Log Signing Key
    └── Application Secrets Key
```

Tenant master keys are derived on first tenant provisioning and stored in Vault with break-glass procedures. Platform operators cannot decrypt tenant data without the tenant's explicit participation (key ceremony).

---

## Data Model

### FHIR Resource Governance

The platform pre-configures each healthcare tenant's FHIR server with:

```
Zib 2024 Profiles (Dutch clinical building blocks):
- nl-core-Patient               (patient identity, BSN)
- nl-core-Practitioner          (healthcare professional, BIG/AGB)
- nl-core-Organization          (provider, AGB-code)
- nl-core-MedicationRequest     (medication prescriptions)
- nl-core-Condition             (diagnoses, ICD-10-NL)
- nl-core-Observation           (measurements, vitals)
- nl-core-Procedure             (interventions)
- nl-core-AllergyIntolerance    (allergies)
- nl-core-Appointment           (scheduling)
- nl-core-Consent               (patient consent)
- nl-core-DocumentReference     (clinical documents)

MedMij Profiles:
- medmij-gpdata-*               (GP data service)
- medmij-medication-*           (medication overview)
- medmij-pdfa-*                 (PDF/A document sharing)

Twiin Profiles:
- twiin-referral-*              (referral between providers)
- twiin-discharge-*             (hospital discharge summary)
```

### Consent Service

Patient consent is tracked as a FHIR `Consent` resource and enforced at the FHIR MCP layer:

```
Consent record:
- patient_id (BSN, encrypted)
- actor (organization or professional requesting access)
- purpose (code from SNOMED/HL7 purpose of use)
- scope (FHIR resource types and/or specific resources)
- period (start / end date)
- provision (permit / deny)
- verification (method: DigiD, eHerkenning, verbal + witnessed)
```

Every `fhir_*` MCP tool call checks: `consent_check(patient_id, requesting_actor, purpose, resource_type)` before executing. Unauthorized access returns `403` with an audit event.

---

## Open Questions

See `0-open-questions.md`.
