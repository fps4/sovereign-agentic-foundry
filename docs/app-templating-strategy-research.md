# Healthcare Application Templates — Design Brief

## Why Templating?

Templating is the right architectural choice for a healthcare-focused agentic platform. It solves three real problems users have:

- They know what they want **functionally**, but not what they need **technically**
- They cannot afford to get **compliance wrong** (HIPAA, GDPR, HL7, FHIR, audit trails)
- They need to move **fast** — patient care doesn't wait

Templates encode guardrails by default. A patient intake form template, for example, would hardwire encryption at rest, no client-side PHI logging, an audit trail on every submission, and FHIR QuestionnaireResponse as the output format — the user never has to think about any of that.

---

## Application Archetypes

### Clinical — patient-facing or clinician-facing, PHI in scope

| App type | Description | Compliance | App pattern |
|---|---|---|---|
| **Patient intake & triage form** | Structured data collection before appointment. Symptom checkers, consent forms, anamnesis flows. | HIPAA/GDPR · FHIR R4 | One-pager |
| **Clinician dashboard** | Patient list, vitals overview, task queue. Reads from EHR via FHIR API, no local data storage. | HIPAA/GDPR · FHIR R4 | Web app |
| **Care pathway tracker** | Step-by-step protocol adherence for chronic conditions (diabetes, oncology). Progress tracking per patient. | HIPAA/GDPR | Workflow app |
| **Appointment scheduling** | Self-service booking with slot availability, reminders, cancellation flows. Integrates with calendar APIs. | PII | Web app + notifications |

### Operational — internal staff tools, often no direct PHI

| App type | Description | Compliance | App pattern |
|---|---|---|---|
| **Staff rota & scheduling** | Shift management, on-call rotations, leave requests for clinical staff. | Internal | CRUD app |
| **Incident reporting** | Near-miss and adverse event capture. Structured forms with audit trail, anonymisation options. | Audit trail | Form + workflow |
| **Asset & equipment tracker** | Medical device inventory, maintenance schedules, location tracking (ward/room level). | No PHI | CRUD app |
| **Clinical knowledge base** | Internal wiki for protocols, SOPs, formularies. Search-first, version-controlled content. | No PHI | Docs app |
| **Referral management** | GP-to-specialist referral queue, status tracking, document attachment. HL7 messaging. | HIPAA/GDPR | Workflow app |
| **Compliance report builder** | Periodic reporting for regulators (CQC, RIVM etc.). Aggregated metrics, no individual records exposed. | Anonymised | Reporting app |

### Integration & data — backend services, minimal or no UI

| App type | Description | Compliance | App pattern |
|---|---|---|---|
| **FHIR integration microservice** | Adapter between legacy HL7v2/v3 systems and modern FHIR R4. Transforms, validates, routes messages. | HIPAA/GDPR | Microservice (no UI) |
| **Alert & notification service** | Threshold-based alerts (lab results, vitals) dispatched via SMS, push, or pager. Escalation logic. | HIPAA/GDPR | Event-driven service |

### Analytics — aggregated, typically de-identified

| App type | Description | Compliance | App pattern |
|---|---|---|---|
| **Operational analytics dashboard** | Bed occupancy, wait times, throughput KPIs. Pre-aggregated data only, no patient drill-through. | De-identified | Dashboard |
| **Population health report** | Cohort-level chronic disease prevalence, screening coverage, outcomes over time. | Aggregated | Reporting app |

---

## Template Complexity vs Compliance Burden

Not all templates are equal. Prioritising by build complexity and compliance weight helps sequence the rollout:

| Quadrant | Templates | Strategy |
|---|---|---|
| Low complexity, high compliance | Patient intake form, incident report | **Best first templates** — fast to build, strong compliance proof point |
| Low complexity, low compliance | Asset tracker, knowledge base | Quick wins — good for validating the pipeline end-to-end |
| High complexity, high compliance | Care pathway tracker, referral management, FHIR adapter | Advanced templates — build after the platform is proven |
| High complexity, low compliance | Operational analytics, FHIR integration | Later additions — valuable but not the opening story |

The **top priority for POC** is the patient intake form and incident report. Both are simple to generate, immediately recognisable to healthcare users, and carry real compliance weight — demonstrating that the platform handles that automatically is a powerful proof point.

---

## Preferred Technology Toolbox

Each template is a combination of three layers: a **stack** (technology choices), a **scaffold** (generated repo structure), and a **compliance profile** (baked-in guardrails).

### Frontend
- Next.js (default for web apps and dashboards)
- SvelteKit (lightweight alternative for one-pagers and forms)

### Backend
- FastAPI (Python — preferred for AI-adjacent services and lightweight APIs)
- Spring Boot (Java — preferred for HL7/FHIR-heavy integrations)

### Data
- PostgreSQL — default relational store, with row-level security for PHI
- Redis — session state, queues, short-lived data
- Qdrant — vector search for knowledge bases and semantic retrieval

### Authentication
- Keycloak — default for all apps requiring user login
- SMART on FHIR — for clinical apps launching from within an EHR

### Interoperability
- HAPI FHIR Server — when FHIR R4 storage or brokering is needed
- Apache Camel — for HL7v2/v3 message routing and transformation

### Platform defaults (every generated app gets these)
- Traefik labels for routing
- Prometheus `/metrics` endpoint
- Structured JSON logging (no free-text logs with PHI)
- Audit log table in PostgreSQL (who, what, when, outcome)
- Gitea repo with Woodpecker CI pipeline pre-configured

---

## Template Discovery: Conversational vs Menu-driven

Both modes are needed:

- **Menu / catalogue** — for discovery. Users browse available templates and pick the closest fit.
- **Conversation** — for customisation. After selecting a template, the user describes what they need and the LLM maps that to configuration choices within the template's guardrails.

This distinction shapes the intent classifier in the orchestrator: the first turn identifies the template category, subsequent turns fill in the template parameters (name, data fields, integrations, deployment target).

---

## Compliance Profiles

Each template declares a compliance profile in its YAML definition. The orchestrator enforces this at generation time and the review agent validates it before any code is committed.

| Profile | Applies to | Enforced controls |
|---|---|---|
| `phi-full` | Clinical apps with stored patient data | Encryption at rest + in transit, audit log, no client-side PHI, FHIR output, DPIA checklist |
| `phi-transit` | Apps that proxy PHI but don't store it | TLS only, no logging of request bodies, session timeout |
| `pii-basic` | Apps with staff or patient contact data | Encrypted DB, access control, data retention policy |
| `internal` | No personal data, internal staff tools | Standard auth, no special data controls |
| `public` | Public-facing, no personal data | Rate limiting, OWASP headers, no auth required |