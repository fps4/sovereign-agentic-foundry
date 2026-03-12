# Foundation Platform — Product Requirements

**Version:** 0.1 (Draft)
**Date:** 2026-03-11
**Status:** For discussion

---

## User Personas

### 1. The Domain Builder (primary)
A clinician, care coordinator, or healthcare operations professional who wants to automate a workflow or build a small tool for their team. Has deep domain knowledge, limited or no programming experience. Interacts primarily via the AI agent.

*Example: A GP practice manager who wants to build a referral tracking tool with FHIR-based data exchange.*

### 2. The Healthcare Service Business Builder (secondary)
A business owner, operations manager, or domain specialist at a non-IT healthcare service business who wants to build applications to digitize or improve their service delivery. Has deep knowledge of their domain and workflows, limited or no programming experience. Uses the AI agent in the same way as the Domain Builder, but their output is a product or service rather than an internal tool.

*Example: A pharmacist at a pharmacy chain who wants to build a medication adherence tracking app for their patients, with automated reminders and GP notifications.*

### 3. The Platform Administrator
Manages the Foundation Platform deployment for an organization. Controls tenant isolation, user access, resource quotas, and compliance settings.

*Example: CISO or IT manager at a regional hospital network.*

### 4. The Compliance Officer
Reviews and approves applications built on the platform. Needs audit trails, data flow documentation, consent records, and compliance status dashboards.

*Example: Functionaris Gegevensbescherming (FG) at a healthcare provider.*

---

## Functional Requirements

### FR-0: Platform Standards Layer

| ID | Requirement | Priority |
|---|---|---|
| FR-0.1 | Platform provides a versioned standards catalog that defines architecture principles and implementation guidelines for generated applications | Must |
| FR-0.2 | AI agents must load applicable standards profile before planning or generating application changes | Must |
| FR-0.3 | Standards profiles include domain, compliance, and environment constraints (POC vs production) | Must |
| FR-0.4 | Generated plans and code must include traceability to the standards profile version used | Should |
| FR-0.5 | Tenant administrators can configure approved standards profiles, but cannot disable mandatory safety/compliance rules | Must |
| FR-0.6 | Platform provides versioned application templates (e.g., one-page workflow app, analytics app, intake app) in the standards layer | Must |
| FR-0.7 | Each application template includes prepared prompt scaffolds, required MCP tool sets, and mandatory compliance checks | Must |
| FR-0.8 | Agents must collect template parameters through guided questions before generation starts | Should |
| FR-0.9 | Template execution metadata (template ID and version) is recorded in audit logs and generated project metadata | Should |

### FR-1: AI Agent Interface

| ID | Requirement | Priority |
|---|---|---|
| FR-1.1 | Users can interact with the platform through a conversational AI agent in Dutch (primary) and English | Must |
| FR-1.2 | The agent can create, modify, and deploy applications from natural language descriptions | Must |
| FR-1.3 | The agent can explain what it is building and why, including compliance implications | Must |
| FR-1.4 | The agent can ask clarifying questions when requirements are ambiguous | Must |
| FR-1.5 | The agent can present generated application previews before deployment | Must |
| FR-1.6 | The agent supports iterative refinement ("make the form only show for patients over 65") | Must |
| FR-1.7 | The agent can query platform audit logs and explain compliance status to users | Should |
| FR-1.8 | The agent supports a code/IDE mode for developer persona interactions | Should |
| FR-1.9 | All agent interactions are logged with user identity, timestamps, and outcomes | Must |
| FR-1.10 | User interaction layer supports Telegram and WhatsApp channels for approved conversational flows | Should |
| FR-1.11 | Messaging-channel interactions are policy-controlled, consent-aware, and fully audit-logged | Must |

### FR-2: MCP Gateway

| ID | Requirement | Priority |
|---|---|---|
| FR-2.1 | The platform exposes all capabilities as MCP servers consumable by any MCP-compatible agent or IDE | Must |
| FR-2.2 | MCP tools are grouped by domain: FHIR, Auth, Storage, AI, Audit, Workflow, Notification, Forms, Code | Must |
| FR-2.3 | Each MCP tool call is authenticated, authorized, and audit-logged | Must |
| FR-2.4 | MCP tool schemas are self-describing and include compliance metadata (e.g., "this tool accesses BSN") | Must |
| FR-2.5 | MCP servers support OAuth 2.0 / OIDC for tool-level authorization | Must |
| FR-2.6 | Rate limiting and quota enforcement apply per tenant at the MCP gateway | Should |
| FR-2.7 | Claude Code and other MCP clients can connect to the platform directly | Should |
| FR-2.8 | MCP server definitions are versionable and backward-compatible | Should |

### FR-3: FHIR Service (Dutch Healthcare)

| ID | Requirement | Priority |
|---|---|---|
| FR-3.1 | Platform provides a managed FHIR R4 server (HAPI FHIR or Firely Server) per tenant | Must |
| FR-3.2 | Dutch Zib (Zorginformatiebouwstenen) 2024 profiles are pre-loaded and validated | Must |
| FR-3.3 | MedMij FHIR implementation guides are supported out of the box | Must |
| FR-3.4 | Twiin interoperability profiles are supported | Should |
| FR-3.5 | FHIR resources are accessible via MCP tools (search, read, create, update) | Must |
| FR-3.6 | FHIR data access is governed by patient consent records stored on-platform | Must |
| FR-3.7 | The AI agent can help users model data using Zib building blocks | Must |
| FR-3.8 | FHIR Bulk Data export is supported for reporting | Should |
| FR-3.9 | Terminology services: SNOMED CT NL, LOINC, ATC, ICD-10-NL are available | Must |
| FR-3.10 | CDA R2 import/export for legacy system compatibility | Could |

### FR-4: Identity and Access Management

| ID | Requirement | Priority |
|---|---|---|
| FR-4.1 | Platform authenticates users via Keycloak (OIDC/SAML) | Must |
| FR-4.2 | DigiD authentication integration for patient-facing applications | Must |
| FR-4.3 | eHerkenning integration for professional-facing applications | Must |
| FR-4.4 | UZI-pas (UZI card) authentication for healthcare professionals | Must |
| FR-4.5 | BSN handling complies with Wbp/AVG: encrypted at rest, access-logged, minimal exposure | Must |
| FR-4.6 | Role-based access control (RBAC) at tenant, application, and data levels | Must |
| FR-4.7 | AGB-code verification for healthcare provider identity | Should |
| FR-4.8 | BIG-register lookup for professional qualification verification | Should |
| FR-4.9 | Multi-factor authentication enforced for all platform users | Must |
| FR-4.10 | Fine-grained consent management: patient controls per-purpose data access | Must |

### FR-5: Storage and Data Services

| ID | Requirement | Priority |
|---|---|---|
| FR-5.1 | Encrypted object storage (MinIO) with per-tenant isolation | Must |
| FR-5.2 | Relational database (PostgreSQL) with encrypted volumes per tenant | Must |
| FR-5.3 | All data encrypted at rest (AES-256) and in transit (TLS 1.3 minimum) | Must |
| FR-5.4 | Data classification labels propagate through the platform (e.g., "contains BSN", "patient data") | Must |
| FR-5.5 | Backup and point-in-time recovery for all tenant data | Must |
| FR-5.6 | Data residency enforcement: data cannot leave configured geographic boundary | Must |
| FR-5.7 | Vector database (Qdrant) for AI/RAG workloads, isolated per tenant | Should |
| FR-5.8 | Data retention policies configurable per dataset with automated enforcement | Must |

### FR-6: AI Services

| ID | Requirement | Priority |
|---|---|---|
| FR-6.1 | Platform serves open-source LLMs on-cluster (vLLM or Ollama) | Must |
| FR-6.2 | Embedding models available for RAG pipelines (multilingual, including Dutch) | Must |
| FR-6.3 | External LLM APIs (Anthropic Claude, OpenAI) usable only with explicit tenant opt-in and data masking | Should |
| FR-6.4 | LLM calls involving patient data are audited and the data is masked before leaving tenant boundary | Must |
| FR-6.5 | AI model registry: versioned, auditable model deployments | Should |
| FR-6.6 | AI-generated outputs that affect clinical decisions are flagged and require human confirmation | Must |
| FR-6.7 | RAG pipeline builder: connect FHIR resources, documents, terminology to AI context | Must |
| FR-6.8 | EU AI Act compliance metadata for deployed AI features (risk classification, intended purpose) | Must |

### FR-7: Audit and Compliance

| ID | Requirement | Priority |
|---|---|---|
| FR-7.1 | All data access events are logged per NEN 7513 (WHO accessed WHAT at WHEN from WHERE for WHY) | Must |
| FR-7.2 | Audit logs are immutable, tamper-evident (append-only + cryptographic signing) | Must |
| FR-7.3 | Audit logs are retained for minimum 15 years (NEN 7513 / WGBO requirement) | Must |
| FR-7.4 | Compliance dashboard: real-time view of NEN 7510 control status per tenant | Should |
| FR-7.5 | Automated alerting on anomalous access patterns (e.g., bulk patient data access) | Must |
| FR-7.6 | Audit log export in standard formats for external auditors | Must |
| FR-7.7 | DPIA (Data Protection Impact Assessment) report generation for applications | Should |
| FR-7.8 | Incident management workflow integrated with audit trail | Should |

### FR-8: Application Lifecycle

| ID | Requirement | Priority |
|---|---|---|
| FR-8.1 | Platform provides Git-based source control (Gitea) per tenant/project | Must |
| FR-8.2 | Generated applications are stored as code in version control | Must |
| FR-8.3 | CI/CD pipeline (ArgoCD or Tekton) for automated build/test/deploy | Must |
| FR-8.4 | Staging/sandbox environments with synthetic patient data for testing | Must |
| FR-8.5 | One-click promotion from staging to production with compliance gate | Must |
| FR-8.6 | Synthetic Dutch patient data generator (based on Zib profiles) for test environments | Must |
| FR-8.7 | Application marketplace: share and reuse compliant application templates | Could |
| FR-8.8 | Rollback to previous application version with data migration support | Must |
| FR-8.9 | Each generated application gets a dedicated Git repository containing app code, deployment manifests, and pipeline configuration | Must |
| FR-8.10 | Deployment changes are applied through GitOps flow only (PR -> checks -> merge -> sync), not direct runtime mutation | Must |
| FR-8.11 | Agents may propose and open pull requests but cannot merge to protected branches without policy/approval gates | Must |
| FR-8.12 | Repository protections are enabled by default (protected main branch, required checks, mandatory review for high-risk changes) | Must |
| FR-8.13 | Release metadata (template ID/version, standards profile version, deployment commit SHA) is recorded per deployment | Should |

### FR-9: Notifications and Workflow

| ID | Requirement | Priority |
|---|---|---|
| FR-9.1 | Secure messaging compliant with NTA 7516 (ZorgMail / ZORG-ID interoperability) | Must |
| FR-9.2 | FHIR Subscription support for event-driven workflows | Should |
| FR-9.3 | Workflow engine (BPMN) for multi-step care coordination processes | Should |
| FR-9.4 | Email notification with end-to-end encryption via NTA 7516 compliant transport | Must |
| FR-9.5 | Push notifications for patient-facing applications via MedMij channels | Could |

### FR-10: Forms and UI Generation

| ID | Requirement | Priority |
|---|---|---|
| FR-10.1 | AI agent can generate web forms backed by FHIR Questionnaire resources | Must |
| FR-10.2 | Generated UI meets WCAG 2.1 AA accessibility requirements | Must |
| FR-10.3 | Forms support DigiD login for patient authentication | Must |
| FR-10.4 | Generated applications are mobile-responsive | Must |
| FR-10.5 | UI components are branded per tenant | Should |

### FR-11: Observability and Agent Operations

| ID | Requirement | Priority |
|---|---|---|
| FR-11.1 | Platform collects metrics, logs, and traces per generated application and environment | Must |
| FR-11.2 | Agent can analyze observability signals and notify users about incidents, degradations, and policy violations | Must |
| FR-11.3 | Low-risk remediation actions can be auto-executed via approved runbooks (e.g., restart, scale, rollback) | Should |
| FR-11.4 | High-risk remediation actions require explicit user or admin approval before execution | Must |
| FR-11.5 | Every alert and remediation action includes full audit metadata (trigger, decision path, action, outcome) | Must |

---

## Non-Functional Requirements

### Security (NFR-S)

| ID | Requirement |
|---|---|
| NFR-S.1 | Zero-trust network model: no implicit trust between services |
| NFR-S.2 | All inter-service communication via mutual TLS (mTLS) through service mesh |
| NFR-S.3 | Secrets management via HashiCorp Vault / OpenBao — no secrets in code or environment variables |
| NFR-S.4 | Container images scanned for CVEs before deployment; critical CVEs block deployment |
| NFR-S.5 | Penetration testing required before production launch |
| NFR-S.6 | Supply chain security: SBOM generated for all components |
| NFR-S.7 | Network policies enforce strict tenant isolation at pod level |
| NFR-S.8 | Encryption keys managed per tenant; keys never co-mingled |

### Compliance (NFR-C)

| ID | Standard | Requirement |
|---|---|---|
| NFR-C.1 | NEN 7510:2017+A1:2020 | Information security management in healthcare — platform must document and evidence all controls |
| NFR-C.2 | NEN 7512:2022 | Trust basis for data exchange — PKI-based identity verification |
| NFR-C.3 | NEN 7513:2018 | Logging of access to electronic patient records |
| NFR-C.4 | NTA 7516 | Secure email for healthcare |
| NFR-C.5 | AVG / GDPR | Data processing agreements, data subject rights, consent management |
| NFR-C.6 | EU AI Act | Risk classification for AI features; transparency and human oversight requirements |
| NFR-C.7 | WGBO | Patient medical record retention (minimum 20 years for healthcare records) |
| NFR-C.8 | Wet BIG | Professional qualification verification for access to clinical functions |
| NFR-C.9 | ISO 27001 | Target certification for platform infrastructure (Phase 2) |
| NFR-C.10 | EHDS | European Health Data Space readiness for future cross-border interoperability |

### Performance (NFR-P)

| ID | Requirement |
|---|---|
| NFR-P.1 | FHIR API response time: p95 < 500ms for single-resource reads |
| NFR-P.2 | LLM inference: first token latency p95 < 3s for 7B parameter models on GPU |
| NFR-P.3 | MCP gateway: p99 latency < 200ms (excluding downstream service time) |
| NFR-P.4 | Platform availability: 99.5% uptime for managed service offering |
| NFR-P.5 | Agent interaction: full application scaffold generated within 60 seconds |

### Scalability (NFR-SC)

| ID | Requirement |
|---|---|
| NFR-SC.1 | Multi-tenant: support 100+ organizations on a single platform cluster |
| NFR-SC.2 | Per-tenant FHIR server supports up to 1M resources |
| NFR-SC.3 | Horizontal scaling of all stateless services |
| NFR-SC.4 | AI serving auto-scales based on queue depth |

### Operability (NFR-O)

| ID | Requirement |
|---|---|
| NFR-O.1 | Full observability stack: metrics (Prometheus), logs (Loki), traces (Tempo/Jaeger) |
| NFR-O.2 | Grafana dashboards for operational health and SLA tracking |
| NFR-O.3 | Alerting to PagerDuty / Opsgenie or equivalent |
| NFR-O.4 | Infrastructure-as-code: all platform configuration in Git (GitOps) |
| NFR-O.5 | Single-command platform deployment for managed service environments |

---

## Compliance Requirements Matrix

| Requirement | NEN 7510 Control | GDPR Article | Platform Feature |
|---|---|---|---|
| Access logging | A.12.4 | Art. 5(1)(f) | NEN 7513 audit log |
| Encryption at rest | A.10.1 | Art. 32 | Per-tenant key encryption |
| Encryption in transit | A.14.1 | Art. 32 | TLS 1.3, mTLS |
| Access control | A.9 | Art. 25 | RBAC + OIDC |
| Data minimization | A.18.1 | Art. 5(1)(c) | Field-level data classification |
| Consent management | — | Art. 6, 9 | Platform consent service |
| Data retention | A.18.1 | Art. 5(1)(e) | Automated retention policies |
| Incident response | A.16 | Art. 33-34 | Incident workflow |
| Backup and recovery | A.12.3 | Art. 32 | Automated backup |
| Security testing | A.14.2 | Art. 25 | CI/CD security gates |

---

## Integration Requirements

### External Systems

| System | Protocol | Direction | Required |
|---|---|---|---|
| DigiD | SAML 2.0 | Inbound (auth) | Must (patient apps) |
| eHerkenning | SAML 2.0 | Inbound (auth) | Must (pro apps) |
| UZI-register | REST / PKCS | Inbound (auth) | Must |
| BIG-register | REST | Outbound (lookup) | Should |
| ZorgMail / NTA 7516 | SMTP+TLS / SOAP | Bidirectional | Must |
| NUTS network | NUTS protocol | Bidirectional | Should |
| MedMij | OAuth 2.0 / FHIR | Bidirectional | Should |
| Twiin | FHIR / HL7v2 | Bidirectional | Should |
| AGB-register | REST | Outbound (lookup) | Should |
| LSP (Landelijk Schakelpunt) | HL7v3 / SOAP | Bidirectional | Could |
| Vektis code tables | REST / CSV | Inbound | Should |

---

## Open Questions

See `0-open-questions.md`.
