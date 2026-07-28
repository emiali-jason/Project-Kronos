# CAR-008 — EDD-008 Engineering Design Authorization Decision

**Document ID:** CAR-008<br>
**Title:** EDD-008 Engineering Design Authorization Decision<br>
**Version:** 1.0<br>
**Status:** Approved<br>
**Canonical Status:** Canonical<br>
**Classification:** Review Package<br>
**Owner:** Chief Architect<br>
**Prepared By:** Repository Governance Team<br>
**Review Authority:** Chief Architect<br>
**Repository Location:** `docs/governance/reviews/CAR-008-EDD-008-ENGINEERING-DESIGN-AUTHORIZATION-DECISION.md`<br>
**Workflow Stage:** Repository Publication<br>
**Decision Status:** APPROVED<br>
**Decision:** AUTHORIZE WITH CONSTRAINTS<br>
**Repository Status:** Published<br>
**Authoritative Branch:** `develop`<br>
**Target Document:** EDD-008 — Observation Acceptance and Governed Observation Establishment Engineering Design<br>
**Direct Engineering Architecture:** EAP-006 Version 1.2<br>
**Governing Architecture:** ADP-001E Version 1.1<br>
**Upstream Engineering Boundary:** EDD-007 Version 1.1<br>
**EDD-008 Draft Authorization:** ES-01 through ES-05, subject to sequential stage gates<br>
**Architecture Authority:** None<br>
**Implementation Authority:** None<br>
**Runtime Authority:** None

---

# 1. Purpose

This decision records the repository-governed authority required before EDD-008 Engineering Design may begin.

The authorization is limited to implementation-independent Engineering Design derived exclusively from:

- EAP-006 Version 1.2;
- ADP-001E Version 1.1;
- the completed EDD-007 Version 1.1 upstream Engineering Design boundary; and
- applicable approved repository governance.

CAR-008 contains no EDD-008 Engineering Design, responsibility decomposition, capability design, Building Block Design, interface design, or verification result.

# 2. Governance Basis

[EAS-007 — Engineering Design Document Governance Standard](../../engineering/eap/EAS-007-ENGINEERING-DESIGN-DOCUMENT-GOVERNANCE-STANDARD.md) requires separate Chief Architect authorization before a specific Engineering Design Document may be created.

[DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md) requires Draft Authorization to remain distinct from Engineering Design content and requires every controlled document to use approved identity, classification, metadata, repository location, lifecycle state, and Document Register governance.

CAR-008 uses the existing CAR Review Package mechanism. It introduces no new governance concept, authority layer, document family, or repository structure.

# 3. Repository Basis

[EAP-006 Version 1.2 — Observation Acceptance and Governed Observation Establishment Engineering Architecture](../../engineering/eap/EAP-006-OBSERVATION-ACCEPTANCE-AND-GOVERNED-OBSERVATION-ESTABLISHMENT.md) is the sole direct, approved, canonical, and active Engineering Architecture baseline for EDD-008.

[ADP-001E Version 1.1 — Observation Domain Architecture](../../architecture/products/swing/SWING-PHASE-1-OBSERVATION-DOMAIN-ARCHITECTURE.md) is the governing Observation architecture translated by EAP-006. It preserves Observation ownership, acceptance authority, factual meaning, subject attribution, provenance, lineage, temporal meaning, factual limits, and separation from interpretation and downstream judgment.

[EDD-007 Version 1.1 — Instrument-to-Observation Attribution Eligibility Engineering Design](../../engineering/edd/EDD-007-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY-ENGINEERING-DESIGN.md) is the completed upstream Engineering Design. Its sole relevant downstream output is the Composite Observation Participation Boundary containing:

1. Observation Participation Eligibility; and
2. the associated Eligible Candidate Factual Context.

EDD-008 shall consume that completed boundary only as governed by EAP-006. EDD-007 completion does not independently authorize EDD-008.

# 4. Target Document

The controlled Engineering Design Document is:

- **Document ID:** EDD-008;
- **Title:** Observation Acceptance and Governed Observation Establishment Engineering Design;
- **Classification:** Engineering Design Document;
- **Owner:** Engineering Architect;
- **Prepared By:** Engineering Design Team;
- **Review Authority:** Chief Architect;
- **Engineering Review Authority:** Chief Systems Engineer;
- **Direct Engineering Architecture:** EAP-006 Version 1.2;
- **Governing Architecture:** ADP-001E Version 1.1;
- **Upstream Engineering Boundary:** EDD-007 Version 1.1;
- **Architecture Authority:** None;
- **Implementation Authority:** None; and
- **Runtime Authority:** None.

The controlled EDD-008 identity shall not become authoritative until CAR-008 is published and synchronized to `develop`.

# 5. Authorization Scope

Upon controlled repository publication, CAR-008 authorizes:

1. creation of EDD-008 Version 0.1 Draft;
2. sequential preparation of ES-01 through ES-05;
3. Chief Systems Engineer review of every Engineering Stage;
4. Chief Architect approval of every Engineering Stage;
5. controlled publication and freezing of each approved Engineering Stage; and
6. Version 1.0 preparation only after ES-05 records a successful Independent Engineering Verification result.

This authorization permits Engineering Design only. It does not predetermine approval, verification, canonicalization, publication, implementation, runtime activity, or downstream product use.

# 6. Authorized Engineering Objectives

EDD-008 shall translate EAP-006 Version 1.2 into implementation-independent Engineering Design for:

- Candidate Observation establishment;
- Observation Acceptance Readiness;
- bounded Observation Acceptance Evaluation;
- exactly one Observation Acceptance Outcome;
- Observation Accepted and Observation Not Accepted meaning;
- exact non-sensitive non-acceptance reason preservation;
- separation of acceptance from resulting ownership;
- Observation ownership establishment following acceptance;
- Governed Observation establishment;
- factual assertion preservation;
- approved subject-attribution preservation;
- temporal meaning preservation;
- provenance and factual-lineage preservation;
- uncertainty, ambiguity, missingness, partiality, and known-limit preservation;
- fact–interpretation separation;
- authority limitation;
- boundary conformance and boundary violations;
- non-sensitive observability; and
- Independent Engineering Verification.

These objectives identify the permitted Engineering Design subject. They do not define responsibilities, capabilities, Building Blocks, interfaces, algorithms, data structures, or implementation.

# 7. Authorized Engineering Boundary

## 7.1 Beginning

EDD-008 shall begin only with exactly one approved EAP-005/EAP-006 Composite Observation Participation Boundary exposed through EDD-007 Version 1.1.

The boundary shall contain both mandatory constituents:

- Observation Participation Eligibility; and
- Eligible Candidate Factual Context.

The constituents shall concern the same candidate and approved canonical subject association and shall remain semantically distinguishable.

EDD-008 shall not reconstruct factual context from eligibility, reopen attribution evaluation, reinterpret canonical Instrument identity, access Provider or EAIC-002 artefacts, or create acquisition authority.

## 7.2 Ending

The positive boundary shall end with a Governed Observation Establishment Contract representing an accepted Observation-owned factual record.

The negative boundary shall end with an Observation Non-Acceptance Contract preserving the exact governed non-sensitive reason or reasons and creating no Observation ownership.

EDD-008 shall terminate before publication, persistence, retrieval, automatic downstream consumption, Validation, business judgment, strategy, Risk, Execution, Portfolio, Event, or product decision responsibility.

# 8. Engineering Deliverables

The authorized lifecycle shall produce only:

1. **ES-01 — Engineering Scope Definition**
   - mission, objectives, scope, responsibilities, exclusions, assumptions, constraints, boundaries, and architectural traceability.
2. **ES-02 — Engineering Capability Design**
   - implementation-independent capability decomposition, conceptual components, responsibility allocation, capability boundaries, dependencies, constraints, and traceability.
3. **ES-03 — Engineering Building Block Design**
   - bounded Engineering Building Blocks, responsibilities, boundaries, relationships, collaboration, cross-cutting concerns, constraints, and capability traceability.
4. **ES-04 — Engineering Interface Design**
   - conceptual engineering interfaces, responsibilities, boundaries, contracts, information meaning, dependencies, constraints, and Building Block traceability.
5. **ES-05 — Independent Engineering Verification**
   - scope, responsibility, capability, Building Block, interface, traceability, boundary, ownership, repository, and implementation-independence verification; NCR recording; readiness assessment; and publication recommendation.

No deliverable authorizes implementation or runtime activity.

# 9. Engineering Constraints and Prohibitions

EDD-008 shall:

1. derive exclusively from EAP-006 Version 1.2 as its sole direct Engineering Architecture;
2. remain consistent with ADP-001E Version 1.1;
3. consume EDD-007 Version 1.1 only through its approved terminal boundary;
4. preserve Instrument ownership of canonical identity;
5. preserve applicable source-domain ownership before acceptance;
6. preserve Observation ownership of Acceptance Authority;
7. preserve that candidate information does not become Observation-owned merely through eligibility or boundary entry;
8. preserve acceptance as distinct from resulting ownership;
9. preserve exactly two mutually exclusive Acceptance Outcomes;
10. preserve uncertainty, ambiguity, missingness, partiality, provenance, lineage, temporal meaning, and known limits;
11. preserve factual meaning separately from interpretation and downstream judgment;
12. remain provider-neutral, product-neutral, implementation-independent, and runtime-independent; and
13. introduce no new domain, dependency, semantic owner, architecture, or authority.

CAR-008 shall not authorize:

- Architecture Discovery or architectural redesign;
- modification or reinterpretation of EAP-006, ADP-001E, or EDD-007;
- Provider communication or factual-data acquisition;
- direct Provider-to-Observation or EAIC-002-to-Observation access;
- canonical identity creation, mapping, or Instrument Lifecycle processing;
- acceptance algorithms, matching, scoring, thresholds, or confidence models;
- correction, supersession, current-state selection, or derived-Observation engineering;
- APIs, methods, fields, schemas, payloads, protocols, transports, or messages;
- databases, storage, persistence, retention, publication, retrieval, or caching;
- scheduling, retries, orchestration, queues, streams, or executable state machines;
- services, modules, classes, packages, or deployment components;
- implementation technology, programming language, infrastructure, or code;
- runtime behavior or runtime authority;
- Validation, business judgment, product logic, GUI, strategy, Risk, Execution, Portfolio, or trading decisions; or
- automatic downstream consumption.

# 10. Sequential Review Gates

## 10.1 ES-01 Gate

ES-01 may begin only after CAR-008 and the controlled EDD-008 identity are approved, published, and synchronized to `develop`.

ES-01 must complete:

1. Chief Systems Engineer review;
2. Chief Architect approval;
3. controlled repository publication; and
4. freezing as the authoritative EDD-008 scope baseline.

ES-02 remains unauthorized until this gate is complete.

## 10.2 ES-02 Gate

ES-02 shall derive only from EAP-006 Version 1.2 and the approved, published ES-01 baseline.

It must complete Chief Systems Engineer review, Chief Architect approval, controlled publication, and freezing before ES-03 begins.

## 10.3 ES-03 Gate

ES-03 shall derive only from EAP-006 Version 1.2 and the approved, published ES-01 and ES-02 baselines.

It must complete Chief Systems Engineer review, Chief Architect approval, controlled publication, and freezing before ES-04 begins.

## 10.4 ES-04 Gate

ES-04 shall derive only from EAP-006 Version 1.2 and the approved, published ES-01 through ES-03 baselines.

It must complete Chief Systems Engineer review, Chief Architect approval, controlled publication, and freezing before ES-05 begins.

## 10.5 ES-05 Gate

ES-05 shall independently verify ES-01 through ES-04 without redesigning them.

Version 1.0 preparation remains unauthorized until ES-05:

1. completes Independent Engineering Verification;
2. records all Engineering Non-Conformities;
3. completes Chief Systems Engineer review;
4. receives Chief Architect approval; and
5. is published and frozen.

# 11. Publication Requirements

1. CAR-008 shall be published as an Approved and Canonical Review Package.
2. The Document Register shall record CAR-008 and the controlled EDD-008 identity.
3. EDD-008 shall initially be Version 0.1 Draft with:
   - Engineering Authority: Draft Preparation;
   - Architecture Authority: None;
   - Implementation Authority: None;
   - Runtime Authority: None.
4. ES-01 shall not become an authoritative frozen baseline until CAR-008 publication and repository synchronization are complete.
5. Every Engineering Stage shall be published and frozen before its successor begins.
6. Version 1.0 canonicalization and repository synchronization shall require separate Chief Architect publication approval after ES-05 PASS.
7. Publication shall not grant implementation or runtime authority.

# 12. Chief Architect Decision

**AUTHORIZE WITH CONSTRAINTS**

Authorize sequential EDD-008 ES-01 through ES-05 Draft Preparation as an implementation-independent Engineering Design translation derived exclusively from EAP-006 Version 1.2, governed by ADP-001E Version 1.1, and beginning only at the completed EDD-007 Version 1.1 upstream boundary.

Preserve:

- **Architecture Authority:** None;
- **Implementation Authority:** None; and
- **Runtime Authority:** None.

This decision becomes effective through controlled repository publication and synchronization of CAR-008. No EDD-008 Engineering Stage may become authoritative before its applicable publication gate is complete.
