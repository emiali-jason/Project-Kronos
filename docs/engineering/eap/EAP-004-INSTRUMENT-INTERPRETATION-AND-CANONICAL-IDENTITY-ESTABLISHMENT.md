# EAP-004 — Instrument Interpretation and Canonical Identity Establishment Engineering Architecture

**Document ID:** EAP-004
**Title:** Instrument Interpretation and Canonical Identity Establishment Engineering Architecture
**Version:** 1.0

**Status:** Approved

**Canonical Status:** Approved Canonical Engineering Architecture

**Classification:** Engineering Architecture Package

**Owner:** Engineering Architect

**Prepared By:** Engineering Architect

**Review Authority:** Chief Architect
**Repository Location:** `docs/engineering/eap/EAP-004-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT.md`

**Approved By:** Chief Architect

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Governing ADP:** ADP-001J Version 1.0

**Supporting ADPs:** ADP-001A, ADP-001B, ADP-001C, ADP-001D, ADP-001E, ADP-001H, ADP-001I

**Upstream EAP:** EAP-003 Version 1.0

**ADR Required:** No

**Engineering Impact:** None

**Runtime Impact:** None

**EDD Authorization:** None

**Implementation Authorization:** None

**Commit Authorization:** None

**Push Authorization:** None

**Next Authorized Capability:** None

## 1. Purpose

EAP-004 translates ADP-001J Version 1.0 into provider-neutral and implementation-neutral engineering contracts and representations for Instrument Interpretation and Canonical Identity Establishment.

EAP-004 begins at the EAP-003 Instrument Interpretation Entry Contract and defines Interpretation Readiness, Interpretation Activity, Interpretation Outcome, the determinate and indeterminate outcome taxonomy, identity-layer semantic sufficiency, identity decision boundaries, identity publication eligibility, provenance preservation, continuity preservation and boundary conformance.

EAP-004 is an engineering contract boundary only. It does not define runtime sequence, executable state machines, physical data movement, service workflows, implementation orchestration or any implementation technology.

## 2. Scope

EAP-004 defines engineering architecture for:

- Interpretation Readiness and Interpretation Not Ready;
- Interpretation Activity and its bounded activity meaning;
- determinate and indeterminate Interpretation Outcomes;
- Existing Identity Determined and New Identity Establishment Eligible;
- Existing Identity Reuse;
- Canonical Identity Establishment Eligibility and Canonical Identity Establishment Decision;
- Canonical Identity Established and Canonical Identity Not Established;
- Identity Publication Eligibility and Identity Publication Ineligibility;
- Instrument Identity Contract availability and unavailability;
- independent semantic sufficiency representations for Economic Instrument, Listed Instrument and Derivative Contract;
- Provider and Acquisition Provenance preservation;
- approved universe-context and identity-layer-context preservation;
- historical identity continuity preservation;
- boundary conformance and boundary violations;
- non-sensitive observability;
- engineering verification obligations; and
- termination before the ADP-001D Instrument-to-Observation boundary.

## 3. Engineering Governance

This Draft is an engineering translation of ADP-001J Version 1.0. It introduces no new architectural concept, semantic owner, domain dependency, physical communication authority, runtime behavior or implementation decision.

Canonical repository architecture remains authoritative. EAP-004 shall be interpreted consistently with ADP-001J, EAP-003, EAP-002, EAP-001 and their approved dependencies. Any conflict remains an architecture matter and shall not be resolved by engineering discretion.

## 4. Explicit Out of Scope

EAP-004 shall not define or authorize:

- Provider communication, Provider acquisition or authentication;
- Provider Submission Eligibility or ADP-001C Architectural Admissibility;
- physical movement or runtime Provider-to-Instrument communication;
- APIs, schemas, fields, payloads, serialization or transport;
- matching algorithms, symbol parsing, fuzzy matching, scoring, ranking, conflict-resolution algorithms or identity-generation algorithms;
- Provider Mapping establishment, Mapping persistence, Mapping reconciliation or Mapping effective-time mechanics;
- Lifecycle transitions, Lifecycle state machines, successor processing or continuous futures;
- Observation attribution, Observation Acceptance, Observation construction or Market Facts;
- Validation, Risk, Execution, Portfolio, Event or Audit meaning;
- databases, persistence, caching, scheduling, retries or runtime orchestration;
- EDD, implementation or code; and
- EAP-005.

EAP-004 shall not reinterpret Provider meaning, create canonical identity from availability, force an identity determination, or represent a semantic boundary as executable behavior.

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
- EAP-001 Version 1.0 — Configuration-to-Provider Authenticated Context Engineering Architecture;
- EAP-002 Version 1.0 — Provider Instrument Master Acquisition Engineering Architecture;
- EAP-003 Version 1.0 — Provider-to-Instrument Architectural Admissibility Engineering Architecture;
- Instrument Domain Architecture;
- Provider Domain Architecture;
- Domain Ownership Matrix;
- DOMAIN_DEPENDENCY_MATRIX.md;
- ENGINE_OWNERSHIP;
- DATA_FLOW;
- ADL-001 where applicable;
- the applicable Document Register; and
- approved architecture and engineering indexes.

## 6. Ownership and Domain Boundary

The primary governing architecture is ADP-001J. Instrument remains the sole semantic owner of Instrument Interpretation, canonical identity and the Instrument Identity Contract.

| Responsibility | Owner |
| --- | --- |
| Provider records, assertions and Provider meaning | Provider |
| Provider Provenance and Acquisition Provenance | Provider |
| EAP-003 Instrument Interpretation Entry Contract | Instrument-owned boundary derived from ADP-001C |
| Interpretation Readiness | Instrument |
| Interpretation Activity | Instrument |
| Interpretation Outcome | Instrument |
| Economic Instrument identity | Instrument |
| Listed Instrument identity | Instrument |
| Derivative Contract identity | Instrument |
| Existing Identity Reuse | Instrument |
| Canonical Identity Establishment | Instrument |
| Identity Publication Eligibility | Instrument |
| Instrument Identity Contract | Instrument |
| Observation attribution | Observation through ADP-001D, outside EAP-004 |

Engineering representation shall not transfer semantic ownership. No shared semantic ownership or new domain dependency is introduced.

## 7. Engineering Boundary

```text
EAP-003 Instrument Interpretation Entry Contract
                         ↓
              EAP-004 Interpretation Readiness
                         ↓
              EAP-004 Interpretation Activity
                         ↓
                 Interpretation Outcome
          ┌──────────────┼────────────────────┐
          ↓              ↓                    ↓
 Existing Identity   New Identity        Indeterminate Outcome
 Determined          Establishment       ├─ No Determination
          │           Eligible            ├─ Ambiguous Determination
          ↓              ↓                ├─ Conflicting Determination
 Existing Identity  Canonical Identity   ├─ Insufficient Semantic Information
 Reuse              Establishment        └─ Unsupported Identity Context
          │          Eligibility                  ↓
          │              ↓               Instrument Identity Contract Availability: Unavailable
          │   Canonical Identity Establishment       ↓
          │          Decision                    No Instrument Identity Contract
          │              ├─ Established
          │              └─ Not Established ──── Instrument Identity Contract Availability: Unavailable
          ↓              ↓
 Identity Publication Eligibility
          ↓
 Instrument Identity Contract Availability: Available
          ↓
 Instrument Identity Contract

EAP-004 terminates before ADP-001D Instrument-to-Observation attribution.
```

This is an engineering contract boundary only. It shall not be represented as a runtime sequence, executable state machine, physical data movement, service workflow or implementation orchestration. The Instrument Identity Contract Availability Contract remains entirely within the EAP-004 publication boundary and only determines whether the Instrument Identity Contract is available. Existing Identity Determined proceeds through Existing Identity Reuse and Identity Publication Eligibility; New Identity Establishment Eligible proceeds through Canonical Identity Establishment Eligibility, Decision and, only when established, Identity Publication Eligibility. An available result then permits the Instrument Identity Contract to cross the EAP-004 boundary as the sole downstream semantic contract. An unavailable result, including for indeterminate outcomes or Canonical Identity Not Established, produces no Instrument Identity Contract and no downstream semantic publication.

## 8. Upstream Dependency

The immediate upstream dependency is EAP-003 Version 1.0. EAP-004 may consume only an EAP-003 Instrument Interpretation Entry Contract that communicates Architectural Admissibility, the bounded Provider-owned Submission Unit association, preserved Provider and Acquisition Provenance, retained uncertainty and ambiguity, admissibility evidence, limitations and non-sensitive traceability.

EAP-004 shall not consume raw Provider payloads, Provider internals, transport objects, implementation exceptions, Authentication Material, Submission Ineligible units or information bypassing EAP-003. EAP-003 Architectural Admissibility remains distinct from Interpretation Readiness and does not itself imply interpretation success.

## 9. Downstream Boundary

The Instrument Identity Contract Availability Contract remains entirely within the EAP-004 publication boundary. Its sole responsibility is to determine whether an Instrument Identity Contract is available. It shall not become the downstream semantic contract presented to ADP-001D.

The only semantic contract crossing the EAP-004 boundary toward ADP-001D is the Instrument Identity Contract. It may cross only when Instrument Identity Contract Available, Identity Publication Eligibility and an approved determinate publication path have all been established. Instrument Identity Contract Unavailable shall produce no Instrument Identity Contract, no downstream identity publication and no downstream semantic contract. EAP-004 shall not define Instrument-side consumer behavior, Observation behavior or any downstream domain behavior.

## 10. Engineering Contracts

The following are semantic engineering contracts only. They shall not become APIs, schemas, payloads, fields, serialized objects, runtime interfaces or persistence structures.

### 10.1 Interpretation Input Contract

Represents the EAP-003 Instrument Interpretation Entry Contract and its preserved Provider meaning, Provider Provenance, Acquisition Provenance, approved universe context, identity-layer context, uncertainty, ambiguity and non-sensitive admissibility evidence.

### 10.2 Interpretation Readiness Contract

Represents whether the EAP-004 engineering preconditions for Interpretation Activity are present. Interpretation Readiness requires that an EAP-003 Instrument Interpretation Entry Contract exists, Architectural Admissibility has already been satisfied upstream, required provenance associations are present, approved Instrument evaluation context exists, approved universe context exists, identity-layer evaluation context exists, and the bounded interpretation may legitimately evaluate the presence, absence, ambiguity, conflict or support of semantic categories. Positive semantic sufficiency is not a readiness prerequisite. Interpretation Readiness is internal Instrument meaning, distinct from ADP-001C Architectural Admissibility and EAP-003 entry eligibility, and creates no second admissibility authority. Interpretation Not Ready is limited to absent upstream contract, ownership context, evaluation context or boundary conformance.

### 10.3 Interpretation Activity Contract

Represents the bounded Instrument-owned engineering activity of interpreting an eligible input. It does not define runtime behavior, algorithms, matching, orchestration or identity results.

### 10.4 Interpretation Outcome Contract

Represents exactly one Interpretation Outcome for one bounded interpretation. The only determinate outcomes are Existing Identity Determined and New Identity Establishment Eligible. The only indeterminate outcomes are No Determination, Ambiguous Determination, Conflicting Determination, Insufficient Semantic Information and Unsupported Identity Context.

### 10.5 Existing Identity Reuse Contract

Represents Existing Identity Reuse only after Existing Identity Determined and continuity conformance establish that an existing canonical identity applies. Existing Identity Determined shall not automatically become Existing Identity Reuse.

### 10.6 New Identity Establishment Eligibility Contract

Represents New Identity Establishment Eligible as a determinate Interpretation Outcome. It does not establish canonical identity and does not itself establish Canonical Identity Establishment Eligibility.

### 10.7 Canonical Identity Establishment Eligibility Contract

Represents the separate Instrument-owned eligibility meaning that a Canonical Identity Establishment Decision may be considered after New Identity Establishment Eligible and applicable semantic sufficiency evaluation.

### 10.8 Canonical Identity Establishment Decision Contract

Represents the Instrument-owned decision that may result in Canonical Identity Established or Canonical Identity Not Established. Canonical Identity Not Established preserves the applicable reason, establishes no canonical identity, produces no Instrument Identity Contract, does not imply Instrument non-existence, does not become No Determination retroactively and does not alter Provider meaning.

### 10.9 Identity Indeterminacy Contract

Represents No Determination, Ambiguous Determination, Conflicting Determination, Insufficient Semantic Information or Unsupported Identity Context. It shall not produce an Instrument Identity Contract.

### 10.10 Identity-Layer Semantic Sufficiency Contract

Represents semantic sufficiency independently for Economic Instrument, Listed Instrument and Derivative Contract. It preserves every conceptual category established by ADP-001J and does not define fields, formats, parsing, matching, thresholds, algorithms or implementation.

### 10.11 Provenance Preservation Contract

Preserves Provider Provenance and Acquisition Provenance without transferring Provider ownership or exposing sensitive values.

### 10.12 Identity Continuity Contract

Represents preserved historical identity continuity and continuity context without defining Mapping mechanics or Lifecycle transition mechanics.

### 10.13 Identity Publication Eligibility Contract

Represents whether approved Instrument meaning may be presented through the Instrument Identity Contract after a determinate outcome and applicable identity decision. It is established before the internal Instrument Identity Contract Availability Contract and remains distinct from that availability determination.

### 10.14 Instrument Identity Contract

Represents only the Instrument-owned semantic contract containing approved canonical Instrument meaning, identity layer, approved classification where already established, approved relationships where already established, approved universe context, applicable historical or effective context where already required, and provenance association without ownership transfer. It is the only semantic contract that may cross the EAP-004 boundary toward ADP-001D. It shall not represent its own availability, and shall not contain raw Provider payloads or sensitive values.

### 10.15 Instrument Identity Contract Availability Contract

Represents exactly one determination: Instrument Identity Contract Available or Instrument Identity Contract Unavailable. It remains downstream of Identity Publication Eligibility, remains entirely within the EAP-004 publication boundary, and is distinct from the Instrument Identity Contract. It shall not be presented to ADP-001D as a semantic contract.

### 10.16 Boundary Violation Contract

Represents a prohibited boundary condition, ownership violation, missing prerequisite, unsupported inference, attempted bypass or prohibited information crossing the EAP-004 boundary. It does not authorize remediation or reinterpretation.

## 11. Engineering Representations

The following representations preserve one-to-one engineering meaning. They are not implementation states or runtime state-machine instructions.

| Engineering representation | Meaning |
| --- | --- |
| `INTERPRETATION_READY` | EAP-004 preconditions permit Interpretation Activity to be represented. |
| `INTERPRETATION_NOT_READY` | EAP-004 preconditions do not permit Interpretation Activity to be represented. |
| `INTERPRETATION_NOT_STARTED` | Interpretation Activity has not been represented as begun. |
| `INTERPRETATION_ACTIVE` | Interpretation Activity is represented as active within the bounded engineering contract. |
| `EXISTING_IDENTITY_DETERMINED` | Determinate outcome establishing that an existing canonical identity applies to the bounded context. |
| `NEW_IDENTITY_ESTABLISHMENT_ELIGIBLE` | Determinate outcome indicating that a new identity decision may be considered. |
| `NO_DETERMINATION` | Indeterminate outcome in which no identity determination is established; it does not imply non-existence. |
| `AMBIGUOUS_DETERMINATION` | Indeterminate outcome preserving materially plausible unresolved alternatives. |
| `CONFLICTING_DETERMINATION` | Indeterminate outcome preserving conflicting identity meaning. |
| `INSUFFICIENT_SEMANTIC_INFORMATION` | Indeterminate outcome where a required semantic category is absent or indistinguishable. |
| `UNSUPPORTED_IDENTITY_CONTEXT` | Indeterminate outcome where the approved identity context is not supported for determination. |
| `EXISTING_IDENTITY_REUSED` | Existing identity reuse after Existing Identity Determined and continuity conformance. |
| `CANONICAL_IDENTITY_ESTABLISHMENT_ELIGIBLE` | Separate eligibility meaning for considering a Canonical Identity Establishment Decision. |
| `CANONICAL_IDENTITY_ESTABLISHED` | Decision result establishing a new canonical identity after positive sufficiency. |
| `CANONICAL_IDENTITY_NOT_ESTABLISHED` | Decision result preserving the applicable reason where new identity conditions were not positively satisfied; no identity contract is available. |
| `IDENTITY_PUBLICATION_ELIGIBLE` | Approved Instrument meaning may be presented through the Instrument Identity Contract. |
| `IDENTITY_PUBLICATION_INELIGIBLE` | Approved Instrument meaning may not be presented through the Instrument Identity Contract. |
| `INSTRUMENT_IDENTITY_CONTRACT_AVAILABLE` | Instrument Identity Contract is available after applicable determinate processing and publication eligibility. |
| `INSTRUMENT_IDENTITY_CONTRACT_UNAVAILABLE` | No Instrument Identity Contract is available, including for indeterminate outcomes or Canonical Identity Not Established. |
| `PROVENANCE_PRESERVED` | Provider and Acquisition Provenance remain associated without sensitive disclosure. |
| `UNIVERSE_CONTEXT_PRESERVED` | Approved universe context remains associated. |
| `IDENTITY_LAYER_CONTEXT_PRESERVED` | Applicable identity-layer context remains associated. |
| `HISTORICAL_IDENTITY_CONTINUITY_PRESERVED` | Approved historical identity continuity remains associated. |
| `BOUNDARY_CONFORMANT` | The engineering contract conforms to the EAP-004 boundary. |
| `BOUNDARY_VIOLATION` | A prohibited condition, ownership violation, bypass or unsupported information crossing is represented. |

Semantic representations are not a runtime sequence and shall not be interpreted as executable lifecycle behavior.

## 12. Identity-Layer Semantic Sufficiency

EAP-004 represents semantic sufficiency independently for each identity layer using the conceptual categories established by ADP-001J.

### 12.1 Economic Instrument

The representation shall preserve: approved economic subject; approved instrument class; approved universe-membership context; semantic distinction from existing Economic Instruments; applicable identity continuity meaning; required provenance; absence of unresolved ambiguity; and absence of unresolved conflict.

### 12.2 Listed Instrument

The representation shall preserve: one approved Economic Instrument association; approved venue or listing context; semantic distinction from other Listed Instruments; applicable identity-layer and continuity context; approved role context where applicable; required provenance; absence of unresolved ambiguity; and absence of unresolved conflict.

### 12.3 Derivative Contract

The representation shall preserve: one approved Listed Instrument association; approved underlying relationship; contract category; contract-expiry identity meaning; semantic distinction from every other expiry; approved universe and role context; required provenance; absence of unresolved ambiguity; and absence of unresolved conflict.

Failure to establish any required category produces an Indeterminate Outcome. Missing meaning shall never be filled through inference, Provider vocabulary, symbols, tokens, price behaviour, availability or implementation convenience.

## 13. Engineering Obligations

Engineering shall:

- preserve Provider meaning, Provider Provenance and Acquisition Provenance;
- preserve approved universe context and identity-layer context;
- preserve historical identity continuity;
- keep Interpretation Readiness distinct from ADP-001C Architectural Admissibility and EAP-003 entry eligibility;
- establish Interpretation Readiness without requiring positive semantic sufficiency;
- evaluate missing semantic categories during Interpretation Activity, allowing Insufficient Semantic Information, Ambiguous Determination, Conflicting Determination or Unsupported Identity Context;
- keep Interpretation Activity distinct from Interpretation Outcome;
- keep determinate outcomes distinct from indeterminate outcomes;
- keep reuse, establishment eligibility, establishment decision and publication eligibility distinct;
- represent Canonical Identity Not Established without converting it to an Interpretation Outcome;
- keep Mapping and Lifecycle mechanics outside EAP-004;
- preserve boundary conformance and violations; and
- terminate before ADP-001D engineering.

## 14. Engineering Observability

Observability shall expose only non-sensitive engineering meaning sufficient to explain:

- Interpretation Readiness or Interpretation Not Ready;
- Interpretation Activity representation;
- exactly one Interpretation Outcome;
- semantic sufficiency by identity layer;
- preserved Provider and Acquisition Provenance presence;
- preserved universe and identity-layer context;
- preserved historical identity continuity;
- Existing Identity Reuse, Canonical Identity Establishment Eligibility and Decision;
- Canonical Identity Established or Canonical Identity Not Established and its applicable non-sensitive reason;
- Identity Publication Eligibility or Ineligibility;
- Instrument Identity Contract Available or Instrument Identity Contract Unavailable; and
- boundary conformance or violation.

Observability shall not expose raw Provider payloads, sensitive values, implementation details, transport details, APIs, schemas, persistence details or downstream semantic outcomes.

## 15. Downstream Restrictions

The Instrument Identity Contract Availability Contract remains internal to the EAP-004 publication boundary. Only an approved determinate publication path that establishes Identity Publication Eligibility and Instrument Identity Contract Available may permit the Instrument Identity Contract to cross the EAP-004 downstream boundary toward the existing ADP-001D boundary. Instrument Identity Contract Unavailable shall produce no Instrument Identity Contract, no downstream identity publication and no downstream semantic contract.

EAP-004 shall define no Instrument consumer behavior, Observation behavior, Market behavior, Validation behavior, Risk behavior, Execution behavior, Portfolio behavior, Event behavior or Audit behavior. No downstream domain may consume EAP-004 contracts directly except through the approved Instrument Identity Contract boundary.

## 16. Mandatory Engineering Question Set

The following questions are reproduced exactly and answered one-to-one.

### 1. What engineering contract represents Instrument Interpretation Readiness?

The Interpretation Readiness Contract represents whether EAP-004 preconditions permit Interpretation Activity. It is internal Instrument meaning and creates no second admissibility authority.

### 2. How is Interpretation Readiness kept distinct from ADP-001C Architectural Admissibility and EAP-003 entry eligibility?

ADP-001C Architectural Admissibility is the approved architectural determination that permits interpretation to begin. EAP-003 entry eligibility is the engineering boundary output that carries that determination. Interpretation Readiness is the subsequent EAP-004 internal Instrument meaning for whether Interpretation Activity may be represented. None implies interpretation success, identity or publication.

### 3. What engineering contract represents Instrument Interpretation Activity?

The Interpretation Activity Contract represents the bounded Instrument-owned engineering activity of interpreting an eligible input without defining runtime behavior, algorithms or implementation.

### 4. What exact preconditions permit Interpretation Activity?

An EAP-003 Instrument Interpretation Entry Contract must be present; Architectural Admissibility must already have been satisfied upstream; required provenance associations must be present; approved Instrument evaluation context, approved universe context and identity-layer evaluation context must exist; the bounded interpretation must be able to legitimately evaluate the presence, absence, ambiguity, conflict or support of semantic categories; and no boundary violation may prevent readiness. Positive semantic sufficiency is not a readiness prerequisite. Interpretation Not Ready is limited to an absent upstream contract, ownership context, evaluation context or required boundary conformance. Missing semantic categories are evaluated during Interpretation Activity and may produce Insufficient Semantic Information, Ambiguous Determination, Conflicting Determination or Unsupported Identity Context.

### 5. What information may enter the EAP-004 boundary?

Only an EAP-003-conforming Instrument Interpretation Entry Contract containing the bounded Provider-owned association, preserved Provider and Acquisition Provenance, approved universe and identity-layer context, retained uncertainty and ambiguity, admissibility evidence and non-sensitive traceability may enter.

### 6. What information is prohibited from entering the EAP-004 boundary?

Raw Provider payloads, Provider internals, transport objects, sensitive values, Authentication Material, implementation exceptions, Mapping mechanics, Lifecycle mechanics, information bypassing EAP-003, and any information that would introduce Observation, Market, Validation, Risk, Execution, Portfolio, Event or Audit meaning are prohibited.

### 7. What engineering contract represents Interpretation Outcome?

The Interpretation Outcome Contract represents exactly one determinate or indeterminate Interpretation Outcome for one bounded interpretation.

### 8. What determinate outcomes are permitted?

Only Existing Identity Determined and New Identity Establishment Eligible are determinate outcomes.

### 9. What indeterminate outcomes are permitted?

Only No Determination, Ambiguous Determination, Conflicting Determination, Insufficient Semantic Information and Unsupported Identity Context are indeterminate outcomes.

### 10. How is Successful Determination prevented from becoming an independent outcome?

Successful Determination is represented only as a collective classification of Existing Identity Determined and New Identity Establishment Eligible. It is not an independent engineering representation or contract.

### 11. What represents Existing Identity Determined?

`EXISTING_IDENTITY_DETERMINED` represents the determinate outcome that an existing canonical identity applies to the bounded context. It does not automatically establish Existing Identity Reuse.

### 12. What engineering conditions establish Existing Identity Reuse?

`EXISTING_IDENTITY_REUSED` may be represented only after Existing Identity Determined and continuity conformance establish that the existing canonical identity applies. Provider-reference change alone is insufficient.

### 13. What represents New Identity Establishment Eligible?

`NEW_IDENTITY_ESTABLISHMENT_ELIGIBLE` represents the determinate outcome that positive semantic sufficiency may permit a Canonical Identity Establishment Decision. It does not establish canonical identity.

### 14. How is New Identity Establishment Eligibility kept distinct from Canonical Identity Establishment Eligibility?

New Identity Establishment Eligible is an Interpretation Outcome. Canonical Identity Establishment Eligibility is a separate Instrument-owned eligibility meaning evaluated afterward and before the Canonical Identity Establishment Decision. Neither is canonical identity.

### 15. What engineering contract represents the Canonical Identity Establishment Decision?

The Canonical Identity Establishment Decision Contract represents the later Instrument-owned decision that may result in Canonical Identity Established or Canonical Identity Not Established.

### 16. What represents Canonical Identity Established?

`CANONICAL_IDENTITY_ESTABLISHED` represents the decision result that a new canonical identity has been positively established after New Identity Establishment Eligible, Canonical Identity Establishment Eligibility and applicable semantic sufficiency.

### 17. What represents Canonical Identity Not Established?

`CANONICAL_IDENTITY_NOT_ESTABLISHED` represents the later decision result that required conditions were not positively satisfied. It preserves the applicable non-sensitive reason, establishes no canonical identity, produces no Instrument Identity Contract, does not imply non-existence, does not become No Determination retroactively and does not alter Provider meaning.

### 18. Why does Canonical Identity Not Established produce no Instrument Identity Contract?

Because no canonical identity was established. Identity Publication Eligibility cannot produce an available Instrument Identity Contract without an established canonical identity.

### 19. What represents No Determination?

`NO_DETERMINATION` represents an indeterminate outcome in which no identity determination is established. It does not imply Instrument non-existence and produces no Instrument Identity Contract.

### 20. What represents Ambiguous Determination?

`AMBIGUOUS_DETERMINATION` represents an indeterminate outcome preserving materially plausible unresolved alternatives. It produces no Instrument Identity Contract.

### 21. What represents Conflicting Determination?

`CONFLICTING_DETERMINATION` represents an indeterminate outcome preserving conflicting identity meaning. It produces no Instrument Identity Contract.

### 22. What represents Insufficient Semantic Information?

`INSUFFICIENT_SEMANTIC_INFORMATION` represents an indeterminate outcome where a required semantic category is absent or indistinguishable. Missing meaning is not filled by inference, Provider vocabulary, symbols, tokens, price behaviour, availability or implementation convenience.

### 23. What represents Unsupported Identity Context?

`UNSUPPORTED_IDENTITY_CONTEXT` represents an indeterminate outcome where the approved identity context is not supported for determination. It shall not be converted into a supported determination.

### 24. How is semantic sufficiency represented separately for Economic Instrument, Listed Instrument and Derivative Contract?

The Identity-Layer Semantic Sufficiency Contract represents each layer independently. Economic Instrument preserves approved subject, class, universe membership, distinction, continuity, provenance, and absence of unresolved ambiguity or conflict. Listed Instrument preserves its approved Economic Instrument association, venue or listing, distinction, identity-layer and continuity context, role where applicable, provenance, and absence of unresolved ambiguity or conflict. Derivative Contract preserves its approved Listed Instrument association, underlying relationship, contract category, expiry identity meaning, distinction from every other expiry, universe and role context, provenance, and absence of unresolved ambiguity or conflict.

### 25. How are Provider meaning and provenance preserved?

Provider meaning, Provider Provenance and Acquisition Provenance remain associated through the Provenance Preservation Contract without transferring ownership or exposing sensitive values.

### 26. How are Mapping mechanics excluded while Mapping ownership remains recognized?

EAP-004 preserves that Mapping is Instrument-owned but defines no Mapping establishment, persistence, reconciliation, selection or effective-time mechanics.

### 27. How are Lifecycle mechanics excluded while identity continuity remains preserved?

EAP-004 preserves historical identity continuity and approved Lifecycle context while defining no Lifecycle transitions, state machines, successor processing or continuous futures.

### 28. What conditions establish Identity Publication Eligibility?

Identity Publication Eligibility shall be established only after Existing Identity Reuse or Canonical Identity Established, with required provenance and context preserved and no boundary violation. It is followed by the internal Instrument Identity Contract Availability Contract, which then determines exactly one of Instrument Identity Contract Available or Instrument Identity Contract Unavailable. Only the Instrument Identity Contract, never the availability contract, may cross toward ADP-001D as the downstream semantic contract.

### 29. What exactly may the Instrument Identity Contract publish and what must it never publish?

The Instrument Identity Contract is the only semantic contract that may cross toward ADP-001D. It may publish canonical identity meaning, identity layer, approved classification where already established, approved relationships where already established, approved universe context, applicable historical or effective context where already required, and provenance association without ownership transfer. It must never represent its own availability or publish raw Provider payloads, sensitive values, an indeterminate outcome, Canonical Identity Not Established, Observation, Market, Validation, Risk, Execution, Portfolio, Event or Audit meaning. The Instrument Identity Contract Availability Contract shall not be presented as this downstream semantic contract.

### 30. What matters require further architecture rather than Engineering discretion?

Provider communication, acquisition, authentication, Mapping mechanics, Lifecycle mechanics, Observation attribution, downstream domain behavior, APIs, schemas, persistence, runtime orchestration, EDD scope, implementation and any change in ownership, dependency or semantic authority require further approved architecture.

## 17. Mandatory Engineering Invariant Set

1. **Instrument Interpretation has one semantic owner: Instrument.**

2. **Canonical Instrument Identity has one semantic owner: Instrument.**

3. **Engineering representation shall not transfer semantic ownership.**

4. **Provider records, Provider assertions and Provider meaning shall remain owned by Provider.**

5. **EAP-003 entry eligibility shall not imply successful Instrument Interpretation.**

6. **Interpretation Readiness shall remain internal Instrument meaning and shall not create a second admissibility authority.**

7. **Interpretation Readiness shall not imply a determinate outcome.**

8. **Interpretation Activity shall remain distinct from Interpretation Outcome.**

9. **Exactly one Interpretation Outcome shall be represented for one bounded interpretation.**

10. **Existing Identity Determined and New Identity Establishment Eligible shall be the only determinate outcomes.**

11. **No Determination, Ambiguous Determination, Conflicting Determination, Insufficient Semantic Information and Unsupported Identity Context shall be the only indeterminate outcomes.**

12. **Successful Determination shall remain a collective classification and shall not become an independent state.**

13. **Existing Identity Determined shall not automatically become Existing Identity Reuse without continuity conformance.**

14. **New Identity Establishment Eligible shall not establish canonical identity.**

15. **Canonical Identity Establishment Eligibility shall remain distinct from the Canonical Identity Establishment Decision.**

16. **Canonical Identity Established and Canonical Identity Not Established shall remain distinct decision results.**

17. **Canonical Identity Not Established shall produce no Instrument Identity Contract.**

18. **An indeterminate outcome shall produce no Instrument Identity Contract.**

19. **No Determination shall not imply Instrument non-existence.**

20. **Ambiguity shall remain explicit and unresolved.**

21. **Conflicting identity meaning shall remain explicit.**

22. **Insufficient semantic information shall not be filled through inference.**

23. **Unsupported Identity Context shall not be converted into a supported determination.**

24. **Economic Instrument, Listed Instrument and Derivative Contract semantic sufficiency shall remain distinct.**

25. **Provider vocabulary, symbols, tokens, price behaviour and availability shall not establish canonical identity.**

26. **Provider Provenance shall remain preserved.**

27. **Approved universe context shall remain preserved.**

28. **Identity-layer context shall remain preserved.**

29. **Historical identity continuity shall remain preserved.**

30. **Provider Mapping mechanics shall remain outside EAP-004.**

31. **Instrument Lifecycle transition mechanics shall remain outside EAP-004.**

32. **Raw Provider payloads and sensitive values shall not enter EAP-004 contracts.**

33. **No Observation, Market, Validation, Risk, Execution, Portfolio, Event or Audit meaning shall be created by EAP-004.**

34. **EAP-004 shall remain provider-neutral and implementation-neutral.**

35. **EAP-004 shall not authorize Provider communication, Instrument-to-Observation attribution, an EDD, implementation or code.**

## 18. Engineering Verification Obligations

Engineering shall verify consistency with ADP-001J Version 1.0, EAP-003 Version 1.0, EAP-001, EAP-002, the authorized 30 Engineering Questions, the authorized 35 Engineering Invariants, the mandatory EAP-004 review criteria, the Domain Ownership Matrix, DOMAIN_DEPENDENCY_MATRIX.md, ENGINE_OWNERSHIP, DATA_FLOW and all listed canonical dependencies.

Verification shall confirm:

- no second admissibility authority;
- Interpretation Readiness does not require positive semantic sufficiency;
- Interpretation Not Ready is limited to missing upstream, ownership, evaluation or boundary context;
- missing semantic categories are evaluated during Interpretation Activity;
- exact determinate and indeterminate outcome taxonomy;
- mutually exclusive outcome meanings;
- no forced identity determination;
- no identity publication from indeterminate outcomes;
- no identity publication from Canonical Identity Not Established;
- Instrument Identity Contract Availability remains separate from the Instrument Identity Contract;
- reuse, establishment and publication remain separate;
- identity-layer semantic sufficiency is complete;
- no inference-based completion;
- Provider ownership and provenance are preserved;
- Mapping is excluded;
- Lifecycle is excluded;
- Observation is excluded; and
- no implementation, EDD or runtime authority exists.

## 19. Mandatory EAP-004 Review Criteria

The independent review shall verify:

1. Interpretation Readiness is not ADP-001C Architectural Admissibility or EAP-003 entry eligibility.
2. Interpretation Readiness requires upstream contract, ownership, evaluation and conformance context only; positive semantic sufficiency is not required.
3. Interpretation Not Ready is not substituted for Insufficient Semantic Information.
4. Interpretation Activity remains distinct from Interpretation Outcome.
5. The determinate and indeterminate outcome sets are exact and mutually exclusive.
6. Successful Determination is not an independent state.
7. Existing Identity Determined remains distinct from Existing Identity Reuse.
8. New Identity Establishment Eligible remains distinct from Canonical Identity Establishment Eligibility.
9. Canonical Identity Establishment Eligibility remains distinct from the Decision.
10. Canonical Identity Not Established produces Instrument Identity Contract Unavailable and no Instrument Identity Contract.
11. Indeterminate outcomes produce Instrument Identity Contract Unavailable and no Instrument Identity Contract.
12. Instrument Identity Contract Availability is separate from the Instrument Identity Contract.
13. Identity Publication Eligibility follows Existing Identity Reuse or Canonical Identity Established only.
14. Semantic sufficiency is represented independently for all three identity layers.
15. No required semantic category is filled by inference, Provider vocabulary, symbols, tokens, price behaviour, availability or convenience.
16. Provider and Acquisition Provenance are preserved without ownership transfer or sensitive disclosure.
17. Approved universe and identity-layer context remain preserved.
18. Historical identity continuity remains preserved.
19. Mapping mechanics and Lifecycle mechanics remain outside EAP-004.
20. The boundary terminates before ADP-001D.
21. The exact 30-question set is retained and answered one-to-one.
22. The exact 35-invariant set is retained.
23. Instrument Identity Contract Availability remains internal to EAP-004 and is not the downstream semantic contract.
24. Only the Instrument Identity Contract may cross toward ADP-001D after the approved determinate publication path.
25. No Observation, Market, Validation, Risk, Execution, Portfolio, Event or Audit meaning is introduced.
26. No implementation, EDD, Provider communication, commit or push authority is introduced.

## 20. ADR Determination

**ADR Required: No**

EAP-004 translates the already-approved ADP-001J boundary and introduces no new semantic owner, domain dependency, architecture, communication authority or implementation decision. Any departure from the approved ownership, dependency, boundary or scope conditions requires Chief Architect review and may require an ADR.

## 21. Document Register Entry

| Field | Required value |
| --- | --- |
| Document ID | EAP-004 |
| Title | Instrument Interpretation and Canonical Identity Establishment Engineering Architecture |
| Classification | Engineering Architecture Package |
| Product | KRONOS Swing |
| Phase | Phase 1 — Market Data Foundation |
| Owner | Engineering Architect |
| Governing ADP | ADP-001J Version 1.0 |
| Supporting ADPs | ADP-001A, ADP-001B, ADP-001C, ADP-001D, ADP-001E, ADP-001H, ADP-001I |
| Upstream EAP | EAP-003 Version 1.0 |
| Version | 0.3 |
| Status | Draft |
| Canonical Status | Not Canonical |
| ADR Required | No |
| Engineering Impact | None |
| Runtime Impact | None |
| EDD Authorization | None |
| Implementation Authorization | None |
| Commit Authorization | None |
| Push Authorization | None |
| Next Authorized Capability | None |
| Repository location | `docs/engineering/eap/EAP-004-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT.md` |

## 22. Authorization Boundaries

| Item | Decision |
| --- | --- |
| Official EAP number | EAP-004 confirmed |
| Original Draft EAP-004 Version 0.1 | Authorized |
| Reviewed and amended Draft EAP-004 Version 0.2 | Amendments applied |
| Canonical EAP-004 Version 1.0 | Approved Canonical Engineering Architecture |
| Interpretation Readiness engineering architecture | Authorized for Draft only |
| Instrument Interpretation implementation | Not authorized |
| Provider communication or acquisition | Not authorized |
| Mapping or normalization | Not authorized |
| Lifecycle implementation | Not authorized |
| Observation attribution | Not authorized |
| EDD | Not authorized |
| Implementation | Not authorized |
| Code | Not authorized |
| EAP-005 | Not authorized |
| Commit | Not authorized |
| Push | Not authorized |

## 23. Review History

EAP-004 Draft Version 0.1 was prepared under the authorized Draft instruction. Engineering Architect verification was completed for Draft Version 0.1. Independent Chief Architect review produced CA-EAP004-001, CA-EAP004-002 and CA-EAP004-003. Draft Version 0.2 applied those required amendments. The Chief Architect re-review produced CA-EAP004-004. Draft Version 0.3 applied that required amendment. Engineering Architect verification was completed for Draft Version 0.3. The final Chief Architect review approved canonicalization. EAP-004 Version 1.0 is the Approved Canonical Engineering Architecture.

## 24. Approval Record

**Chief Architect Decision:** Approved

**Original Draft Version:** 0.1

**Reviewed and Amended Draft Version:** 0.2

**Canonical Version:** 1.0

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
- [Instrument Domain Architecture](../../architecture/platform/domains/instrument/ARCHITECTURE.md)
- [Provider Domain Architecture](../../architecture/platform/domains/provider/ARCHITECTURE.md)
- [Domain Ownership Matrix](../../architecture/platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../architecture/platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [KRONOS Engine Ownership](../../architecture/ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../architecture/DATA_FLOW.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)
