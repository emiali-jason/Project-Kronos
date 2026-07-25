# EAP-005 — Instrument-to-Observation Attribution Eligibility Engineering Architecture

**Document ID:** EAP-005
**Title:** Instrument-to-Observation Attribution Eligibility Engineering Architecture
**Version:** 1.0

**Status:** Approved

**Canonical Status:** Approved Canonical Engineering Architecture

**Classification:** Engineering Architecture Package

**Owner:** Engineering Architect

**Prepared By:** Engineering Architect

**Review Authority:** Chief Architect
**Repository Location:** `docs/engineering/eap/EAP-005-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY.md`

**Approved By:** Chief Architect

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Governing ADP:** ADP-001D Version 1.0

**Supporting ADPs:** ADP-001A, ADP-001B, ADP-001C, ADP-001E, ADP-001H, ADP-001I, ADP-001J

**Upstream EAP:** EAP-004 Version 1.0

**ADR Required:** No

**Engineering Impact:** None

**Runtime Impact:** None

**EDD Authorization:** None

**Implementation Authorization:** None

**Commit Authorization:** None

**Push Authorization:** None

**Next Authorized Capability:** None

## 1. Purpose

EAP-005 translates the approved ADP-001D Instrument-to-Observation Contract into provider-neutral and implementation-neutral engineering contracts, representations and obligations for evaluating whether candidate factual information is eligible for governed attribution and later Observation participation.

EAP-005 begins with an EAP-004 Instrument Identity Contract and source-neutral candidate factual information. It preserves provenance continuity, source attribution, temporal attribution, uncertainty, ambiguity, partiality, failed-information distinction, unavailable-information distinction and effective identity context. It terminates before Candidate Observation construction, Observation Acceptance, Observation ownership and Observation publication.

## 2. Scope

EAP-005 defines engineering architecture for:

- Attribution Evaluation Readiness;
- Attribution Evaluation Activity;
- Attribution Outcome;
- Attribution Eligible and Attribution Ineligible;
- attribution-ineligibility reasons;
- approved canonical identity association;
- candidate factual information association;
- source attribution;
- temporal attribution;
- provenance continuity;
- attribution continuity;
- partiality, failed-information and unavailable-information distinctions;
- identity-metadata and derived-interpretation distinctions;
- retained uncertainty and unresolved ambiguity;
- effective identity-context preservation;
- Observation Participation Eligibility and Ineligibility;
- boundary conformance and violations;
- non-sensitive observability; and
- engineering verification.

## 3. Engineering Governance

This Draft is the engineering translation authorized by the Chief Architect for ADP-001D. It introduces no new domain, semantic owner, dependency, runtime behavior, communication authority or implementation decision.

Canonical repository architecture remains authoritative. EAP-005 shall be interpreted consistently with ADP-001D, ADP-001E, ADP-001J, EAP-004 and all listed approved dependencies. Unresolved matters remain unresolved or become explicit attribution-ineligibility reasons; Engineering shall not invent their meaning.

## 4. Explicit Out of Scope

EAP-005 shall not define or authorize:

- factual-data acquisition;
- Provider communication or Provider-to-Observation runtime communication;
- APIs, schemas, fields, payloads, serialization or transport;
- market-data structures, quote models, candle or OHLC models, depth models or Open Interest structures;
- timestamp formats;
- matching or attribution algorithms;
- identity resolution;
- mapping establishment or mapping-effective-time processing;
- lifecycle transitions;
- factual correction, enrichment or normalization;
- Candidate Observation construction;
- Observation Acceptance, ownership, publication or lifecycle;
- Market Schedule;
- Validation, Risk, Execution, Portfolio, Event or Audit meaning;
- persistence, caching, scheduling, retries or runtime orchestration;
- EDD, implementation, code or EAP-006.

EAP-005 shall not reinterpret Instrument identity, make candidate facts Observation-owned merely by entry, resolve uncertainty or ambiguity, or represent this boundary as executable behavior.

## 5. Canonical Dependencies

The following documents are mandatory dependencies for this Draft:

- Platform Constitution;
- ADP-001A — Swing Phase 1 Market Data Inventory;
- ADP-001B — Instrument Identity Architecture;
- ADP-001C — Provider → Instrument Contract;
- ADP-001D — Instrument → Observation Contract;
- ADP-001E — Observation Domain Architecture;
- ADP-001H — Provider Instrument Master Acquisition Capability and Contract;
- ADP-001I — Approved Instrument Universe and Reference Semantics Architecture;
- ADP-001J Version 1.0 — Instrument Interpretation and Canonical Identity Establishment Architecture;
- EAP-001 Version 1.0;
- EAP-002 Version 1.0;
- EAP-003 Version 1.0;
- EAP-004 Version 1.0;
- Instrument Domain Architecture;
- Observation Domain Architecture;
- Provider Domain Architecture;
- Domain Ownership Matrix;
- DOMAIN_DEPENDENCY_MATRIX.md;
- ENGINE_OWNERSHIP;
- DATA_FLOW;
- Document Register; and
- approved architecture and engineering indexes.

## 6. Semantic and Domain Ownership

| Meaning | Semantic owner |
| --- | --- |
| Canonical Instrument Identity | Instrument |
| Instrument Identity Contract | Instrument |
| Candidate factual information | Has not yet acquired Observation ownership or governed Observation meaning; entry transfers no ownership and creates no authoritative factual state |
| Factual source provenance | Applicable source-domain ownership of source attribution, provenance and source-owned assertions |
| Attribution Authority | Observation |
| Attribution Evaluation | Observation |
| Attribution Outcome | Observation |
| Observation Participation Eligibility | Observation |
| Observation Acceptance | Observation, outside EAP-005 |
| Governed Observation | Observation, outside EAP-005 |

ADP-001D assigns Instrument ownership of identity and Observation ownership of factual attribution and Market Facts. Candidate factual information has no new semantic owner before Observation Acceptance. EAP-005 does not assign a new semantic owner to candidate factual information, introduces no third or premature factual owner and transfers no ownership through engineering representation.

## 7. Engineering Boundary

```text
EAP-004 Instrument Identity Contract
                  +
Candidate Factual Information Contract
                  ↓
          Attribution Evaluation Readiness
                  ↓
              Attribution Evaluation
                  ↓
             Attribution Outcome
          ┌──────────────┴──────────────┐
          ↓                             ↓
 Attribution Eligible          Attribution Ineligible
          ↓                             ↓
 Observation Participation      Attribution Ineligibility
 Eligibility Contract           Reason Preserved
          ↓                             ↓
 EAP-005 terminates             No Observation Participation
                                Eligibility Contract
                                      ↓
                                EAP-005 terminates
```

This is a semantic engineering boundary only. It shall not be represented as a runtime sequence, executable workflow, service orchestration, physical communication or state machine.

## 8. Upstream Boundaries

### 8.1 Instrument Identity Input

The immediate canonical identity dependency is the EAP-004 Version 1.0 Instrument Identity Contract. EAP-005 may consume canonical Instrument identity meaning, identity layer, approved classification and relationships, approved universe context, applicable historical or effective context and approved provenance association. EAP-005 shall not recreate, reinterpret or remap Instrument identity.

### 8.2 Candidate Factual Information Input

The Candidate Factual Information Input Contract is source-neutral and may preserve candidate factual assertion, factual category, source attribution, provenance, temporal context, partiality, failed-information distinction, unavailable-information distinction, uncertainty, ambiguity and limitations. It grants no acquisition or runtime communication authority.

## 9. Downstream Boundary

The downstream output is the Observation Participation Eligibility Contract. It represents only that candidate factual information is attributable to an approved canonical Instrument identity, satisfies governed ADP-001D attribution preconditions and may participate in later Observation architecture.

It shall not establish Candidate Observation construction, Observation Acceptance, Observation ownership, factual correctness, Market Fact authority, publication, Validation or fitness for use. EAP-005 terminates before Observation Acceptance architecture begins.

## 10. Engineering Contracts

The following are semantic engineering contracts only. They shall not become APIs, schemas, payloads, fields, serialized objects, runtime interfaces or persistence structures.

### 10.1 Instrument Identity Input Contract

Consumes the EAP-004 Instrument Identity Contract without recreating, reinterpreting or transferring canonical Instrument identity ownership.

### 10.2 Candidate Factual Information Input Contract

Represents source-neutral candidate factual information and its bounded source, provenance, temporal, uncertainty, ambiguity and limitation context.

### 10.3 Attribution Evaluation Readiness Contract

Represents whether the EAP-005 engineering preconditions for Attribution Evaluation may begin. Readiness requires only the governed EAP-004 Instrument Identity Contract input, the bounded Candidate Factual Information input, applicable ownership context, applicable evaluation context, boundary conformance and the ability to evaluate whether each required attribution precondition is established or not established. Positive establishment of provenance continuity, source attribution, temporal attribution or effective identity context is not a readiness prerequisite; their presence or absence is evaluated during Attribution Evaluation. Attribution Evaluation Not Ready is limited to absent upstream identity contract, absent candidate factual input, absent required ownership context, absent required evaluation context or absent boundary conformance and shall not replace Attribution Ineligible.

### 10.4 Attribution Evaluation Activity Contract

Represents bounded Observation-owned Attribution Evaluation without defining mechanics, algorithms, orchestration or runtime behavior.

### 10.5 Attribution Outcome Contract

Represents exactly one Attribution Outcome for one bounded evaluation: Attribution Eligible or Attribution Ineligible.

### 10.6 Attribution Eligibility Contract

Represents satisfaction of the ADP-001D attribution preconditions only when one approved canonical identity association exists, no unresolved Attribution Ambiguity exists and the required provenance, source, temporal and effective-context preconditions are established. It does not establish factual correctness, Observation Acceptance, ownership or publication.

### 10.7 Attribution Ineligibility Contract

Represents failure to establish one or more required attribution preconditions, including unresolved Attribution Ambiguity, conflicting identity association or inability to establish one approved canonical identity association. It produces no Observation Participation Eligibility.

### 10.8 Attribution Ineligibility Reason Contract

Preserves the exact non-sensitive reason or reasons for ineligibility, including Attribution Ambiguity, without reinterpretation or concealment.

### 10.9 Canonical Identity Association Contract

Associates candidate factual information with an approved canonical Instrument identity without creating, modifying or transferring identity ownership.

### 10.10 Provenance Continuity Contract

Preserves factual source and origin meaning across the bounded evaluation.

### 10.11 Attribution Continuity Contract

Preserves explainable identity-to-factual-information association without defining mapping mechanics.

### 10.12 Source Attribution Contract

Preserves the factual information's source association without defining acquisition or Provider communication.

### 10.13 Temporal Attribution Contract

Preserves approved temporal meaning without defining timestamp formats or temporal implementation mechanics.

### 10.14 Uncertainty and Ambiguity Preservation Contract

Preserves Attribution Ambiguity and Retained Factual Ambiguity distinctly. Attribution Ambiguity concerns which approved canonical Instrument identity the candidate factual information concerns and requires Attribution Ineligible. Retained Factual Ambiguity is ambiguity within candidate factual information or its limitations that does not prevent one approved canonical identity association; it may coexist with Attribution Eligible and shall remain explicit without silent resolution.

### 10.15 Provider-Condition Distinction Contract

Keeps partial, failed and unavailable Provider information distinguishable. Attribution Ambiguity remains distinct from Retained Factual Ambiguity. Provider unavailability shall not become Instrument Lifecycle or Market availability.

### 10.16 Semantic Separation Contract

Keeps identity metadata, factual information and derived interpretation distinct.

### 10.17 Effective Identity Context Contract

Preserves applicable approved identity or lifecycle context without defining Lifecycle processing. Where required context cannot be established, attribution remains ineligible.

### 10.18 Observation Participation Eligibility Contract

Represents only eligibility for later Observation participation. It does not create an Observation, confer Observation ownership or authorize acceptance or publication.

### 10.19 Boundary Violation Contract

Represents prohibited bypasses, ownership violations, unsupported inference or information crossing the EAP-005 boundary. It does not authorize remediation or reinterpretation.

## 11. Engineering Representations

The following representations preserve one-to-one engineering meaning. They are not implementation states or runtime state-machine instructions.

**Required Engineering Representations: 28 present.**

| Engineering representation | Meaning |
| --- | --- |
| `ATTRIBUTION_EVALUATION_READY` | EAP-005 preconditions permit Attribution Evaluation to be represented. |
| `ATTRIBUTION_EVALUATION_NOT_READY` | The upstream identity contract, candidate factual input, required ownership context, required evaluation context or boundary conformance is absent; it shall not replace `ATTRIBUTION_INELIGIBLE`. |
| `ATTRIBUTION_EVALUATION_NOT_STARTED` | Attribution Evaluation has not been represented as begun. |
| `ATTRIBUTION_EVALUATION_ACTIVE` | Attribution Evaluation is represented as active within the bounded contract. |
| `ATTRIBUTION_ELIGIBLE` | The bounded attribution evaluation satisfies the governed preconditions. |
| `ATTRIBUTION_INELIGIBLE` | One or more governed attribution preconditions are not established. |
| `CANONICAL_IDENTITY_ASSOCIATED` | Candidate factual information is associated with an approved canonical Instrument identity. |
| `CANONICAL_IDENTITY_NOT_ESTABLISHED` | The required approved canonical identity association for attribution is not established; it does not create, modify, reinterpret or reopen EAP-004 identity establishment. |
| `FACTUAL_INFORMATION_ASSOCIATED` | Candidate factual information is associated within the bounded evaluation. |
| `PROVENANCE_CONTINUITY_PRESERVED` | Factual source and origin meaning remain associated. |
| `PROVENANCE_CONTINUITY_NOT_ESTABLISHED` | Required provenance continuity is not established. |
| `SOURCE_ATTRIBUTION_PRESERVED` | Source attribution remains associated. |
| `SOURCE_ATTRIBUTION_NOT_ESTABLISHED` | Required source attribution is not established. |
| `TEMPORAL_ATTRIBUTION_PRESERVED` | Approved temporal meaning remains associated. |
| `TEMPORAL_ATTRIBUTION_NOT_ESTABLISHED` | Required temporal attribution is not established. |
| `PARTIALITY_DISTINGUISHED` | Partial information remains explicitly distinguishable. |
| `FAILED_INFORMATION_DISTINGUISHED` | Failed information remains explicitly distinguishable. |
| `UNAVAILABLE_INFORMATION_DISTINGUISHED` | Unavailable information remains explicitly distinguishable. |
| `UNCERTAINTY_PRESERVED` | Retained uncertainty remains explicit. |
| `AMBIGUITY_PRESERVED` | Retained Factual Ambiguity remains explicit and unresolved; Attribution Ambiguity remains an ineligibility condition. |
| `IDENTITY_METADATA_DISTINGUISHED` | Identity metadata remains distinct from factual information. |
| `DERIVED_INTERPRETATION_DISTINGUISHED` | Derived interpretation remains distinct from factual information. |
| `EFFECTIVE_IDENTITY_CONTEXT_PRESERVED` | Applicable effective identity context remains associated. |
| `EFFECTIVE_IDENTITY_CONTEXT_NOT_ESTABLISHED` | Required effective identity context is not established. |
| `OBSERVATION_PARTICIPATION_ELIGIBLE` | Candidate factual information is eligible for later Observation participation. |
| `OBSERVATION_PARTICIPATION_INELIGIBLE` | Candidate factual information is not eligible for later Observation participation. |
| `BOUNDARY_CONFORMANT` | The engineering contract conforms to the EAP-005 boundary. |
| `BOUNDARY_VIOLATION` | A prohibited condition, ownership violation, bypass or unsupported inference is represented. |

No executable state machine is authorized.

## 12. Engineering Obligations

Engineering shall demonstrate that:

1. Instrument retains identity ownership.
2. Observation owns attribution authority.
3. Candidate factual information does not become Observation-owned merely by entering EAP-005 and receives no new semantic owner before Observation Acceptance.
4. Identity does not become factual state.
5. Factual information does not create or redefine identity.
6. EAP-004 identity meaning is consumed without reinterpretation.
7. Attribution Evaluation Readiness remains distinct from Attribution Outcome and does not require positive attribution preconditions.
8. Exactly one Attribution Outcome exists per bounded evaluation.
9. Attribution Eligible and Attribution Ineligible remain mutually exclusive, and Attribution Evaluation Not Ready does not replace Attribution Ineligible.
10. Attribution Eligible does not imply factual correctness.
11. Attribution Eligible does not imply Observation Acceptance.
12. Attribution Eligible does not confer Observation ownership.
13. Attribution Eligible does not authorize publication.
14. Approved canonical identity association is required.
15. Provenance continuity is preserved.
16. Attribution continuity is preserved.
17. Source attribution is preserved.
18. Temporal attribution is preserved.
19. Partial Provider information remains distinguishable.
20. Failed Provider information remains distinguishable.
21. Unavailable Provider information remains distinguishable.
22. Identity metadata remains distinct from factual information.
23. Derived interpretation remains distinct from factual information.
24. Uncertainty remains explicit.
25. Attribution Ambiguity requires Attribution Ineligible, while Retained Factual Ambiguity may coexist with Attribution Eligible and remains explicit and unresolved.
26. Attribution failure remains visible.
27. Missing information does not mean zero.
28. Provider unavailability does not become Instrument lifecycle or Market availability.
29. Applicable effective identity context is preserved where required.
30. Mapping mechanics remain excluded.
31. Lifecycle transition mechanics remain excluded.
32. Observation Acceptance remains excluded.
33. Sensitive information and raw Provider payloads remain excluded.
34. Provider neutrality and implementation neutrality are preserved.
35. EAP-005 terminates before Observation Acceptance architecture begins.

## 13. Engineering Observability

Observability shall expose only non-sensitive meaning sufficient to explain Attribution Evaluation Readiness, exactly one Attribution Outcome, canonical identity association, provenance continuity, source attribution, temporal attribution, partiality, failure, unavailability, Attribution Ambiguity, Retained Factual Ambiguity, uncertainty, effective identity context, Observation Participation Eligibility and boundary conformance or violation.

Observability shall not expose raw Provider payloads, sensitive values, implementation details, transport details, APIs, schemas, persistence details or downstream Observation meaning.

## 14. Downstream Restrictions

Only the Observation Participation Eligibility Contract may cross the EAP-005 boundary as an eligibility meaning for later Observation architecture. It shall not be interpreted as an Observation, Observation Acceptance, Observation ownership, factual correctness, Market Fact authority or publication authority.

EAP-005 shall define no Candidate Observation construction, Observation Acceptance, Observation lifecycle or downstream Validation, Risk, Execution, Portfolio, Event or Audit behavior. No Provider runtime communication is authorized.

## 15. Mandatory Engineering Question Set

The following questions are reproduced exactly and answered one-to-one.

### 1. What engineering contract represents Attribution Evaluation Readiness?

The Attribution Evaluation Readiness Contract represents whether the governed EAP-004 Instrument Identity Contract input, bounded candidate factual input, applicable ownership and evaluation context, boundary conformance and ability to evaluate each attribution precondition permit Attribution Evaluation to be represented. Positive provenance, source, temporal or effective-context establishment is evaluated during Attribution Evaluation, not required for readiness. It is not an Attribution Outcome.

### 2. How is Attribution Evaluation Readiness kept distinct from Architectural Admissibility and Attribution Outcome?

Architectural Admissibility is an upstream approved architectural condition. Attribution Evaluation Readiness is the subsequent engineering readiness meaning, while Attribution Outcome is the single result of the bounded evaluation. None implies factual correctness, Observation Acceptance or ownership.

### 3. What information may enter the EAP-005 boundary?

Only an EAP-004 Instrument Identity Contract and a Candidate Factual Information Input Contract with their approved identity, source, provenance, temporal, uncertainty, ambiguity, limitation and effective-context associations may enter.

### 4. What information is prohibited from entering the EAP-005 boundary?

Raw Provider payloads, sensitive values, acquisition or transport details, APIs, schemas, implementation objects, mapping mechanics, lifecycle mechanics and information that introduces Observation Acceptance, Validation, Risk, Execution, Portfolio, Event or Audit meaning are prohibited.

### 5. What engineering contract represents the approved canonical Instrument identity input?

The Instrument Identity Input Contract represents the EAP-004 Instrument Identity Contract and its approved canonical identity meaning, identity layer, relationships, universe context, effective context and provenance association.

### 6. How is Instrument identity consumed without reinterpretation or ownership transfer?

EAP-005 consumes only the approved semantic meaning published by EAP-004. It does not recreate, reinterpret, remap, modify or transfer Instrument identity ownership.

### 7. What engineering contract represents Candidate Factual Information?

The Candidate Factual Information Input Contract represents source-neutral candidate factual information and its factual category, source, provenance, temporal context, partiality, failure, unavailability, uncertainty, ambiguity and limitations.

### 8. Who owns candidate factual information before Observation Acceptance?

Candidate factual information has not yet acquired Observation ownership or governed Observation meaning. Its source attribution, provenance and any source-owned assertions remain owned by their applicable source domain. Entry into EAP-005 transfers no ownership, creates no authoritative factual state and assigns no new semantic owner before Observation Acceptance. Observation owns Attribution Authority and later governed factual Observation meaning under ADP-001D and ADP-001E.

### 9. What engineering contract represents Attribution Evaluation Activity?

The Attribution Evaluation Activity Contract represents bounded Observation-owned Attribution Evaluation without defining mechanics, algorithms, orchestration or runtime behavior.

### 10. What exact preconditions permit Attribution Evaluation?

An approved EAP-004 Instrument Identity Contract and Candidate Factual Information Input Contract must be present, together with applicable ownership context, evaluation context, boundary conformance and the ability to evaluate whether each required attribution precondition is established or not established. Provenance continuity, source attribution, temporal attribution and effective identity context are evaluated during Attribution Evaluation and are not positive readiness prerequisites. No boundary violation may prevent evaluation.

### 11. What engineering contract represents Attribution Outcome?

The Attribution Outcome Contract represents exactly one Attribution Outcome for one bounded evaluation.

### 12. What Attribution Outcomes are permitted?

Only Attribution Eligible and Attribution Ineligible are permitted.

### 13. What engineering conditions establish Attribution Eligible?

Attribution Eligible may be represented only when one approved canonical identity association exists, no unresolved Attribution Ambiguity exists, required provenance, source, temporal and effective-context preconditions are established, retained factual uncertainty or Retained Factual Ambiguity is preserved where applicable, and no boundary violation exists.

### 14. What engineering conditions establish Attribution Ineligible?

Attribution Ineligible is represented when unresolved Attribution Ambiguity, conflicting identity association, inability to establish one approved canonical identity association, failure to establish provenance, source, temporal or effective-context meaning, unresolved prohibited conditions or a boundary violation prevents eligibility.

### 15. How are attribution-ineligibility reasons preserved?

The Attribution Ineligibility Reason Contract preserves the exact non-sensitive reason or reasons, including Attribution Ambiguity, without reinterpretation, concealment or conversion into Attribution Eligible.

### 16. What constitutes an approved canonical identity association?

An approved canonical identity association is the association supplied by the EAP-004 Instrument Identity Contract. EAP-005 does not create, resolve, map or modify that identity.

### 17. How is provenance continuity preserved?

The Provenance Continuity Contract keeps factual source and origin meaning associated throughout the bounded evaluation without exposing sensitive values or transferring ownership.

### 18. How is attribution continuity preserved?

The Attribution Continuity Contract preserves an explainable association between the approved canonical identity and candidate factual information without defining mapping mechanics.

### 19. How is source attribution preserved?

The Source Attribution Contract preserves the factual information's source association without defining acquisition or Provider communication.

### 20. How is temporal attribution preserved?

The Temporal Attribution Contract preserves approved temporal meaning and effective context without defining timestamp formats or implementation mechanics.

### 21. How are partial Provider information, failed Provider information and unavailable Provider information kept distinct?

The Provider-Condition Distinction Contract represents partial, failed and unavailable information separately. None is converted into zero, factual correctness, Instrument lifecycle or Market availability. Attribution Ambiguity remains distinct from Retained Factual Ambiguity.

### 22. How is identity metadata kept distinct from candidate factual information?

The Semantic Separation Contract represents identity metadata separately from candidate factual information and does not allow either meaning to redefine the other.

### 23. How is derived interpretation kept distinct from candidate factual information?

Derived interpretation remains a distinct representation from candidate factual information. EAP-005 does not turn derived interpretation into factual state or canonical identity.

### 24. How are retained uncertainty and unresolved ambiguity preserved?

The Uncertainty and Ambiguity Preservation Contract keeps Attribution Ambiguity distinct from Retained Factual Ambiguity. Attribution Ambiguity requires Attribution Ineligible; Retained Factual Ambiguity may coexist with Attribution Eligible when one approved canonical identity association and all other preconditions are established. Neither may be silently resolved by engineering convenience.

### 25. How is applicable effective identity context preserved without defining Lifecycle mechanics?

The Effective Identity Context Contract preserves applicable approved context where supplied by canonical architecture. It defines no lifecycle transition, expiry, successor, rollover or persistence mechanics. If required context is not established, attribution remains ineligible.

### 26. What does Attribution Eligible permit?

Attribution Eligible permits only the Observation Participation Eligibility Contract to represent eligibility for later Observation participation.

### 27. What does Attribution Eligible never establish?

Attribution Eligible never establishes factual correctness, Observation Acceptance, Observation ownership, Market Fact authority, publication, Validation success, fitness for use or any downstream business meaning.

### 28. What engineering contract may cross the downstream boundary?

Only the Observation Participation Eligibility Contract may cross as an eligibility meaning for later Observation architecture. It is not an Observation or an acceptance contract.

### 29. Where does EAP-005 terminate?

EAP-005 terminates after the Attribution Outcome. Attribution Eligible may produce the Observation Participation Eligibility Contract. Attribution Ineligible preserves its Attribution Ineligibility Reason and produces no Observation Participation Eligibility Contract. No downstream ineligibility contract is created, implied, authorized or required. EAP-005 terminates before Candidate Observation construction, Observation Acceptance, ownership and publication.

### 30. What matters require further architecture rather than Engineering discretion?

Factual-data acquisition, Provider communication, APIs, schemas, payloads, timestamp formats, mapping, lifecycle transitions, factual correction, enrichment, normalization, Candidate Observation construction, Observation Acceptance, publication, persistence, runtime orchestration, EDD scope, implementation and any ownership or dependency change require further approved architecture.

## 16. Mandatory Engineering Invariant Set

1. **Canonical Instrument Identity shall remain owned exclusively by Instrument.**

2. **Attribution Authority shall remain owned exclusively by Observation.**

3. **Engineering representation shall not transfer semantic ownership.**

4. **Candidate factual information shall not become Observation-owned merely by entering EAP-005.**

5. **Instrument Identity shall not become factual market state.**

6. **Factual market information shall not create or redefine Instrument Identity.**

7. **The EAP-004 Instrument Identity Contract shall be consumed without reinterpretation.**

8. **Attribution Evaluation Readiness shall remain distinct from Attribution Outcome.**

9. **Exactly one Attribution Outcome shall exist for one bounded attribution evaluation.**

10. **Attribution Eligible and Attribution Ineligible shall be the only Attribution Outcomes.**

11. **Attribution Eligible shall not imply factual correctness.**

12. **Attribution Eligible shall not imply Observation Acceptance.**

13. **Attribution Eligible shall not confer Observation ownership.**

14. **Attribution Eligible shall not authorize Observation publication.**

15. **Attribution Eligible shall not imply Validation success or fitness for use.**

16. **Approved canonical Instrument identity association shall be required for Attribution Eligible.**

17. **Provenance continuity shall remain preserved.**

18. **Attribution continuity shall remain preserved.**

19. **Source attribution shall remain preserved.**

20. **Temporal attribution shall remain preserved where required.**

21. **Partial Provider information shall remain distinguishable.**

22. **Failed Provider information shall remain distinguishable.**

23. **Unavailable Provider information shall remain distinguishable.**

24. **Identity metadata shall remain distinct from factual market information.**

25. **Derived interpretation shall remain distinct from factual market information.**

26. **Retained uncertainty shall remain explicit.**

27. **Unresolved ambiguity shall remain explicit and unresolved.**

28. **Attribution failure shall not be silently represented as Attribution Eligible.**

29. **Missing information shall not mean zero or prove market state.**

30. **Provider unavailability shall not establish Instrument Lifecycle or Market availability.**

31. **Provider Mapping mechanics shall remain outside EAP-005.**

32. **Instrument Lifecycle transition mechanics shall remain outside EAP-005.**

33. **Raw Provider payloads and sensitive values shall not enter EAP-005 governed contracts.**

34. **No Observation Acceptance, Market, Validation, Risk, Execution, Portfolio, Event or Audit meaning shall be created by EAP-005.**

35. **EAP-005 shall remain provider-neutral and implementation-neutral and shall not authorize Provider communication, an EDD, implementation or code.**

## 17. Engineering Verification Obligations

Engineering shall verify:

- Instrument and Observation ownership remain separate;
- attribution does not create or alter identity;
- candidate factual information does not become an Observation merely by crossing the boundary;
- EAP-004 identity is consumed without reinterpretation;
- exactly two Attribution Outcomes exist;
- attribution eligibility is not factual correctness, Observation Acceptance or ownership;
- provenance, source and temporal attribution are preserved;
- partiality, failure and unavailability remain distinct;
- uncertainty and ambiguity remain explicit;
- attribution failure remains visible;
- identity metadata and derived interpretation remain distinct from facts;
- effective identity context is preserved without Lifecycle processing;
- Mapping mechanics and Observation Acceptance remain excluded;
- the exact 30-question set is retained;
- the exact 35-invariant set is retained;
- ADP-001D, ADP-001E and EAP-004 traceability is complete;
- no runtime or Provider communication authority is introduced; and
- no EDD or implementation authority is introduced.

## 18. Mandatory EAP-005 Review Criteria

Chief Architect review shall verify:

1. Instrument and Observation ownership remain separate.
2. Attribution does not create or alter identity.
3. Candidate factual information does not become an Observation merely by crossing the boundary.
4. EAP-004 identity is consumed without reinterpretation.
5. Exactly two Attribution Outcomes exist.
6. Attribution eligibility is not factual correctness.
7. Attribution eligibility is not Observation Acceptance or ownership.
8. Provenance, source and temporal attribution are preserved.
9. Partiality, failure and unavailability remain distinct.
10. Uncertainty and ambiguity remain explicit.
11. Attribution failure remains visible.
12. Identity metadata and derived interpretation remain distinct from facts.
13. Effective identity context is preserved without Lifecycle processing.
14. Mapping mechanics remain excluded.
15. Observation Acceptance remains excluded.
16. The exact 30-question set is retained.
17. The exact 35-invariant set is retained.
18. ADP-001D, ADP-001E and EAP-004 traceability is complete.
19. No runtime or Provider communication authority is introduced.
20. No EDD or implementation authority is introduced.

## 19. ADR Determination

**ADR Required: No**

No ADR is required provided EAP-005 translates ADP-001D, preserves Instrument and Observation ownership, uses the existing Instrument → Observation dependency, creates no new domain or dependency, does not define acquisition, does not enter Observation Acceptance and creates no reusable platform attribution framework. An ADR becomes required if any of those conditions are violated.

## 20. Document Register Entry

| Field | Required value |
| --- | --- |
| Document ID | EAP-005 |
| Title | Instrument-to-Observation Attribution Eligibility Engineering Architecture |
| Classification | Engineering Architecture Package |
| Product | KRONOS Swing |
| Phase | Phase 1 — Market Data Foundation |
| Owner | Engineering Architect |
| Governing ADP | ADP-001D Version 1.0 |
| Supporting ADPs | ADP-001A, ADP-001B, ADP-001C, ADP-001E, ADP-001H, ADP-001I, ADP-001J |
| Upstream EAP | EAP-004 Version 1.0 |
| Version | 1.0 |
| Status | Approved |
| Canonical Status | Approved Canonical Engineering Architecture |
| ADR Required | No |
| Engineering Impact | None |
| Runtime Impact | None |
| EDD Authorization | None |
| Implementation Authorization | None |
| Commit Authorization | None |
| Push Authorization | None |
| Next Authorized Capability | None |
| Repository location | `docs/engineering/eap/EAP-005-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY.md` |

## 21. Authorization Boundaries

| Item | Decision |
| --- | --- |
| EAP-005 official capability | Confirmed |
| Original EAP-005 Draft Version 0.1 | Authorized and reviewed |
| Amended EAP-005 Draft Version 0.2 | Authorized for amendment review |
| EAP-005 Draft Version 0.3 | Reviewed and amended |
| Canonical EAP-005 Version 1.0 | Approved Canonical Engineering Architecture |
| Canonicalization | Authorized |
| EAP-006 | Not authorized |
| EDD | Not authorized |
| Implementation | Not authorized |
| Runtime activity | Not authorized |
| Commit | Not authorized |
| Push | Not authorized |

## 22. Review History

EAP-005 Draft Version 0.1 was authorized by the Chief Architect Repository Architecture Review — Next Authorized Capability. Engineering verification was completed. The first independent Chief Architect review produced CA-EAP005-001 through CA-EAP005-003 together with the associated governance corrections. Draft Version 0.2 applied those amendments. Engineering re-verification was completed and the Chief Architect re-review produced CA-EAP005-004 and GOV-EAP005-006. Draft Version 0.3 applied those required amendments. The final Chief Architect review authorized canonicalization. EAP-005 Version 1.0 is the Approved Canonical Engineering Architecture.

## 23. Approval Record

**Chief Architect Decision:** Approved

**Engineering Architect Verification:** Complete

**Canonical Status:** Approved Canonical Engineering Architecture

**ADR Required:** No

**EDD Authorization:** None

**Implementation Authorization:** None

**Commit Authorization:** None

**Push Authorization:** None

**Next Authorized Capability:** None

## Related Approved Authority

- [Platform Constitution](../../architecture/platform/PLATFORM-000-CONSTITUTION.md)
- [ADP-001A — Swing Phase 1 Market Data Inventory](../../architecture/products/swing/SWING-PHASE-1-MARKET-DATA-INVENTORY.md)
- [ADP-001B — Instrument Identity Architecture](../../architecture/products/swing/SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md)
- [ADP-001C — Provider → Instrument Contract](../../architecture/products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md)
- [ADP-001D — Instrument → Observation Contract](../../architecture/products/swing/SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md)
- [ADP-001E — Observation Domain Architecture](../../architecture/products/swing/SWING-PHASE-1-OBSERVATION-DOMAIN-ARCHITECTURE.md)
- [ADP-001H — Provider Instrument Master Acquisition Capability and Contract](../../architecture/products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md)
- [ADP-001I — Approved Instrument Universe and Reference Semantics Architecture](../../architecture/products/swing/SWING-PHASE-1-APPROVED-INSTRUMENT-UNIVERSE-AND-REFERENCE-SEMANTICS-ARCHITECTURE.md)
- [ADP-001J Version 1.0 — Instrument Interpretation and Canonical Identity Establishment Architecture](../../architecture/products/swing/SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md)
- [EAP-001 Version 1.0](EAP-001-CONFIGURATION-TO-PROVIDER-AUTHENTICATED-CONTEXT.md)
- [EAP-002 Version 1.0](EAP-002-PROVIDER-INSTRUMENT-MASTER-ACQUISITION.md)
- [EAP-003 Version 1.0](EAP-003-PROVIDER-TO-INSTRUMENT-ARCHITECTURAL-ADMISSIBILITY.md)
- [EAP-004 Version 1.0](EAP-004-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT.md)
- [Instrument Domain Architecture](../../architecture/platform/domains/instrument/ARCHITECTURE.md)
- [Observation Domain Architecture](../../architecture/platform/domains/observation/ARCHITECTURE.md)
- [Provider Domain Architecture](../../architecture/platform/domains/provider/ARCHITECTURE.md)
- [Domain Ownership Matrix](../../architecture/platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../architecture/platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [KRONOS Engine Ownership](../../architecture/ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../architecture/DATA_FLOW.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)
