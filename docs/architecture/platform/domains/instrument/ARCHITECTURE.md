# DOMAIN-001 — Instrument Domain
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Own the product-neutral canonical meaning of Instrument interpretation, identity, classification, relationships, lifecycle interpretation where already governed, and Provider mapping so every downstream domain and product can refer to the same canonical Instrument without acquiring Provider-owned semantics.

Instrument publishes approved canonical meaning without performing Provider acquisition, factual market observation, business judgment, Risk approval, execution, or product-universe selection.

## Governing Authority

The Instrument Domain derives its architectural meaning from:

- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md);
- [EAIC-002 — Provider → Instrument Submission Contract](../../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md);
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md);
- [Provider Domain Architecture](../provider/ARCHITECTURE.md);
- [ADR-007 — Provider Capability Assessment Architecture](../provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md);
- [ADR-008 — Provider Entitlement Assessment Architecture](../provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md);
- [PLATFORM-000 — KRONOS Platform Constitution](../../PLATFORM-000-CONSTITUTION.md);
- [Domain Ownership Matrix](../../DOMAIN_OWNERSHIP_MATRIX.md);
- [Domain Dependency Matrix](../../DOMAIN_DEPENDENCY_MATRIX.md); and
- [Project KRONOS Data Flow](../../../DATA_FLOW.md).

ADR-009 governs the product-neutral Instrument interpretation and catalogue model established by this migration.

EAIC-002 is the sole governed Provider-to-Instrument submission boundary for the Instrument Master dataset.

MIG-001 governs coordinated repository alignment and does not itself activate runtime behavior.

The Instrument Domain preserves the shared governing principle:

> Acquire Broadly (within an authorised dataset).
>
> Interpret Canonically.
>
> Consume Explicitly.

Provider owns broad acquisition within the separately authorized dataset.

Instrument owns product-neutral canonical interpretation.

Products consume canonical Instruments only through explicit product boundaries.

## Instrument Ownership

Instrument exclusively owns:

- canonical Instrument interpretation;
- interpretation processing status;
- interpretation outcome;
- canonical identity decision;
- canonical Instrument identity;
- canonical classification;
- Provider mapping;
- Provider mapping status;
- cross-Provider reconciliation;
- canonical equivalence;
- conflict-resolution meaning;
- Instrument relationships;
- analysis, reference, and execution Instrument relationships where already governed;
- lifecycle interpretation where already governed;
- canonical identity continuity;
- canonical relationship continuity;
- Instrument Identity Contract publication; and
- Canonical Instrument Catalogue publication.

Instrument Identity remains the single platform semantic responsibility assigned to Instrument by the Domain Ownership Matrix.

Instrument meaning may be informed by Provider-owned evidence without transferring Provider ownership or allowing Provider evidence to become canonical automatically.

## Provider Ownership Exclusions

Instrument does not own:

- Provider Integration;
- Provider Context;
- Provider capability assessment;
- Provider entitlement assessment;
- Provider acquisition;
- Approved Acquisition Scope;
- Requested Acquisition Scope;
- Received Acquisition Scope;
- technical acquisition result;
- Acquisition Outcome;
- Provider Catalogue;
- Provider-and-Dataset Catalogue Partitions;
- Provider Snapshots;
- Provider Records;
- Provider Record Identity;
- Provider record dispositions;
- Snapshot Currentness;
- Snapshot Supersession;
- Submission Eligibility;
- Provider limitations;
- Provider provenance;
- acquisition provenance; or
- Provider-native submission provenance.

Instrument shall preserve Provider attribution and applicable evidence associations without:

- mutating Provider Records;
- repairing Provider assertions;
- selecting among Provider duplicates silently;
- replacing Provider dispositions;
- changing Submission Eligibility;
- changing Provider snapshot currentness;
- changing Provider supersession; or
- acquiring ownership of Provider-native meaning.

## EAIC-002 Boundary

### Sole Governed Submission Boundary

EAIC-002 is the sole governed boundary through which eligible Provider-owned Instrument Master information may enter Instrument for possible interpretation.

Instrument shall not:

- accept direct Provider writes into Instrument-owned state;
- access Provider Catalogue internals;
- consume raw Provider payloads;
- consume Provider SDK objects or exceptions;
- bypass EAIC-002;
- accept product-filtered substitutes for the approved boundary; or
- treat Provider Catalogue presence as submission.

Provider may present a Submission Unit only after separately establishing Submission Eligibility and Provider-to-Instrument Submission Authority under EAIC-002.

Instrument shall not recreate either Provider-owned determination.

### Boundary Meanings

The following meanings remain separate:

1. technical receipt;
2. contract validation;
3. interpretation admission;
4. interpretation processing;
5. interpretation outcome;
6. canonical identity decision; and
7. Provider mapping status.

Technical receipt does not imply:

- contract validity;
- interpretation admission;
- semantic acceptance;
- interpretation success;
- canonical identity; or
- Provider mapping.

Contract validation does not imply interpretation success.

Interpretation admission does not imply:

- interpretation has begun;
- interpretation has completed;
- canonical identity has been established; or
- Provider mapping has been established.

Canonical identity does not automatically imply Provider mapping.

Provider mapping may be deferred independently.

### Receipt and Rejection

Instrument shall validate the complete EAIC-002 Submission Unit atomically.

Contract rejection occurs before Instrument interpretation and shall:

- preserve safe rejection evidence;
- preserve trusted Provider attribution;
- create no Instrument interpretation outcome;
- create no canonical identity decision beyond `NOT_EVALUATED`;
- create no Provider mapping;
- create no Instrument lifecycle state; and
- transfer no Provider ownership.

Instrument shall not reinterpret a contract rejection as:

- Provider record invalidity;
- Instrument non-existence;
- product exclusion;
- Observation rejection;
- Validation rejection;
- Risk rejection; or
- execution prohibition.

## Four Independent Interpretation Dimensions

The Instrument-side architectural model contains exactly four independent dimensions:

1. Interpretation Processing Status;
2. Interpretation Outcome;
3. Canonical Identity Decision; and
4. Provider Mapping Status.

Each dimension has its own cardinality and meaning.

They shall not be collapsed into:

- one Instrument status;
- one success or failure flag;
- one lifecycle state;
- one Provider disposition;
- one product-eligibility state; or
- one implementation workflow state.

### Interpretation Processing Status

Exactly one Interpretation Processing Status shall exist:

- `NOT_STARTED`;
- `PENDING`; or
- `COMPLETED`.

`NOT_STARTED` means Instrument interpretation has not begun.

`PENDING` means Instrument interpretation has begun but has not completed.

`COMPLETED` means the bounded interpretation activity has completed.

Processing status describes processing only.

It does not establish:

- an Interpretation Outcome;
- canonical identity;
- Provider mapping;
- product eligibility; or
- Instrument lifecycle.

Technical receipt and contract validation shall not cause `PENDING` or `COMPLETED`.

### Interpretation Outcome

When Interpretation Processing Status is `COMPLETED`, exactly one mutually exclusive Interpretation Outcome shall exist:

- `INTERPRETED`;
- `UNINTERPRETED`;
- `AMBIGUOUS`; or
- `UNSUPPORTED`.

| Interpretation Outcome | Instrument-owned meaning |
|---|---|
| `INTERPRETED` | Instrument established a bounded semantic interpretation. |
| `UNINTERPRETED` | Processing completed without establishing sufficient semantic interpretation. |
| `AMBIGUOUS` | More than one materially valid Instrument interpretation remains. |
| `UNSUPPORTED` | Current canonical Instrument architecture does not support interpretation of the submitted Provider assertion. |

No Interpretation Outcome shall:

- alter Provider Records;
- alter Provider dispositions;
- alter Submission Eligibility;
- imply Provider failure;
- create product membership; or
- create business judgment.

### Canonical Identity Decision

Exactly one Canonical Identity Decision shall exist:

- `NOT_EVALUATED`;
- `CANONICAL_IDENTITY_ESTABLISHED`; or
- `CANONICAL_IDENTITY_NOT_ESTABLISHED`.

`NOT_EVALUATED` may coexist with `NOT_STARTED` or `PENDING`.

`CANONICAL_IDENTITY_ESTABLISHED` requires:

- Interpretation Processing Status `COMPLETED`;
- Interpretation Outcome `INTERPRETED`; and
- sufficient approved Instrument-owned canonical identity evidence.

Once identity evaluation is completed, an Interpretation Outcome of `UNINTERPRETED`, `AMBIGUOUS`, or `UNSUPPORTED` requires `CANONICAL_IDENTITY_NOT_ESTABLISHED`.

`CANONICAL_IDENTITY_NOT_ESTABLISHED`:

- preserves the applicable reason;
- establishes no canonical identity;
- does not imply Instrument non-existence;
- does not alter Provider meaning;
- does not create product exclusion; and
- is not an Interpretation Outcome.

### Provider Mapping Status

Exactly one Provider Mapping Status shall exist:

- `NOT_EVALUATED`;
- `MAPPING_PENDING`;
- `MAPPED`;
- `NOT_MAPPED`;
- `MAPPING_AMBIGUOUS`; or
- `MAPPING_UNSUPPORTED`.

Provider Mapping Status is independent from Canonical Identity Decision.

The following rules apply:

- a canonical Instrument may exist without a current Provider mapping;
- `MAPPED` requires a canonical identity target;
- `MAPPING_PENDING` may coexist with `CANONICAL_IDENTITY_ESTABLISHED`;
- `NOT_EVALUATED` preserves mapping deferral before evaluation;
- `NOT_MAPPED` does not invalidate canonical identity;
- `MAPPING_AMBIGUOUS` preserves unresolved mapping alternatives;
- `MAPPING_UNSUPPORTED` preserves current mapping-architecture limitations;
- Provider mapping shall not create canonical identity; and
- one Provider mapping shall not establish another Provider's mapping.

Cross-Provider reconciliation remains Instrument-owned.

### Permitted Ordering and Coexistence

The normal architectural ordering is:

```text
EAIC-002 interpretation admission
        ↓
Interpretation processing
        ↓
Interpretation outcome
        ↓
Canonical identity decision
        ↓
Provider mapping evaluation
```

The ordering does not require synchronous completion.

Provider mapping evaluation may be deferred after canonical identity has been established.

The following coexistence is expressly permitted:

- `NOT_STARTED` with Canonical Identity Decision `NOT_EVALUATED` and Provider Mapping Status `NOT_EVALUATED`;
- `PENDING` with Canonical Identity Decision `NOT_EVALUATED` and Provider Mapping Status `NOT_EVALUATED`;
- `COMPLETED` and `INTERPRETED` while the Canonical Identity Decision remains `NOT_EVALUATED`;
- `CANONICAL_IDENTITY_ESTABLISHED` with Provider Mapping Status `NOT_EVALUATED`;
- `CANONICAL_IDENTITY_ESTABLISHED` with `MAPPING_PENDING`;
- `CANONICAL_IDENTITY_ESTABLISHED` with `MAPPED`;
- `CANONICAL_IDENTITY_ESTABLISHED` with `NOT_MAPPED`;
- `CANONICAL_IDENTITY_ESTABLISHED` with `MAPPING_AMBIGUOUS`; and
- `CANONICAL_IDENTITY_ESTABLISHED` with `MAPPING_UNSUPPORTED`.

No permitted coexistence creates an Instrument lifecycle state.

### Bounded Terminal and Deferred Meanings

Within one bounded Instrument evaluation:

- Interpretation Processing Status `COMPLETED` is terminal for that processing activity;
- `INTERPRETED`, `UNINTERPRETED`, `AMBIGUOUS`, and `UNSUPPORTED` are terminal outcomes of that completed interpretation activity;
- Canonical Identity Decision `CANONICAL_IDENTITY_ESTABLISHED` and `CANONICAL_IDENTITY_NOT_ESTABLISHED` are terminal for that bounded identity evaluation;
- Canonical Identity Decision `NOT_EVALUATED` means identity evaluation remains deferred or has not begun;
- Provider Mapping Status `MAPPED`, `NOT_MAPPED`, `MAPPING_AMBIGUOUS`, and `MAPPING_UNSUPPORTED` are terminal for that bounded mapping evaluation;
- Provider Mapping Status `NOT_EVALUATED` means mapping evaluation has not begun; and
- Provider Mapping Status `MAPPING_PENDING` means mapping evaluation remains deferred or incomplete.

A terminal meaning is terminal only for the identified bounded evaluation.

It does not become:

- a permanent prohibition on later separately governed evaluation;
- an Instrument lifecycle state;
- a Provider disposition;
- a product-eligibility state; or
- authority for runtime reassessment.

## Canonical Identity

Canonical Instrument identity is established only by Instrument under approved canonical identity architecture.

Provider-native information is evidence only.

Instrument shall preserve the Provider-owned identity scopes:

- Provider Catalogue Partition Identity is scoped to one Provider-and-dataset boundary;
- Provider Snapshot Identity is unique only within one Provider-and-Dataset Catalogue Partition; and
- Provider Record Identity is unique only within one Provider Snapshot.

Instrument shall not broaden, replace, globalize, override, or reinterpret those Provider-owned identity scopes.

None of the following may alone establish canonical Instrument identity:

- Provider identity;
- Provider Context;
- Provider Catalogue Partition Identity;
- Provider Snapshot Identity;
- Provider Record Identity;
- Submission Unit identity;
- Provider token;
- exchange token;
- symbol;
- row position;
- Provider classification;
- Provider vocabulary;
- record ordering;
- price behavior;
- product demand; or
- implementation convenience.

Submission Unit identity shall not broaden, replace, globalize, or override:

- Provider-and-Dataset Catalogue Partition identity;
- Provider Snapshot Identity;
- Provider Record Identity; or
- canonical Instrument identity.

Instrument shall not infer cross-Provider identity equivalence from Provider-native identifiers, Provider Record Identity, Provider Snapshot Identity, or Submission Unit identity.

Canonical identity is independent from:

- Provider mapping;
- Provider availability;
- Provider snapshot currentness;
- product membership;
- product eligibility;
- Observation availability;
- Validation result;
- Risk Approval;
- execution status; and
- current product consumption.

## Provider Mapping and Cross-Provider Reconciliation

Provider mapping is the Instrument-owned governed association between a Provider reference and canonical Instrument identity.

Provider mapping:

- preserves Provider identity and provenance;
- does not transfer Provider Record ownership;
- does not make Provider vocabulary canonical automatically;
- does not give Provider ownership of canonical semantics;
- may be evaluated or deferred independently after canonical identity establishment;
- may preserve ambiguity or unsupported status;
- does not create product membership;
- does not create product eligibility;
- does not create Observation authority; and
- does not create execution authority.

One Provider mapping shall not:

- establish another Provider's mapping;
- merge Provider Catalogue partitions;
- globalize Provider-native identifiers;
- imply cross-Provider identity equivalence; or
- alter another Provider's evidence.

Cross-Provider reconciliation is Instrument-owned and shall:

- preserve each Provider's identity and provenance separately;
- preserve conflicts and ambiguity;
- avoid silent Provider preference;
- establish no equivalence without sufficient approved Instrument evidence;
- permit deferral without inventing canonical meaning; and
- avoid mutating Provider-owned records.

## Instrument Relationships and Lifecycle

Instrument owns approved canonical relationships, including analysis, reference, and execution Instrument relationships where already governed.

This migration preserves existing approved relationship ownership.

It does not create new relationship types, routing semantics, or lifecycle states.

Provider snapshot change, record addition, record absence, record change, symbol change, token reuse, Submission Eligibility, contract receipt, interpretation processing, interpretation outcome, canonical identity decision, and Provider mapping status shall not become Instrument lifecycle automatically.

Lifecycle interpretation occurs only where separately governed Instrument architecture establishes it.

## Canonical Instrument Catalogue

The Canonical Instrument Catalogue is a product-neutral Instrument-owned catalogue of approved:

- canonical Instrument identities;
- canonical classifications;
- canonical relationships;
- lifecycle meaning where already governed;
- identity continuity;
- Provider mappings; and
- traceable evidence associations.

It is distinct from:

- Provider Catalogue;
- Provider-and-Dataset Catalogue Partitions;
- Provider Snapshots;
- Provider Records;
- Provider dispositions;
- Submission Eligibility;
- EAIC-002 Submission Units;
- EAIC-002 envelopes;
- product universes;
- product eligibility lists;
- Observation stores; and
- trading-eligibility lists.

The Canonical Instrument Catalogue may contain canonical Instruments:

- consumed by Swing;
- consumed by Intraday;
- consumed by both;
- consumed by another future product;
- consumed by no current product;
- mapped to one Provider;
- mapped to multiple Providers; or
- currently mapped to no Provider.

Canonical Instrument Catalogue publication shall occur only through approved Instrument-owned architecture.

Products shall not write canonical identity, classification, relationship, lifecycle, or Provider mapping meaning into the catalogue.

## Rejection, Deferral, Ambiguity, and Unsupported Meaning

Contract rejection remains an EAIC-002 boundary result and does not become an Interpretation Outcome.

Instrument shall not create a generic interpretation-rejection state.

Completed interpretation shall use exactly one approved Interpretation Outcome:

- `INTERPRETED`;
- `UNINTERPRETED`;
- `AMBIGUOUS`; or
- `UNSUPPORTED`.

Provider `AMBIGUOUS` evidence is not automatically Instrument `AMBIGUOUS`.

`UNRECOGNIZED_PROVIDER_VOCABULARY` remains a Provider evidence-quality flag.

It does not automatically establish:

- `UNSUPPORTED`;
- `AMBIGUOUS`;
- malformed Provider data;
- Instrument non-existence; or
- product exclusion.

Insufficient identity evidence shall:

- remain explicit;
- preserve the applicable reason and evidence;
- establish no unsupported canonical meaning;
- establish no canonical identity unless sufficient approved evidence exists; and
- use only the applicable approved Interpretation Outcome after completed processing.

Canonical identity deferral is represented only by Canonical Identity Decision `NOT_EVALUATED`.

Provider mapping deferral is represented only by Provider Mapping Status `NOT_EVALUATED` or `MAPPING_PENDING`, according to the governed evaluation stage.

Cross-Provider reconciliation deferral shall preserve separate Provider mappings, evidence, ambiguity, and conflict without inventing equivalence or a new lifecycle state.

## Dataset Boundary

This migration aligns the EAIC-002 Instrument input boundary only for the Instrument Master dataset governed by ADR-009.

It does not absorb:

- Futures OI;
- Options OI;
- Quotes;
- Historical Data;
- Streaming;
- Market Depth;
- Option Chain data; or
- any other separately governed Provider dataset.

Instrument reference information for Options returned within the approved Instrument Master dataset remains Instrument Master evidence.

It does not authorize Options OI, option-chain acquisition, observations, analytics, Validation, Risk, strategy, orders, or execution.

Each additional Provider dataset requires its own separately approved Provider capability, Dataset Permission, Acquisition Authority, engineering design, endpoint invocation authority, implementation authority, runtime authority, and applicable downstream contract.

Instrument Master submission or interpretation authority shall not be reused for another dataset.

## Provenance and Evidence

Instrument shall preserve sufficient evidence to reconstruct:

- which EAIC-002 contract version applied;
- which Submission Unit was admitted or rejected;
- which Provider, dataset, partition, snapshot, and Provider Records were referenced;
- which Submission Eligibility and submission authority evidence applied;
- which technical receipt and contract-validation outcomes applied;
- whether interpretation was admitted;
- how Interpretation Processing Status changed;
- which Interpretation Outcome was established;
- which Canonical Identity Decision was established;
- which canonical identity evidence applied;
- which Provider Mapping Status was established;
- which mapping or reconciliation evidence applied;
- why ambiguity, unsupported meaning, insufficiency, rejection, or deferral occurred; and
- which Instrument Identity Contract or Canonical Instrument Catalogue publication followed where separately authorized.

The following evidence classes remain distinct:

1. Provider acquisition provenance;
2. EAIC-002 submission provenance;
3. Instrument interpretation evidence;
4. canonical identity evidence; and
5. Provider mapping and cross-Provider reconciliation evidence.

Provider acquisition and Provider-native submission provenance remain Provider-owned.

Instrument preserves their attributable association without acquiring their semantic ownership.

Request initiation time, response receipt time, snapshot closure time, acquisition effective time, submission initiation time, submission receipt time, contract validation time, interpretation admission time, interpretation processing evidence, canonical identity evidence, and mapping evidence shall remain distinct.

No time or evidence meaning may silently substitute for another.

Credentials, tokens, authorization headers, raw Provider payloads, raw SDK clients, SDK response objects, SDK exceptions, private transport state, and unapproved sensitive information shall not become Instrument evidence, canonical identity, Provider mapping, logs, errors, or Audit evidence.

## Product Separation

Swing, Intraday, and future products consume canonical Instruments explicitly through separately approved product-consumption boundaries.

Each product owns:

- its eligible universe;
- supported markets;
- supported Instrument classes;
- required Instrument relationships;
- evidence requirements;
- Observation requirements;
- freshness requirements;
- product limitations;
- Validation policy;
- decision semantics;
- risk interpretation;
- strategy behavior; and
- execution policy.

Products shall not:

- alter canonical Instrument identity;
- alter canonical classification;
- create or alter Provider mappings;
- perform cross-Provider reconciliation;
- alter Provider acquisition;
- filter the approved Provider Instrument Master dataset;
- change Provider snapshot currentness;
- delete Provider Records;
- consume Provider Catalogue records directly;
- consume EAIC-002 Submission Units or envelopes directly; or
- activate another product.

A canonical Instrument may be eligible for one product, multiple products, another future product, or no current product.

Product eligibility shall not be stored as canonical Instrument identity.

## Non-Implications

Instrument interpretation, canonical identity, Provider mapping, and Canonical Instrument Catalogue publication shall not automatically create:

- product-universe membership;
- product eligibility;
- Swing eligibility;
- Intraday eligibility;
- Observation authority;
- Observation acceptance;
- Market Facts;
- Market state;
- Validation approval;
- Business Judgment;
- Risk Approval;
- execution authority;
- trading eligibility;
- trading recommendation;
- order authority;
- Portfolio meaning;
- Provider Dataset Permission;
- Acquisition Authority;
- Provider-to-Instrument Submission Authority;
- persistence authority;
- endpoint invocation authority;
- runtime authority;
- implementation authority; or
- EDD-004 authority.

Instrument interpretation shall not modify Provider acquisition, Provider Catalogue, Provider Records, Provider dispositions, Submission Eligibility, Provider provenance, acquisition outcomes, Requested Acquisition Scope, or Received Acquisition Scope.

## Published Contracts

Instrument publishes:

- Instrument Identity Contract — the authoritative semantic identity and classification of an Instrument and its approved relationships;
- approved Provider mapping meaning through Instrument-owned contracts; and
- Canonical Instrument Catalogue meaning through approved Instrument-owned publication boundaries.

An Instrument Identity Contract shall contain no raw Provider payload, SDK representation, credential, transport-private state, Provider disposition, or product eligibility.

Publication does not authorize Observation, Validation, Risk, execution, product consumption, persistence, or runtime behavior.

## Consumed Contracts and Dependencies

Instrument consumes EAIC-002 as an approved platform-support contract.

Instrument has no business-domain dependency.

EAIC-002 consumption:

- does not place Provider inside the business pipeline;
- does not transfer Provider ownership;
- does not authorize access to Provider internals;
- does not reverse the Domain Dependency Matrix;
- does not make Instrument depend on a product; and
- does not make Instrument depend on Provider-specific adapter mechanics.

Instrument begins the business pipeline:

> Instrument → Observation → Validation → Risk → Execution → Portfolio

Downstream domains and products consume only approved Instrument-owned contracts.

## Architectural Constraints

- Instrument Identity has one semantic owner.
- Instrument interpretation remains product-neutral and Provider-neutral.
- Instrument shall preserve Provider attribution without taking Provider ownership.
- Instrument shall not infer canonical meaning from symbols, tokens, Provider vocabulary, row order, price behavior, product demand, or implementation convenience.
- Instrument shall not repair, select, merge, or discard Provider evidence silently.
- Instrument shall not collapse processing, outcome, identity, mapping, or lifecycle meaning.
- Canonical identity shall remain independent from Provider mapping.
- Provider mapping and cross-Provider reconciliation remain Instrument-owned.
- Canonical Instrument Catalogue shall remain distinct from Provider Catalogue and product universes.
- Products shall consume canonical Instruments explicitly.
- Business domains shall not consume Provider internals or EAIC-002 envelopes.
- Instrument shall communicate through approved contracts only.
- No architecture in this document authorizes implementation, endpoint invocation, live acquisition, persistence, runtime submission, runtime interpretation, or EDD-004.

## Ownership and Dependency Conformance

This architecture remains within the Domain Ownership Matrix assignment:

> Instrument Identity → Instrument

Canonical interpretation, identity, classification, relationships, lifecycle interpretation where governed, Provider mapping, cross-Provider reconciliation, Instrument Identity Contract publication, and Canonical Instrument Catalogue publication are Instrument Identity responsibilities.

They do not create a new domain or transfer any responsibility from Provider, Observation, Market, Validation, Risk, Execution, Portfolio, Configuration, Event, or Audit.

This architecture remains within the Domain Dependency Matrix assignments:

> Instrument → None

Instrument consumption of EAIC-002 is a platform-support dependency, not a business-domain dependency.

It does not make Provider an upstream member of the business pipeline.

## Approved Constitutional References

- CA-013 — Domain Identity
- CA-014 — Responsibility Classes
- CA-015 — Contract-Based Dependencies
- CA-016 — Single Semantic Ownership
- CA-017 — Domain Communication (Platform Only)
- CA-018 — Human Workflow Independence
- CA-019 — Architecture Freeze
- [PLATFORM-000 — KRONOS Platform Constitution](../../PLATFORM-000-CONSTITUTION.md)
- [Platform Business Pipeline](../../PLATFORM_BUSINESS_PIPELINE.md)
- [Domain Dependency Matrix](../../DOMAIN_DEPENDENCY_MATRIX.md)
- [Domain Ownership Matrix](../../DOMAIN_OWNERSHIP_MATRIX.md)

## Related Approved Repository Documents

- [ADL-001 — Futures Model Architecture](../../../ADL-001-Futures-Model.md)
- [ADR-007 — Provider Capability Assessment Architecture](../provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md)
- [ADR-008 — Provider Entitlement Assessment Architecture](../provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md)
- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [Provider Domain Architecture](../provider/ARCHITECTURE.md)
- [KRONOS Engine Ownership](../../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../../DATA_FLOW.md)
- [PP-007 — Execution Semantics Across Markets](../../../principles/PP-007-Execution-Semantics-Across-Markets.md)

## Migration and Authority Status

This Instrument Domain alignment is one controlled MIG-001 work package.

It does not:

- complete the coordinated migration;
- activate ADR-009 or EAIC-002;
- amend the Provider Domain;
- amend ownership or dependency matrices;
- amend DATA_FLOW;
- amend any ADP or EAP;
- authorize Provider communication;
- authorize endpoint invocation;
- authorize live acquisition;
- authorize persistence;
- authorize Provider-to-Instrument submission;
- authorize Instrument interpretation execution;
- authorize EDD-004;
- authorize implementation; or
- authorize runtime behavior.
