# CAR-007 — EDD-007 Engineering Design Authorization Decision

**Document ID:** CAR-007<br>
**Title:** EDD-007 Engineering Design Authorization Decision<br>
**Version:** 1.0<br>
**Status:** Approved<br>
**Canonical Status:** Canonical<br>
**Classification:** Review Package<br>
**Owner:** Chief Architect<br>
**Prepared By:** Repository Governance Team<br>
**Review Authority:** Chief Architect<br>
**Repository Location:** `docs/governance/reviews/CAR-007-EDD-007-ENGINEERING-DESIGN-AUTHORIZATION-DECISION.md`<br>
**Workflow Stage:** Repository Publication<br>
**Decision Status:** APPROVED<br>
**Decision:** AUTHORIZE WITH CONSTRAINTS<br>
**Repository Status:** Ready for Publication<br>
**Authoritative Branch:** `develop`<br>
**Target Document:** EDD-007 — Instrument-to-Observation Attribution Eligibility Engineering Design<br>
**Direct Engineering Architecture:** EAP-005 Version 1.1<br>
**EDD-007 Draft Authorization:** ES-01 through ES-05, subject to sequential stage gates<br>
**Architecture Authority:** None<br>
**Implementation Authority:** None<br>
**Runtime Authority:** None

---

# 1. Purpose

This decision records the minimum repository-governed authority required before EDD-007 Engineering Design may begin.

The authorization is limited to implementation-independent Engineering Design derived exclusively from EAP-005 Version 1.1. It creates no architecture, implementation, runtime, communication, persistence, deployment, or operational authority.

This decision contains no EDD-007 Engineering Scope Definition, capability decomposition, Building Block Design, Interface Design, implementation design, or Engineering Verification result.

# 2. Existing Governance Mechanism

[EAS-007 — Engineering Design Document Governance Standard](../../engineering/eap/EAS-007-ENGINEERING-DESIGN-DOCUMENT-GOVERNANCE-STANDARD.md) requires a separate Chief Architect authorization before a specific EDD may be created.

[DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md) requires Draft Authorization to remain distinct from EDD content and requires every controlled document to use an approved identity, classification, metadata set, repository location, and Document Register entry.

The existing repository mechanism is a Chief Architect decision recorded as a `CAR` Review Package. CAR-007 uses that existing mechanism and introduces no new governance concept, authority layer, document family, or repository structure.

# 3. Repository Basis

[EAP-005 Version 1.1 — Instrument-to-Observation Attribution Eligibility Engineering Architecture](../../engineering/eap/EAP-005-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY.md) is the sole direct, approved, canonical, and active Engineering Architecture baseline for EDD-007.

EDD-007 shall be an implementation-independent Engineering Design translation of EAP-005 Version 1.1. It shall not amend, reinterpret, broaden, narrow, replace, or redesign EAP-005 or any other approved architecture.

The architecture and governance documents referenced by EAP-005 remain applicable only through the authority and boundaries already established by EAP-005. They do not create an additional or competing direct Engineering Architecture authority for EDD-007.

[EDD-006 Version 1.0 — Instrument Identity Engineering Design](../../engineering/edd/EDD-006-INSTRUMENT-IDENTITY-ENGINEERING-DESIGN.md) is the completed upstream Engineering Design. Its Instrument Identity Contract boundary is available to EDD-007 only as governed by EAP-005. EDD-006 completion does not authorize EDD-007.

No prior repository authority authorized creation of EDD-007 or preparation of any EDD-007 Engineering Stage. CAR-007 supplies that specific authority subject to controlled publication and the sequential gates below.

# 4. Target Document

The controlled Engineering Design Document is:

- **Document ID:** EDD-007;
- **Title:** Instrument-to-Observation Attribution Eligibility Engineering Design;
- **Classification:** Engineering Design Document;
- **Owner:** Engineering Architect;
- **Prepared By:** Engineering Design Team;
- **Review Authority:** Chief Architect;
- **Engineering Review Authority:** Chief Systems Engineer;
- **Direct Engineering Architecture:** EAP-005 Version 1.1;
- **Implementation Authority:** None; and
- **Runtime Authority:** None.

CAR-007 authorizes creation of the controlled EDD-007 identity and metadata as part of this publication package. It does not authorize ES-01 to begin before CAR-007 and the controlled identity are published and synchronized to `develop`.

# 5. Authorization

Upon controlled repository publication, CAR-007 authorizes:

1. creation of EDD-007 Version 0.1 Draft;
2. sequential preparation of ES-01 through ES-05;
3. Chief Systems Engineer review of every Engineering Stage;
4. Chief Architect approval of every Engineering Stage;
5. controlled publication and freezing of each approved Engineering Stage; and
6. preparation for Version 1.0 publication only after successful ES-05 Engineering Verification.

The authorization permits Engineering Design only. It does not predetermine approval of any Engineering Stage, Engineering Verification result, canonicalization, Version 1.0 publication, implementation, or runtime activity.

# 6. Authorized Engineering Mission

EDD-007 shall be authorized to translate EAP-005 Version 1.1 into implementation-independent Engineering Design for the bounded Instrument-to-Observation Attribution Eligibility responsibility.

The Engineering Design may address only the EAP-005 meanings for:

- Attribution Evaluation Readiness;
- bounded Attribution Evaluation;
- Attribution Outcome;
- Attribution Eligible and Attribution Ineligible;
- attribution-ineligibility reasons;
- canonical Instrument identity association;
- candidate factual information association;
- provenance, attribution, source, and temporal continuity;
- uncertainty, ambiguity, partiality, failure, and unavailability preservation;
- effective identity-context preservation;
- Observation Participation Eligibility;
- boundary conformance and violations;
- non-sensitive observability; and
- Engineering Verification.

This mission identifies the authorized Engineering Design subject only. It does not define Engineering responsibilities, capabilities, Building Blocks, interfaces, modules, data structures, algorithms, or implementation.

# 7. Authorized Boundary

## 7.1 Beginning

EDD-007 shall begin only with the EAP-005-governed combination of:

- one approved Instrument Identity Contract supplied through the completed EDD-006 boundary; and
- source-neutral candidate factual information with its applicable source, provenance, temporal, uncertainty, ambiguity, partiality, failure, unavailability, and limitation context.

EDD-007 shall not recreate, reinterpret, remap, modify, or acquire ownership of canonical Instrument identity. It shall not create acquisition, Provider communication, or factual ownership authority.

## 7.2 Ending

EDD-007 shall end with:

- Observation Participation Eligibility meaning; or
- preserved Attribution Ineligibility meaning and its governed reason or reasons.

The boundary terminates before Candidate Observation construction, Observation Acceptance, Observation ownership, governed Observation establishment, factual correctness determination, and Observation publication.

EAP-006 Version 1.1 remains the downstream Engineering Architecture. EDD-007 shall not perform or design EAP-006 responsibilities.

# 8. Sequential Engineering Stage Gates

The authorization shall be sequential and conditional.

## 8.1 ES-01 — Engineering Scope Definition

ES-01 may begin only after CAR-007 is approved, published, and synchronized to `develop`.

ES-01 shall complete:

1. Chief Systems Engineer review;
2. Chief Architect approval;
3. controlled repository publication; and
4. freezing as the authoritative EDD-007 scope baseline.

ES-02 remains unauthorized until all ES-01 gates are complete.

## 8.2 ES-02 — Engineering Capability Design

ES-02 shall derive only from the approved and published ES-01 baseline and EAP-005 Version 1.1.

ES-02 shall complete Chief Systems Engineer review, Chief Architect approval, controlled publication, and freezing before ES-03 begins.

## 8.3 ES-03 — Engineering Building Block Design

ES-03 shall derive only from the approved and published ES-01 and ES-02 baselines and EAP-005 Version 1.1.

ES-03 shall complete Chief Systems Engineer review, Chief Architect approval, controlled publication, and freezing before ES-04 begins.

## 8.4 ES-04 — Engineering Interface Design

ES-04 shall derive only from the approved and published ES-01 through ES-03 baselines and EAP-005 Version 1.1.

ES-04 shall complete Chief Systems Engineer review, Chief Architect approval, controlled publication, and freezing before ES-05 begins.

## 8.5 ES-05 — Independent Engineering Verification

ES-05 shall verify the approved and published ES-01 through ES-04 Engineering Design without redesigning it.

Version 1.0 preparation shall remain unauthorized until ES-05:

1. completes Independent Engineering Verification;
2. completes Chief Systems Engineer review;
3. records all engineering non-conformities;
4. receives Chief Architect approval; and
5. is published and frozen.

Version 1.0 canonicalization, publication, and repository synchronization require separate Chief Architect publication approval.

# 9. Preserved Constraints and Explicit Prohibitions

EDD-007 shall:

1. derive exclusively from EAP-005 Version 1.1 as its sole direct Engineering Architecture authority;
2. remain subordinate to approved repository governance, domain ownership, dependencies, and boundaries;
3. preserve Instrument ownership of canonical identity;
4. preserve Observation ownership of attribution authority and later governed factual meaning;
5. preserve candidate factual information without assigning premature Observation ownership;
6. preserve Attribution Evaluation Readiness as distinct from Attribution Outcome;
7. preserve exactly two Attribution Outcomes;
8. preserve uncertainty, ambiguity, partiality, failure, and unavailability without silent resolution;
9. terminate before Observation Acceptance and governed Observation establishment; and
10. remain provider-neutral and implementation-independent.

This authorization shall not authorize EDD-007 to define, perform, create, modify, or grant:

- architecture, architectural authority, or Architecture Discovery;
- changes to EAP-005 or any governing architecture;
- factual-data acquisition or Provider communication;
- canonical identity creation, resolution, reinterpretation, or mapping;
- lifecycle-transition mechanics;
- factual correction, normalization, enrichment, or correctness determination;
- Candidate Observation construction;
- Observation Acceptance, ownership, publication, or lifecycle;
- APIs, fields, schemas, payloads, serialization, protocols, or transports;
- algorithms, matching mechanics, or thresholds;
- persistence, caching, scheduling, retries, or orchestration;
- modules, services, classes, packages, or deployable components;
- implementation, production code, or test code;
- deployment, infrastructure, or technology selection;
- runtime behavior or runtime authority; or
- any downstream authority not expressly established by EAP-005.

# 10. Authority State

The approved authority state is:

- **EDD-007 Draft Authorization:** ES-01 through ES-05, sequential and conditional;
- **Engineering Authority:** Engineering Design only;
- **Architecture Authority:** None;
- **Implementation Authority:** None; and
- **Runtime Authority:** None.

The controlled EDD-007 identity and metadata may be created in this publication package. ES-01 may begin only after CAR-007 and the EDD-007 controlled identity are published and synchronized to `develop`.

Approval of CAR-007 does not predetermine approval, canonicalization, Version 1.0 publication, implementation, or runtime activation of EDD-007.

# 11. Chief Architect Decision

**AUTHORIZE WITH CONSTRAINTS**

Authorize sequential EDD-007 ES-01 through ES-05 Draft Preparation as an implementation-independent Engineering Design translation derived exclusively from EAP-005 Version 1.1, subject to every review, approval, publication, and freeze gate in this decision.

Preserve:

- **Architecture Authority:** None;
- **Implementation Authority:** None; and
- **Runtime Authority:** None.

This decision becomes effective through controlled repository publication of CAR-007. The controlled EDD-007 identity may be published with this decision, but ES-01 shall not begin until repository synchronization is complete.
