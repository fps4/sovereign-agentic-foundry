# App Types

## App Types

### 1. Form
**Collect or manage structured data**

Covers single-purpose data collection (submit once) and ongoing record management (search, edit, delete). The clarifying question at conversation time determines which scaffold is generated.

Healthcare examples: patient intake and consent, incident reports, staff leave requests, referral submissions, staff directories, device registries.

Merged from: Form + Data app

---

### 2. Dashboard
**Display live or aggregated data**

A read-oriented interface that visualises metrics, lists, or statuses pulled from an API or database. Includes filters, drill-downs, and auto-refresh. No write operations.

Healthcare examples: bed occupancy and wait times, clinician patient lists, equipment maintenance status, population health KPIs.

Unchanged from original.

---

### 3. Workflow
**Move tasks through stages, or run on a schedule**

A multi-role app where items progress through defined states with assignments, transitions, notifications, and an audit trail — or a scheduled/event-driven automation that runs without human interaction.

Healthcare examples: referral tracking, care pathway adherence, discharge checklists, nightly report emails, appointment reminder dispatchers.

Merged from: Workflow app + Automation.

---

### 4. Connector
**Link two systems, no UI needed**

A headless backend service that listens for events or messages from one system, transforms the data, and forwards it to another. Exposes a health endpoint but no user-facing interface. Stateless or near-stateless by design.

Healthcare examples: HL7v2 to FHIR R4 adapter, lab result router, EHR to reporting database sync.

Renamed from: Integration service.

---

### 5. Assistant
**Chat and Q&A over documents**

A RAG-powered conversational interface grounded in internal documents or a knowledge base. Users ask questions in natural language; the assistant retrieves relevant content and responds. Distinct architecture from the other four types — no traditional database schema, built around a vector store and LLM inference.

Healthcare examples: protocol and SOP Q&A, drug formulary assistant, discharge instruction bot, staff onboarding helper.

New type, not present in original four.

---

## Coverage Assessment

| What a user wants to build | Type |
|---|---|
| Patient intake form | Form |
| Consent collection | Form |
| Staff or device registry | Form |
| Bed occupancy tracker | Dashboard |
| Clinical KPI view | Dashboard |
| Referral tracking | Workflow |
| Care pathway adherence | Workflow |
| Nightly report email | Workflow |
| Appointment reminders | Workflow |
| HL7 → FHIR adapter | Connector |
| Lab result routing | Connector |
| Protocol Q&A bot | Assistant |
| SOP search assistant | Assistant |

Remaining ~20% not covered: patient portals (too complex, external-facing), mobile native apps (different build chain), multi-tenant platforms (composed of multiple app types).