# Production Considerations

**Version:** 0.1 (Stub)
**Date:** 2026-03-12
**Status:** Placeholder — to be elaborated after POC

This document captures infrastructure and operational decisions that are explicitly deferred from the POC scope. Items here require proper evaluation before production deployment.

---

## Platform Standards Layer Operations

The Platform Standards Layer is a primary production control surface.

Production requirements:

- standards catalog stored in versioned repository with change approval workflow
- mandatory review for changes affecting compliance or agent safety behavior
- per-tenant profile assignment with centrally enforced mandatory baseline rules
- standards profile version attached to deployment records and audit events

---

## Hosting Infrastructure

**Decision needed:** Which EU-sovereign infrastructure to run the managed service on.

| Provider | Jurisdiction | Kubernetes | GPU | Notes |
|---|---|---|---|---|
| SURF ResearchCloud | Netherlands | Yes | A100 | Academic/health research focus; strong NL credibility |
| OVHcloud | France/EU | Managed k8s | A100 | GDPR-compliant, CISPE certified |
| Hetzner | Germany | k3s | No | Cost-effective; no managed GPU |
| TransIP | Netherlands | Own k8s | No | Dutch provider, good NL latency |
| Leaseweb | Netherlands | Dedicated + k8s | Yes | Strong NL presence |

Consider: multi-provider for resilience vs single-provider for simplicity. SURF partnership recommended for Phase 1 given NL healthcare context.

---

## Key Management — HSM

POC uses software keys via OpenBao. Production will likely require an HSM for:
- UZI-pas PKI operations
- PKIoverheid compliance
- NEN 7510 key management controls

**Action:** Evaluate HSM options (Thales Luna, AWS CloudHSM equivalent on EU infra, SoftHSM as intermediate step) before production launch.

Key management must be HSM-ready by design — the OpenBao configuration uses a transit secrets engine that can be backed by HSM without application changes.

---

## High Availability

POC: single-node Docker Compose.

Production targets:
- 3-node Kubernetes control plane
- 3+ worker nodes per workload type
- FHIR server: active-passive with shared PostgreSQL (Patroni)
- PostgreSQL: Patroni HA cluster (3 nodes)
- MinIO: distributed mode (4+ nodes)
- Keycloak: 2+ replicas with shared DB
- 99.5% uptime SLA target

---

## Backup and Disaster Recovery

- PostgreSQL: continuous WAL archiving + daily base backups (Barman or pgBackRest)
- MinIO: replication to secondary bucket in separate AZ or provider
- FHIR data: FHIR Bulk Data export + encrypted offsite archive
- Audit logs: immutable WORM storage, separate from primary cluster
- RTO target: < 4 hours; RPO target: < 1 hour

---

## Network and Connectivity

- Dedicated private network between platform nodes (no public internet between services)
- Private peering or VPN for tenants with systems that need to connect to the platform
- DDoS protection at ingress (Cloudflare or equivalent EU provider)
- DigiD and eHerkenning require PKIoverheid certificate and specific IP allowlisting with Logius

---

## Capacity Planning

Baseline per 10 tenants (mid-size GP cooperative each):
- 6 vCPU / 12GB RAM for FHIR servers
- 2 vCPU / 4GB RAM for Keycloak
- 500GB storage (FHIR data + documents + audit logs)
- 1 GPU node shared for LLM inference (A10 or A30 sufficient for 7B model)

Scale estimates to be validated during POC load testing.

---

## Certification Path

- **NEN 7510 gap assessment** — engage NEN-certified auditor; typically 2-4 weeks
- **ISO 27001** — 6-12 months from gap assessment to certification; requires ISMS documentation
- **PKIoverheid** — required for DigiD/eHerkenning production access; apply via Logius
- **DigiD production access** — requires security assessment (DigiD beveiligingsassessment) by certified party

Start certification process no later than 3 months before planned Phase 1 production launch.
