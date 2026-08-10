# ADP-001I — Swing Phase 1 Approved Instrument Universe and Reference Semantics Architecture

**Document ID:** ADP-001I
**Title:** Swing Phase 1 Approved Instrument Universe and Reference Semantics Architecture
**Version:** 1.0

**Status:** Approved

**Canonical Status:** Approved Canonical Architecture

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Owner:** Chief Architect

**Prepared By:** Engineering Architect

**Approved By:** Chief Architect

**Review Authority:** Not stated

**Repository Location:** `docs/architecture/products/swing/SWING-PHASE-1-APPROVED-INSTRUMENT-UNIVERSE-AND-REFERENCE-SEMANTICS-ARCHITECTURE.md`

**Classification:** Architecture Documentation Package

**Architecture Impact:** Approved canonical Swing Phase 1 product-universe and reference semantics aligned with Instrument-owned canonical identity and Provider mapping architecture

**Engineering Impact:** None

**Runtime Impact:** None

## 1. Status and Governance

This document is the approved canonical Version 1.0 architecture for ADP-001I. It does not authorize implementation, retrieval, Provider communication, mapping implementation, persistence, scheduling, lifecycle processing, an EDD, an Engineering Package, EDD-004, or runtime change.

The following labels govern this approved architecture:

- **Approved base** identifies meaning already established by an approved repository document.
- **Approved definition** identifies semantic architecture approved by the Chief Architect.
- **Unresolved** identifies a matter intentionally reserved for later architecture.
- **Deferred capability** identifies a capability outside this architecture.

ADR-009, MIG-001, EAIC-002, the Provider Domain Architecture, the Instrument Domain Architecture, the Domain Ownership Matrix, the Domain Dependency Matrix, DATA_FLOW, migrated ADP-001B, migrated ADP-001J, ADL-001, and the Platform Constitution remain authoritative. ADP-001C and ADP-001H are superseded and retained only for predecessor traceability. Where this architecture differs from higher approved architecture, the higher approved architecture prevails.

This migration does not activate ADR-009 or EAIC-002 and does not authorize runtime behaviour, implementation or EDD-004.

## 2. Purpose

Define the Swing-owned semantic boundary for the approved Swing Phase 1 product universe and the provider-neutral Instrument-owned reference meanings consumed by that product universe. The document answers which canonical Instrument subjects Swing may consume and which approved Instrument relationships support that consumption, without defining how information is acquired, mapped, stored, scheduled, or processed.

This architecture preserves the three Instrument-owned identity layers approved by ADP-001B: Economic Instrument, Listed Instrument, and Derivative Contract. Provider mapping and cross-Provider reconciliation remain exclusively Instrument-owned. Swing consumes canonical identity and approved Provider mapping outputs explicitly but never performs mapping. The architecture also preserves the distinction between analysis instruments, reference instruments, and execution instruments established by ADL-001 and existing engine ownership.

## 3. Architectural Objective

**Approved definition:** ADP-001I defines the product-owned semantic membership boundary for the approved Swing Phase 1 instrument universe and the Instrument-owned provider-neutral meaning of primary, reference, benchmark, sector, underlying, and execution relationships consumed by Swing.

The objective is to ensure that a Provider reference, Provider-native identifier, symbol, token, market-data record, configuration value, model profile, or product membership cannot silently become canonical Instrument meaning or Provider mapping. This architecture establishes no retrieval authority and no Provider-to-Instrument runtime communication.

## 4. Scope

This architecture covers:

- the approved Swing Phase 1 product-universe boundary;
- provider-neutral semantic membership and exclusion;
- Economic Instrument, Listed Instrument, and Derivative Contract identity;
- explicit consumption of Instrument-owned canonical identity and Provider mapping outputs;
- separation of Provider Mapping Status from Canonical Identity Decision;
- analysis, reference, and execution roles;
- primary, reference, benchmark, sector, underlying, and intended-execution relationships;
- provider-neutral reference meaning;
- instrument-class and venue context;
- futures expiry and historical identity preservation;
- continuous-futures limitations;
- provenance and semantic authority; and
- unresolved lifecycle, mapping-mechanics, and acquisition dependencies.

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
| Instrument Identity | Instrument | Interpretation, Economic Instrument, Listed Instrument, Derivative Contract, canonical identity decision, classification, relationships, lifecycle, Provider mapping, Provider Mapping Status, cross-Provider reconciliation, and Canonical Instrument Catalogue publication |
| Provider Integration | Provider | Acquisition, Provider Catalogue, Provider records, Provider Record Identity, Provider dispositions, Submission Eligibility, provenance, acquisition scope and outcomes, capability, entitlement, availability, and external reference meaning |
| Swing Product Universe and Product Eligibility | Swing | Product-owned membership, eligibility, consumption, evidence requirements, validation requirements, decision semantics, and risk interpretation |
| Market Facts | Observation | Accepted factual market state attributed to an approved Instrument identity |
| Market Schedule | Market | Session and schedule meaning |
| Runtime Configuration | Configuration | Runtime values and selection context only |

Provider support does not acquire Instrument ownership. Swing product membership does not create canonical identity or Provider mapping. Reuse of an approved reference relationship does not transfer semantic authority. A consumer may use approved canonical meaning but must not recreate or override it.

## 7. Terminology

| Term | Architectural meaning |
| --- | --- |
| Approved Swing Product Universe | The bounded, Swing-owned set of canonical Instrument identities and approved product roles admitted to Swing Phase 1 by approved architecture. Membership does not create or alter canonical identity or Provider mapping. |
| Instrument Subject | An Instrument-owned identity that may be referred to by an approved factual or analytical relationship. |
| Economic Instrument | Provider-neutral economic identity, distinct from listings and derivative contracts. |
| Listed Instrument | Venue- and listing-specific identity. A materially different venue or listing may define a distinct Listed Instrument. |
| Derivative Contract | Individual contract-expiry identity, distinct from its underlying and every other expiry. |
| Provider Instrument Reference | External, Provider-owned, non-canonical reference material that may support later Instrument interpretation. |
| Provider Mapping | Instrument-owned governed association between one Provider reference and one canonical Instrument identity. |
| Provider Mapping Status | Instrument-owned dimension, independent from Canonical Identity Decision, with the approved values NOT_EVALUATED, MAPPING_PENDING, MAPPED, NOT_MAPPED, MAPPING_AMBIGUOUS, and MAPPING_UNSUPPORTED. |
| Cross-Provider Reconciliation | Instrument-owned reconciliation of separately preserved Provider mappings and evidence without globalizing Provider-native identifiers. |
| Analysis Instrument | Instrument-owned role used by an approved analytical relationship and consumed explicitly by Swing; the role does not authorize retrieval or judgment. |
| Reference Instrument | Instrument-owned role used to supply approved contextual reference information and consumed explicitly by Swing; it does not transfer ownership or create a new relationship. |
| Execution Instrument | Instrument-owned role associated with an approved intended execution relationship and consumed explicitly by Swing; the role does not authorize orders or execution. |
| Primary Instrument | The principal Instrument subject for an approved relationship. It is not a universal platform role. |
| Benchmark | An approved comparison or contextual Instrument relationship. It does not become a decision or ranking meaning. |
| Sector Reference | An approved sector-context relationship where the applicable Swing model authorizes one. |
| Underlying Relationship | Explicit Instrument-owned semantic relationship between a derivative and its underlying economic or market reference. |
| Intended Execution Relationship | Approved semantic description of which execution subject corresponds to an analysis subject. It does not authorize execution. |
| Swing Product Universe Membership | Swing-owned semantic inclusion in the approved Phase 1 product boundary. It consumes canonical Instrument meaning and does not establish canonical identity or Provider mapping. |
| Reference Semantics | Provider-neutral meaning of why one approved Instrument is used in relation to another. |
| Semantic Authority | Exclusive ownership of the meaning assigned to a responsibility. |
| Recognition | Knowledge that an identity is known within an approved boundary; it does not imply retrieval, observation, validation, or trading support. |
| Historical Identity | Preservation of a distinct identity for historical attribution after expiry, delisting, retirement, or supersession. |
| Continuous Futures Representation | A Provider or analytical representation that spans contracts; it is not automatically a canonical Instrument identity or adjusted historical series. |

Terminology defines no physical identifier, field, schema, storage representation, or runtime object.

## 8. Approved Universe Boundary

ADP-001A classifies Instrument Master reference information, provider tokens, relevant instrument reference fields, expiry, lifecycle information, approved analysis/reference/execution relationships, and required contextual references as Phase 1 information. Classification does not authorize retrieval and does not itself establish canonical membership.

The approved Swing Phase 1 product universe is the following bounded set of 98 canonical analytical subjects:

- the 91 approved NSE cash equities enumerated by `data/nse/KRONOS_NSE_RELATIONSHIPS.csv`;
- the NSE indices NIFTY and BANK NIFTY; and
- the MCX commodity subjects GOLDM, SILVERM, COPPER, CRUDEOIL, and NATURALGAS.

This 98-member universe supersedes the previous Swing Phase 1 Gold, Silver, and Copper-only universe boundary. It also supersedes the prior exclusion of NSE equities, NSE indices, and MCX Energy from Swing Phase 1 product-universe membership. The approved COMEX reference relationships for the MCX Metals model remain unchanged and do not add members to the 98 analytical subjects.

The 98 universe members are the approved Swing analytical subjects. Within the current MCX Metals model, the approved Reference Instruments remain the corresponding COMEX Gold, Silver, and Copper subjects, and the approved Intended Execution Instruments remain the MCX Gold, Silver, and Copper Listed Instruments and their approved futures-contract identities.

Explicit product-universe exclusions are all canonical Instruments outside the approved 98-member set, unsupported venues, unapproved reference markets, Options capability, Provider-only records without approved Instrument meaning, and any subject inferred solely from availability, configuration, price, symbol, token, or Provider mapping.

Swing owns membership of this analytical universe and the stable Swing analytical identity used to refer to each member. Provider-specific symbols, Instrument Master records, current futures-contract resolution, and market-data retrieval remain outside Swing and within the Provider boundary. Expiring futures-contract symbols are operational Provider identities and shall not become permanent Swing analytical identities. Provider mapping ownership and status meaning remain governed by the Instrument Domain Architecture. No Swing product-universe boundary is unresolved by this architecture.

## 9. Identity Layers and Roles

Economic Instrument, Listed Instrument, and Derivative Contract are separate Instrument-owned semantic layers. They shall not be collapsed into one identity or inferred from a Provider token, symbol, price, configuration value, or record presence.

Analysis, reference, and execution are Instrument-owned roles consumed by Swing, not identity layers. Multiple roles exist only where already established by approved canonical architecture. For Phase 1, MCX Metals subjects hold Analysis and Intended Execution roles, while COMEX Metals subjects hold the Reference role. ADP-001I introduces no additional role combination. A role does not create canonical identity, create Provider mapping, change Instrument ownership, or authorize a downstream capability.

An individual derivative contract remains distinct from its underlying and from every other expiry. Historical identity survives expiry. A continuous representation shall not erase the identities of the contracts from which it is derived.

## 10. Reference Semantics

Reference semantics answer why an approved canonical Instrument subject is consumed in relation to another approved canonical subject. Instrument owns canonical Instrument relationships and roles. Swing owns product-universe membership and consumption of those relationships. Reference semantics may describe primary analysis, global or local reference context, benchmark context, sector context, underlying relationship, or intended execution correspondence where approved.

Reference semantics shall:

1. preserve Instrument ownership of canonical relationships and roles and Swing ownership of product-universe membership and consumption;
2. identify the semantic role of the related subject without transferring identity;
3. preserve the distinction between analysis, reference, and execution roles;
4. remain provider-neutral;
5. preserve provenance of any Provider reference used later for interpretation;
6. remain distinct from Market Schedule, Market Facts, Validation, Risk, and Execution meaning; and
7. remain explainable across lifecycle or Provider-reference changes.

Reference semantics shall never be inferred solely from matching names, symbols, prices, connectivity, data presence, configuration, or Provider vocabulary.

### 10.1 Provider reference-meaning classes

**Mandatory Provider-owned reference meanings** shall preserve only Provider assertions: Provider context, Provider identifier meaning, Provider exchange or venue assertion, Provider segment or instrument-type assertion, Provider expiry or contract assertion where supplied, Provider provenance, ambiguity, limitation, and missingness. Provider shall not assign or own Economic Instrument, Listed Instrument, Derivative Contract, canonical Instrument relationships, Provider mapping, Analysis role, Reference role, Execution role, or Swing Product Universe Membership.

**Optional reference meanings** may improve contextual completeness, such as supplementary exchange or relationship description, only when separately approved. Optional meaning shall not be required implicitly and shall not become canonical merely because Provider supplies it.

**Auxiliary Provider metadata** may remain Provider-owned technical or descriptive material, including Provider token, Provider-supplied last price, catalogue status, and other metadata that is not necessary to establish Instrument meaning. Auxiliary metadata shall not become Instrument interpretation, Canonical Instrument Identity, Provider mapping, Current Quote, or Observation-owned market state.

**Instrument-owned interpretation and mapping context** evaluates Provider assertions admitted through EAIC-002 under approved Instrument architecture. EAIC-002 Interpretation Admission, Instrument Interpretation, Canonical Identity Decision, and Provider Mapping Status remain separate meanings. Provider Mapping Status is maintained independently of Canonical Identity Decision, and canonical identity may coexist with mapping `NOT_EVALUATED`, `MAPPING_PENDING`, `MAPPED`, `NOT_MAPPED`, `MAPPING_AMBIGUOUS`, or `MAPPING_UNSUPPORTED` as governed by the Instrument Domain Architecture.

**Swing-owned consumption context** applies only after Instrument processing has established approved canonical Instrument meaning and, where the Swing consumption requires a Provider mapping, the applicable Instrument-owned mapping. Swing shall not perform mapping, cross-Provider reconciliation, canonical identity decision, or Instrument interpretation.

## 11. Relationship Meaning

| Relationship | Owner | Meaning | Explicit limit |
| --- | --- | --- | --- |
| Primary | Instrument | Principal canonical Instrument subject consumed for a defined Swing relationship. | Does not create canonical identity, mapping, or decision authority. |
| Reference | Instrument | Approved canonical contextual subject consumed for factual or analytical context. | Does not transfer facts or create judgment. |
| Benchmark | Instrument | Approved canonical comparison subject consumed for an existing model relationship. | Does not imply ranking or suitability. |
| Sector | Instrument | Approved canonical sector-context subject consumed where an existing model authorizes it. | Does not create a new sector taxonomy. |
| Underlying | Instrument | Explicit relationship from a derivative contract to its underlying subject. | Does not merge identities. |
| Intended execution | Instrument | Approved semantic correspondence between analysis and execution subjects consumed by Swing. | Does not create identity or mapping and does not authorize execution, orders, or positions. |

ADL-001 and existing ENGINE_OWNERSHIP remain authoritative for the approved MCX and NSE relationship meanings. This architecture records no additional relationship and no new domain dependency.

## 12. Reference-Market Semantics

Reference-market instruments are canonical Instrument subjects consumed by Swing to provide contextual market information for an existing analysis or execution relationship. They remain distinct Listed Instruments from the MCX execution subjects and do not become execution instruments merely because they support the same model.

For the currently approved MCX Metals model, COMEX Gold, COMEX Silver, and COMEX Copper are the approved reference-market coverage. MCX Gold, MCX Silver, and MCX Copper remain distinct MCX Listed Instruments; their corresponding COMEX subjects are distinct COMEX Listed Instruments, even where they relate to the same Economic Instrument.

NYMEX reference coverage is not required by the currently approved MCX Metals model. Any future NYMEX reference, other venue, or substitute source is unsupported by this architecture unless separately approved architecture establishes it. Unsupported reference coverage shall remain explicitly unsupported and shall not be silently substituted.

When a selected Provider cannot supply a required reference-market Instrument, the Swing consumption requirement remains unsatisfied. The condition does not alter canonical identity, Canonical Identity Decision, Provider Mapping Status, Market state, or Provider ownership. Another source may satisfy the relationship only after separately governed Provider mapping and product-consumption authority preserve the same canonical Instrument meaning.

## 13. Provider-Neutral Reference Boundary

Provider owns acquisition, Provider Catalogue content, Provider records, Provider-native identifiers, dispositions, Submission Eligibility, provenance, capability, entitlement, availability, acquisition scope, and acquisition outcomes. Provider preserves only its own assertions. Provider-native identifiers never become canonical Instrument identity and never establish cross-Provider identity equivalence.

Provider Instrument Master `last_price` remains auxiliary Provider metadata. It is not Canonical Instrument Identity, not Current Quote, and never replaces Observation-owned market state. Provider availability is not universe membership, Market availability, lifecycle state, or semantic acceptance.

EAIC-002 is the only upstream Provider → Instrument boundary for the Instrument Master dataset governed by ADR-009. Provider owns Submission Eligibility and shall not populate Instrument directly. Instrument owns technical receipt, contract validation, Interpretation Admission, interpretation, canonical identity decision, Provider mapping, Provider Mapping Status, and cross-Provider reconciliation. ADR-009 Version 1.0 and DOMAIN-006 Provider Domain Architecture govern Provider acquisition and Provider Catalogue responsibility. ADP-001C and ADP-001H are superseded predecessors and supply no active authority.

This architecture creates no Provider-to-Instrument runtime communication, physical mapping interface, acquisition contract, mapping algorithm, endpoint authority, persistence authority, or activation authority.

## 14. Lifecycle and Continuity Boundaries

Instrument owns lifecycle meaning. The approved vocabulary includes Prospective, Active, Expired, Retired, Delisted, and Superseded, without authorizing a state machine or transition behavior.

Provider Mapping Status remains independent from Canonical Identity Decision and distinct from Instrument Lifecycle. Canonical identity may exist without a completed Provider mapping. `NOT_EVALUATED`, `MAPPING_PENDING`, `NOT_MAPPED`, `MAPPING_AMBIGUOUS`, and `MAPPING_UNSUPPORTED` do not invalidate canonical identity. Provider Unavailable does not imply expiry, delisting, retirement, supersession, or absence from the Swing product universe.

Symbol changes, Provider-token reuse, disappearance, replacement, and continuous representations shall not silently reassign identity or historical attribution.

**Unresolved — Chief Architect Decision Required:** Applicability of each lifecycle concept to each identity layer, authoritative establishing facts, transition criteria, effective context, successor semantics, and continuous-futures treatment remain unresolved.

## 15. Observation and Market Boundaries

Observation owns accepted factual market state. Observation may consume canonical identity only after Instrument processing has established approved canonical Instrument meaning through an Instrument-owned publication boundary. Observation does not perform interpretation, canonical identity decision, Provider mapping, cross-Provider reconciliation, or product-universe determination. An approved Instrument subject identifies what a fact concerns; it does not become the fact.

Market owns Market Schedule and session meaning. Instrument universe membership does not establish whether a market is open, closed, available, or tradable.

No reference relationship may be used as a substitute for factual Observation, Market Schedule, Validation judgment, Risk Approval, Execution timing, Portfolio state, or Event meaning.

## 16. Configuration Boundary

Configuration owns runtime configuration. A model selector, symbol selection, profile, or configured relationship may select approved behavior but shall never create canonical Instrument identity, Swing product-universe membership, Instrument relationship, lifecycle state, Provider mapping, or Market meaning.

ADP-001F and ADP-001G remain authoritative for runtime configuration and authentication material. This architecture does not redefine Configuration Eligibility, Provider Usability, authentication, custody, token lifecycle, or secret handling.

## 17. Required Provenance

Any later approved interpretation of a Provider reference shall preserve, conceptually:

- Provider origin and Provider context;
- the reference meaning supplied by Provider;
- the applicable Instrument layer and semantic role;
- the applicable canonical Instrument identity;
- the applicable Provider mapping and mapping evidence where established;
- the approved Swing product-universe and product-role context where consumed;
- the relevant effective or lifecycle context where required;
- uncertainty, ambiguity, omission, and limitation; and
- historical attribution after Provider-reference change.

Mapping shall preserve Provider attribution and provenance without converting Provider-native identity into canonical identity or merging evidence across Providers. These are semantic obligations only. No field names, timestamp format, storage model, or processing mechanism is defined.

## 18. Architectural Invariants

The following invariants are normative for this approved architecture:

1. Instrument is the sole semantic owner of Instrument Identity.
2. Economic Instrument, Listed Instrument, and Derivative Contract identities shall remain distinct.
3. Provider mapping and cross-Provider reconciliation shall remain exclusively Instrument-owned.
4. Provider Mapping Status shall remain independent from Canonical Identity Decision.
5. Canonical identity may exist without a completed Provider mapping.
6. Provider references, Provider-native identifiers, symbols, exchange tokens, row positions, and Provider tokens shall remain external and non-canonical.
7. Mapping shall preserve Provider attribution and provenance.
8. Analysis, reference, and execution roles shall remain distinct from identity layers.
9. A reference relationship shall never transfer semantic ownership.
10. Underlying relationships shall be explicit and shall never be inferred solely from Provider vocabulary or price behavior.
11. Different derivative expiries shall remain distinct identities.
12. Historical identity shall survive expiry, delisting, retirement, supersession, and Provider-reference change.
13. Provider Mapping Status shall remain distinct from Instrument Lifecycle.
14. Provider Unavailable shall never imply expiry, delisting, retirement, or supersession.
15. A symbol or token change shall never silently reassign canonical identity.
16. Provider-token reuse shall never silently inherit canonical meaning.
17. Continuous futures shall never automatically become a canonical continuous Instrument identity.
18. Continuous futures shall never automatically imply adjusted or rollover-safe history.
19. Instrument Master `last_price` shall never become Current Quote or Observation-owned market state through this architecture.
20. Swing product-universe membership shall never imply canonical identity, Provider mapping, Market availability, Validation acceptance, Risk approval, Execution authority, or Portfolio ownership.
21. Canonical Instrument relationships and roles shall remain Instrument-owned; Swing product-universe membership and consumption shall remain Swing-owned.
22. Provider provenance shall remain distinguishable from Instrument semantic authority.
23. No relationship in this architecture shall create an unapproved domain dependency.
24. No relationship in this architecture shall authorize Provider communication, acquisition, or implementation.
25. Options recognition shall not activate the Options product or any Options capability.
26. The 91 approved NSE cash equities, NIFTY, BANK NIFTY, GOLDM, SILVERM, COPPER, CRUDEOIL, and NATURALGAS shall form the approved 98-member Swing Phase 1 analytical universe; the preceding Gold, Silver, and Copper-only universe boundary is superseded.
27. A Provider Catalogue shall never define canonical Instrument identity or the approved Swing product universe.
28. Unsupported reference coverage shall remain explicitly unsupported.
29. COMEX Listed Instruments and MCX Listed Instruments shall remain distinct even when related to one Economic Instrument.
30. Ambiguous Provider references shall never establish canonical Instrument identity or cross-Provider equivalence.
31. EAIC-002 shall remain the only upstream Provider → Instrument boundary for this scope.
32. Products shall consume mapped canonical identity where mapping is required and shall never perform Provider mapping or cross-Provider reconciliation.
33. Observation shall consume canonical identity only after Instrument processing and shall never participate in mapping.
34. Provider information shall never assign or own an Instrument identity layer, Swing product role, or canonical relationship.
35. The exact Swing product universe may be canonical even though operational contract enumeration and mapping mechanics remain deferred.
36. No role combination shall exist unless the exact combination is established by approved canonical product architecture.
37. Swing product-universe approval shall not finalize a concrete Requested Acquisition Scope, activate ADR-009 or EAIC-002, or authorize runtime, implementation, or EDD-004.

## 19. Architectural Questions

The following 25 Chief Architect-authorized questions are answered one-to-one. WP-B5 updates only the wording required to replace superseded authority and align canonical terminology; answers marked unresolved intentionally reserve later decisions.

| # | Architectural question | Answer | Status |
| ---: | --- | --- | --- |
| 1 | What is the exact approved KRONOS Swing Phase 1 universe? | The approved Swing product universe is the bounded set of 98 analytical subjects: the 91 approved NSE cash equities enumerated by `data/nse/KRONOS_NSE_RELATIONSHIPS.csv`; NIFTY and BANK NIFTY; and GOLDM, SILVERM, COPPER, CRUDEOIL, and NATURALGAS. This supersedes the preceding Gold, Silver, and Copper-only boundary. | Approved definition |
| 2 | Which Economic Instruments are included in the currently approved MCX Metals model? | Gold, Silver, and Copper are included. | Approved base / ADL-001 |
| 3 | Which Listed Instruments and venues are required for each approved Economic Instrument? | Each approved Economic Instrument requires its MCX Listed Instrument for execution context and its corresponding COMEX Listed Instrument for approved global reference context. | Approved definition; exact venue identifiers deferred |
| 4 | Which Derivative Contract categories are in scope? | Individual futures contracts for the approved MCX and COMEX Listed Instruments are in scope; Option contracts remain identity-recognised but capability-inactive. Operational expiry enumeration remains deferred. | Approved base |
| 5 | Are all expiries in the approved venue eligible as reference material, or is the universe further bounded architecturally? | The Swing product universe is further bounded by canonical Instrument meaning, approved product relationship, lifecycle context, and approved reference scope; venue availability alone does not make every expiry eligible for Swing consumption. Operational expiry enumeration remains deferred. | Approved definition |
| 6 | What provider-neutral meanings are required to distinguish an Economic Instrument? | Provider-neutral economic subject, stable identity continuity, approved classification, and explicit relationships are required; price, token, symbol, and Provider availability are insufficient. | Approved base; detailed attributes deferred |
| 7 | What provider-neutral meanings are required to distinguish a Listed Instrument? | Economic relationship, venue/listing context, and distinct listing or trading rules are required; Provider vocabulary alone is insufficient. | Approved base; detailed attributes deferred |
| 8 | What provider-neutral meanings are required to distinguish an individual Derivative Contract? | Underlying relationship, contract category, expiry, applicable venue/listing context, and any approved contract-specific distinction are required; no physical identifier is defined. | Approved base; detailed attributes deferred |
| 9 | Which Provider-supplied reference meanings are mandatory for Instrument interpretation? | Provider context, Provider identifier meaning, Provider exchange or venue assertion, Provider segment or instrument-type assertion, Provider expiry or contract assertion where supplied, Provider provenance, ambiguity, limitation, and missingness are Provider-owned assertions that may be submitted only through EAIC-002. Instrument owns Interpretation Admission, interpretation, canonical identity decision, Provider mapping, and Provider Mapping Status. | Approved definition |
| 10 | Which reference meanings are optional? | Supplementary exchange, relationship, or descriptive context may be optional when separately approved and shall not be required implicitly. | Approved definition |
| 11 | Which Provider fields may remain auxiliary metadata but must not enter Instrument interpretation? | Provider tokens, Provider-supplied last price, catalogue status, technical capability, availability, and other descriptive or technical metadata not required for semantic identity may remain auxiliary. | Approved base / ADP-001A |
| 12 | How do analysis, reference and execution roles relate to the approved identity layers? | They are roles associated with approved Economic Instrument, Listed Instrument, or Derivative Contract identities; roles do not create identity or authority. | Approved definition / ADL-001 |
| 13 | Can one Instrument-owned identity hold more than one approved role? | One canonical Instrument may hold more than one Instrument-owned role only where established by approved architecture: MCX Metals subjects hold Analysis and Intended Execution, while COMEX Metals subjects hold Reference. Swing consumes those roles and does not alter canonical identity or Provider mapping. | Approved definition |
| 14 | Which existing analysis/reference/execution relationships are authoritative for Phase 1? | ADL-001, ENGINE_OWNERSHIP, DATA_FLOW, and the existing MCX Metals relationships are authoritative; this architecture adds none. | Approved base |
| 15 | What reference-market instruments are architecturally required for MCX Metals? | COMEX Gold, COMEX Silver, and COMEX Copper are required reference subjects for the approved MCX Metals model. | Approved definition / ADL-001 |
| 16 | Does approved reference-market coverage require COMEX, NYMEX or another explicitly approved venue? | The approved MCX Metals coverage requires COMEX. NYMEX and other venues are not approved by this architecture. | Approved definition |
| 17 | What is the architectural consequence when the selected Provider cannot supply a required reference-market instrument? | The Swing consumption requirement remains unsatisfied. The condition does not alter canonical identity, Provider Mapping Status, Market state, or authority to substitute another source. | Approved definition |
| 18 | May another source satisfy a required reference relationship, or must source selection remain separately authorized? | Another source may satisfy it only through separately governed Provider acquisition, Instrument-owned mapping, and Swing consumption authority that preserve the same canonical Instrument meaning. | Approved definition |
| 19 | What Provider vocabulary may support interpretation without becoming canonical vocabulary? | Provider identifiers, symbols, names, exchange or segment descriptions, instrument types, expiry descriptions, and Provider provenance may support Instrument interpretation after EAIC-002 admission, but none becomes canonical identity or cross-Provider equivalence. | Approved definition / EAIC-002 |
| 20 | What conditions permit Provider reference information to enter Instrument interpretation? | Provider owns Submission Eligibility. EAIC-002 separately governs technical receipt, contract validation, and Instrument-owned Interpretation Admission. Admission does not establish an Interpretation Outcome, Canonical Identity Decision, Provider Mapping Status, product membership, or Observation authority. | Approved definition / EAIC-002 |
| 21 | How are missing or ambiguous Provider meanings represented during Instrument processing? | Instrument preserves missingness, limitation, ambiguity, and provenance under the independent Interpretation Outcome, Canonical Identity Decision, and Provider Mapping Status meanings. No Provider-native value is forced into canonical identity or mapping. | Approved definition |
| 22 | What exact information is excluded from the first Instrument Master acquisition scope? | ADP-001I establishes only Swing product-universe membership and exclusion. It does not approve Requested Acquisition Scope or activate Acquisition Authority. Concrete acquisition scope remains separately Provider-owned under ADR-009 Version 1.0 and DOMAIN-006; operational acquisition records and Provider tokens or symbols are excluded from the Swing product-universe definition. | Approved definition |
| 23 | How are Options rows kept outside active Phase 1 scope while Option identity remains conceptually recognised? | Option identity remains conceptually recognised under ADP-001B, but Options rows are excluded from active Phase 1 universe membership and no Options retrieval, analytics, validation, strategy, or execution is authorized. | Approved base |
| 24 | Does the approved universe include only MCX execution contracts and their approved references, or any wider instrument set? | The Swing product universe is the approved 98-member analytical set defined in Section 8. It is not a wider Provider Catalogue or an open-ended model-configuration set. Product membership is resolved; Provider-specific resolution and operational contract enumeration remain outside Swing. | Approved definition |
| 25 | What unresolved matters must remain deferred to lifecycle, mapping or acquisition architecture? | Exact identity attributes, contract enumeration, role cardinality details, mapping-effective context and mechanics, lifecycle transitions, source substitution, acquisition scope, and operational treatment remain deferred. Provider mapping ownership, cross-Provider reconciliation ownership, Provider Mapping Status, and independence from Canonical Identity Decision are resolved. | Unresolved |

## 20. Unresolved Architecture Dependencies

This architecture leaves only operational and downstream architecture unresolved:

- operational contract enumeration, including Provider symbols, Provider tokens, expiry enumeration, lifecycle-effective activation, mapping-effective context, and operational acquisition records;
- identity-defining attributes for each instrument class;
- cardinality and effective context of reference and underlying relationships;
- Provider mapping algorithms, persistence, and effective-context mechanics;
- lifecycle transition criteria and authoritative facts;
- symbol continuity and Provider-token reuse treatment in each context;
- continuous-futures identity, adjustment, and rollover semantics;
- approved source and meaning for any future reference or market metadata;
- exact provenance representation and effective-time semantics; and
- any acquisition, authentication, lifecycle, mapping implementation, or engineering capability needed to operationalize these meanings.

Provider mapping ownership, cross-Provider reconciliation ownership, Provider Mapping Status, independence from Canonical Identity Decision, and the fact that canonical identity may exist without completed Provider mapping are resolved by canonical Instrument architecture. No implementation decision may answer an unresolved architectural question.

## 21. Consistency and Dependency Determination

ADP-001I fully resolves the semantic universe and conforms to the approved repository boundaries:

- ADR-009 governs Provider-bounded Instrument Master acquisition and product-neutral Instrument interpretation.
- MIG-001 governs the coordinated repository migration without activating runtime behaviour.
- EAIC-002 is the sole upstream Provider → Instrument boundary for the governed Instrument Master dataset.
- ADP-001A supplies the Phase 1 inventory and mandatory/optional/conditional/future classifications.
- ADP-001B supplies the three Instrument identity layers, lifecycle separation, mapping principles, and historical attribution.
- ADP-001C is superseded and retained only for predecessor traceability.
- ADP-001D governs attribution eligibility without transferring Instrument or Observation ownership.
- ADP-001E assigns factual Observation ownership and preserves fact-versus-interpretation boundaries.
- ADP-001F and ADP-001G retain Configuration and authentication boundaries.
- ADR-009 Version 1.0 and DOMAIN-006 govern Provider-bounded Instrument Master acquisition and Provider Catalogue responsibilities; EAIC-002 Version 0.1 governs the subsequent boundary and ends before Instrument interpretation.
- ADP-001J aligns Instrument interpretation, canonical identity decision, Provider Mapping Status, and Canonical Instrument Catalogue publication.
- ADL-001 and ENGINE_OWNERSHIP preserve existing analysis/reference/execution relationships and engine ownership.
- The Domain Ownership Matrix assigns Provider mapping and cross-Provider reconciliation to Instrument, Provider acquisition and Submission Eligibility to Provider, and product universe and Product Eligibility to Swing.
- The Domain Dependency Matrix permits Instrument to consume EAIC-002 submissions through the approved platform-support dependency and keeps products downstream of Canonical Instrument Catalogue publication.
- DATA_FLOW preserves Provider → EAIC-002 → Instrument → explicit product consumption and keeps Observation downstream of Instrument processing.

No ownership conflict, new dependency, Provider leakage, implementation leakage, or shared semantic authority is introduced by this architecture.

## 22. ADR Determination

No additional ADR is required for this migration because ADR-009 governs the Provider-bounded acquisition, canonical Instrument interpretation, and explicit product-consumption architecture. Further ADR authority is required if a future proposal would add a domain dependency, reassign ownership, activate Options, alter the approved identity layers, authorize continuous-futures semantics, or change an approved boundary.

## 23. Deferred Capabilities

The following remain deferred and unauthorized. ADP-001I establishes only Swing product-universe membership, explicit consumption of approved Instrument-owned roles and relationships, and semantic exclusion; it does not approve Requested Acquisition Scope, activate Acquisition Authority, or authorize mapping implementation. Concrete acquisition scope remains separately Provider-owned and governed by ADR-009 Version 1.0 and DOMAIN-006.

- operational contract enumeration, including Provider symbols, Provider tokens, expiry enumeration, lifecycle-effective activation, mapping-effective context, and operational acquisition records;
- Provider Instrument Master acquisition beyond the authority of ADR-009 Version 1.0 and DOMAIN-006;
- Provider mapping implementation, algorithms, persistence, and effective-context mechanics;
- EAIC-002 runtime communication or activation;
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

**Review History:** ADP-001I was drafted under Chief Architect authorization as a provider-neutral Phase 1 semantic architecture. Version 1.0 incorporates Chief Architect amendments CA-001 through CA-005, closes Engineering findings EA-001 through EA-009, and has completed Engineering Architect verification. It is approved as canonical architecture. WP-B5 aligned ADP-001I with ADR-009, EAIC-002, the migrated Instrument and Provider domains, and the Instrument-owned Provider mapping architecture. Implementation, acquisition, Provider communication, EDD, Engineering Package, EDD-004, and follow-on capability remain unauthorized.

## Related Approved Authority

- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [ADP-001A — Swing Phase 1 Market Data Inventory](SWING-PHASE-1-MARKET-DATA-INVENTORY.md)
- [ADP-001B — KRONOS Swing Instrument Identity Architecture](SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md)
- [ADP-001C — Superseded Provider → Instrument Contract (historical predecessor)](SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md)
- [ADP-001D — Instrument → Observation Contract](SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md)
- [ADP-001E — Observation Domain Architecture](SWING-PHASE-1-OBSERVATION-DOMAIN-ARCHITECTURE.md)
- [ADP-001F — Configuration → Provider Runtime Configuration Boundary](SWING-PHASE-1-CONFIGURATION-PROVIDER-RUNTIME-CONFIGURATION-BOUNDARY.md)
- [ADP-001G — Configuration → Provider Authentication Boundary](SWING-PHASE-1-CONFIGURATION-PROVIDER-AUTHENTICATION-BOUNDARY.md)
- [ADP-001H — Superseded Provider Instrument Master Acquisition predecessor (historical traceability only)](SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md)
- [ADP-001J — Instrument Interpretation and Canonical Identity Establishment Architecture](SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md)
- [Provider Domain Architecture](../../platform/domains/provider/ARCHITECTURE.md)
- [Instrument Domain Architecture](../../platform/domains/instrument/ARCHITECTURE.md)
- [ADL-001 — Futures Model Architecture](../../ADL-001-Futures-Model.md)
- [Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [KRONOS Engine Ownership](../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../DATA_FLOW.md)
