# DOCUMENT REGISTER

**Document ID:** IDX-001
**Title:** KRONOS Document Register
**Version:** 0.1 Draft
**Status:** Active
**Classification:** Repository Index
**Owner:** Chief Architect Office
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Maintained By:** Engineering Architect / Lead Engineer
**Repository Location:** `docs/indexes/DOCUMENT-REGISTER.md`

---

# 1. Purpose

The KRONOS Document Register is the authoritative inventory of all controlled repository documents.

Its objectives are to:

- maintain visibility of documentation progress;
- prevent duplicate documents;
- identify engineering blockers;
- track document lifecycle;
- provide a single source of documentation status;
- support repository governance.

Every controlled document shall appear in this register.

---

# 2. Status Definitions

| Status | Meaning |
|---------|---------|
| Planned | Approved for creation but not started |
| Draft | Under preparation |
| Engineering Verification | Under Engineering Architect review |
| Chief Architect Review | Under independent review |
| Amendment Required | Changes requested |
| Approved | Architecturally approved |
| Canonical | Official repository version |
| Deferred | Intentionally postponed |
| Retired | No longer active |

---

# 3. Priority Definitions

| Priority | Meaning |
|-----------|---------|
| P0 | Blocks Engineering |
| P1 | Required During Engineering |
| P2 | Post Engineering / Future Enhancement |

---

# 4. P0 — Engineering Blocking Documents

| ID | Document | Category | Priority | Status | Owner | Repository Location | Remarks |
|----|----------|----------|----------|--------|-------|---------------------|---------|
| GOV-001 | Governance Constitution | Governance | P0 | Chief Architect Review | Chief Architect | `docs/governance/constitutions/` | Draft v0.1 Complete |
| GOV-002 | Governance Lifecycle | Governance | P0 | Draft | Engineering Architect | `docs/governance/lifecycle/` | In Progress |
| CAR-001 | Governance Foundation Review | Review | P0 | Chief Architect Review | Chief Architect | `docs/governance/reviews/CAR-001-GOVERNANCE-FOUNDATION-REVIEW.md` | Draft v0.1 |
| CAR-002 | Governance Foundation Closure Review | Review | P0 | Engineering Verification | Chief Architect | `docs/governance/reviews/CAR-002-GOVERNANCE-FOUNDATION-CLOSURE-REVIEW.md` | Draft v0.1 |
| DOC-001 | Document Identification, Classification & Metadata Standard | Governance | P0 | Draft | Chief Architect | `docs/governance/documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md` | Draft v0.1 |
| EAS-001 | Engineering Architecture Framework | Engineering | P0 | Draft | Engineering Architect | `docs/engineering/eap/EAS-001-ENGINEERING-ARCHITECTURE-FRAMEWORK.md` | Draft v0.1 |
| EAS-002 | Repository Engineering Standards | Engineering | P0 | Draft | Engineering Architect | `docs/engineering/eap/EAS-002-REPOSITORY-ENGINEERING-STANDARDS.md` | Draft v0.1 |
| EAS-003 | Interface & Dependency Standards | Engineering | P0 | Planned | Engineering Architect | `docs/engineering/eap/` | |
| EAS-004 | Domain Engineering Standards | Engineering | P0 | Planned | Engineering Architect | `docs/engineering/eap/` | |
| EAS-005 | Engineering Verification & Conformance | Engineering | P0 | Planned | Engineering Architect | `docs/engineering/eap/` | |
| EAS-006 | Engineering Delivery Workflow | Engineering | P0 | Planned | Engineering Architect | `docs/engineering/eap/` | |
| EAP-001 | Configuration-to-Provider Authenticated Context | Engineering | P0 | Approved | Engineering Architect | `docs/engineering/eap/EAP-001-CONFIGURATION-TO-PROVIDER-AUTHENTICATED-CONTEXT.md` | Canonical Version 1.0 |
| EAP-002 | Provider Instrument Master Acquisition | Engineering | P0 | Draft | Engineering Architect | `docs/engineering/eap/EAP-002-PROVIDER-INSTRUMENT-MASTER-ACQUISITION.md` | Draft v0.1 |
| EAP-003 | Provider-to-Instrument Architectural Admissibility | Engineering | P0 | Approved | Engineering Architect | `docs/engineering/eap/EAP-003-PROVIDER-TO-INSTRUMENT-ARCHITECTURAL-ADMISSIBILITY.md` | Approved Canonical Engineering Architecture Version 1.0 |

---

# 5. P1 — Engineering Supporting Documents

| ID | Document | Category | Priority | Status | Owner | Repository Location | Remarks |
|----|----------|----------|----------|--------|-------|---------------------|---------|

---

# 6. P2 — Future Documentation

| ID | Document | Category | Priority | Status | Owner | Repository Location | Remarks |
|----|----------|----------|----------|--------|-------|---------------------|---------|

---

# 7. Completed Documents

Move documents here only after they become **Canonical**.

| ID | Document | Version | Canonical Date | Remarks |
|----|----------|---------|----------------|---------|

---

# 8. Deferred Documents

| ID | Document | Reason | Review Date |
|----|----------|--------|-------------|

---

# 9. Retired Documents

| ID | Document | Superseded By | Retirement Date |
|----|----------|---------------|-----------------|

---

# 10. Register Maintenance Rules

1. Every controlled document shall have a unique Document ID.
2. Every controlled document shall be entered into this register when created.
3. Document status shall be updated whenever its lifecycle changes.
4. Documents shall only move to **Completed** after Canonical status.
5. Deferred and Retired documents shall remain permanently listed for traceability.
6. No controlled document shall exist outside this register.
7. The Engineering Architect is responsible for updating this register during document creation.
8. The Lead Engineer shall ensure repository consistency.
9. The Chief Architect remains the approval authority for document lifecycle transitions.

---

# End of Document
