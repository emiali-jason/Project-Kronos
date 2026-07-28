# EDD-007 — Instrument-to-Observation Attribution Eligibility Engineering Design

**Document ID:** EDD-007<br>
**Title:** Instrument-to-Observation Attribution Eligibility Engineering Design<br>
**Version:** 0.2 Draft<br>
**Status:** Draft<br>
**Canonical Status:** Draft<br>
**Classification:** Engineering Design Document<br>
**Owner:** Engineering Architect<br>
**Prepared By:** Engineering Design Team<br>
**Review Authority:** Chief Architect<br>
**Engineering Review Authority:** Chief Systems Engineer<br>
**Repository Location:** `docs/engineering/edd/EDD-007-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY-ENGINEERING-DESIGN.md`<br>
**Workflow Stage:** Draft Preparation<br>
**Engineering Stage:** Engineering Capability Design<br>
**ES-01 Review Status:** Approved<br>
**ES-01 Approved By:** Chief Systems Engineer<br>
**ES-02 Review Status:** Approved<br>
**ES-02 Approved By:** Chief Systems Engineer<br>
**Authorization Decision:** CAR-007 Version 1.0<br>
**Direct Engineering Architecture:** EAP-005 Version 1.1<br>
**Engineering Authority:** ES-01 through ES-05, sequential under CAR-007 Version 1.0<br>
**Architecture Authority:** None<br>
**Implementation Authority:** None<br>
**Runtime Authority:** None<br>
**Repository Status:** Published

---

# ES-01 — Engineering Scope Definition

## 1. Engineering Mission

EDD-007 shall define the implementation-independent Engineering Design responsibility required to translate EAP-005 Version 1.1 into a complete, bounded, and verifiable Observation-owned attribution-eligibility design.

The engineered subsystem begins only with the governed combination of one approved Instrument Identity Contract supplied through the completed EDD-006 boundary and one bounded source-neutral Candidate Factual Information input. It preserves Instrument ownership of canonical identity, preserves the candidate information's source, provenance, temporal, uncertainty, ambiguity, partiality, failure, unavailability, and limitation meaning, and engineers the responsibilities required to determine Attribution Evaluation Readiness, conduct bounded Attribution Evaluation, and establish exactly one governed Attribution Outcome.

The subsystem terminates with either Observation Participation Eligibility meaning or preserved Attribution Ineligibility meaning and its governed reason or reasons. It ends before Candidate Observation construction, Observation Acceptance, Observation ownership, governed Observation establishment, factual correctness determination, and Observation publication.

## 2. Engineering Objectives

EDD-007 ES-01 establishes the engineering boundary required to:

1. translate EAP-005 without changing its architectural meaning;
2. preserve Instrument as the sole semantic owner of canonical Instrument identity and the Instrument Identity Contract;
3. preserve Observation as the sole owner of attribution authority, Attribution Evaluation, Attribution Outcome, and Observation Participation Eligibility;
4. prevent candidate factual information from acquiring Observation ownership merely by entering the EDD-007 boundary;
5. consume the approved Instrument Identity Contract without recreating, reinterpreting, remapping, modifying, or transferring canonical identity;
6. preserve source-neutral Candidate Factual Information and its governed context without creating acquisition, correction, enrichment, normalization, or factual-ownership authority;
7. preserve Attribution Evaluation Readiness as distinct from Attribution Evaluation and Attribution Outcome;
8. preserve exactly one of the two permitted Attribution Outcomes for one bounded evaluation;
9. preserve approved canonical identity association, provenance continuity, attribution continuity, source attribution, temporal attribution, and effective identity context;
10. preserve partiality, failed information, unavailable information, retained uncertainty, Attribution Ambiguity, Retained Factual Ambiguity, identity metadata, and derived interpretation as distinct meanings;
11. define the bounded eligibility, ineligibility, ineligibility-reason, boundary-conformance, boundary-violation, and non-sensitive observability responsibilities authorized by EAP-005; and
12. establish complete traceability and future Engineering Verification obligations while terminating before downstream Observation architecture begins.

## 3. Engineering Scope

### 3.1 Scope Beginning

EDD-007 begins only when both of the following EAP-005-governed inputs are available:

1. one approved product-neutral Instrument Identity Contract supplied through the completed EDD-006 boundary; and
2. one bounded source-neutral Candidate Factual Information input carrying its applicable factual category, source attribution, provenance, temporal context, partiality, failure, unavailability, uncertainty, ambiguity, and limitation context.

EDD-007 does not acquire either input, does not accept Provider-native records or EAIC-002 submission meaning, and does not recreate any upstream identity or admission responsibility.

### 3.2 Design-Layer Separation

| Layer | Governing responsibility |
|---|---|
| Architecture | EAP-005 and its approved governing authorities define semantic ownership, meanings, boundaries, dependencies, contracts, representations, obligations, invariants, and exclusions. EDD-007 does not alter them. |
| Engineering Design | EDD-007 translates the approved EAP-005 meanings into implementation-independent engineering responsibilities, design boundaries, constraints, evidence obligations, and verification traceability. ES-01 defines scope only. |
| Implementation | Outside EDD-007 ES-01 authority. No implementation decision or authority is created. |

### 3.3 Included Engineering Scope

EDD-007 includes Engineering Design responsibility for:

- governed Instrument Identity Contract consumption;
- bounded Candidate Factual Information consumption;
- Attribution Evaluation Readiness and not-ready meaning;
- bounded Attribution Evaluation meaning;
- exactly one Attribution Outcome;
- Attribution Eligible and Attribution Ineligible meaning;
- attribution-ineligibility reasons;
- approved canonical identity association;
- candidate factual information association;
- provenance continuity and attribution continuity;
- source attribution and temporal attribution;
- partial, failed, and unavailable information distinctions;
- retained uncertainty and unresolved ambiguity;
- Attribution Ambiguity and Retained Factual Ambiguity separation;
- identity-metadata, factual-information, and derived-interpretation separation;
- applicable effective identity-context preservation;
- Observation Participation Eligibility and Ineligibility;
- boundary conformance and boundary violations;
- ownership and authority separation;
- non-sensitive observability; and
- Engineering Verification traceability.

### 3.4 Scope Ending

EDD-007 ends when one bounded Attribution Evaluation has established exactly one of:

1. `ATTRIBUTION_ELIGIBLE`, permitting only an Observation Participation Eligibility meaning to cross the downstream boundary; or
2. `ATTRIBUTION_INELIGIBLE`, preserving the exact governed non-sensitive reason or reasons and producing no Observation Participation Eligibility.

EDD-007 produces no Candidate Observation, Observation Acceptance, Observation ownership, governed Observation, factual correctness determination, Market Fact authority, publication authority, Validation meaning, or fitness-for-use judgment. EAP-006 remains the downstream Engineering Architecture and is not performed or designed by EDD-007 ES-01.

## 4. Engineering Responsibilities

EDD-007 owns the following Engineering Design responsibilities within the EAP-005 boundary:

1. Consume one approved Instrument Identity Contract only through the completed EDD-006 boundary.
2. Preserve the consumed contract's product-neutral canonical identity meaning, identity layer, approved classification and relationships, applicable effective or historical context, and approved provenance association.
3. Prevent consumption from recreating, reinterpreting, remapping, modifying, reopening, or transferring ownership of canonical Instrument identity.
4. Consume one bounded source-neutral Candidate Factual Information input without creating acquisition or communication authority.
5. Preserve the candidate input's factual assertion, factual category, source attribution, provenance, temporal context, partiality, failure, unavailability, uncertainty, ambiguity, and limitations as applicable.
6. Preserve that entry into the subsystem assigns no new semantic owner to candidate factual information and does not create authoritative factual state.
7. Exclude Provider Catalogue content, Provider Snapshots, Provider Records, Provider-native identifiers, Provider dispositions, Submission Units, EAIC-002 envelopes, raw Provider payloads, and sensitive values from the governed input boundary.
8. Represent Attribution Evaluation Readiness independently from Attribution Evaluation and Attribution Outcome.
9. Establish readiness only from the presence of the governed identity input, candidate factual input, required ownership context, required evaluation context, boundary conformance, and the ability to evaluate each attribution precondition.
10. Preserve that positive establishment of provenance continuity, source attribution, temporal attribution, or effective identity context is evaluated during Attribution Evaluation and is not itself a readiness prerequisite.
11. Limit Attribution Evaluation Not Ready to the exact absence conditions authorized by EAP-005 and prevent it from replacing Attribution Ineligible.
12. Represent bounded Observation-owned Attribution Evaluation without introducing mechanics, algorithms, orchestration, or operational behavior.
13. Establish exactly one Attribution Outcome for one bounded evaluation.
14. Preserve `ATTRIBUTION_ELIGIBLE` and `ATTRIBUTION_INELIGIBLE` as the only mutually exclusive Attribution Outcomes.
15. Preserve attributable, non-sensitive evidence for readiness, evaluation meaning, and the established Attribution Outcome.
16. Associate candidate factual information with exactly one approved canonical Instrument identity when that association is established.
17. Preserve canonical identity association without creating, altering, repairing, inferring, or transferring identity meaning.
18. Preserve candidate factual information association as distinct from canonical identity association.
19. Prevent Instrument identity metadata from becoming factual market information or authoritative factual state.
20. Prevent candidate factual information from creating, redefining, classifying, or otherwise altering Instrument identity.
21. Preserve factual source and origin meaning through provenance continuity across the bounded evaluation.
22. Preserve an explainable identity-to-candidate-information association through attribution continuity without defining mapping mechanics.
23. Preserve source attribution without defining factual acquisition or Provider communication.
24. Preserve approved temporal attribution without defining timestamp formats or temporal mechanics.
25. Preserve applicable approved effective identity context without defining Instrument Lifecycle processing or transitions.
26. Preserve partial Provider information as distinguishable from complete, failed, unavailable, missing, ambiguous, or zero-valued information.
27. Preserve failed Provider information as distinguishable from partial, unavailable, missing, ambiguous, or zero-valued information.
28. Preserve unavailable Provider information as distinguishable from partial, failed, missing, ambiguous, or zero-valued information.
29. Preserve that missing information does not mean zero and does not prove factual market state.
30. Preserve identity metadata as distinct from candidate factual information.
31. Preserve derived interpretation as distinct from candidate factual information.
32. Preserve retained uncertainty explicitly without converting uncertainty into certainty.
33. Preserve Attribution Ambiguity as an ineligibility condition and preserve Retained Factual Ambiguity as explicit unresolved factual ambiguity that may coexist with Attribution Eligible when one approved canonical identity association remains established.
34. Establish Attribution Eligible only when one approved canonical identity association exists, no unresolved Attribution Ambiguity exists, and every required provenance, source, temporal, and effective-context precondition is established.
35. Preserve that Attribution Eligible establishes neither factual correctness, Observation Acceptance, Observation ownership, Observation publication, Validation success, product membership, Product Eligibility, nor fitness for use.
36. Establish Attribution Ineligible whenever one or more governed attribution preconditions cannot be established, including unresolved Attribution Ambiguity, conflicting identity association, or inability to establish one approved canonical identity association.
37. Preserve the exact non-sensitive Attribution Ineligibility reason or reasons without reinterpretation, concealment, silent selection, repair, or unsupported inference.
38. Produce Observation Participation Eligibility meaning only for an Attribution Eligible outcome and only through the approved downstream boundary.
39. Produce no Observation Participation Eligibility for an Attribution Ineligible outcome.
40. Represent boundary conformance and prohibited bypass, ownership violation, unsupported inference, or prohibited information crossing as distinct governed meanings.
41. Preserve Instrument ownership of canonical identity, Observation ownership of attribution authority, and applicable source-domain ownership of source assertions, provenance, and attribution.
42. Prevent engineering representation, evidence, eligibility, or boundary crossing from transferring semantic ownership or authority.
43. Preserve Provider partiality, failure, and unavailability without converting Provider condition into Instrument Lifecycle or Market availability meaning.
44. Exclude credentials, authorization material, private technical state, raw Provider content, and unapproved sensitive information from inputs, evidence, reasons, observability, and boundary meaning.
45. Provide only the non-sensitive observability meaning permitted by EAP-005 while excluding implementation details and downstream Observation meaning.
46. Prevent downstream interpretation, product context, or semantic feedback from altering canonical identity association, attribution ownership, factual meaning, or the established Attribution Outcome.
47. Maintain complete backward traceability from every EDD-007 responsibility to EAP-005 and its governed architectural basis.
48. Preserve all EAP-005 contract meanings, required engineering representations, obligations, invariants, and downstream restrictions for realization and verification in later authorized Engineering Stages.
49. Establish future Engineering Verification obligations covering scope completeness, ownership and boundary integrity, outcome cardinality, semantic separation, evidence preservation, neutrality, and prohibited-content absence.
50. Preserve repository, lifecycle, metadata, review, approval, publication, and authorization conformance without converting Draft Engineering Design into architecture, implementation authority, or operational authority.

## 5. Explicit Exclusions

EDD-007 ES-01 does not define, authorize, or perform:

1. architecture amendment, reinterpretation, extension, replacement, or Architecture Discovery;
2. factual-data acquisition, Provider communication, Provider authentication, or Provider-to-Observation communication;
3. Provider Catalogue consumption, Provider Snapshot consumption, Provider Record consumption, Provider-native identifier consumption, EAIC-002 consumption, or any bypass of the approved Instrument Identity Contract boundary;
4. canonical identity creation, resolution, repair, reinterpretation, remapping, classification, relationship establishment, lifecycle transition, or mapping-effective-time processing;
5. matching, attribution, correction, enrichment, normalization, ranking, scoring, fuzzy logic, automated resolution, algorithms, or thresholds;
6. factual correctness determination or conversion of candidate factual information into authoritative factual state;
7. Candidate Observation construction, Observation Acceptance, Observation ownership, governed Observation establishment, Observation publication, or Observation lifecycle;
8. Market Schedule, Validation, Risk, execution, Portfolio, Event, Audit, product-universe, Product Eligibility, strategy, or business-judgment meaning;
9. market-data structures, quote models, candle or OHLC models, depth models, Open Interest structures, or timestamp formats;
10. APIs, fields, schemas, payloads, serialization, protocols, transports, or physical communication;
11. persistence, caching, databases, scheduling, retries, orchestration, infrastructure, deployment, or technology selection;
12. implementation design, modules, services, classes, packages, production code, test code, or operational activation;
13. approval, canonicalization, Version 1.0 publication, implementation authority, or operational authority for EDD-007; or
14. ES-02 capability decomposition or any later Engineering Stage.

## 6. Engineering Assumptions

EDD-007 ES-01 relies only on the following governed assumptions and preconditions:

1. CAR-007 Version 1.0 remains the approved authority for sequential EDD-007 ES-01 through ES-05 Engineering Design subject to its stage gates.
2. EAP-005 Version 1.1 remains the sole direct, approved, canonical, and active Engineering Architecture baseline for EDD-007.
3. EDD-006 Version 1.0 remains the completed upstream Engineering Design and supplies only the approved Instrument Identity Contract boundary governed by EAP-005.
4. The approved Instrument Domain, Observation Domain, Provider Domain, ADP-001D, and EAP-005 ownership model remains unchanged.
5. The upstream boundary supplies one approved Instrument Identity Contract with its governed identity meaning and safe provenance associations intact.
6. The Candidate Factual Information input is source-neutral and carries only the bounded context permitted by EAP-005; its availability creates no acquisition, factual-ownership, or correctness authority.
7. Applicable approved source, provenance, temporal, uncertainty, ambiguity, partiality, failure, unavailability, limitation, and effective identity context may be consumed only where already established by approved authority.
8. EAP-006 Version 1.1 remains the downstream Engineering Architecture and begins only after the EDD-007 terminal boundary.
9. Any attribution precondition that cannot be established remains explicit and results in the governed ineligibility meaning rather than being completed by Engineering assumption.
10. Any matter not decided by EAP-005 remains unresolved and cannot be decided through Engineering convenience.

## 7. Engineering Constraints

EDD-007 ES-01 is constrained as follows:

1. EAP-005 meanings, ownership, boundaries, dependencies, contracts, representations, obligations, invariants, exclusions, and downstream restrictions are normative.
2. Instrument remains the sole semantic owner of canonical Instrument identity and the Instrument Identity Contract.
3. Observation remains the sole semantic owner of attribution authority, Attribution Evaluation, Attribution Outcome, and Observation Participation Eligibility.
4. Candidate factual information acquires no new semantic owner merely by entering the EDD-007 boundary.
5. Engineering representation, evidence, eligibility, and boundary crossing transfer no semantic ownership or authority.
6. The EAP-004 and EDD-006 Instrument Identity Contract is consumed without reinterpretation.
7. Provider Catalogue content, Provider Snapshots, Provider Records, Provider-native identifiers, Provider dispositions, Submission Units, EAIC-002 envelopes, raw Provider payloads, and sensitive values are prohibited inputs.
8. Attribution Evaluation Readiness remains distinct from Attribution Evaluation and Attribution Outcome.
9. Readiness does not require positive establishment of the attribution preconditions evaluated during Attribution Evaluation.
10. Attribution Evaluation Not Ready remains limited to the absence conditions defined by EAP-005 and never replaces Attribution Ineligible.
11. Exactly one Attribution Outcome exists for one bounded evaluation.
12. Attribution Eligible and Attribution Ineligible remain the only Attribution Outcomes and remain mutually exclusive.
13. Approved canonical Instrument identity association is required for Attribution Eligible.
14. Attribution Ambiguity requires Attribution Ineligible.
15. Retained Factual Ambiguity may coexist with Attribution Eligible only when one approved canonical identity association and all other required preconditions remain established; the ambiguity remains explicit and unresolved.
16. Provenance continuity, attribution continuity, source attribution, temporal attribution, and applicable effective identity context remain preserved where required.
17. Partial, failed, unavailable, missing, ambiguous, and zero-valued information remain semantically distinct.
18. Identity metadata, candidate factual information, and derived interpretation remain semantically distinct.
19. Provider unavailability establishes neither Instrument Lifecycle nor Market availability.
20. Attribution Eligible establishes no factual correctness, Observation Acceptance, Observation ownership, publication, Validation, product, strategy, or fitness-for-use meaning.
21. Attribution Ineligible produces no Observation Participation Eligibility.
22. Only Observation Participation Eligibility meaning may cross the downstream boundary; governed ineligibility and its reasons terminate within EDD-007.
23. EDD-007 terminates before Candidate Observation construction, Observation Acceptance, governed Observation establishment, factual correctness determination, and Observation publication.
24. Product membership and product-universe context cannot establish canonical identity association or Attribution Eligibility.
25. Product-specific Observation requirements cannot alter Instrument identity, Observation attribution ownership, candidate factual meaning, or the EDD-007 boundary.
26. Provider neutrality and implementation neutrality are mandatory.
27. Non-sensitive observability may explain governed meanings only and cannot expose prohibited content or downstream Observation meaning.
28. No architecture, implementation, operational, communication, persistence, deployment, or publication authority is created.
29. ES-01 defines Engineering Scope only; capability, Building Block, Interface, and Verification design remain subject to later sequential CAR-007 gates.
30. Any required change to EAP-005 ownership, dependency, boundary, or meaning requires prior architecture governance and cannot be made within EDD-007.

## 8. Traceability to Governing Architecture

| EDD-007 ES-01 scope element | Direct EAP-005 authority | Preserved engineering meaning |
|---|---|---|
| Engineering Mission and terminal boundary | Sections 1, 2, 7, 8, 9, and 14 | Bounded attribution eligibility begins with governed identity and candidate factual inputs and terminates before Observation Acceptance. |
| Objectives 1–4 | Sections 3, 5, 6, and 12 | Architecture remains authoritative; Instrument and Observation ownership remain separate; candidate information gains no premature owner. |
| Objectives 5–7 | Sections 8 and 10.1–10.5 | Inputs are consumed through approved boundaries; readiness, evaluation, and outcome remain distinct. |
| Objectives 8–10 | Sections 10.5–10.17, 11, and 12 | Outcome cardinality, association, continuity, attribution, uncertainty, ambiguity, and semantic separation are preserved. |
| Objectives 11–12 | Sections 10.18–10.19 and 13–18 | Eligibility, boundary control, observability, downstream restrictions, and verification are bounded and traceable. |
| Responsibilities 1–7 | Sections 6, 8, 10.1–10.2, 12, and 14 | Approved upstream inputs, ownership, source-neutrality, and prohibited bypasses are preserved. |
| Responsibilities 8–15 | Sections 10.3–10.5, 11, and 12 | Readiness, bounded evaluation, exactly one outcome, and evidence remain distinct and complete. |
| Responsibilities 16–20 | Sections 10.9, 10.16, and 12 | Canonical identity association and candidate factual association remain separate without identity alteration. |
| Responsibilities 21–25 | Sections 10.10–10.13, 10.17, and 12 | Provenance, attribution, source, temporal, and effective-context continuity are preserved. |
| Responsibilities 26–33 | Sections 10.14–10.16, 11, and 12 | Provider conditions, missingness, uncertainty, ambiguity, identity metadata, and interpretation remain distinct. |
| Responsibilities 34–39 | Sections 9, 10.5–10.8, 10.18, 12, and 14 | Eligibility and ineligibility have bounded conditions, consequences, reasons, and downstream meaning. |
| Responsibilities 40–46 | Sections 6, 10.19, and 12–16 | Boundary, ownership, authority, security, observability, and downstream separation remain intact. |
| Responsibilities 47–50 | Sections 16–18 and 21; CAR-007 Sections 5, 8, and 10 | Traceability, invariant preservation, future verification, and sequential governance remain mandatory. |
| Explicit Exclusions | Sections 3–5 and 14–15; CAR-007 Section 9 | No architecture, acquisition, identity engineering, Observation Acceptance, implementation, or operational authority is introduced. |
| Assumptions and Constraints | Sections 3–9, 12, 14, 16, and 19 | Approved authority, unresolved meaning, neutrality, ownership, outcome cardinality, and terminal boundaries remain normative. |

This traceability does not make EAP-005 supporting dependencies additional direct Engineering Architecture authorities for EDD-007. EAP-005 Version 1.1 remains the sole direct Engineering Architecture authority.

## 9. Governing Repository Authorities

| Authority | EDD-007 ES-01 application |
|---|---|
| CAR-007 Version 1.0 | Authorizes sequential EDD-007 ES-01 through ES-05 Engineering Design and establishes the stage gates, authority limits, and explicit prohibitions. |
| EAP-005 Version 1.1 | Sole direct Engineering Architecture authority and normative source for the EDD-007 scope, ownership, boundary, meanings, obligations, invariants, and exclusions. |
| EDD-006 Version 1.0 | Completed upstream Engineering Design and source of the approved Instrument Identity Contract boundary only; used as a document template without content reuse. |
| EAP-006 Version 1.1 | Downstream Engineering Architecture that begins after the EDD-007 terminal boundary and grants EDD-007 no downstream responsibility. |
| ADP-001D Version 1.0 | Governs the Instrument-to-Observation attribution boundary translated by EAP-005. |
| Instrument Domain Architecture | Preserves Instrument ownership of canonical identity and the approved Instrument Identity Contract dependency. |
| Observation Domain Architecture | Preserves Observation ownership of attribution authority and later authoritative Market Facts while keeping Observation Acceptance outside EDD-007. |
| Provider Domain Architecture | Preserves Provider-owned source, assertion, provenance, and condition meaning and prohibits direct Provider-to-Observation bypass. |
| ADR-009 Version 1.0 and EAIC-002 Version 0.1 | Preserve the upstream Provider-to-Instrument boundary and prevent EAIC-002 meaning from entering EDD-007 as Observation input. |
| Domain Ownership Matrix, Domain Dependency Matrix, ENGINE_OWNERSHIP, and DATA_FLOW | Preserve approved semantic ownership and dependency direction. |
| MIG-001 Version 0.1 | Preserves the governed migration alignment on which EAP-005 Version 1.1 depends. |
| EAS-007 Version 1.0 | Governs EDD lifecycle, metadata, ownership, traceability, review, approval, and authority separation. |
| DOC-001 Version 1.1 | Governs controlled document identity, classification, metadata, repository location, lifecycle state, and Document Register consistency. |

Only EAP-005 Version 1.1 directly defines the Engineering Architecture translated by EDD-007. All other authorities constrain governance, ownership, boundaries, dependencies, and traceability without expanding the ES-01 scope.

---

# ES-02 — Engineering Capability Design

ES-02 decomposes the approved and frozen ES-01 scope into cohesive engineering capabilities and conceptual engineering components. It allocates responsibility only. It does not define Building Blocks, interfaces, modules, physical realization, operational sequencing, or technology.

Every ES-02 capability remains subordinate to EAP-005 Version 1.1 and preserves the complete ES-01 boundary. No capability creates new architecture, ownership, authority, or engineering scope.

## 1. Engineering Capability Decomposition

The EDD-007 capability model contains exactly 16 capabilities:

| Capability | Name | Engineering purpose | ES-01 responsibilities |
|---|---|---|---|
| C1 | Governed Attribution Input Stewardship | Preserve the two governed upstream inputs and their ownership, context, source-neutrality, and prohibited-content boundaries. | R1–R7 |
| C2 | Attribution Evaluation Readiness | Establish readiness or not-ready meaning without evaluating positive attribution preconditions or establishing an Attribution Outcome. | R8–R11 |
| C3 | Bounded Attribution Evaluation and Outcome | Preserve bounded Observation-owned evaluation, exactly-one-outcome cardinality, the two permitted outcome meanings, and attributable outcome evidence. | R12–R15 |
| C4 | Canonical Identity Association | Preserve association with one approved canonical Instrument identity without creating, altering, or transferring identity meaning. | R16–R17 |
| C5 | Candidate Factual Association and Semantic Separation | Preserve candidate factual association and keep identity, factual information, and derived interpretation separate. | R18–R20, R30–R31 |
| C6 | Provenance and Attribution Continuity | Preserve factual source and origin meaning and explainable identity-to-factual-information association. | R21–R22 |
| C7 | Source, Temporal, and Effective Identity Context | Preserve source attribution, approved temporal attribution, and applicable effective identity context without introducing acquisition or lifecycle mechanics. | R23–R25 |
| C8 | Provider Condition Distinction | Preserve partial, failed, unavailable, missing, ambiguous, and zero-valued distinctions without converting Provider condition into lifecycle or Market meaning. | R26–R29, R43 |
| C9 | Uncertainty and Ambiguity Preservation | Preserve uncertainty, Attribution Ambiguity, and Retained Factual Ambiguity with their distinct eligibility consequences. | R32–R33 |
| C10 | Attribution Eligibility Determination | Preserve the complete conditions and explicit non-implications of Attribution Eligible. | R34–R35 |
| C11 | Attribution Ineligibility and Reason Preservation | Preserve the complete conditions of Attribution Ineligible and its exact governed non-sensitive reason or reasons. | R36–R37 |
| C12 | Observation Participation Boundary | Permit Observation Participation Eligibility only for Attribution Eligible and terminate ineligible meaning without downstream eligibility. | R38–R39 |
| C13 | Boundary, Ownership, and Authority Conformance | Preserve boundary conformance, domain ownership, authority separation, and protection from downstream semantic feedback. | R40–R42, R46 |
| C14 | Security Containment and Observability | Exclude prohibited sensitive material and preserve only the non-sensitive observability authorized by EAP-005. | R44–R45 |
| C15 | Architecture Traceability and Meaning Preservation | Maintain backward traceability and preserve every EAP-005 contract, representation, obligation, invariant, and downstream restriction for later realization. | R47–R48 |
| C16 | Engineering Verification and Repository Conformance | Establish verification obligations and preserve lifecycle, metadata, review, publication, and authority conformance. | R49–R50 |

The decomposition is exhaustive and exclusive: all 50 approved ES-01 responsibilities are allocated exactly once, no capability is orphaned, and no capability extends the frozen scope.

## 2. Engineering Components

Each capability is represented by one conceptual engineering component at ES-02. A component is a bounded responsibility allocation only. It is not a Building Block, module, service, class, package, interface, process, or deployable unit and does not predetermine ES-03.

| Component | Capability | Consumed engineering meaning | Established engineering meaning |
|---|---|---|---|
| EC-01 | C1 | Approved Instrument Identity Contract; bounded source-neutral Candidate Factual Information; applicable governed context | Preserved and boundary-conformant attribution-input meaning |
| EC-02 | C2 | Preserved input, ownership, evaluation-context, and boundary-conformance meaning | Attribution Evaluation Ready or Attribution Evaluation Not Ready meaning |
| EC-03 | C3 | Ready bounded evaluation context and governed outcome constraints | Bounded Attribution Evaluation meaning and exactly one permitted Attribution Outcome |
| EC-04 | C4 | Approved canonical Instrument identity and candidate factual association context | Canonical identity association or non-establishment meaning without identity mutation |
| EC-05 | C5 | Candidate factual association, identity metadata, and applicable derived-interpretation context | Preserved semantic separation among identity, facts, and interpretation |
| EC-06 | C6 | Source, origin, identity-association, and provenance context | Preserved provenance continuity and attribution continuity meaning |
| EC-07 | C7 | Source, temporal, and approved effective identity context | Preserved source, temporal, and effective-context attribution meaning |
| EC-08 | C8 | Candidate information condition and Provider-owned condition meaning | Preserved distinctions for partiality, failure, unavailability, missingness, ambiguity, and zero-valued information |
| EC-09 | C9 | Retained uncertainty, Attribution Ambiguity, and Retained Factual Ambiguity context | Explicit uncertainty and ambiguity meaning with governed eligibility consequences |
| EC-10 | C10 | Bounded evaluation meaning and all governed attribution-precondition meanings | Attribution Eligible meaning with all non-implications preserved |
| EC-11 | C11 | Bounded evaluation meaning and absent, conflicting, ambiguous, or unestablished precondition meaning | Attribution Ineligible meaning and exact governed non-sensitive reason or reasons |
| EC-12 | C12 | Attribution Eligible or Attribution Ineligible meaning | Observation Participation Eligibility or terminal ineligibility meaning |
| EC-13 | C13 | Boundary, ownership, authority, and downstream-separation constraints | Boundary conformance or violation meaning with ownership and authority preserved |
| EC-14 | C14 | Sensitive-content exclusions and permitted observability meaning | Security containment and non-sensitive observability constraints |
| EC-15 | C15 | ES-01 allocation and EAP-005 architectural traceability | Preserved architecture-to-capability traceability and mandatory meaning set |
| EC-16 | C16 | Capability model, traceability, verification obligations, and repository governance | Engineering review and repository-conformance obligations |

All 16 components are owned as EDD-007 Engineering Design responsibilities. Semantic ownership remains governed by EAP-005: Instrument retains canonical identity ownership, Observation retains attribution authority, and applicable source domains retain their source-owned assertions and provenance.

## 3. Component Responsibilities

### 3.1 EC-01 — Governed Attribution Input Stewardship

EC-01 owns consumption of the approved Instrument Identity Contract and bounded Candidate Factual Information, preservation of their permitted context and ownership, prevention of premature factual ownership, and exclusion of prohibited upstream or sensitive content.

### 3.2 EC-02 — Attribution Evaluation Readiness

EC-02 owns the exact readiness and not-ready meanings, readiness preconditions, readiness non-implications, and the prohibition on using not-ready meaning as a substitute for Attribution Ineligible.

### 3.3 EC-03 — Bounded Attribution Evaluation and Outcome

EC-03 owns bounded Observation-controlled evaluation meaning, exactly-one-outcome cardinality, the mutual exclusivity of the two permitted outcomes, and attributable non-sensitive evaluation and outcome evidence.

### 3.4 EC-04 — Canonical Identity Association

EC-04 owns association of candidate factual information with one approved canonical Instrument identity and prevents association from creating, altering, repairing, inferring, reopening, or transferring identity meaning.

### 3.5 EC-05 — Candidate Factual Association and Semantic Separation

EC-05 owns candidate factual association and the separation of canonical identity association, identity metadata, candidate factual information, authoritative factual state, and derived interpretation.

### 3.6 EC-06 — Provenance and Attribution Continuity

EC-06 owns factual source-and-origin continuity and explainable identity-to-candidate-information continuity without acquiring source ownership or defining mapping mechanics.

### 3.7 EC-07 — Source, Temporal, and Effective Identity Context

EC-07 owns preservation of source attribution, approved temporal attribution, and applicable effective identity context without defining acquisition, timestamp, lifecycle, or transition mechanics.

### 3.8 EC-08 — Provider Condition Distinction

EC-08 owns the independent preservation of partial, failed, unavailable, missing, ambiguous, and zero-valued information and prevents Provider condition from becoming Instrument Lifecycle or Market availability meaning.

### 3.9 EC-09 — Uncertainty and Ambiguity Preservation

EC-09 owns explicit retained uncertainty, Attribution Ambiguity as an ineligibility condition, and Retained Factual Ambiguity as unresolved factual meaning that may coexist with eligibility only under the approved EAP-005 conditions.

### 3.10 EC-10 — Attribution Eligibility Determination

EC-10 owns the complete governed conditions for Attribution Eligible and preserves every prohibited implication, including factual correctness, Observation Acceptance, ownership, publication, Validation, product, and fitness-for-use meaning.

### 3.11 EC-11 — Attribution Ineligibility and Reason Preservation

EC-11 owns the complete governed conditions for Attribution Ineligible and preservation of the exact non-sensitive reason or reasons without concealment, silent selection, repair, or unsupported inference.

### 3.12 EC-12 — Observation Participation Boundary

EC-12 owns the sole downstream eligibility meaning for Attribution Eligible and ensures that Attribution Ineligible terminates without producing Observation Participation Eligibility.

### 3.13 EC-13 — Boundary, Ownership, and Authority Conformance

EC-13 owns boundary-conformance and violation meaning, Instrument and Observation ownership separation, source-authority preservation, non-transfer of semantic authority, and protection against downstream semantic feedback.

### 3.14 EC-14 — Security Containment and Observability

EC-14 owns exclusion of credentials, authorization material, private technical state, raw Provider content, and unapproved sensitive information and limits observability to the non-sensitive meaning permitted by EAP-005.

### 3.15 EC-15 — Architecture Traceability and Meaning Preservation

EC-15 owns complete backward traceability and preservation of the EAP-005 contracts, representations, obligations, invariants, and downstream restrictions that constrain later Engineering Stages.

### 3.16 EC-16 — Engineering Verification and Repository Conformance

EC-16 owns future Engineering Verification obligations and repository lifecycle, metadata, review, approval, publication, and authorization conformance.

## 4. Capability Boundaries

| Capability | Begins with | Ends with | Explicitly outside |
|---|---|---|---|
| C1 | The two inputs permitted by ES-01 | Preserved, source-neutral, ownership-safe input meaning | Readiness assessment, attribution evaluation, and acquisition |
| C2 | Preserved input and required context availability | Ready or not-ready meaning | Positive attribution-precondition evaluation and outcome determination |
| C3 | A bounded evaluation context permitted by readiness | Bounded evaluation meaning and exactly one permitted outcome | Criteria ownership assigned to C4–C11 and downstream eligibility |
| C4 | Approved identity and candidate-association context | Established or unestablished canonical identity association meaning | Identity creation, resolution, mapping, or lifecycle mechanics |
| C5 | Identity, candidate factual, and interpretation context | Preserved factual association and semantic separation | Factual correctness and derived interpretation |
| C6 | Source, origin, provenance, and identity-association context | Provenance and attribution continuity meaning | Acquisition, mapping mechanics, and source ownership |
| C7 | Source, temporal, and effective identity context | Preserved attribution context | Timestamp formats, acquisition, and lifecycle processing |
| C8 | Candidate-information and Provider-condition context | Explicit condition distinctions | Correction, normalization, or Market and lifecycle conclusions |
| C9 | Uncertainty and the two governed ambiguity meanings | Explicit preserved uncertainty and ambiguity consequences | Ambiguity resolution and identity selection |
| C10 | The bounded evaluation and all required established preconditions | Attribution Eligible meaning and its non-implications | Observation Acceptance, factual correctness, and publication |
| C11 | The bounded evaluation and any unestablished or conflicting precondition | Attribution Ineligible meaning and preserved reason or reasons | Repair, remediation, retry, or downstream eligibility |
| C12 | One governed Attribution Outcome | Observation Participation Eligibility or terminal ineligibility | Candidate Observation construction and Observation Acceptance |
| C13 | EAP-005 boundary, ownership, and authority rules | Conformance or violation meaning with authority preserved | Remediation and transfer of ownership or authority |
| C14 | Prohibited-content and observability rules | Contained evidence and permitted non-sensitive observability | Sensitive disclosure and implementation telemetry design |
| C15 | Frozen ES-01 and EAP-005 meaning | Complete architecture-to-capability traceability | Architecture amendment and new engineering scope |
| C16 | The complete capability model and governance obligations | Reviewable verification and repository-conformance obligations | Implementation tests and approval decisions not yet granted |

Capability boundaries are mutually exclusive. C13 and C14 apply as cross-cutting constraints but do not acquire the primary responsibilities of C1–C12. C15 and C16 assess and preserve the model without redesigning it.

## 5. Capability Dependencies

### 5.1 Dependency Model

Dependencies identify required engineering meaning only. They do not define execution order, calls, interfaces, orchestration, control flow, scheduling, or operational behavior.

| Capability | Required engineering dependencies | Dependency meaning |
|---|---|---|
| C1 | EDD-006 Instrument Identity Contract boundary; EAP-005 Candidate Factual Information boundary | Establishes the only permitted input basis. |
| C2 | C1 | Readiness is meaningful only for governed, preserved inputs and required context. |
| C3 | C2 | Bounded evaluation and outcome meaning require an evaluation context permitted by readiness. |
| C4 | C1, C3 | Canonical identity association is evaluated within the bounded attribution meaning and only from the approved identity input. |
| C5 | C1, C3 | Candidate association and semantic separation apply within the bounded evaluation without changing input meaning. |
| C6 | C1, C3 | Provenance and attribution continuity preserve the input meanings across the bounded evaluation. |
| C7 | C1, C3 | Source, temporal, and effective identity context are evaluated without extending either input boundary. |
| C8 | C1, C3 | Provider-condition distinctions preserve the candidate input condition within the bounded evaluation. |
| C9 | C1, C3 | Uncertainty and ambiguity meanings remain explicit within the bounded evaluation. |
| C10 | C3–C9 | Eligibility depends on the bounded outcome model and establishment of every governed attribution precondition. |
| C11 | C3–C9 | Ineligibility depends on the bounded outcome model and any governed precondition that remains absent, conflicting, ambiguous, or unestablished. |
| C12 | C10, C11 | The terminal boundary depends on the established eligible or ineligible meaning. |
| C13 | EAP-005 ownership and boundary rules | Cross-cutting constraint on C1–C12; it does not create dependency cycles or take over their meanings. |
| C14 | EAP-005 security and observability rules | Cross-cutting constraint on C1–C13; it does not create dependency cycles or take over their meanings. |
| C15 | C1–C14; frozen ES-01; EAP-005 | Traceability preserves the architectural origin of every allocated capability. |
| C16 | C1–C15; CAR-007; EAS-007; DOC-001 | Verification and repository conformance assess the complete design without redesign. |

### 5.2 Dependency Rules

The dependency model shall preserve:

1. one-way dependency from the approved upstream identity boundary into EDD-007;
2. no dependency from EDD-007 back into Instrument identity establishment;
3. no direct Provider or EAIC-002 dependency;
4. no downstream Observation dependency except the terminal Observation Participation Eligibility meaning;
5. readiness as a prerequisite context rather than an Attribution Outcome;
6. evaluation concerns as independent contributors to eligibility or ineligibility;
7. outcome cardinality without collapsing eligibility and ineligibility responsibilities;
8. cross-cutting ownership and security constraints without semantic cycles;
9. traceability and verification as assessment dependencies rather than primary attribution responsibilities; and
10. an acyclic conceptual dependency model.

## 6. Responsibility Allocation

### 6.1 One-to-One Allocation Matrix

| Capability | Allocated ES-01 responsibilities | Allocation count |
|---|---|---:|
| C1 | R1, R2, R3, R4, R5, R6, R7 | 7 |
| C2 | R8, R9, R10, R11 | 4 |
| C3 | R12, R13, R14, R15 | 4 |
| C4 | R16, R17 | 2 |
| C5 | R18, R19, R20, R30, R31 | 5 |
| C6 | R21, R22 | 2 |
| C7 | R23, R24, R25 | 3 |
| C8 | R26, R27, R28, R29, R43 | 5 |
| C9 | R32, R33 | 2 |
| C10 | R34, R35 | 2 |
| C11 | R36, R37 | 2 |
| C12 | R38, R39 | 2 |
| C13 | R40, R41, R42, R46 | 4 |
| C14 | R44, R45 | 2 |
| C15 | R47, R48 | 2 |
| C16 | R49, R50 | 2 |
| **Total** | **R1–R50, each exactly once** | **50** |

### 6.2 Allocation Conformance

The allocation is conformant because:

- every ES-01 responsibility R1–R50 appears in exactly one capability;
- no capability is unallocated;
- no responsibility is split, duplicated, merged away, or reworded as new scope;
- capability purposes summarize allocated responsibilities without replacing their normative ES-01 wording;
- cross-cutting application of C13 and C14 does not reallocate the primary responsibilities owned by other capabilities; and
- later Engineering Stages shall trace to this allocation without changing it.

## 7. Capability Constraints

The following constraints apply to the complete capability model:

1. Every capability shall remain implementation-independent and provider-neutral.
2. EAP-005 Version 1.1 remains the sole direct Engineering Architecture authority.
3. The frozen ES-01 mission, scope, responsibilities, exclusions, assumptions, constraints, and terminal boundary remain unchanged.
4. Instrument retains exclusive ownership of canonical Instrument identity.
5. Observation retains exclusive ownership of attribution authority, Attribution Evaluation, Attribution Outcome, and Observation Participation Eligibility.
6. Candidate factual information gains no new semantic owner through any capability.
7. No capability may consume Provider-native records, EAIC-002 meaning, raw Provider payloads, or prohibited sensitive information.
8. No capability may create, alter, repair, infer, reopen, remap, or transfer canonical identity.
9. Readiness, bounded evaluation, Attribution Outcome, eligibility, and ineligibility remain distinct capabilities and meanings.
10. Exactly one of the two permitted Attribution Outcomes shall remain established for one bounded evaluation.
11. Attribution Ambiguity requires Attribution Ineligible; Retained Factual Ambiguity remains explicit under its governed conditions.
12. Provenance, attribution, source, temporal, uncertainty, ambiguity, partiality, failure, unavailability, and effective identity context remain preserved where required.
13. Identity metadata, candidate factual information, and derived interpretation remain distinct.
14. Eligibility establishes no factual correctness, Observation Acceptance, ownership, publication, Validation, product, strategy, or fitness-for-use meaning.
15. Ineligibility produces no Observation Participation Eligibility.
16. EDD-007 terminates before Candidate Observation construction, Observation Acceptance, governed Observation establishment, and Observation publication.
17. No capability may introduce Building Blocks, interfaces, modules, algorithms, data structures, persistence, deployment, or operational behavior.
18. No capability may introduce architecture, implementation authority, operational authority, or publication authority.
19. Cross-cutting capabilities may constrain but shall not absorb or duplicate primary capability responsibilities.
20. Any dependency that would reverse domain direction, create a semantic cycle, or extend the EAP-005 boundary is prohibited.

## 8. Engineering Traceability

| Capability | Frozen ES-01 source | Direct EAP-005 source | Verification obligation carried forward |
|---|---|---|---|
| C1 | R1–R7 | Sections 6, 8, 10.1–10.2, 12, and 14 | Verify only approved inputs enter and ownership and source-neutrality remain intact. |
| C2 | R8–R11 | Sections 10.3, 11, 12, and 16 | Verify readiness remains distinct, bounded, and does not replace ineligibility. |
| C3 | R12–R15 | Sections 10.4–10.5, 11, 12, and 16 | Verify bounded evaluation, exactly-one-outcome cardinality, and permitted outcomes. |
| C4 | R16–R17 | Sections 10.9, 12, and 16 | Verify one approved identity association without identity alteration or ownership transfer. |
| C5 | R18–R20, R30–R31 | Sections 10.2, 10.16, 12, and 16 | Verify factual association and semantic separation without factual-state or identity creation. |
| C6 | R21–R22 | Sections 10.10–10.11, 12, and 16 | Verify provenance and attribution continuity remain explainable and preserved. |
| C7 | R23–R25 | Sections 10.12–10.13, 10.17, 12, and 16 | Verify source, temporal, and effective-context meaning without mechanics. |
| C8 | R26–R29, R43 | Sections 10.15, 11, 12, and 16 | Verify Provider conditions and missingness remain distinct and create no lifecycle or Market meaning. |
| C9 | R32–R33 | Sections 10.14, 12, and 16 | Verify uncertainty and both ambiguity meanings remain explicit and correctly separated. |
| C10 | R34–R35 | Sections 9, 10.6, 12, 14, and 16 | Verify every eligibility precondition and every eligibility non-implication. |
| C11 | R36–R37 | Sections 10.7–10.8, 12, and 16 | Verify ineligibility conditions and exact non-sensitive reasons remain visible. |
| C12 | R38–R39 | Sections 9, 10.18, 14, and 16 | Verify the sole downstream eligibility meaning and terminal ineligibility boundary. |
| C13 | R40–R42, R46 | Sections 6, 10.19, 12, 14, and 16 | Verify boundary, ownership, authority, and downstream separation. |
| C14 | R44–R45 | Sections 12–13 and 16 | Verify sensitive-content exclusion and bounded non-sensitive observability. |
| C15 | R47–R48 | Sections 15–18 | Verify complete architecture traceability and preservation of mandatory EAP-005 meaning. |
| C16 | R49–R50 | Sections 17–18 and 21; CAR-007 Sections 5, 8, and 10 | Verify scope completeness, repository conformance, sequential governance, and authority limits. |

This traceability is complete at ES-02. It creates no forward authority for Building Blocks, interfaces, implementation, or operational behavior. ES-03 remains prohibited until ES-02 completes the CAR-007 review, approval, publication, and freeze gate.
