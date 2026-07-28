# CAR-009 — EDD-009 Engineering Design Authorization Decision

**Document ID:** CAR-009<br>
**Title:** EDD-009 Engineering Design Authorization Decision<br>
**Version:** 1.0<br>
**Status:** Approved<br>
**Canonical Status:** Canonical<br>
**Classification:** Review Package<br>
**Owner:** Chief Architect<br>
**Prepared By:** Repository Governance Team<br>
**Review Authority:** Chief Architect<br>
**Repository Location:** `docs/governance/reviews/CAR-009-EDD-009-ENGINEERING-DESIGN-AUTHORIZATION-DECISION.md`<br>
**Workflow Stage:** Repository Publication<br>
**Decision Status:** APPROVED<br>
**Decision:** AUTHORIZE WITH CONSTRAINTS<br>
**Repository Status:** Published<br>
**Authorization Baseline:** Frozen<br>
**Authoritative Branch:** `develop`<br>
**Target Document:** EDD-009 — Governed Observation Publication, Lifecycle and Market Facts Engineering Design<br>
**Direct Engineering Architecture:** EAP-007 Version 1.0<br>
**Architecture Authorization Baseline:** CA-EAP-007<br>
**Upstream Engineering Boundary:** EDD-008 Version 1.0<br>
**EDD-009 Draft Authorization:** ES-01 through ES-05, subject to sequential stage gates<br>
**Architecture Authority:** None<br>
**Implementation Authority:** None<br>
**Runtime Authority:** None

---

# 1. Purpose

This decision records the repository-governed authority required before EDD-009 Engineering Design may begin.

The authorization is limited to implementation-independent Engineering Design derived exclusively from:

- EAP-007 Version 1.0;
- the approved, published, synchronized, and frozen CA-EAP-007 authorization baseline; and
- applicable approved repository governance.

CAR-009 contains no EDD-009 Engineering Design, responsibility decomposition, capability design, Building Block Design, interface design, or verification result.

# 2. Governance Basis

[EAS-007 — Engineering Design Document Governance Standard](../../engineering/eap/EAS-007-ENGINEERING-DESIGN-DOCUMENT-GOVERNANCE-STANDARD.md) requires separate Chief Architect authorization before a specific Engineering Design Document may be created.

[DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md) requires Draft Authorization to remain distinct from Engineering Design content and requires every controlled document to use approved identity, classification, metadata, repository location, lifecycle state, and Document Register governance.

CAR-009 uses the existing CAR Review Package mechanism. It introduces no new governance concept, authority layer, document family, or repository structure.

# 3. Repository Basis

[EAP-007 Version 1.0 — Governed Observation Publication, Lifecycle and Market Facts Engineering Architecture](../../engineering/eap/EAP-007-GOVERNED-OBSERVATION-PUBLICATION-LIFECYCLE-AND-MARKET-FACTS.md) is the sole direct, approved, canonical, frozen, and authoritative Engineering Architecture baseline for EDD-009.

[CA-EAP-007 — EAP-007 Draft Authorization](../authorizations/CA-EAP-007-DRAFT-AUTHORIZATION.md) is the approved, published, synchronized, and frozen authorization baseline from which EAP-007 was prepared. It preserves the Chief Architect Boundary Resolution, Observation ownership, the architectural Watchpoint, authority separation, and the absence of implementation and runtime authority.

[EDD-008 Version 1.0 — Observation Acceptance and Governed Observation Establishment Engineering Design](../../engineering/edd/EDD-008-OBSERVATION-ACCEPTANCE-AND-GOVERNED-OBSERVATION-ESTABLISHMENT-ENGINEERING-DESIGN.md) is the completed upstream Engineering Design. Its sole relevant positive downstream output is the Governed Observation Establishment Contract.

EDD-009 shall consume that completed positive boundary only as governed by EAP-007. EDD-008 completion and EAP-007 publication do not independently authorize EDD-009.

# 4. Target Document

The controlled Engineering Design Document is:

- **Document ID:** EDD-009;
- **Title:** Governed Observation Publication, Lifecycle and Market Facts Engineering Design;
- **Classification:** Engineering Design Document;
- **Owner:** Engineering Architect;
- **Prepared By:** Engineering Design Team;
- **Review Authority:** Chief Architect;
- **Engineering Review Authority:** Chief Systems Engineer;
- **Direct Engineering Architecture:** EAP-007 Version 1.0;
- **Architecture Authorization Baseline:** CA-EAP-007;
- **Upstream Engineering Boundary:** EDD-008 Version 1.0;
- **Architecture Authority:** None;
- **Implementation Authority:** None; and
- **Runtime Authority:** None.

The controlled EDD-009 identity is authorized for creation only after CAR-009 is published and synchronized to `develop`.

# 5. Authorization Scope

Upon controlled repository publication, CAR-009 authorizes:

1. creation of EDD-009 Version 0.1 Draft;
2. sequential preparation of ES-01 through ES-05;
3. Chief Systems Engineer review of every Engineering Stage;
4. Chief Architect approval of every Engineering Stage;
5. controlled publication and freezing of each approved Engineering Stage; and
6. Version 1.0 preparation only after ES-05 records a successful Independent Engineering Verification result.

This authorization permits Engineering Design only. It does not predetermine approval, verification, canonicalization, publication, implementation, runtime activity, Validation consumption, or downstream product use.

# 6. Authorized Engineering Objectives

EDD-009 shall translate EAP-007 Version 1.0 into implementation-independent Engineering Design for:

- Governed Observation input;
- Governed Observation identity continuity;
- Observation History;
- Observation Evidence;
- publication eligibility;
- publication outcome;
- exactly one bounded publication result;
- Market Facts publication meaning;
- Market Fact Not Published meaning;
- exact governed Observation-owned non-publication reason preservation;
- Market Facts Contract establishment;
- eligibility for separately approved downstream consumption;
- currentness;
- supersession;
- correction;
- replacement;
- withdrawal;
- archival meaning;
- historical traceability;
- Validation consumption-boundary preservation;
- authority limitation;
- boundary conformance and boundary violations;
- non-sensitive observability; and
- Independent Engineering Verification.

These objectives identify the permitted Engineering Design subject. They do not define responsibilities, capabilities, Building Blocks, interfaces, algorithms, data structures, or implementation.

# 7. Authorized Engineering Boundary

## 7.1 Beginning

EDD-009 shall begin only with the Governed Observation Establishment Contract exposed through the completed EDD-008 Version 1.0 positive terminal boundary.

EDD-009 shall consume that contract as complete upstream meaning. It shall not reopen Observation Acceptance, alter Observation ownership or accepted factual meaning, reconstruct Observation internals, access Provider or EAIC-002 artefacts, or create acquisition authority.

## 7.2 Ending

The positive boundary shall end with Market Facts Contract Published and Eligible for Approved Downstream Consumption.

The negative boundary shall end with Market Fact Not Published with the exact governed Observation-owned reason or reasons preserved and no published Market Facts Contract.

EDD-009 shall terminate before Validation behavior, automatic downstream consumption, business judgment, strategy, Risk, Execution, Portfolio, Event, product decision responsibility, aggregation, synthesis, contextual reasoning, cross-observation inference, historical intelligence, knowledge inference, or market memory.

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
   - scope, responsibility, capability, Building Block, interface, traceability, boundary, ownership, repository, Watchpoint, and implementation-independence verification; NCR recording; readiness assessment; and publication recommendation.

No deliverable authorizes implementation or runtime activity.

# 9. Engineering Constraints and Prohibitions

EDD-009 shall:

1. derive exclusively from EAP-007 Version 1.0 as its sole direct Engineering Architecture;
2. remain consistent with the approved, published, synchronized, and frozen CA-EAP-007 authorization baseline;
3. consume EDD-008 Version 1.0 only through its approved Governed Observation Establishment Contract;
4. preserve Observation ownership of Governed Observation identity continuity;
5. preserve Observation ownership of Observation History and Observation Evidence;
6. preserve Observation ownership of publication eligibility and publication outcome;
7. preserve Observation ownership of Market Facts and the Market Facts Contract;
8. preserve currentness separately from historical validity;
9. preserve supersession, correction, replacement, withdrawal, and archival meaning as distinct and non-destructive;
10. preserve historical traceability;
11. preserve exactly two mutually exclusive publication results and exactly one result for one bounded determination;
12. preserve exact governed Observation-owned non-publication reasons;
13. preserve the Market Facts Contract as Validation's sole Observation input;
14. preserve the distinction among Governed Observation, Published Market Fact, and Validation input;
15. preserve the Architectural Watchpoint — Potential Future Knowledge Layer;
16. remain provider-neutral, product-neutral, implementation-independent, and runtime-independent; and
17. introduce no new domain, dependency, semantic owner, architecture, or authority.

CAR-009 shall not authorize:

- Architecture Discovery or architectural redesign;
- modification or reinterpretation of EAP-007, CA-EAP-007, or EDD-008;
- reopening Observation Acceptance or changing Governed Observation ownership;
- Provider communication or factual-data acquisition;
- direct Provider-to-Observation or EAIC-002-to-Observation access;
- canonical identity creation, mapping, or Instrument Lifecycle processing;
- publication algorithms, eligibility algorithms, matching, scoring, thresholds, or confidence models;
- APIs, methods, fields, schemas, payloads, protocols, transports, or messages;
- databases, storage, persistence, retention mechanics, retrieval, or caching;
- scheduling, retries, orchestration, queues, streams, or executable state machines;
- services, modules, classes, packages, or deployment components;
- implementation technology, programming language, infrastructure, or code;
- runtime behavior, physical publication, delivery, or runtime authority;
- Validation judgment, evidentiary judgment, business judgment, product logic, GUI, strategy, Risk, Execution, Portfolio, Event, or trading decisions;
- automatic downstream consumption;
- aggregation across Market Facts;
- factual synthesis;
- contextual reasoning;
- cross-observation inference;
- historical intelligence;
- knowledge inference;
- market memory; or
- creation of a Knowledge Domain, Knowledge ownership, or a Knowledge-owned contract.

# 10. Sequential Review Gates

## 10.1 ES-01 Gate

ES-01 may begin only after CAR-009 and the controlled EDD-009 identity are approved, published, and synchronized to `develop`.

ES-01 must complete:

1. Chief Systems Engineer review;
2. Chief Architect approval;
3. controlled repository publication; and
4. freezing as the authoritative EDD-009 scope baseline.

ES-02 remains unauthorized until this gate is complete.

## 10.2 ES-02 Gate

ES-02 shall derive only from EAP-007 Version 1.0 and the approved, published ES-01 baseline.

It must complete Chief Systems Engineer review, Chief Architect approval, controlled publication, and freezing before ES-03 begins.

## 10.3 ES-03 Gate

ES-03 shall derive only from EAP-007 Version 1.0 and the approved, published ES-01 and ES-02 baselines.

It must complete Chief Systems Engineer review, Chief Architect approval, controlled publication, and freezing before ES-04 begins.

## 10.4 ES-04 Gate

ES-04 shall derive only from EAP-007 Version 1.0 and the approved, published ES-01 through ES-03 baselines.

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

1. CAR-009 shall be published as an Approved and Canonical Review Package before its decision becomes effective.
2. The Document Register shall record CAR-009 and the controlled EDD-009 identity only after Chief Architect approval.
3. EDD-009 shall initially be Version 0.1 Draft with:
   - Engineering Authority: Draft Preparation;
   - Architecture Authority: None;
   - Implementation Authority: None;
   - Runtime Authority: None.
4. ES-01 shall not begin or become an authoritative frozen baseline until CAR-009 publication and repository synchronization are complete.
5. Every Engineering Stage shall be published and frozen before its successor begins.
6. Version 1.0 canonicalization and repository synchronization shall require separate Chief Architect publication approval after ES-05 PASS.
7. Publication shall not grant implementation or runtime authority.

# 12. Chief Architect Decision

**AUTHORIZE WITH CONSTRAINTS**

Authorize sequential EDD-009 ES-01 through ES-05 Draft Preparation as an implementation-independent Engineering Design translation derived exclusively from EAP-007 Version 1.0 and consistent with the approved, published, synchronized, and frozen CA-EAP-007 authorization baseline, beginning only at the completed EDD-008 Version 1.0 Governed Observation Establishment Contract.

Preserve:

- **Architecture Authority:** None;
- **Implementation Authority:** None; and
- **Runtime Authority:** None.

This decision becomes effective only through controlled repository publication and synchronization of CAR-009. No EDD-009 Engineering Stage may be created or become authoritative before its applicable authorization and publication gate is complete.
