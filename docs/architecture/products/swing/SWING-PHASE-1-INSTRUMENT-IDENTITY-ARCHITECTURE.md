# ADP-001B — KRONOS Swing Instrument Identity Architecture

**Document ID:** ADP-001B
**Title:** KRONOS Swing Instrument Identity Architecture
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Approved Canonical Architecture

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Owner:** Chief Architect

**Prepared By:** Engineering Architect

**Approved By:** Chief Architect
**Review Authority:** Not stated
**Repository Location:** `docs/architecture/products/swing/SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md`

**Classification:** Architecture Documentation Package

**Architecture Impact:** Approved product-neutral canonical Instrument Identity architecture aligned with ADR-009 and EAIC-002

**Engineering Impact:** None

**Runtime Impact:** None

## 1. Document Status and Governance

This document is the approved canonical Version 1.0 Architecture Documentation Package. It does not authorize implementation, retrieval, contracts, Engineering Design Documents, Engineering Packages, or runtime changes.

This migrated version aligns ADP-001B with ADR-007, ADR-008, ADR-009, MIG-001, EAIC-002, the migrated Provider and Instrument Domain architectures, the Domain Ownership Matrix, the Domain Dependency Matrix, DATA_FLOW, and the supersession of ADP-001C and ADP-001H. ADP-001H remains historical predecessor traceability only.

ADR-009 governs Provider-bounded acquisition and product-neutral Instrument interpretation.

EAIC-002 is the sole current canonical Provider → Instrument submission contract. Superseded ADP-001C is retained only for historical predecessor traceability and supplies no active authority.

The Swing placement and metadata of ADP-001B do not make Swing the owner, scope source, prerequisite, or filter for canonical Instrument identity.

Nothing in this migration activates ADR-009 or EAIC-002 or authorizes acquisition, submission, implementation, runtime behavior, an EDD, an Engineering Package, or EDD-004.

## 2. Purpose

Define the Chief Architect-approved product-neutral architecture for canonical KRONOS Instrument Identity while preserving the approved ownership of Instrument, Provider, Observation, Market, Configuration, and applicable products.

This document records the approved separation of Economic Instrument, Listed Instrument, and Derivative Contract identities and clarifies their relationships to Provider references, mappings, reconciliation, lifecycle concepts, the Canonical Instrument Catalogue, and explicit downstream product consumption. It does not define their implementation.

## 3. Architectural Problem

KRONOS must attribute market information to the correct instrument without allowing provider tokens, symbols, runtime configuration, provider availability, market schedules, or observed prices to become Instrument Identity.

The approved architecture assigns interpretation, canonical Instrument Identity, canonical classification, Provider mapping, cross-Provider reconciliation, and the Canonical Instrument Catalogue to Instrument. It assigns Provider acquisition, the Provider Catalogue, Provider records, Provider Record Identity, Provider dispositions, Submission Eligibility, acquisition scope, outcomes, and Provider provenance to Provider. Market Facts remain Observation-owned, Market Schedule remains Market-owned, Runtime Configuration remains Configuration-owned, and each product owns only its product universe, eligibility, and explicit consumption.

Provider information may enter Instrument only through EAIC-002 after the independently governed Provider conditions are satisfied. Receipt, contract validation, Interpretation Admission, interpretation, canonical identity decision, and Provider mapping status remain separate meanings.

The approved identity layering resolves the provider-neutral conceptual model. Detailed identity-defining meanings, relationship cardinality, lifecycle-establishing facts, and mapping effective context remain unresolved where later canonical architecture has not resolved them.

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
- cross-Provider reconciliation;
- product-neutral Canonical Instrument Catalogue meaning;
- instrument lifecycle concepts;
- identity invariants; and
- identity ownership and attribution.

Canonical Instrument Identity is product-neutral. It shall not depend on Swing or Intraday membership, a current product universe, product eligibility, product demand, current strategy, current execution market, current implementation, or current Observation availability.

Swing, Intraday, and future products consume canonical Instrument outputs only through separately approved explicit product-consumption boundaries. Product membership and eligibility do not alter Provider acquisition, Instrument interpretation, canonical identity, Provider mapping, or Canonical Instrument Catalogue state.

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

Future-compatible identity semantics for an individual option contract are within the conceptual identity boundary of this document only. Their inclusion does not activate the KRONOS Options product, authorize any Options capability, or add Options data to the Instrument Master dataset.

Provider Capability Assessment, Provider Entitlement Assessment, Dataset Permission, Acquisition Authority, Submission Eligibility, Provider-to-Instrument Submission Authority, EAIC-002 activation, and product eligibility remain separately governed.

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
| Provider Mapping Status | Instrument-owned meaning describing the result or deferral of one bounded Provider mapping evaluation. It is independent from Canonical Identity Decision and Instrument Lifecycle. | ADR-009 and migrated Instrument Domain architecture. |
| Provider Operational Availability | Provider-owned evidence-based meaning concerning whether Provider operation relevant to an approved Provider Context can be established. It is not Provider Mapping Status or Instrument Lifecycle. | ADR-009 and migrated Provider Domain architecture. |
| Provider Catalogue | The first-class Provider-owned platform artifact composed of isolated Provider-and-Dataset Catalogue Partitions containing Provider Snapshots, Provider Records, dispositions, currentness, supersession, scope, outcomes, and non-sensitive provenance. | ADR-009 and migrated Provider Domain architecture. |
| Provider Record Identity | Provider-owned identity unique only within one Provider Snapshot. It is not canonical Instrument Identity and does not establish cross-snapshot or cross-Provider continuity. | ADR-009 and EAIC-002. |
| Interpretation Admission | The EAIC-002 boundary meaning that contract-valid Provider information may enter Instrument interpretation. It does not imply interpretation success, canonical identity, Provider mapping, or product eligibility. | EAIC-002. |
| Canonical Instrument Catalogue | The product-neutral Instrument-owned publication of approved canonical Instrument meaning. It may contain Instruments consumed by zero, one, or multiple products. | ADR-009 and migrated Instrument Domain architecture. |
| Product Eligibility | Product-owned meaning that a canonical Instrument may be consumed within one product context. It is not Provider acquisition, Instrument interpretation, or canonical identity. | ADR-009 and Domain Ownership Matrix. |
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

Observations refer to an approved Instrument Identity Contract. They do not create identity. Provider records may support interpretation and mapping only after an EAIC-002-conforming Submission Unit is admitted; they do not become canonical through acquisition, catalogue presence, Submission Eligibility, receipt, validation, or Interpretation Admission.

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

The approved identity classification distinguishes:

- **Equity**;
- **Index**;
- **ETF**;
- **Commodity**;
- **Currency**;
- **Future**; and
- **Option** as identity-recognized but capability-inactive.

The exact canonical taxonomy and identity-defining meanings for these classes remain unresolved where later canonical architecture has not resolved them. The classification is product-neutral and does not establish product membership or eligibility.

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

Provider owns Provider acquisition, Provider Catalogue, Provider-and-Dataset Catalogue Partitions, Provider Snapshots, Provider Records, Provider Record Identity, Provider dispositions, Submission Eligibility, acquisition scope and outcomes, Provider provenance, capability, entitlement, and operational availability.

Provider Instrument References:

- are external reference material;
- may support product-neutral Instrument interpretation only through EAIC-002 when that contract is separately activated and the required authorities exist;
- retain provider provenance;
- remain outside the three canonical identity layers and do not become Economic Instrument, Listed Instrument, or Derivative Contract identity automatically;
- do not establish Instrument lifecycle meaning;
- do not establish Market Facts or Market Schedule; and
- do not transfer provider ownership to Instrument.

Provider Catalogue Partition Identity is bounded to one Provider-and-dataset context. Provider Snapshot Identity is unique only within one Provider-and-Dataset Catalogue Partition. Provider Record Identity is unique only within one Provider Snapshot.

Provider-native identifiers, Provider tokens, exchange tokens, symbols, row positions, Provider Record Identity, Provider Snapshot Identity, and Submission Unit identity shall not establish:

- cross-partition permanence;
- cross-snapshot permanence;
- canonical Instrument Identity;
- identity continuity; or
- cross-Provider identity equivalence.

Instrument Master `last_price` is auxiliary Provider metadata under ADR-009. It is not Economic Instrument, Listed Instrument, Derivative Contract, Current Quote, or Observation-owned market state.

## 14. Provider Identifier Mappings

The approved ownership distinction is:

- Provider owns the provider-specific identifier and source record.
- Instrument owns Provider mapping, Provider Mapping Status, cross-Provider reconciliation, and the semantic meaning of each association with the applicable Instrument-owned identity layer.

**Chief Architect-approved principle:** A Provider mapping must preserve Provider provenance and must not allow a Provider identifier to replace an Economic Instrument, Listed Instrument, or Derivative Contract identity. Mapping changes must remain explainable and must not silently reassign historical observations.

**Chief Architect-approved principle:** Provider identifiers must always be interpreted within their Provider context. Provider mappings are potentially time-bounded, and the architecture must not assume perpetual validity. Where Provider reuse, reassignment, lifecycle change, or historical attribution requires it, the mapping must also be interpreted within an effective-time or lifecycle context.

An Instrument-owned identity may have zero, one, or multiple Provider mappings. The existence, absence, replacement, or expiry of a Provider mapping does not create or delete an Economic Instrument, Listed Instrument, or Derivative Contract identity.

Within the same applicable Provider and effective context, one Provider mapping must not resolve ambiguously to multiple active Instrument-owned identities. Ambiguity must prevent canonical attribution until resolved through separately approved architecture.

**Frozen approved principle:** Historical Provider mappings shall remain attributable after a Provider token, symbol, reference, or contract record changes, disappears, is reassigned, or is no longer current.

Provider mapping is independent from Canonical Identity Decision. A canonical Instrument may exist without a current Provider mapping, `MAPPED` requires a canonical identity target, mapping may remain pending or unevaluated after canonical identity is established, and one Provider mapping shall not establish another Provider's mapping.

Cross-Provider reconciliation remains exclusively Instrument-owned. It shall preserve Provider separation and provenance and shall not create a Provider-to-Provider dependency.

These are semantic requirements only. This document does not define mandatory timestamp fields, what constitutes an effective period, how conflicts are detected, or how mapping history is stored or processed.

This document does not define mapping fields, lookup behavior, synchronization, reconciliation algorithms, conflict-resolution algorithms, or persistence. Provider information may cross into Instrument only through an EAIC-002-conforming Submission Unit after the separately governed Provider conditions are established.

## 15. Instrument Lifecycle, Provider Mapping Status, and Provider Availability

ADP-001A approves the need to preserve futures expiry, lifecycle identity, Provider-token changes, and historical attribution. The Chief Architect has approved the following Instrument Lifecycle vocabulary without defining a state machine.

### Instrument Lifecycle

- **Prospective:** an instrument or contract is known or announced but is not yet active within its intended listed or tradable lifecycle context. This does not authorize retrieval, observation, validation, or trading.
- **Active:** the identity is active within its applicable instrument lifecycle context. Active does not mean that the market is open, a Provider is available, current data exists, or trading is authorized.
- **Expired:** a Derivative Contract has reached its contractual expiry. Expiry ends its applicable active contract lifecycle, but historical identity survives expiry and remains attributable.
- **Retired:** the applicable Instrument-owned identity is no longer current for approved use but remains preserved for historical attribution. Operational retirement criteria are not defined here.
- **Delisted:** the Listed Instrument is no longer listed at its venue. Delisting remains distinct from expiry, retirement, supersession, Provider disappearance, and Provider failure.
- **Superseded:** a distinct identity has an explicitly governed successor or replacement relationship. Supersession does not merge identities or transfer historical observations.

Successor relationships are conceptually part of Instrument Identity architecture but are not operationally defined. They connect distinct identities, do not merge identities, do not transfer historical observations, and do not create continuous futures. Their detailed semantics, discovery, maintenance, and operational processing remain undefined.

### Provider Mapping Status

Provider Mapping Status is Instrument-owned and independent from Canonical Identity Decision. Exactly one status applies to one bounded mapping evaluation:

- `NOT_EVALUATED`;
- `MAPPING_PENDING`;
- `MAPPED`;
- `NOT_MAPPED`;
- `MAPPING_AMBIGUOUS`; or
- `MAPPING_UNSUPPORTED`.

Provider Mapping Status does not become Instrument Lifecycle. `NOT_MAPPED`, `MAPPING_AMBIGUOUS`, or `MAPPING_UNSUPPORTED` does not delete an Economic Instrument, Listed Instrument, Derivative Contract, or historical Provider mapping.

### Provider Operational Availability

Provider Operational Availability remains Provider-owned and does not become Provider Mapping Status or Instrument Lifecycle. Provider unavailability does not imply expiry, delisting, retirement, supersession, canonical Instrument non-existence, or product ineligibility.

The following supporting concepts remain recognised:

- **Recognition:** an Instrument becomes known within approved Instrument meaning without implying product membership, Product Eligibility, retrieval, or trading support.
- **Historical identity:** an expired, retired, delisted, superseded, or otherwise no-longer-current identity remains identifiable for previously attributed facts.
- **Provider-reference change:** a Provider reference changes, disappears, reappears, or is replaced without automatically changing an Instrument-owned identity.
- **Successor relationship:** an acknowledged relationship connects distinct identities without merging them or creating continuous-futures identity.

The applicability details of lifecycle concepts across the three identity layers, authoritative establishing facts, transition criteria, and operational lifecycle model remain unresolved where later canonical architecture has not resolved them.

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
11. Canonical Instrument Identity is product-neutral and does not depend on current product membership or eligibility.
12. Provider acquisition, Provider Catalogue state, Submission Eligibility, and EAIC-002 boundary meanings do not establish canonical Instrument Identity.

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
22. **Lifecycle, Mapping, and Availability Separation:** Provider Mapping Status is not Instrument Lifecycle, Provider Operational Availability is not Provider Mapping Status, and Provider unavailability does not imply or alter lifecycle status.
23. **Successor Separation:** successor relationships connect distinct identities without merging identities, transferring historical observations, or creating continuous futures.
24. **Product-Neutral Identity:** canonical Instrument Identity and Canonical Instrument Catalogue membership do not depend on current product membership, product eligibility, product demand, or product implementation.
25. **Explicit Product Consumption:** products consume canonical Instrument outputs only through separately governed explicit product boundaries and do not acquire Instrument ownership.
26. **Sole Provider Boundary:** Provider information may enter Instrument only through EAIC-002 after the applicable Provider-owned determinations and separate authorities are established.
27. **Provider Identity Scope:** Provider Catalogue Partition Identity, Provider Snapshot Identity, Provider Record Identity, and Submission Unit identity remain bounded and do not establish canonical identity or cross-Provider equivalence.
28. **Instrument-Owned Reconciliation:** Provider mapping, Provider Mapping Status, and cross-Provider reconciliation remain Instrument-owned.

These decisions form part of the approved canonical ADP-001B architecture.

## 17. Domain Ownership

| Domain | Approved ownership relevant to this document |
| --- | --- |
| Instrument | Product-neutral interpretation; Economic Instrument, Listed Instrument, and Derivative Contract identity; canonical identity decision; identity semantics; canonical classification; approved relationships; lifecycle semantics; Provider mapping; Provider Mapping Status; cross-Provider reconciliation; identity invariants; Instrument Identity Contract publication; and Canonical Instrument Catalogue publication. |
| Provider | Provider acquisition; Provider Catalogue; Provider-and-Dataset Catalogue Partitions; Provider Snapshots; Provider Records; Provider Record Identity; dispositions; Submission Eligibility; acquisition scope and outcomes; Provider-specific identifiers; Provider Instrument References; Provider provenance; Provider capability; Provider entitlement; and Provider Operational Availability. |
| Observation | Market observations attributed to approved Instrument Identity. |
| Market | Market Schedule, session semantics, and explicit Exchange Availability where authorized. |
| Configuration | Runtime configuration only; configurable values do not acquire identity semantics. |
| Applicable Product | Product universe, Product Eligibility, explicit product consumption, product evidence requirements, product validation requirements, product decision semantics, and product risk interpretation within that product context. |

No new domain or ownership assignment is introduced.

## 18. Permitted Responsibilities

Within approved architecture, Instrument may:

- define authoritative instrument identity and classification;
- preserve approved analysis/reference/execution relationships;
- define lifecycle and mapping meaning within approved architectural semantics;
- perform cross-Provider reconciliation while preserving Provider separation and provenance;
- publish Instrument Identity through an approved contract;
- publish product-neutral canonical meaning through the Canonical Instrument Catalogue; and
- preserve explainable attribution across approved lifecycle changes.

Provider may acquire and preserve Provider-owned reference information and may present an eligible Submission Unit only through EAIC-002 when separately activated and authorized. Products may consume approved canonical Instrument outputs only through explicit product boundaries. Observation may consume approved identity to attribute facts. Market and Configuration retain their separate approved responsibilities.

These permissions do not authorize runtime work from this document.

## 19. Prohibited Responsibilities

Instrument must not:

- acquire Provider Integration, Provider acquisition, Provider Catalogue, Provider Records, Provider dispositions, Submission Eligibility, Provider availability, or provider provenance ownership;
- acquire Market Facts, quote, candle, OI, or factual data-quality ownership;
- acquire Market Schedule or Exchange Availability ownership;
- acquire Runtime Configuration ownership;
- infer identity from current price, missing data, provider connectivity, or session state;
- perform retrieval, persistence, synchronization, caching, or transport;
- create Validation judgment, trading decisions, execution authority, orders, or positions; or
- establish product membership or Product Eligibility, activate Options capability, or create new analysis/reference/execution relationships.

Provider, products, Observation, Market, and Configuration must not recreate or override Instrument Identity.

Instrument shall not accept direct Provider writes, access Provider Catalogue internals, bypass EAIC-002, or recreate Provider-owned Submission Eligibility.

## 20. External Architectural Relationships

| Relationship or capability | Treatment in ADP-001B |
| --- | --- |
| EAIC-002 — Provider → Instrument Submission Contract | Sole current canonical Provider → Instrument submission boundary. It remains inactive pending coordinated migration and separate activation authorization and is referenced rather than redefined here. |
| ADP-001C — Provider → Instrument Contract | Superseded historical Swing-specific predecessor retained only for traceability. It supplies no current boundary or implementation authority. |
| Provider Instrument Master Acquisition | Provider-owned and governed by ADR-009 Version 1.0 and DOMAIN-006 Provider Domain Architecture; EAIC-002 Version 0.1 separately governs Provider → Instrument submission. It is independent of product membership and canonical identity. |
| Provider → Observation Contract | Required future contract for factual acquisition; referenced but not defined here. |
| Historical Observation Architecture | Future Observation architecture dependent on approved identity; not defined here. |
| Current Quote Architecture | Separately governed Observation dataset area; future architecture not defined here. |
| Instrument Lifecycle Capability | Future capability dependent on approved lifecycle semantics; not defined here. |
| Successor Relationships | Conceptually part of Instrument Identity architecture; detailed semantics, discovery, maintenance, and operational processing are not defined here. |
| Explicit Product Consumption | Separately governed product boundary through which a product selects canonical Instrument outputs without changing Provider acquisition or Instrument identity. |
| Continuous Futures Architecture | Conditional under ADP-001A and requires separate approval. |
| TradingView Integration | Excluded from Phase 1 and not defined here. |
| Corporate Actions | Future phase under ADP-001A and not defined here. |
| Options Architecture | Future consumer of the identity foundation for underlyings and individual option contracts; excluded from active Phase 1 product engineering and not defined here. |

No architecture assumption is made about Kite's or another Provider's coverage. Provider Capability and Provider Entitlement remain separately governed Provider meanings. Dataset Permission, Acquisition Authority, submission authority, runtime authority, and Product Eligibility remain independent. Instrument Identity remains Provider-neutral and product-neutral.

## 21. Architectural Traceability

### Historical product traceability from ADP-001A

- historical Instrument Master and provider-to-canonical mapping requirements where consistent with canonical Provider-and-Instrument ownership;
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
- Instrument Lifecycle is distinct from Provider Mapping Status and Provider Operational Availability;
- Provider mappings are potentially time-bounded;
- historical Provider mappings remain attributable;
- successor relationships are conceptually acknowledged; and
- Provider Instrument References remain external and non-canonical.

### Canonical successor and downstream relationships

- ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture;
- EAIC-002 — Provider → Instrument Submission Contract;
- superseded ADP-001H — historical Provider Instrument Master Acquisition predecessor traceability only;
- ADP-001C — superseded historical Provider → Instrument predecessor;
- Instrument Identity Contract;
- Instrument Lifecycle capability or architecture;
- Historical Observation Architecture;
- Current Quote Architecture;
- Continuous Futures Architecture where separately approved; and
- separately governed product-consumption boundaries, including future Options Architecture where approved.

This traceability creates no implementation sequence or runtime authorization.

## 22. Dependencies

ADP-001B depends on:

- ADR-009 for Provider-bounded acquisition, product-neutral interpretation, canonical identity, Provider mapping, the Canonical Instrument Catalogue, and explicit product consumption;
- EAIC-002 for the sole current canonical Provider → Instrument submission boundary;
- MIG-001 for coordinated migration governance and the prohibition on partial activation;
- ADR-007 for Provider-scoped Capability Assessment;
- ADR-008 for account-scoped Provider-Reported Entitlement Assessment;
- ADR-009 Version 1.0 and DOMAIN-006 Provider Domain Architecture for Provider-owned Instrument Master acquisition, with EAIC-002 Version 0.1 governing the subsequent Provider → Instrument submission boundary;
- the approved Platform Constitution;
- the migrated Domain Ownership Matrix and Domain Dependency Matrix;
- the migrated Provider and Instrument Domain architectures;
- DATA_FLOW and existing engine ownership;
- ADP-001A for historical Swing product requirements where consistent with current canonical authority; and
- approved futures relationships.

ADP-001C is superseded and retained only for predecessor traceability. It supplies no active dependency or Provider → Instrument authority.

Instrument has no business-domain dependency. Instrument may consume an EAIC-002-conforming Submission Unit without accessing Provider Catalogue internals or acquiring Provider ownership. Products may consume canonical Instrument outputs through explicit product boundaries without creating a reverse Instrument dependency.

No ADR is required for ADP-001B because it elaborates approved architecture, does not alter domain ownership, does not create a domain, and does not change platform principles. Future operational capabilities may require separate architectural review.

## 23. Unresolved Architectural Questions

1. Which additional provider-neutral reference meanings, if any, require later approval within each identity layer beyond current canonical architecture?
2. What detailed relationship cardinality applies among Economic Instrument, Listed Instrument, Derivative Contract, and underlying relationships beyond the approved three-layer separation?
3. Which authoritative facts establish each Instrument Lifecycle status?
4. How do the approved lifecycle concepts apply in detail across Economic Instrument, Listed Instrument, and Derivative Contract identity?
5. Which facts establish the beginning and end of a Provider mapping's effective context?
6. What detailed ambiguity conditions require canonical attribution to be blocked?
7. Which facts determine identity continuity when a symbol or listing changes?
8. What are the detailed semantics, discovery, and maintenance rules for successor relationships?
9. Which approved ADL-001 relationships apply within each separately governed product-consumption boundary?

Engineering must not answer these questions by implementation or inference. Operational lifecycle processing, mapping procedures, successor discovery, Provider operations, and product consumption remain subject to separately approved architecture and authorization.

## 24. Conformance with ADP-001A

ADP-001B preserves bounded historical traceability to ADP-001A as follows:

- It preserves applicable historical Instrument Master reference and provider-to-canonical mapping requirements without allowing a product classification to govern Provider acquisition or canonical identity.
- It preserves canonical attribution, futures expiry/lifecycle identity, Provider-token change handling, and historical attribution as required identity concerns.
- It preserves approved analysis, reference, and execution instrument roles without adding relationships.
- It treats Provider tokens as external, non-canonical, and non-permanent.
- It preserves Provider-token change handling and historical mapping attribution without treating a current Provider token or symbol as permanent canonical identity.
- It treats Instrument Master `last_price` only as auxiliary Provider metadata.
- It keeps Current Quote and historical observations under Observation ownership.
- It keeps Market Schedule under Market ownership and Provider availability under Provider ownership.
- It does not redefine any product dataset requirement, classification, or completion criterion in ADP-001A.
- It preserves the exclusion of active Options-product capability, TradingView, persistence, streaming, execution, orders, positions, and automated trading while retaining identity-recognized but capability-inactive Option identity semantics.

ADP-001B elaborates product-neutral Instrument Identity architecture only. ADP-001A product requirements do not bound Provider acquisition, Instrument interpretation, canonical identity, Canonical Instrument Catalogue membership, or another product's eligibility.

## 25. Successor and Activation Boundary

ADP-001C is superseded. It remains available only as the historical Swing-specific predecessor to EAIC-002.

EAIC-002 Version 0.1 is the sole current canonical Provider → Instrument submission contract. It remains inactive pending coordinated migration and separate activation authorization.

ADP-001B does not activate EAIC-002, authorize Provider acquisition or submission, authorize Instrument interpretation, or grant implementation, runtime, endpoint, persistence, product, EDD, Engineering Package, or EDD-004 authority.

Any later Instrument Identity Contract, Instrument Lifecycle capability, Observation architecture, Current Quote architecture, Continuous Futures architecture, or product-consumption boundary requires its own applicable governance and authority.

## 26. Approval Record

**Chief Architect Decision:** Approved

**Engineering Architect Verification:** Complete

**ADR Required:** No

**Canonical Status:** Approved Canonical Architecture

**Next Authorized Capability:** None

**Review History:** The Chief Architect initially approved ADP-001B with required amendments. The amendments were incorporated, Engineering Architect conformance verification completed, and repository metadata and indexes were updated before final canonicalization. WP-B3 migrated ADP-001B to ADR-009, EAIC-002, and the migrated Provider and Instrument domains. DG-01 subsequently superseded ADP-001H in favor of ADR-009 Version 1.0, DOMAIN-006 Provider Domain Architecture, and EAIC-002 Version 0.1; ADP-001H remains predecessor traceability only.

**Implementation Authorization:** None

**Runtime Authorization:** None

**EAIC-002 Activation Authorization:** None

**EDD-004 Drafting Authorization:** None

ADP-001C supplies historical predecessor traceability only. EAIC-002 is the sole current canonical Provider → Instrument submission contract and remains separately inactive.

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
- [ADP-001C — Provider → Instrument Contract (superseded historical predecessor)](SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md)
- [ADP-001H — Superseded Provider Instrument Master Acquisition predecessor (historical traceability only)](SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md)
- [ADR-007 — Provider Capability Assessment Architecture](../../platform/domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md)
- [ADR-008 — Provider Entitlement Assessment Architecture](../../platform/domains/provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md)
- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [ADL-001 — Futures Model Architecture](../../ADL-001-Futures-Model.md)
- [EAIC-001 — Exchange Availability Interface Contract](../../interfaces/EAIC-001-Exchange-Availability-Interface-Contract.md)
- [KRONOS Engine Ownership](../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../DATA_FLOW.md)
