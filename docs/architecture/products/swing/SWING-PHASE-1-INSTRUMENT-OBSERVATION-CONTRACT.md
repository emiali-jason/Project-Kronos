# ADP-001D — Instrument → Observation Contract

**Status:** Approved

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Owner:** Chief Architect

**Prepared By:** Codex Engineering Team

**Approved By:** Chief Architect

**Classification:** Architecture Documentation Package

**Architecture Impact:** Approved canonical governed attribution boundary between Instrument and Observation

**Engineering Impact:** None

**Runtime Impact:** None

## 1. Status and Governance

This document is the approved canonical Version 1.0 Architecture Documentation Package. It does not authorize implementation, factual-data acquisition, runtime Instrument-to-Observation communication, an interface, an Engineering Design Document, an Engineering Package, or any runtime change.

The following labels govern this document:

- **Approved base** identifies architecture already approved in ADP-001A, ADP-001B, ADP-001C, or another approved repository document.
- **Approved principle** identifies normative wording approved through ADP-001D.
- **Unresolved** identifies a matter this document does not decide.

The Chief Architect approved the governed attribution boundary, and the Engineering Architect authorized canonicalization. ADP-001D is canonical Version 1.0.

## 2. Purpose

Define the governed architectural conditions under which factual market information may be attributed to an approved canonical Instrument identity and therefore become eligible for Observation participation and possible Observation ownership.

ADP-001D defines a governed attribution boundary. It is not an Instrument architecture document, an Observation architecture document, a market-data model, a runtime contract, a transport contract, a schema, an API, or an implementation design.

## 3. Architectural Problem

Instrument owns the canonical semantic identity that answers **What is this?** Observation owns the factual market state that answers **What happened?**

Factual market information has no inherent Instrument identity. Instrument identity likewise does not become factual market state. KRONOS therefore requires an explicit architectural boundary that permits factual market information to be attributed to an approved canonical Instrument identity without:

- moving Instrument ownership into Observation;
- moving Observation ownership into Instrument;
- allowing factual state to create or redefine identity;
- allowing identity to transform into an Observation;
- treating attribution eligibility as factual correctness or Observation acceptance; or
- concealing attribution failure, uncertainty, ambiguity, or effective-context limitations.

### Central architectural question

> Under what governed architectural conditions may factual market information be attributed to an approved canonical Instrument identity and therefore become eligible for Observation participation and possible Observation ownership?

ADP-001D answers: factual market information may become eligible for Observation participation and possible Observation ownership only when an approved canonical Instrument identity is available for attribution and the governed preconditions for identity, provenance, source, temporal context, uncertainty, ambiguity, and effective identity context are satisfied. Eligibility establishes only that participation boundary; it does not create identity, create an Observation, prove factual correctness, perform validation, establish Observation acceptance, confer Observation ownership, authorize publication, or progress an Observation lifecycle.

## 4. Scope

This document covers only:

- the Instrument → Observation governed attribution boundary;
- the distinction between canonical Instrument identity and factual market information;
- exclusive Instrument and Observation ownership;
- architectural admissibility for attribution;
- preconditions for Observation eligibility;
- attribution requirements and attribution failure;
- provenance continuity and attribution continuity;
- preserved uncertainty and unresolved ambiguity;
- normative contract responsibilities and invariants;
- explicit prohibitions; and
- conformance with ADP-001A, ADP-001B, and ADP-001C.

The boundary applies only to approved Phase 1 factual market-information categories and approved canonical Instrument identity. It does not expand the approved dataset inventory, Instrument universe, product scope, Observation responsibility, or any domain dependency.

## 5. Out of Scope

This document does not define or authorize:

- Instrument architecture, Observation architecture, or a market-data model;
- APIs, implementation interfaces, JSON, serialization, schemas, fields, or payloads;
- REST, RPC, queues, events, polling, streaming, or any transport;
- adapters, synchronization, retries, caching, persistence, repositories, or database models;
- runtime behavior, runtime validation, runtime orchestration, or factual-data acquisition;
- candle, quote, OHLC, depth, or aggregation models;
- aggregation windows, timestamp formats, or market-session logic;
- identity-resolution, attribution, validation, normalization, enrichment, or correction algorithms;
- indicators, trends, business interpretation, strategy logic, scoring, ranking, or execution logic;
- implementation classes, modules, tests, migrations, or configuration;
- thresholds, fallback logic, error-handling procedures, or operational state machines;
- Options capability, TradingView integration, or any expansion of approved Swing scope;
- an ADR, an EDD, an Engineering Package, or implementation sequence; or
- ADP-001E or any subsequent capability document.

## 6. Terminology

| Term | Architectural meaning in this document |
| --- | --- |
| Canonical Instrument Identity | An Instrument-owned canonical semantic identity within the Economic Instrument, Listed Instrument, or Derivative Contract layer approved by ADP-001B. |
| Factual Market Information | A factual claim or state concerning a market or instrument before this boundary establishes eligibility for Observation participation and possible Observation ownership. It is not Instrument meaning and is not automatically an authoritative Market Fact. |
| Market Fact | Authoritative factual market state owned by Observation that answers what happened without assigning business meaning. Factual information does not become a Market Fact merely because it is available or eligible for consideration. |
| Attribution | The governed architectural association of factual market information with an approved canonical Instrument identity, identifying whose factual market state is being considered without transferring ownership. |
| Attribution Authority | Observation's exclusive architectural responsibility for the semantic meaning of factual attribution to an approved Instrument-owned identity, without altering, recreating, or acquiring that identity. |
| Architectural Admissibility | Satisfaction of approved architectural preconditions that permits factual market information to be considered for attribution. It does not imply correctness, identity, acceptance, validation, Observation ownership, or publication. |
| Observation Eligibility | The architectural condition in which factual market information is eligible for Observation participation and possible Observation ownership after governed attribution preconditions are satisfied. Eligibility does not create an Observation, establish acceptance, confer ownership, authorize publication, or progress an Observation lifecycle. |
| Observation Ownership | Observation's exclusive semantic ownership of authoritative factual market state and Market Facts. Eligibility does not itself confer this ownership on candidate information. |
| Provenance Continuity | Preservation of the factual information's source and origin meaning throughout attribution without transferring source ownership. |
| Attribution Continuity | Preservation of an explainable association between factual market information and the approved canonical Instrument identity across the applicable identity and factual context. |
| Uncertainty | A known limit on factual information or attribution that remains explicit rather than being converted into certainty. |
| Ambiguity | More than one possible attribution, or the absence of one determinate attribution, which remains unresolved and visible. |

Terminology in this document defines no runtime type, field, payload, data structure, or implementation representation.

## 7. Governing Principle

**Approved principle:**

> Facts do not possess identity. They are attributed to identity.

This principle means:

- Instrument identity shall never transform into an Observation;
- factual market information shall never create or redefine Instrument identity;
- a governed contract shall govern attribution only;
- approved canonical Instrument identity shall remain owned by Instrument;
- factual market state shall remain owned by Observation; and
- attribution shall never transfer ownership or semantic authority.

This principle is normative and authoritative within the ADP-001D product architecture boundary.

## 8. Domain Ownership

No shared ownership is introduced.

| Domain | Exclusive ownership relevant to ADP-001D | Business question |
| --- | --- | --- |
| Instrument | Canonical identity, Economic Instrument identity, Listed Instrument identity, Derivative Contract identity, identity semantics, classification, lifecycle, relationships, mapping semantics, and identity invariants. | What is this? |
| Observation | Factual market-state records, price, OHLC facts, volume, Open Interest, bid, ask, depth, quote timestamp, exchange-reported factual state, Observation provenance, and factual attribution where defined by approved architecture. | What happened? |

The governed attribution boundary shall never become a third semantic owner. Attribution shall relate approved identity to factual market information without merging their meanings.

## 9. Instrument Responsibilities

Within approved architecture, Instrument:

- owns and publishes canonical Instrument identity;
- preserves Economic Instrument, Listed Instrument, and Derivative Contract distinctions;
- owns identity classification, lifecycle semantics, relationships, mapping semantics, and identity invariants;
- determines Instrument meaning under approved Instrument architecture; and
- publishes approved Instrument meaning through the approved semantic dependency without transferring identity ownership or semantic authority to Observation.

Instrument shall never:

- create factual market state;
- construct an Observation;
- assign Observation meaning;
- own price, OHLC facts, volume, Open Interest, bid, ask, depth, quote timestamp, or exchange-reported factual state; or
- perform business interpretation merely because identity is used for attribution.

ADP-001D does not define the Instrument Identity Contract or how Instrument publishes identity.

## 10. Observation Responsibilities

Within approved architecture, Observation:

- owns authoritative factual market state and Market Facts;
- owns Observation provenance and factual attribution where approved;
- consumes approved canonical Instrument identity without recreating or reinterpreting it;
- answers what happened without answering what it means; and
- preserves the distinction between factual state, identity metadata, and derived interpretation.

Observation shall never:

- define what an Instrument is;
- create, repair, infer, classify, or redefine Instrument identity;
- acquire Instrument lifecycle, relationship, or mapping authority;
- interpret what market behavior means;
- determine whether market behavior is bullish or bearish;
- decide whether a trade should occur; or
- create Validation judgment, strategy meaning, Risk Approval, or execution authority.

Observation eligibility makes factual market information eligible for Observation participation only. It does not create an Observation, establish acceptance, confer ownership, authorize publication, or progress an Observation lifecycle. ADP-001D defines none of those capabilities.

## 11. Nature of the Governed Attribution Boundary

ADP-001D is a governed attribution boundary.

It governs attribution only. It does not govern identity creation, fact generation, Observation structure, business interpretation, validation, strategy, or execution.

The boundary relates:

1. an approved canonical Instrument identity carrying Instrument meaning; and
2. factual market information carrying its factual source, temporal context, provenance, uncertainty, and ambiguity.

A governed contract shall establish only whether the factual market information is architecturally eligible for attribution to the approved identity and therefore eligible for Observation participation and possible Observation ownership.

Instrument shall retain ownership of canonical identity and Instrument meaning. Observation shall retain ownership of factual market state and Market Facts. A governed contract shall define only attribution admissibility and shall never transfer either domain's semantic authority.

A governed contract shall never:

- turn identity into factual state;
- turn factual state into identity;
- create an Observation;
- establish factual correctness;
- perform validation or business interpretation;
- define a runtime path for either input; or
- transfer ownership or semantic authority.

The contract name identifies Observation's approved dependency on Instrument meaning. It does not mean that Instrument produces, transports, or owns factual market information.

## 12. Identity Versus Facts

Canonical Instrument identity and factual market information are separate semantic concepts:

| Concept | Owner | Architectural role |
| --- | --- | --- |
| Canonical Instrument identity | Instrument | Identifies what the factual state is about. |
| Factual market information | Not assigned Observation ownership merely by availability | Supplies a candidate factual claim or state for governed attribution. |
| Authoritative Market Fact | Observation | Represents what happened under Observation's approved ownership. |

Attribution identifies whose factual market state is being considered. It shall never:

- make the identity an Observation;
- make factual information part of Instrument identity;
- transfer identity ownership to Observation;
- transfer factual-state ownership to Instrument; or
- merge the semantic authority of the two domains.

## 13. Architectural Admissibility

Architectural admissibility permits governed attribution to be considered and nothing more.

Architectural admissibility shall never imply:

- factual correctness;
- canonical identity creation;
- identity acceptance;
- successful attribution;
- Observation acceptance;
- Observation ownership;
- Observation publication;
- validation success; or
- fitness for research, trading, strategy, or execution.

Physical availability, successful acquisition, data movement, or matching syntax shall never establish architectural admissibility by themselves.

## 14. Architectural Preconditions for Observation Eligibility

Before factual market information may become eligible for Observation participation and possible Observation ownership, architectural admissibility shall be established only when the information is:

- attributable to an approved canonical Instrument identity;
- provenance-preserving;
- source-attributable;
- temporally attributable;
- distinguishable from partial Provider information;
- distinguishable from failed Provider information;
- distinguishable from unavailable Provider information;
- distinguishable from ambiguous Provider information;
- distinguishable from Instrument identity metadata;
- distinguishable from derived interpretation;
- explicit about retained uncertainty;
- explicit about unresolved ambiguity; and
- consistent with the applicable effective identity context where approved architecture requires it.

These are architectural preconditions only. They define no fields, payloads, schemas, validation algorithms, timestamp formats, database structures, or implementation checks.

Satisfying the preconditions makes factual information eligible for governed attribution and Observation participation. It shall never create an Observation, establish factual correctness, perform validation, establish Observation acceptance, confer Observation ownership, authorize publication, or progress an Observation lifecycle.

If a precondition cannot be established, the factual information is not architecturally eligible for Observation participation or possible Observation ownership under this document. This document defines no runtime disposition for such information.

## 15. Attribution Requirements

Attribution shall identify whose factual market state is being considered by associating factual market information with an approved canonical Instrument identity.

Attribution shall preserve the separate meanings and owners of:

- the canonical Instrument identity;
- the factual market information;
- source provenance;
- temporal context;
- retained uncertainty; and
- unresolved ambiguity.

Attribution shall never:

- create identity;
- alter identity;
- repair identity;
- infer identity;
- redefine lifecycle;
- establish a Provider mapping;
- validate factual correctness;
- interpret market meaning; or
- create strategy meaning.

Attribution eligibility does not transfer Instrument ownership into Observation. It also does not confer Observation ownership on candidate factual information.

## 16. Attribution Failure and Preserved Uncertainty

Attribution failure exists architecturally whenever the governed attribution preconditions cannot be established. Failure may include absence of an approved identity, unresolved identity ambiguity, unavailable effective context, missing provenance, missing temporal attribution, or unresolved conflict.

A governed contract shall preserve attribution failure, retained uncertainty, and unresolved ambiguity as distinct architectural conditions. It shall never:

- conceal failure as successful attribution;
- convert uncertainty into certainty;
- select one ambiguous attribution silently;
- discard conflicting attribution possibilities;
- treat Provider unavailability as Instrument lifecycle meaning; or
- treat missing information as proof of market state.

ADP-001D does not define a failure status, error value, representation, workflow, repair process, or runtime response.

## 17. Contract Responsibilities

A governed attribution contract shall:

1. identify Instrument as the sole owner of canonical Instrument identity and Instrument meaning;
2. identify Observation as the sole owner of authoritative factual market state and Market Facts;
3. establish the architectural conditions for attribution admissibility;
4. require an approved canonical Instrument identity for attribution;
5. preserve provenance continuity and attribution continuity;
6. preserve temporal attribution where required by approved architecture;
7. preserve retained uncertainty and unresolved ambiguity;
8. keep identity metadata distinct from factual market information;
9. keep factual information distinct from derived interpretation;
10. keep attribution failure visible; and
11. prevent eligibility from being mistaken for factual correctness, Observation acceptance, Observation ownership, publication, or validation.

These responsibilities define architectural meaning only. They authorize no runtime contract or implementation.

## 18. Permitted Responsibilities

Within this document, the governed attribution contract may:

- name Instrument and Observation as the domains participating in the approved dependency;
- state their exclusive semantic ownership;
- define architectural admissibility for attribution;
- identify conceptual preconditions for Observation eligibility;
- require preservation of provenance, attribution, temporal context, uncertainty, and ambiguity;
- distinguish identity, factual information, and interpretation;
- preserve attribution failure as architecturally visible; and
- prohibit semantic and ownership transfer.

Instrument may publish approved canonical identity meaning without transferring identity ownership or semantic authority. Factual market information may be considered at the attribution boundary and may become eligible for Observation participation and possible Observation ownership. None of these permissions creates an Observation, establishes acceptance, confers ownership, authorizes publication, progresses an Observation lifecycle, or authorizes runtime communication, Observation construction, acquisition, attribution logic, or implementation.

## 19. Architectural Invariants

The following invariants are normative for ADP-001D:

1. A governed contract shall never transfer Instrument ownership.
2. A governed contract shall never transfer Observation ownership.
3. A governed contract shall never transfer semantic authority.
4. A governed contract shall never create canonical Instrument identity.
5. A governed contract shall never redefine canonical Instrument identity.
6. A governed contract shall never convert identity into factual state.
7. A governed contract shall never allow factual state to redefine identity.
8. A governed contract shall preserve provenance continuity.
9. A governed contract shall preserve attribution continuity.
10. A governed contract shall preserve uncertainty.
11. A governed contract shall preserve unresolved ambiguity.
12. A governed contract shall never silently discard attribution failure.
13. A governed contract shall never perform business interpretation.
14. A governed contract shall never validate trading meaning.
15. A governed contract shall never construct strategy or execution semantics.
16. A governed contract shall preserve the separation between canonical Instrument identity and factual market state.
17. A governed contract shall never equate architectural admissibility with Observation acceptance or ownership.

These invariants apply to the governed attribution boundary and define no implementation enforcement mechanism.

## 20. Explicit Prohibitions

A governed contract shall never:

- create an Observation;
- define Observation structures;
- define candle models;
- define quote models;
- define OHLC models;
- define depth models;
- classify Instruments;
- create canonical identity;
- repair identity ambiguity;
- infer missing identity;
- correct market facts;
- enrich market facts;
- derive indicators;
- calculate trends;
- interpret market behavior;
- validate signals;
- score opportunities;
- rank opportunities;
- produce BUY or SELL logic;
- authorize execution;
- resolve Provider inconsistencies;
- define retrieval;
- define persistence;
- define APIs;
- define schemas;
- define payloads;
- define synchronization; or
- define runtime orchestration.

The governed contract shall never become a generic cross-domain framework, reusable platform pattern, Instrument implementation design, Observation implementation design, or indirect path around an approved dependency.

## 21. Conceptual Attribution Model

Figure 1 presents the conceptual attribution model governed by ADP-001D. It shows an approved canonical Instrument identity and factual market information meeting at the governed attribution boundary, which establishes eligibility for Observation participation and possible Observation ownership without creating identity, facts, or ownership.

```text
Approved Canonical                   Factual Market
Instrument Identity                  Information
        │                                  │
        │  Identity Reference              │  Factual State
        └────────────────┬─────────────────┘
                         ▼
            ────────────────────────────
            Governed Attribution Contract
            ────────────────────────────
                         │
                         │  Attribution Eligibility Only
                         ▼
      Eligible for Observation Participation and
          Possible Observation Ownership
```

**Figure 1 — Conceptual Instrument → Observation attribution model.**

The diagram is conceptual, semantic, and technology-independent. It is not a runtime flow, transport sequence, data model, interface, or implementation design. The layout defines no call direction, processing order, data movement, or communication mechanism.

## 22. Provenance and Attribution Continuity

Provenance continuity shall preserve the factual information's source and origin meaning throughout the attribution boundary. Attribution shall never make a source claim appear to originate from Instrument or Observation.

Attribution continuity shall keep the association between factual market information and the approved canonical Instrument identity explainable across the applicable identity, lifecycle, mapping, source, and temporal context.

Identity provenance and factual provenance shall remain distinguishable. Observation may preserve factual provenance without acquiring Provider or Instrument ownership. Instrument may preserve identity and mapping meaning without acquiring factual-state ownership.

ADP-001D does not define how provenance or attribution continuity is represented, stored, transmitted, reconciled, or processed.

## 23. Architectural Precedent

ADP-001D reinforces the ADP-001C precedent that a domain contract governs admissibility while preserving ownership and semantic authority.

Within KRONOS Swing Phase 1, ADP-001D additionally governs attribution eligibility between Instrument meaning and factual market information. It shall not declare a platform-wide principle, create a reusable platform pattern, amend the Platform Constitution, or modify any existing platform principle.

## 24. Dependencies

ADP-001D depends on:

- ADP-001A for the approved Phase 1 information inventory, factual categories, provenance requirements, and read-only restrictions;
- ADP-001B for canonical Instrument identity layers, lifecycle, mapping semantics, and identity invariants;
- ADP-001C for governed admissibility, preservation of ownership, and separation of physical movement from semantic authority;
- PLATFORM-000 for contract-based dependencies and single semantic ownership;
- DOMAIN-001 for Instrument ownership;
- DOMAIN-002 for Observation ownership;
- the Domain Ownership Matrix; and
- the Domain Dependency Matrix.

ADP-001D elaborates the approved dependency in which Observation consumes Instrument Identity. It creates no new domain dependency and does not alter the Domain Dependency Matrix.

ADP-001D does not replace or define a Provider → Observation acquisition contract. It identifies no producer, retrieval mechanism, or runtime source for factual market information.

No runtime, transport, storage, Provider-specific implementation, validation, or Engineering Package dependency is established.

## 25. Architectural Traceability

The approved architecture progresses as follows:

- **ADP-001A defines what information may enter KRONOS.**
- **ADP-001B defines what that information represents and what Instrument owns.**
- **ADP-001C defines when Provider information becomes eligible for Instrument interpretation.**
- **ADP-001D defines when factual market information may be attributed to a canonical Instrument identity and become eligible for Observation participation and possible Observation ownership.**

ADP-001D shall conform to ADP-001A, ADP-001B, and ADP-001C. It shall never restate them as new decisions, weaken their exclusions, expand their approved scope, or transfer their ownership assignments.

## 26. Conformance with ADP-001A

This document conforms to ADP-001A by:

- limiting the boundary to factual market-information categories within the approved Phase 1 inventory;
- preserving Instrument ownership of canonical identity and Observation ownership of Market Facts;
- preserving source attribution, temporal attribution, partiality, failure, unavailability, uncertainty, and ambiguity;
- keeping Instrument Master metadata distinct from Current Quote and Observation-owned factual state;
- keeping Provider availability separate from Market availability;
- preserving the distinction between missing information and zero and between successful acquisition and dataset completeness;
- retaining Options, TradingView, judgment, ranking, execution, orders, positions, persistence, retries, scheduling, and streaming exclusions;
- creating no factual-data acquisition authority or implementation sequence; and
- preserving read-only Phase 1 scope.

ADP-001D does not amend ADP-001A classifications, datasets, completion criteria, or unresolved questions.

## 27. Conformance with ADP-001B

This document conforms to ADP-001B by:

- preserving Economic Instrument, Listed Instrument, and Derivative Contract as separate Instrument-owned identity layers;
- requiring approved canonical Instrument identity before attribution eligibility;
- preserving Instrument's exclusive ownership of identity semantics, classification, lifecycle, relationships, mapping semantics, interpretation, and identity invariants;
- keeping Provider Instrument References external and non-canonical;
- respecting potentially time-bounded Provider mappings and effective identity context without defining temporal fields or algorithms;
- preserving historical identity and mapping attribution;
- keeping Provider Mapping State separate from Instrument lifecycle;
- allowing no factual state to create or redefine Instrument identity; and
- creating no identity, mapping, classification, lifecycle state, or successor relationship.

ADP-001D defines attribution eligibility only. It does not amend ADP-001B.

## 28. Conformance with ADP-001C

This document conforms to ADP-001C by:

- preserving the separation between physical movement, architectural admissibility, and semantic authority;
- preserving Instrument meaning under Instrument ownership;
- preserving factual source provenance without transferring ownership;
- treating eligibility as permission for Observation participation rather than correctness, acceptance, validation, ownership, publication, or lifecycle progression;
- preserving uncertainty and unresolved ambiguity;
- prohibiting the governed contract from becoming a runtime, transport, payload, schema, or implementation contract;
- creating no reusable platform pattern or platform-wide principle; and
- preserving exclusive domain ownership.

ADP-001D applies the approved governed-boundary precedent to attribution between Instrument and Observation. It does not amend ADP-001C.

## 29. Unresolved Architectural Questions

1. What constitutes an approved canonical Instrument identity for attribution within each identity layer?
2. Shall all approved factual market-information categories share the same attribution preconditions, or shall category-specific architectural obligations apply?
3. Which architectural distinctions must keep attribution failure separate from retained uncertainty and unresolved ambiguity?
4. How shall Instrument lifecycle and effective identity context constrain attribution eligibility?
5. What minimum provenance-continuity obligations apply across Provider, Instrument, and Observation without transferring ownership?
6. What architectural obligations shall keep ambiguous or conflicting attribution visible and unresolved without changing Instrument or Observation ownership?
7. Does future Observation architecture require a separately approved capability document after ADP-001D?
8. Does review identify any material architectural decision beyond the existing Instrument → Observation dependency that must be recorded by ADR before approval?

Engineering shall not answer these questions through implementation or inference. No unresolved matter authorizes fields, APIs, schemas, transport, persistence, algorithms, runtime behavior, or a follow-on package.

## 30. Follow-on Architecture

This document does not select, number, create, or authorize a follow-on architecture package.

The Chief Architect may separately determine whether future Observation architecture or another already identified dependency is ready for architectural work.

This section creates no sequence, roadmap commitment, contract, ADR, EDD, Engineering Package, acquisition authority, or runtime authorization.

## 31. Approval Record

**Chief Architect Decision:** Approved

**Engineering Architect Verification:** Complete

**ADR Required:** No

**Canonical Status:** Version 1.0

**Implementation Authorization:** None

**Next Authorized Capability:** None assigned by this document

**Review History:** The Chief Architect approved ADP-001D after Engineering Architect review. The Engineering Architect authorized canonicalization, and repository metadata and indexes were updated for Version 1.0.

ADP-001A, ADP-001B, ADP-001C, ADP-001D, and the approved Platform architecture retain authority within their respective scopes. Approval of ADP-001D does not independently authorize implementation.

## Related Approved Authority

- [ADP-001A — Swing Phase 1 Market Data Inventory](SWING-PHASE-1-MARKET-DATA-INVENTORY.md)
- [ADP-001B — KRONOS Swing Instrument Identity Architecture](SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md)
- [ADP-001C — Provider → Instrument Contract](SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md)
- [PLATFORM-000 — KRONOS Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [Instrument Domain](../../platform/domains/instrument/ARCHITECTURE.md)
- [Observation Domain](../../platform/domains/observation/ARCHITECTURE.md)
- [KRONOS Engine Ownership](../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../DATA_FLOW.md)
