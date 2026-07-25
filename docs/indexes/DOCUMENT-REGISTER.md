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
| DOC-001 | Document Identification, Classification & Metadata Standard | Governance | P0 | Approved | Chief Architect | `docs/governance/documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md` | Version 1.0; Canonical; EG-001 complete; EDD recognition included |
| EAS-001 | Engineering Architecture Framework | Engineering | P0 | Approved | Engineering Architect | `docs/engineering/eap/EAS-001-ENGINEERING-ARCHITECTURE-FRAMEWORK.md` | Version 1.0; Canonical; completion and review authorized; EAS-001 canonicalized |
| EAS-002 | Repository Engineering Standards | Engineering | P0 | Approved | Engineering Architect | `docs/engineering/eap/EAS-002-REPOSITORY-ENGINEERING-STANDARDS.md` | Version 1.0; Canonical |
| EAS-003 | Engineering Package and Dependency Standards | Engineering | P0 | Approved | Engineering Architect | `docs/engineering/eap/EAS-003-ENGINEERING-PACKAGE-AND-DEPENDENCY-STANDARDS.md` | Version 1.0; Canonical |
| EAS-004 | Domain Engineering Standards | Engineering | P0 | Planned | Engineering Architect | `docs/engineering/eap/` | Drafting/completion authorized; not approved; not canonical |
| EAS-005 | Engineering Verification & Conformance | Engineering | P0 | Planned | Engineering Architect | `docs/engineering/eap/` | Drafting/completion authorized; not approved; not canonical |
| EAS-006 | Engineering Delivery Workflow | Engineering | P0 | Planned | Engineering Architect | `docs/engineering/eap/` | Drafting/completion authorized; not approved; not canonical |
| EAS-007 | Engineering Design Document Governance Standard | Engineering | P0 | Planned | Engineering Architect | `docs/engineering/standards/EAS-007-ENGINEERING-DESIGN-DOCUMENT-GOVERNANCE-STANDARD.md` | Drafting authorized; not approved; not canonical; final location subject to repository-organization review |
| EAP-001 | Configuration-to-Provider Authenticated Context | Engineering | P0 | Approved | Engineering Architect | `docs/engineering/eap/EAP-001-CONFIGURATION-TO-PROVIDER-AUTHENTICATED-CONTEXT.md` | Version 1.0; Approved Canonical Engineering Architecture; ADR Required: No |
| EAP-002 | Provider Instrument Master Acquisition | Engineering | P0 | Approved | Engineering Architect | `docs/engineering/eap/EAP-002-PROVIDER-INSTRUMENT-MASTER-ACQUISITION.md` | Version 1.0; Approved Canonical Engineering Architecture; ADR Required: No |
| EAP-003 | Provider-to-Instrument Architectural Admissibility | Engineering | P0 | Approved | Engineering Architect | `docs/engineering/eap/EAP-003-PROVIDER-TO-INSTRUMENT-ARCHITECTURAL-ADMISSIBILITY.md` | Version 1.0; Approved Canonical Engineering Architecture; ADR Required: No; Governing ADP: ADP-001C; Supporting ADPs: ADP-001A, ADP-001B, ADP-001H, ADP-001I; Engineering Impact: None; Runtime Impact: None; Implementation Authorization: None; EDD Authorization: None |
| EAP-004 | Instrument Interpretation and Canonical Identity Establishment Engineering Architecture | Engineering | P0 | Approved | Engineering Architect | `docs/engineering/eap/EAP-004-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT.md` | Version 1.0; Approved Canonical Engineering Architecture; Governing ADP: ADP-001J Version 1.0; Supporting ADPs: ADP-001A, ADP-001B, ADP-001C, ADP-001D, ADP-001E, ADP-001H, ADP-001I; Upstream EAP: EAP-003 Version 1.0; ADR Required: No; Engineering Impact: None; Runtime Impact: None; EDD Authorization: None; Implementation Authorization: None |
| EAP-005 | Instrument-to-Observation Attribution Eligibility Engineering Architecture | Engineering | P0 | Approved | Engineering Architect | `docs/engineering/eap/EAP-005-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY.md` | Version 1.0; Approved Canonical Engineering Architecture; Governing ADP: ADP-001D Version 1.0; Supporting ADPs: ADP-001A, ADP-001B, ADP-001C, ADP-001E, ADP-001H, ADP-001I, ADP-001J; Upstream EAP: EAP-004 Version 1.0; ADR Required: No; Engineering Impact: None; Runtime Impact: None; EDD Authorization: None; Implementation Authorization: None |
| EAP-006 | Observation Acceptance and Governed Observation Establishment Engineering Architecture | Engineering | P0 | Approved | Engineering Architect | `docs/engineering/eap/EAP-006-OBSERVATION-ACCEPTANCE-AND-GOVERNED-OBSERVATION-ESTABLISHMENT.md` | Version 1.0; Approved Canonical Engineering Architecture; Governing ADP: ADP-001E Version 1.0; Immediate Upstream EAP: EAP-005 Version 1.0; ADR Required: No; EDD Authorization: None; Implementation Authorization: None |
| EDD-001 | Kite Authentication and Session Management Engineering Design | Engineering | P0 | Planned | Engineering Architect | `docs/engineering/edd/EDD-001-KITE-AUTHENTICATION-AND-SESSION-MANAGEMENT-ENGINEERING-DESIGN.md` | Reserved; Drafting Not Yet Authorized; Governing EAP: EAP-001; Implementation Authority: None; file not created |
| ADP-001J | Instrument Interpretation and Canonical Identity Establishment Architecture | Product Architecture | P0 | Approved | Chief Architect | `docs/architecture/products/swing/SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md` | Version 1.0; Approved Canonical Architecture; Approved By: Chief Architect; ADR Required: No; Implementation Authority: None; Engineering Architecture Authority: None; EDD Authority: None; Runtime Authority: None |

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
