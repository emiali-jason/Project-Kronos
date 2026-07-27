# ADP-001H — Provider Instrument Master Acquisition Capability and Contract

**Document ID:** ADP-001H
**Title:** Provider Instrument Master Acquisition Capability and Contract
**Version:** 1.0

**Status:** Approved

**Canonical Status:** Approved Canonical Architecture

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Owner:** Chief Architect

**Prepared By:** Codex Engineering Team

**Approved By:** Chief Architect

**Review Authority:** Not stated

**Repository Location:** `docs/architecture/products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md`

**Classification:** Architecture Documentation Package

**Architecture Impact:** Approved Provider-bounded acquisition capability, Provider Catalogue preservation, and EAIC-002 submission boundary for the Instrument Master dataset

**Engineering Impact:** None

**Runtime Impact:** None

## 1. Status and Governance

This document is the approved canonical Version 1.0 architecture for ADP-001H.

This migrated version aligns ADP-001H with ADR-007, ADR-008, ADR-009, MIG-001, EAIC-002, the migrated Provider and Instrument Domain architectures, the Domain Ownership Matrix, the Domain Dependency Matrix, and DATA_FLOW.

Nothing in this approval authorizes authentication, Instrument Master acquisition, Provider communication, implementation, an Engineering Design Document, an Engineering Package, or any runtime change.

ADR-009 is the governing acquisition architecture.

EAIC-002 is the sole governed Provider-to-Instrument submission boundary for Instrument Master.

The KRONOS Swing product placement of ADP-001H does not make Swing or any product the owner, scope source, prerequisite, or filter for Provider acquisition.

Canonical publication does not activate ADR-009 or EAIC-002. Their separate activation constraints remain unchanged.

## 2. Purpose

Define the governed Provider capability required to acquire the approved Instrument Master dataset, preserve it in the Provider Catalogue, and terminate at Provider-owned Submission Eligibility before the EAIC-002 Provider → Instrument boundary.

This architecture addresses one architectural question:

> Under what approved architectural conditions may Provider acquire the approved Instrument Master dataset, preserve Provider meaning and provenance in the Provider Catalogue, represent acquisition outcomes, and make acquired information eligible for submission through EAIC-002 without creating canonical Instrument identity, interpreting Instrument meaning, or granting downstream authority?

The Provider capability and its acquisition contract remain one bounded architecture document because the approved repository evidence requires one Provider-owned operation, its input conditions, its result meanings, and its exact termination boundary to be reviewed together. This architecture establishes no reusable acquisition framework.

## 3. Architectural Problem

ADP-001A classifies Instrument Master reference information for Swing but does not authorize or bound platform acquisition. ADR-007 and ADR-008 keep Provider Capability and Provider Entitlement independent from Dataset Permission and Acquisition Authority. ADR-009 governs Provider-bounded Instrument Master acquisition and Provider Catalogue preservation. EAIC-002 governs the sole Provider-to-Instrument submission boundary. ADP-001F and ADP-001G preserve Configuration and authentication boundaries while expressly withholding acquisition authority.

The first Instrument Master acquisition therefore requires architecture that:

- identifies one Provider-bounded and dataset-bounded capability;
- distinguishes dataset permission from Acquisition Authority;
- distinguishes authentication success from acquisition eligibility and acquisition success;
- preserves requested and received scope separately;
- represents complete, partial, missing, unsupported, and failed outcomes;
- preserves Provider meaning, Provider identifiers, Provider provenance, uncertainty, and ambiguity;
- prevents Provider acquisition from creating Instrument meaning; and
- ends before EAIC-002 receipt, contract validation, interpretation admission, or Instrument interpretation.

Without this architecture, a future implementation could silently treat connectivity as permission, treat a Provider response as complete, turn Provider records into canonical identity, or bypass the governed Provider → Instrument boundary.

## 4. Architectural Objective

**Approved architectural definition:** ADP-001H defines one read-only Provider capability for the approved Instrument Master dataset and one acquisition contract governing that capability's architectural preconditions, Provider-bounded scope, outcomes, Provider Catalogue preservation, provenance, and Submission Eligibility boundary.

The capability shall:

1. remain exclusively Provider-owned;
2. operate only within separately approved dataset permission and Acquisition Authority;
3. depend on, but never redefine, Configuration and authentication architecture;
4. preserve approved, requested, and received scope as distinct meanings;
5. preserve technical outcome distinctions;
6. keep acquired records external and non-canonical;
7. establish only Submission Eligibility for presentation through EAIC-002; and
8. terminate before EAIC-002 receipt, contract validation, interpretation admission, or Instrument interpretation begins.

## 5. Scope

This architecture defines only:

- Provider capability for Instrument Master acquisition;
- Provider Acquisition Authority;
- approved acquisition scope;
- requested acquisition scope;
- received acquisition scope;
- the Provider acquisition boundary;
- the Instrument Master acquisition contract;
- Provider Catalogue preservation;
- Provider-and-Dataset Catalogue Partition isolation;
- Provider Snapshot and Provider Record meaning;
- Provider record dispositions;
- Provider-owned acquisition outcomes;
- Provider record meaning;
- Provider identifiers;
- Provider provenance;
- acquisition provenance;
- acquisition eligibility;
- Submission Eligibility for EAIC-002;
- preservation of technical-operation meaning, Provider Availability context, partiality, emptiness, missingness, unsupported scope, failure, duplication, internal inconsistency, ambiguity, and uncertainty; and
- architectural termination before EAIC-002.

This architecture applies only to the approved Provider-bounded Instrument Master dataset.

Swing, Intraday, and future products consume canonical Instrument outputs only through separately approved explicit product-consumption boundaries. Their universes, eligibility, and demand do not bound Provider acquisition.

## 6. Out of Scope

This architecture shall not define, redesign, or authorize:

- Instrument identity or Instrument interpretation;
- Economic Instrument, Listed Instrument, or Derivative Contract construction;
- Provider mapping or Provider-to-canonical mapping meaning;
- Instrument classification or Instrument lifecycle;
- Observation creation, acceptance, ownership, publication, or lifecycle;
- Market interpretation, Market Schedule, Exchange Availability, or market-open status;
- Validation or Business Judgment;
- historical data, candles, quotes, volume, Open Interest, current market state, or market depth;
- Long Build-up, Short Build-up, Long Unwinding, or Short Covering;
- opportunity discovery, ranking, or research orchestration;
- BUY READY, SELL READY, BUY NOW, or SELL NOW;
- execution, orders, positions, portfolio behavior, or automated trading;
- TradingView integration;
- Futures OI, Options OI, quotes, historical data, streaming, market depth, option-chain data, or any separately governed Provider dataset;
- implementation, APIs, SDKs, provider endpoints, OAuth, payloads, schemas, or interfaces;
- retries, persistence, caching, batching, threading, polling, scheduling, or streaming;
- transport, serialization, storage, databases, repositories, or algorithms;
- authentication acquisition, browser login, token exchange, token refresh, or Authentication Material lifecycle;
- a generic Provider framework or a reusable platform-wide acquisition standard;
- an ADR, an Engineering Design Document, an Engineering Package, tests, or runtime code; or
- a follow-on architecture capability.

Instrument Master `last_price`, when supplied by a Provider, remains auxiliary Provider metadata under ADR-009. It is not part of Canonical Instrument Identity, is not Current Quote, shall never replace Observation-owned market state, and is not made submission-eligible by this architecture.

## 7. Definitions

| Term | Architectural meaning in this architecture |
| --- | --- |
| Instrument Master | The Provider reference dataset governed by ADR-009. ADP-001A historically classifies its Swing use, but that product classification does not bound Provider acquisition. Its records are external Provider reference material and are not canonical Instruments. |
| Instrument Master Acquisition Capability | The Provider-owned architectural capability to acquire the approved Instrument Master dataset through one bounded read-only acquisition operation. It defines no mechanism. |
| Instrument Master Acquisition Operation | The single conceptual read-only Provider operation governed by this capability. It is not an API, SDK call, endpoint, request format, sequence, or implementation. |
| Dataset Permission | Separately governed platform-scoped permission for the Instrument Master dataset to be in scope. It does not itself authorize acquisition. |
| Acquisition Authority | The operation-scoped architectural authority for Provider to perform the bounded Instrument Master Acquisition Operation. Canonical approval of ADP-001H shall never activate concrete Acquisition Authority. It remains distinct from Provider Capability, Provider Entitlement, Dataset Permission, authentication, implementation authorization, runtime authority, and acquisition success. |
| Approved Acquisition Scope | The maximum Provider, dataset, operation, Provider Context, environment, security, and authority boundary within which acquisition may be requested. It is not bounded by a product universe or inferred from Provider availability. |
| Requested Acquisition Scope | Provider-owned meaning describing what part of the Approved Acquisition Scope an acquisition seeks to obtain. It shall never exceed Approved Acquisition Scope. |
| Received Acquisition Scope | Provider-owned meaning describing what the Provider actually supplied, including explicit limits, omissions, and out-of-scope material where present. It shall never be silently equated with Requested Acquisition Scope. |
| Acquisition Eligibility | A Provider-owned architectural determination that all approved preconditions for the bounded acquisition are satisfied. It permits the acquisition to begin only when separately implemented and authorized; it does not mean an acquisition occurred or succeeded. |
| Acquisition Boundary | The Provider-owned architectural boundary beginning with approved acquisition intent and preconditions and ending with an Acquisition Outcome and, where present, acquired Provider records carrying Provider meaning and provenance. |
| Acquisition Contract | The normative architecture contract governing Provider-owned capability meaning, scope, preconditions, outcome distinctions, provenance obligations, and the Submission Eligibility boundary. It is not the physical Provider → Instrument interface, a transport contract, a runtime interface, or a communication contract. |
| Technical Acquisition Success | Provider-owned technical-operation meaning that the bounded acquisition operation completed without a technical failure and produced a Provider response. It does not establish any acquisition-coverage outcome, Provider record presence, completeness, Submission Eligibility, or downstream authority. |
| Acquisition Outcome | Provider-owned acquisition-coverage meaning explaining whether the Requested Acquisition Scope was completely received, partially received, empty, missing, unsupported, or failed. It is distinct from Technical Acquisition Success. |
| Empty Acquisition Outcome | A Provider-owned Acquisition Outcome meaning that the operation produced no Provider records. Empty may coexist with Technical Acquisition Success but does not establish completeness, Instrument non-existence, Provider unavailability, or Market unavailability. |
| Provider Availability | Provider-owned contextual meaning that the relevant approved Provider capability is available within a stated Provider and operational context. It is not an Acquisition Outcome and defines no runtime state. |
| Provider Unavailability | Provider-owned contextual meaning that the relevant approved Provider capability is unavailable within a stated Provider and operational context. It is not established by an Acquisition Outcome alone and defines no runtime state. |
| Provider Instrument Reference | Provider-owned external and non-canonical reference material, including Provider-specific identifiers and records, as defined by ADP-001B. |
| Provider Record | A Provider-owned record acquired within this capability that retains Provider meaning, Provider identifiers, Provider provenance, limits, uncertainty, and ambiguity. |
| Provider Catalogue | The first-class Provider-owned platform artifact composed of isolated Provider-and-Dataset Catalogue Partitions containing durable lineages of Provider Snapshots, Provider Records, dispositions, scope, currentness, supersession, and non-sensitive provenance. |
| Provider-and-Dataset Catalogue Partition | One strictly isolated Provider-and-dataset-bounded part of the Provider Catalogue. No identity, currentness, supersession, record, or Provider-native meaning crosses partitions. |
| Provider Snapshot | One immutable Provider-owned representation of acquired Provider Records and acquisition evidence within one Provider-and-Dataset Catalogue Partition. |
| Provider Snapshot Identity | Provider-owned identity unique only within one Provider-and-Dataset Catalogue Partition. |
| Provider Record Identity | Provider-owned identity unique only within one Provider Snapshot. It is not canonical Instrument identity. |
| Provider Record Disposition | Provider-owned structural, quality, quarantine, interpretation-support, and submission status meaning for one Provider Record. |
| Provider Identifier | A Provider-scoped identifier meaningful only within the issuing or supplying Provider context. It is not a permanent KRONOS identity. |
| Provider Meaning | The semantic meaning owned by Provider for Provider records, identifiers, metadata, provenance, capability, availability, acquisition activity, and technical outcomes. |
| Provider Provenance | Provider-owned origin and source context explaining from which approved Provider context a Provider record or outcome arose. |
| Acquisition Provenance | Provider-owned non-sensitive context explaining the approved acquisition intent, requested and received scope, request and receipt timing, source context, and Acquisition Outcome without exposing Authentication Material. |
| Submission Unit | One individual Provider record or one explicitly bounded subset of Provider records evaluated for Submission Eligibility. An acquisition operation and a received dataset as a whole are not Submission Units. |
| Submission Eligibility | A Provider-owned determination applied to one Submission Unit that the Provider Information in that unit may be presented through EAIC-002. It does not establish technical receipt, contract validity, interpretation admission, Instrument interpretation, canonical identity, Provider mapping, or product eligibility. |
| Submission Ineligibility | A Provider-owned determination applied to one Submission Unit that one or more required conditions for Submission Eligibility are not established. It defines no runtime disposition. |
| Interpretation Admission | The EAIC-002 boundary result that contract-valid Provider Information may enter Instrument interpretation. It is distinct from Submission Eligibility and does not imply interpretation success, canonical identity, Provider mapping, or product eligibility. |
| Partiality | A Provider-owned distinction meaning some, but not all, of the Requested Acquisition Scope was received. |
| Missingness | A Provider-owned distinction meaning an approved requested element was not present in the received result. Missingness is not zero, unsupported scope, Provider unavailability, or Instrument lifecycle meaning. |
| Unsupported Scope | A Provider-owned distinction meaning the Provider capability does not support some or all of the approved requested scope in the relevant Provider context. |
| Failed Acquisition Outcome | A Provider-owned acquisition-coverage outcome meaning dependable Received Acquisition Scope was not established. It produces no Submission Eligible Provider Information. Any associated information remains Provider-owned technical information only and shall never become Submission Eligible under ADP-001H. |
| Uncertainty | An explicit limit on what Provider Information or an Acquisition Outcome establishes. |
| Ambiguity | The presence of more than one possible Provider-context interpretation or the absence of one determinate Provider-context interpretation. |

These definitions establish architectural meaning only. They define no field, value, enumeration, payload, type, object, or runtime representation.

## 8. Governing Principles

### 8.1 Information crosses domains; meaning does not

Provider Information shall retain Provider meaning and ownership. Acquisition shall never convert a Provider record into Instrument meaning.

### 8.2 Permission, authority, eligibility, activity, and success are distinct

Provider Capability, Provider Entitlement, Dataset Permission, Acquisition Authority, Authentication Success, Acquisition Eligibility, the acquisition activity, Acquisition Outcome, Submission Eligibility, EAIC-002 receipt, contract validation, Interpretation Admission, and Instrument interpretation are separate architectural meanings.

No one meaning shall imply another unless approved architecture explicitly establishes the relationship.

### 8.3 Requested scope and received scope are distinct

A response shall never establish that the Requested Acquisition Scope was received completely. Completeness is an explicit Provider-owned acquisition outcome.

### 8.4 Provider records remain non-canonical

Provider identifiers, symbols, expiry assertions, exchange or segment vocabulary, reference values, and other Provider record content shall remain Provider-owned reference material until Instrument independently assigns Instrument meaning under approved architecture.

### 8.5 Acquisition is read-only

The capability shall acquire reference information only. It shall never modify Provider state, place or manage orders, mutate positions or holdings, or authorize any trading behavior.

### 8.6 Provider-neutral architecture

The capability shall be defined by Provider-owned architectural meaning, not by a particular SDK, endpoint, payload, vendor vocabulary, or transport. ADP-001A's expected Kite source does not make Kite-specific mechanics architectural.

## 9. Ownership

| Domain | Ownership preserved by ADP-001H |
| --- | --- |
| Provider | Instrument Master acquisition capability, acquisition activity, Provider records, Provider identifiers, Provider provenance, acquisition provenance, requested and received scope, Provider capability, Provider Availability and Provider Unavailability, Technical Acquisition Success and technical failure, Acquisition Outcomes, Acquisition Eligibility, Submission Eligibility, and Submission Ineligibility. |
| Configuration | Runtime Configuration meaning, Configuration Eligibility, Operational Configuration Validity, sensitive classification, lifecycle, approval for supply, and Configuration provenance. |
| Instrument | Canonical Instrument Identity, Instrument meaning, interpretation, classification, lifecycle, relationships, mapping meaning, and identity invariants. |
| Observation | Governed factual market state, Observation acceptance and ownership, factual provenance and lineage, and Observation semantics. |
| Market | Market Schedule, session meaning, and explicit Exchange Availability where approved. |
| Validation | Business Judgment. |

Provider also owns Provider Catalogue, Provider-and-Dataset Catalogue Partitions, Provider Snapshots, Provider Record Identity, Provider record dispositions, partition-scoped currentness, and non-destructive supersession.

Instrument owns interpretation processing status, interpretation outcome, canonical identity decision, Provider mapping status, cross-Provider reconciliation, and Canonical Instrument Catalogue publication.

Products own their product universes, product eligibility, and explicit consumption without acquiring Provider or Instrument ownership.

No shared ownership, ownership migration, or ownership duplication is introduced.

Provider shall never assume Instrument ownership. Instrument shall never assume Provider ownership.

Acquisition Contract ownership is not a second semantic ownership category. The contract governs the Provider capability and its termination boundary without owning Provider or Instrument meaning.

## 10. Responsibilities

### 10.1 Provider responsibilities

**Approved architectural definition:** Within this bounded capability, Provider shall:

1. establish that the capability and acquisition are architecturally eligible;
2. keep Requested Acquisition Scope within Approved Acquisition Scope;
3. distinguish Requested Acquisition Scope from Received Acquisition Scope;
4. preserve Provider records as external and non-canonical;
5. preserve Provider identifiers within Provider context;
6. preserve Provider provenance and Acquisition Provenance;
7. state the Provider-owned Acquisition Outcome;
8. preserve technical-operation meaning, Provider Availability context, partiality, emptiness, missingness, unsupported scope, failure, duplication, internal inconsistency, uncertainty, and ambiguity;
9. exclude out-of-scope information from Submission Eligibility;
10. determine Submission Eligibility without claiming EAIC-002 receipt, contract validity, Interpretation Admission, or Instrument meaning; and
11. terminate the capability before Instrument interpretation begins.

### 10.2 Provider non-responsibilities

Provider shall never:

- create, select, resolve, or validate canonical Instrument Identity;
- interpret Provider records as Economic Instruments, Listed Instruments, or Derivative Contracts;
- create or select Provider mappings;
- classify Instruments;
- assign Instrument lifecycle or mapping meaning;
- create Observations or Market Facts;
- assign Market Schedule or Exchange Availability meaning;
- perform Validation or research interpretation; or
- authorize downstream use.

### 10.3 Other-domain responsibilities

Configuration retains all Configuration meaning. Instrument retains all Instrument meaning. Observation, Market, and Validation retain their approved meanings and do not participate in this capability.

EAIC-002 independently governs technical receipt, contract validation, and Interpretation Admission before Instrument interpretation may begin.

## 11. Information Model

The conceptual information model contains only:

1. **Approved Acquisition Scope** — the externally governed maximum scope;
2. **Requested Acquisition Scope** — Provider-owned acquisition intent within that maximum;
3. **Received Acquisition Scope** — Provider-owned actual coverage;
4. **Provider Records** — external, non-canonical reference information, if received;
5. **Technical Operation Result** — Provider-owned meaning distinguishing Technical Acquisition Success from technical failure;
6. **Acquisition Outcome** — Provider-owned acquisition-coverage meaning;
7. **Provider Availability Context** — Provider-owned contextual Availability or Unavailability meaning, where separately established;
8. **Provider Provenance** — source and Provider context;
9. **Acquisition Provenance** — non-sensitive acquisition context;
10. **Preserved Limits** — partiality, emptiness, missingness, unsupported scope, failure, uncertainty, ambiguity, duplication, and internal inconsistency;
11. **Submission Unit** — one Provider record or explicitly bounded subset evaluated independently;
12. **Provider Catalogue State** — the applicable isolated partition, immutable snapshot, Provider Records, dispositions, currentness, supersession, and non-sensitive provenance;
13. **Submission Eligibility** — the Provider-owned determination governing presentation of one Submission Unit through EAIC-002; and
14. **Submission Ineligibility** — the Provider-owned determination that a Submission Unit shall not cross EAIC-002.

This model defines conceptual meanings only. It defines no schema, cardinality, identifier format, record shape, collection, status code, storage representation, or processing model.

## 12. Approved Acquisition Scope

### 12.1 Scope source

Approved Acquisition Scope shall be traceable to ADR-009, the exact approved Provider and Instrument Master dataset, and all separately governed capability, permission, context, authority, environment, and security boundaries.

It shall never be inferred from:

- Provider capability;
- Provider availability;
- Authentication Success;
- what a Provider happens to return;
- implementation convenience;
- existing SDK functionality; or
- a future consumer's request.

### 12.2 Instrument Master reference information

Instrument Master Provider Records may preserve safely representable Provider reference information including:

- Provider instrument token;
- trading symbol;
- exchange;
- segment;
- instrument type;
- instrument name or underlying reference;
- expiry where applicable; and
- source, scope, timing, outcome, partiality, missingness, unsupported information, and Provider limitations required to explain acquisition.

These categories retain Provider meaning under ADP-001H. Their presence does not itself authorize acquisition, establish canonical identity, or establish product eligibility.

### 12.3 Additional Provider reference information

Exchange token, lot size, tick size, and other safely representable Instrument Master information remain Provider-owned reference information. Their presence or omission shall preserve Provider meaning and shall not be interpreted through product demand.

### 12.4 Excluded information

The Approved Acquisition Scope shall exclude:

- Instrument Master `last_price` as a Current Quote or canonical identity element;
- Futures OI, Options OI, quotes, historical data, streaming, market depth, and option-chain data;
- Market Schedule and exchange availability;
- account identity, order permissions, market depth, streaming information, and corporate actions;
- raw Provider payloads, SDK objects, and Provider-private exceptions as contract information; and
- any separately governed Provider dataset outside Instrument Master.

If a Provider supplies excluded information incidentally, its presence shall be explicit in Received Acquisition Scope, it shall remain Provider-internal, and it shall never become submission-eligible under this capability.

### 12.5 Product independence

Approved Acquisition Scope is Provider-bounded and dataset-bounded.

It shall not be bounded by:

- Swing or Intraday universe membership;
- a current product universe;
- product eligibility;
- product demand;
- current strategy requirements;
- current execution markets; or
- implementation convenience.

Provider shall acquire broadly within the separately authorized Instrument Master dataset. Instrument shall interpret canonically. Products shall consume explicitly through separately governed product-consumption boundaries.

## 13. Requested and Received Scope

### 13.1 Requested Acquisition Scope

**Approved architectural definition:** Requested Acquisition Scope shall identify the approved Provider, approved Instrument Master dataset, approved operation, Provider Context, authority, environment, security boundary, and complete approved dataset sought without defining a physical request.

Requested Acquisition Scope shall:

- be bounded by Approved Acquisition Scope;
- exclude separately governed datasets and other out-of-scope information;
- remain independent from product universe and product eligibility;
- never imply that the Provider supports the request; and
- never imply that the requested information will be received.

### 13.2 Received Acquisition Scope

**Approved architectural definition:** Received Acquisition Scope shall explain the actual Provider-supplied coverage and its limits.

Received Acquisition Scope shall:

- remain distinct from Requested Acquisition Scope;
- make omissions and excess or out-of-scope material explicit;
- preserve Provider-specific limitations without making Provider vocabulary canonical;
- never convert an empty response into completeness;
- never convert Technical Acquisition Success into dataset completeness; and
- never establish Instrument acceptance or identity.

### 13.3 Scope comparison

The architectural comparison of requested and received scope establishes only Provider technical outcome meaning. It shall not perform Instrument classification, mapping, identity resolution, Validation, or Observation acceptance.

No comparison algorithm, rule engine, tolerance, ordering, or runtime procedure is defined.

## 14. Capability Semantics

### 14.1 Capability meaning

**Approved architectural definition:** Instrument Master Acquisition Capability means Provider is architecturally capable of performing the bounded read-only Instrument Master Acquisition Operation in an approved Provider context.

Capability shall never mean:

- Dataset Permission;
- Acquisition Authority;
- authentication;
- Provider availability;
- acquisition eligibility;
- acquisition success;
- dataset completeness;
- Submission Eligibility;
- EAIC-002 receipt, contract validity, or Interpretation Admission; or
- Instrument identity.

### 14.2 Capability boundary

The capability is specific to Instrument Master acquisition. It shall never authorize historical data, quote, OI, streaming, Market Schedule, or any other Provider operation.

This architecture shall never be treated as a generic acquisition abstraction or a precedent that authorizes another dataset.

### 14.3 Read-only operation

The Instrument Master Acquisition Operation is architecturally read-only. No Provider mutation, trading activity, order capability, position capability, holdings capability, or account-administration capability is within its meaning.

No endpoint, SDK method, request form, or Provider-specific mechanism is defined.

## 15. Acquisition Authority

ADP-001H defines the architectural meaning of Acquisition Authority. Canonical approval of ADP-001H shall never activate concrete Acquisition Authority for any acquisition.

Concrete Acquisition Authority requires separate Chief Architect approval of:

- the exact Provider;
- the exact Instrument Master dataset and operation;
- the exact Provider Context;
- the exact approved dataset scope;
- the exact operational environment;
- the exact security boundary; and
- the exact authority context.

Only after those concrete approvals exist may Acquisition Authority be bounded to:

- the Provider domain;
- one approved Instrument Master capability;
- one approved read-only dataset;
- one approved Provider context;
- one approved Configuration and authentication context;
- one approved operational environment and security context;
- Approved Acquisition Scope; and
- all exclusions and invariants in this architecture.

Acquisition Authority shall never be inferred from:

- ADP-001A classification alone;
- Configuration Eligibility;
- Operational Configuration Validity;
- Provider Usability;
- Authentication Eligibility;
- Authentication Success;
- an Authenticated Provider Context;
- Provider capability;
- Provider availability;
- a successful prior operation; or
- implementation existence.

Canonical approval of ADP-001H approves only the architectural definition and boundary. It does not activate concrete Acquisition Authority or authorize implementation, a runtime call, an EDD, an Engineering Package, or an acquisition.

## 16. Preconditions

**Approved architectural definition:** Acquisition Eligibility may be established only when all of the following are independently satisfied:

1. the Instrument Master dataset has separately approved Dataset Permission;
2. the exact Provider, dataset, and operation are approved;
3. the Instrument Master Acquisition Capability is approved;
4. concrete Acquisition Authority is separately approved for the exact Provider, dataset, operation, Provider Context, environment, security boundary, and approved scope;
5. Provider capability for the operation is established without treating capability as authority;
6. Configuration Eligibility and Operational Configuration Validity are established by Configuration where required;
7. Provider Usability is established by Provider where required;
8. any Authentication Activity is separately authorized under ADP-001G;
9. any Authenticated Provider Context is valid for the same approved Provider, account or authorization context, operating environment, authentication context, capability, Configuration approval context, lifecycle or effective context, sensitive classification, and operational boundary;
10. Requested Acquisition Scope is within Approved Acquisition Scope; and
11. product universe, product eligibility, and product demand are not used as acquisition preconditions; and
12. no unresolved authority, context, environment, security, or dataset boundary is being answered through implementation.

Failure of any precondition means Acquisition Eligibility is not established. It does not itself establish Configuration invalidity, Authentication Rejection, Provider unavailability, Market unavailability, or an Acquisition Outcome.

Acquisition Eligibility shall not be established while an unresolved authority, Provider Context, environment, security, or dataset boundary affects the concrete acquisition.

No detection method, evaluation sequence, runtime state, or enforcement mechanism is defined.

## 17. Relationship to Authentication

ADP-001H is downstream of ADP-001G. It shall never acquire Authentication Material, define authentication mechanics, or initiate an Authentication Activity.

**Approved architectural definition:** An Authenticated Provider Context may support the bounded Instrument Master Acquisition Operation only when:

- the context was established under separately authorized ADP-001G-conforming authentication;
- reuse is explicit for this capability;
- every ADP-001G reuse boundary remains satisfied;
- Configuration authority and Temporary Operational Custody remain unchanged;
- Authentication Material never enters acquisition information, provenance, outcomes, errors, or downstream information; and
- the context grants no Dataset Permission, Acquisition Authority, or acquisition success by itself.

This bounded use is not authentication authorization. It does not define session mechanics, credentials, tokens, renewal, refresh, persistence, transport, or cleanup.

## 18. Acquisition Boundary

The Acquisition Boundary begins only after Acquisition Eligibility has been established for approved acquisition intent.

It contains only:

- the bounded read-only acquisition activity;
- preservation of Requested Acquisition Scope;
- recognition of Received Acquisition Scope;
- Provider-owned acquired records where present;
- Provider-owned technical Acquisition Outcome;
- Provider Provenance and Acquisition Provenance; and
- preservation of Technical Acquisition Success or technical failure, Provider Availability context, partiality, emptiness, missingness, unsupported scope, failure, duplication, internal inconsistency, uncertainty, and ambiguity.

The Acquisition Boundary ends with:

- a Provider-owned Acquisition Outcome; and
- immutable Provider Catalogue preservation within one Provider-and-Dataset Catalogue Partition; and
- where applicable, Provider-owned information evaluated for Submission Eligibility to EAIC-002.

The boundary shall never extend into EAIC-002 receipt, contract validation, Interpretation Admission, or Instrument interpretation.

## 19. Acquisition Contract

The Instrument Master Acquisition Contract is a normative Provider-owned architecture contract governing acquisition capability, scope, outcomes, Provider Catalogue preservation, dispositions, provenance, and Submission Eligibility. It is not:

- the physical Provider → Instrument interface;
- a transport contract;
- a runtime interface; or
- a communication contract.

The Instrument Master Acquisition Contract shall:

1. identify Provider as the sole owner of the capability, activity, records, identifiers, provenance, scope meanings, technical outcomes, and eligibility meanings defined here;
2. require approved Dataset Permission and Acquisition Authority;
3. require Requested Acquisition Scope to remain within Approved Acquisition Scope;
4. preserve Requested and Received Acquisition Scope separately;
5. preserve Technical Acquisition Success or technical failure separately from acquisition coverage;
6. preserve Complete, Partial, Empty, Missing, Unsupported, and Failed outcome distinctions;
7. preserve Provider Availability and Provider Unavailability separately from Acquisition Outcome;
8. preserve Provider meaning and Provider provenance;
9. preserve non-sensitive Acquisition Provenance;
10. preserve uncertainty, ambiguity, duplication, and internal inconsistency;
11. exclude Authentication Material and sensitive configuration;
12. exclude out-of-scope information from Submission Eligibility;
13. prohibit identity creation and Instrument interpretation;
14. establish only Provider-owned per-Submission-Unit Eligibility or Ineligibility; and
15. preserve Provider Catalogue partition, snapshot, record, identity, disposition, currentness, and supersession meaning;
16. present eligible Provider Information only through EAIC-002; and
17. terminate before EAIC-002 receipt, contract validation, Interpretation Admission, or Instrument interpretation.

The contract defines normative architectural meaning only. It defines no runtime producer, runtime consumer, call direction, interface, payload, transport, event, storage, orchestration, or sequence.

## 20. Acquisition Outcomes

Technical Acquisition Success and Acquisition Outcome are separate Provider-owned architectural meanings.

**Approved architectural definition:** Technical Acquisition Success means only that the bounded acquisition operation completed without a technical failure and produced a Provider response. It shall never establish:

- that any Provider record was received;
- that Requested Acquisition Scope was covered;
- that a Complete outcome exists;
- that Provider is available beyond the stated operation and context;
- that any Provider Information is Submission Eligible; or
- that any downstream authority exists.

The following Acquisition Outcomes describe acquisition coverage rather than technical-operation success:

| Acquisition Outcome | Architectural meaning | Shall never imply |
| --- | --- | --- |
| Complete | The Received Acquisition Scope covers the Requested Acquisition Scope within the stated Provider context and known limits. | Correctness, canonical identity, Instrument acceptance, or absence of Provider limitations. |
| Partial | Some but not all Requested Acquisition Scope was received. | Completeness, failure of every requested element, or Instrument lifecycle meaning. |
| Empty | The operation produced no Provider records. Empty may coexist with Technical Acquisition Success. | Completeness, Instrument non-existence, Provider unavailability, Market unavailability, or successful coverage of Requested Acquisition Scope. |
| Missing | A specific approved requested element was not present in the received result. | Zero, unsupported scope, Provider unavailability, market closure, or non-existence of an Instrument. |
| Unsupported | The Provider capability does not support some or all approved requested scope in the relevant context. | Dataset prohibition, Market unavailability, Instrument invalidity, or Configuration invalidity. |
| Failed | The acquisition did not establish dependable Received Acquisition Scope. It produces no Submission Eligible Provider Information. Any associated information remains Provider-owned technical information only. | Configuration failure, Authentication Rejection, Provider unavailability, Market unavailability, absence of an Instrument, or any Submission Eligible unit. |

Outcome names are conceptual and define no runtime enumeration or state machine.

Technical Acquisition Success and Complete outcome are distinct. A technically successful operation may have a Complete, Partial, Empty, Missing, or Unsupported Acquisition Outcome. A Failed outcome does not establish Provider Unavailability and defines no automatic availability change.

A Failed Acquisition Outcome produces no Submission Eligible Provider Information because dependable Received Acquisition Scope was not established. Any information associated with a Failed outcome remains Provider-owned technical information only and shall never become Submission Eligible under ADP-001H.

### 20.1 Provider Availability and Provider Unavailability

Provider Availability and Provider Unavailability are Provider-owned contextual meanings about the relevant approved Provider capability within a stated Provider and operational context.

They shall remain separate from Acquisition Outcome:

- Provider Availability shall never imply Technical Acquisition Success, a Complete outcome, dataset completeness, or Submission Eligibility.
- Provider Unavailability shall never be inferred from an Empty, Missing, Unsupported, Partial, or Failed outcome alone.
- An Acquisition Outcome shall describe only the bounded acquisition result and shall never assign or alter Provider Availability meaning automatically.
- Provider Availability and Provider Unavailability shall never establish Market Availability, Market Schedule, Instrument existence, Observation readiness, or research readiness.

Provider availability and acquisition outcome are distinct. Market availability and acquisition outcome are distinct.

## 21. Outcome Preservation Rules

A Provider acquisition shall:

- preserve partiality rather than silently dropping missing scope;
- preserve an Empty outcome without treating technical success as completeness;
- preserve missingness rather than substituting zero or an empty value;
- preserve unsupported scope rather than representing it as failure or absence;
- preserve failure without exposing Provider-private exception meaning downstream;
- preserve the distinction between Technical Acquisition Success and acquisition coverage;
- preserve Provider Availability meaning separately from Acquisition Outcome;
- preserve known Provider limitations;
- preserve uncertainty about received content;
- preserve ambiguity in Provider records; and
- preserve the stated boundary of completeness.

An Acquisition Outcome shall never:

- create Provider Mapping State automatically;
- create or alter Instrument Lifecycle;
- establish Market Schedule or market-open status;
- establish Observation readiness or research readiness;
- establish Provider Availability or Provider Unavailability automatically;
- create Validation judgment;
- authorize fallback acquisition; or
- authorize retry, repair, enrichment, or substitution.

## 22. Provider Record Meaning and Provider Identifiers

Provider records acquired under this capability remain Provider Instrument References.

A Provider record shall:

- retain its Provider source and context;
- retain Provider-specific identifier meaning;
- retain explicit known limitations;
- remain external and non-canonical;
- remain distinguishable from Instrument-owned identity;
- remain distinguishable from Observation-owned factual market state; and
- cross into Instrument only through an EAIC-002-conforming Submission Unit after Submission Eligibility is established.

Provider identifiers shall never:

- become Economic Instrument, Listed Instrument, or Derivative Contract identity;
- become permanent KRONOS identifiers;
- silently establish mapping continuity;
- silently transfer historical attribution;
- establish lifecycle state;
- establish that two records identify the same Instrument; or
- establish that one record identifies a valid Instrument.

Provider tokens, exchange tokens, symbols, and row positions shall not, alone or by implication, establish globally permanent Provider Record Identity.

Provider Snapshot Identity is unique only within one Provider-and-Dataset Catalogue Partition.

Provider Record Identity is unique only within one Provider Snapshot.

No Provider-native identifier, Provider Snapshot Identity, Provider Record Identity, or Submission Unit identity shall establish canonical Instrument identity, cross-partition permanence, cross-snapshot permanence, or cross-Provider identity equivalence.

### 22.1 Minimum Provider meaning for a Submission Unit

**Approved architectural definition:** Every Submission Eligible Provider record shall retain, at minimum, the following conceptual Provider meaning:

- the approved Provider and Provider context from which it originated;
- its status as a Provider-owned, external, non-canonical Provider Instrument Reference;
- its Provider-specific identifier meaning where an identifier is present;
- its relationship to the applicable Requested and Received Acquisition Scope;
- its Provider Provenance and non-sensitive Acquisition Provenance;
- Technical Acquisition Success together with the applicable Acquisition Outcome and coverage limits;
- known Provider limitations; and
- explicit uncertainty, ambiguity, duplication, or internal inconsistency where present.

These are semantic obligations only. They define no schema, fields, values, payload, type, format, storage, or implementation.

### 22.2 Duplicate and internally inconsistent Provider records

Duplicate and internally inconsistent Provider records shall remain preserved as Provider-owned information. Provider shall never silently repair, merge, select, normalize, or discard them.

Such records may coexist in one acquisition and may remain Submission Eligible as individual Submission Units or as an explicitly bounded subset only when:

- the minimum Provider meaning in Section 22.1 remains attached to every record;
- duplication or internal inconsistency is explicit;
- Provider Provenance and Acquisition Provenance remain preserved;
- no record is represented as canonical, preferred, corrected, or authoritative Instrument meaning; and
- every other Submission Eligibility condition is independently satisfied.

Submission Eligibility for a duplicate or internally inconsistent Provider record does not resolve the duplication or inconsistency. EAIC-002 retains independent contract validation and Interpretation Admission, and Instrument retains interpretation, identity, and mapping decisions.

Where duplication or internal inconsistency cannot remain explicit, prevents the minimum Provider meaning from being established, or makes the Submission Unit's Provider provenance or scope indeterminate, the affected Provider information shall remain Submission Ineligible.

## 23. Provenance

### 23.1 Provider Provenance

Provider Provenance shall preserve enough architectural context to explain that a Provider record or outcome originated from the approved Provider and Provider context.

It shall never establish Instrument meaning, factual correctness, or Provider infallibility.

### 23.2 Acquisition Provenance

**Approved architectural definition:** Acquisition Provenance shall preserve conceptually:

- the approved Provider and acquisition context;
- the approved dataset and capability;
- Requested Acquisition Scope;
- Received Acquisition Scope;
- request time and receipt time as KRONOS acquisition timing;
- Acquisition Outcome;
- known Provider limitations;
- Technical Acquisition Success or technical failure, Provider Availability context, partiality, emptiness, missingness, unsupported scope, duplication, internal inconsistency, uncertainty, and ambiguity where present; and
- the applicable Configuration and authentication authority without containing Authentication Material.

Request time and receipt time are not exchange timestamps, observation timestamps, or Market Schedule facts.

No field set, identifier, correlation mechanism, payload, log, audit record, storage, persistence, or retention rule is defined.

### 23.3 Sensitive-information containment

Authentication Material, secrets, tokens used for authentication, credentials, and reconstructable sensitive values shall never enter:

- Provider records presented through EAIC-002;
- Provider Provenance;
- Acquisition Provenance;
- Acquisition Outcomes;
- errors or diagnostics;
- Instrument information;
- Observation provenance or lineage; or
- any downstream contract.

Provider instrument tokens remain Provider identifiers and shall not be confused with Authentication Material or canonical Instrument Identity.

## 24. Ambiguity and Uncertainty

Ambiguity and uncertainty shall remain explicit wherever the Provider record or Acquisition Outcome does not establish one determinate Provider-context meaning.

The capability and contract shall never:

- select one Instrument interpretation;
- infer a missing identifier or field;
- repair inconsistent Provider records;
- normalize Provider ambiguity into canonical certainty;
- treat multiple possible meanings as one identity;
- treat partiality as completeness;
- treat absence as non-existence;
- treat Provider vocabulary as canonical vocabulary; or
- suppress known Provider limitations.

Preserving ambiguity and uncertainty does not establish Submission Eligibility, EAIC-002 contract validity, Interpretation Admission, canonical identity, Provider mapping, or product eligibility.

## 25. Acquisition Eligibility

**Approved architectural definition:** Acquisition Eligibility is Provider's bounded determination that the approved preconditions in this architecture are satisfied for one approved Instrument Master Acquisition Operation.

Acquisition Eligibility shall never:

- grant Dataset Permission;
- create Acquisition Authority;
- establish Authentication Success;
- establish Provider availability;
- mean that an acquisition began;
- mean that information was received;
- establish an Acquisition Outcome;
- establish Submission Eligibility;
- establish EAIC-002 receipt, contract validity, or Interpretation Admission; or
- authorize Instrument interpretation.

Acquisition Eligibility ends when the approved acquisition context ends or when any required precondition no longer holds. This is an architectural boundary, not a runtime state transition or lifecycle mechanism.

Acquisition Eligibility shall not be established for a concrete acquisition while any unresolved authority or boundary affects:

- the Provider;
- the Instrument Master dataset or operation;
- the Provider Context;
- the approved dataset scope; or
- the approved environment, security, or authority context.

## 26. Submission Eligibility to EAIC-002

**Approved architectural definition:** Submission Eligibility applies independently to one Submission Unit: either one individual Provider record or one explicitly bounded subset of Provider records.

Submission Eligibility shall never apply to:

- the acquisition operation;
- Technical Acquisition Success;
- an Acquisition Outcome;
- Received Acquisition Scope as a whole; or
- the received dataset as an undifferentiated whole.

Eligible and ineligible Provider information may coexist within one acquisition. Eligibility of one Submission Unit shall never make another record, subset, operation, outcome, or dataset eligible.

Provider may determine one Submission Unit to be eligible for presentation through EAIC-002 only when:

- it arose from the approved Instrument Master Acquisition Capability;
- it arose from Technical Acquisition Success;
- it is within Approved Acquisition Scope;
- its Requested and Received Acquisition Scope remain distinguishable;
- its Provider source and Provider Provenance are preserved;
- its Acquisition Provenance is preserved without Authentication Material;
- Technical Acquisition Success together with the applicable Acquisition Outcome and coverage limits remains explicit;
- the applicable Provider Availability context, partiality, emptiness, missingness, unsupported scope, uncertainty, and ambiguity remains explicit;
- any duplication or internal inconsistency remains explicit and governed by Section 22.2;
- every Provider record in the Submission Unit retains the minimum Provider meaning defined by Section 22.1;
- it remains Provider-owned and non-canonical; and
- no out-of-scope information is represented as eligible.

Submission Eligible Provider records shall arise only from Technical Acquisition Success. A Failed Acquisition Outcome shall yield no Submission Eligible unit.

Submission Eligibility means only that Provider Information may be presented through the EAIC-002 governed contract boundary for independent technical receipt, contract validation, and Interpretation Admission.

Submission Eligibility shall never imply:

- technical receipt, contract validity, or Interpretation Admission;
- correctness;
- completeness beyond stated scope;
- Instrument acceptance;
- canonical identity;
- a valid Provider mapping;
- Instrument classification or lifecycle;
- Observation eligibility or ownership;
- Validation success;
- research readiness; or
- permission for any downstream runtime use.

No physical submission, Provider → Instrument runtime communication, interface, payload, transport, or consumer behavior is authorized.

## 27. Submission Ineligibility

**Approved architectural definition:** Provider information shall remain Submission Ineligible when any one of the following conditions applies to the Submission Unit:

1. it is outside Approved Acquisition Scope;
2. it did not arise from the approved Instrument Master Acquisition Capability;
3. the Provider or Provider context is not attributable;
4. minimum Provider meaning required by Section 22.1 is absent or indeterminate;
5. Provider Provenance or required non-sensitive Acquisition Provenance is absent or indeterminate;
6. Requested Acquisition Scope and Received Acquisition Scope cannot remain distinguishable;
7. Technical Acquisition Success is not established;
8. the applicable Acquisition Outcome or coverage limit is concealed;
9. partiality, emptiness, missingness, unsupported scope, failure, uncertainty, or ambiguity is silently removed;
10. duplication or internal inconsistency is silently repaired, merged, selected, normalized, discarded, or cannot remain explicit;
11. Authentication Material, sensitive configuration, or reconstructable sensitive information is present;
12. the information is raw Provider payload, an SDK object, or Provider-private exception meaning;
13. the information is represented as canonical identity, Instrument meaning, mapping meaning, Observation, Market meaning, Validation judgment, or downstream authority;
14. the Submission Unit is an acquisition operation, Technical Acquisition Success, Acquisition Outcome, Received Acquisition Scope as a whole, or an undifferentiated received dataset rather than a permitted Submission Unit; or
15. an applicable unresolved acquisition-scope dependency would be answered through submission; or
16. the Acquisition Outcome is Failed.

An Empty Acquisition Outcome contains no Provider records and therefore yields no Submission Unit. Empty remains a Provider-owned Acquisition Outcome and shall never be represented as Submission Eligible Provider Information.

Missing and Unsupported outcomes remain Provider-owned acquisition-result meanings. They are not Provider records and shall never become Submission Units by themselves.

A Failed Acquisition Outcome produces no Submission Eligible Provider Information because dependable Received Acquisition Scope was not established. Any information associated with a Failed outcome remains Provider-owned technical information only and shall never become Submission Eligible under ADP-001H.

Submission Ineligibility defines no deletion, quarantine, rejection mechanism, storage treatment, error procedure, retry, or runtime disposition.

## 28. Architectural Termination Before EAIC-002

ADP-001H ends after Provider determines Submission Eligibility or Submission Ineligibility for each Submission Unit. Only a Submission Eligible unit may be presented through EAIC-002; an ineligible unit terminates within Provider.

The conceptual boundary is:

```text
Approved Dataset Permission + Acquisition Authority
                         │
                         ▼
Provider Instrument Master Acquisition Capability
                         │
                         ├── Requested Acquisition Scope
                         ├── Received Acquisition Scope
                         ├── Acquisition Outcome
                         ├── Provider Catalogue Partition
                         ├── Provider Snapshot and Provider Records
                         ├── Provider Record Dispositions
                         └── Provider and Acquisition Provenance
                         │
                         ▼
              Submission Eligibility
                         │
              ADP-001H terminates here
═════════════════════════╪═════════════════════════
                         │
                         ▼
      EAIC-002 Provider → Instrument Boundary
                         │
                         ▼
       Technical Receipt and Contract Validation
                         │
                         ▼
              Interpretation Admission
                         │
                         ▼
       Possible Instrument interpretation
```

**Figure 1 — Conceptual ADP-001H acquisition and termination boundary.**

The figure is an architectural meaning model. It is not a runtime sequence, data-flow implementation, transport, call graph, process, or state machine.

The figure shows the eligible path. Submission Ineligible Provider information terminates inside the Provider boundary and does not cross EAIC-002.

ADP-001H shall never:

- decide EAIC-002 technical receipt, contract validation, or Interpretation Admission;
- begin Instrument interpretation;
- create Instrument Information;
- create canonical identity;
- create or select a mapping;
- define physical Provider → Instrument communication; or
- bypass EAIC-002.

## 29. Architectural Questions

The following twenty questions provide one-to-one traceability to the Chief Architect-authorized central question, eighteen scope items, and bounded-document decision. Every question has an explicit answer or is marked `Architecture dependency unresolved.`:

| # | Architectural question | Architecture answer | Status |
| --- | --- | --- | --- |
| 1 | Under what approved architectural conditions may Provider acquire the approved Instrument Master dataset, preserve it in the Provider Catalogue, and make acquired information eligible for submission through EAIC-002 without creating downstream meaning or authority? | Only when all Section 16 preconditions and separately approved concrete Acquisition Authority are established; acquisition retains Provider meaning, Provider Catalogue identity remains bounded as defined by ADR-009, and eligible Submission Units cross only through EAIC-002. Canonical approval of ADP-001H does not activate that authority. | Migrated to canonical Provider → Instrument architecture |
| 2 | What Provider capability is defined? | One Provider-owned, read-only Instrument Master Acquisition Capability bounded to the ADR-009 Instrument Master dataset. | Migrated to canonical dataset authority |
| 3 | What is Provider Acquisition Authority? | ADP-001H defines its architectural meaning only. Concrete authority requires separate Chief Architect approval of the exact Provider, dataset, operation, Provider Context, environment, security context, and authority reference. It does not derive from a product universe. | Migrated to canonical Provider acquisition authority |
| 4 | What is the approved acquisition scope? | It is bounded by approved Provider Capability, Provider-Reported Entitlement where applicable, Dataset Permission, operation-scoped Acquisition Authority, Provider Context, environment, security context, and the authorized Instrument Master dataset. Scope is Provider-and-dataset bounded and does not encode a product universe or product eligibility. | Migrated to canonical scope |
| 5 | What is Requested Acquisition Scope? | Provider-owned acquisition intent that shall remain within Approved Acquisition Scope and shall not imply support, receipt, or completeness. | Approved |
| 6 | What is Received Acquisition Scope? | Provider-owned actual coverage that preserves omissions, excess or out-of-scope material, and limitations without proving requested-scope completeness. | Approved |
| 7 | Where does the Acquisition Boundary begin and end? | It begins after Acquisition Eligibility and ends with Provider-owned results and Provider records, where present, evaluated as individual or bounded-subset Submission Units. | Approved |
| 8 | What does the Acquisition Contract govern? | It is the normative architecture contract governing Provider-owned capability meaning, preconditions, scope, technical-operation meaning, coverage outcomes, Provider Catalogue state, Provider records, provenance, preserved limits, Submission Eligibility, Submission Ineligibility, and termination before EAIC-002 technical receipt. It is not a physical interface, transport contract, runtime interface, or communication contract. | Migrated to canonical Provider and EAIC-002 boundaries |
| 9 | What Acquisition Outcomes are required? | Complete, Partial, Empty, Missing, Unsupported, and Failed are distinct Provider-owned acquisition-coverage meanings. | Approved |
| 10 | What meaning do Provider records retain? | Provider records remain Provider Instrument References carrying the minimum Provider meaning in Section 22.1; they are external and non-canonical. | Approved |
| 11 | What meaning do Provider identifiers retain? | Provider-scoped reference meaning only; they never become permanent KRONOS identity or establish mapping or lifecycle meaning. | Approved base |
| 12 | What Provider Provenance is required? | Provider source and Provider context remain attached conceptually to every Provider record and outcome without establishing Instrument meaning or Provider infallibility. | Approved base applied to this capability |
| 13 | What Acquisition Provenance is required? | Non-sensitive requested and received scope, acquisition timing, technical-operation meaning, coverage outcome, limitations, partiality, emptiness, missingness, unsupported scope, uncertainty, ambiguity, duplication, and inconsistency where applicable. | Approved |
| 14 | What is Acquisition Eligibility? | Provider's determination that all approved preconditions are satisfied; it is not authority, activity, Technical Acquisition Success, or coverage outcome. It shall not be established for a concrete acquisition while an unresolved dependency affects the Provider, dataset, operation, Provider Context, environment, security context, or authority reference. | Migrated to canonical acquisition boundary |
| 15 | What is Submission Eligibility? | A Provider-owned determination applied independently to one Provider record or explicitly bounded subset originating from Technical Acquisition Success; eligible and ineligible information may coexist in one acquisition, and eligibility does not establish EAIC-002 technical receipt, contract validation, Interpretation Admission, Instrument interpretation, or canonical identity. | Migrated to canonical EAIC-002 boundary |
| 16 | What Provider-owned technical outcome meaning is required? | Technical Acquisition Success or technical failure remains distinct from Complete, Partial, Empty, Missing, Unsupported, and Failed acquisition-coverage meanings and from Provider Availability or Unavailability. Submission Eligible Provider records shall arise only from Technical Acquisition Success. | Chief Architect-approved amendment |
| 17 | How is ambiguity preserved? | Ambiguity, including duplicate or internally inconsistent Provider records, remains explicit and shall never be silently repaired, merged, selected, normalized, discarded, or converted into Instrument certainty. | Approved |
| 18 | How is uncertainty preserved? | Known limits, incomplete scope, unsupported scope, technical limits, and indeterminate Provider meaning remain explicit and shall never be represented as certainty or completeness. | Approved base applied to this capability |
| 19 | Where does ADP-001H terminate? | Submission Ineligible information terminates inside Provider. For Submission Eligible information, ADP-001H terminates before EAIC-002 technical receipt; EAIC-002 then governs the complete Provider → Instrument submission boundary. | Migrated to canonical termination boundary |
| 20 | Shall the capability and Acquisition Contract remain one bounded architecture document? | Yes. Repository evidence requires the capability, its authority, preconditions, outcomes, provenance, and exact termination boundary to be governed together; no evidence requires separation. | Approved |

Any unresolved concrete acquisition dependency remains visible and shall not be resolved through product coupling, Provider-specific vocabulary, or implementation assumptions.

### 29.1 Unresolved dependency resolution

The Chief Architect has resolved the effect of unresolved acquisition-scope dependencies:

1. Canonical approval of ADP-001H may approve the architectural meaning and boundary defined by this document.
2. Canonical approval of ADP-001H shall never activate concrete Acquisition Authority.
3. Concrete Acquisition Authority requires separate approval of the exact Provider, dataset, operation, Provider Context, environment, security context, and authority reference required by repository governance.
4. Acquisition Eligibility shall not be established while an unresolved dependency affects any required concrete approval.
5. An EDD, Engineering Package, Provider communication, implementation, and Instrument Master acquisition remain unauthorized until their separate gates and approvals are satisfied.

Any unresolved Provider, dataset, operation, Provider Context, environment, security-context, or authority-reference dependency remains an architecture dependency for concrete acquisition authority and engineering. It does not become an implementation decision.

## 30. Architectural Invariants

The following invariants are normative and approved by the Chief Architect:

1. Instrument Master acquisition shall have one semantic owner: Provider.
2. Acquisition shall remain read-only.
3. Dataset Permission shall never imply Acquisition Authority.
4. Authentication Success shall never imply Acquisition Authority.
5. Acquisition Eligibility shall never imply acquisition activity or success.
6. Provider capability shall never imply Dataset Permission or Acquisition Authority.
7. Requested Acquisition Scope and Received Acquisition Scope shall remain distinct.
8. Technical Acquisition Success and acquisition coverage shall remain distinct.
9. Complete, Partial, Empty, Missing, Unsupported, and Failed outcomes shall remain distinct.
10. Empty may coexist with Technical Acquisition Success but shall never establish completeness.
11. Empty and Missing shall never mean zero or Instrument non-existence.
12. Partial, Empty, Missing, Unsupported, and Failed shall never establish Provider Unavailability.
13. Provider Availability and Provider Unavailability shall remain Provider-owned contextual meanings distinct from Acquisition Outcome.
14. Provider Availability or Provider Unavailability shall never establish Market availability.
15. Provider records shall remain external and non-canonical.
16. Provider identifiers shall never become permanent KRONOS identities.
17. Provider meaning and Provider provenance shall be preserved.
18. Acquisition Provenance shall remain non-sensitive.
19. Authentication Material shall never enter acquisition information or downstream provenance.
20. Information belonging to a separately governed dataset shall never become submission-eligible under the Instrument Master dataset authority.
21. Instrument Master `last_price` shall never become Canonical Instrument Identity, Current Quote, or Observation-owned market state through this capability.
22. Duplicate and internally inconsistent Provider records shall never be silently repaired, merged, selected, normalized, or discarded.
23. Submission Eligibility shall apply only to one Provider record or one explicitly bounded subset originating from Technical Acquisition Success and shall be determined independently for each Submission Unit.
24. Eligible and ineligible Provider information may coexist in one acquisition.
25. Submission Ineligibility shall apply whenever any consolidated condition in Section 27 is present.
26. Acquisition shall never create Instrument identity, classification, lifecycle, relationships, or mapping meaning.
27. Acquisition shall never create Observation, Market, Validation, research, or execution meaning.
28. Submission Eligibility shall never imply EAIC-002 technical receipt, contract validation, Interpretation Admission, Instrument interpretation, or canonical identity.
29. ADP-001H shall terminate before Instrument interpretation begins.
30. No physical Provider → Instrument runtime communication is authorized.
31. No unresolved architecture dependency shall be answered by implementation.
32. Reuse shall never transfer ownership or semantic authority.
33. Canonical approval of ADP-001H shall never activate concrete Acquisition Authority.
34. Concrete Acquisition Authority requires separately approved Provider, dataset, operation, Provider Context, environment, security context, and authority reference.
35. A Failed Acquisition Outcome shall yield no Submission Eligible unit.
36. Provider Catalogue identity shall remain isolated by Provider-and-Dataset Catalogue Partition.
37. Provider Snapshot Identity shall be unique only within one Provider-and-Dataset Catalogue Partition.
38. Provider Record Identity shall be unique only within one Provider Snapshot.
39. Provider-native identifiers, Provider Snapshot Identity, Provider Record Identity, and Submission Unit identity shall never establish canonical Instrument identity or cross-Provider identity equivalence.
40. Provider shall submit eligible information to Instrument only through EAIC-002.

These invariants define architecture only and prescribe no enforcement mechanism.

## 31. Explicit Prohibitions

The capability and contract shall never:

- acquire information outside Approved Acquisition Scope;
- treat Provider availability or returned information as Dataset Permission, Acquisition Authority, or approved dataset scope;
- acquire Futures OI, Options OI, Quotes, Historical Data, Market Depth, Streaming, Option Chain, or any other separately governed dataset under Instrument Master authority;
- treat raw Provider payloads or SDK objects as governed contract information;
- expose Provider-private exceptions or sensitive material;
- infer Instrument identity from a token, symbol, name, exchange, segment, type, expiry, price, or record presence;
- resolve record collisions or ambiguities;
- create Provider mappings or mapping effective context;
- infer lifecycle from missing, replaced, or unavailable Provider references;
- create canonical vocabulary from Provider vocabulary;
- convert `last_price` into Current Quote;
- create an Observation or factual market state;
- establish Market Schedule, market-open status, or Exchange Availability;
- validate, rank, score, interpret, or make a business decision;
- authorize historical data, quote, OI, streaming, execution, or trading behavior;
- define retries, fallback, substitution, repair, caching, persistence, scheduling, or orchestration;
- define implementation or select technology;
- create a new domain or business-pipeline dependency; or
- bypass EAIC-002 or populate Instrument directly.

## 32. Dependencies

ADP-001H depends on:

- ADR-009 for Provider-bounded acquisition, the Provider Catalogue, Provider-and-Dataset Catalogue Partition isolation, scoped Provider identity, and the `Acquire Broadly. Interpret Canonically. Consume Explicitly.` principle;
- EAIC-002 for the sole governed Provider → Instrument submission boundary;
- ADR-007 for Provider-scoped Capability Assessment;
- ADR-008 for account-scoped Provider-Reported Entitlement Assessment;
- MIG-001 for coordinated migration governance and the prohibition on partial activation;
- ADP-001A for historical Instrument Master inventory, read-only scope, provenance and outcome distinctions, and exclusions where those meanings remain consistent with canonical authority;
- ADP-001B for Provider Instrument Reference meaning, Provider identifier boundaries, Provider Mapping State separation, and Instrument ownership where those meanings remain consistent with canonical authority;
- ADP-001D for separation from Instrument → Observation attribution admissibility;
- ADP-001E for separation from Observation acceptance, ownership, factual semantics, provenance, and lineage;
- ADP-001F for Configuration Eligibility, Operational Configuration Validity, Provider Usability, Temporary Operational Custody, secret containment, and failure ownership;
- ADP-001G for Authentication Eligibility, Authentication Activity, Authentication Outcome, Authenticated Provider Context, reuse restrictions, and the mandatory acquisition-architecture prerequisite;
- PLATFORM-000 for domain identity, contract-based dependencies, single semantic ownership, platform-only domain communication, human-workflow independence, and architecture freeze;
- the Domain Ownership Matrix and Domain Dependency Matrix;
- the approved Configuration, migrated Provider, and migrated Instrument Domain architectures;
- ENGINE_OWNERSHIP and DATA_FLOW for preservation of existing engine ownership and paths; and
- ADR-006 solely to preserve the distinction between DOMAIN-006 Provider and the Execution Context Provider.

This architecture creates no business-domain dependency and does not amend the Domain Dependency Matrix. Provider remains a platform domain supplying approved support through governed contracts.

No runtime, transport, storage, SDK, endpoint, package, or implementation dependency is established.

## 33. Relationship to ADP-001A Through ADP-001G

| Canonical document | ADP-001H relationship |
| --- | --- |
| ADP-001A | Retains the approved Instrument Master inventory, outcome/provenance distinctions, read-only boundary, and exclusions where consistent with canonical Provider-and-dataset authority. Product classification does not govern Provider acquisition scope. |
| ADP-001B | Keeps Provider records and identifiers external, Provider-owned, and non-canonical. It does not create identity, classification, lifecycle, or mappings. |
| ADP-001C | Preserved as historical traceability. Its former Provider → Instrument boundary is superseded by ADR-009 and EAIC-002; Interpretation Admission and all Instrument interpretation remain Instrument-owned. |
| ADP-001D | Creates no attribution admissibility and no Instrument → Observation boundary behavior. |
| ADP-001E | Creates no candidate factual information, Observation acceptance, Observation ownership, factual provenance, or factual lineage. |
| ADP-001F | Consumes no Configuration meaning and preserves Configuration Eligibility, Provider Usability, Temporary Operational Custody, provenance, and secret containment. |
| ADP-001G | Depends on separately authorized authentication and permits only bounded context use consistent with all reuse restrictions. It does not authenticate or treat authentication as acquisition authority. |

ADP-001H is downstream of ADP-001G. Submission Ineligible information terminates within Provider; eligible information may cross only through EAIC-002. This relationship is architectural, not temporal runtime sequencing.

## 34. Conformance with Platform Architecture

This architecture conforms to:

- **CA-013 — Domain Identity** by preserving Provider, Configuration, Instrument, Observation, Market, and Validation as separate approved domains;
- **CA-014 — Responsibility Classes** by separating semantic ownership from technical capability and acquisition activity;
- **CA-015 — Contract-Based Dependencies** by defining a governed architectural contract without direct internal dependency;
- **CA-016 — Single Semantic Ownership** by assigning every meaning to exactly one approved owner;
- **CA-017 — Domain Communication (Platform Only)** by keeping Provider as platform support and creating no business-pipeline dependency;
- **CA-018 — Human Workflow Independence** by defining no human-operated runtime workflow;
- **CA-019 — Architecture Freeze** by introducing no domain, responsibility transfer, or dependency change.

Provider Integration remains distinct from ADR-006's Execution Context Provider. ADP-001H conforms to the migrated Domain Ownership Matrix, Domain Dependency Matrix, and DATA_FLOW without changing their authority.

## 35. Completeness and Determinism

The architecture is deterministic at the semantic level:

- every acquisition meaning has one owner;
- every scope meaning has a stated relationship;
- every outcome has a distinct architectural interpretation;
- every termination point is explicit;
- every excluded domain meaning remains outside the capability; and
- every unresolved dependency is visible.

Determinism does not prescribe an algorithm, ordering, runtime state machine, or implementation.

The architecture remains explainable because any acquisition must be traceable to approved capability, entitlement where applicable, permission, authority, scope, outcome, provenance, Provider Catalogue state, and the exact EAIC-002 boundary.

The Chief Architect has resolved the effect of unresolved dependencies in Section 29.1. Those dependencies remain blockers to concrete Acquisition Authority and subsequent engineering until their required concrete approvals exist.

## 36. ADR Determination

**ADR Recommendation:** No.

This architecture elaborates an explicitly authorized Provider capability within existing Provider ownership. It does not:

- add or remove a domain;
- transfer semantic ownership;
- alter the business pipeline;
- change the Domain Dependency Matrix;
- amend a constitutional decision or approved principle;
- redefine ADP-001A through ADP-001G; or
- introduce a platform-wide standard.

Any unresolved Provider, dataset, operation, context, environment, security, or authority-reference dependency requires governed resolution before concrete acquisition or implementation authority. It does not presently require another ADR unless resolving it would change frozen Platform architecture.

If resolving a dependency would change approved Platform ownership, dependencies, or constitutional architecture, the need for an ADR shall be reassessed separately.

## 37. Deferred Capabilities

This architecture defers:

- exact physical acquisition behavior;
- implementation design and technology;
- runtime realization of EAIC-002;
- Instrument interpretation and identity construction;
- Provider mapping and effective-context rules;
- Instrument lifecycle processing;
- historical data, quote, OI, and streaming acquisition;
- Observation, Market, Validation, research, and execution capabilities;
- persistence, retries, scheduling, fallback, and operations;
- a future EDD or Engineering Package; and
- selection of any follow-on architecture capability.

No deferral creates authority.

## 38. EDD Authorization Gate

ADP-001H authorizes no EDD.

**Approved architectural definition:** An EDD for the Instrument Master Acquisition Capability may be considered only after all of the following architectural conditions exist:

1. ADP-001H is approved canonical architecture.
2. The required Provider, dataset, operation, Provider Context, environment, security context, and authority reference have been separately approved under repository governance.
3. No unresolved architecture dependency affects the Provider, dataset, operation, Provider Context, environment, security context, or authority reference.
4. The exact Approved Acquisition Scope required for engineering is Provider-and-dataset bounded and approved without product-universe coupling.
5. Provider capability, Dataset Permission, concrete Acquisition Authority, Acquisition Eligibility, Technical Acquisition Success, Acquisition Outcomes, Provider Availability context, and Submission Eligibility remain distinctly governed.
6. Complete, Partial, Empty, Missing, Unsupported, and Failed outcome meanings are approved.
7. Submission Eligibility and Submission Ineligibility conditions, including duplicate and internally inconsistent Provider-record treatment, are approved.
8. Provider Provenance, non-sensitive Acquisition Provenance, and minimum Provider meaning obligations are approved.
9. ADP-001F and ADP-001G prerequisites remain satisfied without redefining Configuration or authentication meaning.
10. The termination boundary remains conformant with EAIC-002, and no runtime communication or activation authority has been inferred.
11. No additional ADR or Platform architecture change is required, or any required ADR or change has been separately approved.
12. The Chief Architect separately authorizes EDD preparation.

Satisfaction of these conditions shall never authorize implementation, an Engineering Package, Provider communication, or Instrument Master acquisition. Each requires separate authority under repository governance.

## 39. Approval Record

**Chief Architect Decision:** Approved

**Engineering Architect Verification:** Complete

**Canonical Status:** Approved Canonical Architecture

**ADR Required:** No

**Canonicalization Authorization:** Authorized

**Implementation Authorization:** None

**Authentication Authorization:** None

**Acquisition Authorization:** None

**Concrete Acquisition Authority:** Not Authorized

**Provider Communication Authorization:** None

**EDD Authorization:** None

**Engineering Package Authorization:** None

**Commit Authorization:** Authorized

**Push Authorization:** Authorized after successful commit verification

**Next Authorized Capability:** None

**Review History:** The Chief Architect authorized preparation of the first engineering Draft of ADP-001H. The Engineering Architect reviewed Version 0.1 and identified findings EA-001 through EA-010, which Version 0.2 addressed. The Chief Architect then approved ADP-001H with required amendments CA-001 through CA-005. Version 1.0 incorporates those amendments, has completed Engineering Architect verification, and is approved as canonical architecture. No concrete Acquisition Authority, acquisition, implementation, EDD, Engineering Package, or follow-on capability is authorized. Commit and push are authorized only for this canonicalization after successful verification.

## Related Approved Authority

- [ADP-001A — Swing Phase 1 Market Data Inventory](SWING-PHASE-1-MARKET-DATA-INVENTORY.md)
- [ADP-001B — KRONOS Swing Instrument Identity Architecture](SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md)
- [ADP-001C — Provider → Instrument Contract (historical traceability)](SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md)
- [ADP-001D — Instrument → Observation Contract](SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md)
- [ADP-001E — Observation Domain Architecture](SWING-PHASE-1-OBSERVATION-DOMAIN-ARCHITECTURE.md)
- [ADP-001F — Configuration → Provider Runtime Configuration Boundary](SWING-PHASE-1-CONFIGURATION-PROVIDER-RUNTIME-CONFIGURATION-BOUNDARY.md)
- [ADP-001G — Configuration → Provider Authentication Boundary](SWING-PHASE-1-CONFIGURATION-PROVIDER-AUTHENTICATION-BOUNDARY.md)
- [PLATFORM-000 — KRONOS Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [ADR-007 — Provider Capability Assessment Architecture](../../platform/domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md)
- [ADR-008 — Provider Entitlement Assessment Architecture](../../platform/domains/provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md)
- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [Configuration Domain](../../platform/domains/configuration/ARCHITECTURE.md)
- [Provider Domain](../../platform/domains/provider/ARCHITECTURE.md)
- [Instrument Domain](../../platform/domains/instrument/ARCHITECTURE.md)
- [KRONOS Engine Ownership](../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../DATA_FLOW.md)
- [ADR-006 — Execution Context Provider Architecture](../../adr/ADR-006-Execution-Context-Provider-Architecture.md)
