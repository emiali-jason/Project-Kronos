# ADP-001J — Instrument Interpretation and Canonical Identity Establishment Architecture

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

**EAP Authorization:** None

**EDD Authorization:** None

**Implementation Authorization:** None

**Commit Authorization:** None

**Push Authorization:** None

**Next Authorized Capability:** None

## 1. Purpose

ADP-001J defines the provider-neutral, implementation-neutral architecture through which Instrument evaluates architecturally admissible Provider-owned information and approved Instrument context to determine whether an existing canonical Instrument identity is established, a new canonical Instrument identity may be established, no identity determination can be made, the interpretation remains ambiguous, the interpretation contains conflicting meaning, required semantic information is insufficient, or the identity context is unsupported.

The capability defines the semantic Instrument Identity Contract that may be published after an approved identity determination. It terminates before the ADP-001D Instrument-to-Observation attribution boundary begins.

## 2. Scope

ADP-001J defines architecture for:

- Interpretation Eligibility;
- Instrument Interpretation and Interpretation Activity;
- Interpretation Outcomes;
- Economic Instrument, Listed Instrument and Derivative Contract determination;
- Existing Canonical Identity Reuse;
- New Canonical Identity Establishment;
- No Determination, Ambiguous Determination, Conflicting Determination, Insufficient Semantic Information and Unsupported Identity Context;
- Canonical Identity Establishment Eligibility and Decision;
- Instrument Identity Contract eligibility and meaning;
- preservation of Provider meaning, Provider Provenance and supplied Acquisition Provenance;
- preservation of approved universe context, uncertainty and ambiguity;
- identity traceability and historical identity continuity;
- downstream publication restrictions; and
- architectural termination before ADP-001D attribution.

The Draft may define conceptual architecture states and boundaries. It shall not define runtime transitions or implementation mechanics.

## 3. Explicit Out of Scope

ADP-001J shall not define or authorize:

- Provider acquisition, communication or authentication;
- Provider Submission Eligibility or ADP-001C Architectural Admissibility;
- runtime Provider-to-Instrument communication or physical transport;
- APIs, schemas, fields, payloads, serialization, persistence, caching, databases, repositories, synchronization, scheduling, retries, polling or event processing;
- implementation services, identity-matching algorithms, symbol parsing, fuzzy matching, scoring, ranking, collision-resolution algorithms, automatic correction, normalization, enrichment or deduplication;
- Provider mapping implementation, mapping persistence or mapping reconciliation;
- lifecycle state machines, transition criteria, successor discovery, rollover processing or continuous-futures construction;
- Observation eligibility, factual attribution, Observation Acceptance, Observation ownership, Market Facts, Market Schedule, Validation, Risk, Execution, Portfolio, Event or Audit meaning;
- Options capability;
- EAP-004, EDD, implementation or code.

The Draft shall not define mapping-effective-time mechanics or Instrument lifecycle-transition behaviour unless separately authorized through approved architecture.

## 4. Governing Architecture

The primary governing architecture is ADP-001B — KRONOS Swing Instrument Identity Architecture. ADP-001B establishes Instrument ownership, the three identity layers, stable identity, Provider-reference separation, Provider mapping principles, historical identity, lifecycle vocabulary and boundaries.

ADP-001C governs the Provider → Instrument Architectural Admissibility boundary. ADP-001C ends when Provider information becomes eligible for Instrument interpretation; it does not perform interpretation or assign Instrument meaning.

## 5. Supporting Architecture

ADP-001J shall conform to:

- Platform Constitution;
- ADP-001A — Swing Phase 1 Market Data Inventory;
- ADP-001B — Instrument Identity Architecture;
- ADP-001C — Provider → Instrument Contract;
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
- ADL-001 where existing analysis, reference and execution relationships apply; and
- EAP-003 only as an engineering representation of the upstream ADP-001C boundary.

ADP-001I establishes the approved Phase 1 semantic universe and approved MCX/COMEX relationships while leaving operational enumeration, detailed mapping, lifecycle and effective-context matters deferred.

## 6. Semantic Ownership

| Meaning | Semantic owner |
| --- | --- |
| Instrument Interpretation | Instrument |
| Interpretation Outcome | Instrument |
| Canonical Instrument Identity | Instrument |
| Canonical Identity Establishment | Instrument |
| Instrument Identity Contract | Instrument |
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
| Interpretation Eligibility | Instrument |
| Instrument Interpretation | Instrument |
| Interpretation Outcome | Instrument |
| Economic Instrument identity | Instrument |
| Listed Instrument identity | Instrument |
| Derivative Contract identity | Instrument |
| Canonical Identity Establishment | Instrument |
| Instrument Identity Contract | Instrument |
| Provider Mapping meaning | Instrument; detailed mapping architecture remains outside ADP-001J unless narrowly required |
| Instrument Lifecycle meaning | Instrument; lifecycle transitions remain outside ADP-001J |
| Factual attribution | Observation, outside ADP-001J |
| Observation Acceptance | Observation, outside ADP-001J |

Instrument publishes the Instrument Identity Contract and owns identity, mapping, classification and approved relationships. No ownership is transferred by interpretation.

## 8. Architectural Boundary

```text
Architecturally Admissible Provider Information
                    ↓
 Interpretation Eligibility
(internal Instrument readiness;
 not a second authorization)
                    ↓
          Instrument Interpretation
                    ↓
          Interpretation Outcome
          ├─ Existing Identity Determined
          │  └─ Existing Identity Reuse
          │     └─ Identity Publication Eligibility
          │        └─ Instrument Identity Contract
          ├─ New Identity Establishment Eligible
          │  └─ Canonical Identity Establishment Eligibility
          │     └─ Canonical Identity Establishment Decision
          │        ├─ Canonical Identity Established
          │        │  └─ Identity Publication Eligibility
          │        │     └─ Instrument Identity Contract
          │        └─ Canonical Identity Not Established
          │           └─ No Instrument Identity Contract
          └─ Indeterminate Outcome
             ├─ No Determination
             ├─ Ambiguous Determination
             ├─ Conflicting Determination
             ├─ Insufficient Semantic Information
             ├─ Unsupported Identity Context
             └─ No Instrument Identity Contract
                              ↓
                       ADP-001J ends
```

This is the conceptual semantic boundary model. ADP-001C Architectural Admissibility permits Instrument Interpretation to begin. Interpretation Eligibility is an Instrument-owned internal readiness meaning used only to identify the applicable approved Instrument context; it is not a second authorization, does not override or redefine ADP-001C, and missing Instrument context shall not retroactively invalidate Architectural Admissibility. Interpretation Outcome branches into Existing Identity Determined, New Identity Establishment Eligible and Indeterminate Outcome. Only the two determinate outcomes may continue toward Existing Identity Reuse or Canonical Identity Establishment evaluation. Indeterminate Outcome terminates immediately with No Instrument Identity Contract. A Canonical Identity Establishment Decision may result in Canonical Identity Established or Canonical Identity Not Established; the latter produces no Instrument Identity Contract.

The model does not define execution order, runtime state, synchronous processing, data movement, services, modules or persistence.

## 9. Upstream Boundary

The immediate upstream architecture is ADP-001C — Provider → Instrument Contract. The upstream input must be architecturally admissible Provider-owned information carrying Provider meaning, Provider reference, Provider assertions, Provider Provenance, relevant Provider context, retained uncertainty and ambiguity, applicable scope limitations, applicable acquisition context and approved Instrument interpretation and universe context. ADP-001C Architectural Admissibility permits interpretation to begin. Interpretation Eligibility is a subsequent Instrument-owned internal readiness meaning for identifying applicable approved Instrument context, not a second authorization; missing context does not retroactively invalidate ADP-001C Architectural Admissibility.

EAP-003 may provide engineering representations of that boundary, but ADP-001C remains authoritative. Architecturally Inadmissible information shall not enter Instrument Interpretation.

## 10. Downstream Boundary

The immediate downstream architecture is ADP-001D — Instrument → Observation Contract. ADP-001J provides an Instrument Identity Contract that can identify the approved canonical Instrument subject for later attribution.

The Instrument Identity Contract shall not attribute facts, create factual market information, establish Observation Eligibility, establish Observation Acceptance, confer Observation ownership, create a Market Fact, prove factual correctness or authorize publication.

## 11. Architectural Responsibilities

Instrument shall:

- determine Interpretation Eligibility as an internal readiness meaning for the applicable approved Instrument context, without overriding or redefining ADP-001C;
- interpret eligible Provider information under approved Instrument architecture;
- identify the applicable identity layer;
- preserve Provider ownership and provenance;
- preserve approved universe context;
- evaluate semantic sufficiency;
- distinguish identity reuse from new identity establishment;
- preserve ambiguity, conflict and insufficiency;
- establish one permitted Interpretation Outcome from the determinate or indeterminate taxonomy;
- allow only determinate outcomes to continue toward Existing Identity Reuse or a Canonical Identity Establishment Decision;
- establish canonical identity only where sufficiently supported and only after the applicable establishment decision;
- preserve Canonical Identity Not Established as a later decision result when new identity conditions are not positively satisfied;
- evaluate Identity Publication Eligibility only after a determinate outcome and applicable identity decision;
- preserve historical identity continuity;
- publish approved Instrument meaning through an Instrument Identity Contract only after Identity Publication Eligibility; and
- terminate before factual attribution.

## 12. Architectural Non-Responsibilities

Instrument shall not acquire Provider ownership, reinterpret Provider availability as identity, perform Provider acquisition, repair Provider information, resolve ambiguity through implementation convenience, construct Observations, judge factual correctness, assign Market Schedule, perform Validation, or authorize trading or execution.

Provider retains responsibility for Provider records, identifiers, assertions, context, provenance, availability, capability and Provider Mapping State.

Mapping remains the Instrument-owned governed association between a Provider reference and an Instrument identity. ADP-001J may define only the minimum relationship between interpretation and mapping required to avoid ownership or sequence ambiguity; it shall not define mapping mechanics, storage, reconciliation or effective-time implementation.

Lifecycle remains Instrument-owned. ADP-001J may consume approved lifecycle context only where necessary to preserve identity continuity; it shall not define transition criteria, state machines or operational processing.

Observation begins only after approved Instrument meaning is available through the downstream boundary.

## 13. Architectural Principles

### AP-J-001 — Instrument assigns Instrument meaning

Provider information may support interpretation. Only Instrument may assign Instrument meaning.

### AP-J-002 — Interpretation requires admissibility

Instrument Interpretation shall begin only after the approved Provider-to-Instrument Architectural Admissibility boundary has been satisfied.

### AP-J-003 — Provider meaning survives interpretation

Instrument Interpretation shall preserve Provider meaning, origin and provenance without transferring Provider ownership.

### AP-J-004 — Identity requires semantic sufficiency

Canonical Instrument Identity shall be established only through sufficient approved Instrument meaning, never merely through availability, symbol presence, token presence, connectivity or data receipt.

### AP-J-005 — Existing identity continuity precedes new identity establishment

An existing canonical identity shall be reused when approved semantic continuity is established. Provider-reference change alone shall not create a new identity.

### AP-J-006 — No forced determination

Instrument Interpretation may legitimately produce no determination, ambiguity, conflict, insufficiency or unsupported context.

### AP-J-007 — Ambiguity remains explicit

Instrument Interpretation shall not silently choose one identity while materially plausible alternatives remain unresolved.

### AP-J-008 — Identity layers remain separate

Economic Instrument, Listed Instrument and Derivative Contract shall remain distinct Instrument-owned identity layers.

### AP-J-009 — Identity is not factual acceptance

Canonical Identity Establishment shall not imply Observation Acceptance, factual correctness or Market Fact ownership.

### AP-J-010 — Publication is governed

Instrument Identity publication shall occur only through the approved Instrument Identity Contract and shall not transfer Instrument ownership.

## 14. Architectural Invariants

1. **Instrument Interpretation shall have one semantic owner: Instrument.**
2. **Canonical Instrument Identity shall have one semantic owner: Instrument.**
3. **Provider records and Provider meaning shall remain owned by Provider throughout interpretation.**
4. **Engineering or architectural representation shall not transfer semantic ownership.**
5. **Architectural Admissibility shall permit Instrument Interpretation to begin but shall not imply successful Instrument Interpretation.**
6. **Interpretation Eligibility shall be an Instrument-owned internal readiness meaning for approved Instrument context, shall not override or redefine Architectural Admissibility, and missing Instrument context shall not retroactively invalidate Architectural Admissibility.**
7. **Provider Submission Eligibility shall not establish Instrument Identity.**
8. **Provider availability shall not establish Instrument Identity.**
9. **Physical receipt shall not establish Instrument Identity.**
10. **A Provider token shall never become a permanent KRONOS identity.**
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
21. **No Determination shall not mean Instrument non-existence.**
22. **A new canonical identity shall require positive semantic sufficiency.**
23. **An existing identity shall be reused when approved semantic continuity is established.**
24. **Provider Provenance shall remain preserved.**
25. **Approved universe context shall remain preserved.**
26. **Applicable identity-layer context shall remain preserved.**
27. **Instrument Interpretation shall not create Provider meaning.**
28. **Instrument Interpretation shall not create Observation, Market, Validation, Risk, Execution, Portfolio, Event or Audit meaning.**
29. **Instrument Interpretation shall not perform Provider acquisition.**
30. **ADP-001J shall not define mapping-effective-time mechanics unless separately authorized.**
31. **ADP-001J shall not define lifecycle transitions unless separately authorized.**
32. **The Instrument Identity Contract shall not contain raw Provider payloads.**
33. **Sensitive information shall not enter Instrument Interpretation or Instrument Identity contracts.**
34. **Historical identity shall survive Provider-reference change and lifecycle change where canonical architecture requires continuity.**
35. **ADP-001J shall remain provider-neutral and implementation-neutral and shall not authorize an EAP, EDD, implementation or code.**

## 15. Architectural Terminology

| Term | Architectural definition |
| --- | --- |
| Instrument Interpretation | Instrument-owned architectural activity that evaluates eligible Provider meaning and approved Instrument context without transferring Provider ownership. |
| Interpretation Eligibility | Instrument-owned internal readiness meaning used only to identify the applicable approved Instrument context after ADP-001C Architectural Admissibility permits interpretation to begin. It is not a second authorization, shall not override or redefine ADP-001C, and missing Instrument context shall not retroactively invalidate Architectural Admissibility. |
| Interpretation Activity | The conceptual Instrument-owned activity of interpreting eligible information; no runtime mechanics are defined. |
| Interpretation Outcome | Exactly one determinate or indeterminate outcome of interpretation. Determinate outcomes are Existing Identity Determined and New Identity Establishment Eligible. Indeterminate outcomes are No Determination, Ambiguous Determination, Conflicting Determination, Insufficient Semantic Information and Unsupported Identity Context. |
| Successful Determination | A collective architectural description of Existing Identity Determined and New Identity Establishment Eligible only; it is not an independent Interpretation Outcome and does not imply correctness or acceptance. |
| Existing Identity Determined | Determinate outcome that an existing canonical identity is established for the bounded context. |
| Existing Identity Reuse | Establishment that an existing canonical identity satisfies approved semantic continuity conditions. |
| New Identity Establishment Eligible | Determinate outcome that positive semantic sufficiency may permit a Canonical Identity Establishment Decision. |
| New Canonical Identity Establishment | Instrument-owned decision establishing a new canonical identity where sufficient approved meaning exists. |
| No Determination | Outcome in which no identity determination is established; it does not mean non-existence. |
| Ambiguous Determination | Outcome in which materially plausible alternatives remain explicit and unresolved. |
| Conflicting Determination | Outcome in which identity meanings conflict and no single determination is established. |
| Insufficient Semantic Information | Outcome in which required meaning is absent or indistinguishable. |
| Unsupported Identity Context | Outcome in which the approved identity context is not supported for determination. |
| Identity Layer | One of the distinct Instrument-owned layers: Economic Instrument, Listed Instrument or Derivative Contract. |
| Economic Instrument | Instrument-owned identity layer representing the economic subject. |
| Listed Instrument | Instrument-owned identity layer representing an approved listing and venue context. |
| Derivative Contract | Instrument-owned identity layer representing an individual derivative contract. |
| Semantic Sufficiency | Presence of sufficient approved Instrument meaning for the bounded determination. |
| Identity Continuity | Preservation of an existing identity across approved Provider-reference or lifecycle change where canonical architecture requires it. |
| Canonical Identity Establishment | Instrument-owned establishment of an approved canonical identity after a determinate outcome and applicable decision. |
| Canonical Identity Establishment Eligibility | Instrument-owned condition, evaluated only after New Identity Establishment Eligible, that a new canonical identity decision may be considered. |
| Canonical Identity Establishment Decision | Instrument-owned decision, available only after New Identity Establishment Eligible and Canonical Identity Establishment evaluation, establishing either Canonical Identity Established or Canonical Identity Not Established. Canonical Identity Not Established preserves the applicable reason, establishes no canonical identity, produces no Instrument Identity Contract, does not imply Instrument non-existence, does not become No Determination retroactively and does not alter Provider meaning. |
| Identity Publication Eligibility | Instrument-owned condition, evaluated only after a determinate outcome and applicable identity decision, that approved Instrument meaning may be presented through the Instrument Identity Contract. |
| Identity Indeterminacy | Collective architectural meaning for No Determination, Ambiguous Determination, Conflicting Determination, Insufficient Semantic Information and Unsupported Identity Context. An indeterminate outcome shall not produce an Instrument Identity Contract. |
| Economic Instrument Semantic Sufficiency | Conceptual minimum semantic categories for an Economic Instrument determination: approved economic subject; approved instrument class; approved universe-membership context; semantic distinction from existing Economic Instruments; applicable identity continuity meaning; required provenance; absence of unresolved ambiguity; and absence of unresolved conflict. These are semantic categories only, not fields, formats, parsing, matching, thresholds, algorithms or implementation. |
| Listed Instrument Semantic Sufficiency | Conceptual minimum semantic categories for a Listed Instrument determination: one approved Economic Instrument association; approved venue or listing context; semantic distinction from other Listed Instruments; applicable identity-layer and continuity context; approved role context where applicable; required provenance; absence of unresolved ambiguity; and absence of unresolved conflict. These are semantic categories only, not fields, formats, parsing, matching, thresholds, algorithms or implementation. |
| Derivative Contract Semantic Sufficiency | Conceptual minimum semantic categories for a Derivative Contract determination: one approved Listed Instrument association; approved underlying relationship; contract category; contract-expiry identity meaning; semantic distinction from every other expiry; approved universe and role context; required provenance; absence of unresolved ambiguity; and absence of unresolved conflict. These are semantic categories only, not fields, formats, parsing, matching, thresholds, algorithms or implementation. |
| Canonical Identity Not Established | Instrument-owned decision result after New Identity Establishment Eligible and Canonical Identity Establishment evaluation in which the conditions required to establish a new canonical identity were not positively satisfied. It preserves the applicable reason, establishes no canonical identity, produces no Instrument Identity Contract, does not imply Instrument non-existence, does not become No Determination retroactively and does not alter Provider meaning. It is not an Interpretation Outcome. |
| Instrument Identity Contract | Governed Instrument-owned semantic contract publishing approved canonical Instrument meaning for downstream use. |
| Provider Instrument Reference | Provider-owned reference to an instrument, external and non-canonical. |
| Provider Meaning | Provider-owned assertions and context preserved without becoming Instrument meaning. |
| Instrument Meaning | Instrument-owned interpretation and identity meaning. |
| Historical Identity | Canonical identity continuity preserved across historical reference or lifecycle change. |
| Provider Mapping | Instrument-owned governed association between a Provider reference and an Instrument identity. |
| Lifecycle Context | Approved context relevant to identity continuity; lifecycle transitions remain outside this Draft. |

Semantic sufficiency is evaluated separately for each identity layer at the architectural level. Failure to establish any required semantic category produces an Indeterminate Outcome. Sufficiency shall never be satisfied through inference, Provider vocabulary, symbol presence, token presence, implementation convenience or price behaviour.

## 16. Architectural Contracts

### 16.1 Interpretation Input Contract

Carries architecturally admissible Provider-owned information and approved Instrument context into Instrument Interpretation. The applicable identity-layer evaluation shall preserve the conceptual semantic categories defined for Economic Instrument, Listed Instrument or Derivative Contract sufficiency, including required provenance and absence of unresolved ambiguity and conflict. These categories do not define fields, formats, parsing, matching, thresholds, algorithms or implementation.

### 16.2 Interpretation Eligibility Contract

Represents Instrument-owned internal readiness for the applicable approved Instrument context after ADP-001C Architectural Admissibility permits interpretation to begin. It is not a second authorization and shall not override or redefine ADP-001C.

### 16.3 Interpretation Outcome Contract

Represents exactly one Interpretation Outcome from the approved taxonomy: Existing Identity Determined or New Identity Establishment Eligible as determinate outcomes; or No Determination, Ambiguous Determination, Conflicting Determination, Insufficient Semantic Information or Unsupported Identity Context as indeterminate outcomes. An indeterminate outcome shall not produce an Instrument Identity Contract.

### 16.4 Existing Identity Reuse Contract

Represents that an already canonical Instrument identity satisfies approved semantic continuity conditions after Existing Identity Determined. It is available only for a determinate outcome.

### 16.5 New Identity Establishment Contract

Represents the bounded Instrument-owned Canonical Identity Establishment Decision available after New Identity Establishment Eligible and the applicable conceptual semantic sufficiency evaluation. The decision may result in Canonical Identity Established or Canonical Identity Not Established. Failure to establish any required semantic category prevents positive establishment and preserves the applicable reason.

### 16.6 Identity Indeterminacy Contract

Represents No Determination, Ambiguous Determination, Conflicting Determination, Insufficient Semantic Information or Unsupported Identity Context without forcing identity creation. It records Identity Indeterminacy and shall not produce an Instrument Identity Contract.

### 16.7 Canonical Identity Establishment Eligibility Contract

Represents the Instrument-owned condition, available only after New Identity Establishment Eligible, that a Canonical Identity Establishment Decision may be considered.

### 16.8 Canonical Identity Establishment Decision Contract

Represents the Instrument-owned decision establishing whether a new canonical identity is established after New Identity Establishment Eligible and applicable establishment evaluation. A Canonical Identity Not Established result preserves the applicable reason, establishes no canonical identity, produces no Instrument Identity Contract, does not imply Instrument non-existence, does not become No Determination retroactively and does not alter Provider meaning.

### 16.9 Identity Publication Eligibility Contract

Represents the Instrument-owned condition, available only after a determinate outcome and applicable identity decision, that approved Instrument meaning may be presented through the Instrument Identity Contract.

### 16.10 Provenance Preservation Contract

Preserves Provider origin, Provider assertions and applicable Acquisition Provenance.

### 16.11 Identity Continuity Contract

Preserves existing and historical identity across Provider-reference change without defining lifecycle processing.

### 16.12 Instrument Identity Contract

Publishes approved canonical Instrument meaning only after a determinate outcome, an applicable identity decision that is not Canonical Identity Not Established, and Identity Publication Eligibility, including identity layer, canonical identity meaning, approved classification and relationships where already established, approved universe context, relevant historical or effective context where architecture requires it, and traceable provenance association without Provider ownership transfer.

### 16.13 Downstream Eligibility Contract

Represents only that approved canonical Instrument meaning may be presented to the ADP-001D attribution boundary.

No contract above is an API, payload, schema, runtime object or implementation interface.

## 17. Resolved Architecture Decisions

- Instrument is the exclusive semantic owner of Instrument Interpretation, Canonical Identity Establishment and the Instrument Identity Contract.
- Provider retains ownership of Provider records, identifiers, assertions, meaning and provenance.
- Economic Instrument, Listed Instrument and Derivative Contract remain distinct identity layers.
- ADP-001C Architectural Admissibility permits Interpretation to begin. Interpretation Eligibility is Instrument-owned internal readiness for the applicable approved Instrument context, not a second authorization, and missing context does not retroactively invalidate Admissibility.
- Existing identity reuse is distinct from new identity establishment.
- Interpretation Outcome branches into determinate outcomes (Existing Identity Determined and New Identity Establishment Eligible) and indeterminate outcomes (No Determination, Ambiguous Determination, Conflicting Determination, Insufficient Semantic Information and Unsupported Identity Context). Only determinate outcomes may continue toward Existing Identity Reuse or a Canonical Identity Establishment Decision, followed by Identity Publication Eligibility.
- Successful Determination is a collective description of the two determinate outcomes and is not an independent outcome.
- Ambiguity, conflict, insufficiency, unsupported context and no determination remain legitimate indeterminate outcomes and shall not produce an Instrument Identity Contract.
- Canonical Identity Not Established is a possible result of the later Canonical Identity Establishment Decision, not an Interpretation Outcome; it preserves the applicable reason, establishes no canonical identity, produces no Instrument Identity Contract, does not imply Instrument non-existence, does not become No Determination retroactively and does not alter Provider meaning.
- ADP-001J terminates before ADP-001D factual attribution.

## 18. Unresolved Architecture Decisions

The following matters remain unresolved and are not decided by this Draft:

- exact identity-defining attributes for each identity layer;
- detailed mapping-effective-time rules;
- detailed lifecycle-transition behaviour;
- provider-token reuse treatment in each future context;
- continuous-futures identity treatment;
- physical identifier format;
- storage or persistence representation; and
- any Provider-to-Instrument communication mechanism.

These matters require separate approved architecture where applicable.

## 19. Architecture Risks

- Provider meaning may be mistaken for Instrument meaning.
- Admissibility or Interpretation Eligibility may be mistaken for identity determination.
- Ambiguity or conflict may be silently forced into one identity.
- Provider-reference changes may incorrectly create new identity.
- Mapping or lifecycle responsibilities may be absorbed into interpretation.
- Instrument Identity Contract may be treated as factual acceptance or Observation authority.
- Downstream attribution may begin before approved Instrument meaning is available.

These are architectural risks, not implementation instructions.

## 20. Architecture Review Questions

### 1. What is Instrument Interpretation?

Instrument Interpretation is the Instrument-owned architectural activity that evaluates architecturally admissible Provider-owned information and approved Instrument context to establish one permitted Interpretation Outcome without transferring Provider ownership.

### 2. Who owns Instrument Interpretation?

Instrument exclusively owns Instrument Interpretation.

### 3. What architectural conditions establish Interpretation Eligibility?

ADP-001C Architectural Admissibility permits Instrument Interpretation to begin. Interpretation Eligibility is an Instrument-owned internal readiness meaning used only to identify the applicable approved Instrument context, including preserved provenance, approved universe and identity-layer context, and required semantic information distinguishable within its bounded context. It is not a second authorization.

### 4. How is Interpretation Eligibility kept distinct from Architectural Admissibility?

Architectural Admissibility is the ADP-001C determination permitting Instrument Interpretation to begin. Interpretation Eligibility is the Instrument-owned internal readiness meaning after that boundary used only to identify the applicable approved Instrument context. It shall not override or redefine ADP-001C, and missing Instrument context shall not retroactively invalidate Architectural Admissibility. Neither implies a successful determination.

### 5. What begins Instrument Interpretation?

Instrument Interpretation begins when the approved ADP-001C Architectural Admissibility boundary has been satisfied. Interpretation Eligibility may then identify the applicable approved Instrument context, but it is not an additional authorization and shall not override or redefine ADP-001C.

### 6. What ends Instrument Interpretation?

It ends after one Interpretation Outcome. Only a determinate outcome may continue toward Existing Identity Reuse or a Canonical Identity Establishment Decision and then Identity Publication Eligibility; the Instrument Identity Contract is presented to ADP-001D only after those boundaries.

### 7. What Provider-owned information may support interpretation?

Provider records, Provider identifiers, Provider assertions, Provider Meaning, Provider Provenance, supplied Acquisition Provenance, Provider context, scope limitations, uncertainty, ambiguity and approved universe context may support interpretation.

### 8. What Provider-owned information is prohibited from becoming Instrument meaning?

Provider ownership, raw Provider payloads, Provider availability, Provider tokens, Provider assertions as canonical meaning, and any Provider information not established as Instrument-owned meaning shall not become Instrument meaning.

### 9. What approved Instrument-owned context is required?

Approved identity-layer context, approved universe context, applicable semantic context, identity continuity context and any approved lifecycle or effective context required by canonical architecture are required. Conceptual semantic sufficiency is separate for each layer. Economic Instrument requires an approved economic subject, approved instrument class, approved universe-membership context, semantic distinction from existing Economic Instruments, applicable identity continuity meaning, required provenance, absence of unresolved ambiguity and absence of unresolved conflict. Listed Instrument requires one approved Economic Instrument association, approved venue or listing context, semantic distinction from other Listed Instruments, applicable identity-layer and continuity context, approved role context where applicable, required provenance, absence of unresolved ambiguity and absence of unresolved conflict. Derivative Contract requires one approved Listed Instrument association, approved underlying relationship, contract category, contract-expiry identity meaning, semantic distinction from every other expiry, approved universe and role context, required provenance, absence of unresolved ambiguity and absence of unresolved conflict. These remain conceptual semantic categories only, not fields, formats, parsing, matching, thresholds, algorithms or implementation. Failure to establish any required category produces an Indeterminate Outcome.

### 10. What Interpretation Outcomes are permitted?

The determinate outcomes are Existing Identity Determined and New Identity Establishment Eligible. The indeterminate outcomes are No Determination, Ambiguous Determination, Conflicting Determination, Insufficient Semantic Information and Unsupported Identity Context. Successful Determination is only a collective description of the two determinate outcomes and is not an independent Interpretation Outcome.

### 11. What constitutes a Successful Determination?

Successful Determination is a collective architectural description of Existing Identity Determined and New Identity Establishment Eligible. It is not an independent Interpretation Outcome, and does not imply correctness, acceptance or validation.

### 12. What constitutes Existing Identity Reuse?

Existing Identity Reuse occurs only after the determinate outcome Existing Identity Determined establishes that approved semantic continuity makes an already canonical Instrument identity apply to the bounded interpretation context.

### 13. When must an existing canonical identity be reused?

An existing canonical identity shall be reused when approved semantic continuity is established. Provider-reference change alone shall not create a new identity.

### 14. What conditions may permit New Canonical Identity Establishment?

New Canonical Identity Establishment may be permitted only after the determinate outcome New Identity Establishment Eligible and positive semantic sufficiency for the applicable identity layer. Economic Instrument sufficiency requires an approved economic subject, approved instrument class, approved universe-membership context, semantic distinction from existing Economic Instruments, applicable identity continuity meaning, required provenance, absence of unresolved ambiguity and absence of unresolved conflict. Listed Instrument sufficiency requires one approved Economic Instrument association, approved venue or listing context, semantic distinction from other Listed Instruments, applicable identity-layer and continuity context, approved role context where applicable, required provenance, absence of unresolved ambiguity and absence of unresolved conflict. Derivative Contract sufficiency requires one approved Listed Instrument association, approved underlying relationship, contract category, contract-expiry identity meaning, semantic distinction from every other expiry, approved universe and role context, required provenance, absence of unresolved ambiguity and absence of unresolved conflict. Failure to establish any required category produces an Indeterminate Outcome and shall never be satisfied through inference, Provider vocabulary, symbol presence, token presence, implementation convenience or price behaviour. The subsequent Canonical Identity Establishment Decision may result in Canonical Identity Not Established, which preserves the applicable reason, establishes no canonical identity, produces no Instrument Identity Contract, does not imply Instrument non-existence, does not become No Determination retroactively and does not alter Provider meaning.

### 15. Why does absence of an existing identity not by itself authorize new identity creation?

Absence proves neither non-existence nor semantic sufficiency. A new identity requires a positive approved determination, not merely a missing mapping or existing identity.

### 16. What constitutes No Determination?

No Determination is an outcome in which the available approved meaning does not establish an identity. It does not mean Instrument non-existence.

### 17. What constitutes Ambiguous Determination?

Ambiguous Determination is an outcome in which materially plausible identity alternatives remain unresolved and explicit.

### 18. What constitutes Conflicting Determination?

Conflicting Determination is an outcome in which identity meanings conflict and no single identity determination is established.

### 19. What constitutes Insufficient Semantic Information?

Insufficient Semantic Information is an indeterminate outcome in which any required semantic category for the bounded identity determination is absent or indistinguishable. It shall not produce an Instrument Identity Contract.

### 20. What constitutes Unsupported Identity Context?

Unsupported Identity Context is an indeterminate outcome in which the approved identity context is not supported for determination. It shall not produce an Instrument Identity Contract.

### 21. How are Economic Instrument, Listed Instrument and Derivative Contract determinations kept distinct?

They remain separate Instrument-owned identity-layer determinations. Meaning established at one layer shall not silently establish another layer. Failure to establish any required semantic category for the applicable layer produces an Indeterminate Outcome.

### 22. How are analysis, reference and execution roles kept distinct from identity layers?

Analysis, reference and execution roles remain separate architectural roles. They do not define or replace Economic Instrument, Listed Instrument or Derivative Contract identity layers.

### 23. How is Provider meaning preserved throughout interpretation?

Provider meaning, origin, assertions and provenance remain associated with the interpreted information and are not transferred, rewritten or converted into Provider-owned canonical identity.

### 24. How is Provider Provenance preserved without transferring ownership?

Provider Provenance remains associated as traceable provenance context while Instrument owns only the interpretation and identity meaning it establishes.

### 25. What relationship exists between Instrument Interpretation and Provider Mapping?

Mapping remains an Instrument-owned governed association between a Provider reference and an Instrument identity. ADP-001J defines only the minimum relationship required to avoid ownership or sequence ambiguity; mapping mechanics remain deferred.

### 26. What relationship exists between Instrument Interpretation and Instrument Lifecycle?

Lifecycle remains Instrument-owned. Interpretation may consume approved lifecycle context for continuity but does not define lifecycle transitions or processing.

### 27. What exactly is the Instrument Identity Contract?

It is the Instrument-owned governed contract publishing approved canonical Instrument meaning, identity-layer context, approved relationships and traceable provenance association for later downstream use only after a determinate Interpretation Outcome, an applicable Canonical Identity Establishment Decision that is not Canonical Identity Not Established, and Identity Publication Eligibility. Canonical Identity Not Established produces no Instrument Identity Contract.

### 28. What may the Instrument Identity Contract never establish?

It may never establish factual correctness, Observation Acceptance, Observation ownership, Market Facts, Validation, Risk, Execution, Portfolio, Event or Audit meaning, or authorize publication beyond approved architecture. An indeterminate Interpretation Outcome shall never produce it.

### 29. What downstream capability may consume the Instrument Identity Contract?

Only the approved ADP-001D Instrument-to-Observation attribution boundary may receive the downstream-eligible Instrument Identity Contract after Identity Publication Eligibility. ADP-001D remains outside this Draft.

### 30. What matters require separate architecture rather than resolution within ADP-001J?

Identity-defining attributes, detailed mapping and lifecycle mechanics, provider-token reuse, continuous-futures treatment, physical identifier format, persistence, Provider-to-Instrument communication, and any implementation or runtime behavior require separate approved architecture.

## 21. Architecture Review Criteria

The independent Chief Architect review shall verify:

1. Instrument exclusively owns interpretation and canonical identity.
2. Provider meaning remains Provider-owned.
3. ADP-001C admissibility is not duplicated or redefined.
4. Interpretation Eligibility remains distinct from Architectural Admissibility.
5. Interpretation Activity remains distinct from Interpretation Outcome.
6. Interpretation Outcome branches into the determinate and indeterminate taxonomies.
7. Successful Determination is only a collective description and not an independent outcome.
8. Only determinate outcomes may continue toward identity reuse or a Canonical Identity Establishment Decision.
9. Indeterminate outcomes do not produce an Instrument Identity Contract.
10. No Determination is legitimate and does not mean non-existence.
11. Ambiguity, conflict, insufficiency and unsupported context remain explicit.
12. Existing identity reuse is separated from new identity establishment.
13. New identity requires positive semantic sufficiency for the applicable identity layer.
14. Required semantic categories cannot be satisfied by inference, Provider vocabulary, symbol or token presence, implementation convenience or price behaviour.
15. Economic Instrument Semantic Sufficiency includes approved economic subject, approved instrument class, approved universe-membership context, distinction from existing Economic Instruments, continuity meaning, required provenance, and absence of unresolved ambiguity or conflict.
16. Listed Instrument Semantic Sufficiency includes one approved Economic Instrument association, approved venue or listing context, distinction from other Listed Instruments, identity-layer and continuity context, approved role context where applicable, required provenance, and absence of unresolved ambiguity or conflict.
17. Derivative Contract Semantic Sufficiency includes one approved Listed Instrument association, approved underlying relationship, contract category, contract-expiry identity meaning, distinction from every other expiry, approved universe and role context, required provenance, and absence of unresolved ambiguity or conflict.
18. Provider-reference change does not silently create a new identity.
19. Identity layers and roles remain distinct.
20. Mapping and lifecycle are not silently implemented inside interpretation.
21. Historical identity continuity is preserved.
22. The Instrument Identity Contract is semantically defined and contains no raw Provider payload.
23. Canonical Identity Not Established is not an Interpretation Outcome; it preserves the applicable reason, establishes no canonical identity, produces no Instrument Identity Contract, does not imply Instrument non-existence, does not become No Determination retroactively and does not alter Provider meaning.
24. The downstream boundary stops before factual attribution.
25. Observation, Market, Validation, Risk, Execution, Portfolio, Event and Audit meaning is not created.
26. The approved Instrument Universe is not expanded.
27. Options capability is not activated.
28. Provider neutrality and implementation neutrality are preserved.
29. No EAP, EDD, implementation, commit or push authority is introduced.

## 22. ADR Determination

**ADR Required: No**

No ADR is required to draft ADP-001J provided the Draft preserves Instrument ownership, Provider ownership, the existing ADP-001C and ADP-001D boundaries, creates no new domain or dependency, creates no generic platform identity-resolution framework, and does not reassign mapping or lifecycle responsibility.

An ADR becomes mandatory if the Draft proposes shared interpretation ownership, a new semantic owner, a new domain or dependency, an alternate Provider-to-Instrument route, a platform-wide identity-resolution service, reassignment of mapping or lifecycle responsibility, or modification of the Domain Dependency Matrix or Platform Constitution.

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
| Governing Architecture | ADP-001B |
| Upstream Boundary | ADP-001C |
| Downstream Boundary | ADP-001D |
| Supporting Architecture | ADP-001A, ADP-001E, ADP-001H, ADP-001I |
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

ADP-001J Version 0.1 was authorized for Draft preparation. CA-ADP001J-001 through CA-ADP001J-004 were applied. Draft Version 0.2 incorporated those amendments. CA-ADP001J-005 through CA-ADP001J-007 were applied in Draft Version 0.3. The Product Master Architect performed drafting and self-review. Independent review was performed by the Chief Architect. Product Master Architect Verification was completed. Final Chief Architect Review resulted in canonicalization approval.

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
- [ADP-001A — Swing Phase 1 Market Data Inventory](SWING-PHASE-1-MARKET-DATA-INVENTORY.md)
- [ADP-001B — Instrument Identity Architecture](SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md)
- [ADP-001C — Provider → Instrument Contract](SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md)
- [ADP-001D — Instrument → Observation Contract](SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md)
- [ADP-001E — Observation Domain Architecture](SWING-PHASE-1-OBSERVATION-DOMAIN-ARCHITECTURE.md)
- [ADP-001H — Provider Instrument Master Acquisition Capability and Contract](SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md)
- [ADP-001I — Approved Instrument Universe and Reference Semantics Architecture](SWING-PHASE-1-APPROVED-INSTRUMENT-UNIVERSE-AND-REFERENCE-SEMANTICS-ARCHITECTURE.md)
- [EAP-003 Version 1.0](../../../engineering/eap/EAP-003-PROVIDER-TO-INSTRUMENT-ARCHITECTURAL-ADMISSIBILITY.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [KRONOS Engine Ownership](../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../DATA_FLOW.md)
