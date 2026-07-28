# EDD-011 — Market Facts Validation Assessment and Business Judgment Engineering Design

**Document ID:** EDD-011<br>
**Title:** Market Facts Validation Assessment and Business Judgment Engineering Design<br>
**Version:** 0.2<br>
**Status:** Approved<br>
**Canonical Status:** Draft<br>
**Classification:** Engineering Design Document<br>
**Owner:** Engineering Architect<br>
**Prepared By:** Engineering Design Team<br>
**Review Authority:** Chief Architect<br>
**Engineering Review Authority:** Chief Systems Engineer<br>
**Repository Location:** `docs/engineering/edd/EDD-011-MARKET-FACTS-VALIDATION-ASSESSMENT-AND-BUSINESS-JUDGMENT-ENGINEERING-DESIGN.md`<br>
**Workflow Stage:** ES-02 Published<br>
**Baseline Status:** ES-01 and ES-02 Frozen<br>
**Engineering Stage:** ES-02 Complete<br>
**Engineering Lifecycle:** In Progress<br>
**ES-01 Review Status:** Approved<br>
**ES-01 Approved By:** Chief Architect<br>
**ES-01 Baseline Status:** Frozen<br>
**ES-01 Repository Publication:** Published<br>
**ES-02 Review Status:** Approved<br>
**ES-02 Approved By:** Chief Architect<br>
**ES-02 Baseline Status:** Frozen<br>
**ES-02 Repository Publication:** Published<br>
**Authorization Decision:** CAR-010 Version 1.0<br>
**Direct Engineering Architecture:** EAP-008 Version 1.0<br>
**Upstream Engineering Architecture Dependency:** EAP-007 Version 1.0<br>
**Supporting Completed Upstream Engineering Design:** EDD-009 Version 1.0<br>
**Engineering Authority:** ES-01 published and frozen; ES-02 Draft Preparation; ES-03 through ES-05 remain subject to sequential stage gates<br>
**Architecture Authority:** None<br>
**Implementation Authority:** None<br>
**Runtime Authority:** None<br>
**Repository Status:** Published — ES-02 Frozen Baseline

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
