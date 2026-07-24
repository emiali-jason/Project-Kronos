# ADP-001I — Swing Phase 1 Approved Instrument Universe and Reference Semantics Architecture

**Version:** 1.0

**Status:** Approved

**Canonical Status:** Approved Canonical Architecture

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Owner:** Chief Architect

**Prepared By:** Engineering Architect

**Approved By:** Chief Architect

**Classification:** Architecture Documentation Package

**Architecture Impact:** Approved canonical provider-neutral semantic definition of the approved Swing Phase 1 instrument universe and reference meanings

**Engineering Impact:** None

**Runtime Impact:** None

## 1. Status and Governance

This document is the approved canonical Version 1.0 architecture for ADP-001I. It does not authorize implementation, retrieval, Provider communication, mapping, persistence, scheduling, lifecycle processing, an EDD, an Engineering Package, or runtime change.

The following labels govern this approved architecture:

- **Approved base** identifies meaning already established by an approved repository document.
- **Approved definition** identifies semantic architecture approved by the Chief Architect.
- **Unresolved** identifies a matter intentionally reserved for later architecture.
- **Deferred capability** identifies a capability outside this architecture.

ADP-001A through ADP-001H, ADL-001, the Platform Constitution, the Domain Ownership Matrix, the Domain Dependency Matrix, ENGINE_OWNERSHIP, and DATA_FLOW remain authoritative. Where this architecture differs from approved architecture, the approved architecture prevails.

## 2. Purpose

Define a provider-neutral semantic boundary for the approved Swing Phase 1 instrument universe and for the reference meanings used to describe that universe. The document answers what may be treated as an approved instrument subject and what a reference relationship means, without defining how information is acquired, mapped, stored, scheduled, or processed.

This architecture preserves the three Instrument-owned identity layers approved by ADP-001B: Economic Instrument, Listed Instrument, and Derivative Contract. It also preserves the distinction between analysis instruments, reference instruments, and execution instruments established by ADL-001 and existing engine ownership.

## 3. Architectural Objective

**Approved definition:** ADP-001I defines the semantic membership boundary for the approved Swing Phase 1 instrument universe and the provider-neutral meaning of primary, reference, benchmark, sector, underlying, and execution relationships.

The objective is to ensure that a Provider reference, symbol, token, market-data record, configuration value, or model profile cannot silently become canonical Instrument meaning. This architecture establishes no retrieval authority and no Provider-to-Instrument runtime communication.

## 4. Scope

This architecture covers:

- the approved Swing Phase 1 instrument-universe boundary;
- provider-neutral semantic membership and exclusion;
- Economic Instrument, Listed Instrument, and Derivative Contract identity;
- analysis, reference, and execution roles;
- primary, reference, benchmark, sector, underlying, and intended-execution relationships;
- provider-neutral reference meaning;
- instrument-class and venue context;
- futures expiry and historical identity preservation;
- continuous-futures limitations;
- provenance and semantic authority; and
- unresolved lifecycle, mapping, and acquisition dependencies.

This architecture applies only to KRONOS Swing Phase 1 — Market Data Foundation. It does not enlarge the currently supported model or activate a planned model merely because its configuration or Provider data exists.

## 5. Out of Scope and Prohibitions

This architecture shall not define or authorize:

- Provider communication, acquisition, authentication, or retrieval mechanics;
- mapping algorithms, matching rules, symbol parsing, identifier generation, or collision resolution;
- APIs, schemas, payloads, transport, persistence, databases, caching, scheduling, retries, or synchronization;
- lifecycle state machines, rollover processing, replacement processing, continuous-series construction, or adjustment logic;
- market observations, quotes, candles, Open Interest, Market Facts, Market Schedule, or Exchange Availability ownership;
- Validation judgment, ranking, research orchestration, Business Judgment, Risk Approval, Execution, Orders, Positions, or automated trading;
- TradingView integration or changes to KR-370, KR-380, KR-390, or KR-400 ownership;
- Options retrieval, option chains, options analytics, valuation, validation, strategy, or execution;
- a new domain, a new shared ownership assignment, or an unapproved dependency; or
- an EDD, Engineering Package, implementation sequence, or implementation authorization.

Recognition of an identity-recognized but capability-inactive Option contract does not activate the Options product or authorize any Options capability.

## 6. Governing Ownership

| Responsibility | Owner | Meaning preserved by this architecture |
| --- | --- | --- |
| Instrument Identity | Instrument | Economic Instrument, Listed Instrument, Derivative Contract, classification, relationships, lifecycle, mapping meaning, and identity invariants |
| Provider Integration | Provider | Provider records, identifiers, provenance, capability, availability, and external reference meaning |
| Market Facts | Observation | Accepted factual market state attributed to an approved Instrument identity |
| Market Schedule | Market | Session and schedule meaning |
| Runtime Configuration | Configuration | Runtime values and selection context only |

Provider support does not acquire Instrument ownership. Reuse of an approved reference relationship does not transfer semantic authority. A consumer may use an approved meaning but must not recreate or override it.

## 7. Terminology

| Term | Architectural meaning |
| --- | --- |
| Approved Instrument Universe | The bounded set of Instrument-owned semantic identities and approved roles admitted to Swing Phase 1 by approved architecture. |
| Instrument Subject | An Instrument-owned identity that may be referred to by an approved factual or analytical relationship. |
| Economic Instrument | Provider-neutral economic identity, distinct from listings and derivative contracts. |
| Listed Instrument | Venue- and listing-specific identity. A materially different venue or listing may define a distinct Listed Instrument. |
| Derivative Contract | Individual contract-expiry identity, distinct from its underlying and every other expiry. |
| Provider Instrument Reference | External, Provider-owned, non-canonical reference material that may support later Instrument interpretation. |
| Analysis Instrument | Instrument role used by an approved analytical relationship; the role does not authorize retrieval or judgment. |
| Reference Instrument | Instrument role used to supply approved contextual reference information; it does not transfer ownership or create a new relationship. |
| Execution Instrument | Instrument role associated with an approved intended execution relationship; the role does not authorize orders or execution. |
| Primary Instrument | The principal Instrument subject for an approved relationship. It is not a universal platform role. |
| Benchmark | An approved comparison or contextual Instrument relationship. It does not become a decision or ranking meaning. |
| Sector Reference | An approved sector-context relationship where the applicable Swing model authorizes one. |
| Underlying Relationship | Explicit Instrument-owned semantic relationship between a derivative and its underlying economic or market reference. |
| Intended Execution Relationship | Approved semantic description of which execution subject corresponds to an analysis subject. It does not authorize execution. |
| Instrument Universe Membership | Instrument-owned semantic inclusion in the approved Phase 1 boundary. Provider availability does not establish membership. |
| Reference Semantics | Provider-neutral meaning of why one approved Instrument is used in relation to another. |
| Semantic Authority | Exclusive ownership of the meaning assigned to a responsibility. |
| Recognition | Knowledge that an identity is known within an approved boundary; it does not imply retrieval, observation, validation, or trading support. |
| Historical Identity | Preservation of a distinct identity for historical attribution after expiry, delisting, retirement, or supersession. |
| Continuous Futures Representation | A Provider or analytical representation that spans contracts; it is not automatically a canonical Instrument identity or adjusted historical series. |

Terminology defines no physical identifier, field, schema, storage representation, or runtime object.

## 8. Approved Universe Boundary

ADP-001A classifies Instrument Master reference information, provider tokens, relevant instrument reference fields, expiry, lifecycle information, approved analysis/reference/execution relationships, and required contextual references as Phase 1 information. Classification does not authorize retrieval and does not itself establish canonical membership.

The approved Swing Phase 1 semantic universe is fully resolved by this architecture as the bounded set of MCX Metals execution subjects and their approved reference subjects required by the currently supported model. The approved MCX Metals Economic Instruments are Gold, Silver, and Copper. Their MCX Listed Instruments are the approved execution listings, and their COMEX Listed Instruments are the approved global reference listings. The approved Derivative Contract category is the individual futures contract for each approved listing and expiry. The repository also records MCX Energy, NSE Equity Swing, and NSE Index Swing as model/configuration contexts; their presence does not make their market-data integration operational or enlarge the approved Phase 1 universe.

The approved Analysis Instruments are the MCX Gold, Silver and Copper subjects used by the current model. The approved Reference Instruments are the corresponding COMEX Gold, Silver and Copper subjects. The approved Intended Execution Instruments are the MCX Gold, Silver and Copper Listed Instruments and their approved futures-contract identities.

Explicit semantic exclusions are all non-approved instruments, unsupported venues, unapproved reference markets, Options capability, unapproved NSE or MCX Energy market-data integration, Provider-only records without approved Instrument meaning, and any instrument inferred solely from availability, configuration, price, symbol, or token.

Only operational contract enumeration remains deferred: Provider symbols, Provider tokens, expiry enumeration, lifecycle-effective activation, Provider mapping, and operational acquisition records. No semantic universe boundary is unresolved by this architecture.

## 9. Identity Layers and Roles

Economic Instrument, Listed Instrument, and Derivative Contract are separate Instrument-owned semantic layers. They shall not be collapsed into one identity or inferred from a Provider token, symbol, price, configuration value, or record presence.

Analysis, reference, and execution are roles, not identity layers. Multiple roles exist only where already established by approved canonical architecture. For Phase 1, MCX Metals subjects hold Analysis and Intended Execution roles, while COMEX Metals subjects hold the Reference role. ADP-001I introduces no additional role combination. A role does not create identity, change ownership, or authorize a downstream capability.

An individual derivative contract remains distinct from its underlying and from every other expiry. Historical identity survives expiry. A continuous representation shall not erase the identities of the contracts from which it is derived.

## 10. Reference Semantics

Reference semantics answer why an approved Instrument subject is related to another approved subject. They may describe primary analysis, global or local reference context, benchmark context, sector context, underlying relationship, or intended execution correspondence where approved.

Reference semantics shall:

1. be Instrument-owned;
2. identify the semantic role of the related subject without transferring identity;
3. preserve the distinction between analysis, reference, and execution roles;
4. remain provider-neutral;
5. preserve provenance of any Provider reference used later for interpretation;
6. remain distinct from Market Schedule, Market Facts, Validation, Risk, and Execution meaning; and
7. remain explainable across lifecycle or Provider-reference changes.

Reference semantics shall never be inferred solely from matching names, symbols, prices, connectivity, data presence, configuration, or Provider vocabulary.

### 10.1 Provider reference-meaning classes

**Mandatory Provider-owned reference meanings** shall preserve only Provider assertions: Provider context, Provider identifier meaning, Provider exchange or venue assertion, Provider segment or instrument-type assertion, Provider expiry or contract assertion where supplied, Provider provenance, ambiguity, limitation, and missingness. Provider shall not assign or own Economic Instrument, Listed Instrument, Derivative Contract, Analysis role, Reference role, Execution role, or Universe Membership.

**Optional reference meanings** may improve contextual completeness, such as supplementary exchange or relationship description, only when separately approved. Optional meaning shall not be required implicitly and shall not become canonical merely because Provider supplies it.

**Auxiliary Provider metadata** may remain Provider-owned technical or descriptive material, including Provider token, Provider-supplied last price, catalogue status, and other metadata that is not necessary to establish Instrument meaning. Auxiliary metadata shall not enter Instrument interpretation, Canonical Instrument Identity, Current Quote, or Observation-owned market state.

**Instrument-owned intended interpretation context** evaluates those Provider assertions under approved Instrument architecture. Semantic sufficiency for later ADP-001C evaluation exists only when the Provider assertions and the separately owned Instrument context are both present, attributable, and non-ambiguous. Sufficiency does not establish Architectural Admissibility, Instrument identity, Observation ownership, or acquisition authority.

## 11. Relationship Meaning

| Relationship | Owner | Meaning | Explicit limit |
| --- | --- | --- | --- |
| Primary | Instrument | Principal approved subject for a defined Swing relationship. | Not a universal identity or decision authority. |
| Reference | Instrument | Approved contextual subject used to supply factual or analytical context. | Does not transfer facts or create judgment. |
| Benchmark | Instrument | Approved comparison subject for an existing model relationship. | Does not imply ranking or suitability. |
| Sector | Instrument | Approved sector-context subject where an existing model authorizes it. | Does not create a new sector taxonomy. |
| Underlying | Instrument | Explicit relationship from a derivative contract to its underlying subject. | Does not merge identities. |
| Intended execution | Instrument | Approved semantic correspondence between analysis and execution subjects. | Does not authorize execution, orders, or positions. |

ADL-001 and existing ENGINE_OWNERSHIP remain authoritative for the approved MCX and NSE relationship meanings. This architecture records no additional relationship and no new domain dependency.

## 12. Reference-Market Semantics

Reference-market instruments are approved Instrument subjects that provide contextual market information for an existing analysis or execution relationship. They remain distinct Listed Instruments from the MCX execution subjects and do not become execution instruments merely because they support the same model.

For the currently approved MCX Metals model, COMEX Gold, COMEX Silver, and COMEX Copper are the approved reference-market coverage. MCX Gold, MCX Silver, and MCX Copper remain distinct MCX Listed Instruments; their corresponding COMEX subjects are distinct COMEX Listed Instruments, even where they relate to the same Economic Instrument.

NYMEX reference coverage is not required by the currently approved MCX Metals model. Any future NYMEX reference, other venue, or substitute source is unsupported by this architecture unless separately approved architecture establishes it. Unsupported reference coverage shall remain explicitly unsupported and shall not be silently substituted.

When a selected Provider cannot supply a required reference-market Instrument, the required relationship remains semantically unsatisfied. The consequence is preserved insufficiency for later capability review; it does not establish Instrument absence, Market closure, Provider ownership of the relationship, or permission to select another source. Another source may satisfy the relationship only after separate architecture authorizes that source and preserves the same Instrument-owned semantics.

## 13. Provider-Neutral Reference Boundary

Provider may preserve external references, identifiers, records, provenance, capability, availability, and acquisition outcomes under separately approved Provider architecture. Provider preserves only its own assertions; Instrument-owned architecture establishes intended interpretation context and membership.

Provider Instrument Master `last_price` remains auxiliary Provider metadata. It is not Canonical Instrument Identity, not Current Quote, and never replaces Observation-owned market state. Provider availability is not universe membership, Market availability, lifecycle state, or semantic acceptance.

No Provider-to-Instrument runtime communication, physical mapping interface, acquisition contract, or mapping algorithm is created by this architecture. ADP-001C and ADP-001H remain the governing boundaries for later eligibility and acquisition architecture.

## 14. Lifecycle and Continuity Boundaries

Instrument owns lifecycle meaning. The approved vocabulary includes Prospective, Active, Expired, Retired, Delisted, and Superseded, without authorizing a state machine or transition behavior.

Provider Mapping State remains distinct from Instrument Lifecycle. Provider Unavailable does not imply expiry, delisting, retirement, supersession, or absence from the approved universe.

Symbol changes, Provider-token reuse, disappearance, replacement, and continuous representations shall not silently reassign identity or historical attribution.

**Unresolved — Chief Architect Decision Required:** Applicability of each lifecycle concept to each identity layer, authoritative establishing facts, transition criteria, effective context, successor semantics, and continuous-futures treatment remain unresolved.

## 15. Observation and Market Boundaries

Observation owns accepted factual market state. An approved Instrument subject identifies what a fact concerns; it does not become the fact.

Market owns Market Schedule and session meaning. Instrument universe membership does not establish whether a market is open, closed, available, or tradable.

No reference relationship may be used as a substitute for factual Observation, Market Schedule, Validation judgment, Risk Approval, Execution timing, Portfolio state, or Event meaning.

## 16. Configuration Boundary

Configuration owns runtime configuration. A model selector, symbol selection, profile, or configured relationship may select approved behavior but shall never create an Instrument identity, membership, relationship, lifecycle state, Provider mapping, or Market meaning.

ADP-001F and ADP-001G remain authoritative for runtime configuration and authentication material. This architecture does not redefine Configuration Eligibility, Provider Usability, authentication, custody, token lifecycle, or secret handling.

## 17. Required Provenance

Any later approved interpretation of a Provider reference shall preserve, conceptually:

- Provider origin and Provider context;
- the reference meaning supplied by Provider;
- the applicable Instrument layer and semantic role;
- the approved universe context;
- the relevant effective or lifecycle context where required;
- uncertainty, ambiguity, omission, and limitation; and
- historical attribution after Provider-reference change.

These are semantic obligations only. No field names, timestamp format, storage model, or processing mechanism is defined.

## 18. Architectural Invariants

The following invariants are normative for this approved architecture:

1. Instrument is the sole semantic owner of Instrument Identity.
2. Economic Instrument, Listed Instrument, and Derivative Contract identities shall remain distinct.
3. Provider references and tokens shall remain external and non-canonical.
4. Provider availability shall never establish universe membership.
5. Configuration shall never create Instrument identity or membership.
6. Market Schedule shall never establish Instrument identity or membership.
7. Observation shall consume approved Instrument meaning and shall never create it.
8. Analysis, reference, and execution roles shall remain distinct from identity layers.
9. A reference relationship shall never transfer semantic ownership.
10. Underlying relationships shall be explicit and shall never be inferred solely from Provider vocabulary or price behavior.
11. Different derivative expiries shall remain distinct identities.
12. Historical identity shall survive expiry, delisting, retirement, supersession, and Provider-reference change.
13. Provider Mapping State shall remain distinct from Instrument Lifecycle.
14. Provider Unavailable shall never imply expiry, delisting, retirement, or supersession.
15. A symbol or token change shall never silently reassign canonical identity.
16. Provider-token reuse shall never silently inherit canonical meaning.
17. Continuous futures shall never automatically become a canonical continuous Instrument identity.
18. Continuous futures shall never automatically imply adjusted or rollover-safe history.
19. Instrument Master `last_price` shall never become Current Quote or Observation-owned market state through this architecture.
20. Universe membership shall never imply Market availability, Validation acceptance, Risk approval, Execution authority, or Portfolio ownership.
21. Reference semantics shall remain provider-neutral and Instrument-owned.
22. Provider provenance shall remain distinguishable from Instrument semantic authority.
23. No relationship in this architecture shall create an unapproved domain dependency.
24. No relationship in this architecture shall authorize Provider communication, acquisition, or implementation.
25. Options recognition shall not activate the Options product or any Options capability.
26. Gold, Silver, and Copper, together with their approved MCX and COMEX listings and relationships, shall form the approved semantic operating universe for this capability.
27. A Provider catalogue shall never define the approved Instrument Universe.
28. Unsupported reference coverage shall remain explicitly unsupported.
29. COMEX Listed Instruments and MCX Listed Instruments shall remain distinct even when related to one Economic Instrument.
30. Ambiguous Provider references shall never establish canonical Instrument identity.
31. Approval of the Instrument Universe shall never authorize Provider communication.
32. Approval of the Instrument Universe shall never activate concrete Acquisition Authority.
33. Approval of the Instrument Universe shall never authorize implementation.
34. Provider information shall never assign or own an Instrument identity layer, universe role, or canonical relationship.
35. The exact semantic universe may be canonical even though operational contract enumeration remains deferred.
36. No role combination shall exist unless the exact combination is established by approved canonical product architecture.
37. Semantic universe approval shall not finalize a concrete Requested Acquisition Scope under ADP-001H.

## 19. Architectural Questions

The following 25 Chief Architect-authorized questions are answered one-to-one. The question wording and numbering are preserved exactly; answers marked unresolved intentionally reserve later decisions.

| # | Architectural question | Answer | Status |
| ---: | --- | --- | --- |
| 1 | What is the exact approved KRONOS Swing Phase 1 universe? | The approved semantic universe is the bounded MCX Metals execution subjects Gold, Silver, and Copper, their approved MCX futures-contract identities, and the approved COMEX reference subjects required by the current model. Only operational contract enumeration remains deferred. | Approved definition |
| 2 | Which Economic Instruments are included in the currently approved MCX Metals model? | Gold, Silver, and Copper are included. | Approved base / ADL-001 |
| 3 | Which Listed Instruments and venues are required for each approved Economic Instrument? | Each approved Economic Instrument requires its MCX Listed Instrument for execution context and its corresponding COMEX Listed Instrument for approved global reference context. | Approved definition; exact venue identifiers deferred |
| 4 | Which Derivative Contract categories are in scope? | Individual futures contracts for the approved MCX and COMEX Listed Instruments are in scope; Option contracts remain identity-recognised but capability-inactive. Operational expiry enumeration remains deferred. | Approved base |
| 5 | Are all expiries in the approved venue eligible as reference material, or is the universe further bounded architecturally? | The universe is further bounded by approved Instrument meaning, model relationship, lifecycle context, and approved reference scope; venue availability alone does not make every expiry operationally eligible. Operational expiry enumeration remains deferred. | Approved definition |
| 6 | What provider-neutral meanings are required to distinguish an Economic Instrument? | Provider-neutral economic subject, stable identity continuity, approved classification, and explicit relationships are required; price, token, symbol, and Provider availability are insufficient. | Approved base; detailed attributes deferred |
| 7 | What provider-neutral meanings are required to distinguish a Listed Instrument? | Economic relationship, venue/listing context, and distinct listing or trading rules are required; Provider vocabulary alone is insufficient. | Approved base; detailed attributes deferred |
| 8 | What provider-neutral meanings are required to distinguish an individual Derivative Contract? | Underlying relationship, contract category, expiry, applicable venue/listing context, and any approved contract-specific distinction are required; no physical identifier is defined. | Approved base; detailed attributes deferred |
| 9 | Which Provider-supplied reference meanings are mandatory for Instrument interpretation? | Provider context, Provider identifier meaning, Provider exchange or venue assertion, Provider segment or instrument-type assertion, Provider expiry or contract assertion where supplied, Provider provenance, ambiguity, limitation, and missingness are mandatory Provider-owned assertions. Instrument owns intended interpretation context. | Approved definition |
| 10 | Which reference meanings are optional? | Supplementary exchange, relationship, or descriptive context may be optional when separately approved and shall not be required implicitly. | Approved definition |
| 11 | Which Provider fields may remain auxiliary metadata but must not enter Instrument interpretation? | Provider tokens, Provider-supplied last price, catalogue status, technical capability, availability, and other descriptive or technical metadata not required for semantic identity may remain auxiliary. | Approved base / ADP-001A |
| 12 | How do analysis, reference and execution roles relate to the approved identity layers? | They are roles associated with approved Economic Instrument, Listed Instrument, or Derivative Contract identities; roles do not create identity or authority. | Approved definition / ADL-001 |
| 13 | Can one Instrument-owned identity hold more than one approved role? | Only where already established by approved canonical architecture: MCX Metals subjects hold Analysis and Intended Execution, while COMEX Metals subjects hold Reference. ADP-001I introduces no additional role combinations. | Approved definition |
| 14 | Which existing analysis/reference/execution relationships are authoritative for Phase 1? | ADL-001, ENGINE_OWNERSHIP, DATA_FLOW, and the existing MCX Metals relationships are authoritative; this architecture adds none. | Approved base |
| 15 | What reference-market instruments are architecturally required for MCX Metals? | COMEX Gold, COMEX Silver, and COMEX Copper are required reference subjects for the approved MCX Metals model. | Approved definition / ADL-001 |
| 16 | Does approved reference-market coverage require COMEX, NYMEX or another explicitly approved venue? | The approved MCX Metals coverage requires COMEX. NYMEX and other venues are not approved by this architecture. | Approved definition |
| 17 | What is the architectural consequence when the selected Provider cannot supply a required reference-market instrument? | Required reference coverage remains semantically unsatisfied; the condition does not establish Instrument absence, Market closure, or authority to substitute another source. | Approved definition |
| 18 | May another source satisfy a required reference relationship, or must source selection remain separately authorized? | Another source may satisfy it only after separate architecture authorizes that source and preserves Instrument-owned semantics. | Approved definition |
| 19 | What Provider vocabulary may support interpretation without becoming canonical vocabulary? | Provider identifiers, symbols, names, exchange/segment descriptions, instrument types, expiry descriptions, and Provider provenance may support later interpretation, but none becomes canonical without Instrument-owned meaning. | Approved base / ADP-001C |
| 20 | What conditions make Provider reference information semantically sufficient for ADP-001C evaluation? | Provider assertions must be preserved and the separately Instrument-owned intended interpretation context must be present, attributable to the approved semantic universe, and non-ambiguous. | Approved definition |
| 21 | What missing or ambiguous reference meanings must prevent Instrument interpretation? | Missing Provider assertions, missing Instrument-owned intended interpretation context, missing required contract or expiry assertion, absent provenance, limitation, missingness, or unresolved ambiguity shall prevent interpretation. | Approved definition |
| 22 | What exact information is excluded from the first Instrument Master acquisition scope? | ADP-001I establishes only semantic eligibility and semantic exclusion. It does not approve Requested Acquisition Scope, activate Acquisition Authority, or modify ADP-001H governance. Concrete acquisition scope remains separately governed; operational acquisition records and Provider tokens/symbols are excluded from this semantic scope. | Approved definition |
| 23 | How are Options rows kept outside active Phase 1 scope while Option identity remains conceptually recognised? | Option identity remains conceptually recognised under ADP-001B, but Options rows are excluded from active Phase 1 universe membership and no Options retrieval, analytics, validation, strategy, or execution is authorized. | Approved base |
| 24 | Does the approved universe include only MCX execution contracts and their approved references, or any wider instrument set? | It includes only the approved MCX Metals execution contracts and their approved COMEX reference subjects, not a wider Provider catalogue or model configuration set. The semantic universe is resolved; operational contract enumeration remains deferred. | Approved definition |
| 25 | What unresolved matters must remain deferred to lifecycle, mapping or acquisition architecture? | Exact identity attributes, contract enumeration, role cardinality details, effective context, lifecycle transitions, Provider mapping semantics, source substitution, acquisition scope, and operational treatment remain deferred. | Unresolved |

## 20. Unresolved Architecture Dependencies

This architecture leaves only operational and downstream architecture unresolved:

- operational contract enumeration, including Provider symbols, Provider tokens, expiry enumeration, lifecycle-effective activation, Provider mapping, and operational acquisition records;
- identity-defining attributes for each instrument class;
- cardinality and effective context of reference and underlying relationships;
- provider-to-canonical mapping semantics and mapping authority;
- lifecycle transition criteria and authoritative facts;
- symbol continuity and Provider-token reuse treatment in each context;
- continuous-futures identity, adjustment, and rollover semantics;
- approved source and meaning for any future reference or market metadata;
- exact provenance representation and effective-time semantics; and
- any acquisition, authentication, lifecycle, or engineering capability needed to operationalize these meanings.

No implementation decision may answer an unresolved architectural question.

## 21. Consistency and Dependency Determination

ADP-001I fully resolves the semantic universe and conforms to the approved repository boundaries:

- ADP-001A supplies the Phase 1 inventory and mandatory/optional/conditional/future classifications.
- ADP-001B supplies the three Instrument identity layers, lifecycle separation, mapping principles, and historical attribution.
- ADP-001C governs Provider-information admissibility before Instrument interpretation.
- ADP-001D governs attribution eligibility without transferring Instrument or Observation ownership.
- ADP-001E assigns factual Observation ownership and preserves fact-versus-interpretation boundaries.
- ADP-001F and ADP-001G retain Configuration and authentication boundaries.
- ADP-001H governs the bounded Provider Instrument Master capability and ends before Instrument interpretation.
- ADL-001 and ENGINE_OWNERSHIP preserve existing analysis/reference/execution relationships and engine ownership.
- The Domain Ownership Matrix assigns Instrument Identity to Instrument and Provider Integration to Provider.
- The Domain Dependency Matrix permits only approved contract-based dependencies; this architecture creates none.
- DATA_FLOW and PP-007 remain unchanged; execution and automated trading are excluded.

No ownership conflict, new dependency, Provider leakage, implementation leakage, or shared semantic authority is introduced by this architecture.

## 22. ADR Determination

This architecture does not create or require an ADR by itself. An ADR is required if a future proposal would add a domain dependency, reassign ownership, activate Options, alter the approved identity layers, authorize continuous-futures semantics, or change an approved boundary.

## 23. Deferred Capabilities

The following remain deferred and unauthorized. ADP-001I establishes only semantic eligibility and semantic exclusion; it does not approve Requested Acquisition Scope, activate Acquisition Authority, or modify ADP-001H governance. Concrete acquisition scope remains separately governed.

- operational contract enumeration, including Provider symbols, Provider tokens, expiry enumeration, lifecycle-effective activation, Provider mapping, and operational acquisition records;
- Provider Instrument Master acquisition beyond ADP-001H authority;
- Provider-to-Instrument mapping contract or runtime communication;
- Instrument lifecycle implementation and transition processing;
- continuous-futures construction or adjustment;
- historical and current market-data acquisition;
- Observation acceptance or publication implementation;
- Market Schedule acquisition or Exchange Availability production;
- Options capability;
- Validation, ranking, research orchestration, execution, orders, positions, and automated trading; and
- any EDD, Engineering Package, or runtime change.

## 24. Approval Record

**Chief Architect Decision:** Approved

**Engineering Architect Verification:** Complete

**Canonical Status:** Approved Canonical Architecture

**ADR Required:** No

**Implementation Authorization:** None

**Provider Communication Authorization:** None

**Acquisition Authorization:** None

**EDD Authorization:** None

**Engineering Package Authorization:** None

**Next Authorized Capability:** None

**Review History:** ADP-001I was drafted under Chief Architect authorization as a provider-neutral Phase 1 semantic architecture. Version 1.0 incorporates Chief Architect amendments CA-001 through CA-005, closes Engineering findings EA-001 through EA-009, and has completed Engineering Architect verification. It is approved as canonical architecture. Implementation, acquisition, Provider communication, EDD, Engineering Package, and follow-on capability remain unauthorized.

## Related Approved Authority

- [ADP-001A — Swing Phase 1 Market Data Inventory](SWING-PHASE-1-MARKET-DATA-INVENTORY.md)
- [ADP-001B — KRONOS Swing Instrument Identity Architecture](SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md)
- [ADP-001C — Provider → Instrument Contract](SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md)
- [ADP-001D — Instrument → Observation Contract](SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md)
- [ADP-001E — Observation Domain Architecture](SWING-PHASE-1-OBSERVATION-DOMAIN-ARCHITECTURE.md)
- [ADP-001F — Configuration → Provider Runtime Configuration Boundary](SWING-PHASE-1-CONFIGURATION-PROVIDER-RUNTIME-CONFIGURATION-BOUNDARY.md)
- [ADP-001G — Configuration → Provider Authentication Boundary](SWING-PHASE-1-CONFIGURATION-PROVIDER-AUTHENTICATION-BOUNDARY.md)
- [ADP-001H — Provider Instrument Master Acquisition Capability and Contract](SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md)
- [ADL-001 — Futures Model Architecture](../../ADL-001-Futures-Model.md)
- [Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [KRONOS Engine Ownership](../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../DATA_FLOW.md)
