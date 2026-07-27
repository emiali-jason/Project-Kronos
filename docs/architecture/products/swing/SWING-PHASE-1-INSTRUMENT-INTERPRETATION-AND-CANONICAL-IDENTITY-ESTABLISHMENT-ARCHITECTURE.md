# ADP-001J — Instrument Interpretation and Canonical Identity Establishment Architecture

**Document ID:** ADP-001J
**Title:** Instrument Interpretation and Canonical Identity Establishment Architecture
**Version:** 1.0

**Status:** Approved

**Canonical Status:** Approved Canonical Architecture

**Classification:** Architecture Documentation Package

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Owner:** Chief Architect

**Prepared By:** Product Master Architect

**Review Authority:** Chief Architect

**Approved By:** Chief Architect

**ADR Required:** No

**Repository Location:** `docs/architecture/products/swing/SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md`

**EAP Authorization:** None

**EDD Authorization:** None

**Implementation Authorization:** None

**Commit Authorization:** None

**Push Authorization:** None

**Next Authorized Capability:** None

## 1. Purpose

ADP-001J defines the provider-neutral, implementation-neutral architecture through which Instrument interprets Provider-owned information admitted through EAIC-002, establishes an Interpretation Outcome, evaluates a Canonical Identity Decision and establishes a Provider Mapping Status as independent Instrument-owned dimensions.

The capability defines the semantic Instrument Identity Contract and Canonical Instrument Catalogue publication meaning that may follow an approved canonical identity decision. Canonical identity remains independent of product membership. The capability terminates before the ADP-001D Instrument-to-Observation attribution boundary begins.

## 2. Scope

ADP-001J defines architecture for:

- Interpretation Processing Status;
- Instrument Interpretation and Interpretation Activity;
- Interpretation Outcomes;
- Canonical Identity Decision;
- Provider Mapping Status;
- Economic Instrument, Listed Instrument and Derivative Contract determination;
- Existing Canonical Identity Reuse;
- New Canonical Identity Establishment;
- Instrument Identity Contract eligibility and meaning;
- Canonical Instrument Catalogue publication;
- preservation of Provider meaning, Provider Provenance and supplied Acquisition Provenance;
- preservation of uncertainty and ambiguity;
- identity traceability and historical identity continuity;
- downstream publication restrictions; and
- architectural termination before ADP-001D attribution.

The architecture may define conceptual states and boundaries. It shall not define runtime transitions or implementation mechanics.

## 3. Explicit Out of Scope

ADP-001J shall not define or authorize:

- Provider acquisition, communication or authentication;
- Provider Submission Eligibility, EAIC-002 technical receipt, contract validation or Interpretation Admission;
- runtime Provider-to-Instrument communication or physical transport;
- APIs, schemas, fields, payloads, serialization, persistence, caching, databases, repositories, synchronization, scheduling, retries, polling or event processing;
- implementation services, identity-matching algorithms, symbol parsing, fuzzy matching, scoring, ranking, collision-resolution algorithms, automatic correction, normalization, enrichment or deduplication;
- Provider mapping implementation, mapping persistence or mapping reconciliation;
- lifecycle state machines, transition criteria, successor discovery, rollover processing or continuous-futures construction;
- Observation eligibility, factual attribution, Observation Acceptance, Observation ownership, Market Facts, Market Schedule, Validation, Risk, Execution, Portfolio, Event or Audit meaning;
- Options capability;
- EAP-004, EDD, implementation or code.

The architecture shall not define mapping-effective-time mechanics or Instrument lifecycle-transition behaviour unless separately authorized through approved architecture.

## 4. Governing Architecture

The primary governing architecture is ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture. ADR-009 establishes Provider acquisition and catalogue ownership, Instrument interpretation and canonical identity ownership, product-independent canonical identity, and the governing principle Acquire Broadly, Interpret Canonically, Consume Explicitly.

EAIC-002 — Provider → Instrument Submission Contract is the sole canonical upstream boundary. It distinguishes Provider-owned Submission Eligibility from Instrument-owned Interpretation Admission and does not perform interpretation or assign Instrument meaning. ADP-001B remains supporting Instrument identity architecture. ADP-001C is superseded and retained only for predecessor traceability.

This migration does not activate ADR-009 or EAIC-002 and does not authorize runtime behaviour, implementation or EDD-004.

## 5. Supporting Architecture

ADP-001J shall conform to:

- Platform Constitution;
- ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture;
- MIG-001 — ADR-009 Coordinated Architecture Migration Package;
- EAIC-002 — Provider → Instrument Submission Contract;
- ADP-001A — Swing Phase 1 Market Data Inventory;
- ADP-001B — Instrument Identity Architecture;
- ADP-001D — Instrument → Observation Contract;
- ADP-001E — Observation Domain Architecture;
- ADP-001H — Provider Instrument Master Acquisition Capability;
- ADP-001I — Approved Instrument Universe and Reference Semantics Architecture;
- Instrument Domain Architecture;
- Provider Domain Architecture;
- Domain Ownership Matrix;
- Domain Dependency Matrix;
- ENGINE_OWNERSHIP;
- DATA_FLOW;
- ADL-001 where existing analysis, reference and execution relationships apply.

ADP-001C is a superseded predecessor and grants no current authority. ADP-001I may provide approved reference semantics and relationships, but product membership or a product universe shall not establish or constrain canonical Instrument identity.

## 6. Semantic Ownership

| Meaning | Semantic owner |
| --- | --- |
| Instrument Interpretation | Instrument |
| Interpretation Processing Status | Instrument |
| Interpretation Outcome | Instrument |
| Canonical Identity Decision | Instrument |
| Provider Mapping Status | Instrument |
| Canonical Instrument Identity | Instrument |
| Canonical Identity Establishment | Instrument |
| Instrument Identity Contract | Instrument |
| Canonical Instrument Catalogue | Instrument |
| Provider records, identifiers and assertions | Provider |
| Provider Provenance | Provider |

No shared semantic ownership is authorized. Provider information remains Provider-owned while Instrument evaluates admissibility and interpretation.

## 7. Domain Ownership

| Responsibility | Owner |
| --- | --- |
| Provider Instrument Reference | Provider |
| Provider identifier | Provider |
| Provider assertion | Provider |
| Provider Provenance | Provider |
| Acquisition Provenance | Provider |
| Interpretation Processing Status | Instrument |
| Instrument Interpretation | Instrument |
| Interpretation Outcome | Instrument |
| Canonical Identity Decision | Instrument |
| Provider Mapping Status | Instrument |
| Economic Instrument identity | Instrument |
| Listed Instrument identity | Instrument |
| Derivative Contract identity | Instrument |
| Canonical Identity Establishment | Instrument |
| Instrument Identity Contract | Instrument |
| Provider Mapping and cross-Provider reconciliation | Instrument; detailed mechanics remain outside ADP-001J |
| Canonical Instrument Catalogue publication | Instrument |
| Instrument Lifecycle meaning | Instrument; lifecycle transitions remain outside ADP-001J |
| Factual attribution | Observation, outside ADP-001J |
| Observation Acceptance | Observation, outside ADP-001J |

Instrument publishes the Instrument Identity Contract and Canonical Instrument Catalogue and owns interpretation, canonical identity, classification, Provider mapping, cross-Provider reconciliation and approved relationships. Products consume canonical Instrument identity explicitly and do not create it. No ownership is transferred by interpretation.

## 8. Architectural Boundary

```text
Provider-owned Submission Unit
            through EAIC-002
                    ↓
     Interpretation Admission
                    ↓
          Instrument Interpretation
                    ↓
   ┌───────────────────────────────────────┐
   │ Interpretation Processing Status      │
   │ NOT_STARTED | PENDING | COMPLETED     │
   ├───────────────────────────────────────┤
   │ Interpretation Outcome                │
   │ INTERPRETED | UNINTERPRETED |         │
   │ AMBIGUOUS | UNSUPPORTED               │
   ├───────────────────────────────────────┤
   │ Canonical Identity Decision           │
   │ NOT_EVALUATED |                       │
   │ CANONICAL_IDENTITY_ESTABLISHED |      │
   │ CANONICAL_IDENTITY_NOT_ESTABLISHED    │
   ├───────────────────────────────────────┤
   │ Provider Mapping Status               │
   │ NOT_EVALUATED | MAPPING_PENDING |     │
   │ MAPPED | NOT_MAPPED |                 │
   │ MAPPING_AMBIGUOUS |                   │
   │ MAPPING_UNSUPPORTED                   │
   └───────────────────────────────────────┘
                    ↓
   Instrument Identity Contract and
   Canonical Instrument Catalogue publication
   only where canonical identity is established
                              ↓
                       ADP-001J ends
```

This is the conceptual semantic boundary model. EAIC-002 Interpretation Admission permits Instrument Interpretation to begin but does not perform it. Interpretation Processing Status, Interpretation Outcome, Canonical Identity Decision and Provider Mapping Status are independent Instrument-owned dimensions. Completion of one dimension shall not imply a value in another. An INTERPRETED outcome does not by itself establish canonical identity or Provider mapping. Canonical identity establishment does not depend on product membership. Only CANONICAL_IDENTITY_ESTABLISHED permits publication of canonical Instrument meaning.

The model does not define execution order, runtime state, synchronous processing, data movement, services, modules or persistence.

## 9. Upstream Boundary

The immediate and only upstream boundary is EAIC-002 — Provider → Instrument Submission Contract. The upstream input is a Provider-owned Submission Unit carrying Provider meaning, Provider reference, Provider assertions, Provider Provenance, relevant Provider context, retained uncertainty and ambiguity, applicable scope limitations and applicable acquisition context. Provider owns Submission Eligibility. Instrument owns technical receipt, contract validation, Interpretation Admission and every interpretation dimension after admission.

Provider shall submit through EAIC-002 only and shall never populate Instrument or the Canonical Instrument Catalogue directly. A Submission Unit not admitted for interpretation shall not enter Instrument Interpretation. ADP-001C is historical predecessor traceability only and shall not be used as an active boundary.

## 10. Downstream Boundary

The immediate downstream architecture is ADP-001D — Instrument → Observation Contract. ADP-001J provides an Instrument Identity Contract that can identify the approved canonical Instrument subject for later attribution.

The Instrument Identity Contract shall not attribute facts, create factual market information, establish Observation Eligibility, establish Observation Acceptance, confer Observation ownership, create a Market Fact, prove factual correctness or authorize publication.

## 11. Architectural Responsibilities

Instrument shall:

- receive Provider-owned Submission Units only through EAIC-002 and own Interpretation Admission;
- establish and preserve Interpretation Processing Status;
- interpret admitted Provider information under approved Instrument architecture;
- identify the applicable identity layer;
- preserve Provider ownership and provenance;
- evaluate semantic sufficiency;
- distinguish identity reuse from new identity establishment;
- preserve ambiguity, conflict and insufficiency;
- establish exactly one applicable Interpretation Outcome when processing is completed;
- establish the Canonical Identity Decision independently from Interpretation Outcome;
- establish Provider Mapping Status independently from Interpretation Outcome and Canonical Identity Decision;
- own Provider mapping and cross-Provider reconciliation;
- establish canonical identity only where sufficiently supported;
- preserve historical identity continuity;
- publish approved Instrument meaning through an Instrument Identity Contract and the Canonical Instrument Catalogue only after CANONICAL_IDENTITY_ESTABLISHED;
- keep canonical identity independent of product membership and product eligibility; and
- terminate before factual attribution.

## 12. Architectural Non-Responsibilities

Instrument shall not acquire Provider ownership, reinterpret Provider availability as identity, perform Provider acquisition, repair Provider information, resolve ambiguity through implementation convenience, construct Observations, judge factual correctness, assign Market Schedule, perform Validation, or authorize trading or execution.

Provider retains responsibility for acquisition, Provider Catalogue, Provider-and-Dataset Catalogue Partitions, Provider records, Provider Record Identity, Provider dispositions, Submission Eligibility, Provider provenance, acquisition scope and outcomes, Provider Context, Provider Capability and Provider Entitlement.

Provider mapping remains Instrument-owned. Cross-Provider reconciliation remains Instrument-owned. ADP-001J defines Provider Mapping Status as an independent dimension but shall not define mapping mechanics, storage or effective-time implementation.

Lifecycle remains Instrument-owned. ADP-001J may consume approved lifecycle context only where necessary to preserve identity continuity; it shall not define transition criteria, state machines or operational processing.

Products own product universes, product eligibility and product consumption. Products consume canonical Instrument identity explicitly and shall not create, broaden or constrain it. Observation remains downstream and shall not participate in interpretation, canonical identity decision, Provider mapping or Canonical Instrument Catalogue publication.

## 13. Architectural Principles

### AP-J-001 — Instrument assigns Instrument meaning

Provider information may support interpretation. Only Instrument may assign Instrument meaning.

### AP-J-002 — Interpretation requires EAIC-002 admission

Instrument Interpretation shall begin only after EAIC-002 Interpretation Admission has been established.

### AP-J-003 — Provider meaning survives interpretation

Instrument Interpretation shall preserve Provider meaning, origin and provenance without transferring Provider ownership.

### AP-J-004 — Identity requires semantic sufficiency

Canonical Instrument Identity shall be established only through sufficient approved Instrument meaning, never merely through availability, symbol presence, token presence, connectivity or data receipt.

### AP-J-005 — Existing identity continuity precedes new identity establishment

An existing canonical identity shall be reused when approved semantic continuity is established. Provider-reference change alone shall not create a new identity.

### AP-J-006 — Independent dimensions remain independent

Interpretation Processing Status, Interpretation Outcome, Canonical Identity Decision and Provider Mapping Status shall not imply one another.

### AP-J-007 — Ambiguity remains explicit

Instrument Interpretation shall not silently choose one identity while materially plausible alternatives remain unresolved.

### AP-J-008 — Identity layers remain separate

Economic Instrument, Listed Instrument and Derivative Contract shall remain distinct Instrument-owned identity layers.

### AP-J-009 — Identity is not factual acceptance

Canonical Identity Establishment shall not imply Observation Acceptance, factual correctness or Market Fact ownership.

### AP-J-010 — Publication is product-independent

Instrument Identity publication through the Instrument Identity Contract and Canonical Instrument Catalogue shall remain Instrument-owned and independent of product membership.

## 14. Architectural Invariants

1. **Instrument Interpretation shall have one semantic owner: Instrument.**
2. **Canonical Instrument Identity shall have one semantic owner: Instrument.**
3. **Provider records and Provider meaning shall remain owned by Provider throughout interpretation.**
4. **Engineering or architectural representation shall not transfer semantic ownership.**
5. **EAIC-002 Interpretation Admission shall permit Instrument Interpretation to begin but shall not imply successful Instrument Interpretation.**
6. **EAIC-002 shall be the only upstream Provider → Instrument boundary.**
7. **Provider Submission Eligibility shall not establish Instrument Identity.**
8. **Provider availability shall not establish Instrument Identity.**
9. **Physical receipt shall not establish Instrument Identity.**
10. **Provider-native identifiers, Provider tokens, exchange tokens, symbols and row positions shall never establish canonical Instrument identity.**
11. **Economic Instrument, Listed Instrument and Derivative Contract shall remain distinct identity layers.**
12. **Analysis, reference and execution roles shall remain distinct from identity layers.**
13. **Existing identity continuity shall not be broken solely by Provider-reference change.**
14. **A symbol change shall not automatically create a new identity.**
15. **Provider-token reuse shall not automatically inherit canonical identity.**
16. **Absence of an existing Provider mapping shall not prove absence of an Instrument identity.**
17. **Presence of a Provider mapping shall not by itself prove semantic correctness.**
18. **Unresolved ambiguity shall not produce one canonical identity.**
19. **Conflicting identity meaning shall remain explicit.**
20. **Insufficient semantic information shall not be converted into a determined identity.**
21. **An UNINTERPRETED outcome shall not mean Instrument non-existence.**
22. **A new canonical identity shall require positive semantic sufficiency.**
23. **An existing identity shall be reused when approved semantic continuity is established.**
24. **Provider Provenance shall remain preserved.**
25. **Canonical identity shall remain independent of product membership and product eligibility.**
26. **Applicable identity-layer context shall remain preserved.**
27. **Instrument Interpretation shall not create Provider meaning.**
28. **Instrument Interpretation shall not create Observation, Market, Validation, Risk, Execution, Portfolio, Event or Audit meaning.**
29. **Instrument Interpretation shall not perform Provider acquisition.**
30. **Interpretation Processing Status, Interpretation Outcome, Canonical Identity Decision and Provider Mapping Status shall remain independent dimensions.**
31. **Cross-Provider reconciliation and Canonical Instrument Catalogue publication shall remain Instrument-owned.**
32. **The Instrument Identity Contract and Canonical Instrument Catalogue shall not contain raw Provider payloads.**
33. **Sensitive information shall not enter Instrument Interpretation or Instrument Identity contracts.**
34. **Historical identity shall survive Provider-reference change and lifecycle change where canonical architecture requires continuity.**
35. **ADP-001J shall remain provider-neutral and implementation-neutral and shall not authorize runtime, implementation or EDD-004.**

## 15. Architectural Terminology

| Term | Architectural definition |
| --- | --- |
| Instrument Interpretation | Instrument-owned architectural activity that evaluates Provider meaning admitted through EAIC-002 without transferring Provider ownership. |
| Interpretation Admission | Instrument-owned EAIC-002 boundary determination that a valid Submission Unit may enter Instrument Interpretation; it does not perform interpretation. |
| Interpretation Processing Status | Independent Instrument-owned processing dimension with values NOT_STARTED, PENDING and COMPLETED. |
| Interpretation Outcome | Independent Instrument-owned semantic dimension established when processing is COMPLETED, with values INTERPRETED, UNINTERPRETED, AMBIGUOUS and UNSUPPORTED. |
| INTERPRETED | Interpretation produced a supported Instrument meaning; it does not by itself establish canonical identity or Provider mapping. |
| UNINTERPRETED | Interpretation did not establish supported Instrument meaning; it does not imply Instrument non-existence. |
| AMBIGUOUS | Multiple materially plausible meanings remain unresolved. |
| UNSUPPORTED | The admitted information or semantic context is outside supported Instrument interpretation. |
| Canonical Identity Decision | Independent Instrument-owned dimension with values NOT_EVALUATED, CANONICAL_IDENTITY_ESTABLISHED and CANONICAL_IDENTITY_NOT_ESTABLISHED. |
| Provider Mapping Status | Independent Instrument-owned dimension with values NOT_EVALUATED, MAPPING_PENDING, MAPPED, NOT_MAPPED, MAPPING_AMBIGUOUS and MAPPING_UNSUPPORTED. |
| Existing Identity Reuse | Establishment that an existing canonical identity satisfies approved semantic continuity conditions. |
| New Canonical Identity Establishment | Instrument-owned decision establishing a new canonical identity where sufficient approved meaning exists. |
| Identity Layer | One of the distinct Instrument-owned layers: Economic Instrument, Listed Instrument or Derivative Contract. |
| Economic Instrument | Instrument-owned identity layer representing the economic subject. |
| Listed Instrument | Instrument-owned identity layer representing an approved listing and venue context. |
| Derivative Contract | Instrument-owned identity layer representing an individual derivative contract. |
| Semantic Sufficiency | Presence of sufficient approved Instrument meaning for the bounded determination. |
| Identity Continuity | Preservation of an existing identity across approved Provider-reference or lifecycle change where canonical architecture requires it. |
| Canonical Identity Establishment | Instrument-owned establishment of an approved canonical identity after CANONICAL_IDENTITY_ESTABLISHED. |
| Identity Publication Eligibility | Instrument-owned condition that CANONICAL_IDENTITY_ESTABLISHED permits approved Instrument meaning to be published. |
| Economic Instrument Semantic Sufficiency | Conceptual minimum semantic categories for an Economic Instrument determination: approved economic subject; approved instrument class; semantic distinction from existing Economic Instruments; applicable identity continuity meaning; required provenance; absence of unresolved ambiguity; and absence of unresolved conflict. These are semantic categories only, not fields, formats, parsing, matching, thresholds, algorithms or implementation. |
| Listed Instrument Semantic Sufficiency | Conceptual minimum semantic categories for a Listed Instrument determination: one approved Economic Instrument association; approved venue or listing context; semantic distinction from other Listed Instruments; applicable identity-layer and continuity context; approved role context where applicable; required provenance; absence of unresolved ambiguity; and absence of unresolved conflict. These are semantic categories only, not fields, formats, parsing, matching, thresholds, algorithms or implementation. |
| Derivative Contract Semantic Sufficiency | Conceptual minimum semantic categories for a Derivative Contract determination: one approved Listed Instrument association; approved underlying relationship; contract category; contract-expiry identity meaning; semantic distinction from every other expiry; applicable role context where required; required provenance; absence of unresolved ambiguity; and absence of unresolved conflict. These are semantic categories only, not fields, formats, parsing, matching, thresholds, algorithms or implementation. |
| Instrument Identity Contract | Governed Instrument-owned semantic contract publishing approved canonical Instrument meaning for downstream use. |
| Canonical Instrument Catalogue | Instrument-owned, product-neutral publication of established canonical Instrument identities, classifications, relationships and applicable lifecycle meaning. |
| Provider Instrument Reference | Provider-owned reference to an instrument, external and non-canonical. |
| Provider Meaning | Provider-owned assertions and context preserved without becoming Instrument meaning. |
| Instrument Meaning | Instrument-owned interpretation and identity meaning. |
| Historical Identity | Canonical identity continuity preserved across historical reference or lifecycle change. |
| Provider Mapping | Instrument-owned governed association between a Provider reference and an Instrument identity. |
| Lifecycle Context | Approved context relevant to identity continuity; lifecycle transitions remain outside this architecture. |

Semantic sufficiency is evaluated separately for each identity layer at the architectural level. Failure to establish required semantic meaning prevents CANONICAL_IDENTITY_ESTABLISHED. Sufficiency shall never be satisfied through product membership, Provider vocabulary, symbol presence, token presence, implementation convenience or price behaviour.

## 16. Architectural Contracts

### 16.1 Interpretation Input Contract

Carries a Provider-owned Submission Unit admitted through EAIC-002 into Instrument Interpretation. The applicable identity-layer evaluation shall preserve the conceptual semantic categories defined for Economic Instrument, Listed Instrument or Derivative Contract sufficiency, including required provenance and absence of unresolved ambiguity and conflict.

### 16.2 Interpretation Processing Status Contract

Represents exactly one independent processing status: NOT_STARTED, PENDING or COMPLETED.

### 16.3 Interpretation Outcome Contract

Represents exactly one outcome after completed processing: INTERPRETED, UNINTERPRETED, AMBIGUOUS or UNSUPPORTED. It does not imply a Canonical Identity Decision or Provider Mapping Status.

### 16.4 Canonical Identity Decision Contract

Represents exactly one independent decision: NOT_EVALUATED, CANONICAL_IDENTITY_ESTABLISHED or CANONICAL_IDENTITY_NOT_ESTABLISHED.

### 16.5 Provider Mapping Status Contract

Represents exactly one independent mapping status: NOT_EVALUATED, MAPPING_PENDING, MAPPED, NOT_MAPPED, MAPPING_AMBIGUOUS or MAPPING_UNSUPPORTED.

### 16.6 Existing Identity Reuse Contract

Represents that an already canonical Instrument identity satisfies approved semantic continuity conditions without dependence on product membership.

### 16.7 New Identity Establishment Contract

Represents bounded Instrument-owned establishment of a new canonical identity only where positive semantic sufficiency supports CANONICAL_IDENTITY_ESTABLISHED.

### 16.8 Identity Publication Eligibility Contract

Represents the Instrument-owned condition that CANONICAL_IDENTITY_ESTABLISHED permits publication of approved canonical Instrument meaning.

### 16.9 Provenance Preservation Contract

Preserves Provider origin, Provider assertions and applicable Acquisition Provenance.

### 16.10 Identity Continuity Contract

Preserves existing and historical identity across Provider-reference change without defining lifecycle processing.

### 16.11 Instrument Identity Contract

Publishes approved canonical Instrument meaning after CANONICAL_IDENTITY_ESTABLISHED, including identity layer, canonical identity meaning, approved classification and relationships where established, relevant historical or effective context where architecture requires it, and traceable provenance association without Provider ownership transfer.

### 16.12 Canonical Instrument Catalogue Publication Contract

Publishes established canonical Instrument identities in an Instrument-owned, product-neutral catalogue. Product universe membership and product eligibility remain separate downstream meanings.

### 16.13 Downstream Eligibility Contract

Represents only that approved canonical Instrument meaning may be presented to the ADP-001D attribution boundary. Observation remains downstream and does not participate in interpretation.

No contract above is an API, payload, schema, runtime object or implementation interface.

## 17. Resolved Architecture Decisions

- Instrument is the exclusive semantic owner of Instrument Interpretation, all four interpretation dimensions, Provider mapping, cross-Provider reconciliation, Canonical Identity Establishment, the Instrument Identity Contract and Canonical Instrument Catalogue publication.
- Provider retains ownership of Provider records, identifiers, assertions, meaning and provenance.
- Economic Instrument, Listed Instrument and Derivative Contract remain distinct identity layers.
- EAIC-002 is the sole upstream boundary. Provider owns Submission Eligibility; Instrument owns technical receipt, contract validation and Interpretation Admission.
- Existing identity reuse is distinct from new identity establishment.
- Interpretation Processing Status, Interpretation Outcome, Canonical Identity Decision and Provider Mapping Status are independent Instrument-owned dimensions.
- Canonical identity is independent of product membership; products consume canonical identity explicitly rather than creating it.
- Provider-native identifiers never establish canonical Instrument identity.
- Observation remains downstream and does not participate in interpretation.
- ADP-001J terminates before ADP-001D factual attribution.

## 18. Unresolved Architecture Decisions

The following matters remain unresolved and are not decided by this architecture:

- exact identity-defining attributes for each identity layer;
- detailed mapping-effective-time rules;
- detailed lifecycle-transition behaviour;
- continuous-futures identity treatment;
- physical identifier format;
- storage or persistence representation.

These matters require separate approved architecture where applicable.

## 19. Architecture Risks

- Provider meaning may be mistaken for Instrument meaning.
- Submission Eligibility or Interpretation Admission may be mistaken for interpretation or identity determination.
- Ambiguity or conflict may be silently forced into one identity.
- Provider-reference changes may incorrectly create new identity.
- Independent interpretation dimensions may be collapsed into one state.
- Product membership may be mistaken for canonical identity authority.
- Instrument Identity Contract may be treated as factual acceptance or Observation authority.
- Downstream attribution may begin before approved Instrument meaning is available.

These are architectural risks, not implementation instructions.

## 20. Architecture Review Questions

### 1. What is Instrument Interpretation?

Instrument Interpretation is the Instrument-owned architectural activity that evaluates Provider-owned information admitted through EAIC-002 and establishes Instrument meaning without transferring Provider ownership.

### 2. Who owns Instrument Interpretation?

Instrument exclusively owns Instrument Interpretation.

### 3. What is the only upstream boundary?

EAIC-002 is the sole Provider → Instrument boundary. Provider owns Submission Eligibility; Instrument owns technical receipt, contract validation and Interpretation Admission.

### 4. How is Interpretation Admission kept distinct from interpretation?

Interpretation Admission permits a valid Submission Unit to enter Instrument Interpretation. It does not perform interpretation, establish an Interpretation Outcome, decide canonical identity or establish Provider mapping.

### 5. What begins Instrument Interpretation?

Instrument Interpretation begins only after EAIC-002 Interpretation Admission.

### 6. What ends Instrument Interpretation?

Interpretation processing ends when Interpretation Processing Status becomes COMPLETED and exactly one Interpretation Outcome is established. Canonical Identity Decision and Provider Mapping Status remain independent dimensions.
### 7. What Provider-owned information may support interpretation?

Provider records, Provider identifiers, Provider assertions, Provider Meaning, Provider Provenance, supplied Acquisition Provenance, Provider context, scope limitations, uncertainty and ambiguity admitted through EAIC-002 may support interpretation.

### 8. What Provider-owned information is prohibited from becoming Instrument meaning?

Provider ownership, raw Provider payloads, Provider availability, Provider tokens, Provider assertions as canonical meaning, and any Provider information not established as Instrument-owned meaning shall not become Instrument meaning.

### 9. What approved Instrument-owned context is required?

Approved identity-layer context, applicable semantic context, identity continuity context and any approved lifecycle or effective context required by canonical architecture are required. Conceptual semantic sufficiency is separate for each identity layer and remains independent of product membership. These are semantic categories only, not fields, formats, parsing, matching, thresholds, algorithms or implementation.

### 10. What Interpretation Outcomes are permitted?

The permitted outcomes are INTERPRETED, UNINTERPRETED, AMBIGUOUS and UNSUPPORTED.

### 11. How is Interpretation Outcome related to Canonical Identity Decision?

They are independent dimensions. INTERPRETED does not by itself establish canonical identity, and CANONICAL_IDENTITY_ESTABLISHED requires its own Instrument-owned decision.

### 12. What constitutes Existing Identity Reuse?

Existing Identity Reuse occurs when approved semantic continuity makes an already canonical Instrument identity apply to the bounded interpretation context.

### 13. When must an existing canonical identity be reused?

An existing canonical identity shall be reused when approved semantic continuity is established. Provider-reference change alone shall not create a new identity.

### 14. What conditions may permit New Canonical Identity Establishment?

New Canonical Identity Establishment may be permitted only through positive semantic sufficiency for the applicable identity layer and the independent CANONICAL_IDENTITY_ESTABLISHED decision. It shall never be satisfied through product membership, Provider vocabulary, symbol presence, token presence, implementation convenience or price behaviour.

### 15. Why does absence of an existing identity not by itself authorize new identity creation?

Absence proves neither non-existence nor semantic sufficiency. A new identity requires a positive approved determination, not merely a missing mapping or existing identity.

### 16. What does INTERPRETED mean?

INTERPRETED means supported Instrument meaning was produced. It does not itself establish canonical identity, Provider mapping, product eligibility or Observation meaning.

### 17. What does UNINTERPRETED mean?

UNINTERPRETED means supported Instrument meaning was not established. It does not imply Instrument non-existence or Provider failure.

### 18. What does AMBIGUOUS mean?

AMBIGUOUS means multiple materially plausible Instrument meanings remain unresolved and explicit.

### 19. What does UNSUPPORTED mean?

UNSUPPORTED means the admitted information or semantic context is outside supported Instrument interpretation. It does not imply Provider capability, entitlement or acquisition meaning.

### 20. What does CANONICAL_IDENTITY_NOT_ESTABLISHED mean?

It means the independent identity decision did not establish canonical identity. It produces no canonical identity publication and does not imply Instrument non-existence.

### 21. How are Economic Instrument, Listed Instrument and Derivative Contract determinations kept distinct?

They remain separate Instrument-owned identity-layer determinations. Meaning established at one layer shall not silently establish another layer.

### 22. How are analysis, reference and execution roles kept distinct from identity layers?

Analysis, reference and execution roles remain separate architectural roles. They do not define or replace Economic Instrument, Listed Instrument or Derivative Contract identity layers.

### 23. How is Provider meaning preserved throughout interpretation?

Provider meaning, origin, assertions and provenance remain associated with the interpreted information and are not transferred, rewritten or converted into Provider-owned canonical identity.

### 24. How is Provider Provenance preserved without transferring ownership?

Provider Provenance remains associated as traceable provenance context while Instrument owns only the interpretation and identity meaning it establishes.

### 25. What relationship exists between Instrument Interpretation and Provider Mapping?

Mapping and cross-Provider reconciliation remain Instrument-owned. Provider Mapping Status is independent from Interpretation Outcome and Canonical Identity Decision; mapping mechanics remain deferred.

### 26. What relationship exists between Instrument Interpretation and Instrument Lifecycle?

Lifecycle remains Instrument-owned. Interpretation may consume approved lifecycle context for continuity but does not define lifecycle transitions or processing.

### 27. What exactly is the Instrument Identity Contract?

It is the Instrument-owned governed contract publishing approved canonical Instrument meaning, identity-layer context, approved relationships and traceable provenance association for later downstream use only after CANONICAL_IDENTITY_ESTABLISHED.

### 28. What may the Instrument Identity Contract never establish?

It may never establish product eligibility, factual correctness, Observation Acceptance, Observation ownership, Market Facts, Validation, Risk, Execution, Portfolio, Event or Audit meaning, or authorize publication beyond approved architecture.

### 29. What downstream capability may consume the Instrument Identity Contract?

Only the approved ADP-001D Instrument-to-Observation attribution boundary may receive the downstream-eligible Instrument Identity Contract. Observation remains downstream and does not participate in interpretation.

### 30. What matters require separate architecture rather than resolution within ADP-001J?

Identity-defining attributes, detailed mapping and lifecycle mechanics, continuous-futures treatment, physical identifier format, persistence, and any implementation or runtime behavior require separate approved architecture. Provider-to-Instrument submission is already governed exclusively by EAIC-002.

## 21. Architecture Review Criteria

The independent Chief Architect review shall verify:

1. Instrument exclusively owns interpretation and canonical identity.
2. Provider meaning remains Provider-owned.
3. EAIC-002 remains the sole upstream boundary.
4. Submission Eligibility remains Provider-owned and Interpretation Admission remains Instrument-owned.
5. Interpretation Processing Status remains distinct from Interpretation Outcome.
6. Interpretation Outcome remains distinct from Canonical Identity Decision.
7. Provider Mapping Status remains distinct from the other three dimensions.
8. The four approved dimension vocabularies are used exactly.
9. Existing identity reuse remains separated from new identity establishment.
10. New identity requires positive semantic sufficiency for the applicable identity layer.
11. Required semantic categories cannot be satisfied by product membership, Provider vocabulary, symbol or token presence, implementation convenience or price behaviour.
12. Economic Instrument Semantic Sufficiency remains product-independent.
13. Listed Instrument Semantic Sufficiency remains product-independent.
14. Derivative Contract Semantic Sufficiency remains product-independent.
15. Provider-reference change does not silently create a new identity.
16. Provider-native identifiers never establish canonical identity.
17. Identity layers and roles remain distinct.
18. Provider mapping and cross-Provider reconciliation remain Instrument-owned.
19. Mapping and lifecycle mechanics are not silently implemented inside interpretation.
20. Historical identity continuity is preserved.
21. Canonical Instrument Catalogue publication remains Instrument-owned.
22. Product universes and product eligibility remain downstream product-owned meanings.
23. The Instrument Identity Contract is semantically defined and contains no raw Provider payload.
24. The downstream boundary stops before factual attribution.
25. Observation remains downstream and does not participate in interpretation.
26. Observation, Market, Validation, Risk, Execution, Portfolio, Event and Audit meaning is not created.
27. Options capability is not activated.
28. Provider neutrality and implementation neutrality are preserved.
29. No EAP, EDD, implementation, runtime or EDD-004 authority is introduced.

## 22. ADR Determination

**ADR Required: No**

No additional ADR is required for this migration because ADR-009 already governs the Provider-bounded acquisition and canonical Instrument interpretation architecture. ADP-001J preserves Instrument ownership, Provider ownership, the EAIC-002 and ADP-001D boundaries, and creates no new domain or dependency.

Further ADR authority becomes mandatory if a future amendment proposes shared interpretation ownership, a new semantic owner, a new domain or dependency, an alternate Provider-to-Instrument route, reassignment of mapping or lifecycle responsibility, or modification of the Domain Dependency Matrix or Platform Constitution.

## 23. Document Register Entry

| Field | Required value |
| --- | --- |
| Document ID | ADP-001J |
| Title | Instrument Interpretation and Canonical Identity Establishment Architecture |
| Classification | Architecture Documentation Package |
| Product | KRONOS Swing |
| Phase | Phase 1 — Market Data Foundation |
| Owner | Chief Architect |
| Prepared By | Product Master Architect |
| Review Authority | Chief Architect |
| Version | 1.0 |
| Status | Approved |
| Canonical Status | Approved Canonical Architecture |
| Governing Architecture | ADR-009 and ADP-001B |
| Upstream Boundary | EAIC-002 |
| Downstream Boundary | ADP-001D |
| Supporting Architecture | MIG-001, ADP-001A, ADP-001E, ADP-001H, ADP-001I |
| Semantic Owner | Instrument |
| ADR Required | No |
| Engineering Impact | None |
| Runtime Impact | None |
| EAP Authorization | None |
| EDD Authorization | None |
| Implementation Authorization | None |
| Commit Authorization | None |
| Push Authorization | None |
| Next Authorized Capability | None |
| Repository location | `docs/architecture/products/swing/SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md` |

## 24. Review History

ADP-001J Version 0.1 was authorized for Draft preparation. CA-ADP001J-001 through CA-ADP001J-004 were applied. Draft Version 0.2 incorporated those amendments. CA-ADP001J-005 through CA-ADP001J-007 were applied in Draft Version 0.3. The Product Master Architect performed drafting and self-review. Independent review was performed by the Chief Architect. Product Master Architect Verification was completed. Final Chief Architect Review resulted in canonicalization approval. WP-B4 migrated ADP-001J to ADR-009, EAIC-002 and the canonical Instrument Domain architecture without introducing runtime or implementation authority.

## 25. Approval Record

**Chief Architect Decision:** Approved

**Product Master Architect Verification:** Complete

**Canonical Status:** Approved Canonical Architecture

**Approved By:** Chief Architect

**ADR Required:** No

**EAP Authorization:** None

**EDD Authorization:** None

**Implementation Authorization:** None

**Commit Authorization:** None

**Push Authorization:** None

**Next Authorized Capability:** None

## Related Approved Authority

- [Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [ADP-001A — Swing Phase 1 Market Data Inventory](SWING-PHASE-1-MARKET-DATA-INVENTORY.md)
- [ADP-001B — Instrument Identity Architecture](SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md)
- [ADP-001C — Superseded Provider → Instrument Contract (historical predecessor)](SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md)
- [ADP-001D — Instrument → Observation Contract](SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md)
- [ADP-001E — Observation Domain Architecture](SWING-PHASE-1-OBSERVATION-DOMAIN-ARCHITECTURE.md)
- [ADP-001H — Provider Instrument Master Acquisition Capability and Contract](SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md)
- [ADP-001I — Approved Instrument Universe and Reference Semantics Architecture](SWING-PHASE-1-APPROVED-INSTRUMENT-UNIVERSE-AND-REFERENCE-SEMANTICS-ARCHITECTURE.md)
- [Instrument Domain Architecture](../../platform/domains/instrument/ARCHITECTURE.md)
- [Provider Domain Architecture](../../platform/domains/provider/ARCHITECTURE.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [KRONOS Engine Ownership](../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../DATA_FLOW.md)
