# Open Questions

**Version:** 0.4 (Draft)
**Date:** 2026-03-12

---

**OQ-1: Which FHIR Implementation Guides to build first?**
For POC, a single Zib-profiled FHIR server suffices without committing to a full IG. Prioritization needed before Phase 1 production:
1. Zib 2024 + BgZ (foundation)
2. MedMij (patient portal)
3. Twiin (inter-provider referral)
4. eOverdracht (care transfer)

---

**OQ-2: BSN handling — pseudonymization strategy**
Option (c) preferred (never store BSN; use DigiD/UZI opaque identifier). Not required for POC. Needs legal/privacy review before production.

---

**OQ-3: NUTS network integration**
Revisit after POC. NUTS adoption is growing; include as optional integration in Phase 1 production.

---

**OQ-4: Medical device regulation (MDR) scope**
Validate before any clinical decision support feature goes live. Platform is infrastructure; app owners take MDR responsibility. Needs legal opinion.

---

**OQ-5: Pilot partner selection**
To be validated. Recommended starting point: GP cooperative (HAP) or public health service (GGD) — lower MDR complexity than hospital.

---

**OQ-6: Agent memory and conversation persistence**
Keep session-scoped by default. Persistent memory optional per tenant. Revisit governance model before enabling in production.

---

**OQ-7: Synthetic patient data generation**
Decide whether this is a platform-level service or left to each application. If platform-level: build on Synthea with Dutch Zib profiles. Required before any realistic POC testing with clinical data.
