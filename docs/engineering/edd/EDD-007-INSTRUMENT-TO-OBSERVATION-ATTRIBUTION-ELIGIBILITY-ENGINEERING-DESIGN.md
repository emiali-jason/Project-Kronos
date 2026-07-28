# EDD-007 — Instrument-to-Observation Attribution Eligibility Engineering Design

**Document ID:** EDD-007<br>
**Title:** Instrument-to-Observation Attribution Eligibility Engineering Design<br>
**Version:** 0.1 Draft<br>
**Status:** Draft<br>
**Canonical Status:** Draft<br>
**Classification:** Engineering Design Document<br>
**Owner:** Engineering Architect<br>
**Prepared By:** Engineering Design Team<br>
**Review Authority:** Chief Architect<br>
**Engineering Review Authority:** Chief Systems Engineer<br>
**Repository Location:** `docs/engineering/edd/EDD-007-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY-ENGINEERING-DESIGN.md`<br>
**Workflow Stage:** Draft Preparation<br>
**Engineering Stage:** Engineering Scope Definition<br>
**ES-01 Review Status:** Approved<br>
**ES-01 Approved By:** Chief Systems Engineer<br>
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
