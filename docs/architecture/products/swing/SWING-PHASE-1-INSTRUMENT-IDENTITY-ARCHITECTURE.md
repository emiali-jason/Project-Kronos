# ADP-001B — KRONOS Swing Instrument Identity Architecture

**Status:** Approved

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Owner:** Chief Architect

**Prepared By:** Engineering Architect

**Approved By:** Chief Architect

**Classification:** Architecture Documentation Package

**Architecture Impact:** Approved canonical elaboration of Instrument Identity architecture

**Engineering Impact:** None

**Runtime Impact:** None

## 1. Document Status and Governance

This document is the approved canonical Version 1.0 Architecture Documentation Package. It does not authorize implementation, retrieval, contracts, Engineering Design Documents, Engineering Packages, or runtime changes.

The following labels govern this document:

- **Approved base** identifies architecture already approved elsewhere in the repository.
- **Chief Architect-approved decision** identifies architecture approved by the Chief Architect.
- **Unresolved** identifies questions for which this document supplies no answer.

The Chief Architect initially approved ADP-001B with required amendments. Those amendments were incorporated, the Engineering Architect verified conformance, and the repository metadata and indexes were updated. ADP-001B is now approved as canonical Version 1.0.

## 2. Purpose

Define the Chief Architect-approved provider-neutral architecture for KRONOS Swing Instrument Identity within Phase 1 — Market Data Foundation while preserving the approved ownership of Instrument, Provider, Observation, Market, and Configuration.

This document records the approved separation of Economic Instrument, Listed Instrument, and Derivative Contract identities and clarifies their relationships to Provider references, mappings, and lifecycle concepts. It does not define their implementation.

## 3. Architectural Problem

KRONOS must attribute market information to the correct instrument without allowing provider tokens, symbols, runtime configuration, provider availability, market schedules, or observed prices to become Instrument Identity.

The approved architecture assigns Instrument Identity to Instrument, Provider Integration to Provider, Market Facts to Observation, Market Schedule to Market, and Runtime Configuration to Configuration. ADP-001A additionally requires provider-to-canonical mapping inputs, futures lifecycle identity, provider-token change handling, and historical attribution while prohibiting silent ownership transfer.

The approved identity layering resolves the provider-neutral conceptual model. Detailed identity-defining meanings, relationship cardinality, lifecycle-establishing facts, and mapping effective context remain unresolved.

## 4. Scope

This document covers only architectural meaning for:

- Economic Instrument identity;
- Listed Instrument identity;
- stable identity;
- instrument classification;
- listing and venue context;
- derivative contract identity;
- underlying relationships;
- provider instrument references;
- provider identifier mappings;
- instrument lifecycle concepts;
- identity invariants; and
- identity ownership and attribution.

The current approved Swing scope remains unchanged. MCX Metals remains the currently supported model. Planned models, reference coverage, and provider availability do not expand the approved universe.

## 5. Out of Scope

This document does not define or authorize:

- retrieval behavior or Instrument Reference Retrieval;
- synchronization, scheduling, caching, persistence, or storage;
- databases, tables, schemas, payloads, APIs, or lookup services;
- symbol parsing, matching algorithms, mapping algorithms, or collision resolution;
- market observations, quote fields, candles, Open Interest, or data-quality judgment;
- Market Schedule or Exchange Availability semantics;
- runtime configuration or provider availability;
- continuous-futures construction, adjustment, rollover, or replacement policy;
- TradingView integration;
- corporate-action processing;
- active Options-product architecture, option-chain capabilities, options retrieval, options analytics, option valuation, option scoring, option validation, option strategy, and option execution;
- validation, ranking, trading decisions, execution, orders, positions, or automated trading; or
- implementation sequencing, an EDD, an Engineering Package, or an ADR.

Future-compatible identity semantics for an individual option contract are within the conceptual identity boundary of this document only. Their inclusion does not activate the KRONOS Options product or authorize any Options capability.

## 6. Terminology

| Term | Architectural meaning in this document | Authority |
| --- | --- | --- |
| Instrument Identity | The authoritative semantic meaning that answers what instrument is being referenced. Economic Instrument, Listed Instrument, and Derivative Contract are Instrument-owned canonical semantic identities within their respective layers. | Approved base and Chief Architect-approved layering. |
| Economic Instrument | The provider-neutral economic identity. It is distinct from its listings and derivative contracts. | Chief Architect-approved decision. |
| Listed Instrument | The venue- and listing-specific identity. Venue may define listed identity. | Chief Architect-approved decision. |
| Derivative Contract | The individual contract-expiry identity. Different expiries are distinct identities. | Chief Architect-approved decision. |
| Stable Identity | Identity continuity that is not silently replaced by a provider identifier, symbol change, or provider-record change. | Chief Architect-approved direction; detailed continuity rules remain unresolved. |
| Underlying Relationship | An explicit semantic relationship between a Derivative Contract and the Economic Instrument or market reference it derives from. | Chief Architect-approved direction; detailed semantics remain unresolved and existing approved analysis/reference/execution relationships remain preserved. |
| Provider Instrument Reference | Provider-owned external and non-canonical reference material, including provider-specific identifiers and records. | Approved base and Chief Architect-approved boundary. |
| Provider Identifier Mapping | An Instrument-owned governed semantic association between one Provider-specific Instrument Reference and one Instrument-owned identity. A mapping is potentially time-bounded and must preserve historical attribution. | Chief Architect-approved principles; detailed effective-context semantics remain unresolved. |
| Provider Mapping State | Provider-owned state describing access to a Provider Instrument Reference or mapping. It is not Instrument Lifecycle. | Chief Architect-approved decision. |
| Provider Unavailable | A Provider Mapping State meaning that a particular Provider does not currently supply or expose the relevant Provider Instrument Reference or mapping. | Chief Architect-approved decision; no runtime detection is defined. |
| Market Observation | A factual market observation attributed to Instrument Identity. | Approved base; Observation-owned. |
| Market Schedule | Authoritative session or schedule meaning. | Approved base; Market-owned. |

Terminology in this document defines no contract fields or runtime representation.

## 7. Identity Model

The Chief Architect has approved three separate Instrument-owned semantic identity layers and one external reference boundary:

1. **Economic Instrument** is the provider-neutral economic identity.
2. **Listed Instrument** is the venue- and listing-specific identity.
3. **Derivative Contract** is the individual contract-expiry identity.
4. **Provider Instrument Reference** remains outside the canonical identity layers as an external, non-canonical, Provider-owned representation.

The approved conceptual relationship is:

```text
Economic Instrument
        │
        ▼
Listed Instrument
        │
        ▼
Derivative Contract
```

These layers must not be collapsed. All three are Instrument-owned canonical semantic identities within their respective layer. Future architecture may reuse these layers. This is a semantic model, not a physical identifier, payload hierarchy, class hierarchy, schema, or storage model.

Observations refer to an approved Instrument Identity Contract. They do not create identity. Provider records support mapping but do not become canonical merely because they are available.

## 8. Instrument Classes and Identity Levels

Two different classifications must remain separate:

### Approved role classification

The approved Instrument Domain preserves the distinction between:

- analysis instruments;
- reference instruments; and
- execution instruments.

These are architectural roles and must preserve the relationships already approved by ADL-001 and existing engine ownership. A role does not authorize data retrieval, analysis, or execution.

### Approved identity layers

Economic Instrument, Listed Instrument, and Derivative Contract are separate Chief Architect-approved semantic identity layers. They do not replace the approved analysis/reference/execution roles.

The approved Phase 1 identity classification distinguishes:

- **Equity**;
- **Index**;
- **ETF**;
- **Commodity**;
- **Currency**;
- **Future**; and
- **Option** as identity-recognized but capability-inactive.

The exact canonical taxonomy and identity-defining meanings for these classes remain unresolved.

Recognition of Option as identity-recognized but capability-inactive does not activate the KRONOS Options product and does not authorize option retrieval, option-chain capabilities, analytics, valuation, validation, strategy, or execution.

## 9. Economic Instrument Identity

**Approved base:** Instrument is the sole owner of Instrument Identity, classification, approved relationships, lifecycle meaning, and provider-to-canonical mapping meaning.

**Chief Architect-approved decision:** Economic Instrument is the provider-neutral economic identity. It is distinct from Listed Instrument and Derivative Contract identity, and the three layers must not be collapsed.

Economic Instrument identity must remain sufficiently stable to preserve attribution when Provider identifiers or Provider records change. It shall not be defined by current price, Market Schedule, Provider availability, or runtime configuration. Detailed identity-defining meanings for each approved instrument class remain unresolved.

## 10. Listed-Instrument Identity

**Chief Architect-approved decision:** Listed Instrument is the venue- and listing-specific identity. Venue creates a distinct Listed Instrument whenever trading rules differ, exchange identity differs, or the listing differs.

Venue does not merely decorate identity; venue may define Listed Instrument identity. For example, MCX Gold and COMEX Gold may be related through an Economic Instrument but are not the same Listed Instrument.

Venue identity does not give Instrument ownership of Market Schedule or Exchange Availability. It also does not make a Provider's exchange or segment vocabulary canonical without review. Detailed multi-listing relationship cardinality and identity-continuity rules remain unresolved and must not be inferred from matching names or symbols.

## 11. Derivative Contract Identity

**Approved base:** Futures expiry and lifecycle identity are required by ADP-001A, and approved analysis/reference/execution distinctions in ADL-001 remain preserved.

**Chief Architect-approved decision:** Each expiring derivative contract is an individual canonical semantic identity distinct from its underlying relationship and from every other expiry. Historical identity survives expiry and must not be silently replaced by a successor contract or continuous representation.

Conceptual derivative-contract identity may require, where applicable:

- underlying reference;
- contract type;
- expiry;
- exchange;
- segment;
- strike; and
- option side.

Strike and option side apply only to future-compatible option-contract identity. Their recognition here does not define option schemas, option-type values, strike formats, option-chain relationships, parsing, valuation, analytics, retrieval, validation, strategy, or execution.

This document defines no rollover rule, front-contract rule, replacement rule, adjustment method, continuous series, active Options-product architecture, or operational Options capability.

## 12. Underlying Relationships

**Chief Architect-approved direction:** Underlying relationships are explicit Instrument-owned semantic relationships. They must not be inferred solely from Provider symbols, naming patterns, configuration, or price behavior.

An underlying relationship does not merge the identities of the related instruments. Existing approved analysis, reference, and execution relationships remain authoritative and are not expanded by this document.

The permissible cardinality and exact semantics of underlying relationships remain unresolved.

## 13. Provider Instrument References

Provider owns provider-specific identifiers, records, provenance, capability, and availability.

Provider Instrument References:

- are external reference material;
- may support Instrument identification through a future approved contract;
- retain provider provenance;
- remain outside the three canonical identity layers and do not become Economic Instrument, Listed Instrument, or Derivative Contract identity automatically;
- do not establish Instrument lifecycle meaning;
- do not establish Market Facts or Market Schedule; and
- do not transfer provider ownership to Instrument.

Instrument Master `last_price` is auxiliary Provider metadata under ADP-001A. It is not Economic Instrument, Listed Instrument, Derivative Contract, Current Quote, or Observation-owned market state.

## 14. Provider Identifier Mappings

The approved ownership distinction is:

- Provider owns the provider-specific identifier and source record.
- Instrument owns the semantic meaning of its association with the applicable Instrument-owned identity layer.

**Chief Architect-approved principle:** A Provider mapping must preserve Provider provenance and must not allow a Provider identifier to replace an Economic Instrument, Listed Instrument, or Derivative Contract identity. Mapping changes must remain explainable and must not silently reassign historical observations.

**Chief Architect-approved principle:** Provider identifiers must always be interpreted within their Provider context. Provider mappings are potentially time-bounded, and the architecture must not assume perpetual validity. Where Provider reuse, reassignment, lifecycle change, or historical attribution requires it, the mapping must also be interpreted within an effective-time or lifecycle context.

An Instrument-owned identity may have zero, one, or multiple Provider mappings. The existence, absence, replacement, or expiry of a Provider mapping does not create or delete an Economic Instrument, Listed Instrument, or Derivative Contract identity.

Within the same applicable Provider and effective context, one Provider mapping must not resolve ambiguously to multiple active Instrument-owned identities. Ambiguity must prevent canonical attribution until resolved through separately approved architecture.

**Frozen approved principle:** Historical Provider mappings shall remain attributable after a Provider token, symbol, reference, or contract record changes, disappears, is reassigned, or is no longer current.

These are semantic requirements only. This document does not define mandatory timestamp fields, what constitutes an effective period, how conflicts are detected, or how mapping history is stored or processed.

This document does not define mapping fields, lookup behavior, synchronization, reconciliation algorithms, conflict-resolution algorithms, or persistence. A Provider → Instrument Contract is required before cross-domain mapping information can be exchanged.

## 15. Instrument Lifecycle and Provider Mapping State

ADP-001A approves the need to preserve futures expiry, lifecycle identity, Provider-token changes, and historical attribution. The Chief Architect has approved the following Instrument Lifecycle vocabulary without defining a state machine.

### Instrument Lifecycle

- **Prospective:** an instrument or contract is known or announced but is not yet active within its intended listed or tradable lifecycle context. This does not authorize retrieval, observation, validation, or trading.
- **Active:** the identity is active within its applicable instrument lifecycle context. Active does not mean that the market is open, a Provider is available, current data exists, or trading is authorized.
- **Expired:** a Derivative Contract has reached its contractual expiry. Expiry ends its applicable active contract lifecycle, but historical identity survives expiry and remains attributable.
- **Retired:** the applicable Instrument-owned identity is no longer current for approved use but remains preserved for historical attribution. Operational retirement criteria are not defined here.
- **Delisted:** the Listed Instrument is no longer listed at its venue. Delisting remains distinct from expiry, retirement, supersession, Provider disappearance, and Provider failure.
- **Superseded:** a distinct identity has an explicitly governed successor or replacement relationship. Supersession does not merge identities or transfer historical observations.

Successor relationships are conceptually part of Phase 1 identity architecture but are not operationally defined. They connect distinct identities, do not merge identities, do not transfer historical observations, and do not create continuous futures. Their detailed semantics, discovery, maintenance, and operational processing remain undefined.

### Provider Mapping State

- **Provider Unavailable:** a particular Provider does not currently supply or expose the relevant Provider Instrument Reference or mapping.

Provider Mapping State does not become Instrument Lifecycle. Provider Unavailable does not imply expiry, delisting, retirement, or supersession. It does not delete an Economic Instrument, Listed Instrument, Derivative Contract, or historical Provider mapping. Provider availability remains Provider-owned.

The following supporting concepts remain recognised:

- **Recognition:** an instrument becomes known within an approved universe without implying retrieval or trading support.
- **Historical identity:** an expired, retired, delisted, superseded, or otherwise no-longer-current identity remains identifiable for previously attributed facts.
- **Provider-reference change:** a Provider reference changes, disappears, reappears, or is replaced without automatically changing an Instrument-owned identity.
- **Successor relationship:** an acknowledged relationship connects distinct identities without merging them or creating continuous-futures identity.

The applicability details of lifecycle concepts across the three identity layers, authoritative establishing facts, transition criteria, and operational lifecycle model remain unresolved.

No state machine, transition behavior, availability monitoring, health check, detection, persistence, synchronization, successor discovery, maintenance procedure, or operational processing is authorized.

## 16. Identity Invariants

### Approved repository invariants

1. Instrument Identity has one semantic owner: Instrument.
2. Provider-specific identifiers and records are external and non-canonical; they are not Economic Instrument, Listed Instrument, or Derivative Contract identity.
3. Observation consumes Instrument Identity and does not create or reinterpret it.
4. Identity is not Market State, Market Schedule, or Exchange Availability.
5. Identity is not Runtime Configuration.
6. Identity is not Provider availability or Provider capability.
7. Provider tokens are not permanent KRONOS identities.
8. Missing data and data availability do not establish identity or lifecycle state.
9. Historical identity and attributed observations survive expiry and remain attributable.
10. Approved analysis/reference/execution relationships retain Instrument ownership.

### Chief Architect-approved ADP-001B invariants

1. **Provider Neutrality:** provider representation must not define canonical meaning.
2. **Identity Before Observation:** an observation must be attributable to approved Instrument Identity.
3. **Identity Is Not Market State:** identity must remain separate from observations and session meaning.
4. **Identity Is Not Configuration:** configuration may select approved behavior but must not create identity.
5. **Identity Is Not Provider Availability:** connectivity or provider state must not create, remove, or reinterpret identity.
6. **Explicit Lifecycle:** identity continuity and change must be explicit.
7. **No Silent Identity Reuse:** a reused or changed Provider identifier must not silently reassign canonical meaning or historical attribution.
8. **Explainable Attribution:** the instrument to which a fact is attributed must be explainable through approved identity and mapping meaning.
9. **Single Ownership:** no other domain may duplicate Instrument's identity semantics.
10. **Provider Context:** a Provider identifier has meaning only within the context of the Provider that issued or supplied it.
11. **Potentially Time-Bounded Mapping:** Provider mappings are potentially time-bounded, and the architecture must not assume perpetual validity. Where identifier reuse, reassignment, lifecycle, or historical attribution requires it, a mapping must be interpreted within an effective-time or lifecycle context.
12. **Unambiguous Active Mapping:** one Provider mapping must not resolve ambiguously to multiple active Instrument-owned identities within the same applicable context.
13. **Mapping Cardinality:** an Instrument-owned identity may have zero, one, or multiple Provider mappings.
14. **Mapping Independence:** loss, expiry, replacement, or absence of a Provider mapping does not delete an Economic Instrument, Listed Instrument, or Derivative Contract identity.
15. **Historical Mapping Attribution:** historical Provider mappings shall remain attributable after identifiers or symbols change.
16. **Identity Layer Separation:** Economic Instrument, Listed Instrument, and Derivative Contract are distinct Instrument-owned semantic identity layers and must not be collapsed.
17. **Contract Distinction:** Derivative Contracts with different expiries have different identities, and historical identity survives expiry.
18. **Venue-Defined Listing:** venue creates a distinct Listed Instrument when trading rules, exchange identity, or the listing differs.
19. **Symbol Continuity Is Not Automatic:** a symbol change does not automatically create a new Instrument-owned identity.
20. **No Identity Inheritance by Reuse:** a materially different instrument must not inherit an existing Instrument-owned identity solely because a Provider symbol or identifier was reused.
21. **Provider Provenance:** Provider-originated identity claims and references require Provider provenance.
22. **Lifecycle and Mapping-State Separation:** Provider Mapping State is not Instrument Lifecycle, and Provider Unavailable does not imply or alter lifecycle status.
23. **Successor Separation:** successor relationships connect distinct identities without merging identities, transferring historical observations, or creating continuous futures.

These decisions form part of canonical Version 1.0.

## 17. Domain Ownership

| Domain | Approved ownership relevant to this document |
| --- | --- |
| Instrument | Economic Instrument, Listed Instrument, and Derivative Contract identity; identity semantics; classification; approved relationships; lifecycle semantics; Provider mapping meaning; and identity invariants. |
| Provider | Provider-specific identifiers, Provider Instrument References, Provider records, Provider provenance, Provider capability, Provider availability, and Provider Mapping State. |
| Observation | Market observations attributed to approved Instrument Identity. |
| Market | Market Schedule, session semantics, and explicit Exchange Availability where authorized. |
| Configuration | Runtime configuration only; configurable values do not acquire identity semantics. |

No new domain or ownership assignment is introduced.

## 18. Permitted Responsibilities

Within approved architecture, Instrument may:

- define authoritative instrument identity and classification;
- preserve approved analysis/reference/execution relationships;
- define lifecycle and mapping meaning within approved architectural semantics;
- publish Instrument Identity through an approved contract; and
- preserve explainable attribution across approved lifecycle changes.

Provider may supply provider references and provenance through an approved platform contract. Observation may consume approved identity to attribute facts. Market and Configuration retain their separate approved responsibilities.

These permissions do not authorize runtime work from this document.

## 19. Prohibited Responsibilities

Instrument must not:

- acquire Provider Integration, Provider availability, or provider provenance ownership;
- acquire Market Facts, quote, candle, OI, or factual data-quality ownership;
- acquire Market Schedule or Exchange Availability ownership;
- acquire Runtime Configuration ownership;
- infer identity from current price, missing data, provider connectivity, or session state;
- perform retrieval, persistence, synchronization, caching, or transport;
- create Validation judgment, trading decisions, execution authority, orders, or positions; or
- expand the approved universe, activate Options capability, or create new analysis/reference/execution relationships.

Provider, Observation, Market, and Configuration must not recreate or override Instrument Identity.

## 20. External Architectural Relationships

| Relationship or capability | Treatment in ADP-001B |
| --- | --- |
| Provider → Instrument Contract | Required future contract; referenced but not defined or approved here. |
| Provider → Observation Contract | Required future contract for factual acquisition; referenced but not defined here. |
| Instrument Reference Retrieval Capability | Future Provider capability; not authorized or designed here. |
| Historical Observation Architecture | Future Observation architecture dependent on approved identity; not defined here. |
| Current Quote Architecture | Mandatory dataset area under ADP-001A; future architecture not defined here. |
| Instrument Lifecycle Capability | Future capability dependent on approved lifecycle semantics; not defined here. |
| Successor Relationships | Conceptually part of Phase 1 identity architecture; detailed semantics, discovery, maintenance, and operational processing are not defined here. |
| Continuous Futures Architecture | Conditional under ADP-001A and requires separate approval. |
| TradingView Integration | Excluded from Phase 1 and not defined here. |
| Corporate Actions | Future phase under ADP-001A and not defined here. |
| Options Architecture | Future consumer of the identity foundation for underlyings and individual option contracts; excluded from active Phase 1 product engineering and not defined here. |

No architecture assumption is made about Kite's long-term COMEX or NYMEX coverage. Provider capability belongs to Provider, Instrument Identity remains Provider-neutral, and source coverage is deferred to Provider capability architecture.

## 21. Architectural Traceability

### Principles originating from ADP-001A

- approved Instrument Master and provider-to-canonical mapping information boundary;
- canonical attribution requirement;
- futures expiry and lifecycle identity;
- Provider-token change handling;
- historical attribution;
- Provider tokens being non-canonical and non-permanent; and
- separation of Instrument Master metadata from Current Quote and Observation-owned market state.

### Principles newly established by ADP-001B

- Economic Instrument, Listed Instrument, and Derivative Contract as separate identity layers;
- venue context may define Listed Instrument identity;
- each Derivative Contract expiry is a distinct identity;
- historical identity survives expiry;
- Options are identity-recognized but capability-inactive;
- Instrument Lifecycle is distinct from Provider Mapping State;
- Provider mappings are potentially time-bounded;
- historical Provider mappings remain attributable;
- successor relationships are conceptually acknowledged; and
- Provider Instrument References remain external and non-canonical.

### Future capabilities dependent on ADP-001B

- ADP-001C — Provider → Instrument Contract;
- Instrument Identity Contract;
- Instrument Lifecycle capability or architecture;
- Provider Instrument Reference Retrieval capability;
- Historical Observation Architecture;
- Current Quote Architecture;
- Continuous Futures Architecture where separately approved; and
- future Options Architecture as a consumer of the identity foundation.

This traceability creates no implementation sequence or runtime authorization.

## 22. Dependencies

ADP-001B depends on the approved Platform Constitution, ownership and dependency matrices, Instrument Domain architecture, ADP-001A, existing engine ownership, data flow, and approved futures relationships.

Future realization depends on separately approved contracts and capabilities listed in Architectural Traceability. ADP-001C is authorized for architecture documentation only and does not yet define or authorize Provider → Instrument communication.

Instrument has no business-domain dependency. Platform-supplied Provider values may support identification only through an approved contract and do not transfer identity ownership.

No ADR is required for ADP-001B because it elaborates approved architecture, does not alter domain ownership, does not create a domain, and does not change platform principles. Future operational capabilities may require separate architectural review.

## 23. Unresolved Architectural Questions

1. Which exact provider-neutral reference meanings are required within each approved identity layer?
2. What detailed relationship cardinality applies among Economic Instrument, Listed Instrument, Derivative Contract, and underlying relationships beyond the approved three-layer separation?
3. Which authoritative facts establish each Instrument Lifecycle status?
4. How do the approved lifecycle concepts apply in detail across Economic Instrument, Listed Instrument, and Derivative Contract identity?
5. Which facts establish the beginning and end of a Provider mapping's effective context?
6. What detailed ambiguity conditions require canonical attribution to be blocked?
7. Which facts determine identity continuity when a symbol or listing changes?
8. What are the detailed semantics, discovery, and maintenance rules for successor relationships?
9. Which approved ADL-001 relationships are activated in Phase 1 beyond the already approved scope?

Engineering must not answer these questions by implementation or inference. Operational lifecycle processing, mapping procedures, successor discovery, and Provider capability remain deferred to later architecture.

## 24. Conformance with ADP-001A

ADP-001B conforms to ADP-001A as follows:

- It preserves the Mandatory classification of approved Instrument Master reference data and provider-to-canonical mapping inputs.
- It preserves canonical attribution, futures expiry/lifecycle identity, Provider-token change handling, and historical attribution as required identity concerns.
- It preserves approved analysis, reference, and execution instrument roles without adding relationships.
- It treats Provider tokens as external, non-canonical, and non-permanent.
- It preserves Provider-token change handling and historical mapping attribution without treating a current Provider token or symbol as permanent canonical identity.
- It treats Instrument Master `last_price` only as auxiliary Provider metadata.
- It keeps Current Quote and historical observations under Observation ownership.
- It keeps Market Schedule under Market ownership and Provider availability under Provider ownership.
- It does not redefine any dataset, classification, retrieval authority, or completion criterion in ADP-001A.
- It preserves the exclusion of active Options-product capability, TradingView, persistence, streaming, execution, orders, positions, and automated trading while retaining identity-recognized but capability-inactive Option identity semantics.

ADP-001B elaborates Instrument Identity architecture only. It does not amend ADP-001A.

## 25. Follow-on Architecture

**Next Chief Architect-authorized capability:** ADP-001C — Provider → Instrument Contract

**Objective:** Define the governed architectural contract through which Provider-supplied instrument reference information becomes eligible for interpretation by the Instrument domain.

Authorization is for architecture documentation only. ADP-001C does not authorize implementation, retrieval, runtime Provider-to-Instrument communication, an EDD, or an Engineering Package.

Later dependent architecture may address the Instrument Identity Contract, Instrument Lifecycle capability or architecture, Provider Instrument Reference Retrieval capability, Historical Observation Architecture, Current Quote Architecture, Continuous Futures Architecture where separately approved, and future Options Architecture as a consumer of the identity foundation.

ADP-001C is the next authorized architectural capability; the later dependencies are not competing next packages. This section creates no contract, implementation order, runtime authority, or engineering authorization.

## 26. Approval Record

**Chief Architect Decision:** Approved

**Engineering Architect Verification:** Complete

**ADR Required:** No

**Canonical Status:** Version 1.0

**Next Authorized Capability:** ADP-001C — Provider → Instrument Contract

**Review History:** The Chief Architect initially approved ADP-001B with required amendments. The amendments were incorporated, Engineering Architect conformance verification completed, and repository metadata and indexes were updated before final canonicalization.

ADP-001C is architecture-only and does not authorize implementation, retrieval, runtime Provider-to-Instrument communication, an EDD, or an Engineering Package. ADP-001C has not been created by this document.

## Related Approved Authority

- [PLATFORM-000 — KRONOS Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [KRONOS Platform Overview](../../platform/PLATFORM_OVERVIEW.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [Instrument Domain](../../platform/domains/instrument/ARCHITECTURE.md)
- [Provider Domain](../../platform/domains/provider/ARCHITECTURE.md)
- [Observation Domain](../../platform/domains/observation/ARCHITECTURE.md)
- [Market Domain](../../platform/domains/market/ARCHITECTURE.md)
- [Configuration Domain](../../platform/domains/configuration/ARCHITECTURE.md)
- [ADP-001A — Swing Phase 1 Market Data Inventory](SWING-PHASE-1-MARKET-DATA-INVENTORY.md)
- [ADL-001 — Futures Model Architecture](../../ADL-001-Futures-Model.md)
- [EAIC-001 — Exchange Availability Interface Contract](../../interfaces/EAIC-001-Exchange-Availability-Interface-Contract.md)
- [KRONOS Engine Ownership](../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../DATA_FLOW.md)
