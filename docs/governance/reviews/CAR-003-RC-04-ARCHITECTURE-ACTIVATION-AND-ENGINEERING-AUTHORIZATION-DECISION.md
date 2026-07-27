# CAR-003 — RC-04 Architecture Activation and Engineering Authorization Decision

**Document ID:** CAR-003
**Title:** RC-04 Architecture Activation and Engineering Authorization Decision
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Review Package
**Owner:** Chief Architect
**Prepared By:** Repository Governance Team
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/reviews/CAR-003-RC-04-ARCHITECTURE-ACTIVATION-AND-ENGINEERING-AUTHORIZATION-DECISION.md`
**Workflow Stage:** Repository Publication
**Decision:** Approved
**Decision Date:** 2026-07-27
**Authoritative Branch:** `develop`
**Implementation Authorization:** None
**Runtime Authority:** None
**Provider Endpoint Invocation Authority:** None
**Persistence Authority:** None
**Provider-to-Instrument Submission Authority:** None
**Product Activation Authority:** None

---

# 1. Purpose

This controlled record publishes the already-approved RC-04 Chief Architect governance decision.

It makes the repository authoritative for the activation of the approved ADR-009 architecture, the operational canonical status of EAIC-002, the constrained authorization of the Engineering Programme, and the constrained authorization of EDD-004 Draft Preparation.

This record does not review, redesign, amend, reinterpret, or replace architecture or engineering content.

# 2. Reviewed Repository Baseline

The Chief Architect decision was made against the repository state established after:

- completed ADR-009 coordinated architecture migration;
- completed RC-02 engineering architecture publication;
- completed RC-03 repository synchronization;
- successful MIG-001 migration measures MSM-001 through MSM-010;
- publication of ADR-009 Version 1.0;
- publication of EAIC-002 Version 0.1;
- publication of EAP-002 Version 2.0;
- publication of EAP-003 Version 2.0;
- publication of EAP-004 Version 2.0;
- publication of EAP-005 Version 1.1; and
- publication of EAP-006 Version 1.1.

# 3. Chief Architect Decisions

The approved RC-04 outcomes are:

| Decision area | Approved outcome |
|---|---|
| Architecture Programme | Accepted |
| Repository | Ready |
| ADR-009 | Operational Architecture |
| EAIC-002 | Operational Canonical Provider → Instrument Contract |
| Engineering Programme | Authorized with Constraints |
| EDD-004 Draft Preparation | Approved with Constraints |

# 4. Activation Effect

RC-04 activates ADR-009 as the operational architecture for the approved Provider-bounded Instrument Master acquisition boundary.

RC-04 activates EAIC-002 as the operational canonical Provider → Instrument contract for architectural and Engineering Design authority.

`Operational` in this decision describes active canonical architecture and engineering authority. It does not authorize runtime execution, live Provider communication, endpoint invocation, acquisition, persistence, Provider-to-Instrument submission, Instrument interpretation, product consumption, or deployment.

# 5. Engineering Authorization

The Engineering Programme may proceed only within the activated canonical architecture and published engineering baseline.

EDD-004 Draft Preparation is authorized with the following constraints:

1. EDD-004 is Engineering Design only.
2. EDD-004 shall remain subordinate to ADR-009, EAIC-002, MIG-001, EAP-001, EAP-002, EAP-003, EAP-004, EAP-005, EAP-006, and applicable approved domain and governance authority.
3. EDD-004 shall remain Provider-neutral, product-neutral, dataset-specific, compatible with Kite as the first adapter, compatible with future Providers, retention-aware, provenance-preserving, and bounded before Instrument interpretation.
4. EDD-004 shall not define Swing or Intraday eligibility.
5. EDD-004 shall not redesign Provider, Instrument, Observation, or product ownership.
6. EDD-004 shall not redesign EAIC-002 or any other canonical contract.
7. EDD-004 shall not create implementation, runtime, endpoint, acquisition, persistence, submission, interpretation, product-consumption, deployment, scheduling, retry, API, database, GUI, commit, or push authority.
8. EDD-004 approval and canonicalization remain separate future governance decisions.
9. Any implementation activity requires separate explicit Implementation Authorization after canonical EDD-004 approval.

The governed Authorization State for EDD-004 is `Draft Authorized`.

# 6. Authority Separation

The following states remain unchanged:

| Authority | State after RC-04 |
|---|---|
| EDD-004 Draft Preparation | Approved with Constraints |
| EDD-004 canonicalization | None |
| Implementation Authorization | None |
| Runtime Authority | None |
| Provider Endpoint Invocation Authority | None |
| Live Acquisition Authority | None |
| Persistence Authority | None |
| Retention implementation authority | None |
| Deletion Authority | None |
| Provider-to-Instrument Submission Authority | None |
| Instrument Interpretation Runtime Authority | None |
| Product Consumption Authority | None |
| Product Activation Authority | None |
| GUI Authority | None |

No authority in this table implies another.

# 7. Repository Publication Effect

Publication of this record:

- satisfies MIG-001 measure MSM-011;
- closes RC-04 Activation Governance;
- records ADR-009 as active Operational Architecture;
- records EAIC-002 as the active Operational Canonical Provider → Instrument Contract;
- records EAP-002 through EAP-006 as the active Engineering Design baseline;
- records the Engineering Programme as Authorized with Constraints; and
- records EDD-004 Draft Preparation as Approved with Constraints.

RC-04A is a repository-publication work package only. It introduces no architectural, engineering, implementation, or runtime content.

# 8. Approval Record

**Chief Architect Decision:** Approved

**Architecture Programme:** Accepted

**Repository:** Ready

**ADR-009 Activation State:** Active — Operational Architecture

**EAIC-002 Activation State:** Active — Operational Canonical Contract

**Engineering Programme:** Authorized with Constraints

**EDD-004 Authorization State:** Draft Authorized

**EDD-004 Drafting Authorization:** Approved with Constraints

**EDD-004 Canonicalization Authorization:** None

**Implementation Authorization:** None

**Runtime Authority:** None

**Provider Endpoint Invocation Authority:** None

**Persistence Authority:** None

**Provider-to-Instrument Submission Authority:** None

**Commit Authorization:** Approved — RC-04A Governance Publication Only

**Push Authorization:** Approved — RC-04A Governance Publication Only

# 9. Related Authority

- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../../architecture/platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../../architecture/interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../architecture/migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [EAP-002 — Provider Instrument Master Acquisition](../../engineering/eap/EAP-002-PROVIDER-INSTRUMENT-MASTER-ACQUISITION.md)
- [EAP-003 — Provider-to-Instrument Submission Validation and Interpretation Admission](../../engineering/eap/EAP-003-PROVIDER-TO-INSTRUMENT-ARCHITECTURAL-ADMISSIBILITY.md)
- [EAP-004 — Instrument Interpretation and Canonical Identity Establishment](../../engineering/eap/EAP-004-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT.md)
- [EAP-005 — Instrument-to-Observation Attribution Eligibility](../../engineering/eap/EAP-005-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY.md)
- [EAP-006 — Observation Acceptance and Governed Observation Establishment](../../engineering/eap/EAP-006-OBSERVATION-ACCEPTANCE-AND-GOVERNED-OBSERVATION-ESTABLISHMENT.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)

# End of Document
