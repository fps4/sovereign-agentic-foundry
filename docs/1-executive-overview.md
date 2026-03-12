# Foundation Platform — Executive Overview

**Version:** 0.1 (Draft)
**Date:** 2026-03-11
**Status:** For discussion

---

## Vision

Enable Dutch healthcare organizations and healthcare service businesses to build compliant business applications through AI-assisted development — without depending on US hyperscalers, without a team of compliance specialists, and without months of integration work.

The platform provides a sovereign, open-source AI cloud where Dutch healthcare compliance is infrastructure, not an afterthought.

---

## The Problem

Building software for Dutch healthcare today requires:

- Deep integration expertise with Dutch standards (FHIR Zib profiles, NEN 7510, DigiD, BSN, MedMij, Twiin)
- Expensive compliance consultants and security audits
- Dependency on US cloud providers (AWS, Azure, GCP) that create data sovereignty risk
- Long development cycles before a single working feature ships
- Separate toolchains for development, compliance management, audit trails, and deployment

Small and mid-sized organizations — a regional hospital, a GP cooperative, a homecare company, a pharmacy chain — cannot afford to do this well. They either buy expensive vendor-locked software or skip important requirements. Either way, the result is workflows that remain manual, fragmented, or non-compliant.

---

## The Opportunity

**Netherlands healthcare alone:** ~17,000 general practitioners, ~100 hospitals, ~350+ mental health providers, ~1,500+ homecare organizations, thousands of pharmacies, physiotherapy practices, and care coordination businesses — all required to meet NEN 7510, NTA 7516, FHIR interoperability, and AVG/GDPR. The software market serving them is fragmented, expensive, and largely proprietary. Many of these organizations have specific workflow needs that off-the-shelf software cannot meet, but no practical way to build compliant custom tooling themselves.

**EU Digital Health:** The European Health Data Space (EHDS) regulation and the EU AI Act are creating mandatory compliance requirements, generating further urgency for platforms that can absorb this complexity.

---

## What We Are Building

**Foundation Platform** is an AI-powered application development environment for Dutch healthcare, designed around four principles:

### 1. Sovereign Infrastructure
Delivered as a subscription-based managed service running on EU-based, open-source infrastructure. Organizations do not manage servers, containers, or upgrades — they subscribe and use the platform. No data leaves Dutch/EU jurisdiction by design. No dependency on US cloud providers.

### 2. Compliance as a Service
Dutch healthcare standards (NEN 7510/7512/7513, NTA 7516, FHIR R4, Zib 2024, MedMij, Twiin) are exposed as platform services — not documentation to read and implement. The platform enforces encryption, audit logging, consent management, and identity verification at the infrastructure level, so solutions built on the platform are compliant by design.

### 3. Agent-Assisted Development
Users interact with an AI agent in natural language to build, configure, and deploy applications. The agent orchestrates all platform capabilities through the Model Context Protocol (MCP) — a structured interface that exposes platform services to AI models. Users describe what they need; the agent translates that into compliant, deployed software.

### 4. Platform Standards Layer
The platform defines and versions architecture principles, implementation guidelines, and agent operating rules centrally. Agents consume these standards as runtime context and policy constraints, so generated solutions follow platform-approved design patterns and safety rules by default.

This is the same shift Nebius made from raw GPU access to managed inference — but applied one layer higher: from raw cloud APIs to governed and standardized business application capabilities.

---

## How It Differs from Existing Solutions

| Dimension | AWS/Azure/GCP | Nebius | Foundation Platform |
|---|---|---|---|
| Data sovereignty | US jurisdiction | Finland/EU | Customer jurisdiction |
| Compliance | DIY | DIY | Built-in (NEN, FHIR, AVG) |
| Target users | General | ML practitioners | Healthcare orgs + healthcare service businesses |
| Developer interface | Console + APIs | Console + APIs | AI agent (MCP) |
| Domain knowledge | None | None | Dutch healthcare |
| Open source | Partial | Partial | Fully open-source stack |
| Deployment model | Hosted only | Hosted only | Managed service on EU-sovereign cloud |

Nebius (reviewed March 2026) is a useful reference for the "managed AI infrastructure" category — strong GPU provisioning, OpenAI-compatible APIs, managed MLflow/PostgreSQL. But it targets ML practitioners building AI products, not domain organizations building regulated applications. It has no concept of healthcare standards, audit logging, consent, or domain-specific data models.

---

## Platform Layers

```
┌─────────────────────────────────────────────────────┐
│  User (clinician, care coordinator, service business)│
│  Interacts via: chat agent, web IDE, CLI, Telegram, │
│  and WhatsApp (policy-controlled integrations)       │
├─────────────────────────────────────────────────────┤
│  AI Agent Layer                                     │
│  Claude / open LLM + MCP client                     │
│  Understands: intent → compliant application        │
├─────────────────────────────────────────────────────┤
│  Platform Standards Layer                           │
│  Architecture principles · Agent guidelines         │
│  Policy profiles · Versioned implementation rules   │
├─────────────────────────────────────────────────────┤
│  MCP Gateway (Domain Service Bus)                   │
│  FHIR · Auth · Storage · Audit · AI · Workflow      │
│  Notifications · Code Execution · Forms · Registry  │
├─────────────────────────────────────────────────────┤
│  Domain Compliance Layer                            │
│  NEN 7510 · FHIR R4 · AVG/GDPR · NTA 7516          │
│  DigiD · UZI · BSN · AGB · Zib · MedMij · Twiin    │
├─────────────────────────────────────────────────────┤
│  Platform Services Layer                            │
│  PostgreSQL · MinIO · Kafka · Keycloak · Vault      │
│  vLLM · Qdrant · Gitea · ArgoCD · Prometheus        │
├─────────────────────────────────────────────────────┤
│  Sovereign Infrastructure                           │
│  Kubernetes · EU-sovereign cloud                    │
│  Istio · Cilium · OpenTelemetry                     │
└─────────────────────────────────────────────────────┘
```

---

## Target: Dutch Healthcare Organizations and Healthcare Service Businesses

Both user types interact with the platform the same way — through the AI agent — and neither requires IT expertise to build and deploy applications.

**Healthcare organizations** — build internal tools and workflows:
- GP cooperatives (HAP, huisartsenposten)
- Regional hospitals and specialist clinics
- Mental health providers (GGZ)
- Homecare organizations
- Public health services (GGD)

**Healthcare service businesses** — build applications for their service delivery or coordination with care providers:
- Pharmacy chains (medication management, patient communication)
- Physiotherapy and allied health practices (intake, care plans, reporting)
- Care coordination companies (referral management, multi-provider workflows)
- Home medical equipment suppliers (prescription workflows, delivery coordination)
- Occupational health services (Arbo) (employer reporting, case management)

Why Dutch healthcare first:
- Well-defined, mature standards (NEN 7510, FHIR Zib profiles, MedMij, Twiin)
- Strong regulatory pressure creating urgency
- Significant open-source health IT community (OpenEHR NL, NUTS foundation, VWS initiatives)
- Government mandates for FHIR interoperability (2026 deadlines)

Initial use cases:
- GP referral workflow automation
- Patient consent management
- Care plan coordination between providers
- Clinical decision support integration
- Reporting to registries (NHR, DHD, etc.)

---

## POC Focus and Next Step

The current delivery focus is a Proof of Concept (POC) to validate the agent-assisted workflow, core MCP services, and compliance-by-design foundations using synthetic data only.

Detailed POC scope, purpose, and design are documented in:

`docs/6-poc.md`

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| LLM output quality for regulated code | Human review gates, compliance test suites, sandboxed preview environments |
| Dutch healthcare standards complexity | NUTS/FHIR community partnerships, existing Zib implementors |
| Sovereign infra performance vs hyperscalers | GPU-optimized EU nodes (OVHcloud AI, SURF), quantized model serving |
| Regulatory liability for generated applications | Platform certifies infrastructure; app owners certify their applications |
