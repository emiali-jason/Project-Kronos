# EDD-011 — Market Facts Validation Assessment and Business Judgment Engineering Design

**Document ID:** EDD-011<br>
**Title:** Market Facts Validation Assessment and Business Judgment Engineering Design<br>
**Version:** 0.4<br>
**Status:** Approved<br>
**Canonical Status:** Draft<br>
**Classification:** Engineering Design Document<br>
**Owner:** Engineering Architect<br>
**Prepared By:** Engineering Design Team<br>
**Review Authority:** Chief Architect<br>
**Engineering Review Authority:** Chief Systems Engineer<br>
**Repository Location:** `docs/engineering/edd/EDD-011-MARKET-FACTS-VALIDATION-ASSESSMENT-AND-BUSINESS-JUDGMENT-ENGINEERING-DESIGN.md`<br>
**Workflow Stage:** ES-04 Published<br>
**Baseline Status:** ES-01 through ES-04 Frozen<br>
**Engineering Stage:** ES-04 Complete<br>
**Engineering Lifecycle:** In Progress<br>
**ES-01 Review Status:** Approved<br>
**ES-01 Approved By:** Chief Architect<br>
**ES-01 Baseline Status:** Frozen<br>
**ES-01 Repository Publication:** Published<br>
**ES-02 Review Status:** Approved<br>
**ES-02 Approved By:** Chief Architect<br>
**ES-02 Baseline Status:** Frozen<br>
**ES-02 Repository Publication:** Published<br>
**ES-03 Review Status:** Approved<br>
**ES-03 Approved By:** Chief Architect<br>
**ES-03 Baseline Status:** Frozen<br>
**ES-03 Repository Publication:** Published<br>
**ES-04 Review Status:** Approved<br>
**ES-04 Approved By:** Chief Architect<br>
**ES-04 Baseline Status:** Frozen<br>
**ES-04 Repository Publication:** Published<br>
**Authorization Decision:** CAR-010 Version 1.0<br>
**Direct Engineering Architecture:** EAP-008 Version 1.0<br>
**Upstream Engineering Architecture Dependency:** EAP-007 Version 1.0<br>
**Supporting Completed Upstream Engineering Design:** EDD-009 Version 1.0<br>
**Engineering Authority:** ES-01 through ES-04 published and frozen; ES-05 Draft Preparation<br>
**Architecture Authority:** None<br>
**Implementation Authority:** None<br>
**Runtime Authority:** None<br>
**Repository Status:** Published — ES-04 Frozen Baseline

---

# ES-01 — Engineering Scope Definition

## 1. Engineering Mission

EDD-011 shall define the implementation-independent Engineering Design scope required to translate EAP-008 Version 1.0 into a complete, bounded and verifiable Market Facts Validation Assessment and Business Judgment design.

The engineered subsystem begins only with the published Market Facts Contract governed by EAP-007 Version 1.0 and represented through the completed EDD-009 Version 1.0 supporting upstream Engineering boundary. EAP-008 Version 1.0 remains the sole direct Engineering Architecture authority.

For one bounded Validation Assessment, the subsystem preserves one explicit Validation Proposition, one Validation Programme, governed Validation Assessment identity, bounded reasoning across approved Market Facts, distinct evidentiary meanings, exactly one Validation Outcome and exactly one terminal publication result.

The subsystem terminates with either Validation Assessment Contract Published and Eligible for Separately Approved Downstream Consumption or Validation Assessment Not Published with the exact Validation-owned reason preserved.

EDD-011 creates no architecture and grants no implementation, runtime, persistence, storage, API, schema, algorithm, numerical-model, product, Risk, Execution or Knowledge-layer authority.

## 2. Engineering Objectives

EDD-011 ES-01 establishes the engineering boundary required to:

1. translate EAP-008 Version 1.0 without amending, reinterpreting, broadening, narrowing or replacing it;
2. consume only the published Market Facts Contract governed by EAP-007 Version 1.0;
3. preserve EDD-009 Version 1.0 as completed supporting upstream Engineering Design without treating it as architectural authority;
4. preserve Observation ownership and prevent Observation internals from crossing the Validation boundary;
5. keep Observation Acceptance closed and keep Market Facts exclusively Observation-owned;
6. preserve exactly one explicit Validation Proposition for one completed Validation Assessment;
7. preserve Validation Proposition integrity without silent broadening, merging, replacement or reinterpretation;
8. preserve one Validation Programme as Validation-owned assessment authority for one bounded Validation Assessment;
9. preserve Validation Programme neutrality from product, strategy, Risk and execution policy;
10. preserve that Validation Programme conformance establishes no Product Eligibility, opportunity status, trade direction, trade expression, Risk approval or execution readiness;
11. preserve one governed Validation Assessment identity and non-destructive lifecycle lineage;
12. preserve revalidation, supersession, withdrawal and archival as governed Validation Assessment relationships rather than silent identity replacement;
13. preserve bounded multi-fact reasoning only across Market Facts from approved Market Facts Contracts;
14. prevent bounded reasoning from creating reusable synthesis, generalized historical intelligence, persistent market memory, reusable cross-assessment knowledge or Knowledge constructs;
15. preserve Evidence Sufficiency, evidence quality, confidence assessment and processing status as distinct meanings;
16. preserve evidentiary judgment, business interpretation and explanation as Validation-owned meanings;
17. preserve exactly one of `VALIDATED`, `NOT_VALIDATED`, `INDETERMINATE` or `UNSUPPORTED`;
18. preserve Validation Outcome separately from publication eligibility and publication outcome;
19. preserve exactly one terminal publication result and exact Validation-owned non-publication reasons;
20. preserve the Validation Assessment Contract as the sole positive terminal contract eligible for separately approved downstream consumption;
21. preserve both approved Knowledge Watchpoints;
22. terminate before automatic downstream consumption, product judgment, Risk, Execution or Knowledge-layer responsibility; and
23. establish complete architectural traceability and future Independent Engineering Verification obligations.

## 3. Engineering Scope

### 3.1 Scope Beginning

EDD-011 begins only with:

> **Published Market Facts Contract produced under EAP-007 Version 1.0**

The completed EDD-009 Version 1.0 is supporting upstream Engineering Design for this boundary. It does not jointly produce, govern, reinterpret or replace the architectural input defined by EAP-007.

The published Market Facts Contract is consumed as complete upstream meaning. It may expose only governed factual assertion, approved subject attribution, temporal meaning, provenance, lineage, uncertainty, ambiguity, partiality, missingness, known limits, factual currentness and approved Observation-owned lifecycle meaning carried by the contract.

EDD-011 shall not consume unpublished Observations, Observation History internals, Observation Evidence internals, publication-eligibility internals, publication-outcome internals, Provider internals or Instrument internals.

Absence of a published Market Facts Contract means the approved EDD-011 input boundary is not established. ES-01 defines no runtime response to that absence.

### 3.2 Design-Layer Separation

EDD-011 preserves three distinct layers:

1. **Architecture:** EAP-008 Version 1.0 is the sole direct Engineering Architecture authority. EAP-007 Version 1.0 is its upstream Engineering Architecture dependency.
2. **Engineering Design:** EDD-011 translates EAP-008 into bounded engineering responsibilities and later authorized Engineering Stages. EDD-009 Version 1.0 supplies supporting completed upstream Engineering Design only.
3. **Implementation:** physical realization, runtime behavior, algorithms, data structures, persistence, storage, communication, technology, deployment and code remain outside EDD-011.

Engineering Design shall not resolve an architectural omission, contradiction or undecided matter through engineering convenience.

### 3.3 Included Engineering Scope

EDD-011 includes Engineering Design responsibility for:

- published Market Facts Contract input conformance;
- Observation-boundary isolation;
- Observation Acceptance closure;
- Observation ownership preservation;
- Market Facts ownership preservation;
- Validation Proposition identity, explicitness and integrity;
- Validation Programme identity, authority, conformance and neutrality;
- bounded Validation Assessment identity and scope;
- Validation Assessment lifecycle lineage;
- governed revalidation relationships;
- governed supersession relationships;
- governed withdrawal relationships;
- governed archival relationships;
- bounded multi-fact reasoning;
- evidence association;
- Evidence Sufficiency;
- evidence quality;
- confidence assessment;
- processing-status separation;
- evidentiary judgment;
- business interpretation;
- explanation;
- exactly-one Validation Outcome cardinality;
- `VALIDATED`;
- `NOT_VALIDATED`;
- `INDETERMINATE`;
- `UNSUPPORTED`;
- Validation Assessment lifecycle meaning;
- publication eligibility;
- publication outcome;
- Validation Assessment Contract establishment;
- Validation Assessment Not Published;
- exact Validation-owned non-publication reasons;
- eligibility for separately approved downstream consumption;
- boundary conformance and boundary violation;
- non-sensitive observability;
- both Knowledge Watchpoints;
- architectural traceability;
- governance conformance; and
- future Independent Engineering Verification readiness.

### 3.4 Validation Assessment Identity

One Validation Assessment possesses one governed engineering identity derived from the architectural identity established by EAP-008.

Validation Assessment lifecycle events preserve lineage rather than silently mutating that identity.

Revalidation, supersession, withdrawal and archival preserve governed relationships to the existing Validation Assessment rather than replacing it.

These relationships remain Validation-owned lifecycle meaning. They do not alter Observation-owned identity, history, evidence, publication meaning, Market Facts, factual lifecycle meaning or historical traceability.

ES-01 defines no identifier format, data structure, persistence mechanism, runtime sequence, state machine, API or implementation behavior.

### 3.5 Scope Ending

EDD-011 terminates immediately with exactly one of:

1. **Validation Assessment Contract Published and Eligible for Separately Approved Downstream Consumption**; or
2. **Validation Assessment Not Published**, with the exact Validation-owned reason preserved.

The terminal results are mutually exclusive.

Positive publication establishes only the governed Validation Assessment Contract and eligibility for separately approved downstream consumption. It does not establish automatic consumption, Product Eligibility, opportunity status, trade direction, trade expression, Risk approval or execution readiness.

Non-publication establishes no published Validation Assessment Contract and no downstream-consumption eligibility.

EDD-011 terminates before product decisions, opportunity ranking, strategy selection, Risk approval, Execution, Portfolio decisions, trading decisions, Knowledge-layer responsibility, implementation, runtime behavior, persistence, storage, APIs, schemas, algorithms, thresholds or numerical confidence models.

### 3.6 Architectural Watchpoint — Potential Future Knowledge Layer

The Chief Architect recognizes the possible future emergence of a separate KRONOS Knowledge architectural layer.

EAP-007 shall remain strictly limited to Observation-owned factual continuity, history, evidence association, lifecycle meaning, publication eligibility, publication outcome, currentness, correction, supersession, replacement, withdrawal, archival meaning, historical traceability, and Market Facts Contract establishment.

EAP-007 shall not define or absorb responsibilities for aggregation, synthesis, contextual reasoning, cross-observation inference, historical intelligence, knowledge inference, market memory, opportunity interpretation, Validation judgment, or product decision-making.

During EAP-007 review, and again after EAP-007 completion, the Chief Architect shall assess whether governed relationships or synthesis across multiple Market Facts justify a separate future Knowledge Domain or Engineering Architecture.

Until that separate architecture is explicitly approved, no Knowledge-layer domain, ownership, dependency, contract, implementation authority, or runtime authority exists.

### 3.7 Validation-Specific Watchpoint — Reusable Knowledge

Validation may perform bounded reasoning across multiple approved Market Facts only for one explicit Validation Proposition, one Validation Programme and one bounded Validation Assessment.

If reusable synthesis, generalized historical intelligence, persistent market memory, reusable cross-assessment knowledge, or Knowledge constructs become necessary, Engineering shall stop and return the matter for Chief Architect review.

Until separately approved architecture exists, EDD-011 shall create no Knowledge Domain, Knowledge owner, Knowledge dependency, Knowledge contract, reusable Knowledge construct, implementation authority or runtime authority.

## 4. Engineering Responsibilities

EDD-011 ES-01 allocates the following Engineering Design responsibilities:

1. **R1 — Architecture Translation:** translate EAP-008 Version 1.0 without architectural redesign or reinterpretation.
2. **R2 — Sole Direct Architecture Authority:** preserve EAP-008 Version 1.0 as the sole direct Engineering Architecture authority.
3. **R3 — Upstream Architecture Dependency:** preserve EAP-007 Version 1.0 as the upstream Engineering Architecture dependency.
4. **R4 — Supporting Design Separation:** preserve EDD-009 Version 1.0 as supporting completed upstream Engineering Design only.
5. **R5 — Published Input Boundary:** consume only the published Market Facts Contract.
6. **R6 — Input Conformance:** preserve conformance to the approved Market Facts Contract boundary.
7. **R7 — Observation Internal Isolation:** prevent Observation internals from crossing the boundary.
8. **R8 — Observation Acceptance Closure:** keep Observation Acceptance closed.
9. **R9 — Observation Ownership Preservation:** preserve all Observation-owned meaning.
10. **R10 — Market Facts Ownership:** keep Market Facts and the Market Facts Contract exclusively Observation-owned.
11. **R11 — Validation Proposition Establishment:** preserve one explicit Validation Proposition for one bounded assessment.
12. **R12 — Validation Proposition Cardinality:** preserve exactly one proposition for one completed Validation Assessment.
13. **R13 — Validation Proposition Integrity:** prevent silent broadening, merging, replacement or reinterpretation.
14. **R14 — Validation Programme Establishment:** preserve one Validation Programme as Validation-owned assessment authority.
15. **R15 — Validation Programme Cardinality:** preserve one programme for one bounded Validation Assessment.
16. **R16 — Validation Programme Neutrality:** prevent the programme from becoming product, strategy, Risk or execution policy.
17. **R17 — Programme Conformance Non-Implication:** prevent programme conformance from establishing Product Eligibility, opportunity status, trade direction, trade expression, Risk approval or execution readiness.
18. **R18 — Bounded Assessment Establishment:** preserve one bounded Validation Assessment.
19. **R19 — Validation Assessment Identity:** preserve one governed identity for one Validation Assessment.
20. **R20 — Lifecycle Lineage:** preserve lifecycle lineage without silent identity mutation.
21. **R21 — Revalidation Relationship:** preserve revalidation as a governed relationship rather than identity replacement.
22. **R22 — Supersession Relationship:** preserve Validation Assessment supersession as a governed relationship.
23. **R23 — Withdrawal Relationship:** preserve Validation Assessment withdrawal as a governed relationship.
24. **R24 — Archival Relationship:** preserve Validation Assessment archival meaning as a governed relationship.
25. **R25 — Multi-Fact Source Admissibility:** permit reasoning only across facts from approved Market Facts Contracts.
26. **R26 — Multi-Fact Boundedness:** bind multi-fact reasoning to one proposition, one programme and one assessment.
27. **R27 — Reusable Knowledge Prohibition:** prevent creation of reusable Knowledge.
28. **R28 — Evidence Association:** preserve association to approved Market Facts without ownership transfer.
29. **R29 — Evidence Sufficiency:** preserve Evidence Sufficiency as distinct engineering meaning.
30. **R30 — Evidence Quality:** preserve evidence quality as distinct engineering meaning.
31. **R31 — Sufficiency and Quality Separation:** keep Evidence Sufficiency separate from evidence quality.
32. **R32 — Confidence Assessment:** preserve confidence assessment without numerical-model design.
33. **R33 — Processing Status:** preserve processing status as distinct engineering meaning.
34. **R34 — Evidentiary Separation:** keep sufficiency, quality, confidence and processing status separate from Validation Outcome.
35. **R35 — Evidentiary Judgment:** preserve Validation-owned evidentiary judgment.
36. **R36 — Business Interpretation:** preserve Validation-owned business interpretation.
37. **R37 — Explanation:** preserve attributable Validation explanation.
38. **R38 — Validation Outcome Cardinality:** establish exactly one Validation Outcome for one completed Validation Assessment.
39. **R39 — Validated Outcome:** preserve `VALIDATED` independently.
40. **R40 — Not Validated Outcome:** preserve `NOT_VALIDATED` independently.
41. **R41 — Indeterminate Outcome:** preserve `INDETERMINATE` independently.
42. **R42 — Unsupported Outcome:** preserve `UNSUPPORTED` independently.
43. **R43 — Outcome Mutual Exclusivity:** keep the four Validation Outcomes mutually exclusive.
44. **R44 — Outcome and Facts Separation:** prevent Validation Outcome from mutating Observation-owned Market Facts.
45. **R45 — Validation Assessment Lifecycle:** preserve Validation-owned assessment lifecycle meaning.
46. **R46 — Publication Eligibility:** preserve assessment publication eligibility independently.
47. **R47 — Publication Outcome:** preserve publication outcome independently.
48. **R48 — Publication Separation:** keep Validation Outcome, publication eligibility and publication outcome distinct.
49. **R49 — Terminal Result Cardinality:** establish exactly one terminal publication result.
50. **R50 — Positive Publication:** preserve Validation Assessment Contract Published meaning.
51. **R51 — Negative Publication:** preserve Validation Assessment Not Published meaning.
52. **R52 — Non-Publication Reason:** preserve the exact Validation-owned non-publication reason.
53. **R53 — Downstream Eligibility:** preserve eligibility only for separately approved downstream consumption.
54. **R54 — Automatic Consumption Prohibition:** prevent publication from establishing automatic downstream consumption.
55. **R55 — EAP-007 Watchpoint:** preserve the Potential Future Knowledge Layer Watchpoint unchanged.
56. **R56 — Validation Watchpoint:** preserve the Validation-specific Engineering stop condition.
57. **R57 — Knowledge Authority Prohibition:** prevent creation of Knowledge-layer ownership, dependency, contract, implementation authority or runtime authority.
58. **R58 — Boundary Conformance:** preserve engineering conformance to the approved beginning and ending boundaries.
59. **R59 — Boundary Violation:** preserve explicit engineering meaning for boundary violations.
60. **R60 — Non-Sensitive Observability:** preserve only approved explanatory and non-sensitive observability meaning.
61. **R61 — Neutrality:** preserve provider, product, implementation and runtime neutrality.
62. **R62 — Governance and Verification Readiness:** preserve complete traceability, authority separation and future Independent Engineering Verification readiness.

Every responsibility is owned by EDD-011 Engineering Design. Ownership of the meaning being preserved remains with the domain or authority identified by EAP-008.

## 5. Explicit Exclusions

EDD-011 ES-01 excludes:

- Architecture Discovery;
- architectural redesign, reinterpretation or extension;
- capability decomposition;
- Engineering Component design;
- Building Block design;
- interface design;
- API design;
- method, field, payload, message, event, schema, protocol or transport design;
- algorithm design;
- threshold selection;
- numerical confidence models;
- scoring mechanisms;
- data-structure design;
- database design;
- persistence;
- storage;
- retention or retrieval mechanics;
- caching;
- runtime behavior;
- scheduling;
- retries;
- orchestration;
- queues;
- streams;
- executable state machines;
- services;
- modules;
- classes;
- packages;
- programming languages;
- frameworks;
- infrastructure;
- deployment;
- code;
- implementation tests;
- Provider internals;
- Instrument internals;
- Observation internals;
- Observation Acceptance reopening;
- Observation redesign;
- Observation publication redesign;
- Observation lifecycle ownership;
- Market Facts ownership transfer;
- Market Facts recreation;
- unpublished Observation consumption;
- Product Eligibility;
- product decisions;
- opportunity status;
- opportunity ranking;
- strategy selection;
- trade direction;
- trade expression;
- Risk approval;
- execution readiness;
- Execution;
- Portfolio decisions;
- trading decisions;
- automatic downstream consumption;
- reusable synthesis;
- generalized historical intelligence;
- persistent market memory;
- reusable cross-assessment knowledge;
- Knowledge Domain creation;
- Knowledge ownership;
- Knowledge dependencies;
- Knowledge contracts;
- physical publication; and
- any authority not explicitly granted by CAR-010 Version 1.0.

## 6. Engineering Assumptions

ES-01 relies only on the following governed assumptions:

1. EAP-008 Version 1.0 is approved, canonical, active and frozen.
2. CAR-010 Version 1.0 is approved, canonical, published, synchronized and frozen.
3. EAP-007 Version 1.0 remains the approved upstream Engineering Architecture dependency.
4. EDD-009 Version 1.0 remains completed supporting upstream Engineering Design.
5. The published Market Facts Contract is the only permitted input.
6. The Market Facts Contract carries only meaning approved by EAP-007.
7. Observation-owned meaning is complete at the boundary and is not reconstructed by Validation.
8. Validation Proposition, Validation Programme, evidentiary judgment, business interpretation, Evidence Sufficiency, evidence quality, confidence, explanation, Validation Outcome, Validation Assessment lifecycle and Validation Assessment Contract remain Validation-owned.
9. Market Facts remain Observation-owned.
10. Separately approved downstream consumption remains outside EDD-011.
11. Any architectural ambiguity or required Knowledge capability is returned to the Chief Architect.
12. ES-01 establishes scope only and does not predetermine later capability, Building Block or interface design.

No assumption grants implementation, runtime, persistence, API, schema, product, Risk, Execution or Knowledge-layer authority.

## 7. Engineering Constraints

EDD-011 ES-01 is constrained as follows:

1. EAP-008 Version 1.0 is the sole direct Engineering Architecture authority.
2. EAP-007 Version 1.0 remains the upstream Engineering Architecture dependency.
3. EDD-009 Version 1.0 remains supporting Engineering Design only.
4. CAR-010 Version 1.0 controls the sequential Engineering lifecycle.
5. Architecture ownership and engineering ownership shall remain distinct.
6. Observation ownership shall not transfer to Validation.
7. Validation shall never own Market Facts.
8. Observation internals shall not cross the boundary.
9. Observation Acceptance shall not be reopened.
10. One completed Validation Assessment shall assess exactly one explicit Validation Proposition.
11. A Validation Proposition shall not silently broaden, merge, replace or be reinterpreted during assessment.
12. One Validation Programme shall govern one bounded Validation Assessment.
13. A Validation Programme shall not become product, strategy, Risk or execution policy.
14. Validation Programme conformance shall not establish Product Eligibility, opportunity status, trade direction, trade expression, Risk approval or execution readiness.
15. One Validation Assessment shall possess one governed engineering identity.
16. Validation Assessment lifecycle events shall preserve lineage rather than silently mutate identity.
17. Revalidation, supersession, withdrawal and archival shall create governed relationships rather than replace an existing Validation Assessment.
18. Multi-fact reasoning shall use only Market Facts from approved Market Facts Contracts.
19. Multi-fact reasoning shall remain bounded to one proposition, one programme and one assessment.
20. Multi-fact reasoning shall create no reusable Knowledge construct.
21. Evidence Sufficiency, evidence quality, confidence and processing status shall remain separate.
22. Each evidentiary meaning shall remain distinct from Validation Outcome.
23. Exactly one Validation Outcome shall exist for one completed Validation Assessment.
24. The only outcomes shall be `VALIDATED`, `NOT_VALIDATED`, `INDETERMINATE` and `UNSUPPORTED`.
25. The four outcomes shall remain mutually exclusive.
26. Validation Outcome shall not mutate Market Facts.
27. Validation Outcome, publication eligibility and publication outcome shall remain distinct.
28. Exactly one terminal publication result shall be represented.
29. Positive and negative publication results shall remain mutually exclusive.
30. Validation Assessment Not Published shall preserve the exact Validation-owned reason.
31. Validation Assessment Not Published shall create no published Validation Assessment Contract.
32. Positive publication shall not establish automatic downstream consumption.
33. Publication shall not establish Product Eligibility, opportunity status, trade direction, trade expression, Risk approval or execution readiness.
34. Both Knowledge Watchpoints shall remain normative.
35. Engineering shall stop and return to the Chief Architect if reusable Knowledge becomes necessary.
36. No new domain, owner, dependency, architecture or authority shall be introduced.
37. Provider neutrality shall be preserved.
38. Product neutrality shall be preserved.
39. Implementation neutrality shall be preserved.
40. Runtime neutrality shall be preserved.
41. No persistence, storage, API, schema, algorithm, threshold or numerical confidence-model authority shall be introduced.
42. ES-01 shall contain no capability, Building Block or interface decomposition.
43. ES-02 shall remain unauthorized until ES-01 review, approval, publication and freeze are complete.

## 8. Traceability to Governing Architecture

| EAP-008 authority | ES-01 translation |
|---|---|
| Purpose and Architectural Mission | Mission; Objectives 1–23; R1–R4 and R62 |
| Scope beginning and sole Market Facts Contract input | Scope 3.1; R5–R10; Constraints 1–9 |
| Validation Proposition Architecture | Objectives 6–7; R11–R13; Constraints 10–11 |
| Validation Programme Architecture and neutrality | Objectives 8–10; R14–R17; Constraints 12–14 |
| Validation Assessment Identity | Objectives 11–12; Scope 3.4; R18–R24; Constraints 15–17 |
| Bounded Multi-Fact Reasoning | Objectives 13–14; R25–R27; Constraints 18–20 |
| Evidence and interpretation meanings | Objectives 15–16; R28–R37; Constraints 21–22 |
| Validation Outcome Architecture | Objectives 17–18; R38–R45; Constraints 23–27 |
| Publication Architecture and terminal boundary | Objectives 19–20; Scope 3.5; R46–R54; Constraints 28–33 |
| Architectural Watchpoint — Potential Future Knowledge Layer | Scope 3.6; R55 and R57; Constraints 34–36 |
| Validation-Specific Watchpoint — Reusable Knowledge | Scope 3.7; R56–R57; Constraints 34–36 |
| Architectural ownership and authority separation | Scope 3.2; R2–R4, R9–R10 and R61–R62 |
| Engineering observability | R58–R60 |
| Engineering verification obligations | R62; Constraints 36–43 |
| Explicit exclusions | Section 5 |

### 8.1 Boundary Traceability

| Boundary | Governing authority | ES-01 treatment |
|---|---|---|
| Architectural input | EAP-007 Version 1.0 Market Facts Contract, consumed only as governed by EAP-008 Version 1.0 | Scope 3.1; R3–R10 |
| Supporting upstream Engineering Design | EDD-009 Version 1.0 | Scope 3.1–3.2; R4 |
| Positive terminal boundary | Validation Assessment Contract Published and Eligible for Separately Approved Downstream Consumption | Scope 3.5; R49–R54 |
| Negative terminal boundary | Validation Assessment Not Published with exact Validation-owned reason preserved | Scope 3.5; R49–R54 |
| Downstream authority | Separately approved and outside EDD-011 | Mission; Scope 3.5; Exclusions |

### 8.2 Responsibility Completeness

Responsibilities R1–R62 collectively translate the complete approved EAP-008 Engineering Architecture boundary into ES-01 scope.

No responsibility creates architecture, implementation, runtime behavior, persistence, APIs, schemas, product policy, Risk policy, execution policy or Knowledge-layer authority.

Each responsibility shall be allocated exactly once during ES-02 only after the ES-01 publication gate is complete.

## 9. Governing Repository Authorities

EDD-011 ES-01 is governed by:

1. [CAR-010 Version 1.0](../../governance/reviews/CAR-010-EDD-011-ENGINEERING-AUTHORIZATION-DECISION.md) — Engineering Design authorization and sequential stage gates.
2. [EAP-008 Version 1.0](../eap/EAP-008-MARKET-FACTS-VALIDATION-ASSESSMENT-AND-BUSINESS-JUDGMENT.md) — sole direct Engineering Architecture authority.
3. [EAP-007 Version 1.0](../eap/EAP-007-GOVERNED-OBSERVATION-PUBLICATION-LIFECYCLE-AND-MARKET-FACTS.md) — upstream Engineering Architecture dependency.
4. [EDD-009 Version 1.0](EDD-009-GOVERNED-OBSERVATION-PUBLICATION-LIFECYCLE-AND-MARKET-FACTS-ENGINEERING-DESIGN.md) — completed supporting upstream Engineering Design.
5. [CA-EAP-008 Version 1.0](../../governance/authorizations/CA-EAP-008-DRAFT-AUTHORIZATION.md) — frozen authorization baseline for EAP-008.
6. [EAS-007](../eap/EAS-007-ENGINEERING-DESIGN-DOCUMENT-GOVERNANCE-STANDARD.md) — Engineering Design lifecycle governance.
7. [DOC-001](../../governance/documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md) — controlled identity, classification, metadata and repository governance.
8. [Observation Domain Architecture](../../architecture/platform/domains/observation/ARCHITECTURE.md) — Observation ownership.
9. [Validation Domain Architecture](../../architecture/platform/domains/validation/ARCHITECTURE.md) — Validation ownership.
10. [Domain Ownership Matrix](../../architecture/platform/DOMAIN_OWNERSHIP_MATRIX.md) — cross-domain ownership authority.
11. [Domain Dependency Matrix](../../architecture/platform/DOMAIN_DEPENDENCY_MATRIX.md) — dependency authority.
12. [Project KRONOS Data Flow](../../architecture/DATA_FLOW.md) — governed architectural flow context.
13. [Document Register](../../indexes/DOCUMENT-REGISTER.md) — controlled repository identity and lifecycle record.

If these authorities conflict, the approved canonical repository authority prevails. Engineering Design shall record the conflict and return it for governance resolution rather than invent an engineering resolution.

---

## ES-01 Review State

| Item | State |
|---|---|
| CAR-010 Version 1.0 | Approved, Published, Synchronized and Frozen |
| EAP-008 Version 1.0 | Approved, Canonical, Active and Frozen |
| EAP-007 Version 1.0 | Approved upstream Engineering Architecture dependency |
| EDD-009 Version 1.0 | Completed supporting upstream Engineering Design |
| EDD-011 controlled identity | Allocated and active |
| ES-01 Draft Preparation | Complete |
| Engineering Architect review | Complete |
| Chief Systems Engineer review | Complete |
| Chief Architect review | Approved |
| ES-01 publication | Published |
| ES-01 baseline freeze | Frozen |
| ES-02 | Authorized after ES-01 repository synchronization |
| Implementation | Not Authorized |
| Runtime | Not Authorized |

---

# ES-02 — Engineering Capability Design

## 1. Executive Summary

EDD-011 ES-02 decomposes the frozen ES-01 scope into 22 cohesive, non-overlapping and implementation-independent Engineering Capabilities.

The capability model allocates Responsibilities R1–R62 exactly once. It preserves EAP-008 Version 1.0 as the sole direct Engineering Architecture authority, EAP-007 Version 1.0 as the upstream Engineering Architecture dependency, EDD-009 Version 1.0 as supporting completed upstream Engineering Design and CAR-010 Version 1.0 as lifecycle authority.

Capabilities describe cohesive Engineering Design responsibility. They are not modules, services, classes, packages, APIs, schemas, runtime components, persistence structures, algorithms or technology selections.

## 2. Approved Scope Baseline

The sole Engineering Scope baseline is the published and frozen EDD-011 ES-01.

ES-02 shall:

- allocate every ES-01 responsibility exactly once;
- preserve every ES-01 exclusion, assumption, constraint and boundary;
- preserve Observation and Validation ownership;
- preserve the Market Facts Contract input boundary;
- preserve Validation Proposition integrity;
- preserve Validation Programme neutrality;
- preserve Validation Assessment identity and lifecycle lineage;
- preserve bounded multi-fact reasoning;
- preserve Validation Outcome separation;
- preserve publication eligibility and publication outcome separation;
- preserve both Knowledge Watchpoints;
- introduce no new engineering scope; and
- remain provider-neutral, product-neutral, implementation-neutral and runtime-neutral.

## 3. Engineering Capability Model

### C1 — Architecture and Governance Translation

- **Engineering Purpose:** Maintain faithful translation of the governing architecture and authorization chain.
- **Responsibilities:** R1, R2, R3, R4
- **Inputs:** EAP-008 Version 1.0; EAP-007 Version 1.0; EDD-009 Version 1.0; CAR-010 Version 1.0.
- **Outputs:** Preserved architecture, dependency, supporting-design and authorization traceability meaning.
- **Dependencies:** None within the capability model.
- **Boundary:** Begins with governing repository authorities and ends with their unaltered engineering applicability.
- **Constraints:** Creates no architecture and cannot elevate supporting Engineering Design into architectural authority.
- **Invariants:** EAP-008 remains the sole direct Engineering Architecture; EAP-007 remains upstream architecture; EDD-009 remains supporting design only.

### C2 — Published Market Facts Input Stewardship

- **Engineering Purpose:** Preserve the sole permitted factual input boundary and its conformance.
- **Responsibilities:** R5, R6
- **Inputs:** Published Market Facts Contract.
- **Outputs:** Established Market Facts input-boundary and conformance meaning.
- **Dependencies:** C1.
- **Boundary:** Begins at the EAP-007 Market Facts Contract and ends before any Validation-owned assessment meaning.
- **Constraints:** Admits no unpublished Observation or reconstructed factual meaning.
- **Invariants:** Only a published Market Facts Contract establishes the EDD-011 input boundary.

### C3 — Observation Boundary and Ownership Preservation

- **Engineering Purpose:** Prevent Observation meaning or ownership from leaking into Validation.
- **Responsibilities:** R7, R8, R9, R10
- **Inputs:** Established Market Facts input boundary and canonical ownership authorities.
- **Outputs:** Preserved Observation isolation, closed Acceptance boundary and Market Facts ownership.
- **Dependencies:** C1, C2.
- **Boundary:** Begins with the published contract boundary and ends before Validation Proposition establishment.
- **Constraints:** Cannot expose Observation internals, reopen Observation Acceptance or transfer Market Facts ownership.
- **Invariants:** Observation remains the exclusive owner of Market Facts and the Market Facts Contract; Validation never owns Market Facts.

### C4 — Validation Proposition Integrity

- **Engineering Purpose:** Establish exactly one explicit and stable proposition for one completed assessment.
- **Responsibilities:** R11, R12, R13
- **Inputs:** Established Market Facts input and preserved Observation boundary.
- **Outputs:** Explicit Validation Proposition with preserved identity and meaning.
- **Dependencies:** C2, C3.
- **Boundary:** Begins with a proposed Validation subject and ends with one explicit proposition whose integrity is governed.
- **Constraints:** Cannot silently broaden, merge, replace or reinterpret the proposition.
- **Invariants:** One completed Validation Assessment assesses exactly one explicit Validation Proposition.

### C5 — Validation Programme Authority and Neutrality

- **Engineering Purpose:** Preserve one Validation-owned assessment authority without policy leakage.
- **Responsibilities:** R14, R15, R16, R17
- **Inputs:** Explicit Validation Proposition and governing Validation architecture.
- **Outputs:** One conformant Validation Programme bounded to one Validation Assessment.
- **Dependencies:** C1, C4.
- **Boundary:** Begins with Validation-owned programme authority and ends before assessment establishment.
- **Constraints:** Cannot become product, strategy, Risk or execution policy.
- **Invariants:** Programme conformance establishes no Product Eligibility, opportunity status, trade direction, trade expression, Risk approval or execution readiness.

### C6 — Bounded Validation Assessment Identity

- **Engineering Purpose:** Establish one bounded Validation Assessment with one governed identity.
- **Responsibilities:** R18, R19, R20
- **Inputs:** One explicit proposition and one Validation Programme.
- **Outputs:** Bounded Validation Assessment identity with non-destructive lifecycle lineage.
- **Dependencies:** C4, C5.
- **Boundary:** Begins when proposition and programme meaning are both established and ends with one bounded assessment identity.
- **Constraints:** Defines no identifier format, runtime state or persistence mechanism.
- **Invariants:** Lifecycle events preserve lineage rather than silently mutate Validation Assessment identity.

### C7 — Validation Assessment Lifecycle Relationships

- **Engineering Purpose:** Preserve governed revalidation, supersession, withdrawal and archival relationships.
- **Responsibilities:** R21, R22, R23, R24
- **Inputs:** Governed Validation Assessment identity and lifecycle meaning.
- **Outputs:** Non-destructive Validation Assessment relationship meaning.
- **Dependencies:** C6.
- **Boundary:** Begins with an existing assessment identity and ends with preserved lineage relationships.
- **Constraints:** Cannot replace, erase or silently mutate an existing Validation Assessment.
- **Invariants:** Revalidation, supersession, withdrawal and archival create governed relationships rather than identity replacement.

### C8 — Bounded Multi-Fact Reasoning Admissibility

- **Engineering Purpose:** Bound reasoning across multiple approved Market Facts without creating reusable Knowledge.
- **Responsibilities:** R25, R26, R27
- **Inputs:** Approved Market Facts Contracts; one proposition; one programme; one bounded assessment; Knowledge Watchpoint constraints.
- **Outputs:** Multi-fact reasoning admissibility or non-admissibility meaning.
- **Dependencies:** C2, C4, C5, C6, C21.
- **Boundary:** Begins with candidate approved facts and ends with bounded reasoning meaning local to one assessment.
- **Constraints:** Cannot create aggregation assets, reusable synthesis, generalized historical intelligence, persistent market memory or reusable cross-assessment knowledge.
- **Invariants:** Every fact originates from an approved Market Facts Contract and all reasoning remains bounded to one proposition, programme and assessment.

### C9 — Evidence Association

- **Engineering Purpose:** Associate approved Market Facts with the bounded assessment without transferring ownership.
- **Responsibilities:** R28
- **Inputs:** Bounded assessment and admissible approved Market Facts.
- **Outputs:** Attributable evidence-association meaning.
- **Dependencies:** C3, C8.
- **Boundary:** Begins with admissible facts and ends with their governed association to one assessment.
- **Constraints:** Cannot mutate Market Facts or create Observation ownership in Validation.
- **Invariants:** Evidence association preserves source, provenance, lineage and Observation ownership.

### C10 — Evidence Sufficiency

- **Engineering Purpose:** Preserve Evidence Sufficiency independently from evidence quality and outcome.
- **Responsibilities:** R29, R31
- **Inputs:** Governed evidence associations.
- **Outputs:** Evidence Sufficiency meaning and preserved sufficiency-quality separation.
- **Dependencies:** C9.
- **Boundary:** Begins with associated evidence and ends with sufficiency meaning.
- **Constraints:** Defines no threshold, scoring mechanism or algorithm.
- **Invariants:** Evidence Sufficiency remains distinct from evidence quality and Validation Outcome.

### C11 — Evidence Quality

- **Engineering Purpose:** Preserve evidence quality as independent Validation meaning.
- **Responsibilities:** R30
- **Inputs:** Governed evidence associations.
- **Outputs:** Evidence-quality meaning.
- **Dependencies:** C9.
- **Boundary:** Begins with associated evidence and ends with quality meaning.
- **Constraints:** Defines no numerical quality model, weighting or score.
- **Invariants:** Evidence quality does not substitute for Evidence Sufficiency or Validation Outcome.

### C12 — Confidence Assessment

- **Engineering Purpose:** Preserve confidence as independent assessment meaning.
- **Responsibilities:** R32
- **Inputs:** Governed evidence association and applicable Validation meaning.
- **Outputs:** Confidence-assessment meaning.
- **Dependencies:** C9.
- **Boundary:** Begins with governed assessment evidence and ends with non-prescriptive confidence meaning.
- **Constraints:** Defines no numerical confidence model, scale, threshold or algorithm.
- **Invariants:** Confidence remains distinct from Evidence Sufficiency, evidence quality and Validation Outcome.

### C13 — Processing and Evidentiary Separation

- **Engineering Purpose:** Keep processing status and all evidentiary assessments semantically independent from Validation Outcome.
- **Responsibilities:** R33, R34
- **Inputs:** Sufficiency, quality, confidence and assessment-status meanings.
- **Outputs:** Preserved processing and evidentiary separation.
- **Dependencies:** C10, C11, C12.
- **Boundary:** Begins with distinct assessment meanings and ends with their non-substitutive separation.
- **Constraints:** Cannot convert processing state or evidentiary state into an outcome.
- **Invariants:** Processing status, Evidence Sufficiency, evidence quality and confidence never silently become Validation Outcome.

### C14 — Evidentiary Judgment and Business Interpretation

- **Engineering Purpose:** Preserve Validation-owned judgment and interpretation without product-policy leakage.
- **Responsibilities:** R35, R36
- **Inputs:** Bounded proposition, programme, assessment and distinct evidentiary meanings.
- **Outputs:** Evidentiary judgment and business interpretation meaning.
- **Dependencies:** C4, C5, C6, C10, C11, C12, C13.
- **Boundary:** Begins with governed assessment meaning and ends before explanation and outcome establishment.
- **Constraints:** Cannot create product decisions, strategy, Risk approval, execution policy or Knowledge constructs.
- **Invariants:** Judgment and interpretation remain Validation-owned and bounded to one assessment.

### C15 — Validation Explanation

- **Engineering Purpose:** Preserve an attributable explanation for the bounded Validation judgment.
- **Responsibilities:** R37
- **Inputs:** Proposition, programme, evidence and Validation-owned judgment meaning.
- **Outputs:** Attributable Validation explanation.
- **Dependencies:** C14.
- **Boundary:** Begins with bounded judgment meaning and ends with non-sensitive explanatory meaning.
- **Constraints:** Cannot expose Observation internals, sensitive information or implementation structures.
- **Invariants:** Explanation remains associated with one proposition, one programme and one assessment.

### C16 — Validation Outcome Cardinality and Fact Separation

- **Engineering Purpose:** Establish exactly one outcome without altering Observation-owned facts.
- **Responsibilities:** R38, R43, R44
- **Inputs:** One bounded assessment, distinct evidentiary meanings, judgment, interpretation and explanation.
- **Outputs:** Exactly-one outcome cardinality with mutual exclusivity and Market Facts separation.
- **Dependencies:** C4, C6, C10, C11, C12, C13, C14, C15.
- **Boundary:** Begins after bounded assessment meaning is established and ends with exactly-one-outcome meaning.
- **Constraints:** Cannot mutate Market Facts or collapse multiple outcome meanings.
- **Invariants:** Exactly one mutually exclusive Validation Outcome exists for one completed Validation Assessment.

### C17 — Validation Outcome Meaning

- **Engineering Purpose:** Preserve the four approved outcomes as distinct meanings.
- **Responsibilities:** R39, R40, R41, R42
- **Inputs:** Exactly-one outcome cardinality.
- **Outputs:** One of `VALIDATED`, `NOT_VALIDATED`, `INDETERMINATE` or `UNSUPPORTED`.
- **Dependencies:** C16.
- **Boundary:** Begins with outcome cardinality and ends with one approved outcome meaning.
- **Constraints:** Cannot add, merge, rename or reinterpret outcome categories.
- **Invariants:** The four approved outcomes are exhaustive within EAP-008 and mutually exclusive.

### C18 — Validation Assessment Lifecycle Stewardship

- **Engineering Purpose:** Preserve Validation-owned assessment lifecycle meaning after outcome establishment.
- **Responsibilities:** R45
- **Inputs:** Governed assessment identity, lifecycle relationships and exactly one outcome.
- **Outputs:** Preserved Validation Assessment lifecycle meaning.
- **Dependencies:** C6, C7, C17, C21.
- **Boundary:** Begins with governed assessment identity and ends with attributable lifecycle meaning.
- **Constraints:** Cannot absorb Observation lifecycle or define runtime lifecycle mechanics.
- **Invariants:** Assessment lifecycle remains Validation-owned and identity lineage remains non-destructive.

### C19 — Assessment Publication Eligibility and Outcome Separation

- **Engineering Purpose:** Preserve publication eligibility, publication outcome and Validation Outcome as independent meanings.
- **Responsibilities:** R46, R47, R48
- **Inputs:** Completed assessment, exactly one Validation Outcome and lifecycle meaning.
- **Outputs:** Distinct publication-eligibility and publication-outcome meanings.
- **Dependencies:** C16, C17, C18.
- **Boundary:** Begins after outcome establishment and ends before terminal publication meaning.
- **Constraints:** Eligibility cannot imply publication and publication cannot alter Validation Outcome.
- **Invariants:** Validation Outcome, publication eligibility and publication outcome never substitute for one another.

### C20 — Terminal Validation Assessment Publication

- **Engineering Purpose:** Establish exactly one terminal publication result and preserve downstream authority separation.
- **Responsibilities:** R49, R50, R51, R52, R53, R54
- **Inputs:** Publication eligibility, publication outcome, assessment lifecycle and exactly one Validation Outcome.
- **Outputs:** Validation Assessment Contract Published and Eligible for Separately Approved Downstream Consumption, or Validation Assessment Not Published with exact Validation-owned reason.
- **Dependencies:** C19, C21.
- **Boundary:** Begins with separated publication meanings and ends at the EAP-008 terminal boundary.
- **Constraints:** Cannot establish automatic downstream consumption or downstream product, Risk or Execution authority.
- **Invariants:** Positive and negative terminal results are mutually exclusive; non-publication creates no published contract.

### C21 — Knowledge Watchpoint and Authority Guard

- **Engineering Purpose:** Preserve both Knowledge Watchpoints and stop Engineering at any required architectural expansion.
- **Responsibilities:** R55, R56, R57
- **Inputs:** EAP-007 Knowledge Watchpoint; EAP-008 Validation-specific Watchpoint; governed ownership boundaries.
- **Outputs:** Preserved Watchpoint and Engineering-stop meaning.
- **Dependencies:** C1, C3.
- **Boundary:** Applies across the full EDD-011 scope without owning primary assessment meaning.
- **Constraints:** Cannot create a Knowledge Domain, Knowledge owner, dependency, contract, reusable Knowledge, implementation authority or runtime authority.
- **Invariants:** Any need for reusable synthesis, generalized historical intelligence, persistent market memory, reusable cross-assessment knowledge or Knowledge constructs returns to Chief Architect review.

### C22 — Boundary, Neutrality, Observability and Verification Governance

- **Engineering Purpose:** Preserve subsystem boundaries, neutrality, non-sensitive observability, traceability and review readiness.
- **Responsibilities:** R58, R59, R60, R61, R62
- **Inputs:** All capability meanings and governing repository authorities.
- **Outputs:** Boundary conformance or violation meaning, approved observability, neutrality, traceability and verification readiness.
- **Dependencies:** C1 through C21.
- **Boundary:** Cross-cutting across the entire capability model and terminates at the approved EAP-008 boundary.
- **Constraints:** Cannot create implementation, runtime, persistence, API, schema, algorithm, technology, product, Risk, Execution or Knowledge-layer design.
- **Invariants:** Every capability remains traceable, non-overlapping, implementation-independent, runtime-neutral, provider-neutral and product-neutral.

## 4. Capability Dependency Model

Dependencies express semantic engineering reliance only. They do not prescribe runtime order, invocation, orchestration, scheduling, concurrency, persistence or control flow.

| Capability | Direct engineering dependencies |
|---|---|
| C1 | None |
| C2 | C1 |
| C3 | C1, C2 |
| C4 | C2, C3 |
| C5 | C1, C4 |
| C6 | C4, C5 |
| C7 | C6 |
| C8 | C2, C4, C5, C6, C21 |
| C9 | C3, C8 |
| C10 | C9 |
| C11 | C9 |
| C12 | C9 |
| C13 | C10, C11, C12 |
| C14 | C4, C5, C6, C10, C11, C12, C13 |
| C15 | C14 |
| C16 | C4, C6, C10, C11, C12, C13, C14, C15 |
| C17 | C16 |
| C18 | C6, C7, C17, C21 |
| C19 | C16, C17, C18 |
| C20 | C19, C21 |
| C21 | C1, C3 |
| C22 | C1 through C21 |

The dependency model is acyclic. C21 constrains Knowledge-sensitive reasoning and lifecycle meaning without depending on those capabilities. C22 observes and verifies the completed semantic model without feeding new meaning back into it.

## 5. Capability Boundary Model

| Capability | Begins with | Ends with | Explicitly outside |
|---|---|---|---|
| C1 | Repository authorities | Preserved authority applicability | Architecture creation |
| C2 | Published Market Facts Contract | Input conformance meaning | Unpublished Observation |
| C3 | Established input boundary | Observation isolation and ownership preservation | Observation internals |
| C4 | Candidate Validation subject | One explicit stable proposition | Proposition algorithms |
| C5 | Validation programme authority | One neutral conformant programme | Product, strategy, Risk or execution policy |
| C6 | Proposition and programme | One bounded assessment identity | Identifier implementation |
| C7 | Existing assessment identity | Governed lifecycle relationships | Identity replacement |
| C8 | Approved facts and bounded assessment | Admissible bounded reasoning | Reusable Knowledge |
| C9 | Admissible approved facts | Evidence association | Fact ownership transfer |
| C10 | Associated evidence | Evidence Sufficiency | Threshold design |
| C11 | Associated evidence | Evidence quality | Scoring design |
| C12 | Associated evidence | Confidence meaning | Numerical models |
| C13 | Distinct evidentiary and processing meanings | Preserved separation | Outcome substitution |
| C14 | Bounded evidentiary meaning | Judgment and interpretation | Product decisions |
| C15 | Judgment and interpretation | Attributable explanation | Sensitive or implementation detail |
| C16 | Completed bounded assessment meaning | Exactly-one outcome cardinality | Fact mutation |
| C17 | Outcome cardinality | One approved outcome | Additional outcome categories |
| C18 | Assessment identity and outcome | Assessment lifecycle meaning | Observation lifecycle |
| C19 | Outcome and lifecycle | Separated publication meanings | Terminal publication |
| C20 | Publication meanings | Exactly one terminal result | Downstream consumption |
| C21 | Approved Watchpoints | Preserved stop condition | Knowledge architecture |
| C22 | Complete capability meanings | Conformance and verification readiness | Implementation design |

No capability crosses the published Market Facts Contract input boundary upstream or the Validation Assessment terminal publication boundary downstream.

## 6. Responsibility Allocation

| Capability | Frozen ES-01 responsibilities allocated |
|---|---|
| C1 | R1, R2, R3, R4 |
| C2 | R5, R6 |
| C3 | R7, R8, R9, R10 |
| C4 | R11, R12, R13 |
| C5 | R14, R15, R16, R17 |
| C6 | R18, R19, R20 |
| C7 | R21, R22, R23, R24 |
| C8 | R25, R26, R27 |
| C9 | R28 |
| C10 | R29, R31 |
| C11 | R30 |
| C12 | R32 |
| C13 | R33, R34 |
| C14 | R35, R36 |
| C15 | R37 |
| C16 | R38, R43, R44 |
| C17 | R39, R40, R41, R42 |
| C18 | R45 |
| C19 | R46, R47, R48 |
| C20 | R49, R50, R51, R52, R53, R54 |
| C21 | R55, R56, R57 |
| C22 | R58, R59, R60, R61, R62 |

Allocation result:

- responsibilities allocated: 62;
- missing responsibilities: 0;
- duplicate allocations: 0;
- orphan capabilities: 0; and
- new responsibilities introduced: 0.

## 7. Capability Constraints

Every capability shall:

1. remain within the frozen ES-01 scope;
2. preserve EAP-008 Version 1.0 without redesign or reinterpretation;
3. preserve EAP-007 Version 1.0 as the upstream architecture dependency;
4. preserve EDD-009 Version 1.0 as supporting completed Engineering Design only;
5. preserve Observation ownership;
6. preserve Validation ownership;
7. keep Market Facts exclusively Observation-owned;
8. preserve the Market Facts Contract as the sole input;
9. preserve proposition integrity;
10. preserve Validation Programme neutrality;
11. preserve Validation Assessment identity and lifecycle lineage;
12. preserve bounded multi-fact reasoning;
13. preserve evidentiary separation;
14. preserve exactly-one Validation Outcome;
15. preserve publication separation and terminal cardinality;
16. preserve both Knowledge Watchpoints;
17. remain non-overlapping and independently reviewable;
18. remain provider-neutral and product-neutral;
19. remain implementation-independent and runtime-neutral;
20. introduce no architecture, domain, owner, dependency or authority;
21. introduce no module, Building Block or interface design;
22. introduce no API, schema, algorithm, persistence or technology choice; and
23. return any required architectural expansion to governance review.

## 8. Engineering Traceability

| Governing meaning | ES-01 responsibilities | ES-02 capabilities |
|---|---|---|
| Architecture and governance separation | R1–R4 | C1 |
| Published Market Facts input | R5–R6 | C2 |
| Observation boundary and ownership | R7–R10 | C3 |
| Validation Proposition | R11–R13 | C4 |
| Validation Programme | R14–R17 | C5 |
| Bounded assessment identity | R18–R20 | C6 |
| Assessment lifecycle relationships | R21–R24 | C7 |
| Bounded multi-fact reasoning | R25–R27 | C8 |
| Evidence association | R28 | C9 |
| Evidence Sufficiency and separation | R29, R31 | C10 |
| Evidence quality | R30 | C11 |
| Confidence assessment | R32 | C12 |
| Processing and evidentiary separation | R33–R34 | C13 |
| Judgment and interpretation | R35–R36 | C14 |
| Explanation | R37 | C15 |
| Outcome cardinality and fact separation | R38, R43–R44 | C16 |
| Four Validation Outcomes | R39–R42 | C17 |
| Validation Assessment lifecycle | R45 | C18 |
| Publication eligibility and outcome separation | R46–R48 | C19 |
| Terminal publication | R49–R54 | C20 |
| Knowledge Watchpoints | R55–R57 | C21 |
| Boundary, neutrality, observability and verification | R58–R62 | C22 |

Future stages may realize these capabilities through Building Blocks and conceptual interfaces only after their respective stage gates. This traceability does not predetermine Building Block or interface design.

## 9. ES-02 Engineering Invariants

1. Every frozen ES-01 responsibility is allocated exactly once.
2. No capability introduces a new responsibility.
3. No capability changes semantic ownership.
4. No capability crosses the EAP-008 beginning or ending boundary.
5. No capability reopens Observation Acceptance.
6. No capability makes Market Facts Validation-owned.
7. No capability changes the Validation Proposition during assessment.
8. No capability makes Validation Programme conformance product, strategy, Risk or execution policy.
9. No capability replaces Validation Assessment identity through lifecycle meaning.
10. No capability creates reusable Knowledge.
11. No capability collapses sufficiency, quality, confidence, processing status or outcome.
12. No capability introduces an additional Validation Outcome.
13. No capability collapses Validation Outcome, publication eligibility or publication outcome.
14. No capability creates automatic downstream authority.
15. No capability defines implementation or runtime behavior.
16. The conceptual dependency model remains acyclic.

## 10. ES-02 Verification Criteria

Engineering Architect review shall verify:

1. exactly 22 capabilities are defined;
2. all 62 ES-01 responsibilities are allocated exactly once;
3. no responsibility is missing or duplicated;
4. no capability is orphaned;
5. capability purposes are cohesive and non-overlapping;
6. capability boundaries are explicit;
7. capability dependencies are conceptual and acyclic;
8. EAP-008 traceability is complete;
9. ES-01 remains unchanged and frozen;
10. Observation and Validation ownership are preserved;
11. the Market Facts Contract boundary is preserved;
12. Validation Proposition integrity is preserved;
13. Validation Programme neutrality is preserved;
14. Validation Assessment identity and lifecycle are preserved;
15. bounded multi-fact reasoning is preserved without Knowledge creation;
16. Validation Outcome and publication separations are preserved;
17. both Knowledge Watchpoints are preserved;
18. provider and product neutrality are preserved;
19. implementation and runtime neutrality are preserved;
20. no Building Blocks, interfaces, APIs, schemas, algorithms, persistence or technology decisions are introduced; and
21. ES-03 remains unauthorized.

## ES-02 Review State

| Item | State |
|---|---|
| CAR-010 Version 1.0 | Approved, Published, Synchronized and Frozen |
| EAP-008 Version 1.0 | Sole direct Engineering Architecture authority |
| EAP-007 Version 1.0 | Upstream Engineering Architecture dependency |
| EDD-009 Version 1.0 | Supporting completed upstream Engineering Design |
| EDD-011 ES-01 | Approved, Published and Frozen |
| ES-02 Draft Preparation | Complete |
| Engineering Architect review | Complete |
| Chief Systems Engineer review | Complete |
| Chief Architect review | Approved |
| ES-02 publication | Published |
| ES-02 baseline freeze | Frozen |
| ES-03 | Authorized after ES-02 repository synchronization |
| Implementation | Not Authorized |
| Runtime | Not Authorized |
---

# ES-03 — Engineering Building Block Design

## 1. Executive Summary

EDD-011 ES-03 realizes the frozen 22-capability ES-02 model through 19 cohesive and independently reviewable Engineering Building Blocks:

- 17 primary Building Blocks; and
- 2 cross-cutting Building Blocks.

Every capability C1–C22 is realized exactly once. Every frozen responsibility R1–R62 remains allocated exactly once.

Capabilities C10–C13 are realized together by BB-10 — Evidence Evaluation because their separate sufficiency, quality, confidence, processing-status and evidentiary-separation meanings form one cohesive Building Block boundary. This grouping does not merge, alter or reassign any capability, responsibility, dependency or invariant.

Building Blocks are bounded Engineering Design responsibilities. They are not modules, services, classes, packages, APIs, schemas, runtime components, persistence structures, algorithms or technology selections.

## 2. Approved Engineering Baselines

ES-03 derives only from:

- CAR-010 Version 1.0;
- EAP-008 Version 1.0;
- EAP-007 Version 1.0;
- EDD-009 Version 1.0 as supporting completed upstream Engineering Design;
- frozen EDD-011 ES-01; and
- frozen EDD-011 ES-02.

ES-03 preserves:

- all 62 frozen responsibilities;
- all 22 frozen capabilities;
- the ES-02 dependency model;
- Observation and Validation ownership;
- the Market Facts Contract boundary;
- Validation Proposition integrity;
- Validation Programme neutrality;
- Validation Assessment identity and lifecycle lineage;
- bounded multi-fact reasoning;
- evidentiary separation;
- exactly-one Validation Outcome;
- publication separation and terminal cardinality;
- both Knowledge Watchpoints; and
- provider, product, implementation and runtime neutrality.

## 3. Engineering Building Block Model

### BB-01 — Architecture and Governance Translation

- **Engineering Purpose:** Preserve the governing architecture, dependency, supporting-design and authorization chain.
- **Capability Coverage:** C1
- **Responsibilities:** R1, R2, R3, R4
- **Inputs:** CAR-010, EAP-008, EAP-007 and EDD-009 authority meanings.
- **Outputs:** Unaltered Engineering Design authority and traceability meaning.
- **Dependencies:** None.
- **Boundary:** Governing repository authority to engineering applicability.
- **Constraints:** Cannot create architecture or elevate EDD-009 into architectural authority.
- **Invariants:** EAP-008 remains the sole direct Engineering Architecture.

### BB-02 — Published Market Facts Input Stewardship

- **Engineering Purpose:** Establish the sole permitted factual input and its conformance.
- **Capability Coverage:** C2
- **Responsibilities:** R5, R6
- **Inputs:** Published Market Facts Contract.
- **Outputs:** Established and conformant input-boundary meaning.
- **Dependencies:** BB-01.
- **Boundary:** EAP-007 published contract to pre-assessment Validation boundary.
- **Constraints:** Cannot admit unpublished Observation meaning.
- **Invariants:** No other factual input establishes the EDD-011 boundary.

### BB-03 — Observation Boundary and Ownership Guard

- **Engineering Purpose:** Preserve Observation isolation, closed Acceptance and Market Facts ownership.
- **Capability Coverage:** C3
- **Responsibilities:** R7, R8, R9, R10
- **Inputs:** Established Market Facts input and canonical ownership authority.
- **Outputs:** Preserved Observation boundary and ownership meaning.
- **Dependencies:** BB-01, BB-02.
- **Boundary:** Published contract boundary to Validation-owned proposition meaning.
- **Constraints:** Cannot expose Observation internals or transfer ownership.
- **Invariants:** Validation never owns Market Facts.

### BB-04 — Validation Proposition Integrity

- **Engineering Purpose:** Establish one explicit and stable Validation Proposition.
- **Capability Coverage:** C4
- **Responsibilities:** R11, R12, R13
- **Inputs:** Conformant Market Facts boundary and proposed Validation subject.
- **Outputs:** One explicit proposition with preserved integrity.
- **Dependencies:** BB-02, BB-03.
- **Boundary:** Proposed Validation subject to governed proposition.
- **Constraints:** Cannot broaden, merge, replace or reinterpret the proposition.
- **Invariants:** One completed assessment evaluates exactly one explicit proposition.

### BB-05 — Validation Programme Authority

- **Engineering Purpose:** Establish one neutral Validation-owned programme authority.
- **Capability Coverage:** C5
- **Responsibilities:** R14, R15, R16, R17
- **Inputs:** Explicit proposition and Validation architecture.
- **Outputs:** One conformant Validation Programme for one bounded assessment.
- **Dependencies:** BB-01, BB-04.
- **Boundary:** Programme authority to bounded assessment authority.
- **Constraints:** Cannot become product, strategy, Risk or execution policy.
- **Invariants:** Conformance establishes no Product Eligibility, opportunity status, trade direction, trade expression, Risk approval or execution readiness.

### BB-06 — Bounded Validation Assessment Identity

- **Engineering Purpose:** Establish one bounded Validation Assessment with governed identity and lineage.
- **Capability Coverage:** C6
- **Responsibilities:** R18, R19, R20
- **Inputs:** One proposition and one Validation Programme.
- **Outputs:** One bounded Validation Assessment identity.
- **Dependencies:** BB-04, BB-05.
- **Boundary:** Established proposition and programme to governed assessment identity.
- **Constraints:** Defines no identifier, persistence or runtime mechanism.
- **Invariants:** Lifecycle meaning never silently mutates identity.

### BB-07 — Validation Assessment Lifecycle Relationships

- **Engineering Purpose:** Preserve non-destructive revalidation, supersession, withdrawal and archival relationships.
- **Capability Coverage:** C7
- **Responsibilities:** R21, R22, R23, R24
- **Inputs:** Governed Validation Assessment identity.
- **Outputs:** Governed lifecycle relationship meaning.
- **Dependencies:** BB-06.
- **Boundary:** Existing assessment identity to preserved relationship lineage.
- **Constraints:** Cannot erase or replace the existing assessment.
- **Invariants:** Lifecycle events create relationships rather than identity replacement.

### BB-08 — Bounded Multi-Fact Reasoning Admissibility

- **Engineering Purpose:** Bound reasoning across approved Market Facts without creating reusable Knowledge.
- **Capability Coverage:** C8
- **Responsibilities:** R25, R26, R27
- **Inputs:** Approved Market Facts, one proposition, one programme, one assessment and XBB-01 constraints.
- **Outputs:** Admissible or non-admissible bounded reasoning meaning.
- **Dependencies:** BB-02, BB-04, BB-05, BB-06, XBB-01.
- **Boundary:** Candidate approved facts to assessment-local reasoning meaning.
- **Constraints:** Cannot create reusable synthesis, historical intelligence, market memory or cross-assessment knowledge.
- **Invariants:** Reasoning remains bounded to one proposition, programme and assessment.

### BB-09 — Evidence Association

- **Engineering Purpose:** Associate approved Market Facts to one assessment without ownership transfer.
- **Capability Coverage:** C9
- **Responsibilities:** R28
- **Inputs:** Admissible facts and bounded assessment.
- **Outputs:** Attributable evidence-association meaning.
- **Dependencies:** BB-03, BB-08.
- **Boundary:** Admissible facts to governed assessment association.
- **Constraints:** Cannot mutate or assume ownership of Market Facts.
- **Invariants:** Source, provenance, lineage and Observation ownership remain preserved.

### BB-10 — Evidence Evaluation

- **Engineering Purpose:** Preserve distinct sufficiency, quality, confidence and processing meanings and their non-substitutive separation.
- **Capability Coverage:** C10, C11, C12, C13
- **Responsibilities:** R29, R30, R31, R32, R33, R34
- **Inputs:** Governed evidence associations and assessment-status meaning.
- **Outputs:** Distinct Evidence Sufficiency, evidence quality, confidence assessment, processing status and separation meaning.
- **Dependencies:** BB-09.
- **Boundary:** Associated evidence to preserved evidentiary and processing distinctions.
- **Constraints:** Defines no scoring, weighting, scale, threshold, numerical model or algorithm.
- **Invariants:** C10–C13 remain separately traceable; none of their meanings substitutes for another or for Validation Outcome.

### BB-11 — Evidentiary Judgment and Business Interpretation

- **Engineering Purpose:** Preserve Validation-owned judgment and interpretation within one bounded assessment.
- **Capability Coverage:** C14
- **Responsibilities:** R35, R36
- **Inputs:** Proposition, programme, assessment and BB-10 evidentiary meanings.
- **Outputs:** Evidentiary judgment and business interpretation meaning.
- **Dependencies:** BB-04, BB-05, BB-06, BB-10.
- **Boundary:** Governed evidentiary meaning to bounded Validation judgment.
- **Constraints:** Cannot create product, strategy, Risk, Execution or Knowledge-layer decisions.
- **Invariants:** Judgment and interpretation remain Validation-owned and assessment-bounded.

### BB-12 — Validation Explanation

- **Engineering Purpose:** Preserve attributable and non-sensitive explanation.
- **Capability Coverage:** C15
- **Responsibilities:** R37
- **Inputs:** Proposition, programme, evidence and Validation-owned judgment.
- **Outputs:** Attributable Validation explanation.
- **Dependencies:** BB-11.
- **Boundary:** Bounded judgment meaning to governed explanation.
- **Constraints:** Cannot expose Observation internals, sensitive information or implementation detail.
- **Invariants:** Explanation remains associated with one proposition, programme and assessment.

### BB-13 — Validation Outcome Cardinality

- **Engineering Purpose:** Establish exactly-one outcome cardinality without mutating Market Facts.
- **Capability Coverage:** C16
- **Responsibilities:** R38, R43, R44
- **Inputs:** Bounded assessment, BB-10 evidentiary meanings, judgment, interpretation and explanation.
- **Outputs:** Mutually exclusive exactly-one Validation Outcome cardinality.
- **Dependencies:** BB-04, BB-06, BB-10, BB-11, BB-12.
- **Boundary:** Completed bounded assessment meaning to outcome cardinality.
- **Constraints:** Cannot mutate Market Facts or collapse outcome categories.
- **Invariants:** One completed assessment has exactly one Validation Outcome.

### BB-14 — Validation Outcome Meaning

- **Engineering Purpose:** Preserve the four approved Validation Outcomes independently.
- **Capability Coverage:** C17
- **Responsibilities:** R39, R40, R41, R42
- **Inputs:** Exactly-one outcome cardinality.
- **Outputs:** `VALIDATED`, `NOT_VALIDATED`, `INDETERMINATE` or `UNSUPPORTED`.
- **Dependencies:** BB-13.
- **Boundary:** Outcome cardinality to one approved outcome meaning.
- **Constraints:** Cannot add, remove, merge, rename or reinterpret outcomes.
- **Invariants:** The four outcome meanings remain mutually exclusive.

### BB-15 — Validation Assessment Lifecycle Stewardship

- **Engineering Purpose:** Preserve Validation-owned lifecycle meaning after outcome establishment.
- **Capability Coverage:** C18
- **Responsibilities:** R45
- **Inputs:** Assessment identity, lifecycle relationships, one outcome and XBB-01 constraints.
- **Outputs:** Preserved Validation Assessment lifecycle meaning.
- **Dependencies:** BB-06, BB-07, BB-14, XBB-01.
- **Boundary:** Assessment identity and outcome to attributable lifecycle meaning.
- **Constraints:** Cannot absorb Observation lifecycle or define runtime mechanics.
- **Invariants:** Validation Assessment lineage remains non-destructive.

### BB-16 — Assessment Publication Separation

- **Engineering Purpose:** Preserve Validation Outcome, publication eligibility and publication outcome as distinct meanings.
- **Capability Coverage:** C19
- **Responsibilities:** R46, R47, R48
- **Inputs:** Completed assessment, one outcome and lifecycle meaning.
- **Outputs:** Separated publication eligibility and publication outcome.
- **Dependencies:** BB-13, BB-14, BB-15.
- **Boundary:** Established outcome and lifecycle to pre-terminal publication meaning.
- **Constraints:** Eligibility cannot imply publication; publication cannot change outcome.
- **Invariants:** Outcome, eligibility and publication result never substitute for one another.

### BB-17 — Terminal Validation Assessment Publication

- **Engineering Purpose:** Establish exactly one terminal publication result.
- **Capability Coverage:** C20
- **Responsibilities:** R49, R50, R51, R52, R53, R54
- **Inputs:** Separated publication meanings and XBB-01 authority constraints.
- **Outputs:** Published Validation Assessment Contract eligible for separately approved downstream consumption, or Validation Assessment Not Published with exact reason.
- **Dependencies:** BB-16, XBB-01.
- **Boundary:** Pre-terminal publication meaning to the EAP-008 ending boundary.
- **Constraints:** Cannot establish automatic downstream consumption or downstream authority.
- **Invariants:** Positive and negative results are mutually exclusive; non-publication creates no published contract.

### XBB-01 — Knowledge Watchpoint and Authority Guard

- **Engineering Purpose:** Preserve both Knowledge Watchpoints and stop Engineering at required architectural expansion.
- **Capability Coverage:** C21
- **Responsibilities:** R55, R56, R57
- **Inputs:** Approved Watchpoints and domain ownership boundaries.
- **Outputs:** Preserved stop condition and Knowledge-authority prohibition.
- **Dependencies:** BB-01, BB-03.
- **Boundary:** Cross-cutting across all Knowledge-sensitive Building Blocks.
- **Constraints:** Cannot create Knowledge ownership, dependency, contract, reusable construct, implementation authority or runtime authority.
- **Invariants:** Reusable synthesis, historical intelligence, persistent market memory or cross-assessment knowledge requires Chief Architect review.

### XBB-02 — Boundary, Neutrality, Observability and Verification Governance

- **Engineering Purpose:** Preserve conformance, neutrality, non-sensitive observability, traceability and verification readiness.
- **Capability Coverage:** C22
- **Responsibilities:** R58, R59, R60, R61, R62
- **Inputs:** Meanings established by BB-01 through BB-17 and XBB-01.
- **Outputs:** Boundary conformance or violation, approved observability, neutrality and verification readiness.
- **Dependencies:** BB-01 through BB-17 and XBB-01.
- **Boundary:** Cross-cutting across the complete Building Block model.
- **Constraints:** Cannot create implementation, runtime, persistence, API, schema, algorithm, technology, Product, Risk, Execution or Knowledge-layer design.
- **Invariants:** Every Building Block remains traceable, non-overlapping and inside the EAP-008 boundary.

## 4. Capability-to-Building-Block Traceability

| Building Block | Capability realization |
|---|---|
| BB-01 | C1 |
| BB-02 | C2 |
| BB-03 | C3 |
| BB-04 | C4 |
| BB-05 | C5 |
| BB-06 | C6 |
| BB-07 | C7 |
| BB-08 | C8 |
| BB-09 | C9 |
| BB-10 | C10, C11, C12, C13 |
| BB-11 | C14 |
| BB-12 | C15 |
| BB-13 | C16 |
| BB-14 | C17 |
| BB-15 | C18 |
| BB-16 | C19 |
| BB-17 | C20 |
| XBB-01 | C21 |
| XBB-02 | C22 |

Traceability result:

- approved capabilities realized: 22;
- capabilities realized more than once: 0;
- missing capabilities: 0;
- orphan Building Blocks: 0; and
- new capabilities introduced: 0.

BB-10 preserves the internal frozen dependency distinction:

- C10, C11 and C12 each depend on C9; and
- C13 depends on C10, C11 and C12.

Grouping does not remove or alter those dependencies.

## 5. Responsibility-to-Building-Block Allocation

| Building Block | Frozen responsibilities preserved |
|---|---|
| BB-01 | R1, R2, R3, R4 |
| BB-02 | R5, R6 |
| BB-03 | R7, R8, R9, R10 |
| BB-04 | R11, R12, R13 |
| BB-05 | R14, R15, R16, R17 |
| BB-06 | R18, R19, R20 |
| BB-07 | R21, R22, R23, R24 |
| BB-08 | R25, R26, R27 |
| BB-09 | R28 |
| BB-10 | R29, R30, R31, R32, R33, R34 |
| BB-11 | R35, R36 |
| BB-12 | R37 |
| BB-13 | R38, R43, R44 |
| BB-14 | R39, R40, R41, R42 |
| BB-15 | R45 |
| BB-16 | R46, R47, R48 |
| BB-17 | R49, R50, R51, R52, R53, R54 |
| XBB-01 | R55, R56, R57 |
| XBB-02 | R58, R59, R60, R61, R62 |

Allocation result:

- frozen responsibilities preserved: 62;
- missing responsibilities: 0;
- duplicate allocations: 0; and
- new responsibilities introduced: 0.

## 6. Building Block Boundary Model

| Building Block | Primary boundary test | Independent Engineering Team Test |
|---|---|---|
| BB-01 | Governing authority only | PASS — reviewable without assessment semantics |
| BB-02 | Published input only | PASS — reviewable without Observation internals |
| BB-03 | Ownership and isolation only | PASS — reviewable without proposition meaning |
| BB-04 | Proposition identity and integrity only | PASS — reviewable without programme policy |
| BB-05 | Programme authority and neutrality only | PASS — reviewable without assessment mechanics |
| BB-06 | Bounded assessment identity only | PASS — reviewable without lifecycle relationship realization |
| BB-07 | Lifecycle relationships only | PASS — reviewable without outcome meaning |
| BB-08 | Multi-fact admissibility only | PASS — reviewable without evidentiary evaluation |
| BB-09 | Evidence association only | PASS — reviewable without sufficiency or quality judgment |
| BB-10 | Evidence evaluation separation only | PASS — reviewable without business judgment or outcome |
| BB-11 | Judgment and interpretation only | PASS — reviewable without outcome publication |
| BB-12 | Explanation only | PASS — reviewable without outcome cardinality |
| BB-13 | Outcome cardinality only | PASS — reviewable without selecting additional categories |
| BB-14 | Four outcome meanings only | PASS — reviewable without publication meaning |
| BB-15 | Assessment lifecycle only | PASS — reviewable without Observation lifecycle |
| BB-16 | Publication separation only | PASS — reviewable without terminal delivery |
| BB-17 | Terminal publication only | PASS — reviewable without downstream consumption |
| XBB-01 | Knowledge authority guard only | PASS — cross-cutting and independently reviewable |
| XBB-02 | Governance and verification only | PASS — cross-cutting and independently reviewable |

No Building Block overlaps another primary responsibility boundary.

## 7. Building Block Relationship Model

Relationships express semantic Engineering Design dependencies only. They are not runtime calls, sequences, workflows, orchestration, scheduling, queues, transports or APIs.

| Building Block | Direct semantic dependencies |
|---|---|
| BB-01 | None |
| BB-02 | BB-01 |
| BB-03 | BB-01, BB-02 |
| BB-04 | BB-02, BB-03 |
| BB-05 | BB-01, BB-04 |
| BB-06 | BB-04, BB-05 |
| BB-07 | BB-06 |
| BB-08 | BB-02, BB-04, BB-05, BB-06, XBB-01 |
| BB-09 | BB-03, BB-08 |
| BB-10 | BB-09 |
| BB-11 | BB-04, BB-05, BB-06, BB-10 |
| BB-12 | BB-11 |
| BB-13 | BB-04, BB-06, BB-10, BB-11, BB-12 |
| BB-14 | BB-13 |
| BB-15 | BB-06, BB-07, BB-14, XBB-01 |
| BB-16 | BB-13, BB-14, BB-15 |
| BB-17 | BB-16, XBB-01 |
| XBB-01 | BB-01, BB-03 |
| XBB-02 | BB-01 through BB-17 and XBB-01 |

The relationship model is acyclic. BB-10 internalizes only the already-approved C10–C13 dependency relationships. XBB-01 constrains Knowledge-sensitive blocks without semantic feedback. XBB-02 verifies completed meaning without creating feedback into primary responsibility.

## 8. Building Block Collaboration

Collaboration means conceptual responsibility alignment only:

1. BB-01 preserves authority context for every Building Block.
2. BB-02 and BB-03 jointly preserve the upstream Market Facts and Observation boundary without overlapping ownership.
3. BB-04 and BB-05 provide distinct proposition and programme meaning to BB-06.
4. BB-06 provides governed assessment identity to BB-07 and assessment-bounded blocks.
5. BB-08 and BB-09 preserve admissibility and association before BB-10 evaluates evidence meaning.
6. BB-10 preserves C10–C13 distinctions before BB-11 establishes judgment and interpretation.
7. BB-11 and BB-12 preserve judgment and explanation before BB-13 establishes outcome cardinality.
8. BB-13 and BB-14 preserve cardinality separately from outcome meaning.
9. BB-15 preserves lifecycle meaning independently from BB-16 publication separation.
10. BB-16 preserves eligibility and publication-outcome separation before BB-17 establishes a terminal result.
11. XBB-01 constrains BB-08, BB-15 and BB-17 where Knowledge-layer leakage could occur.
12. XBB-02 preserves conformance and verification across the complete model.

This collaboration model defines no interface, payload, method, protocol or execution flow.

## 9. Cross-Cutting Building Blocks

### 9.1 XBB-01 — Knowledge Watchpoint and Authority Guard

XBB-01 remains cross-cutting because both Watchpoints constrain multiple primary responsibilities without owning proposition, programme, evidence, judgment, outcome, lifecycle or publication meaning.

It cannot be absorbed into BB-08, BB-15 or BB-17 because doing so would narrow the Chief Architect stop condition to one primary responsibility.

### 9.2 XBB-02 — Boundary, Neutrality, Observability and Verification Governance

XBB-02 remains cross-cutting because boundary conformance, violation meaning, neutrality, observability, traceability and verification apply across the entire subsystem.

It does not own primary Validation meaning and cannot alter a capability or Building Block result.

## 10. Building Block Constraints and Invariants

Every Building Block shall:

1. preserve its allocated capabilities exactly;
2. preserve its allocated responsibilities exactly;
3. remain within frozen ES-01 and ES-02 boundaries;
4. preserve capability ownership;
5. preserve the ES-02 dependency model;
6. preserve Observation and Validation ownership;
7. preserve the Market Facts Contract boundary;
8. preserve Validation Proposition integrity;
9. preserve Validation Programme neutrality;
10. preserve Validation Assessment identity and lifecycle lineage;
11. preserve bounded multi-fact reasoning;
12. preserve Evidence Sufficiency, evidence quality, confidence, processing status and outcome separation;
13. preserve exactly-one Validation Outcome;
14. preserve publication separation and terminal cardinality;
15. preserve both Knowledge Watchpoints;
16. remain cohesive, non-overlapping and independently reviewable;
17. remain provider-neutral and product-neutral;
18. remain implementation-independent and runtime-neutral;
19. introduce no architecture, owner, domain, dependency or authority;
20. introduce no interface design;
21. introduce no API, schema, algorithm, persistence or technology selection; and
22. return any required architectural expansion to governance review.

## 11. Engineering Traceability

| Architectural concern | ES-02 capabilities | ES-03 Building Blocks |
|---|---|---|
| Authority translation | C1 | BB-01 |
| Market Facts input | C2 | BB-02 |
| Observation boundary | C3 | BB-03 |
| Validation Proposition | C4 | BB-04 |
| Validation Programme | C5 | BB-05 |
| Assessment identity | C6 | BB-06 |
| Lifecycle relationships | C7 | BB-07 |
| Multi-fact reasoning | C8 | BB-08 |
| Evidence association | C9 | BB-09 |
| Sufficiency, quality, confidence and processing separation | C10–C13 | BB-10 |
| Judgment and interpretation | C14 | BB-11 |
| Explanation | C15 | BB-12 |
| Outcome cardinality | C16 | BB-13 |
| Outcome meaning | C17 | BB-14 |
| Assessment lifecycle | C18 | BB-15 |
| Publication separation | C19 | BB-16 |
| Terminal publication | C20 | BB-17 |
| Knowledge Watchpoints | C21 | XBB-01 |
| Boundary, neutrality, observability and verification | C22 | XBB-02 |

Future ES-04 may define conceptual engineering interfaces between these approved Building Blocks only after the ES-03 publication gate. This statement does not define interface content.

## 12. ES-03 Verification Criteria

Engineering Architect review shall verify:

1. exactly 19 Building Blocks are defined;
2. exactly 17 are primary and 2 are cross-cutting;
3. all 22 capabilities are realized exactly once;
4. all 62 responsibilities are preserved exactly once;
5. no capability responsibility or dependency is changed;
6. BB-10 preserves C10–C13 as separate capabilities with their internal dependencies intact;
7. no Building Block is orphaned or overlapping;
8. all Building Blocks pass the Independent Engineering Team Test;
9. the Building Block dependency model is acyclic;
10. ES-01 and ES-02 remain unchanged and frozen;
11. ownership and boundaries are preserved;
12. both Knowledge Watchpoints are preserved;
13. no architecture, implementation, runtime, persistence, API, schema, algorithm, technology, Product, Risk, Execution or Knowledge-layer design is introduced;
14. no interface design is introduced; and
15. ES-04 remains unauthorized.

## ES-03 Review State

| Item | State |
|---|---|
| CAR-010 Version 1.0 | Approved, Published, Synchronized and Frozen |
| EAP-008 Version 1.0 | Sole direct Engineering Architecture authority |
| EAP-007 Version 1.0 | Upstream Engineering Architecture dependency |
| EDD-009 Version 1.0 | Supporting completed upstream Engineering Design |
| EDD-011 ES-01 | Approved, Published and Frozen |
| EDD-011 ES-02 | Approved, Published and Frozen |
| ES-03 Draft Preparation | Complete |
| Engineering Architect review | Complete |
| Chief Systems Engineer review | Complete |
| Chief Architect review | Approved |
| ES-03 publication | Published |
| ES-03 baseline freeze | Frozen |
| ES-04 | Authorized after ES-03 repository synchronization |
| Implementation | Not Authorized |
| Runtime | Not Authorized |

---

# ES-04 — Engineering Interface Design

## 1. Executive Summary

EDD-011 ES-04 translates the frozen ES-03 Building Block relationship model into 58 conceptual Engineering Interfaces.

Every approved direct Building Block dependency is represented exactly once:

- 40 primary or Knowledge-watchpoint interfaces; and
- 18 cross-cutting governance interfaces into XBB-02.

Interfaces transfer established engineering meaning only. They do not transfer ownership, authority, execution responsibility, implementation behavior, runtime behavior or technology choices.

The interface model introduces no new Building Block, capability, responsibility, dependency, architecture or authority.

## 2. Engineering Interface Principle

Every EDD-011 interface:

- has exactly one source Building Block and one destination Building Block;
- is directional only for conceptual responsibility reliance;
- preserves source ownership of established meaning;
- permits the destination to rely only on meaning authorized by its own boundary;
- preserves Observation ownership, Validation ownership and Building Block ownership;
- preserves semantic independence;
- preserves provider, product, implementation and runtime neutrality;
- preserves architectural authority separation;
- creates no runtime order, call, execution flow or orchestration; and
- creates no API, payload, message, schema, protocol, transport, event, queue, persistence structure or technology choice.

An interface never transfers ownership and never redefines architecture.

## 3. Interface Catalogue

The **Ownership** column identifies the Building Block that retains ownership of the transferred engineering meaning. Directionality is conceptual source-to-destination reliance only.

| Interface | Source | Destination | Engineering purpose and information meaning | Ownership | Directionality | Contract class |
|---|---|---|---|---|---|---|
| IF-01 | BB-01 | BB-02 | Governing authority applicable to published-input stewardship | BB-01 | BB-01 → BB-02 | AUTH |
| IF-02 | BB-01 | BB-03 | Governing ownership authority applicable to the Observation guard | BB-01 | BB-01 → BB-03 | AUTH |
| IF-03 | BB-02 | BB-03 | Established Market Facts input-boundary meaning | BB-02 | BB-02 → BB-03 | INPUT |
| IF-04 | BB-02 | BB-04 | Conformant published-input meaning applicable to proposition establishment | BB-02 | BB-02 → BB-04 | INPUT |
| IF-05 | BB-03 | BB-04 | Preserved Observation boundary and ownership constraints | BB-03 | BB-03 → BB-04 | OWN |
| IF-06 | BB-01 | BB-05 | Governing Validation authority applicable to programme meaning | BB-01 | BB-01 → BB-05 | AUTH |
| IF-07 | BB-04 | BB-05 | Explicit proposition identity applicable to one programme | BB-04 | BB-04 → BB-05 | PROP |
| IF-08 | BB-04 | BB-06 | Explicit proposition and integrity meaning applicable to assessment identity | BB-04 | BB-04 → BB-06 | PROP |
| IF-09 | BB-05 | BB-06 | Neutral conformant Validation Programme meaning | BB-05 | BB-05 → BB-06 | PROG |
| IF-10 | BB-06 | BB-07 | Governed Validation Assessment identity and lineage basis | BB-06 | BB-06 → BB-07 | ASSESS |
| IF-11 | BB-02 | BB-08 | Approved Market Facts source admissibility meaning | BB-02 | BB-02 → BB-08 | INPUT |
| IF-12 | BB-04 | BB-08 | One explicit proposition boundary for multi-fact reasoning | BB-04 | BB-04 → BB-08 | PROP |
| IF-13 | BB-05 | BB-08 | One neutral Validation Programme boundary for reasoning | BB-05 | BB-05 → BB-08 | PROG |
| IF-14 | BB-06 | BB-08 | One bounded Validation Assessment identity for reasoning | BB-06 | BB-06 → BB-08 | ASSESS |
| IF-15 | XBB-01 | BB-08 | Knowledge Watchpoint constraint on bounded reasoning | XBB-01 | XBB-01 → BB-08 | WATCH |
| IF-16 | BB-03 | BB-09 | Observation ownership constraints applicable to evidence association | BB-03 | BB-03 → BB-09 | OWN |
| IF-17 | BB-08 | BB-09 | Admissible bounded multi-fact reasoning meaning | BB-08 | BB-08 → BB-09 | REASON |
| IF-18 | BB-09 | BB-10 | Governed evidence-association meaning | BB-09 | BB-09 → BB-10 | EVID |
| IF-19 | BB-04 | BB-11 | Proposition meaning bounding judgment and interpretation | BB-04 | BB-04 → BB-11 | PROP |
| IF-20 | BB-05 | BB-11 | Programme authority and neutrality bounding judgment | BB-05 | BB-05 → BB-11 | PROG |
| IF-21 | BB-06 | BB-11 | Assessment identity bounding judgment and interpretation | BB-06 | BB-06 → BB-11 | ASSESS |
| IF-22 | BB-10 | BB-11 | Distinct evidence-evaluation meanings | BB-10 | BB-10 → BB-11 | EVID |
| IF-23 | BB-11 | BB-12 | Bounded judgment and interpretation meaning for explanation | BB-11 | BB-11 → BB-12 | JUDGE |
| IF-24 | BB-04 | BB-13 | Proposition cardinality applicable to outcome cardinality | BB-04 | BB-04 → BB-13 | PROP |
| IF-25 | BB-06 | BB-13 | Assessment identity applicable to exactly-one outcome | BB-06 | BB-06 → BB-13 | ASSESS |
| IF-26 | BB-10 | BB-13 | Evidentiary separation applicable to outcome cardinality | BB-10 | BB-10 → BB-13 | EVID |
| IF-27 | BB-11 | BB-13 | Judgment and interpretation meaning applicable to outcome cardinality | BB-11 | BB-11 → BB-13 | JUDGE |
| IF-28 | BB-12 | BB-13 | Attributable explanation meaning applicable to outcome cardinality | BB-12 | BB-12 → BB-13 | EXPLAIN |
| IF-29 | BB-13 | BB-14 | Exactly-one mutually exclusive outcome cardinality | BB-13 | BB-13 → BB-14 | OUTCOME |
| IF-30 | BB-06 | BB-15 | Governed assessment identity applicable to lifecycle stewardship | BB-06 | BB-06 → BB-15 | ASSESS |
| IF-31 | BB-07 | BB-15 | Non-destructive lifecycle relationship meaning | BB-07 | BB-07 → BB-15 | ASSESS |
| IF-32 | BB-14 | BB-15 | One approved Validation Outcome applicable to lifecycle meaning | BB-14 | BB-14 → BB-15 | OUTCOME |
| IF-33 | XBB-01 | BB-15 | Knowledge Watchpoint constraint on lifecycle stewardship | XBB-01 | XBB-01 → BB-15 | WATCH |
| IF-34 | BB-13 | BB-16 | Outcome cardinality applicable to publication separation | BB-13 | BB-13 → BB-16 | OUTCOME |
| IF-35 | BB-14 | BB-16 | One approved outcome meaning applicable to publication separation | BB-14 | BB-14 → BB-16 | OUTCOME |
| IF-36 | BB-15 | BB-16 | Assessment lifecycle meaning applicable to publication separation | BB-15 | BB-15 → BB-16 | LIFE |
| IF-37 | BB-16 | BB-17 | Separated publication eligibility and publication-outcome meaning | BB-16 | BB-16 → BB-17 | PUBLISH |
| IF-38 | XBB-01 | BB-17 | Knowledge and downstream-authority constraint on terminal publication | XBB-01 | XBB-01 → BB-17 | WATCH |
| IF-39 | BB-01 | XBB-01 | Governing authority applicable to both Knowledge Watchpoints | BB-01 | BB-01 → XBB-01 | AUTH |
| IF-40 | BB-03 | XBB-01 | Observation ownership boundary applicable to Knowledge guarding | BB-03 | BB-03 → XBB-01 | OWN |
| IF-41 | BB-01 | XBB-02 | Authority-translation conformance meaning | BB-01 | BB-01 → XBB-02 | GOV |
| IF-42 | BB-02 | XBB-02 | Input-boundary conformance meaning | BB-02 | BB-02 → XBB-02 | GOV |
| IF-43 | BB-03 | XBB-02 | Observation-boundary conformance meaning | BB-03 | BB-03 → XBB-02 | GOV |
| IF-44 | BB-04 | XBB-02 | Proposition-integrity conformance meaning | BB-04 | BB-04 → XBB-02 | GOV |
| IF-45 | BB-05 | XBB-02 | Programme-authority and neutrality conformance meaning | BB-05 | BB-05 → XBB-02 | GOV |
| IF-46 | BB-06 | XBB-02 | Assessment-identity conformance meaning | BB-06 | BB-06 → XBB-02 | GOV |
| IF-47 | BB-07 | XBB-02 | Lifecycle-relationship conformance meaning | BB-07 | BB-07 → XBB-02 | GOV |
| IF-48 | BB-08 | XBB-02 | Bounded-reasoning conformance meaning | BB-08 | BB-08 → XBB-02 | GOV |
| IF-49 | BB-09 | XBB-02 | Evidence-association conformance meaning | BB-09 | BB-09 → XBB-02 | GOV |
| IF-50 | BB-10 | XBB-02 | Evidence-evaluation separation conformance meaning | BB-10 | BB-10 → XBB-02 | GOV |
| IF-51 | BB-11 | XBB-02 | Judgment and interpretation conformance meaning | BB-11 | BB-11 → XBB-02 | GOV |
| IF-52 | BB-12 | XBB-02 | Explanation conformance meaning | BB-12 | BB-12 → XBB-02 | GOV |
| IF-53 | BB-13 | XBB-02 | Outcome-cardinality conformance meaning | BB-13 | BB-13 → XBB-02 | GOV |
| IF-54 | BB-14 | XBB-02 | Outcome-meaning conformance meaning | BB-14 | BB-14 → XBB-02 | GOV |
| IF-55 | BB-15 | XBB-02 | Assessment-lifecycle conformance meaning | BB-15 | BB-15 → XBB-02 | GOV |
| IF-56 | BB-16 | XBB-02 | Publication-separation conformance meaning | BB-16 | BB-16 → XBB-02 | GOV |
| IF-57 | BB-17 | XBB-02 | Terminal-publication conformance meaning | BB-17 | BB-17 → XBB-02 | GOV |
| IF-58 | XBB-01 | XBB-02 | Watchpoint and Knowledge-authority conformance meaning | XBB-01 | XBB-01 → XBB-02 | GOV |

## 4. Conceptual Interface Contracts

### 4.1 Contract Classes

| Class | Preconditions | Postconditions | Boundary guarantees | Failure ownership |
|---|---|---|---|---|
| AUTH | Source authority meaning is established and applicable | Destination may rely on that authority within its own boundary | No architecture or authority transfer | Source owns invalid authority meaning; destination owns non-admission |
| INPUT | Source input meaning is published and conformant | Destination may rely on approved factual-boundary meaning | No unpublished or reconstructed meaning crosses | Source owns input non-conformance; destination owns refusal |
| OWN | Source ownership constraint is established | Destination remains bounded by preserved ownership | No domain or Building Block ownership transfer | Source owns constraint defect; destination owns boundary violation |
| PROP | One explicit proposition and integrity meaning are established | Destination may rely on unchanged proposition meaning | No broadening, merging, replacement or reinterpretation | BB-04 owns proposition defect; destination owns misuse |
| PROG | One neutral conformant programme is established | Destination may rely on bounded programme authority | No product, strategy, Risk or execution policy implication | BB-05 owns programme defect; destination owns policy leakage |
| ASSESS | One governed assessment identity or relationship is established | Destination may rely on bounded identity and lineage | No silent identity mutation or runtime lifecycle implication | Source owns identity defect; destination owns lineage misuse |
| WATCH | Approved Watchpoint constraint is established | Destination remains inside the non-Knowledge boundary | No reusable Knowledge or Knowledge authority | XBB-01 owns Watchpoint meaning; destination owns violation |
| REASON | Multi-fact reasoning is admissible and bounded | Destination may associate only approved facts | No reusable synthesis or cross-assessment knowledge | BB-08 owns admissibility defect; destination owns association misuse |
| EVID | Evidence association or evaluation meaning is distinct and established | Destination may rely on the specific evidentiary meaning only | No collapse into another evidentiary meaning or outcome | Source owns evidentiary defect; destination owns substitution |
| JUDGE | Bounded Validation judgment and interpretation are established | Destination may rely on Validation-owned judgment only | No product, Risk, Execution or Knowledge meaning | BB-11 owns judgment defect; destination owns authority leakage |
| EXPLAIN | Attributable non-sensitive explanation is established | Destination may associate explanation to one assessment | No sensitive, Observation-internal or implementation detail | BB-12 owns explanation defect; destination owns misuse |
| OUTCOME | Exactly-one outcome cardinality or one approved outcome is established | Destination may rely on that outcome meaning only | No Market Facts mutation or publication implication | Source owns outcome defect; destination owns collapse or misuse |
| LIFE | Validation Assessment lifecycle meaning is established | Destination may rely on attributable non-destructive lifecycle meaning | No Observation lifecycle transfer or runtime mechanism | BB-15 owns lifecycle defect; destination owns misuse |
| PUBLISH | Publication meanings are separated and eligible for terminal determination | Destination may establish exactly one terminal publication result | No automatic downstream authority | BB-16 owns separation defect; BB-17 owns terminal misuse |
| GOV | Source meaning is independently reviewable | XBB-02 may establish conformance or violation meaning | No feedback, mutation or primary-meaning ownership | Source owns source defect; XBB-02 owns conformance finding |

### 4.2 Universal Interface Contract

Every interface in the catalogue inherits these normative terms:

1. **Precondition:** the source Building Block has established the exact engineering meaning named in the catalogue and remains boundary-conformant.
2. **Postcondition:** the destination may rely on that meaning only for its approved responsibilities; no destination result is implied.
3. **Ownership:** source ownership of the transferred meaning remains unchanged.
4. **Authority:** no architecture, domain, Product, Risk, Execution, Knowledge, implementation or runtime authority transfers.
5. **Boundary:** no information outside the approved source output or destination input meaning crosses.
6. **Failure ownership:** source owns missing, invalid or non-conformant source meaning; destination owns refusal, misuse or boundary violation within its responsibility.
7. **Failure meaning:** failure is conceptual conformance meaning only and defines no error object, exception, retry, recovery or runtime path.
8. **Governance:** XBB-01 applies wherever Knowledge-sensitive meaning exists; XBB-02 applies to every interface.
9. **Verification:** both source and destination traceability, ownership, boundary and neutrality shall be independently reviewable.

## 5. Interface Responsibility and Traceability Matrix

The source responsibilities establish the transferred meaning. Destination responsibilities may rely on it without acquiring ownership.

| Interface | Source responsibilities | Destination responsibilities | Capability trace | EAP-008 trace |
|---|---|---|---|---|
| IF-01 | R1–R4 | R5–R6 | C1 → C2 | Authority; input |
| IF-02 | R1–R4 | R7–R10 | C1 → C3 | Authority; ownership |
| IF-03 | R5–R6 | R7–R10 | C2 → C3 | Input; ownership |
| IF-04 | R5–R6 | R11–R13 | C2 → C4 | Input; proposition |
| IF-05 | R7–R10 | R11–R13 | C3 → C4 | Ownership; proposition |
| IF-06 | R1–R4 | R14–R17 | C1 → C5 | Authority; programme |
| IF-07 | R11–R13 | R14–R17 | C4 → C5 | Proposition; programme |
| IF-08 | R11–R13 | R18–R20 | C4 → C6 | Proposition; assessment identity |
| IF-09 | R14–R17 | R18–R20 | C5 → C6 | Programme; assessment identity |
| IF-10 | R18–R20 | R21–R24 | C6 → C7 | Assessment identity; lifecycle relationships |
| IF-11 | R5–R6 | R25–R27 | C2 → C8 | Input; multi-fact reasoning |
| IF-12 | R11–R13 | R25–R27 | C4 → C8 | Proposition; multi-fact reasoning |
| IF-13 | R14–R17 | R25–R27 | C5 → C8 | Programme; multi-fact reasoning |
| IF-14 | R18–R20 | R25–R27 | C6 → C8 | Assessment; multi-fact reasoning |
| IF-15 | R55–R57 | R25–R27 | C21 → C8 | Watchpoints; multi-fact reasoning |
| IF-16 | R7–R10 | R28 | C3 → C9 | Ownership; evidence association |
| IF-17 | R25–R27 | R28 | C8 → C9 | Multi-fact reasoning; association |
| IF-18 | R28 | R29–R34 | C9 → C10–C13 | Evidence association; evaluation |
| IF-19 | R11–R13 | R35–R36 | C4 → C14 | Proposition; judgment |
| IF-20 | R14–R17 | R35–R36 | C5 → C14 | Programme; judgment |
| IF-21 | R18–R20 | R35–R36 | C6 → C14 | Assessment; judgment |
| IF-22 | R29–R34 | R35–R36 | C10–C13 → C14 | Evidence evaluation; judgment |
| IF-23 | R35–R36 | R37 | C14 → C15 | Judgment; explanation |
| IF-24 | R11–R13 | R38, R43–R44 | C4 → C16 | Proposition; outcome cardinality |
| IF-25 | R18–R20 | R38, R43–R44 | C6 → C16 | Assessment; outcome cardinality |
| IF-26 | R29–R34 | R38, R43–R44 | C10–C13 → C16 | Evidence evaluation; outcome separation |
| IF-27 | R35–R36 | R38, R43–R44 | C14 → C16 | Judgment; outcome cardinality |
| IF-28 | R37 | R38, R43–R44 | C15 → C16 | Explanation; outcome cardinality |
| IF-29 | R38, R43–R44 | R39–R42 | C16 → C17 | Outcome cardinality; outcome meanings |
| IF-30 | R18–R20 | R45 | C6 → C18 | Assessment identity; lifecycle |
| IF-31 | R21–R24 | R45 | C7 → C18 | Lifecycle relationships; lifecycle |
| IF-32 | R39–R42 | R45 | C17 → C18 | Outcome; lifecycle |
| IF-33 | R55–R57 | R45 | C21 → C18 | Watchpoints; lifecycle |
| IF-34 | R38, R43–R44 | R46–R48 | C16 → C19 | Outcome cardinality; publication separation |
| IF-35 | R39–R42 | R46–R48 | C17 → C19 | Outcome; publication separation |
| IF-36 | R45 | R46–R48 | C18 → C19 | Lifecycle; publication separation |
| IF-37 | R46–R48 | R49–R54 | C19 → C20 | Publication separation; terminal result |
| IF-38 | R55–R57 | R49–R54 | C21 → C20 | Watchpoints; terminal result |
| IF-39 | R1–R4 | R55–R57 | C1 → C21 | Authority; Watchpoints |
| IF-40 | R7–R10 | R55–R57 | C3 → C21 | Ownership; Watchpoints |
| IF-41 | R1–R4 | R58–R62 | C1 → C22 | Authority conformance |
| IF-42 | R5–R6 | R58–R62 | C2 → C22 | Input conformance |
| IF-43 | R7–R10 | R58–R62 | C3 → C22 | Ownership conformance |
| IF-44 | R11–R13 | R58–R62 | C4 → C22 | Proposition conformance |
| IF-45 | R14–R17 | R58–R62 | C5 → C22 | Programme conformance |
| IF-46 | R18–R20 | R58–R62 | C6 → C22 | Assessment identity conformance |
| IF-47 | R21–R24 | R58–R62 | C7 → C22 | Lifecycle relationship conformance |
| IF-48 | R25–R27 | R58–R62 | C8 → C22 | Reasoning conformance |
| IF-49 | R28 | R58–R62 | C9 → C22 | Evidence association conformance |
| IF-50 | R29–R34 | R58–R62 | C10–C13 → C22 | Evidence evaluation conformance |
| IF-51 | R35–R36 | R58–R62 | C14 → C22 | Judgment conformance |
| IF-52 | R37 | R58–R62 | C15 → C22 | Explanation conformance |
| IF-53 | R38, R43–R44 | R58–R62 | C16 → C22 | Cardinality conformance |
| IF-54 | R39–R42 | R58–R62 | C17 → C22 | Outcome conformance |
| IF-55 | R45 | R58–R62 | C18 → C22 | Lifecycle conformance |
| IF-56 | R46–R48 | R58–R62 | C19 → C22 | Publication separation conformance |
| IF-57 | R49–R54 | R58–R62 | C20 → C22 | Terminal publication conformance |
| IF-58 | R55–R57 | R58–R62 | C21 → C22 | Watchpoint conformance |

Responsibilities remain owned and allocated to their ES-03 Building Blocks. The matrix records meaning relied upon across interfaces; it does not reallocate a responsibility.

## 6. Building Block Interface Matrix

| Building Block | Incoming interfaces | Outgoing interfaces |
|---|---|---|
| BB-01 | None | IF-01, IF-02, IF-06, IF-39, IF-41 |
| BB-02 | IF-01 | IF-03, IF-04, IF-11, IF-42 |
| BB-03 | IF-02, IF-03 | IF-05, IF-16, IF-40, IF-43 |
| BB-04 | IF-04, IF-05 | IF-07, IF-08, IF-12, IF-19, IF-24, IF-44 |
| BB-05 | IF-06, IF-07 | IF-09, IF-13, IF-20, IF-45 |
| BB-06 | IF-08, IF-09 | IF-10, IF-14, IF-21, IF-25, IF-30, IF-46 |
| BB-07 | IF-10 | IF-31, IF-47 |
| BB-08 | IF-11, IF-12, IF-13, IF-14, IF-15 | IF-17, IF-48 |
| BB-09 | IF-16, IF-17 | IF-18, IF-49 |
| BB-10 | IF-18 | IF-22, IF-26, IF-50 |
| BB-11 | IF-19, IF-20, IF-21, IF-22 | IF-23, IF-27, IF-51 |
| BB-12 | IF-23 | IF-28, IF-52 |
| BB-13 | IF-24, IF-25, IF-26, IF-27, IF-28 | IF-29, IF-34, IF-53 |
| BB-14 | IF-29 | IF-32, IF-35, IF-54 |
| BB-15 | IF-30, IF-31, IF-32, IF-33 | IF-36, IF-55 |
| BB-16 | IF-34, IF-35, IF-36 | IF-37, IF-56 |
| BB-17 | IF-37, IF-38 | IF-57 |
| XBB-01 | IF-39, IF-40 | IF-15, IF-33, IF-38, IF-58 |
| XBB-02 | IF-41 through IF-58 | None |

All 19 Building Blocks are represented. No Building Block is orphaned.

## 7. Interface Dependency Matrix

An interface dependency means its source engineering meaning must be established before that interface contract is conceptually satisfied. It does not define execution order.

| Destination | Incoming interface set | Conceptual prerequisite |
|---|---|---|
| BB-02 | IF-01 | Governing authority |
| BB-03 | IF-02, IF-03 | Authority and published input |
| BB-04 | IF-04, IF-05 | Input conformance and Observation boundary |
| BB-05 | IF-06, IF-07 | Authority and explicit proposition |
| BB-06 | IF-08, IF-09 | Proposition and programme |
| BB-07 | IF-10 | Assessment identity |
| BB-08 | IF-11 through IF-15 | Input, proposition, programme, assessment and Watchpoint |
| BB-09 | IF-16, IF-17 | Ownership constraint and admissible reasoning |
| BB-10 | IF-18 | Evidence association |
| BB-11 | IF-19 through IF-22 | Proposition, programme, assessment and evidence evaluation |
| BB-12 | IF-23 | Judgment and interpretation |
| BB-13 | IF-24 through IF-28 | Proposition, assessment, evidence, judgment and explanation |
| BB-14 | IF-29 | Outcome cardinality |
| BB-15 | IF-30 through IF-33 | Assessment identity, lifecycle relationships, outcome and Watchpoint |
| BB-16 | IF-34 through IF-36 | Outcome cardinality, outcome meaning and lifecycle |
| BB-17 | IF-37, IF-38 | Publication separation and Watchpoint |
| XBB-01 | IF-39, IF-40 | Authority and Observation ownership |
| XBB-02 | IF-41 through IF-58 | Reviewable meaning from every other Building Block |

The interface dependency graph is identical in topology to the frozen ES-03 Building Block dependency graph and remains acyclic.

## 8. Interface Boundary Rules

1. IF-01 through IF-58 begin only after their source meaning is established.
2. An interface ends when the destination may rely on the named meaning within its approved boundary.
3. Interfaces carry no unstated context.
4. Interfaces never transfer ownership.
5. Interfaces never transfer architecture or execution authority.
6. Observation-owned meaning remains Observation-owned across every interface.
7. Validation-owned meaning remains Validation-owned across every interface.
8. Building Block responsibility remains with the originating Building Block.
9. Interface meaning cannot broaden a Validation Proposition.
10. Interface meaning cannot make Validation Programme conformance product, strategy, Risk or execution policy.
11. Interface meaning cannot silently mutate Validation Assessment identity.
12. Interface meaning cannot create reusable Knowledge.
13. Interface meaning cannot collapse evidentiary meanings or Validation Outcome.
14. Interface meaning cannot collapse Validation Outcome, publication eligibility or publication outcome.
15. No interface crosses upstream of the EAP-007 Market Facts Contract boundary.
16. No interface crosses downstream of the EAP-008 terminal publication boundary.

The external Market Facts Contract input and Validation Assessment terminal outputs remain architectural boundaries, not ES-04 inter-Block interfaces.

## 9. Interface Governance Rules

Every interface shall preserve:

- CAR-010 lifecycle authority;
- EAP-008 as sole direct Engineering Architecture;
- EAP-007 as upstream Engineering Architecture dependency;
- EDD-009 as supporting completed upstream Engineering Design only;
- frozen ES-01 responsibilities;
- frozen ES-02 capability ownership and dependencies;
- frozen ES-03 Building Block ownership and dependencies;
- Observation ownership;
- Validation ownership;
- provider neutrality;
- product neutrality;
- implementation neutrality;
- runtime neutrality; and
- architecture-first governance.

No interface may introduce architecture, owner, domain, dependency, responsibility, capability or Building Block scope.

Any required architectural expansion shall be returned for governance review.

## 10. Interface Watchpoint Preservation

Both approved Knowledge Watchpoints remain normative for every interface.

IF-15, IF-33 and IF-38 carry the Validation-specific Watchpoint into Knowledge-sensitive primary Building Blocks.

IF-39 and IF-40 establish the authority and ownership basis for XBB-01.

IF-58 exposes Watchpoint conformance meaning to XBB-02 without transferring Watchpoint ownership.

No interface may create:

- reusable Knowledge;
- reusable synthesis;
- generalized historical intelligence;
- persistent market memory;
- reusable cross-assessment knowledge;
- Knowledge ownership;
- Knowledge contracts;
- Knowledge dependencies;
- implementation authority; or
- runtime authority.

If any interface requires such meaning, Engineering shall stop and return the matter for Chief Architect governance.

## 11. Interface Verification Obligations

Every interface shall be verified for:

1. unique identifier;
2. unique source-destination pair;
3. justified ES-03 dependency;
4. source responsibility traceability;
5. destination responsibility traceability;
6. originating capability traceability;
7. EAP-008 traceability;
8. source ownership preservation;
9. destination boundary preservation;
10. directionality without runtime sequencing;
11. precondition completeness;
12. postcondition completeness;
13. boundary guarantee completeness;
14. conceptual failure ownership;
15. XBB-01 applicability where Knowledge-sensitive;
16. XBB-02 governance applicability;
17. Observation ownership preservation;
18. Validation ownership preservation;
19. provider and product neutrality;
20. implementation and runtime neutrality;
21. absence of APIs, messages, schemas, protocols and transports;
22. absence of persistence, algorithms and technology decisions;
23. absence of Product, Risk, Execution or Knowledge-layer authority; and
24. no semantic feedback cycle.

Verification is Engineering Design review only. It defines no implementation test or runtime verification mechanism.

## 12. Complete ES-04 Traceability

| Trace level | Preserved ES-04 evidence |
|---|---|
| EAP-008 | Interface catalogue meaning, contract classes, boundary rules, ownership rules, Watchpoints and terminal limits |
| ES-01 | R1–R62 remain allocated to their approved Building Blocks and are referenced without reallocation |
| ES-02 | C1–C22 appear in IF-01 through IF-58 capability traceability |
| ES-03 | Every one of the 58 direct Building Block dependencies is represented exactly once |
| Ownership | Catalogue ownership column and universal ownership contract |
| Boundaries | Interface Boundary Rules and per-class guarantees |
| Governance | IF-41 through IF-58 and Interface Governance Rules |
| Watchpoints | IF-15, IF-33, IF-38, IF-39, IF-40 and IF-58 |
| Verification | Interface Verification Obligations |

Traceability result:

- approved Building Blocks represented: 19;
- approved direct dependencies represented: 58;
- interfaces defined: 58;
- orphan interfaces: 0;
- duplicate source-destination pairs: 0;
- new dependencies: 0;
- responsibilities reallocated: 0;
- ownership transfers: 0; and
- semantic cycles: 0.

## 13. ES-04 Verification Criteria

Engineering Architect review shall verify:

1. exactly 58 conceptual interfaces are defined;
2. all 58 frozen ES-03 dependencies are represented exactly once;
3. every interface has one source and one destination Building Block;
4. every interface has purpose, meaning, ownership, directionality, responsibilities, preconditions, postconditions, guarantees, failure ownership, traceability, governance applicability and verification obligations;
5. all 19 Building Blocks are represented;
6. all 22 capabilities remain traceable;
7. all 62 responsibilities remain allocated exactly once to Building Blocks;
8. no interface is orphaned or duplicated;
9. interface dependencies remain conceptual and acyclic;
10. ES-01 through ES-03 remain unchanged and frozen;
11. ownership and authority separation are preserved;
12. both Knowledge Watchpoints remain normative;
13. no API, message, schema, protocol, transport, event, queue, persistence, algorithm or technology design is introduced;
14. no implementation or runtime semantics are introduced;
15. no Product, Risk, Execution or Knowledge-layer authority is introduced; and
16. ES-05 remains unauthorized.

## ES-04 Review State

| Item | State |
|---|---|
| CAR-010 Version 1.0 | Approved, Published, Synchronized and Frozen |
| EAP-008 Version 1.0 | Sole direct Engineering Architecture authority |
| EAP-007 Version 1.0 | Upstream Engineering Architecture dependency |
| EDD-009 Version 1.0 | Supporting completed upstream Engineering Design |
| EDD-011 ES-01 | Approved, Published and Frozen |
| EDD-011 ES-02 | Approved, Published and Frozen |
| EDD-011 ES-03 | Approved, Published and Frozen |
| ES-04 Draft Preparation | Complete |
| Engineering Architect review | Pending |
| Chief Systems Engineer review | Not Yet Started |
| Chief Architect review | Not Yet Started |
| ES-04 publication | Not Authorized |
| ES-04 baseline freeze | Not Authorized |
| ES-05 | Not Authorized |
| Implementation | Not Authorized |
| Runtime | Not Authorized |
