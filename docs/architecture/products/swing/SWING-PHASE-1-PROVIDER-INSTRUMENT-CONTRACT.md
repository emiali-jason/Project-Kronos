# ADP-001C — Provider → Instrument Contract

**Status:** Approved

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Owner:** Chief Architect

**Prepared By:** Codex Engineering Team

**Approved By:** Chief Architect

**Classification:** Architecture Documentation Package

**Architecture Impact:** Approved canonical governed semantic boundary between Provider and Instrument

**Engineering Impact:** None

**Runtime Impact:** None

## 1. Status and Governance

This document is the approved canonical Version 1.0 Architecture Documentation Package. It does not authorize implementation, retrieval, runtime Provider-to-Instrument communication, an interface, an Engineering Design Document, an Engineering Package, or any runtime change.

The following labels govern this document:

- **Approved base** identifies architecture already approved in ADP-001A, ADP-001B, or another approved repository document.
- **Approved principle** identifies normative wording approved through ADP-001C.
- **Unresolved** identifies a matter this document does not decide.

ADP-001B authorized ADP-001C as architecture documentation. The Chief Architect approved the governed semantic boundary, and the Engineering Architect authorized canonicalization. ADP-001C is canonical Version 1.0.

## 2. Purpose

Define the governed architectural contract through which Provider-supplied instrument reference information becomes eligible for interpretation by the Instrument domain.

ADP-001C defines an architectural boundary. It does not define physical delivery, a runtime contract, a transport contract, an API, a payload, a schema, an adapter, or an implementation.

## 3. Architectural Problem

Provider owns external Provider Instrument References, Provider identifiers, Provider records, Provider metadata, Provider provenance, Provider availability, and Provider meaning. Instrument exclusively owns Instrument Identity and Instrument meaning.

KRONOS therefore requires an explicit architectural boundary that permits Provider information to become eligible for Instrument interpretation without:

- treating physical movement as semantic acceptance;
- transferring ownership or semantic authority;
- allowing Provider meaning to become Instrument meaning automatically;
- creating canonical identity at the boundary; or
- concealing partiality, failure, unavailability, uncertainty, or ambiguity.

Without this boundary, implementation could silently collapse Provider Integration into Instrument Identity or allow raw availability to be mistaken for canonical meaning.

## 4. Scope

This document covers only:

- the Provider → Instrument governed semantic boundary;
- the distinction between physical movement, architectural admissibility, and semantic interpretation;
- exclusive Provider and Instrument ownership;
- architectural preconditions for Instrument interpretation;
- information eligibility and admissibility;
- provenance, attribution, uncertainty, and ambiguity preservation;
- normative contract responsibilities and invariants;
- explicit prohibitions; and
- conformance with ADP-001A and ADP-001B.

The boundary applies only to Provider-supplied instrument reference information that is within approved Phase 1 architecture. It does not expand the approved instrument universe, dataset inventory, product scope, Provider capability, or Instrument responsibility.

## 5. Out of Scope

This document does not define or authorize:

- APIs, implementation interfaces, JSON, serialization, schemas, fields, or payloads;
- REST, RPC, queues, events, polling, streaming, or any transport;
- adapters, synchronization, retries, caching, persistence, repositories, or database models;
- runtime validation, runtime orchestration, Provider retrieval, or Provider capability;
- canonicalization, mapping, matching, identity-resolution, enrichment, or repair algorithms;
- implementation classes, modules, tests, migrations, or configuration;
- thresholds, fallback logic, error-handling procedures, or operational state machines;
- Market Facts, observations, Market Schedule, Validation judgment, ranking, execution, orders, positions, or automated trading;
- Options capability, TradingView integration, or any expansion of approved Swing scope;
- an ADR, an EDD, an Engineering Package, or implementation sequence; or
- ADP-001D or any subsequent capability document.

## 6. Terminology

| Term | Architectural meaning in this document |
| --- | --- |
| Provider Information | Provider-owned information supplied from the Provider domain, retaining Provider meaning and provenance. |
| Provider Meaning | The semantic meaning owned by Provider for Provider Instrument References, identifiers, records, metadata, provenance, capability, availability, and related Provider context. |
| Instrument Meaning | The semantic meaning exclusively assigned by Instrument for canonical identity, classification, lifecycle, relationships, mappings, interpretation, and identity invariants. |
| Semantic Authority | The exclusive architectural authority of an owning domain to assign and govern its owned meaning. Crossing a domain boundary does not transfer this authority. |
| Governed Semantic Boundary | The architectural boundary that establishes conditions under which Provider Information becomes eligible for Instrument interpretation without changing ownership or meaning. |
| Physical Movement | Information crossing a domain boundary by any mechanism. Physical movement has no architectural-admissibility or semantic effect. |
| Architectural Admissibility | Satisfaction of approved architectural preconditions that permits Instrument interpretation to begin. It does not imply correctness, identity, acceptance, or validation. |
| Interpretation | Consideration of eligible Provider Information by Instrument for the possible assignment of Instrument meaning under approved Instrument architecture. Eligibility permits interpretation to begin but does not determine its result. |
| Eligible for Interpretation | Architecturally admissible for Instrument to consider. Eligibility does not prove correctness, completeness, identity, mapping, lifecycle status, acceptance, or validation. |
| Provenance | Preserved Provider origin and source context associated with Provider Information. |
| Attribution | The ability to associate Provider Information with its Provider source and relevant Provider context without assigning Instrument meaning. |
| Uncertainty | Provider Information whose limits or incompleteness remain explicit rather than being silently removed. |
| Ambiguity | Provider Information that permits more than one possible interpretation or does not support one determinate interpretation. |

Terminology in this document defines no runtime type, contract field, payload, or implementation representation.

## 7. Governing Principle

**Approved governing principle:**

> Provider-supplied information carries Provider meaning only. Crossing the Provider → Instrument architectural boundary does not alter its semantic meaning or ownership. The approved Provider → Instrument Contract establishes only the governed conditions under which Provider information becomes eligible for interpretation by the Instrument domain. Only the Instrument domain may assign Instrument meaning.

This principle is normative and authoritative within the ADP-001C product architecture boundary.

## 8. Nature of the Governed Semantic Boundary

A Provider → Instrument Contract is a **governed semantic boundary**.

A governed contract shall govern only whether Provider Information is architecturally eligible for Instrument interpretation. A governed contract shall never carry out interpretation, validate information, create identity, or prescribe how information moves.

Crossing the governed boundary shall never:

- change Provider Information into Instrument Information;
- make a Provider Instrument Reference canonical;
- transfer responsibility from Provider to Instrument or from Instrument to Provider;
- establish that an identity or mapping exists;
- establish lifecycle status; or
- establish that the information is correct, complete, accepted, validated, or suitable for any runtime use.

Information remains Provider-owned and retains Provider meaning while the Instrument domain considers it. Instrument meaning exists only when assigned by Instrument under separately approved Instrument architecture.

## 9. Physical Movement, Architectural Admissibility, and Semantic Interpretation

The following concepts are separate:

| Concept | Architectural treatment |
| --- | --- |
| Physical movement of data | The Provider runtime may physically move information. ADP-001C defines no mechanism and grants movement no semantic effect. |
| Architectural admissibility | ADP-001C governs the conditions under which Provider Information may become eligible for Instrument interpretation. |
| Semantic interpretation | Only Instrument may assign Instrument meaning. ADP-001C does not perform or define the interpretation. |

Physical movement does not establish admissibility. Architectural admissibility permits interpretation to begin; it shall never imply correctness, identity, acceptance, or validation. Interpretation shall never retroactively alter Provider provenance or Provider meaning.

## 10. Provider Ownership

Provider exclusively owns:

- Provider Instrument References;
- Provider identifiers;
- Provider records;
- Provider metadata;
- Provider provenance;
- Provider availability;
- Provider meaning; and
- the Provider-specific context required to understand those Provider-owned meanings.

Provider shall preserve its owned meaning through the boundary. Provider shall never assign canonical identity, classification, Instrument lifecycle, mapping semantics, or any other Instrument meaning.

Provider ownership does not make Provider Information a Market Fact, Market Schedule, Validation judgment, or approved Instrument identity.

## 11. Instrument Ownership

Instrument exclusively owns:

- canonical identities;
- Economic Instrument identity;
- Listed Instrument identity;
- Derivative Contract identity;
- classification;
- lifecycle semantics;
- mapping semantics;
- interpretation;
- identity invariants; and
- Instrument meaning.

Only Instrument may assign these meanings. Instrument shall never acquire ownership of Provider records, Provider identifiers, Provider provenance, Provider availability, or Provider meaning merely because Provider Information becomes eligible for interpretation.

No shared ownership is introduced.

## 12. Contract Boundary

The proposed contract boundary begins with Provider-owned information carrying Provider meaning and ends with a determination of architectural eligibility for Instrument interpretation.

The boundary does not include:

- Instrument interpretation itself;
- the creation or selection of an Instrument identity;
- mapping creation or selection;
- classification or lifecycle assignment;
- correction, enrichment, repair, or normalization of Provider meaning;
- publication of an Instrument Identity Contract; or
- physical delivery and operational handling.

A governed contract shall preserve the ownership boundary in both directions. Provider shall never acquire Instrument authority through the governed contract, and Instrument shall never acquire Provider authority through the governed contract.

## 13. Architectural Preconditions for Interpretation

Before Instrument is permitted to begin interpretation, architectural admissibility shall be established only when the relevant Provider Information is:

- attributable to its Provider source and relevant Provider context;
- provenance-preserving;
- syntactically complete where completeness is required by approved architecture;
- distinguishable from a partial Provider response;
- distinguishable from a failed Provider response;
- distinguishable from unavailable Provider Information; and
- explicit about any retained uncertainty or ambiguity.

These are architectural preconditions only. A governed contract shall never treat them as identity acceptance or validation. They do not define fields, structures, checks, thresholds, algorithms, error handling, or runtime validation.

Satisfying these preconditions makes information eligible for interpretation to begin. Architectural admissibility shall never establish that the Provider Information is correct, that an Instrument identity exists, that a mapping is valid, that validation succeeded, or that Instrument accepted any proposed interpretation.

If a precondition cannot be established, the information is not architecturally eligible for Instrument interpretation under this document. This document defines no runtime disposition for such information.

## 14. Information Eligibility and Admissibility

Architectural admissibility permits Instrument interpretation to begin and nothing more. It shall never imply correctness, identity, acceptance, or validation.

Architectural admissibility shall never be represented as:

- canonical identity;
- identity acceptance;
- successful mapping;
- classification;
- lifecycle state;
- correctness;
- completeness beyond the stated Provider context;
- validation success;
- Market Fact acceptance; or
- fitness for research, trading, execution, or any business decision.

Architectural admissibility shall preserve the distinction between complete, partial, failed, unavailable, uncertain, and ambiguous Provider Information where those distinctions exist. ADP-001C does not define a runtime status model or the representation of those distinctions.

## 15. Contract Responsibilities

A governed contract shall:

1. identify Provider as the owner of supplied Provider Information and Provider meaning;
2. identify Instrument as the sole owner of Instrument interpretation and Instrument meaning;
3. establish the governed conditions for architectural admissibility;
4. preserve Provider provenance and attribution;
5. preserve retained uncertainty and ambiguity;
6. keep partial, failed, and unavailable Provider Information distinguishable where applicable;
7. prevent eligibility from being mistaken for canonical identity, validation, mapping, or acceptance;
8. preserve the separation between physical movement and semantic authority; and
9. prevent the contract boundary from becoming a second owner of either domain's meaning.

These responsibilities define architectural meaning only. They authorize no runtime contract or implementation.

## 16. Contract Invariants

The following invariants are normative for ADP-001C:

1. A governed contract shall never transfer ownership.
2. A governed contract shall never transfer semantic authority.
3. A governed contract shall never create canonical identity.
4. A governed contract shall never validate identity.
5. A governed contract shall never repair Provider data.
6. A governed contract shall never perform business interpretation.
7. A governed contract shall preserve provenance.
8. A governed contract shall preserve attribution.
9. A governed contract shall preserve uncertainty.
10. A governed contract shall never silently discard semantic ambiguity.

These invariants apply to the governed semantic boundary and do not define an implementation enforcement mechanism.

## 17. Permitted Responsibilities

Within this document, the architectural contract may:

- name the producing and interpreting domains;
- state exclusive semantic ownership;
- define architectural admissibility;
- identify the minimum conceptual preconditions for interpretation;
- require preservation of provenance, attribution, uncertainty, and ambiguity;
- distinguish eligibility from physical movement and Instrument interpretation; and
- prohibit semantic and ownership transfer.

Provider may supply Provider Information carrying Provider meaning. Instrument may begin interpretation only after architectural admissibility is established. Neither permission authorizes retrieval, runtime communication, canonicalization, mapping, or implementation.

## 18. Explicit Prohibitions

A governed contract shall never:

- resolve identity ambiguity;
- repair Provider inconsistencies;
- enrich Provider records;
- infer missing identity;
- classify instruments;
- correct Provider data;
- derive canonical identity;
- construct observations;
- perform validation;
- assign lifecycle state;
- select or create mappings;
- silently normalize away uncertainty;
- transfer Instrument responsibility to Provider;
- transfer Provider responsibility to Instrument;
- become a generic cross-domain framework;
- declare a reusable platform pattern;
- become a Provider retrieval design or Instrument processing design; or
- create an indirect path around an approved domain dependency.

## 19. Semantic Boundary Model

Figure 1 presents the conceptual semantic boundary model governed by ADP-001C. It shows Provider Meaning reaching the governed boundary, eligibility permitting Instrument interpretation to begin, and Instrument retaining exclusive authority to assign canonical meaning.

```text
Provider Domain
      │
      │  Provider Meaning
      ▼
────────────────────────
Governed Contract
────────────────────────
      │
      │  Eligibility Only
      ▼
Instrument Domain
      │
      │  Instrument Interpretation
      ▼
Canonical Identity
```

**Figure 1 — Conceptual Provider → Instrument semantic boundary model.**

This is a conceptual semantic boundary diagram. It is not an implementation, transport, sequence, processing, or runtime diagram. The downward layout does not define call direction, data flow technology, execution order, or synchronous behavior.

## 20. Provenance, Attribution, Uncertainty, and Ambiguity

Provider provenance and attribution shall remain associated conceptually with Provider Information throughout the governed boundary. A governed contract shall never erase the Provider origin or make a Provider claim appear to originate from Instrument.

Uncertainty and ambiguity shall remain explicit when present. A governed contract shall never:

- convert uncertainty into certainty;
- treat absence as a definitive identity claim;
- treat partiality as completeness;
- treat failure or unavailability as a lifecycle meaning;
- select one interpretation silently; or
- discard competing possible meanings.

ADP-001C does not define how provenance, attribution, uncertainty, or ambiguity is represented. It also does not define how Instrument may later interpret or resolve eligible information.

## 21. Architectural Philosophy

> Information crosses domains. Meaning does not.

Meaning shall be assigned only by the owning domain. This principle is normative for ADP-001C and applies to this product architecture boundary.

ADP-001C may establish an architectural precedent, but this document does not declare a reusable platform pattern, create a platform-wide principle, amend the Platform Constitution, or modify any existing platform principle.

## 22. Dependencies

ADP-001C depends on:

- ADP-001A for the approved Phase 1 inventory, classification boundaries, and read-only restrictions;
- ADP-001B for Instrument identity layers, Provider Instrument Reference boundaries, mapping ownership, lifecycle separation, and identity invariants;
- PLATFORM-000 for contract-based dependencies and single semantic ownership;
- DOMAIN-001 for Instrument ownership;
- DOMAIN-006 for Provider ownership;
- the Domain Ownership Matrix; and
- the Domain Dependency Matrix.

ADP-001C does not alter the Domain Dependency Matrix. Provider is a platform domain, and the contract supplies platform support without making Instrument dependent on another business domain or placing Provider in the business pipeline.

No runtime dependency, transport dependency, storage dependency, Provider-specific implementation dependency, or Engineering Package dependency is established.

## 23. Architectural Traceability

The approved architecture progresses as follows:

- **ADP-001A defines what KRONOS may know.**
- **ADP-001B defines what an Instrument is and owns.**
- **ADP-001C defines how Provider information becomes eligible for Instrument interpretation.**

ADP-001C shall conform to both ADP-001A and ADP-001B. It shall never restate them as new decisions, weaken their exclusions, expand their approved scope, or transfer their ownership assignments.

## 24. Conformance with ADP-001A

This document conforms to ADP-001A by:

- limiting the boundary to information within the approved Phase 1 inventory;
- preserving the distinction between Provider acquisition and canonical business meaning;
- keeping Instrument Master rows and Provider tokens non-canonical;
- preserving Provider provenance, source attribution, partiality, failure, unavailability, uncertainty, and ambiguity;
- preserving the separation of missing information from zero and of API success from dataset completeness;
- retaining Options, TradingView, judgment, ranking, execution, orders, positions, persistence, retries, scheduling, and streaming exclusions;
- creating no retrieval authority or implementation sequence; and
- preserving read-only Phase 1 scope.

ADP-001C does not amend ADP-001A classifications, datasets, completion criteria, or unresolved questions.

## 25. Conformance with ADP-001B

This document conforms to ADP-001B by:

- preserving Economic Instrument, Listed Instrument, and Derivative Contract as separate Instrument-owned identities;
- keeping Provider Instrument References external, non-canonical, and Provider-owned;
- preserving Instrument's exclusive ownership of classification, lifecycle semantics, mapping semantics, interpretation, identity invariants, and Instrument meaning;
- preserving Provider's ownership of Provider records, identifiers, metadata, provenance, availability, and Provider meaning;
- treating Provider mappings as potentially time-bounded without defining temporal fields or algorithms;
- preserving historical Provider mapping attribution;
- keeping Provider Mapping State separate from Instrument Lifecycle;
- creating no identity, mapping, classification, lifecycle state, or successor relationship; and
- defining no runtime Provider-to-Instrument communication.

ADP-001C elaborates only the governed semantic boundary authorized by ADP-001B. It does not amend ADP-001B.

## 26. Unresolved Architectural Questions

1. Which approved Phase 1 Provider reference-information categories fall within the initial architectural scope of this contract?
2. What minimum semantic provenance and attribution obligations apply to each approved information category?
3. Which architectural distinctions shall the contract preserve among complete, partial, failed, and unavailable Provider Information?
4. Which uncertainty and ambiguity distinctions are architecturally material for each approved information category?
5. Which facts establish the beginning and end of the effective context for potentially time-bounded Provider mapping information?
6. Shall approved admissibility obligations be uniform across Provider reference-information categories or defined per category?
7. How will this boundary relate to a future Instrument Identity Contract without duplicating Instrument-owned meaning?

Engineering shall not answer these questions through implementation or inference. No unresolved matter authorizes fields, schemas, runtime behavior, or a follow-on package.

## 27. Follow-on Architecture

This document does not select, number, create, or authorize a follow-on architecture package.

After ADP-001C review, the Chief Architect may separately determine whether an already identified dependency—such as an Instrument Identity Contract, Instrument Lifecycle architecture, Provider Instrument Reference Retrieval capability, Historical Observation Architecture, or Current Quote Architecture—is ready for architectural work.

This section creates no sequence, roadmap commitment, contract, ADR, EDD, Engineering Package, retrieval authority, or runtime authorization.

## 28. Approval Record

**Chief Architect Decision:** Approved

**Engineering Architect Verification:** Complete

**ADR Required:** No

**Canonical Status:** Version 1.0

**Implementation Authorization:** None

**Next Authorized Capability:** None assigned by this document

**Review History:** The Chief Architect approved ADP-001C after Engineering Architect review. The Engineering Architect authorized canonicalization, and repository metadata and indexes were updated for Version 1.0.

ADP-001A, ADP-001B, ADP-001C, and the approved Platform architecture retain authority within their respective scopes. Approval of ADP-001C does not independently authorize implementation.

## Related Approved Authority

- [ADP-001A — Swing Phase 1 Market Data Inventory](SWING-PHASE-1-MARKET-DATA-INVENTORY.md)
- [ADP-001B — KRONOS Swing Instrument Identity Architecture](SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md)
- [PLATFORM-000 — KRONOS Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [Instrument Domain](../../platform/domains/instrument/ARCHITECTURE.md)
- [Provider Domain](../../platform/domains/provider/ARCHITECTURE.md)
- [KRONOS Engine Ownership](../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../DATA_FLOW.md)
