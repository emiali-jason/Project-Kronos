# EDD-006 — Instrument Identity Engineering Design

**Document ID:** EDD-006<br>
**Title:** Instrument Identity Engineering Design<br>
**Version:** 0.3 Draft<br>
**Status:** Draft<br>
**Canonical Status:** Draft<br>
**Classification:** Engineering Design Document<br>
**Owner:** Engineering Architect<br>
**Prepared By:** Engineering Design Team<br>
**Review Authority:** Chief Architect<br>
**Engineering Review Authority:** Chief Systems Engineer<br>
**Repository Location:** `docs/engineering/edd/EDD-006-INSTRUMENT-IDENTITY-ENGINEERING-DESIGN.md`<br>
**Workflow Stage:** Draft Preparation<br>
**Engineering Stage:** Engineering Building Block Architecture<br>
**ES-01 Review Status:** Approved<br>
**ES-01 Approved By:** Chief Systems Engineer<br>
**ES-02 Review Status:** Approved<br>
**ES-02 Approved By:** Chief Systems Engineer<br>
**ES-03 Review Status:** Approved<br>
**ES-03 Approved By:** Chief Systems Engineer<br>
**Draft Authorization:** ES-01 completed under CAR-006 Version 1.0; ES-02 through ES-05 authorized under CAR-006 Version 1.1<br>
**Direct Engineering Architecture:** EAP-004 Version 2.0<br>
**Immediate Upstream Engineering Design:** EDD-005 Version 1.0<br>
**Downstream Engineering Architecture:** EAP-005 Version 1.1<br>
**Implementation Authorization:** None<br>
**Runtime Authority:** None<br>
**Repository Status:** Published

---

# ES-01 — Engineering Scope Definition

## 1. Engineering Mission

EDD-006 shall define the implementation-independent Engineering Design responsibility required to translate EAP-004 Version 2.0 into a complete, bounded, and verifiable Instrument-owned design.

The engineered subsystem begins only with one EAIC-002 Submission Unit for which `ACCEPTED_FOR_INTERPRETATION` has already been established. It preserves the admitted Provider meaning while engineering the responsibilities for Instrument interpretation, the four independent Instrument dimensions, identity-layer semantic sufficiency, canonical identity continuity, Provider mapping and cross-Provider reconciliation evidence, Instrument Identity Contract publication eligibility, and Canonical Instrument Catalogue publication eligibility.

The subsystem terminates before EAP-005 factual attribution evaluation and before any downstream product-consumption decision.

## 2. Engineering Objectives

EDD-006 ES-01 establishes the engineering boundary required to:

1. translate EAP-004 without changing its architectural meaning;
2. preserve Instrument as the sole semantic owner of Instrument interpretation, canonical identity, Provider mapping, cross-Provider reconciliation, governed Instrument relationships and lifecycle meaning, and Instrument publication meaning;
3. preserve Provider ownership of Provider Records, assertions, dispositions, identity scopes, limitations, and provenance;
4. consume only an EAIC-002 Submission Unit already accepted for interpretation;
5. preserve Interpretation Processing Status, Interpretation Outcome, Canonical Identity Decision, and Provider Mapping Status as independent dimensions with their governed cardinality and non-implications;
6. preserve the distinction among Economic Instrument, Listed Instrument, and Derivative Contract identity layers;
7. require positive semantic sufficiency for canonical identity establishment;
8. preserve existing identity continuity before permitting new identity establishment;
9. preserve deferral, ambiguity, unsupported meaning, insufficiency, and non-establishment without forced resolution;
10. preserve Provider mapping independence and Provider-separated reconciliation evidence;
11. define publication eligibility and evidence obligations without creating publication authority; and
12. establish complete traceability and future Engineering Verification obligations within the EAP-004 boundary.

## 3. Engineering Scope

### 3.1 Scope Beginning

EDD-006 begins only after the immediate upstream Engineering Design has established `ACCEPTED_FOR_INTERPRETATION` and associated governed evidence for one EAIC-002 Submission Unit.

Receipt, contract validation, admission determination, pre-interpretation rejection, and logical response establishment remain upstream. EDD-006 neither recreates nor extends them.

### 3.2 Design-Layer Separation

| Layer | Governing responsibility |
|---|---|
| Architecture | EAP-004 and its approved governing authorities define semantic ownership, dimensions, meanings, boundaries, dependencies, contracts, invariants, and exclusions. EDD-006 does not alter them. |
| Engineering Design | EDD-006 translates the approved EAP-004 meanings into implementation-independent engineering responsibilities, design boundaries, constraints, evidence obligations, and verification traceability. ES-01 defines scope only. |
| Implementation | Outside EDD-006 ES-01 authority. No implementation decision or authority is created. |

### 3.3 Included Engineering Scope

EDD-006 includes Engineering Design responsibility for:

- admitted interpretation-input consumption;
- Provider ownership, identity-scope, assertion, limitation, and provenance preservation;
- Interpretation Processing Status;
- Interpretation Outcome;
- Canonical Identity Decision;
- Provider Mapping Status;
- governed coexistence, deferral, and bounded terminal meaning across the four dimensions;
- Economic Instrument, Listed Instrument, and Derivative Contract identity-layer sufficiency;
- existing canonical identity reuse and new canonical identity establishment;
- canonical identity continuity;
- Provider mapping and cross-Provider reconciliation evidence;
- governed Instrument relationships and lifecycle meaning only where already approved;
- Instrument Identity Contract publication eligibility and meaning;
- Canonical Instrument Catalogue publication eligibility and meaning;
- product-neutrality and downstream separation;
- evidence, provenance, security containment, observability, and Audit authority separation; and
- Engineering Verification traceability.

### 3.4 Scope Ending

EDD-006 ends when the applicable Instrument-owned interpretation, identity, mapping, evidence, and publication-eligibility meanings defined by EAP-004 have been established or explicitly preserved as deferred, ambiguous, unsupported, insufficient, or not established.

EDD-006 produces no factual attribution, Observation participation eligibility, Observation meaning, or downstream product decision. Entry into EAP-005 is permitted only through the approved Instrument Identity Contract boundary with associated safe provenance.

## 4. Engineering Responsibilities

EDD-006 owns the following Engineering Design responsibilities within the EAP-004 boundary:

1. Consume exactly one EAIC-002 Submission Unit only after `ACCEPTED_FOR_INTERPRETATION` has been established.
2. Preserve the admitted unit's immutable Provider, dataset, partition, snapshot, record, unit, contract-version, admission, evidence, and provenance associations.
3. Preserve Provider assertions, Provider vocabulary, limitations, missingness, ambiguity, duplication, inconsistency, and applicable acquisition context as Provider-owned meaning.
4. Preserve Provider Catalogue Partition Identity, Provider Snapshot Identity, Provider Record Identity, and Submission Unit identity within their governed scopes without globalizing them.
5. Exclude raw Provider content and other prohibited sensitive or private technical material from Instrument-owned engineering evidence and publication meaning.
6. Preserve contract rejection as an upstream result that never becomes an Instrument Interpretation Outcome.
7. Represent Interpretation Processing Status with the exact governed cardinality and values established by EAP-004.
8. Prevent technical receipt, contract validation, or Interpretation Admission from establishing that interpretation has begun or completed.
9. Represent exactly one governed Interpretation Outcome when the bounded interpretation activity is completed.
10. Preserve Interpretation Outcome as Instrument meaning that does not alter Provider information, Provider dispositions, Submission Eligibility, product membership, or business judgment.
11. Prevent Provider ambiguity evidence or unrecognized Provider vocabulary from automatically establishing an Instrument Interpretation Outcome.
12. Represent Canonical Identity Decision with the exact governed cardinality and values established by EAP-004.
13. Permit canonical identity establishment only after completed interpretation, an `INTERPRETED` outcome, sufficient approved Instrument evidence, resolved identity ambiguity, and an Instrument-owned reuse-or-establishment decision.
14. Preserve canonical identity non-establishment with its applicable reason and evidence without implying Instrument non-existence, Provider invalidity, or product exclusion.
15. Keep Interpretation Processing Status, Interpretation Outcome, Canonical Identity Decision, and Provider Mapping Status independent, without collapsing them into one status or allowing one dimension to imply another.
16. Preserve every EAP-004-permitted coexistence and the bounded meaning of terminal values without creating a lifecycle state or reassessment authority.
17. Preserve canonical identity and Provider mapping deferral only through the governed deferral meanings assigned to their respective dimensions.
18. Preserve Economic Instrument, Listed Instrument, and Derivative Contract as distinct Instrument-owned identity layers.
19. Establish identity-layer semantic sufficiency only from the approved meaning required by EAP-004 for the applicable layer.
20. Prevent product membership, Provider vocabulary, Provider-native identity, token or symbol presence, row order, price behavior, demand, or technical convenience from establishing semantic sufficiency.
21. Reuse an existing canonical identity when approved semantic continuity is established.
22. Permit new canonical identity establishment only when positive semantic sufficiency exists for the applicable layer and the identity remains distinguishable from existing identities.
23. Treat Provider record addition, absence, change, token reuse, symbol change, or reference change only as evaluation evidence and never as automatic canonical identity mutation.
24. Preserve canonical and historical identity continuity with attributable supporting evidence.
25. Represent Provider Mapping Status with the exact governed cardinality and values established by EAP-004.
26. Preserve Provider Mapping Status as independent from Canonical Identity Decision and prevent Provider mapping from creating or invalidating canonical identity.
27. Preserve cross-Provider reconciliation as Instrument-owned meaning with each Provider's evidence, identity, provenance, ambiguity, and conflict kept separate.
28. Prevent one Provider mapping from establishing another Provider's mapping, merging Provider partitions, globalizing Provider-native identifiers, or implying unsupported equivalence.
29. Determine Instrument Identity Contract publication eligibility only when every EAP-004 publication precondition and separately required publication authority are established.
30. Preserve the Instrument Identity Contract as an Instrument-owned publication of approved canonical meaning while excluding Provider-private, Provider-owned, and product-eligibility meaning prohibited by EAP-004.
31. Determine Canonical Instrument Catalogue publication eligibility and preserve its approved product-neutral Instrument-owned meaning.
32. Keep the Canonical Instrument Catalogue distinct from Provider Catalogue meaning, EAIC-002 submission meaning, downstream factual information, and product-specific eligibility meaning.
33. Prevent downstream consumers from writing canonical identity, classification, relationship, lifecycle, or Provider mapping meaning into Instrument-owned publication meaning.
34. Expose EAP-004 output toward EAP-005 only through the approved Instrument Identity Contract and associated safe provenance.
35. Terminate before factual attribution, Observation formation or acceptance, and any downstream product-consumption decision.
36. Preserve Provider acquisition provenance, EAIC-002 submission provenance, Instrument interpretation evidence, canonical identity evidence, and Provider mapping or reconciliation evidence as distinct evidence classes.
37. Preserve attributable evidence for Interpretation Processing Status, Interpretation Outcome, Canonical Identity Decision, and Provider Mapping Status.
38. Preserve attributable semantic-sufficiency, identity-reuse, new-identity-establishment, and identity-continuity evidence.
39. Preserve attributable Provider mapping and cross-Provider reconciliation evidence without transferring Provider ownership.
40. Preserve the reasons and evidence for deferral, ambiguity, unsupported meaning, insufficiency, and canonical identity non-establishment.
41. Preserve Instrument Identity Contract and Canonical Instrument Catalogue publication evidence where publication is separately authorized.
42. Prevent credentials, authorization material, raw Provider content, private technical state, and unapproved sensitive information from entering Instrument evidence, identity meaning, mapping meaning, observability, errors, or Audit evidence.
43. Provide only the non-sensitive observability meaning permitted by EAP-004 while preserving Audit as owner of the Audit Trail and not of Instrument or Provider semantics.
44. Preserve only already-governed Instrument relationship and lifecycle meaning, without creating relationship types, lifecycle states, transition criteria, or operational processing.
45. Preserve that Instrument interpretation, identity, mapping, and publication meaning creates no downstream factual, Validation, Risk, execution, Portfolio, Event, Audit, or product authority.
46. Establish Engineering Verification obligations covering complete EAP-004 traceability, exact dimension semantics, ownership preservation, identity-layer sufficiency, identity and mapping independence, catalogue separation, evidence safety, and authority separation.
47. Preserve repository, lifecycle, metadata, review, and authorization conformance without converting Draft Engineering Design into approved architecture or implementation authority.

## 5. Explicit Exclusions

EDD-006 ES-01 does not define, authorize, or perform:

1. architecture amendment, reinterpretation, extension, replacement, or discovery;
2. Provider acquisition, Provider communication, Provider authentication, Provider Catalogue mutation, Submission Eligibility, or Provider-side authority establishment;
3. EAIC-002 presentation, delivery, technical receipt, contract validation, admission determination, pre-interpretation rejection, or logical response establishment;
4. raw Provider-content processing or correction;
5. parsing, matching, ranking, scoring, fuzzy logic, normalization, enrichment, deduplication, repair, automated resolution, algorithms, or thresholds;
6. new Instrument relationship types, lifecycle states, lifecycle transitions, rollover processing, successor discovery, or continuous-instrument construction;
7. mapping-effective-time mechanics or Provider mapping implementation;
8. factual attribution, Observation formation, Observation acceptance, Market Facts, or factual correctness;
9. Validation, Risk, execution, Portfolio, Event, or Audit meaning;
10. product-universe membership, Product Eligibility, product consumption, strategy, or execution selection;
11. physical catalogue realization, persistence design, interfaces at implementation detail, or technology choice;
12. implementation design, production code, or operational activation;
13. approval, canonicalization, publication, or implementation authority for EDD-006; or
14. ES-02 capability decomposition or any later Engineering stage.

## 6. Engineering Assumptions

EDD-006 ES-01 relies only on the following governed assumptions and preconditions:

1. CAR-006 Version 1.0 remains the approved authority for ES-01 Draft Preparation only.
2. EAP-004 Version 2.0 remains the sole direct, approved, canonical, and active Engineering Architecture baseline for EDD-006.
3. The approved Instrument Domain, Provider Domain, EAIC-002, and EAP-004 ownership model remains unchanged.
4. The immediate upstream boundary supplies one EAIC-002 Submission Unit already accepted for interpretation with its governed evidence associations intact.
5. Provider-owned evidence remains attributable and immutable in meaning when consumed by Instrument Engineering Design.
6. Applicable approved Instrument context may be consumed only where already governed; absence of sufficient context remains explicit and cannot be repaired by assumption.
7. Existing Instrument relationships and lifecycle meaning may be preserved only where separately approved architecture already establishes them.
8. Instrument Identity Contract or Canonical Instrument Catalogue publication requires separately established publication authority; EDD-006 may define eligibility and meaning but does not assume that authority.
9. EAP-005 remains the immediate downstream Engineering Architecture and begins only at its approved factual-attribution boundary.
10. Any unresolved matter not decided by EAP-004 remains unresolved and cannot be completed by Engineering convenience.

## 7. Engineering Constraints

EDD-006 ES-01 is constrained as follows:

1. EAP-004 meanings, values, cardinalities, ordering, coexistence rules, non-implications, invariants, and exclusions are normative.
2. Instrument remains the sole semantic owner of Instrument interpretation and every Instrument-owned output within scope.
3. Provider information remains Provider-owned throughout Instrument interpretation and identity engineering.
4. EAIC-002 is the sole admitted Provider-to-Instrument boundary for the governed Instrument Master dataset.
5. Instrument interpretation begins only after `ACCEPTED_FOR_INTERPRETATION`.
6. Contract rejection never becomes an Interpretation Outcome.
7. The four Instrument dimensions remain independent and retain their exact governed cardinality.
8. Processing status does not establish an Interpretation Outcome.
9. `INTERPRETED` does not by itself establish canonical identity.
10. Canonical identity does not by itself establish Provider mapping.
11. Provider mapping does not create canonical identity.
12. Provider-owned identity scopes never become canonical identity automatically.
13. Instrument does not silently repair, select, merge, discard, or globalize Provider evidence.
14. Canonical identity remains product-neutral and independent of product membership or eligibility.
15. Identity-layer sufficiency remains semantic and cannot be replaced by a technical heuristic or Provider-native identifier.
16. Existing identity continuity precedes new identity establishment where approved semantic continuity exists.
17. Unresolved ambiguity, conflict, insufficiency, unsupported meaning, and deferral remain explicit.
18. Cross-Provider reconciliation remains Instrument-owned and preserves Provider-separated evidence and provenance.
19. Provider snapshot currentness and Provider record change do not create Instrument lifecycle meaning.
20. The Canonical Instrument Catalogue remains distinct from Provider Catalogue and downstream product or factual-information collections.
21. Instrument publication creates no downstream eligibility, acceptance, judgment, approval, or execution authority.
22. Sensitive or private technical material remains excluded from Instrument evidence and publication meaning.
23. Evidence classes and their applicable time meanings remain distinct and attributable.
24. EDD-006 remains implementation-independent, Provider-neutral, product-neutral, and bounded before EAP-005 factual attribution.
25. EDD-006 remains Draft and non-canonical until completion of all separately governed later stages, reviews, verification, approval, canonicalization, and publication.
26. ES-01 creates no authority beyond Engineering Scope Definition.

## 8. Traceability to Governing Architecture

| EDD-006 ES-01 element | Direct authority | Preserved engineering effect |
|---|---|---|
| Draft creation and stage limit | CAR-006 Sections 4–7 | Authorizes Version 0.1 ES-01 only; all later stages and implementation authority remain excluded. |
| Engineering Mission and boundary | EAP-004 Sections 1, 4, and 18 | Begins after accepted Interpretation Admission and ends before EAP-005 factual attribution or downstream product consumption. |
| Ownership model | EAP-004 Section 6; Instrument Domain; Provider Domain; Domain Ownership Matrix | Preserves Instrument ownership of interpretation and canonical meaning and Provider ownership of Provider meaning. |
| Responsibilities 1–6 | EAP-004 Sections 7 and 17; EAIC-002 | Preserves the admitted input boundary, identity scopes, Provider evidence, and rejection separation. |
| Responsibilities 7–17 | EAP-004 Sections 8–12 | Translates the four independent dimensions, coexistence, terminal meaning, and deferral constraints. |
| Responsibilities 18–24 | EAP-004 Sections 13–14 | Translates identity-layer sufficiency, existing identity reuse, new identity establishment, and continuity. |
| Responsibilities 25–28 | EAP-004 Sections 11 and 17; Instrument Domain | Translates Provider Mapping Status and cross-Provider reconciliation without ownership transfer or unsupported equivalence. |
| Responsibilities 29–35 | EAP-004 Sections 15–18; EAP-005 | Translates Instrument publication eligibility, catalogue separation, downstream restrictions, and terminal boundary. |
| Responsibilities 36–43 | EAP-004 Section 19 | Translates provenance, evidence, security containment, observability, and Audit authority separation. |
| Responsibilities 44–45 | EAP-004 Sections 16, 18, and 20; Instrument Domain | Preserves only governed relationship and lifecycle meaning and every downstream non-implication. |
| Responsibilities 46–47 | EAP-004 Sections 20–21; EAS-007; DOC-001 | Establishes future verification, repository, lifecycle, review, and authority-conformance obligations. |
| Explicit Exclusions | EAP-004 Section 5; CAR-006 Section 5 | Preserves every architecture, ownership, downstream, implementation, and stage prohibition. |
| Engineering Assumptions | EAP-004 Sections 3, 7, 15–18, and 23; CAR-006 | Limits assumptions to approved authorities, admitted inputs, existing governed context, and separate publication authority. |
| Engineering Constraints | EAP-004 Section 20; ADP-001J; Instrument Domain; Provider Domain | Carries the mandatory architectural and engineering invariants into the Engineering Design boundary. |

This traceability records derivation only. EAP-004 remains the sole direct Engineering Architecture authority and is not duplicated, amended, or replaced by EDD-006.

## 9. Governing Repository Authorities

EDD-006 ES-01 derives only from approved repository authority. The governing authorities and their bounded effects are:

| Repository authority | Governing effect on EDD-006 ES-01 |
|---|---|
| [CAR-006 — EDD-006 ES-01 Draft Preparation Authorization Decision](../../governance/reviews/CAR-006-EDD-006-ES-01-DRAFT-PREPARATION-AUTHORIZATION-DECISION.md) | Authorizes creation of Version 0.1 Draft and ES-01 Engineering Scope Definition only; grants no later-stage, implementation, or runtime authority. |
| [EAP-004 — Instrument Interpretation and Canonical Identity Establishment Engineering Architecture](../eap/EAP-004-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT.md) | Sole direct Engineering Architecture baseline; governs the mission, scope, responsibilities, boundaries, dimensions, evidence obligations, invariants, exclusions, and verification traceability translated by ES-01. |
| [Instrument Domain Architecture](../../architecture/platform/domains/instrument/ARCHITECTURE.md) | Governs Instrument semantic ownership, the four independent dimensions, canonical identity, Provider mapping, cross-Provider reconciliation, relationships and lifecycle meaning already approved, and Instrument publication meaning. |
| [Provider Domain Architecture](../../architecture/platform/domains/provider/ARCHITECTURE.md) | Governs Provider ownership, Provider identity scopes, catalogue and snapshot meaning, record dispositions, limitations, and Provider provenance that EDD-006 must preserve. |
| [EAIC-002 — Provider → Instrument Submission Contract](../../architecture/interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md) | Governs the sole Provider-to-Instrument submission boundary and the admitted Submission Unit consumed by EDD-006. |
| [EAP-003 — Provider-to-Instrument Architectural Admissibility](../eap/EAP-003-PROVIDER-TO-INSTRUMENT-ARCHITECTURAL-ADMISSIBILITY.md) | Governs the immediate upstream Engineering Architecture and establishes the accepted-for-interpretation precondition without transferring upstream responsibility. |
| [EAP-005 — Instrument-to-Observation Attribution Eligibility](../eap/EAP-005-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY.md) | Governs the immediate downstream Engineering Architecture and fixes the terminal boundary before factual attribution. |
| [EAS-007 — Engineering Design Document Governance Standard](../eap/EAS-007-ENGINEERING-DESIGN-DOCUMENT-GOVERNANCE-STANDARD.md) | Governs EDD lifecycle, metadata, ownership, traceability, review, approval, canonicalization, repository publication, and authority separation. |
| [DOC-001 — Document Identification, Classification & Metadata Standard](../../governance/documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md) | Governs controlled-document identity, classification, metadata, repository location, lifecycle state, and Document Register consistency. |

The following approved authorities constrain EDD-006 through EAP-004 and remain unchanged:

- [PLATFORM-000 — KRONOS Platform Constitution](../../architecture/platform/PLATFORM-000-CONSTITUTION.md);
- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../../architecture/platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md);
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../architecture/migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md);
- [ADP-001B — Instrument Identity Architecture](../../architecture/products/swing/SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md);
- [ADP-001J — Instrument Interpretation and Canonical Identity Establishment Architecture](../../architecture/products/swing/SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md);
- [ADP-001D — Instrument → Observation Contract](../../architecture/products/swing/SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md);
- [Domain Ownership Matrix](../../architecture/platform/DOMAIN_OWNERSHIP_MATRIX.md);
- [Domain Dependency Matrix](../../architecture/platform/DOMAIN_DEPENDENCY_MATRIX.md);
- [Project KRONOS Data Flow](../../architecture/DATA_FLOW.md); and
- [EAS-001 through EAS-006](../eap/EAS-001-ENGINEERING-ARCHITECTURE-FRAMEWORK.md), together with EAS-007.

Repository content is the sole authority for this Engineering Design. Undocumented discussion creates no engineering authority, and any conflict is resolved in favor of the approved repository authority.

---

# ES-02 — Engineering Capability Design

ES-02 decomposes the approved ES-01 scope into cohesive engineering capabilities and conceptual engineering components. It allocates responsibility only. It does not define building blocks, modules, interfaces, physical realization, operational sequencing, or technology.

Every ES-02 capability remains subordinate to EAP-004 Version 2.0 and preserves the complete ES-01 boundary. No capability creates new architecture, ownership, authority, or engineering scope.

## 1. Engineering Capability Decomposition

The EDD-006 capability model contains exactly 16 capabilities:

| Capability | Name | Engineering purpose | ES-01 responsibilities |
|---|---|---|---|
| C1 | Admitted Interpretation Input Stewardship | Preserve one accepted EAIC-002 Submission Unit and all governed Provider-owned meaning required for Instrument evaluation. | R1–R6 |
| C2 | Interpretation Processing Status | Establish the independent processing-status dimension without implying any other Instrument meaning. | R7–R8 |
| C3 | Interpretation Outcome | Establish the bounded Instrument Interpretation Outcome while preserving Provider meaning and outcome non-implications. | R9–R11 |
| C4 | Canonical Identity Decision | Establish the independent canonical-identity decision and preserve justified non-establishment. | R12–R14 |
| C5 | Dimension Independence and Coexistence | Preserve independence, permitted coexistence, terminal meaning, and deferral across the four Instrument dimensions. | R15–R17 |
| C6 | Identity-Layer Semantic Sufficiency | Establish approved sufficiency meaning independently for Economic Instrument, Listed Instrument, and Derivative Contract layers. | R18–R20 |
| C7 | Canonical Identity Continuity and Establishment | Preserve existing identity continuity and govern reuse or new identity establishment from positive semantic sufficiency. | R21–R24 |
| C8 | Provider Mapping Determination | Establish Provider Mapping Status independently from canonical identity while preserving its governed meanings. | R25–R26 |
| C9 | Cross-Provider Reconciliation | Preserve Instrument-owned reconciliation evidence without merging Provider scopes or inventing equivalence. | R27–R28 |
| C10 | Instrument Identity Contract Publication Eligibility | Determine eligibility and preserve approved meaning for the Instrument Identity Contract without creating publication authority. | R29–R30 |
| C11 | Canonical Instrument Catalogue Publication Eligibility | Determine eligibility and preserve product-neutral Canonical Instrument Catalogue meaning and write-ownership restrictions. | R31–R33 |
| C12 | Downstream Boundary Control | Restrict EDD-006 output to the approved Instrument Identity Contract boundary and terminate before EAP-005 evaluation. | R34–R35 |
| C13 | Evidence and Provenance Integrity | Preserve distinct, attributable evidence and provenance obligations for every governed EDD-006 meaning. | R36–R41 |
| C14 | Security Containment and Observability | Exclude prohibited sensitive material and preserve only approved non-sensitive observability with Audit authority separation. | R42–R43 |
| C15 | Governed Relationship and Authority Separation | Preserve only already-approved relationship and lifecycle meaning and prevent downstream authority creation. | R44–R45 |
| C16 | Engineering Verification and Repository Conformance | Establish verification, traceability, lifecycle, metadata, review, and authorization conformance. | R46–R47 |

The decomposition is exhaustive and exclusive: each ES-01 responsibility is allocated to exactly one capability, and every capability is justified by at least one ES-01 responsibility.

## 2. Engineering Components

Each capability is represented by one conceptual engineering component at ES-02. These components are responsibility boundaries only and do not predetermine the ES-03 building-block model.

| Component | Capability | Conceptual engineering input | Conceptual engineering output |
|---|---|---|---|
| EC-01 | C1 | Accepted EAIC-002 Submission Unit and its governed associations | Preserved admitted interpretation-input meaning |
| EC-02 | C2 | Preserved admitted input meaning and processing evidence obligations | One governed Interpretation Processing Status meaning |
| EC-03 | C3 | Preserved admitted input meaning and completed processing meaning | One governed Interpretation Outcome meaning when applicable |
| EC-04 | C4 | Processing, outcome, semantic-sufficiency, continuity, and establishment meaning | One governed Canonical Identity Decision meaning |
| EC-05 | C5 | The four independently established dimension meanings | Governed coexistence, terminal-meaning, and deferral conformance |
| EC-06 | C6 | Provider-owned evidence and applicable approved Instrument context | Identity-layer semantic-sufficiency meaning |
| EC-07 | C7 | Semantic-sufficiency, continuity, distinction, and Provider-change evidence | Reuse-or-establishment determination evidence with continuity evidence |
| EC-08 | C8 | Canonical-identity meaning where applicable and reconciliation evidence | One governed Provider Mapping Status meaning |
| EC-09 | C9 | Canonical-identity decision and Provider-separated identity, provenance, ambiguity, and conflict evidence | Instrument-owned reconciliation evidence without unsupported equivalence |
| EC-10 | C10 | Canonical-identity, continuity, mapping, evidence, and containment conformance | Instrument Identity Contract publication-eligibility meaning |
| EC-11 | C11 | Approved canonical identity, relationship, continuity, mapping, and evidence meaning | Canonical Instrument Catalogue publication-eligibility meaning |
| EC-12 | C12 | Eligible Instrument Identity Contract meaning and safe provenance | EDD-006 terminal boundary meaning toward EAP-005 |
| EC-13 | C13 | EAP-004 evidence and provenance obligations | Distinct evidence classes, attribution requirements, and preservation constraints |
| EC-14 | C14 | EAP-004 sensitive-data exclusions and permitted observability meaning | Containment and observability constraints with Audit authority preserved |
| EC-15 | C15 | Approved Instrument relationship, lifecycle, ownership, and authority constraints | Preserved relationship meaning and downstream non-authority constraints |
| EC-16 | C16 | ES-01, EAP-004, component allocation, and repository governance traceability | Engineering conformance obligations and review evidence requirements |

All 16 components are owned as EDD-006 Engineering Design responsibilities. Semantic ownership remains assigned by EAP-004: Instrument owns Instrument meaning, Provider retains Provider meaning, and Audit retains the Audit Trail only.

## 3. Component Responsibilities

### 3.1 EC-01 — Admitted Interpretation Input Stewardship

EC-01 owns consumption-boundary qualification, immutable association preservation, Provider-meaning preservation, Provider identity-scope preservation, sensitive-content exclusion at entry, and contract-rejection separation.

### 3.2 EC-02 — Interpretation Processing Status

EC-02 owns the exact processing-status cardinality and meaning and prevents upstream boundary results from establishing interpretation progress.

### 3.3 EC-03 — Interpretation Outcome

EC-03 owns the exact bounded outcome cardinality and meaning, Provider non-mutation, and protection against automatic conversion of Provider ambiguity or vocabulary limitations into Instrument outcomes.

### 3.4 EC-04 — Canonical Identity Decision

EC-04 owns canonical-identity decision cardinality, establishment preconditions, and attributable non-establishment meaning.

### 3.5 EC-05 — Dimension Independence and Coexistence

EC-05 owns non-collapse of the four dimensions, permitted coexistence, bounded terminal meaning, and dimension-specific deferral.

### 3.6 EC-06 — Identity-Layer Semantic Sufficiency

EC-06 owns separation of the three identity layers, positive semantic-sufficiency meaning, and exclusion of technical or product-derived substitutes for sufficiency.

### 3.7 EC-07 — Canonical Identity Continuity and Establishment

EC-07 owns existing-identity reuse assessment, bounded new-identity establishment assessment, Provider-change non-mutation, and canonical and historical continuity evidence.

### 3.8 EC-08 — Provider Mapping Determination

EC-08 owns Provider Mapping Status cardinality, independence from Canonical Identity Decision, and the prohibition on mapping-created identity.

### 3.9 EC-09 — Cross-Provider Reconciliation

EC-09 owns Provider-separated reconciliation evidence, provenance preservation, conflict preservation, and the prohibition on cross-Provider scope merger or unsupported equivalence.

### 3.10 EC-10 — Instrument Identity Contract Publication Eligibility

EC-10 owns publication-precondition assessment and preservation of approved Instrument Identity Contract meaning and exclusions.

### 3.11 EC-11 — Canonical Instrument Catalogue Publication Eligibility

EC-11 owns catalogue-publication eligibility, product-neutral catalogue meaning, separation from Provider and downstream collections, and Instrument-only write ownership.

### 3.12 EC-12 — Downstream Boundary Control

EC-12 owns the sole EDD-006 terminal projection toward EAP-005 and prevents factual attribution, Observation meaning, or downstream product decisions from entering EDD-006.

### 3.13 EC-13 — Evidence and Provenance Integrity

EC-13 owns evidence-class separation, attribution, preservation of dimension and identity evidence, reconciliation evidence, unresolved-meaning evidence, and publication evidence where separately authorized.

### 3.14 EC-14 — Security Containment and Observability

EC-14 owns sensitive-material exclusion, permitted non-sensitive observability, and preservation of Audit authority without semantic ownership transfer.

### 3.15 EC-15 — Governed Relationship and Authority Separation

EC-15 owns preservation of already-governed relationship and lifecycle meaning and every EAP-004 downstream non-implication.

### 3.16 EC-16 — Engineering Verification and Repository Conformance

EC-16 owns complete architecture and scope traceability, design-conformance obligations, repository metadata, lifecycle, review, and authorization conformance.

## 4. Component Boundaries

| Component | Boundary begins | Boundary ends | Explicitly remains outside |
|---|---|---|---|
| EC-01 | At one accepted EAIC-002 Submission Unit | With preserved admitted input meaning suitable for Instrument-owned evaluation | Receipt, contract validation, admission determination, Provider acquisition, and Provider mutation |
| EC-02 | With preserved admitted input meaning | With exactly one governed processing-status meaning | Interpretation Outcome, identity decision, mapping status, and lifecycle meaning |
| EC-03 | With preserved admitted meaning and completed processing meaning | With exactly one governed Interpretation Outcome when applicable | Provider disposition, identity decision, mapping status, and product meaning |
| EC-04 | With completed interpretation meaning and required identity evidence | With exactly one governed canonical-identity decision | Provider mapping, product eligibility, and downstream factual meaning |
| EC-05 | With independently established dimension meanings | With coexistence, terminal-meaning, and deferral conformance | Creation of a combined status, lifecycle state, or reassessment authority |
| EC-06 | With preserved Provider evidence and approved Instrument context | With semantic-sufficiency meaning for the applicable identity layer | Parsing rules, heuristics, scores, thresholds, and product membership |
| EC-07 | With positive sufficiency and continuity evidence | With governed reuse-or-establishment determination evidence and continuity evidence | Automatic mutation from Provider record, symbol, token, or reference change |
| EC-08 | With mapping evidence and canonical target meaning where required | With exactly one governed Provider Mapping Status | Canonical identity creation, Provider disposition, and cross-Provider scope merger |
| EC-09 | With canonical-identity decision and Provider-separated identity and provenance evidence | With Instrument-owned reconciliation evidence | Silent Provider preference, partition merger, and unsupported equivalence |
| EC-10 | With established publication preconditions | With Instrument Identity Contract publication-eligibility meaning | Publication authority itself, Provider-private meaning, and product eligibility |
| EC-11 | With approved canonical catalogue meaning and publication preconditions | With Canonical Instrument Catalogue publication-eligibility meaning | Physical catalogue realization, Provider Catalogue meaning, and product-specific lists |
| EC-12 | With eligible Instrument Identity Contract meaning and safe provenance | At the EAP-005 factual-attribution boundary | Factual attribution, Observation formation, and downstream product decisions |
| EC-13 | At every governed evidence obligation within EDD-006 | With distinct, attributable preservation requirements | Semantic ownership transfer and substitution of one evidence time or class for another |
| EC-14 | At every EDD-006 evidence and publication boundary | With containment and permitted observability constraints | Sensitive material exposure and Audit ownership of Provider or Instrument meaning |
| EC-15 | At approved Instrument relationship, lifecycle, and authority constraints | With preserved relationship meaning and downstream non-authority | New relationship types, lifecycle states, transitions, or downstream authority |
| EC-16 | At ES-01, EAP-004, CAR-006, and repository-governance traceability | With complete ES-02 conformance and review obligations | Engineering approval, architecture amendment, and later-stage design |

The boundaries are mutually exclusive by owned responsibility. Cross-cutting constraints from EC-13 through EC-15 apply to other components without transferring those components' semantic responsibilities.

## 5. Component Dependencies

### 5.1 Dependency Rules

Component dependencies describe required engineering meaning only. They do not define calls, timing, orchestration, concurrency, or physical interaction.

The primary semantic dependency model is acyclic:

| Component | Direct engineering dependencies | Dependency meaning |
|---|---|---|
| EC-01 | None within EDD-006 | Begins at the separately governed accepted EAIC-002 boundary. |
| EC-13 | None | Establishes cross-cutting evidence and provenance obligations. |
| EC-14 | None | Establishes cross-cutting containment and observability obligations. |
| EC-15 | None | Establishes cross-cutting relationship and authority-separation obligations. |
| EC-02 | EC-01, EC-13, EC-14, EC-15 | Processing status requires admitted meaning and governed conformance obligations. |
| EC-03 | EC-01, EC-02, EC-13, EC-14, EC-15 | Outcome meaning requires admitted meaning and completed processing meaning. |
| EC-06 | EC-01, EC-13, EC-14, EC-15 | Sufficiency requires preserved evidence and approved Instrument context. |
| EC-07 | EC-01, EC-06, EC-13, EC-14, EC-15 | Identity continuity and establishment require positive semantic sufficiency and preserved evidence. |
| EC-04 | EC-02, EC-03, EC-07, EC-13, EC-14, EC-15 | Canonical identity decision requires processing, outcome, and reuse-or-establishment determination evidence. |
| EC-09 | EC-01, EC-04, EC-06, EC-07, EC-13, EC-14, EC-15 | Reconciliation requires a canonical-identity decision, Provider-separated evidence, and approved Instrument identity meaning. |
| EC-08 | EC-04, EC-09, EC-13, EC-14, EC-15 | Mapping status uses identity meaning where applicable and reconciliation evidence. |
| EC-05 | EC-02, EC-03, EC-04, EC-08, EC-13, EC-15 | Coexistence conformance evaluates the four independent dimensions without collapsing them. |
| EC-10 | EC-04, EC-05, EC-07, EC-08, EC-13, EC-14, EC-15 | Contract eligibility requires identity, coexistence, continuity, applicable mapping, evidence, and containment conformance. |
| EC-11 | EC-04, EC-05, EC-07, EC-08, EC-13, EC-14, EC-15 | Catalogue eligibility requires approved canonical meaning, coexistence, evidence, and authority separation. |
| EC-12 | EC-10, EC-13, EC-14, EC-15 | Terminal projection requires eligible contract meaning and safe provenance. |
| EC-16 | EC-01 through EC-15 | Verification consumes traceability from every component and creates no semantic feedback dependency. |

### 5.2 Dependency Preservation

- EC-01 preserves the sole admitted entry boundary.
- EC-02, EC-03, EC-04, and EC-08 remain distinct despite their approved dependency direction.
- EC-06 and EC-07 preserve positive semantic sufficiency and identity continuity before identity establishment.
- EC-09 preserves Provider-separated reconciliation evidence before EC-08 establishes mapping meaning.
- EC-10 and EC-11 remain separate publication-eligibility responsibilities.
- EC-12 is the sole terminal downstream component.
- EC-13, EC-14, and EC-15 are cross-cutting constraints, not alternative semantic owners.
- EC-16 assesses conformance and does not modify component meaning.

## 6. Engineering Information Flow

Engineering information flow describes transfer of established meaning between conceptual components. It is not an execution sequence.

| Flow | Source | Consumer | Engineering meaning transferred |
|---|---|---|---|
| EIF-01 | EC-01 | EC-02, EC-03, EC-06, EC-07, EC-09 | Preserved admitted Submission Unit meaning and Provider-owned evidence associations |
| EIF-02 | EC-02 | EC-03, EC-04, EC-05 | Interpretation Processing Status meaning |
| EIF-03 | EC-03 | EC-04, EC-05 | Interpretation Outcome meaning |
| EIF-04 | EC-06 | EC-07 | Applicable identity-layer semantic-sufficiency meaning |
| EIF-05 | EC-07 | EC-04, EC-09, EC-10, EC-11 | Reuse-or-establishment determination evidence and continuity evidence |
| EIF-06 | EC-04 | EC-05, EC-08, EC-09, EC-10, EC-11 | Canonical Identity Decision meaning |
| EIF-07 | EC-09 | EC-08 | Provider-separated reconciliation evidence |
| EIF-08 | EC-08 | EC-05, EC-10, EC-11 | Provider Mapping Status meaning |
| EIF-09 | EC-05 | EC-10, EC-11 | Four-dimension coexistence and bounded terminal-meaning conformance |
| EIF-10 | EC-13 | EC-01 through EC-12 and EC-15 | Evidence-class, attribution, provenance, and preservation obligations |
| EIF-11 | EC-14 | EC-01 through EC-13 and EC-15 | Sensitive-material containment and permitted observability constraints |
| EIF-12 | EC-15 | EC-01 through EC-14 | Relationship, lifecycle, ownership, and downstream-authority constraints |
| EIF-13 | EC-10 | EC-12 | Eligible Instrument Identity Contract meaning and associated safe provenance obligations |
| EIF-14 | EC-01 through EC-15 | EC-16 | Responsibility, boundary, dependency, constraint, and traceability evidence |

No information flow transfers semantic ownership. Provider meaning remains Provider-owned, Instrument meaning remains Instrument-owned, and Audit remains owner only of the Audit Trail.

## 7. Responsibility Allocation

### 7.1 One-to-One Allocation Matrix

| ES-01 responsibility | Capability | Component |
|---|---|---|
| R1–R6 | C1 | EC-01 |
| R7–R8 | C2 | EC-02 |
| R9–R11 | C3 | EC-03 |
| R12–R14 | C4 | EC-04 |
| R15–R17 | C5 | EC-05 |
| R18–R20 | C6 | EC-06 |
| R21–R24 | C7 | EC-07 |
| R25–R26 | C8 | EC-08 |
| R27–R28 | C9 | EC-09 |
| R29–R30 | C10 | EC-10 |
| R31–R33 | C11 | EC-11 |
| R34–R35 | C12 | EC-12 |
| R36–R41 | C13 | EC-13 |
| R42–R43 | C14 | EC-14 |
| R44–R45 | C15 | EC-15 |
| R46–R47 | C16 | EC-16 |

### 7.2 Allocation Rules

1. Responsibilities R1 through R47 are allocated exactly once.
2. No component owns a responsibility outside ES-01.
3. No cross-cutting constraint transfers the primary responsibility allocated to another component.
4. No component transfers Provider, Instrument, Observation, product, or Audit ownership.
5. No unallocated or duplicate responsibility remains.

## 8. Capability Constraints

| Capability | Mandatory capability constraints |
|---|---|
| C1 | Consume only an accepted EAIC-002 Submission Unit; preserve immutable associations and Provider identity scopes; never convert upstream rejection into Instrument outcome meaning. |
| C2 | Preserve exact processing-status cardinality; prevent receipt, validation, or admission meaning from establishing processing progress; imply no other dimension. |
| C3 | Preserve exact outcome cardinality; require completed bounded interpretation; alter no Provider meaning and infer no automatic outcome from Provider ambiguity or vocabulary. |
| C4 | Preserve exact decision cardinality; require every EAP-004 establishment precondition; preserve justified non-establishment without downstream implication. |
| C5 | Keep all four dimensions independent; preserve every permitted coexistence and bounded terminal meaning; use only governed dimension-specific deferral. |
| C6 | Keep all three identity layers distinct; require positive approved semantic evidence; exclude product, Provider-native, behavioral, and technical substitutes for sufficiency. |
| C7 | Prefer existing identity continuity where established; require positive sufficiency for new identity; never mutate identity automatically from Provider record change. |
| C8 | Preserve exact mapping-status cardinality; keep mapping independent from canonical identity; require a canonical target for mapped meaning and never create identity through mapping. |
| C9 | Keep every Provider's evidence and provenance separate; prohibit silent Provider preference, partition merger, identifier globalization, and unsupported equivalence. |
| C10 | Require all EAP-004 publication preconditions and separate publication authority; publish only approved Instrument-owned meaning; exclude prohibited Provider and product meaning. |
| C11 | Preserve product-neutral catalogue meaning; keep the catalogue distinct from Provider and downstream collections; permit only Instrument-owned canonical writes. |
| C12 | Use only the approved Instrument Identity Contract boundary with safe provenance; terminate before factual attribution and Observation meaning; create no downstream decision. |
| C13 | Keep evidence classes and applicable time meanings distinct; preserve attribution and unresolved reasons; transfer no Provider ownership. |
| C14 | Exclude credentials, raw Provider content, and private technical material; expose only approved non-sensitive observability; preserve Audit authority separation. |
| C15 | Preserve only already-governed relationship and lifecycle meaning; create no new state or transition; create no downstream factual, business, execution, or product authority. |
| C16 | Verify complete ES-01 and EAP-004 traceability; preserve repository and lifecycle conformance; create no architecture, approval, or later-stage authority. |

These constraints survive all later EDD-006 Engineering Stages and any separately authorized future realization.

## 9. ES-01 and EAP-004 Traceability

| Capability | ES-01 authority | Direct EAP-004 authority |
|---|---|---|
| C1 | R1–R6 | Sections 7, 17, and 19 |
| C2 | R7–R8 | Sections 8 and 20 |
| C3 | R9–R11 | Sections 9 and 20 |
| C4 | R12–R14 | Sections 10 and 20 |
| C5 | R15–R17 | Sections 12, 17, and 20 |
| C6 | R18–R20 | Sections 13 and 20 |
| C7 | R21–R24 | Sections 14 and 20 |
| C8 | R25–R26 | Sections 11 and 20 |
| C9 | R27–R28 | Sections 11, 17, and 20 |
| C10 | R29–R30 | Sections 15, 19, and 20 |
| C11 | R31–R33 | Sections 16, 18, and 20 |
| C12 | R34–R35 | Sections 18 and 20 |
| C13 | R36–R41 | Section 19 |
| C14 | R42–R43 | Sections 19 and 20 |
| C15 | R44–R45 | Sections 16, 18, and 20 |
| C16 | R46–R47 | Sections 20 and 21; CAR-006 Version 1.1; EAS-007; DOC-001 |

The traceability model confirms complete realization of ES-01 without duplication, loss, reinterpretation, or extension. EAP-004 remains the sole direct Engineering Architecture authority.

---

# ES-03 — Engineering Building Block Design

ES-03 translates the approved ES-02 capability model into bounded Engineering Building Blocks. The Building Blocks allocate established engineering meaning only. They do not define modules, services, classes, interfaces, physical components, operational sequencing, or technology.

Every Building Block remains subordinate to EAP-004 Version 2.0 and preserves the complete ES-01 and ES-02 boundaries. The model contains 12 primary Building Blocks and four cross-cutting Building Blocks. Each ES-02 capability and conceptual component is realized exactly once.

## 1. Engineering Building Blocks

### 1.1 Primary Building Blocks

| Building Block | Name | Engineering purpose | ES-02 realization |
|---|---|---|---|
| BB-01 | Admitted Interpretation Input Boundary | Preserve one accepted EAIC-002 Submission Unit and its governed Provider-owned meaning as the sole EDD-006 interpretation input. | C1 / EC-01 |
| BB-02 | Interpretation Processing Status Determination | Establish the independent processing-status dimension with its exact approved cardinality and non-implications. | C2 / EC-02 |
| BB-03 | Interpretation Outcome Determination | Establish the bounded Instrument Interpretation Outcome without altering or replacing Provider meaning. | C3 / EC-03 |
| BB-04 | Identity-Layer Semantic Sufficiency Assessment | Establish approved semantic-sufficiency meaning independently for each canonical identity layer. | C6 / EC-06 |
| BB-05 | Canonical Identity Continuity and Establishment Assessment | Determine whether approved evidence supports existing identity reuse or bounded new identity establishment. | C7 / EC-07 |
| BB-06 | Canonical Identity Decision Determination | Establish the independent canonical-identity decision and preserve justified non-establishment. | C4 / EC-04 |
| BB-07 | Cross-Provider Reconciliation Evidence | Preserve Instrument-owned reconciliation meaning while keeping Provider scopes, evidence, ambiguity, and conflict separate. | C9 / EC-09 |
| BB-08 | Provider Mapping Status Determination | Establish Provider Mapping Status independently from canonical identity and without creating identity through mapping. | C8 / EC-08 |
| BB-09 | Dimension Independence and Coexistence Conformance | Preserve independence, permitted coexistence, terminal meaning, and deferral across the four Instrument dimensions. | C5 / EC-05 |
| BB-10 | Instrument Identity Contract Publication Eligibility | Determine whether approved Instrument Identity Contract publication preconditions are satisfied without creating publication authority. | C10 / EC-10 |
| BB-11 | Canonical Instrument Catalogue Publication Eligibility | Determine whether approved product-neutral catalogue publication preconditions are satisfied while preserving Instrument-only write ownership. | C11 / EC-11 |
| BB-12 | Downstream Boundary Control | Restrict EDD-006 output to eligible Instrument Identity Contract meaning and terminate before EAP-005 factual attribution. | C12 / EC-12 |

### 1.2 Cross-Cutting Building Blocks

| Building Block | Name | Engineering purpose | ES-02 realization |
|---|---|---|---|
| XBB-01 | Evidence and Provenance Integrity | Apply distinct, attributable evidence and provenance obligations to every governed EDD-006 meaning. | C13 / EC-13 |
| XBB-02 | Security Containment and Observability | Apply sensitive-material exclusion and approved non-sensitive observability while preserving Audit authority separation. | C14 / EC-14 |
| XBB-03 | Governed Relationship and Authority Separation | Preserve only approved relationship and lifecycle meaning and prevent creation of downstream authority. | C15 / EC-15 |
| XBB-04 | Engineering Verification and Repository Conformance | Preserve design traceability, lifecycle, metadata, review, and authorization conformance across the Building Block model. | C16 / EC-16 |

The cross-cutting Building Blocks constrain primary Building Blocks without acquiring their semantic responsibilities or changing Provider, Instrument, or Audit ownership.

## 2. Building Block Responsibilities

### 2.1 BB-01 — Admitted Interpretation Input Boundary

BB-01 owns qualification of the sole consumption boundary, preservation of immutable input associations, Provider meaning and identity scopes, exclusion of prohibited sensitive content, and separation of contract rejection from Instrument interpretation.

### 2.2 BB-02 — Interpretation Processing Status Determination

BB-02 owns the exact Interpretation Processing Status cardinality and meaning and prevents receipt, validation, or admission meaning from establishing interpretation progress or any other Instrument dimension.

### 2.3 BB-03 — Interpretation Outcome Determination

BB-03 owns the exact bounded Interpretation Outcome cardinality and meaning, requires completed interpretation meaning where applicable, preserves Provider non-mutation, and prevents Provider ambiguity or vocabulary limitations from automatically becoming Instrument outcomes.

### 2.4 BB-04 — Identity-Layer Semantic Sufficiency Assessment

BB-04 owns separation of Economic Instrument, Listed Instrument, and Derivative Contract sufficiency meaning; positive approved semantic evidence requirements; and exclusion of technical, Provider-native, behavioral, and product-derived substitutes for sufficiency.

### 2.5 BB-05 — Canonical Identity Continuity and Establishment Assessment

BB-05 owns existing-identity reuse assessment, bounded new-identity establishment assessment, Provider-change non-mutation, and canonical and historical continuity evidence.

### 2.6 BB-06 — Canonical Identity Decision Determination

BB-06 owns canonical-identity decision cardinality, establishment preconditions, and attributable non-establishment meaning without creating Provider mapping, product eligibility, or downstream factual meaning.

### 2.7 BB-07 — Cross-Provider Reconciliation Evidence

BB-07 owns Provider-separated reconciliation evidence, provenance preservation, ambiguity and conflict preservation, and prohibition of Provider scope merger, silent Provider preference, identifier globalization, or unsupported equivalence.

### 2.8 BB-08 — Provider Mapping Status Determination

BB-08 owns Provider Mapping Status cardinality and meaning, independence from Canonical Identity Decision, the canonical-target requirement for mapped meaning, and the prohibition on mapping-created identity.

### 2.9 BB-09 — Dimension Independence and Coexistence Conformance

BB-09 owns non-collapse of Interpretation Processing Status, Interpretation Outcome, Canonical Identity Decision, and Provider Mapping Status; permitted coexistence; bounded terminal meaning; and dimension-specific deferral.

### 2.10 BB-10 — Instrument Identity Contract Publication Eligibility

BB-10 owns assessment of every EAP-004 Instrument Identity Contract publication precondition and preservation of approved Instrument-owned contract meaning and exclusions. It creates no publication authority.

### 2.11 BB-11 — Canonical Instrument Catalogue Publication Eligibility

BB-11 owns catalogue-publication eligibility, product-neutral catalogue meaning, separation from Provider and product collections, and preservation of Instrument-only canonical write ownership. It defines no physical catalogue realization.

### 2.12 BB-12 — Downstream Boundary Control

BB-12 owns the sole EDD-006 terminal projection toward EAP-005 and prevents factual attribution, Observation meaning, product decisions, or downstream authority from entering EDD-006.

### 2.13 XBB-01 — Evidence and Provenance Integrity

XBB-01 owns evidence-class separation, attribution, dimension and identity evidence obligations, reconciliation evidence, unresolved-meaning evidence, continuity evidence, and publication evidence where separately authorized.

### 2.14 XBB-02 — Security Containment and Observability

XBB-02 owns sensitive-material exclusion, permitted non-sensitive observability constraints, and preservation of Audit Trail ownership without semantic ownership transfer.

### 2.15 XBB-03 — Governed Relationship and Authority Separation

XBB-03 owns preservation of already-approved Instrument relationship and lifecycle meaning and every EAP-004 downstream non-implication.

### 2.16 XBB-04 — Engineering Verification and Repository Conformance

XBB-04 owns complete ES-01, ES-02, and EAP-004 traceability; Building Block conformance obligations; repository metadata and lifecycle conformance; and review-evidence requirements.

## 3. Building Block Boundaries

| Building Block | Boundary begins | Boundary ends | Explicitly remains outside |
|---|---|---|---|
| BB-01 | At one accepted EAIC-002 Submission Unit | With preserved admitted input meaning suitable for Instrument-owned evaluation | Receipt, contract validation, admission determination, pre-interpretation rejection, Provider acquisition, and Provider mutation |
| BB-02 | With preserved admitted input meaning | With exactly one governed Interpretation Processing Status meaning | Interpretation Outcome, identity decision, mapping status, and lifecycle meaning |
| BB-03 | With preserved admitted meaning and completed processing meaning | With exactly one governed Interpretation Outcome when applicable | Provider disposition, identity decision, mapping status, and product meaning |
| BB-04 | With Provider-owned evidence and applicable approved Instrument context | With semantic-sufficiency meaning for the applicable identity layer | Fields, parsing rules, algorithms, scores, thresholds, and product membership |
| BB-05 | With positive sufficiency, continuity, and distinction evidence | With governed reuse-or-establishment assessment evidence and continuity evidence | Automatic identity mutation from Provider record, symbol, token, snapshot, or reference change |
| BB-06 | With completed interpretation meaning and required identity evidence | With exactly one governed Canonical Identity Decision meaning | Provider mapping, product eligibility, and downstream factual meaning |
| BB-07 | With canonical-identity meaning and Provider-separated identity and provenance evidence | With Instrument-owned reconciliation evidence | Provider partition merger, silent Provider preference, and unsupported equivalence |
| BB-08 | With canonical-target meaning where applicable and reconciliation evidence | With exactly one governed Provider Mapping Status meaning | Canonical identity creation, Provider disposition, and another Provider's mapping |
| BB-09 | With the four independently established dimension meanings | With coexistence, bounded terminal-meaning, and deferral conformance | Combined status, Instrument lifecycle state, or reassessment authority |
| BB-10 | With identity, continuity, mapping, evidence, containment, and authority-separation conformance | With Instrument Identity Contract publication-eligibility meaning | Publication authority, raw Provider meaning, product eligibility, and physical publication |
| BB-11 | With approved canonical catalogue meaning and publication preconditions | With Canonical Instrument Catalogue publication-eligibility meaning | Physical catalogue realization, Provider Catalogue meaning, product universes, and product-specific lists |
| BB-12 | With eligible Instrument Identity Contract meaning and safe provenance | At the EAP-005 factual-attribution boundary | Factual attribution, Observation formation, Validation, and downstream product decisions |
| XBB-01 | At every governed evidence obligation within EDD-006 | With distinct, attributable preservation requirements | Semantic ownership transfer and substitution of one evidence class or time meaning for another |
| XBB-02 | At every EDD-006 evidence, observability, and publication boundary | With containment and permitted observability constraints | Sensitive-material exposure and Audit ownership of Provider or Instrument meaning |
| XBB-03 | At approved Instrument relationship, lifecycle, ownership, and authority constraints | With preserved relationship meaning and downstream non-authority constraints | New relationship types, lifecycle states, transitions, factual meaning, or product authority |
| XBB-04 | At ES-01, ES-02, EAP-004, CAR-006, and repository-governance traceability | With complete ES-03 conformance and review obligations | Engineering approval, architecture amendment, implementation authority, and later-stage design |

Each boundary is independently reviewable and non-overlapping by primary responsibility. Cross-cutting application does not transfer or duplicate the responsibility owned by a primary Building Block.

## 4. Building Block Relationships

Building Block relationships express semantic dependency only. They do not define execution order, calls, orchestration, scheduling, concurrency, persistence, or physical interaction.

| Building Block | Direct engineering dependencies | Relationship meaning |
|---|---|---|
| BB-01 | None within EDD-006 | Begins at the separately governed accepted EAIC-002 boundary. |
| XBB-01 | None | Establishes cross-cutting evidence and provenance obligations. |
| XBB-02 | None | Establishes cross-cutting containment and observability obligations. |
| XBB-03 | None | Establishes cross-cutting relationship and authority-separation obligations. |
| BB-02 | BB-01, XBB-01, XBB-02, XBB-03 | Processing-status meaning requires preserved admitted meaning and governed conformance obligations. |
| BB-03 | BB-01, BB-02, XBB-01, XBB-02, XBB-03 | Outcome meaning requires admitted meaning and completed processing meaning. |
| BB-04 | BB-01, XBB-01, XBB-02, XBB-03 | Sufficiency meaning requires preserved evidence and approved Instrument context. |
| BB-05 | BB-01, BB-04, XBB-01, XBB-02, XBB-03 | Continuity and establishment assessment requires positive semantic sufficiency and preserved evidence. |
| BB-06 | BB-02, BB-03, BB-05, XBB-01, XBB-02, XBB-03 | Canonical identity decision requires processing, outcome, and reuse-or-establishment assessment evidence. |
| BB-07 | BB-01, BB-04, BB-05, BB-06, XBB-01, XBB-02, XBB-03 | Reconciliation requires Provider-separated evidence and approved Instrument identity meaning. |
| BB-08 | BB-06, BB-07, XBB-01, XBB-02, XBB-03 | Mapping status uses canonical identity meaning where applicable and reconciliation evidence. |
| BB-09 | BB-02, BB-03, BB-06, BB-08, XBB-01, XBB-03 | Coexistence conformance assesses the four independent dimensions without collapsing them. |
| BB-10 | BB-05, BB-06, BB-08, BB-09, XBB-01, XBB-02, XBB-03 | Contract eligibility requires identity, coexistence, continuity, applicable mapping, evidence, containment, and authority conformance. |
| BB-11 | BB-05, BB-06, BB-08, BB-09, XBB-01, XBB-02, XBB-03 | Catalogue eligibility requires approved canonical meaning, coexistence, continuity, mapping, evidence, containment, and authority conformance. |
| BB-12 | BB-10, XBB-01, XBB-02, XBB-03 | Terminal projection requires eligible contract meaning and safe provenance. |
| XBB-04 | BB-01 through BB-12, XBB-01 through XBB-03 | Verification consumes traceability from every Building Block and creates no semantic feedback dependency. |

The dependency model is acyclic. XBB-01 through XBB-03 are independent constraints, and XBB-04 is a conformance responsibility rather than a semantic producer.

## 5. Building Block Collaboration

Collaboration means conceptual exchange of established engineering meaning. It does not define an interface, message, payload, method, protocol, transport, or runtime interaction.

| Collaboration | Contributors | Receiving Building Block | Established engineering meaning |
|---|---|---|---|
| BBC-01 | BB-01 | BB-02, BB-03, BB-04, BB-05, BB-07 | Preserved admitted Submission Unit meaning and Provider-owned evidence associations |
| BBC-02 | BB-02 | BB-03, BB-06, BB-09 | Interpretation Processing Status meaning |
| BBC-03 | BB-03 | BB-06, BB-09 | Interpretation Outcome meaning |
| BBC-04 | BB-04 | BB-05, BB-07 | Applicable identity-layer semantic-sufficiency meaning |
| BBC-05 | BB-05 | BB-06, BB-07, BB-10, BB-11 | Reuse-or-establishment assessment evidence and continuity evidence |
| BBC-06 | BB-06 | BB-07, BB-08, BB-09, BB-10, BB-11 | Canonical Identity Decision meaning |
| BBC-07 | BB-07 | BB-08 | Provider-separated reconciliation evidence |
| BBC-08 | BB-08 | BB-09, BB-10, BB-11 | Provider Mapping Status meaning |
| BBC-09 | BB-09 | BB-10, BB-11 | Four-dimension coexistence and bounded terminal-meaning conformance |
| BBC-10 | XBB-01 | BB-01 through BB-12 and XBB-03 | Evidence-class, attribution, provenance, and preservation obligations |
| BBC-11 | XBB-02 | BB-01 through BB-12, XBB-01, and XBB-03 | Sensitive-material containment and permitted observability constraints |
| BBC-12 | XBB-03 | BB-01 through BB-12, XBB-01, and XBB-02 | Relationship, lifecycle, ownership, and downstream-authority constraints |
| BBC-13 | BB-10 | BB-12 | Eligible Instrument Identity Contract meaning and safe provenance obligations |
| BBC-14 | BB-01 through BB-12, XBB-01 through XBB-03 | XBB-04 | Responsibility, boundary, relationship, constraint, and traceability evidence |

No collaboration transfers semantic ownership. Provider meaning remains Provider-owned, Instrument meaning remains Instrument-owned, and Audit remains owner only of the Audit Trail.

## 6. Responsibility Mapping

### 6.1 ES-02-to-ES-03 Allocation

| ES-02 capability | ES-02 component | ES-01 responsibilities | ES-03 Building Block | Direct EAP-004 authority |
|---|---|---|---|---|
| C1 | EC-01 | R1–R6 | BB-01 | Sections 7, 17, and 19 |
| C2 | EC-02 | R7–R8 | BB-02 | Sections 8 and 20 |
| C3 | EC-03 | R9–R11 | BB-03 | Sections 9 and 20 |
| C4 | EC-04 | R12–R14 | BB-06 | Sections 10 and 20 |
| C5 | EC-05 | R15–R17 | BB-09 | Sections 12, 17, and 20 |
| C6 | EC-06 | R18–R20 | BB-04 | Sections 13 and 20 |
| C7 | EC-07 | R21–R24 | BB-05 | Sections 14 and 20 |
| C8 | EC-08 | R25–R26 | BB-08 | Sections 11 and 20 |
| C9 | EC-09 | R27–R28 | BB-07 | Sections 11, 17, and 20 |
| C10 | EC-10 | R29–R30 | BB-10 | Sections 15, 19, and 20 |
| C11 | EC-11 | R31–R33 | BB-11 | Sections 16, 18, and 20 |
| C12 | EC-12 | R34–R35 | BB-12 | Sections 18 and 20 |
| C13 | EC-13 | R36–R41 | XBB-01 | Section 19 |
| C14 | EC-14 | R42–R43 | XBB-02 | Sections 19 and 20 |
| C15 | EC-15 | R44–R45 | XBB-03 | Sections 16, 18, and 20 |
| C16 | EC-16 | R46–R47 | XBB-04 | Sections 20 and 21; CAR-006 Version 1.1; EAS-007; DOC-001 |

### 6.2 Allocation Conformance

1. Capabilities C1 through C16 are realized exactly once.
2. Components EC-01 through EC-16 are realized exactly once.
3. Responsibilities R1 through R47 remain allocated exactly once.
4. Every Building Block is justified by one approved ES-02 capability and conceptual component.
5. No Building Block introduces responsibility outside ES-01 or ES-02.
6. No primary or cross-cutting Building Block transfers Provider, Instrument, Observation, product, or Audit ownership.
7. BB-12 remains the sole EDD-006 terminal Building Block before EAP-005 factual attribution.

## 7. Building Block Constraints

| Building Block | Mandatory constraints |
|---|---|
| BB-01 | Consume only an accepted EAIC-002 Submission Unit; preserve immutable associations and Provider identity scopes; never convert upstream rejection into Instrument outcome meaning. |
| BB-02 | Preserve exact processing-status cardinality; prevent receipt, validation, or admission meaning from establishing progress; imply no other dimension. |
| BB-03 | Preserve exact outcome cardinality; require completed bounded interpretation; alter no Provider meaning and infer no automatic outcome from Provider ambiguity or vocabulary. |
| BB-04 | Keep the three identity layers distinct; require positive approved semantic evidence; exclude product, Provider-native, behavioral, and technical substitutes for sufficiency. |
| BB-05 | Prefer existing identity continuity where established; require positive sufficiency for new identity; never mutate identity automatically from Provider record change. |
| BB-06 | Preserve exact decision cardinality; require every EAP-004 establishment precondition; preserve justified non-establishment without downstream implication. |
| BB-07 | Keep every Provider's evidence and provenance separate; prohibit silent Provider preference, partition merger, identifier globalization, and unsupported equivalence. |
| BB-08 | Preserve exact mapping-status cardinality; keep mapping independent from canonical identity; require a canonical target for mapped meaning; never create identity through mapping. |
| BB-09 | Keep all four dimensions independent; preserve every permitted coexistence and bounded terminal meaning; use only governed dimension-specific deferral. |
| BB-10 | Require every EAP-004 Instrument Identity Contract publication precondition and separate publication authority; exclude prohibited Provider and product meaning. |
| BB-11 | Preserve product-neutral catalogue meaning; keep the catalogue distinct from Provider and product collections; preserve Instrument-only canonical write ownership. |
| BB-12 | Use only eligible Instrument Identity Contract meaning and safe provenance; terminate before factual attribution and Observation meaning; create no downstream decision. |
| XBB-01 | Keep evidence classes and applicable time meanings distinct; preserve attribution and unresolved reasons; transfer no Provider ownership. |
| XBB-02 | Exclude credentials, raw Provider content, and private technical material; permit only approved non-sensitive observability; preserve Audit authority separation. |
| XBB-03 | Preserve only governed relationship and lifecycle meaning; create no new state or transition; create no downstream factual, business, execution, or product authority. |
| XBB-04 | Verify complete ES-01, ES-02, and EAP-004 traceability; preserve repository and lifecycle conformance; create no architecture, approval, implementation, or later-stage authority. |

These constraints survive ES-04, ES-05, and any separately authorized future realization. ES-03 grants no implementation, runtime, persistence, publication, or downstream authority.
