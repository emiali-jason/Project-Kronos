# CAR-006 — EDD-006 ES-01 Draft Preparation Authorization Decision

**Document ID:** CAR-006<br>
**Title:** EDD-006 ES-01 Draft Preparation Authorization Decision<br>
**Version:** 1.1<br>
**Status:** Approved<br>
**Canonical Status:** Canonical<br>
**Classification:** Review Package<br>
**Owner:** Chief Architect<br>
**Prepared By:** Repository Governance Team<br>
**Review Authority:** Chief Architect<br>
**Repository Location:** `docs/governance/reviews/CAR-006-EDD-006-ES-01-DRAFT-PREPARATION-AUTHORIZATION-DECISION.md`<br>
**Workflow Stage:** Repository Publication<br>
**Decision Status:** APPROVED<br>
**Decision:** AUTHORIZE WITH CONSTRAINTS<br>
**Decision Date:** 2026-07-28<br>
**Repository Status:** Published<br>
**Authoritative Branch:** `develop`<br>
**Target Document:** EDD-006 — Instrument Identity Engineering Design<br>
**Direct Engineering Architecture:** EAP-004 Version 2.0<br>
**Prior Canonical Version:** 1.0<br>
**Prior Canonical Decision:** ES-01 Draft Preparation only<br>
**Canonical Baseline:** Version 1.1 supersedes Version 1.0 as the canonical CAR-006 authority<br>
**EDD-006 Draft Authorization:** ES-02 through ES-05, subject to sequential stage gates<br>
**Implementation Authority:** None<br>
**Runtime Authority:** None

---

# Version 1.0 Canonical Decision — Preserved

Sections 1 through 7 preserve the approved and published Version 1.0 decision unchanged as historical authority. Section 8 is the approved Version 1.1 amendment and controls where it extends the Version 1.0 stage limit.

# 1. Purpose

This controlled decision records the minimum repository-governed authority required before EDD-006 may be created.

It contains no EDD-006 Engineering Scope Definition, Engineering Discovery, architecture redesign, capability decomposition, building-block architecture, interface architecture, implementation design, or runtime design.

# 2. Existing Governance Mechanism

[EAS-007 — Engineering Design Document Governance Standard](../../engineering/eap/EAS-007-ENGINEERING-DESIGN-DOCUMENT-GOVERNANCE-STANDARD.md) requires a separate Chief Architect EDD Authorization before a specific EDD may be created.

[DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md) requires Draft Authorization to be recorded independently and requires every new controlled authority to use an approved document family, identifier, metadata, repository location, and Document Register entry.

The existing repository mechanism is therefore a Chief Architect decision recorded as a `CAR` Review Package. No new governance mechanism or document family is introduced.

# 3. Repository Basis

[EAP-004 Version 2.0 — Instrument Interpretation and Canonical Identity Establishment Engineering Architecture](../../engineering/eap/EAP-004-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT.md) is the approved canonical and active Engineering Architecture baseline for EDD-006.

EDD-006 shall be an implementation-independent Engineering Design translation of EAP-004. It shall not amend, reinterpret, broaden, narrow, replace, or redesign EAP-004 or any other approved architecture.

No current repository authority authorizes creation of EDD-006 or its ES-01 Draft Preparation.

# 4. Authorization

This approved and published decision authorizes Engineering to:

- create EDD-006 Version 0.1 Draft;
- perform ES-01 Engineering Scope Definition only; and
- prepare ES-01 for Engineering Review and Chief Architect review.

The authorization terminates at completion of the ES-01 Draft. It does not authorize ES-02 or any later Engineering stage.

# 5. Constraints

EDD-006 ES-01 shall:

1. derive solely from EAP-004 and its approved governing authorities;
2. remain subordinate to approved architecture, contracts, domain ownership, and EAS-001 through EAS-007;
3. preserve the complete EAP-004 boundary, ownership model, dependencies, constraints, and exclusions;
4. define Engineering scope only;
5. introduce no Architecture Discovery or architecture redesign; and
6. introduce no implementation, runtime, persistence, scheduling, deployment, GUI, product logic, or technology choice.

# 6. Authority State

- **EDD-006 Draft Authorization:** ES-01 Draft Preparation only;
- **Engineering Authority:** Engineering Scope Definition only;
- **Implementation Authority:** None; and
- **Runtime Authority:** None.

Approval of this decision shall not predetermine approval, canonicalization, publication, implementation, or runtime activation of EDD-006.

# 7. Chief Architect Decision

**AUTHORIZE WITH CONSTRAINTS**

Authorize EDD-006 ES-01 Draft Preparation only as an Engineering Design translation of EAP-004 Version 2.0, subject to the constraints in this decision.

This decision is effective through its approved controlled repository publication.

# 8. Version 1.1 Amendment — Engineering Lifecycle Authorization

## 8.1 Amendment Purpose

This controlled minor amendment records the smallest change required to extend EDD-006 Draft Preparation authority beyond the completed ES-01 stage.

It does not amend EAP-004, change EDD-006 engineering scope, introduce architecture, or create implementation or runtime authority.

CAR-006 Version 1.0 remains preserved as historical authority. Version 1.1 is the canonical CAR-006 authority for the remaining EDD-006 Engineering Stages.

## 8.2 Authorization

This approved and published amendment authorizes Draft Preparation for:

1. ES-02 — Engineering Capability Decomposition;
2. ES-03 — Engineering Building Block Architecture;
3. ES-04 — Engineering Interface Architecture; and
4. ES-05 — Independent Engineering Verification.

Each stage shall remain an implementation-independent Engineering Design translation of EAP-004 Version 2.0. EAP-004 remains the sole direct Engineering Architecture authority for EDD-006.

## 8.3 Sequential Stage Gates

The authorization is sequential and conditional:

1. each Engineering Stage shall derive from the preceding approved and published EDD-006 repository version;
2. each Engineering Stage shall complete Chief Systems Engineer review;
3. each Engineering Stage shall complete Chief Architect approval;
4. each approved Engineering Stage shall be published and frozen before the next Engineering Stage begins; and
5. Version 1.0 publication shall occur only after ES-05 completion, Engineering Verification, Chief Architect approval, and separately governed repository publication.

No stage approval is predetermined by this amendment. Failure to complete a required gate leaves every subsequent Engineering Stage unauthorized.

## 8.4 Preserved Constraints

The Version 1.0 constraints remain unchanged and apply to ES-02 through ES-05.

This amendment:

- preserves EAP-004 Version 2.0 as the sole direct Engineering Architecture authority;
- authorizes no architectural amendment, reinterpretation, extension, replacement, or discovery;
- authorizes no implementation, production code, persistence, deployment, or technology choice;
- preserves **Implementation Authority: None**;
- preserves **Runtime Authority: None**; and
- changes no domain ownership, contract boundary, dependency direction, or approved engineering meaning.

## 8.5 Chief Architect Decision

**AUTHORIZE WITH CONSTRAINTS**

Authorize sequential EDD-006 ES-02 through ES-05 Draft Preparation subject to the stage gates and preserved constraints in this amendment.

This decision is effective through its approved controlled repository publication as CAR-006 Version 1.1.
